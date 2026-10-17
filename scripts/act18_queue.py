"""Default-off matched two-candidate reference training queue, no wall cap."""
import argparse
from datetime import datetime, timezone
import json
import os
from pathlib import Path
import signal
import subprocess
import sys
import time

sys.path.insert(0,str(Path(__file__).resolve().parent))
from act16w_runtime import require_gcp2, frozen_source, sha256
from act17_data import read
from act17_compact_records import original_sha256
from act18_diagnose import write

B=Path('/home/ugrp/ugrp-sim')
ROOT=Path(__file__).resolve().parents[1]


def main():
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('--enabled',action='store_true')
    # AGENTS 2026-10-17: bf16 is the default for new ACT training; fp32 is an
    # explicit replay/matched-fp32 comparison and never pools with bf16.
    p.add_argument('--precision',choices=('bf16_autocast_v1','fp32'),default='bf16_autocast_v1')
    for name in ('dataset','protocol','out','prior-rejections','stack-values'):
        p.add_argument('--'+name,type=Path,required=True)
    a=p.parse_args()
    if not a.enabled:
        p.error('ACT18 reference training is default OFF')
    host=require_gcp2(training=True);source=frozen_source(ROOT)
    protocol=read(a.protocol)
    if not a.prior_rejections.is_file() or not read(a.prior_rejections).get('failures'):
        raise ValueError('actual preceding expert-state rejection table required')
    a.out.mkdir(parents=True,exist_ok=False)
    table=dict(funnel=[dict(gate='registered_candidates',passed=2,rejected=0),
        dict(gate='full_v7_TRAIN_data',passed=2,rejected=0)],pending=2,
        prior=dict(path=str(a.prior_rejections),sha256=sha256(a.prior_rejections)),
        raw=str(a.out),reproduce=sys.argv)
    write(a.out/'rejection_table.json',table)
    queue=dict(flow='train',source_sha=source,host=host,candidates=['R8','R100'],
        dataset_manifest_sha256=original_sha256(a.dataset/'manifest.json'),
        protocol_sha256=sha256(a.protocol),stack_values=read(a.stack_values),
        training_precision=a.precision,
        rejection_table=str(a.out/'rejection_table.json'),wall_cap=None,max_parallel=2,
        dataset_provenance=read(a.stack_values))
    write(a.out/'queue.json',queue)
    subprocess.run([sys.executable,str(ROOT/'scripts/check_current_stack.py'),str(a.out/'queue.json'),
        '--flow','train','--output',str(a.out/'current-stack-check.json')],check=True)
    lease=B/'leases/act18.json';old=read(lease)
    if old.get('task')!='act18':
        raise ValueError('owned lease required')
    old.update(pid=os.getpid(),active='act18_queue',concurrency=0,
        expected_end='two finite100k candidates then TRAIN gate; no wall cap')
    write(lease,old)
    stop={'requested':False};jobs=[];clock=time.monotonic()
    for sig in (signal.SIGINT,signal.SIGTERM):
        signal.signal(sig,lambda *_:stop.update(requested=True))
    report=dict(status='running',complete=False,source_sha=source,host=host,
        started_utc=datetime.now(timezone.utc).isoformat(),queue_sha256=sha256(a.out/'queue.json'),candidates={})
    try:
        for name in queue['candidates']:
            cmd=[sys.executable,'-u',str(ROOT/'scripts/act18_train.py'),'--enabled','--candidate',name,
                '--precision',a.precision,
                '--dataset',str(a.dataset),'--protocol',str(a.protocol),'--queue',str(a.out/'queue.json'),'--out',str(a.out/name)]
            log=(a.out/(name+'.log')).open('x')
            proc=subprocess.Popen(cmd,stdout=log,stderr=subprocess.STDOUT,cwd=ROOT,start_new_session=True,
                env={**os.environ,'OMP_NUM_THREADS':'2','OPENBLAS_NUM_THREADS':'1','PYTHONDONTWRITEBYTECODE':'1'})
            jobs.append(dict(name=name,process=proc,log=log))
        while jobs:
            if stop['requested']:
                raise InterruptedError('explicit supervisor stop')
            for job in jobs:
                path=a.out/job['name']/'summary.json'
                value=read(path) if path.exists() else {}
                report['candidates'][job['name']]=value
                rc=job['process'].poll()
                if rc is not None and (rc or not value.get('complete') or not value.get('readback_verified')):
                    raise RuntimeError('training child failed; stop the sibling and preserve failure')
            report['wall_s']=time.monotonic()-clock
            write(a.out/'summary.json',report)
            if all(j['process'].poll()==0 for j in jobs):
                break
            time.sleep(5)
        report.update(status='complete',complete=True)
    except BaseException as error:
        report.update(status='SUPERVISOR_STOP' if isinstance(error,InterruptedError) else 'HOST_ERROR',error=repr(error))
        raise
    finally:
        for job in jobs:
            if job['process'].poll() is None:
                os.killpg(job['process'].pid,signal.SIGINT)
                job['process'].wait()
            job['log'].close()
        report['wall_s']=time.monotonic()-clock
        write(a.out/'summary.json',report)


if __name__=='__main__':
    main()
