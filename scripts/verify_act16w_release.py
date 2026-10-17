"""Public native model download, full inventory and CPU loading on owned L4.

Invoke from a clean fresh checkout containing the registry, using the existing
qualified ACT environment. This verifies distribution/loading, not a clean venv,
new physics, task success, or raw training-data backup.
"""
import argparse
from datetime import datetime, timezone
import json
import os
from pathlib import Path
import subprocess
import sys

from act16w_runtime import require_gcp2, frozen_source, sha256
from model_artifacts import load_registry, fetch, verify_directory

ROOT=Path(__file__).resolve().parents[1]
B=Path('/home/ugrp/ugrp-sim')


def main():
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('--out',type=Path,required=True);a=p.parse_args()
    host,source=require_gcp2(training=True),frozen_source(ROOT)
    registry=load_registry(ROOT)
    wanted={f'act16w-native-v1-{arm}-step10000-20261016' for arm in ('a','b','c','d1')}
    rows=[row for row in registry['artifacts'] if row['id'] in wanted]
    if {row['id'] for row in rows}!=wanted:raise ValueError('all four native registry models required')
    a.out.mkdir(parents=True,exist_ok=False)
    lease=B/'leases'/f'act16w-release-verify-{os.getpid()}.json'
    with lease.open('x') as f:
        json.dump(dict(task='act16w-release-verify',pid=os.getpid(),start=datetime.now(timezone.utc).isoformat(),
            expected_end='four public assets and CPU loading; no wall cap',concurrency=0),f)
    results=[]
    try:
        for row in rows:
            destination=a.out/'models'/row['id']
            downloaded=fetch(row,destination)
            verified=verify_directory(row,destination)
            command=[sys.executable,str(destination/'inference/load_model.py')]
            env={**os.environ,'CUDA_VISIBLE_DEVICES':'','OMP_NUM_THREADS':'1','OPENBLAS_NUM_THREADS':'1','PYTHONDONTWRITEBYTECODE':'1'}
            proc=subprocess.run(command,env=env,stdout=subprocess.PIPE,stderr=subprocess.PIPE,text=True)
            (a.out/(row['id']+'-load.stdout')).write_text(proc.stdout)
            (a.out/(row['id']+'-load.stderr')).write_text(proc.stderr)
            if proc.returncode:raise RuntimeError('public model CPU loading failed '+row['id'])
            response=json.loads(proc.stdout.strip().splitlines()[-1])
            if response.get('ready') is not True or response.get('device')!='cpu':
                raise ValueError('explicit CPU ready receipt required')
            results.append(dict(id=row['id'],release=row['release'],archive=row['archive'],
                public_anonymous_download=True,full_inventory_verified=verified,
                fetched=downloaded,loading=response,loading_exit_code=proc.returncode,
                loader_sha256=sha256(destination/'inference/load_model.py')))
            (a.out/'progress.json').write_text(json.dumps(dict(models=results,complete=False),indent=2)+'\n')
        report=dict(status='complete',complete=True,utc=datetime.now(timezone.utc).isoformat(),host=host,
            fresh_checkout=str(ROOT),fresh_checkout_sha=source,registry_sha256=sha256(ROOT/'configs/model_artifacts.json'),
            interpreter=sys.executable,models=results,
            scope='fresh clean checkout, public re-download/full archive+file hashes, existing ACT environment CPU loading only; no clean-environment or physics-success claim')
        (a.out/'summary.json').write_text(json.dumps(report,indent=2)+'\n')
        print(json.dumps(dict(status='complete',models=len(results),source_sha=source)))
    finally:
        if json.loads(lease.read_text()).get('pid')==os.getpid():lease.unlink()


if __name__=='__main__':main()
