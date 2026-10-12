"""Infrastructure recovery only: five egomap65 jobs that never began physics.

Run after the original batch EXIT exists. Child source/arguments remain frozen;
only output paths differ so original HOST failures are never overwritten.
"""
import argparse,json,os,platform,shutil,subprocess,sys,time
from pathlib import Path
SOURCE='4f759965ca00d4ae29ec9419083a8dca62cfb736'
EXPECTED={(63005,'a','filtered_hysteresis_v1'),*( (63006,p,h) for p in ('baseline','a') for h in ('off','filtered_hysteresis_v1') )}

def read(p):return json.loads(p.read_text())
def dump(p,r):p.write_text(json.dumps(r,indent=2)+'\n')

def admission(original,out,source_root):
    if not (original.parent/'EXIT').exists():raise ValueError('WAIT_ORIGINAL_BATCH_TERMINAL')
    if source_root.name!=SOURCE:raise ValueError('FROZEN_CHILD_SOURCE_REQUIRED')
    jobs=read(original/'batch-status.json')
    eligible=[j for j in jobs if j['status']=='HOST_ERROR_NO_RESULT']
    if {(j['seed'],j['profile'],j['heading_stability']) for j in eligible}!=EXPECTED:raise ValueError('UNREGISTERED_RETRY_SET')
    retries=[]
    for row in eligible:
        old=Path(row['output'])
        if (old/'result.json').exists() or (old/'own-controller.jsonl').exists():raise ValueError('PHYSICS_ALREADY_STARTED')
        text=(original/(row['name']+'.log')).read_text()
        if 'FileNotFoundError' not in text or row['checkpoint'] not in text:raise ValueError('NOT_INPUT_LOSS')
        if not Path(row['checkpoint']).is_file():raise ValueError('INPUT_NOT_RESTORED')
        j=dict(row);cmd=list(j['command']);cmd[cmd.index('--output')+1]=str(out/row['name'])
        j.update(status='QUEUED',output=str(out/row['name']),command=cmd,original_failure='HOST_ERROR_NO_RESULT',original_log=str(original/(row['name']+'.log')))
        j.pop('pid',None);j.pop('exit_code',None);retries.append(j)
    return retries

def main():
    p=argparse.ArgumentParser();p.add_argument('--original',type=Path,required=True);p.add_argument('--output',type=Path,required=True);p.add_argument('--source-root',type=Path,required=True)
    a=p.parse_args()
    if platform.system()!='Linux' or os.getenv('UGRP_EXECUTION_HOST')!='oracle-x86':raise ValueError('ORACLE_ONLY')
    out=a.output.resolve()
    jobs=admission(a.original.resolve(),out,a.source_root.resolve())
    out.mkdir(parents=True,exist_ok=False)
    dump(out/'batch-plan.json',dict(source_sha=SOURCE,orchestrator_source_sha=Path(__file__).resolve().parents[1].name,host='oracle-x86',jobs=jobs,reason='missing original checkpoint restored byte-for-byte; original five physical attempts zero'))
    running=[];queue=list(jobs)
    while queue or running:
        free=next(int(x.split()[1])/1048576 for x in Path('/proc/meminfo').read_text().splitlines() if x.startswith('MemAvailable:'))
        while queue and free>=6 and shutil.disk_usage(out).free/2**30>=2:
            j=queue.pop(0);stream=(out/(j['name']+'.log')).open('x')
            proc=subprocess.Popen(j['command'],cwd=a.source_root,stdout=stream,stderr=subprocess.STDOUT)
            j.update(status='RUNNING',pid=proc.pid);running.append((j,proc,stream))
            free=next(int(x.split()[1])/1048576 for x in Path('/proc/meminfo').read_text().splitlines() if x.startswith('MemAvailable:'))
        for j,proc,stream in running.copy():
            if proc.poll() is None:continue
            stream.close();j['exit_code']=proc.returncode;result=Path(j['output'])/'result.json'
            j['status']=read(result)['status'] if result.exists() else 'HOST_ERROR_NO_RESULT';running.remove((j,proc,stream))
        if queue and not running and shutil.disk_usage(out).free/2**30<2:
            for j in queue:j.update(status='BLOCKED_DISK_CAPACITY')
            queue=[]
        dump(out/'batch-status.json',jobs)
        if queue or running:time.sleep(2)
    # Same post-hoc scorer; all recovery physics has terminated.
    from scripts.run_own_route_heading_stability import score_batch
    score_batch(jobs,out)
    return 0
if __name__=='__main__':raise SystemExit(main())
