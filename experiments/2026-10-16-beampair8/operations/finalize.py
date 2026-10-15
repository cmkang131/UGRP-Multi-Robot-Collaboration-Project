"""Finite completion dependency: analyze/package only the completed200 attempts."""
from pathlib import Path
import importlib.metadata
import json,os,platform,subprocess,time
from harness.grasp_act_data import read_json,write_json,sha256

ROOT=Path('/home/ugrp/ugrp-sim');OPS=ROOT/'ops-reviews/beampair8';SRC=ROOT/'src/72c0e83dab384b4f7d4bb73e37e440e0d1b248f6'
BATCH=OPS/'record200-72c0e83d';PY=ROOT/'ugrp/.venv-sim/bin/python'
while not (BATCH/'DONE.json').exists():time.sleep(5)
done=read_json(BATCH/'DONE.json')
assert len(done['completed'])==200 and not done['not_started'], 'incomplete collection: root agent must investigate before packaging'
lease=ROOT/'leases/beampair8.json';v=read_json(lease)
v.update(pid=os.getpid(),concurrency=1,stage='offline_dataset_analysis',expected_end='bounded audit + tensor conversion + lossless archive verification')
write_json(lease,v)
env={**os.environ,'PYTHONPATH':str(SRC),'OMP_NUM_THREADS':'1','OPENBLAS_NUM_THREADS':'1'}
try:
 versions={}
 for name in ('mujoco','numpy','opencv-python','opencv-python-headless','pillow'):
  try:versions[name]=importlib.metadata.version(name)
  except importlib.metadata.PackageNotFoundError:pass
 write_json(OPS/'environment-recording-v2.json',dict(python=platform.python_version(),platform=platform.platform(),
  packages=versions,execution_source_sha=SRC.name,dependency_sha='26f84d0f0ada1c33473c83cca2d3415ce51bd247',
  host=read_json(OPS/'gate-proof.json')['execution_host'],backend='C MuJoCo CPU',
  operations={p.name:sha256(p) for p in OPS.glob('*.py')}))
 subprocess.run([str(PY),str(OPS/'analyze_cohort.py'),'--batch',str(BATCH),'--out',str(OPS/'cohort-analysis-v2')],cwd=SRC,env=env,check=True)
 subprocess.run([str(PY),str(OPS/'prepare_dataset.py'),'--batch',str(BATCH),'--output',str(OPS/'dataset-v1'),
  '--heldout',str(OPS/'heldout-plan.json'),'--convert'],cwd=SRC,env=env,check=True)
 summary=read_json(OPS/'dataset-v1/summary.json')
 write_json(OPS/'FINALIZED.json',dict(status=summary['status'],n=summary['n'],N=summary['N'],
  summary=str(OPS/'dataset-v1/summary.json'),summary_sha256=sha256(OPS/'dataset-v1/summary.json'),
  archive=summary['dataset']['archive'],host='gcp2'))
finally:
 v=read_json(lease);v.update(concurrency=0,stage='Mac summary retrieval/verification');write_json(lease,v)
