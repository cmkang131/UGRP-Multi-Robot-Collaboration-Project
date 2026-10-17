"""Public ACT17 archive/file hashes and bundled CPU loading from a fresh checkout.

Existing pinned ACT environment is reused. This is distribution/loading proof,
not a clean virtual environment, new physical trial or raw-data backup.
"""
import argparse
from datetime import datetime,timezone
import json
import os
from pathlib import Path
import subprocess
import sys

sys.path.insert(0,str(Path(__file__).resolve().parent))
from act16w_runtime import require_gcp2,frozen_source,sha256
from model_artifacts import load_registry,fetch,verify_directory

ROOT=Path(__file__).resolve().parents[1];B=Path('/home/ugrp/ugrp-sim')


def main():
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('--out',type=Path,required=True)
    a=p.parse_args();host=require_gcp2(training=True);source=frozen_source(ROOT);registry=load_registry(ROOT)
    ids={'act17-v7-native-r1-'+c+'-step10000-20261017' for c in ['m','f','s']}
    rows=[r for r in registry['artifacts'] if r['id'] in ids]
    if {r['id'] for r in rows}!=ids:raise ValueError('all three registered ACT17 R1 assets required')
    a.out.mkdir(parents=True,exist_ok=False);results=[]
    lease=B/'leases/act17-release-verification.json'
    with lease.open('x') as f:json.dump(dict(task='act17',pid=os.getpid(),start=datetime.now(timezone.utc).isoformat(),expected_end='three public downloads/full hashes and CPU loads',concurrency=0),f)
    report=dict(status='running',complete=False,source_sha=source,host=host,models=results,
        registry_sha256=sha256(ROOT/'configs/model_artifacts.json'),fresh_checkout=str(ROOT),
        scope='fresh checkout, anonymous public download/full archive+file hashes, bundled CPU loading in existing pinned ACT environment; no task-success or raw-data-backup claim')
    try:
        for row in rows:
            destination=a.out/'models'/row['id'];downloaded=fetch(row,destination);verified=verify_directory(row,destination)
            proc=subprocess.run([sys.executable,str(destination/'inference/load_model.py')],
                env={**os.environ,'CUDA_VISIBLE_DEVICES':'','OMP_NUM_THREADS':'1','OPENBLAS_NUM_THREADS':'1','PYTHONDONTWRITEBYTECODE':'1'},
                stdout=subprocess.PIPE,stderr=subprocess.PIPE,text=True)
            (a.out/(row['id']+'-load.stdout')).write_text(proc.stdout);(a.out/(row['id']+'-load.stderr')).write_text(proc.stderr)
            if proc.returncode:raise RuntimeError('public bundle loading failed '+row['id'])
            response=json.loads(proc.stdout.strip().splitlines()[-1])
            if response.get('ready') is not True or response.get('device')!='cpu' or response.get('bundled_inference_library') is not True:
                raise ValueError('actual bundled CPU ready proof required')
            results.append(dict(id=row['id'],archive=row['archive'],release=row['release'],download=downloaded,full_inventory=verified,
                loading=response,loading_exit_code=proc.returncode,loader_sha256=sha256(destination/'inference/load_model.py')))
            (a.out/'progress.json').write_text(json.dumps(report,indent=2)+'\n')
        report.update(status='complete',complete=True,utc=datetime.now(timezone.utc).isoformat())
    except BaseException as error:
        report.update(status='HOST_ERROR',error=repr(error));raise
    finally:
        (a.out/'summary.json').write_text(json.dumps(report,indent=2)+'\n')
        if lease.exists() and json.loads(lease.read_text()).get('pid')==os.getpid():lease.unlink()


if __name__=='__main__':main()
