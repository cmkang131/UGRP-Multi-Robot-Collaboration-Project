"""Receive selected gcp3 evidence on gcp2 CPU, then use the frozen playback tool."""
import argparse
import datetime
import json
import os
from pathlib import Path
import subprocess
import sys
import tarfile

ROOT=Path('/home/ugrp/ugrp-sim')


def main():
    p=argparse.ArgumentParser()
    p.add_argument('--receive',action='store_true')
    p.add_argument('--run',required=True)
    p.add_argument('--asset-root',type=Path)
    a=p.parse_args()
    if a.run not in ('graph-isolated-beampair','graph-isolated-release-s3'):
        raise ValueError('selected diagnostic evidence only')
    lease=ROOT/'leases/warp6-analysis.json'
    if lease.exists():raise RuntimeError('existing analysis lease must be inspected')
    now=datetime.datetime.now(datetime.timezone.utc)
    lease.write_text(json.dumps(dict(task='warp6-analysis',pid=os.getpid(),
        started_at=now.isoformat(),expected_end=(now+datetime.timedelta(minutes=20)).isoformat(),
        purpose='gcp3 diagnostic evidence CPU playback; no physics/controller')))
    try:
        if a.receive:
            destination=ROOT/'runs/warp6';destination.mkdir(parents=True,exist_ok=True)
            with tarfile.open(fileobj=sys.stdin.buffer,mode='r|gz') as archive:
                for member in archive:
                    if not member.name.startswith(a.run+'/'):
                        raise ValueError('archive outside selected run')
                    archive.extract(member,destination,filter='data')
            return
        if a.asset_root is None:raise ValueError('explicit frozen asset root required')
        out=ROOT/'ops-reviews/warp6/playback'/a.run
        subprocess.run([str(ROOT/'ugrp/.venv-sim/bin/python'),
            str(ROOT/'ops-reviews/warp6/make_playback.py'),
            '--run',str(ROOT/'runs/warp6'/a.run),'--out',str(out),
            '--asset-root',str(a.asset_root)],check=True,cwd=a.asset_root,
            env={**os.environ,'OMP_NUM_THREADS':'1','OPENBLAS_NUM_THREADS':'1','MUJOCO_GL':'osmesa'})
        print(out,flush=True)
    finally:
        if json.loads(lease.read_text()).get('pid')!=os.getpid():
            raise RuntimeError('analysis lease ownership changed')
        lease.unlink()


if __name__=='__main__':main()
