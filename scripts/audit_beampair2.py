"""Read saved inputs on GCP; reconstruct observed worlds, never feed evaluator poses.

The exact command replay includes the beampair1 disturbance adapter. Its
clearance diagnostics use only that replay's own visible/issued world.
"""
import argparse
from collections import Counter
from copy import deepcopy
import hashlib
import json
import math
from pathlib import Path
import subprocess

from scripts.run_beampair1 import dependency_modules, profiles
from harness.beampair_teacher import PairRecoveryPerturb, perturb_model, defer_ready_during_probe


def load(path, lines=False):
    path=Path(path)
    data=path.read_bytes() if path.exists() else subprocess.check_output(['zstd','-qdc',str(path)+'.zst'])
    return [json.loads(x) for x in data.splitlines()] if lines else json.loads(data)


def replay(raw, dependency):
    plan=load(raw/'plan.json');result=load(raw/'result.json')
    frames=load(raw/'eval-only.jsonl',True)
    labels={r:load(raw/f'teacher-{r}.jsonl',True) for r in plan['roles']}
    audit_rows=[];states=[];mismatches=[]
    with dependency_modules(dependency):
        from harness.grasp_act_visible_world import VisibleWorld
        from harness.grasp_act_contract import IssuedClock
        from harness.grasp_act_start_sync import GraspStartSync
        from sim.grasp_act_teacher_v3 import VisibleOnlyGraspTeacher
        from sim.grasp_act_visible_route import free, constraints
        from scripts.zone_teacher import PeerDisc
        from harness.static_keepouts import rect_distance
        def clearance(t,w,goal,now,event):
            radius,discs,rects=constraints(w,t.rid,t.folded_ready)
            peers={r:v['pose'][:2] for r,v in w['robots'].items() if r!=t.rid}
            details=[]
            for d in discs:
                if isinstance(d,PeerDisc):name=min(peers,key=lambda r:math.dist(peers[r],d[:2]))
                else:
                    objects=w['objects']
                    name=min(objects,key=lambda k:math.dist(objects[k]['xy'],d[:2])) if objects else 'beam_1'
                    if math.dist(objects[name]['xy'],d[:2])>.1:name='beam_1'
                gap=math.dist(goal,d[:2])-d[2]-radius
                details.append(dict(blocked_object=name,min_gap_m=gap,reason_category='peer_goal' if isinstance(d,PeerDisc) else 'cargo_goal'))
            for j,r in enumerate(rects):
                details.append(dict(blocked_object=f'visible_wall_{j}',min_gap_m=rect_distance(goal,r)-radius,reason_category='wall_goal'))
            nearest=min(details,key=lambda d:d['min_gap_m'])
            audit_rows.append(dict(t=now,robot=t.rid,event=event,goal=list(goal),
                pose=w['robots'][t.rid]['pose'],phase=t.phase,peer_wait_since=t.peer_wait_since,
                peer_wait_ids=sorted(t.peer_wait_ids),fresh_peers=w['visibility'][t.rid]['peers'],
                peer_poses=peers,blocked=not free(goal,discs,rects,radius),**nearest,
                blockers=[d for d in details if d['min_gap_m']<0]))
        class Teacher(VisibleOnlyGraspTeacher):
            def _peer_route(self,w,goal,now):
                value=super()._peer_route(w,goal,now)
                clearance(self,w,goal,now,'peer_route')
                return value
        selected=profiles('baseline')
        for k in ('teacher_profile','self_pose_source','handoff_observation'):selected.pop(k)
        models={r:VisibleWorld(r,e,odometry=selected['search17_odometry'],search22=selected['search22'],search23=selected['search23']) for r,e in plan['roles'].items()}
        ts={r:Teacher(r,e,labels[r][0]['clean_teacher_command']['pwm'],bounds=(-20,20,-20,20),**selected) for r,e in plan['roles'].items()}
        perturb={r:PairRecoveryPerturb(perturb_model(plan['burst_ticks'] if r=='r1' else 13-plan['burst_ticks']),seed=plan['seed']+(r=='r2')) for r in ts}
        previous={r:labels[r][0]['clean_teacher_command'] for r in ts};clocks={r:IssuedClock() for r in ts}
        sync=GraspStartSync(plan['roles'],result['grasp_start_delays_s'])
        for i,f in enumerate(frames):
            now=f['t'];worlds={r:models[r].observe(f['visible_measurements'][r],now) for r in ts}
            permits=sync.tick({r:t.prepare_signal(worlds[r],now) for r,t in ts.items()},now)
            for r,t in ts.items():
                w=worlds[r];skill='wait' if t.phase=='ready' and not permits[r] else 'grasp'
                elapsed=clocks[r].observe((skill,t.end,t.handoff),now,previous[r]['pwm']);t.skill_started=now-elapsed['skill_elapsed_s']
                before=t.phase;before_t=t.phase_t;clean,done=t.step(w,now,permit_pick=permits[r])
                defer_ready_during_probe(t,before,before_t,perturb[r].active)
                actual,dist=perturb[r].apply(clean,phase_before=before,phase_after=t.phase,holding=False,
                    visible=any(m['id']=='band_'+t.end and m['visible_n']>=5 for m in f['visible_measurements'][r]))
                if dist:t.sink.pwm.update({int(k):v for k,v in actual['pwm'].items()});t.arm.commanded.update(t.sink.pwm)
                expected=labels[r][i]['applied_command']
                if actual['wheels']!=expected['wheels'] or actual['pwm']!=expected['pwm'] or any(abs(a-b)>1e-10 for a,b in zip(actual['duration_s'],expected['duration_s'])):
                    mismatches.append(dict(t=now,robot=r,tick=i))
                if t.peer_wait_since is not None and w['beam'] is not None:
                    clearance(t,w,t._geometry(w)[3],now,'encounter_tick')
                if i%10==0 or i==len(frames)-1:
                    states.append(dict(t=now,elapsed_sim_s=now-frames[0]['t'],robot=r,phase=t.phase,
                        outcome=t.outcome,peer_wait_since=t.peer_wait_since,own_pose=w['robots'][r]['pose'],
                        observed_peers={k:v for k,v in w['robots'].items() if k!=r},
                        fresh_peers=w['visibility'][r]['peers'],moving=any(actual['wheels'])))
                previous[r]=expected;models[r].issue(expected);t.remember_applied(expected)
                if done:t.done_recorded=True
        terminal={r:t.diagnostic() for r,t in ts.items()}
    counts=Counter((d['reason_category'],d['blocked_object']) for row in audit_rows for d in row['blockers'])
    return dict(raw=str(raw),source_sha=(raw.parent/'SOURCE_SHA').read_text().strip(),seed=plan['seed'],
        replay_command_N=len(frames)*len(ts),mismatch_N=len(mismatches),first_mismatches=mismatches[:3],
        reason_distribution=[dict(reason_category=k[0],blocked_object=k[1],count=v,
            min_gap_m=min(d['min_gap_m'] for row in audit_rows for d in row['blockers'] if (d['reason_category'],d['blocked_object'])==k)) for k,v in counts.most_common()],
        rows=audit_rows,states=states,terminal=terminal,
        scope='saved own visible measurements + issued commands only; post-divergence replay not a new physical trajectory')


if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('--raw',type=Path,required=True);p.add_argument('--dependency',type=Path,required=True);p.add_argument('--out',type=Path,required=True)
    a=p.parse_args();report=replay(a.raw,a.dependency);a.out.parent.mkdir(parents=True,exist_ok=True)
    a.out.write_text(json.dumps(report,indent=2,allow_nan=False)+'\n')
    print(json.dumps({k:v for k,v in report.items() if k not in ('rows','states','terminal')}))
