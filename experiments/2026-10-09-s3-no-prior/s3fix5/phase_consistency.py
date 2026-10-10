"""Post-hoc eval only; no fitting or runtime feedback."""
import json,hashlib
from pathlib import Path
import numpy as np
B=Path(__file__).parent
R=B.parent/'s3-sweep-b73ce193-s14201-v149'
truth=[json.loads(s) for s in (R/'eval_only/r2/trajectory.jsonl').read_text().splitlines()]
ts=[q['t'] for q in truth];xy=np.array([q['robot_xyz_m'][:2] for q in truth])
result={'scope':'posthoc diagnostic windows; not causal proof or tuning','gt_use':'eval_only','variants':{}}
for label in ['off','on']:
 p=B/f'replay-{label}/state.json';poses=json.loads(p.read_text())['r2']['poses']
 poses=[p for p in poses if p['t_est']>=13.34-1e-8]
 at=np.array([p['t_est'] for p in poses]);est=np.array([[p['x'],p['y']] for p in poses]);sigma=np.array([p['std_xy_m'] for p in poses]);actual=np.array([np.interp(at,ts,xy[:,j]) for j in range(2)]).T
 error=np.linalg.norm(est-actual,axis=1)
 windows={}
 for name,lo,hi in [('pre_contact',13.34,102.55),('contact_period',102.55,210.05),('after_contact',210.05,276.)]:
  selected=(at>=lo-1e-8)&(at<hi-1e-8)
  windows[name]={'bounds':[lo,hi],'frames':int(selected.sum()),'error_end':float(error[selected][-1]),'sigma_end':float(sigma[selected][-1]),'over_3sigma':int((error[selected]>3*sigma[selected]).sum()),'rmse':float(np.sqrt((error[selected]**2).mean()))}
 result['variants'][label]={'windows':windows,'prediction_sha256':hashlib.sha256(p.read_bytes()).hexdigest()}
(B/'phase-consistency.json').write_text(json.dumps(result,indent=2)+'\n')
print(json.dumps(result,indent=2))
