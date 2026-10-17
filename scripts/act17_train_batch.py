"""One hash-bound M/F/S training queue, current-stack admission before launch."""
import argparse
from datetime import datetime,timezone
import json
import os
from pathlib import Path
import signal
import subprocess
import sys
import time

sys.path.insert(0,str(Path(__file__).resolve().parent))
from act16w_runtime import require_gcp2,frozen_source,sha256
from act17_data import read
from act17_v7 import ROOT,B


def write(path,value):
    tmp=path.with_suffix('.tmp');tmp.write_text(json.dumps(value,indent=2)+'\n');tmp.replace(path)


def main():
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('--enabled',action='store_true')
    for key in ['dataset','protocol','out','stack','checker','stack-values']:
        p.add_argument('--'+key,type=Path,required=True)
    p.add_argument('--max-parallel',type=int,choices=[1,2],default=2)
    a=p.parse_args()
    if not a.enabled:p.error('ACT17 training queue is default OFF')
    host=require_gcp2(training=True);source=frozen_source(ROOT);manifest=read(a.dataset/'manifest.json');protocol=read(a.protocol)
    if not manifest.get('complete') or set(manifest['eligible_train_seeds'])!=set(protocol['train_seeds']):
        raise ValueError('all200 preregistered TRAIN starts required')
    a.out.mkdir(parents=True,exist_ok=False)
    queue=dict(flow='train',cohort='act17-v7-native',source_sha=source,host=host,stack_values=read(a.stack_values),
        rejection_table=str(a.dataset/'rejection_table.json'),rejection_table_sha256=sha256(a.dataset/'rejection_table.json'),
        dataset_manifest_sha256=sha256(a.dataset/'manifest.json'),protocol_sha256=sha256(a.protocol),
        candidates=protocol['candidates'],training=protocol['training'],max_parallel=a.max_parallel,wall_cap=None)
    write(a.out/'queue.json',queue)
    subprocess.run([sys.executable,str(a.checker),str(a.out/'queue.json'),'--stack',str(a.stack),
        '--output',str(a.out/'current-stack-check.json')],check=True)
    pending=['M','F','S'];running={};finished=[];stop={'requested':False};start=datetime.now(timezone.utc).isoformat();clock=time.monotonic()
    lease=B/'leases/act17-training-queue.json'
    with lease.open('x') as f:json.dump(dict(task='act17',pid=os.getpid(),start=start,expected_end='finite M/F/S10000updates',concurrency=0),f)
    for sig in [signal.SIGINT,signal.SIGTERM]:signal.signal(sig,lambda *_:stop.update(requested=True))
    report=dict(status='running',complete=False,source_sha=source,started_utc=start,queue_sha256=sha256(a.out/'queue.json'))
    try:
        while pending or running:
            if stop['requested']:raise InterruptedError('supervisor stop')
            for candidate,job in list(running.items()):
                rc=job['process'].poll()
                if rc is None:continue
                job['log'].close();del running[candidate]
                summary=read(a.out/candidate/'summary.json') if (a.out/candidate/'summary.json').exists() else {}
                finished.append(dict(candidate=candidate,returncode=rc,summary=summary))
                if rc or not summary.get('complete') or not summary.get('readback_verified'):
                    raise RuntimeError('training child HOST_ERROR or incomplete')
            while pending and len(running)<a.max_parallel:
                candidate=pending.pop(0);command=[sys.executable,'-u',str(ROOT/'scripts/act17_train.py'),
                    '--candidate',candidate,'--dataset',str(a.dataset),'--protocol',str(a.protocol),'--out',str(a.out/candidate)]
                log=(a.out/(candidate+'.log')).open('x');proc=subprocess.Popen(command,cwd=ROOT,stdout=log,stderr=subprocess.STDOUT,
                    start_new_session=True,env={**os.environ,'OMP_NUM_THREADS':'2','OPENBLAS_NUM_THREADS':'1','PYTHONDONTWRITEBYTECODE':'1'})
                write(a.out/(candidate+'-launch.json'),dict(argv=command,pid=proc.pid,source_sha=source))
                running[candidate]=dict(process=proc,log=log)
            report.update(active={c:j['process'].pid for c,j in running.items()},pending=pending,finished=finished,wall_s=time.monotonic()-clock)
            write(a.out/'summary.json',report);time.sleep(2)
        report.update(status='complete',complete=True)
    except BaseException as error:
        report.update(status='HOST_ERROR',complete=False,error=repr(error));raise
    finally:
        for job in running.values():
            if job['process'].poll() is None:
                os.killpg(job['process'].pid,signal.SIGINT)
                try:job['process'].wait(timeout=30)
                except subprocess.TimeoutExpired:os.killpg(job['process'].pid,signal.SIGKILL);job['process'].wait()
            job['log'].close()
        report['wall_s']=time.monotonic()-clock;write(a.out/'summary.json',report)
        if lease.exists() and read(lease).get('pid')==os.getpid():lease.unlink()


if __name__=='__main__':main()
