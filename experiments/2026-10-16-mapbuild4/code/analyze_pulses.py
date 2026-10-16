import hashlib,json,sys
from pathlib import Path
import numpy as np
base=Path('/home/ugrp/ugrp-sim/runs/mapbuild4');out=base/'pulse-analysis-r1';out.mkdir(exist_ok=True)
model=json.load(open('/home/ugrp/ugrp-sim/src/mapbuild4-8ca00ad59/harness/data/s2_motion_v7_pulse_cal_v122.json'))
rows=[]
for backend in ['warp','cpu']:
 root=base/('pulse-'+backend+'-r1')
 if not (root/'metrics.json').exists():continue
 for r in json.load(open(root/'metrics.json')):
  delta=np.asarray(r['delta']);key=f"{int(r['pose']=='high')}:{r['axis']}:{r['u']:.2f}:{r['ms']/1000:.2f}"
  p=model['profiles'].get(key);pred=None if p is None else p['mean_delta']
  rows.append(dict(backend=backend,name=r['name'],axis=r['axis'],pose=r['pose'],u=r['u'],duration_ms=r['ms'],
     actual_mm=(1000*delta[:2]).tolist(),actual_deg=float(np.degrees(delta[2])),during_mm=(np.asarray(r['during_delta'][:2])*1000).tolist(),
     translation_mm=float(np.linalg.norm(delta[:2])*1000),wheel_rotation_rad=r['wheel_rotation'],
     subtree_com=r['subtree_com'],predicted_v122_mm=None if pred is None else (np.asarray(pred[:2])*1000).tolist(),
     prediction_qualification='missing_exact_profile' if p is None else 'unqualified_transfer' if p.get('transfer') else 'historical_CPU_fit',
     source=str(root/'metrics.json')))
(out/'matrix.json').write_text(json.dumps(rows,indent=2)+'\n')
print('\n'.join(f"{r['backend']:4s} {r['name']:25s} xy={r['actual_mm']} yaw={r['actual_deg']:.6f} wheels={np.round(r['wheel_rotation_rad'],4)}" for r in rows))
