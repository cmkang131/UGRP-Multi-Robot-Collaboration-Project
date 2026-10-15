from pathlib import Path
from collections import Counter
from bisect import bisect_right
import json,subprocess,sys
sys.path.insert(0,'/home/ugrp/ugrp-sim/src/8d24a525fc3e2d480050dc08788befd8f3d4fde4')
from sim import release23 as new
from sim.release18 import GOAL_REGION
R=Path('/home/ugrp/ugrp-sim/runs');O=Path('/home/ugrp/ugrp-sim/ops-reviews/release23')
def read(p):
 if not p.exists():p=p.with_suffix(p.suffix+'.zst')
 return subprocess.check_output(['zstd','-dc',str(p)]) if p.suffix=='.zst' else p.read_bytes()
profiles={'baseline':{},'margin_only':{'margin_common_mode':new.MARGIN},'leg_only':{'release_leg_budget':new.LEG},'margin_plus_leg':{'margin_common_mode':new.MARGIN,'release_leg_budget':new.LEG}}
counts={k:Counter() for k in profiles};diffs={k:0 for k in profiles};N=0
for root in sorted([*R.glob('r21ag-*-46afd8b0'),*R.glob('r21bg-*-46afd8b0')]):
 d=json.loads(read(root/'raw/result.json'));tr={r:[json.loads(l) for l in read(root/f'raw/teacher-{r}.jsonl').splitlines()] for r in ('r1','r2')}
 for i,c in enumerate(d['code_decisions']):
  if not c.get('reason'):continue
  rows={}
  for r in tr:
   q=[v for v in tr[r] if 't' in v];v=q[bisect_right([v['t'] for v in q],c['t']+1e-7)-1];rows[r]=dict(v.get('report') or {},observation_epoch=i,observed_at=c['t'],zone_axis_width_m=1.4)
  if not all(v.get('kind')=='localized_margin' for v in rows.values()):continue
  N+=1;choices={}
  for k,p in profiles.items():
   v=new.pair_choice(rows,('r1','r2'),c['t'],goal_region=GOAL_REGION,lateral_recovery='bounded_v1',axis_recovery=True,**p)
   counts[k][v['action']+':'+v['reason']]+=1;choices[k]=(v['action'],v.get('shift_m'),v.get('lateral_shift_m'))
  for k in profiles:diffs[k]+=choices[k]!=choices['baseline']
result=dict(schema='ugrp.release23.saved_ablations.v1',scope='Saved same-round input decision replay only. Does not simulate changed trajectories; no physical causal attribution.',paired_observations=N,
 profiles={k:dict(options=v,choices=dict(counts[k]),changed_vs_baseline=diffs[k]) for k,v in profiles.items()},
 lateral_only=dict(old_rate_m_s=.08,new_rate_m_s=.122,yaw_rate_preserved_rad_s=1.05,validation='test_lateral_cal_changes_only_lateral_and_inverse_plans_match_propagation'),
 yaw_only=dict(saved_seed=88639,validation='test_saved_88639_keeps_cap_and_evaluates_lateral_then_fresh_rgb',physical_success=False),
 compute_only=dict(validation='No wall time in active planning modules; finite authored sweep check count'),
 reproduce='cd /home/ugrp/ugrp-sim/src/8d24a525fc3e2d480050dc08788befd8f3d4fde4 && .venv-sim/bin/python '+str(O/'ablate_saved.py'))
(O/'saved-ablations.json').write_text(json.dumps(result,indent=2)+'\n');print(json.dumps(result))
