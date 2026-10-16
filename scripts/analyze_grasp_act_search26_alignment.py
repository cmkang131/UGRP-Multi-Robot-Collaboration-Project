"""GCP-only final visible/issued safety decomposition, no physics or truth."""
import json,math
from pathlib import Path
from scripts.replay_grasp_act_search18 import read,KW
from harness.grasp_act_visible_world import VisibleWorld,command_delta
from sim.grasp_act_teacher_v3 import VisibleOnlyGraspTeacher
from sim.grasp_act_search15_modes import ALL_MODES
from sim.grasp_act_goal_set import geometry
from sim.grasp_act_pregrasp import issued_sweep_reason
from sim.grasp_act_search23 import BodyNavigation
from sim.grasp_act_teacher import local,wrap
import argparse
ap=argparse.ArgumentParser();ap.add_argument('raw',type=Path);ap.add_argument('--out',type=Path,required=True);args=ap.parse_args();raw=args.raw
r=json.loads(read(raw/'result.json'));ev=[json.loads(x) for x in read(raw/'eval-only.jsonl').splitlines()];led=[json.loads(x) for x in read(raw/'teacher-r1.jsonl').splitlines()]
m=VisibleWorld('r1','blue',odometry=r['search17_odometry'],search22=r['search22'],search23=r['search23']);out=[]
for i,e in enumerate(ev):
 w=m.observe(e['visible_measurements']['r1'],e['t'])
 if i==len(ev)-1:
  pwm={int(k):v for k,v in led[i-1]['applied_command']['pwm'].items()};t=VisibleOnlyGraspTeacher('r1','blue',pwm,**KW,**{k:r.get(k,'off') for k in ALL_MODES});c=next(x['selected']['choice'] for x in reversed(r['teachers']['r1']['goal_set_log']) if x.get('selected'));t.approach_choice=tuple(c);t.staging_distance=c[1];t.phase='align';t.sampled_stance=True;t.search19_body_active=True
  pose,p,h,g=geometry(w,t.rid,t.end,c);x,y=local(pose,p);errors=(x-c[1],y,wrap(h-pose[2]))
  for axis in (2,0,1):
   d=[0.,0.,0.];d[axis]=(.9,.9,.8)[axis]*errors[axis];v=t._continuous(e['t'],*d,restore_ik=True);tests=[]
   for mode in ('off',r['search17_odometry']):
    nav=BodyNavigation(t,w);dx,dy,da=command_delta(v,.1,mode=mode);co,si=math.cos(pose[2]),math.sin(pose[2]);end=(pose[0]+co*dx-si*dy,pose[1]+si*dx+co*dy,pose[2]+da);ok=nav.pose_segment(pose,end);tests.append({'mode':mode,'delta':(dx,dy,da),'body_ok':ok,'blockers':nav.last_blockers})
   audit=[];reason=issued_sweep_reason(w,t.rid,pose,pwm,pwm,command_delta(v,.1),audit=audit);out.append({'axis':axis,'errors':errors,'command':v,'checks':tests,'arm_reason':reason,'arm_audit':audit})
 if i<len(led):m.issue(led[i]['applied_command'])
args.out.write_text(json.dumps(out,indent=2)+'\n');print(json.dumps(out))
