"""Replay retrieved search11 inputs and ablate planner constraints; no World/render."""
import argparse
import hashlib
import json
import math
from pathlib import Path
from copy import deepcopy
from harness.grasp_act_contract import IssuedClock
from harness.grasp_act_start_sync import GraspApproachSync
from harness.grasp_act_visible_world import VisibleWorld, command_delta
from scripts.replay_grasp_act_nominal_handoff import verified
from scripts.replay_grasp_act_recovery import KW
from sim.grasp_act_teacher_v3 import VisibleOnlyGraspTeacher
from sim.grasp_act_priority import MODE, checked_path, beam_xy
from sim.grasp_act_visible_route import constraints, free, segment_free
from scripts.zone_teacher import plan_path, PeerDisc
from harness.static_keepouts import rect_distance

SOURCE='845a189072d0e82f4638b72a02f6f1bb33e8acc6'


def geometry_proof(w, t, goal):
    start=w['robots'][t.rid]['pose'][:2];r,ds,rs=t._constraints(w);_,bd,br=constraints(w,t.rid,t.folded_ready)
    sets={'all':(r,ds,rs),'no_peer_bodies':(r,[d for d in ds if not isinstance(d,PeerDisc)],rs),
          'no_reservations':(r,bd,br),'no_opposite_end_disc':(r,ds[:-1],rs),
          'no_side_rectangle':(r,ds,rs[:len(br)]+rs[len(br)+1:]),
          'no_parking_halfplane':(r,ds,rs[:-1]) if t.end=='teal' else (r,ds,rs)}
    proof={k:bool(checked_path(start,goal,t.bounds,cs)) for k,cs in sets.items()}
    path=plan_path(start,goal,t.bounds,ds,rects=rs,radius=r) or []
    pts=[start,*path,goal]
    bad=[]
    for a,b in zip(pts,pts[1:]):
        if not segment_free(a,b,ds,rs,r):
            bad.append({'from':a,'to':b,'discs':[i for i,d in enumerate(ds) if not segment_free(a,b,[d],[],r)],
                        'rectangles':[i for i,q in enumerate(rs) if not segment_free(a,b,[],[q],r)]})
    return {'world':deepcopy(w),'rid':t.rid,'end':t.end,'round':t.priority.round,'start':start,'goal':goal,
            'start_beam_xy':beam_xy(w,start),'goal_beam_xy':beam_xy(w,goal),'radius':r,
            'discs':[{'geometry':d,'peer':isinstance(d,PeerDisc),'start_clearance':math.dist(start,d[:2])-d[2]-r,'goal_clearance':math.dist(goal,d[:2])-d[2]-r} for d in ds],
            'rectangles':[{'geometry':q,'reservation':i>=len(br),'start_clearance':rect_distance(start,q)-r,'goal_clearance':rect_distance(goal,q)-r} for i,q in enumerate(rs)],
            'path_exists_by_ablation':proof,'unchecked_astar_path':path,'rejected_segments':bad}


class DiagnosticTeacher(VisibleOnlyGraspTeacher):
    def _route(self,w,goal,heading,now):
        before=self.no_path_calls;cmd=super()._route(w,goal,heading,now)
        if self.no_path_calls>before and not hasattr(self,'no_path_witness'):
            self.no_path_witness={'t':now,**geometry_proof(w,self,goal)}
        return cmd

    def _step(self,w,now,*,permit_pick):
        result=super()._step(w,now,permit_pick=permit_pick);self.before_guard=result[0];return result


