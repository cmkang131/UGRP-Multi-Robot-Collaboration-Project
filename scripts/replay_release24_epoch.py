from pathlib import Path
from bisect import bisect_right
import json,subprocess,math,sys
import numpy as np
from harness.zone_final_environment import resolve
from sim.global_landmark_localization import GlobalLandmarkMatcher
R=Path('/home/ugrp/ugrp-sim/runs');O=Path('/home/ugrp/ugrp-sim/ops-reviews/release24');rows=[]
def read(p):
 if not p.exists():p=p.with_suffix(p.suffix+'.zst')
 return json.loads(subprocess.check_output(['zstd','-dc',str(p)]) if p.suffix=='.zst' else p.read_bytes())
for name in ['r24d1-f-02-b20bb52a','r24d1-f-04-b20bb52a','r24d1-f-00-b20bb52a']:
 raw=R/name/'raw';d=read(raw/'result.json');plan=read(raw/'plan.json');static,_,_=resolve(plan['map_id'])
 for rid,r in d['lookaround_result'].items():
  loc=r['localizer'];vs=loc['views'];choices=[c for c in d['code_decisions'] if c.get('reason')]
  for j,c in enumerate(choices):
   if j<len(choices)-2:continue
   previous=choices[j-1]['t'] if j else -1
   current=[v for v in vs if previous<v['t']<=c['t']]
   if not current:continue
   command=current[-1]['command_pose'];matcher=GlobalLandmarkMatcher(static,localization_support='map_free_v1')
   fit=matcher.fit(current,command)
   full=matcher.fit([v for v in vs if v['t']<=c['t']],command)
   row=dict(run=name,rid=rid,t=c['t'],N=len(current),current=fit,all_history=full,
      evaluated_pose_at_last_view=min(r['evaluation']['views'],key=lambda e:abs(e['t']-current[-1]['t'])) if r['evaluation']['views'] else None)
   # Per-view evaluation is stored in eval-only, not the source input.
   rows.append(row)
   print(name,rid,round(c['t'],1),len(current),fit.get('accepted'),fit.get('proposed'),full.get('proposed'),flush=True)
for row in rows:
 raw=R/row['run']/'raw/eval-only.jsonl.zst'
 ev=[json.loads(v) for v in subprocess.check_output(['zstd','-dc',str(raw)]).splitlines()]
 e=[v for v in ev if v.get('kind')=='lookaround_view' and v.get('rid')==row['rid'] and v['t']<=row['t']][-1]
 row['evaluation_truth_at_view']=e['truth']
 for key in ('current','all_history'):
  q=row[key].get('proposed')
  if q:row[key+'_evaluation_error']=dict(xy_m=math.dist(q[:2],e['truth'][:2]),yaw_deg=math.degrees((q[2]-e['truth'][2]+math.pi)%(2*math.pi)-math.pi))
(Path(sys.argv[1]) if len(sys.argv)>1 else O/'epoch-replay.json').write_text(json.dumps(rows,indent=2)+'\n')
