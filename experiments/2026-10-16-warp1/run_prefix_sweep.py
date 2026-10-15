"""Finite gcp2-only RGB prefix measurements; not a teacher success gate."""
import json,os,subprocess,time
from pathlib import Path
import platform
if platform.system()!='Linux':raise RuntimeError('gcp2 only; no Mac simulator')
source=Path('/home/ugrp/ugrp-sim/src/49b436ce')
root=Path('/home/ugrp/ugrp-sim/runs/warp1')
py='/home/ugrp/ugrp-sim/runs/simalt3/warp-env/bin/python'
env={**os.environ,'MUJOCO_GL':'osmesa','LP_NUM_THREADS':'1','OMP_NUM_THREADS':'1','OPENBLAS_NUM_THREADS':'1'}
rows=[]
for n in (16,64,256):
 out=root/f'bench-n{n}-prefix01'
 cmd=[py,'-u',str(source/'scripts/run_warp_act_teacher.py'),'--physics-backend','mjwarp_batch_v1','--teacher-source','/home/ugrp/ugrp-sim/src/warp1-teacher-snapshot-6f057f7e','--plan','/home/ugrp/ugrp-sim/pilot-plans.json','--nworld',str(n),'--out',str(out),'--compiled-reference-v1',str(root/'export-osmesa-seed0/compiled-312.json'),'--compiled-geometry-312-v1',str(root/'export-osmesa-seed0/compiled-geometry312.npz'),'--cap-s','0.1','--vm-hourly-usd','1.096']
 before=subprocess.check_output(['nvidia-smi','--query-compute-apps=pid,process_name,used_memory','--format=csv'],text=True)
 started=time.time()
 with (root/f'bench-n{n}-prefix01.log').open('x') as log:
  result=subprocess.run(cmd,env=env,stdout=log,stderr=subprocess.STDOUT)
 rows.append(dict(n=n,command=cmd,exit_code=result.returncode,started_epoch_s=started,ended_epoch_s=time.time(),gpu_before=before))
 (root/'prefix-sweep.json').write_text(json.dumps(dict(scope='shared GPU, one0.1SIMs RGB tick; no steady-state or full-teacher efficiency verdict',rows=rows),indent=2)+'\n')
