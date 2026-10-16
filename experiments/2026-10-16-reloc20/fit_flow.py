import sys,json,subprocess,collections
from pathlib import Path
import numpy as np,cv2
sys.path.insert(0,'/home/ugrp/ugrp-sim/src/e042139b0930ee7b31eae08a917ff501ee01075f')
from harness.e2e_stall_odometry import flow_pair
R=Path('/home/ugrp/ugrp-sim/runs');rows=[]
def obj(p):return json.loads(p.read_bytes() if p.exists() else subprocess.check_output(['zstd','-dc',str(p)+'.zst']))
for seed in (93266,93315):
 raw=R/f'reloc19-r3-carry-A_pan-{seed}-e042139b'/'raw';ff=obj(raw/'playback/manifest.json')['frames']
 for a,b in zip(ff,ff[1:]):
  if b['t']-a['t']>.51:continue
  if seed==93315 and 43<=a['t']<=58.5:group='beam_onset'
  elif seed==93266 and 127<=a['t']<=144.5:group='wall_onset'
  elif (seed==93315 and 248<a['t']<256) or (seed==93266 and 294<a['t']<301):group='idle_loaded'
  elif 32<a['t']<42:group='free_loaded'
  else:continue
  aa=cv2.imread(str(raw/'playback'/a['files']['r1']));bb=cv2.imread(str(raw/'playback'/b['files']['r1']))
  assert aa.shape==(480,640,3),aa.shape
  d=flow_pair(cv2.cvtColor(aa,cv2.COLOR_BGR2RGB),cv2.cvtColor(bb,cv2.COLOR_BGR2RGB))
  rows.append(dict(seed=seed,t=a['t'],end_t=b['t'],group=group,**d))
idle=[x for x in rows if x['group']=='idle_loaded' and x['median_px'] is not None]
fit=dict(schema='ugrp.reloc20_flow.v1',scope='retrospective DEV2Hz pixel stationarity; not metric loaded VO',source_sha='e042139b0930ee7b31eae08a917ff501ee01075f',rows=rows,groups={g:dict(N=sum(x['group']==g for x in rows),quantiles={k:np.percentile([x[k] for x in rows if x['group']==g and x[k] is not None],[50,95,99]).tolist() for k in ('median_px','p90_px','mean_abs_diff')}) for g in sorted({x['group'] for x in rows})},stationary_thresholds={k:float(np.percentile([x[k] for x in idle],99)) for k in ('median_px','p90_px','mean_abs_diff')},basis='p99 of terminal loaded idle windows; detector additionally requires original LK tracks/cells and >=.05m independent command in <=1.4SIMs; calibration not held-out')
o=R/'reloc20-prior/flow-fit.json';o.write_text(json.dumps(fit,indent=2)+'\n');print(json.dumps({k:fit[k] for k in ('groups','stationary_thresholds')},indent=2))
