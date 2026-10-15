"""Finite gcp2 validation of the exact graph schedule, shared-load RGB prefixes."""
import argparse,datetime,json,os,platform,subprocess,time
from pathlib import Path
if platform.system()!='Linux':raise RuntimeError('gcp2 only')
p=argparse.ArgumentParser();p.add_argument('--out',type=Path,required=True);a=p.parse_args()
root=a.out;root.mkdir(parents=True,exist_ok=False)
source=Path('/home/ugrp/ugrp-sim/src/90a25999')
runroot=Path('/home/ugrp/ugrp-sim/runs/warp1')
py='/home/ugrp/ugrp-sim/runs/simalt3/warp-env/bin/python'
env={**os.environ,'MUJOCO_GL':'osmesa','LP_NUM_THREADS':'1','OMP_NUM_THREADS':'1','OPENBLAS_NUM_THREADS':'1'}
# Administrative deadline leaves the already-installed four-hour guard intact.
deadline=datetime.datetime.fromisoformat('2026-10-15T21:56:00+00:00').timestamp()
rows=[]
for n in (16,64,256):
 if time.time()>=deadline:break
 out=runroot/f'bench-native-n{n}-prefix01'
 cmd=[py,'-u',str(source/'scripts/run_warp_act_teacher.py'),'--physics-backend','mjwarp_batch_v1','--teacher-source','/home/ugrp/ugrp-sim/src/warp1-teacher-snapshot-6f057f7e','--plan','/home/ugrp/ugrp-sim/pilot-plans.json','--nworld',str(n),'--out',str(out),'--compiled-reference-v1',str(runroot/'sleep-export-index0/compiled-312.json'),'--compiled-geometry-312-v1',str(runroot/'sleep-export-index0/compiled-geometry312.npz'),'--native-sleep-policy-compat-v1','--cap-s','0.1','--vm-hourly-usd','1.096']
 before=subprocess.check_output(['nvidia-smi','--query-compute-apps=pid,process_name,used_memory','--format=csv'],text=True)
 with (root/f'N{n}.log').open('x') as log:
  started=time.time();result=subprocess.run(cmd,env=env,stdout=log,stderr=subprocess.STDOUT)
 rows.append(dict(n=n,command=cmd,exit_code=result.returncode,started_epoch_s=started,ended_epoch_s=time.time(),gpu_before=before))
 (root/'measurement.json').write_text(json.dumps(dict(scope='one0.1SIMs RGB tick; shared GPU; no steady-state efficiency claim',rows=rows),indent=2)+'\n')
