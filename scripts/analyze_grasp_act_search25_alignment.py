"""Visible/issued-only endpoint readiness decomposition; no physics/replay."""
import argparse
import json
import math
from pathlib import Path
from harness.grasp_act_visible_world import VisibleWorld
from scripts.replay_grasp_act_search18 import read,KW
from sim.grasp_act_search15_modes import ALL_MODES
from sim.grasp_act_teacher_v3 import VisibleOnlyGraspTeacher
from sim.grasp_act_teacher import local,grasp_poses,wrap
from sim.grasp_act_goal_set import geometry
from sim.grasp_act_pregrasp import jaw_geometry,collision_reason,actual_pick_cloud
from sim.grasp_act_search23 import BodyNavigation
from harness.visual_arm_v3 import tool_pose


def analyze(raw,out,rid='r1'):
    res=json.loads(read(raw/'result.json'));plan=json.loads(read(raw/'plan.json'));end=plan['roles'][rid]
    ev=[json.loads(x) for x in read(raw/'eval-only.jsonl').splitlines()]
    led=[json.loads(x) for x in read(raw/f'teacher-{rid}.jsonl').splitlines()]
    m=VisibleWorld(rid,end,odometry=res['search17_odometry'],search22=res['search22'],search23=res['search23'])
    rows=[];history=res['teachers'][rid]['goal_set_log']
    for i,e in enumerate(ev):
        w=m.observe(e['visible_measurements'][rid],e['t'])
        chosen=next((h['selected'] for h in reversed(history) if h['t']<=e['t'] and h.get('selected')),None)
        if i>=len(ev)-15 and w['beam'] and chosen:
            choice=tuple(chosen['choice']);pose,point,h,g=geometry(w,rid,end,choice)
            x,y=local(pose,point);pwm={int(k):v for k,v in led[max(0,min(i-1,len(led)-1))]['applied_command']['pwm'].items()}
            t=VisibleOnlyGraspTeacher(rid,end,pwm,**KW,**{k:res.get(k,'off') for k in ALL_MODES})
            nav=BodyNavigation(t,w)
            audit=nav.candidate_audit(pose[:2],pose[2]);row={'t':e['t'],'phase':led[min(i,len(led)-1)]['teacher_phase'],
                'local_target_m':[x,y,point[2]],'choice':choice,'errors':[x-choice[1],y,wrap(h-pose[2])],
                'goal_error_m':math.dist(pose[:2],g),'visible_probes':w['visibility'][rid]['visible_probes'],
                'body_blockers':[a for a in audit if a['blocked']],
                'wheels':led[min(i,len(led)-1)]['applied_command']['wheels']}
            try:
                hover,desc=grasp_poses((x,y,point[2]));row['IK']='ok'
                offset=wrap(pose[2]+math.radians(tool_pose(desc[-1]).yaw_left_deg)-w['beam']['pose'][2]-(math.pi if end=='blue' else 0.))
                row['jaw']=jaw_geometry(offset,desc[-1]);arm=[]
                row['arm_reason']=collision_reason(w,rid,pose,*actual_pick_cloud(pwm,(x,y,point[2])),audit=arm)
                row['arm_blockers']=arm
            except ValueError as error:row['IK']=str(error)
            rows.append(row)
        if i<len(led):m.issue(led[i]['applied_command'])
    report={'raw':str(raw),'source_sha':res['source_sha'],'scope':'visible+issued reconstruction; no teacher cache replay or truth',
            'reproduce':f'.venv-sim/bin/python -m scripts.analyze_grasp_act_search25_alignment {raw} --out {out}',
            'rows':rows}
    out.parent.mkdir(parents=True,exist_ok=True);out.write_text(json.dumps(report,indent=2)+'\n')
    print(json.dumps(rows[-2:]))


if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('raw',type=Path);p.add_argument('--out',type=Path,required=True)
    a=p.parse_args();analyze(a.raw,a.out)
