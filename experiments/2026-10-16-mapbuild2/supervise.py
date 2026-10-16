"""Remote GCP2 L4 finite acquisition owner; no wall deadline or VM stop."""
import argparse
import datetime
import json
import os
from pathlib import Path
import signal
import subprocess


def dump(p,x):p.write_text(json.dumps(x,indent=2)+'\n')


def main():
    p=argparse.ArgumentParser();p.add_argument('--source',type=Path,required=True)
    p.add_argument('--attempt',required=True);a=p.parse_args()
    if not a.attempt.startswith('capture-') or '/' in a.attempt:raise ValueError('ATTEMPT_NAME')
    base=Path('/home/ugrp/ugrp-sim');run=base/'runs/mapbuild2';run.mkdir(exist_ok=True)
    queue=run/(a.attempt+'-queue.json');out=run/a.attempt
    if queue.exists() or out.exists():raise ValueError('NEW_ATTEMPT_REQUIRED')
    previous=base/'runs/mapbuild1/capture-r2/frames/rejection-table.json'
    if not previous.is_file():raise ValueError('PREVIOUS_FUNNEL_MISSING')
    source=a.source.resolve()
    q=dict(task='mapbuild2',source_sha=subprocess.check_output(['git','rev-parse','HEAD'],cwd=source,text=True).strip(),
        toggle='mapbuild2_v1',enabled=True,shared=True,rejection_table=str(previous))
    cmd=[str(base/'runs/simalt3/warp-env/bin/python'),'-u',str(source/'scripts/mapbuild2_capture.py'),
        '--execute','--queue',str(queue),'--renderer-source',str(base/'src/5974a181a'),'--output',str(out)]
    entry=dict(task='mapbuild2',pid=os.getpid(),start=datetime.datetime.now(datetime.timezone.utc).isoformat(),
        expected_end='finite 4 SIM seconds; no wall runtime cap',concurrency=4,gpu_shared=True,source_sha=q['source_sha'])
    lease=base/'leases/mapbuild2.json'
    with lease.open('x') as f:json.dump(entry,f,indent=2)
    dump(queue,q)
    try:
        with (run/(a.attempt+'.log')).open('w') as log:
            child=subprocess.Popen(cmd,cwd=source,stdout=log,stderr=subprocess.STDOUT,
                preexec_fn=lambda:signal.signal(signal.SIGINT,signal.SIG_DFL),
                env={**os.environ,'PYTHONPATH':str(source),'MUJOCO_GL':'osmesa','OMP_NUM_THREADS':'1','OPENBLAS_NUM_THREADS':'1'})
            entry['child_pid']=child.pid;dump(lease,entry);code=child.wait()
        dump(run/(a.attempt+'-exit.json'),dict(exit_code=code,command=cmd))
    finally:
        if lease.exists() and json.loads(lease.read_text()).get('pid')==os.getpid():lease.unlink()
        dump(run/(a.attempt+'-lease-release.json'),dict(remaining_leases=[p.name for p in (base/'leases').glob('*.json')],vm_stop_attempted=False))


if __name__=='__main__':main()