def replay(raw):
    proof=[];p=json.loads(verified(raw,'plan.json',proof));res=json.loads(verified(raw,'result.json',proof));assert res['source_sha']==SOURCE
    labels={r:[json.loads(l) for l in verified(raw,f'teacher-{r}.jsonl.zst',proof).splitlines()] for r in p['roles']}
    rows=[{'t':v['t'],'measurements':v['visible_measurements']} for line in verified(raw,'eval-only.jsonl.zst',proof).splitlines() if (v:=json.loads(line))]
    prev={r:labels[r][0]['clean_teacher_command'] for r in labels};models={r:VisibleWorld(r,e) for r,e in p['roles'].items()}
    ts={r:DiagnosticTeacher(r,e,prev[r]['pwm'],**KW,approach_coordination=MODE) for r,e in p['roles'].items()}
    clocks={r:IssuedClock() for r in labels};sync=GraspApproachSync(labels,res['grasp_start_delays_s']);guard={};maxdelta=0.
    for i,row in enumerate(rows):
        now=row['t'];ws={r:models[r].observe(row['measurements'][r],now) for r in labels}
        permits=sync.tick({r:t.prepare_signal(ws[r],now) for r,t in ts.items()},now)
        for r,t in ts.items():
            skill='wait' if (t.phase=='ready' and not permits[r]) or (t.priority.waiting and (t.end=='teal' or t.priority.round==1)) else 'grasp'
            elapsed=clocks[r].observe((skill,t.end,t.handoff),now,prev[r]['pwm']);t.skill_started=now-elapsed['skill_elapsed_s']
            cmd,done=t.step(ws[r],now,permit_pick=permits[r]);expected=labels[r][i]['clean_teacher_command']
            delta=max(abs(a-b) for a,b in zip(cmd['duration_s'],expected['duration_s']));maxdelta=max(maxdelta,delta)
            assert all(cmd[k]==expected[k] for k in ('t','wheels','pwm')) and delta<=1e-12,(raw,i,r,'mismatch')
            assert done==labels[r][i]['done'] and t.phase==labels[r][i]['teacher_phase']
            if any(t.before_guard['wheels']) and not any(cmd['wheels']) and r not in guard:
                pose=ws[r]['robots'][r]['pose'];dx,dy,_=command_delta(t.before_guard,.1)
                end=(pose[0]+math.cos(pose[2])*dx-math.sin(pose[2])*dy,pose[1]+math.sin(pose[2])*dx+math.cos(pose[2])*dy)
                rad,discs,rects=t._constraints(ws[r]);_,_,base_rects=constraints(ws[r],r,t.folded_ready)
                guard[r]={'t':now,'phase':t.phase,'pulse_start':pose[:2],'pulse_end':end,
                    'blocking_discs':[{'index':j,'peer':isinstance(d,PeerDisc)} for j,d in enumerate(discs) if not segment_free(pose[:2],end,[d],[],rad)],
                    'blocking_rectangles':[{'index':j,'reservation':j>=len(base_rects)} for j,q in enumerate(rects) if not segment_free(pose[:2],end,[],[q],rad)],
                    **geometry_proof(ws[r],t,t._geometry(ws[r])[3])}
            t.remember_applied(labels[r][i]['applied_command']);prev[r]=labels[r][i]['applied_command'];models[r].issue(prev[r])
    return {'episode':int(raw.parent.name[-3:]),'sim_s':res['sim_s'],'physical_success':res['physical_success'],
            'verified_commands':len(rows)*len(labels),'max_duration_delta':maxdelta,'raw_proof':proof,
            'teachers':{r:{'end':t.end,'no_path':getattr(t,'no_path_witness',None),'first_pulse_guard':guard.get(r),
                'result':res['teachers'][r],'last_visible_local_distance_m':labels[r][-1]['local_distance_m'],
                'last_parking_signal':t.priority.signal(t,ws[r]),
                'last_park_distance_m':math.dist(ws[r]['robots'][r]['pose'][:2],t.priority.park_goal(ws[r],r)) if t.priority.park_x is not None else None,
                'last_visible_probes':ws[r]['visibility'][r]['visible_probes']} for r,t in ts.items()}}


def main():
    p=argparse.ArgumentParser();p.add_argument('--run',type=Path,required=True);p.add_argument('--out',type=Path,required=True);a=p.parse_args();rows=[]
    for i in range(13):
        row=replay(a.run/'diagnostic'/f'episode-{i:03d}'/'raw');rows.append(row)
        print(i,{r:{'no_path':v['no_path'] and v['no_path']['path_exists_by_ablation'],'guard':v['first_pulse_guard'] and v['first_pulse_guard']['phase']} for r,v in row['teachers'].items()},flush=True)
    result={'source_sha':SOURCE,'scope':'saved input replay; ablated paths are diagnostic geometry only, never control or physical success',
            'N':13,'physical_success_n':0,'verified_commands':sum(r['verified_commands'] for r in rows),'rows':rows}
    a.out.write_text(json.dumps(result,indent=2)+'\n')
if __name__=='__main__':main()
