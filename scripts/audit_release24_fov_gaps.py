from pathlib import Path
import json,sys,subprocess,bisect,numpy as np
sys.path.insert(0,'/home/ugrp/ugrp-sim/src/8b7f2f4517d827b39a79246b892fa549bbcec0a8')
from sim import release17,release15,release21
from sim.visible_belief import odometry
from sim.lookaround_localization import Camera
R=Path('/home/ugrp/ugrp-sim/runs');out=[]
def read(p):
 if not p.exists():p=p.with_suffix(p.suffix+'.zst')
 return subprocess.check_output(['zstd','-dc',str(p)]) if p.suffix=='.zst' else p.read_bytes()
for root in sorted(R.glob('r24d2-c-*-8b7f2f45')):
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
p=Path('/home/ugrp/ugrp-sim/ops-reviews/release24/fov-gaps.json');p.write_text(json.dumps(out,indent=2)+'\n');print(json.dumps(out))

# Derived supplement: preserve the original ledger and identify the nominal
# RGB/command projection; never use evaluator geometry or feed it to control.
table=p.parent/'rejection_table.json'
if table.exists():
 d=json.loads(table.read_text())
 for entry in d.get('rejection_records',[]):
  match=next((r for r in out if (r['run'],r['robot'],r['t'])==(entry['run'],entry['robot'],entry['t'])),None)
  if match:
   entry['raw_minimum_gap']=entry['minimum_gap'];entry.update(minimum_gap=match['minimum_gap'],basis=match['basis'],gap_derivation=str(p))
   entry.pop('gap_unknown_reason',None)
 d['fov_gap_reproduction']='cd /home/ugrp/ugrp-sim/src/8b7f2f4517d827b39a79246b892fa549bbcec0a8 && .venv-sim/bin/python /home/ugrp/ugrp-sim/ops-reviews/release24/fov_gaps.py'
 table.write_text(json.dumps(d,indent=2)+'\n')
