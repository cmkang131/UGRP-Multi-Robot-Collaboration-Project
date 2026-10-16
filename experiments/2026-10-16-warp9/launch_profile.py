"""Finite exclusive gcp3/gcp4 scaling diagnostic. Wait owns no GPU context.

No VM lifecycle operations, credentials, or automatic optimization/gate launch.
The explicit --wait flag only waits for the user-named warp8 lease to end.
"""
import argparse
import copy
import datetime
import fcntl
import hashlib
import json
import os
from pathlib import Path
import platform
import subprocess
import sys
import time

ROOT=Path(__file__).resolve().parents[2]
BASE=Path('/home/ugrp/ugrp-sim')


def write(path,value):
    path.write_text(json.dumps(value,indent=2)+'\n')


def resources():
    leases={p.name:json.loads(p.read_text()) for p in (BASE/'leases').glob('*.json')}
    gpu=subprocess.check_output(['nvidia-smi','--query-compute-apps=pid,process_name','--format=csv,noheader'],text=True).strip()
    return dict(leases=leases,gpu_processes=gpu,utc=datetime.datetime.now(datetime.timezone.utc).isoformat())


def main():
    parser=argparse.ArgumentParser()
    parser.add_argument('--wait',action='store_true')
    parser.add_argument('--host',choices=('gcp3','gcp4'),default='gcp3')
    parser.add_argument('--output',type=Path,required=True)
    args=parser.parse_args()
    if platform.node()!='ugrp-act-l4-'+args.host:raise ValueError('requested registered L4 only')
    sha=subprocess.check_output(['git','rev-parse','HEAD'],cwd=ROOT,text=True).strip()
    if subprocess.check_output(['git','status','--porcelain','--untracked-files=no'],cwd=ROOT):raise ValueError('clean committed source required')
    args.output.mkdir(parents=True,exist_ok=False)
    write(args.output/'status.json',dict(status='WAITING_EXCLUSIVE',source_sha=sha))
    lease=BASE/'leases/warp9-profile.json'
    claimed=False
    try:
        while not claimed:
            # This local lock prevents two warp9 dispatchers claiming together.
            # Other tasks' leases remain authoritative and are never removed.
            with (BASE/'leases/.warp9-claim.lock').open('a') as lock:
                fcntl.flock(lock,fcntl.LOCK_EX)
                state=resources()
                write(args.output/'last-resource-check.json',state)
                if not state['leases'] and not state['gpu_processes']:
                    with lease.open('x') as f:
                        json.dump(dict(task='warp9',pid=os.getpid(),started_at=state['utc'],
                            expected_end='finite four sizes x0.3 SIM s; no wall cap',concurrency=64,
                            stage='exclusive scaling profile',source_sha=sha,gpu_shared=False),f,indent=2)
                    claimed=True
            if not claimed:
                if not args.wait:raise RuntimeError('requested host occupied; no GPU work submitted')
                # Resource polling is not a planner or task time budget.
                time.sleep(30)
        original=json.loads((ROOT/'experiments/2026-10-16-warp9/warp7-r3-queue.json').read_text())
        for n in (1,4,16,64):
            q=copy.deepcopy(original)
            table=args.output/f'n{n}-selection.json'
            write(table,dict(unit='explicit_world_replica',unique_initial_cases=1,independent_task_trials=0,
                stages=[dict(stage='fixed_R3_initial_case',cumulative_pass_n=1,rejected_n=0),
                        dict(stage='explicit_scaling_replication',cumulative_pass_n=n,rejected_n=0)],
                previous_controller_table=str(ROOT/'experiments/2026-10-16-warp7/final-record/rejection-table.json'),
                raw=str(ROOT/'experiments/2026-10-16-warp9/warp7-r3-queue.json'),
                reproduction=[sys.executable,__file__,*sys.argv[1:]]))
            q.update(task='warp9',source_sha=sha,rejection_table=str(table),
                render_gate=str(ROOT/'experiments/2026-10-16-warp7/colour/r5-summary.json'),
                runs=[copy.deepcopy(original['runs'][0]) for _ in range(n)],
                warp9_exclusive_host_v1=args.host,warp9_profile_v1=True,profile_sim_s=.3,
                independent_initial_cases=1,duplicate_isolation_worlds=n-1,
                interpretation='fixed-work scaling diagnostic, not task qualification')
            # Source-relative calibration paths keep the exact saved hashes.
            for key,value in q['environment'].items():
                if key.endswith('CALIBRATION'):
                    q['environment'][key]=str(ROOT/'experiments'/value.split('/experiments/',1)[1])
            q['storage_budget']['reserved_bytes']=0
            q['storage_budget']['reserved_basis']='exclusive diagnostic; no foreign-stage reservation'
            qp=args.output/f'n{n}-queue.json';write(qp,q)
            command=[sys.executable,'-m','scripts.run_warp5_batch','--execute','--queue',str(qp),'--output',str(args.output/f'n{n}')]
            write(args.output/'status.json',dict(status='PROFILING',nworld=n,source_sha=sha,command=command))
            env=dict(os.environ,MUJOCO_GL='osmesa',PYOPENGL_PLATFORM='osmesa',
                OMP_NUM_THREADS='1',OPENBLAS_NUM_THREADS='1',PYTHONPATH=str(ROOT/'scripts')+':'+str(ROOT))
            with (args.output/f'n{n}.log').open('xb') as log:
                result=subprocess.run(command,cwd=ROOT,env=env,stdout=log,stderr=subprocess.STDOUT)
            if result.returncode:raise RuntimeError(f'N{n} failed; no repeated submission, see n{n}.log')
        write(args.output/'status.json',dict(status='PROFILE_COMPLETE',source_sha=sha,
            task_gates='not_submitted',next='rank measured phases before changing performance code'))
    except BaseException as exc:
        write(args.output/'status.json',dict(status='HOST_ERROR',source_sha=sha,reason=repr(exc)))
        raise
    finally:
        if claimed:
            value=json.loads(lease.read_text())
            if value.get('pid')!=os.getpid():raise RuntimeError('lease ownership changed; refusing removal')
            lease.unlink()
        write(args.output/'release.json',dict(own_lease_removed=claimed,remaining=resources(),vm_stop_attempts=0))


if __name__=='__main__':main()
