from pathlib import Path
import json,sys,subprocess,bisect,numpy as np
sys.path.insert(0,'/home/ugrp/ugrp-sim/src/8d24a525fc3e2d480050dc08788befd8f3d4fde4')
from sim import release17,release15,release21
from sim.visible_belief import odometry
from sim.lookaround_localization import Camera
R=Path('/home/ugrp/ugrp-sim/runs');out=[]
def read(p):
 if not p.exists():p=p.with_suffix(p.suffix+'.zst')
 return subprocess.check_output(['zstd','-dc',str(p)]) if p.suffix=='.zst' else p.read_bytes()
for root in sorted(R.glob('r23d3-*-8d24a525')):
 d=json.loads(read(root/'raw/result.json'));profile=d['effective_motion_profile']
 for check in d['line_rechecks']:
  rid=check['robot'];tr=[json.loads(l) for l in read(root/f'raw/teacher-{rid}.jsonl').splitlines()];tr=[v for v in tr if 't' in v];f=None
  for e in check['events']:
   if e.get('points'):f=e
   if e['event']!='release21_fov_blocked':continue
   row=min(tr,key=lambda v:abs(v['t']-e['t']));pwm={int(k):v for k,v in row['pwm'].items()};motion=e.get('proposed_motion')
   points=f['points'];basis='current observed own feature pixels (no proposal retained)'
   if motion is not None:
    w,ds,_=release17.yaw_pulse_for(*motion,profile);actual=odometry([v*t/.1 for v,t in zip(w,ds)],.1,profile)
    points=release15.project_motion(points,Camera(),pwm,actual);basis='nominal-plane predicted feature pixels from own RGB + issued PWM and floored proposed pulse'
   gap=release21.margin(points)
   out.append(dict(run=root.name,robot=rid,t=e['t'],reason_category='release21_fov_blocked',blocking_object='own camera FOV boundary',minimum_gap=gap,gap_unit='pixel',basis=basis,source_sha=d['source_sha'],raw=str(root/'raw/result.json.zst')))
p=Path('/home/ugrp/ugrp-sim/ops-reviews/release23/round3/fov-gaps.json');p.write_text(json.dumps(out,indent=2)+'\n');print(json.dumps(out))
