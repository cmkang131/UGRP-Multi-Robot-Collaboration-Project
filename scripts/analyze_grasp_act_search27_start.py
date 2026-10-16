"""GCP-only visible/issued reconstruction around first invalid body start.

This is geometry reconstruction, NOT a full teacher replay or physics result.
Evaluator poses/objects never enter the constructed world.
"""
import argparse
from collections import deque
from copy import deepcopy
import hashlib
import json
from pathlib import Path

from scripts.analyze_grasp_act_search24 import read
from scripts.replay_grasp_act_search18 import KW
from harness.grasp_act_visible_world import VisibleWorld
from sim.grasp_act_teacher_v3 import VisibleOnlyGraspTeacher
from sim.grasp_act_search15_modes import ALL_MODES
from sim.grasp_act_search23 import BodyNavigation


def analyze(raw, out):
    d=json.loads(read(raw/'result.json'));plan=json.loads(read(raw/'plan.json'))
    ev=[json.loads(x) for x in read(raw/'eval-only.jsonl').splitlines()]
    rows=[]
    for rid,end in plan['roles'].items():
        labels=[json.loads(x) for x in read(raw/f'teacher-{rid}.jsonl').splitlines()]
        model=VisibleWorld(rid,end,odometry=d['search17_odometry'],search22=d['search22'],search23=d['search23'])
        previous_world=None
        modes={k:d.get(k,'off') for k in ALL_MODES};tail=deque(maxlen=3);last_motion=None
        for i,e in enumerate(ev):
            if i>=len(labels):break
            w=model.observe(e['visible_measurements'][rid],e['t'])
            before=labels[max(0,i-1)]['applied_command'];pwm={int(k):v for k,v in before['pwm'].items()}
            t=VisibleOnlyGraspTeacher(rid,end,pwm,**KW,**modes);nav=BodyNavigation(t,w)
            gaps,slack=nav.measure([nav.pose[:2]],nav.pose[2])
            band=w['visibility'][rid].get('observations',{}).get('band_'+end)
            item={'sample':i,'t':e['t'],'issued_pose':list(nav.pose),'issued_pwm':pwm,
                  'minimum_gap_m':float(gaps.min()),'blockers':nav.last_blockers,
                  'body_discs':nav.discs,'band':band,'fresh_band':band is not None and band['seen_t']>=e['t']-1e-8,
                  'command_before':before,'command_now':labels[i]['applied_command'],
                  'review_frame':str(raw/'eval-own'/rid/f'{i//10*10:06d}.jpg'),
                  'visible_measurements_sha256':hashlib.sha256(json.dumps(e['visible_measurements'][rid],sort_keys=True).encode()).hexdigest()}
            if bool((slack<0).any()):
                prev=tail[-1] if tail else None
                old_nav=BodyNavigation(t,previous_world) if previous_world else None
                crossed_old=(float(old_nav.measure([nav.pose[:2]],nav.pose[2])[0].min()) if old_nav else None)
                new_at_old=(float(nav.measure([prev['issued_pose'][:2]],prev['issued_pose'][2])[0].min()) if prev else None)
                rows.append({'old_geometry_at_new_issued_pose_gap_m':crossed_old,
                    'new_geometry_at_previous_issued_pose_gap_m':new_at_old,'rid':rid,'first_invalid':item,'before':list(tail),'last_nonzero_command':last_motion,
                    'issued_pose_changed':prev is not None and prev['issued_pose']!=item['issued_pose'],
                    'geometry_changed':prev is not None and prev['body_discs']!=item['body_discs']})
                break
            tail.append(deepcopy(item))
            if any(labels[i]['applied_command']['wheels']):last_motion=deepcopy(item)
            previous_world=deepcopy(w)
            model.issue(labels[i]['applied_command'])
    report={'raw':str(raw),'source_sha':d['source_sha'],'seed':plan['seed'],
        'scope':'visible+issued body reconstruction; no teacher hint/free-space cache replay; no physics',
        'reproduce':f'python -m scripts.analyze_grasp_act_search27_start {raw} --out {out}',
        'rows':rows}
    out.parent.mkdir(parents=True,exist_ok=True);out.write_text(json.dumps(report,indent=2)+'\n')
    print(json.dumps([{'rid':r['rid'],'t':r['first_invalid']['t'],'gap':r['first_invalid']['minimum_gap_m'],
        'pose_changed':r['issued_pose_changed'],'geometry_changed':r['geometry_changed']} for r in rows]))


if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('raw',type=Path);p.add_argument('--out',type=Path,required=True)
    a=p.parse_args();analyze(a.raw,a.out)
