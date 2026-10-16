import platform
assert platform.node().startswith("ugrp-sim-gcp2"), "gcp2-only analysis"
from pathlib import Path
import json,math,hashlib,subprocess
import numpy as np
def read(p):return p.read_text() if p.exists() else subprocess.check_output(['zstd','-dc',str(p)+'.zst'],text=True)
R=Path('/home/ugrp/ugrp-sim/runs');q=json.load(open(R/'reloc20-round2/queue.json'));data={}
# Freeze first180SIMs of stored exposures, before inspecting later outcomes.
for task in q['runs']:
 if task['kind']!='carry':continue
 raw=Path(task['raw']);cmd=[json.loads(x) for x in read(raw/'teacher-commands.jsonl').splitlines()];ee={round(x['t'],5):x for x in [json.loads(s) for s in read(raw/'eval-only.jsonl').splitlines()]};ww={round(x['t'],5):x for x in [json.loads(s) for s in read(raw/'drive-eval-only.jsonl').splitlines()]};values=[]
 for a,b in zip(cmd,cmd[1:]):
  if b['t']>180 or a.get('phase_before',a['phase'])!='carry_to_zone':continue
  wa,wb=ww.get(round(a['t'],5)),ww.get(round(b['t'],5));ea,eb=ee.get(round(a['t'],5)),ee.get(round(b['t'],5))
  if any(x is None for x in (wa,wb,ea,eb)):continue
  u,v,w,z=a['command']['wheels'];ds=a['command']['duration_s'];pure=abs(u)>1e-9 and abs(u+v)+abs(u-w)+abs(v-z)<1e-9 and max(ds)-min(ds)<1e-9
  obstruction=any(any(name and ('wall_' in name or 'cargo_beam' in name) for name in x['geoms']) for x in wa['contacts'])
  if not pure or obstruction:continue
  pred=b['map_pose']['last_nominal_delta'][2];true=(eb['base_yaw_rad']-ea['base_yaw_rad']+np.pi)%(2*np.pi)-np.pi;angles=np.array(wb['wheel_qpos_rad'])-np.array(wa['wheel_qpos_rad']);wheel=.0325*(-angles[0]+angles[1]-angles[2]+angles[3])/(4*.12435)
  values.append(dict(t=a['t'],end_t=b['t'],pred=pred,actual=true,wheel=wheel,dt=b['t']-a['t']))
 data[task['seed']]=dict(run=task['name'],raw=str(raw),samples=values)
train=data[93266]['samples'];gains={}
for name,sign in [('left',1),('right',-1)]:
 v=[x for x in train if x['pred']*sign>0];p=np.array([x['pred'] for x in v]);y=np.array([x['actual'] for x in v]);gains[name]=dict(N=len(v),scale=float(p@y/(p@p)),method='origin constrained least squares body delta on ODE delta; pure equal-duration held travel rotation only')
scores={}
for seed,d in data.items():
 v=d['samples'];old=np.array([x['pred']-x['actual'] for x in v]);new=np.array([x['pred']*gains['left' if x['pred']>=0 else 'right']['scale']-x['actual'] for x in v]);wheel=np.array([x['wheel']-x['actual'] for x in v]);scores[seed]=dict(N=len(v),role='calibration' if seed==93266 else 'validation_not_fitted',raw_local_yaw_p95_deg=float(np.percentile(abs(np.degrees(old)),95)),corrected_local_yaw_p95_deg=float(np.percentile(abs(np.degrees(new)),95)),raw_signed_yaw_residual_deg=float(np.degrees(old.sum())),corrected_signed_yaw_residual_deg=float(np.degrees(new.sum())),wheel_body_local_yaw_p95_deg=float(np.percentile(abs(np.degrees(wheel)),95)))
record=dict(schema='ugrp.reloc20_yaw_gain.v1',prefix_end_sim_s=180,calibration_seed=93266,validation_seed=93315,gains=gains,scores=scores,data=data,scope='retrospective DEV own-command mean fit; evaluator truth/contact only in offline sample selection and response. Runtime uses issued pure-turn commands and held command state only; no hardware or contact-point slip claim.')
p=R/'reloc20-prior/yaw-fit.json';p.write_text(json.dumps(record,indent=2)+'\n');print(json.dumps(dict(gains=gains,scores=scores),indent=2))
