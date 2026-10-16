import sys,json,pathlib,numpy as np
root=pathlib.Path('/Users/changmin/projects/ugrp-wt/drive-friction');sys.path.insert(0,str(root))
from scripts.analyze_s2_pulse_calibration import extract
base=pathlib.Path('/Users/changmin/projects/ugrp/outputs');data={}
for seed,raw in [(1045,'s2-realism-f0bb26e7-s1045-P1-2-place'),(1046,'s2-realism-e619ee57-s1046-P1-2-place')]:
 rows,_=extract(base/raw);out=[]
 for prev,row in zip(rows,rows[1:]):
  if row['loaded'] and row['axis']=='forward' and row['u']==.35 and row['duration_s']==.1:
   out.append(dict(t=row['t'],gap=row['t']-prev['t']-prev['duration_s'],preceding_axis=prev['axis'],preceding_u=prev['u'],delta=row['delta']))
 q=[r for r in out if r['preceding_axis']=='forward' and r['preceding_u']==.35]
 if seed==1046:q=[r for r in q if r['t']<162.65] # before first checkpoint, report boundary explicitly
 data[str(seed)]=dict(n=len(q),scope='successive loaded +forward; s1046 before first checkpoint, s1045 whole saved carry',gap_quantiles_s=np.quantile([r['gap'] for r in q],[0,.5,1]).tolist(),forward_delta_quantiles_m=np.quantile([r['delta'][0] for r in q],[.05,.5,.95]).tolist())
result=dict(scope='offline only; no refit or causal ablation',groups=data,interpretation='Old fit cycles and new stopped-feedback cycles have different pre-pulse idle intervals; starting-state transfer is unqualified. This is a confound, not proof that the interval alone caused the residual.')
(base/'s2-realism-e619ee57-analysis/s1046-stop-intervals.json').write_text(json.dumps(result,indent=2)+'\n');print(json.dumps(result,indent=2))
