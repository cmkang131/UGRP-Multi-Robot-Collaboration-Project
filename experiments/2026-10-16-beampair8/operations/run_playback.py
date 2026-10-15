"""One extra recording-analysis slot, serial saved-state review, no physics steps."""
from pathlib import Path
import json,os,subprocess
from harness.grasp_act_data import read_json,write_json
ROOT=Path('/home/ugrp/ugrp-sim');OPS=ROOT/'ops-reviews/beampair8';SRC=ROOT/'src/72c0e83dab384b4f7d4bb73e37e440e0d1b248f6'
lease=ROOT/'leases/beampair8.json'
other=sum(read_json(p).get('concurrency',0) for p in lease.parent.glob('*.json') if p!=lease)
value=read_json(lease);assert other+17<=40 and value['task']=='beampair8'
value.update(concurrency=17,analysis_pid=os.getpid(),analysis='one saved-state renderer, no physics; serial3')
write_json(lease,value)
env={**os.environ,'PYTHONPATH':str(SRC),'MUJOCO_GL':'osmesa','OMP_NUM_THREADS':'1','OPENBLAS_NUM_THREADS':'1','LP_NUM_THREADS':'1'}
results=[]
try:
 for seed in [8328015,8328010,8328003]:
  run=ROOT/'runs'/f'beampair8-record-{seed}-72c0e83d'
  out=OPS/'playback'/str(seed);out.parent.mkdir(exist_ok=True)
  cmd=[str(ROOT/'ugrp/.venv-sim/bin/python'),str(OPS/'review_playback.py'),'--raw',str(run/'raw'),'--out',str(out)]
  subprocess.run(cmd,cwd=SRC,env=env,check=True)
  results.append(read_json(out/'review.json'))
 write_json(OPS/'playback-index.json',[{k:r[k] for k in ('seed','duration_sim_s','saved_eval_rows','video','video_bytes','video_sha256','original_own_rgb_frames_used','sheets')} for r in results])
finally:
 value=read_json(lease)
 if value.get('concurrency')==17:value['concurrency']=16
 value.pop('analysis_pid',None);value.pop('analysis',None);write_json(lease,value)
