"""One finite eight-job two-seed submission, with active early checks and own-job stops."""
import argparse
from concurrent.futures import ThreadPoolExecutor
import json
from pathlib import Path
import shlex
import subprocess
import time
from scripts.run_s4_pair_live8_r2 import ROOT,RECORD
from scripts.submit_s4_pair_batch import stage_source as archive_source,submit_one


def stage_source(sha):
    archive_source(sha)
    # Only our new committed source cache is deduplicated. Existing caches and
    # every run/raw remain intact. Byte-identical immutable assets share inodes.
    script='''import pathlib,json,hashlib,os
root=pathlib.Path.home()/'ugrp-sim/src';new=root/SHA;old=root/UPSTREAM;linked=[]
def digest(p):
 h=hashlib.sha256()
 with p.open('rb') as f:
  for b in iter(lambda:f.read(1048576),b''):h.update(b)
 return h.hexdigest()
for p in new.rglob('*'):
 if p.is_symlink() or not p.is_file() or p.stat().st_size<131072:continue
 q=old/p.relative_to(new)
 if not q.is_file() or q.is_symlink() or q.stat().st_size!=p.stat().st_size:continue
 h=digest(p)
 if digest(q)!=h:continue
 tmp=p.with_name(p.name+'.s4live8-link');os.link(q,tmp);os.replace(tmp,p)
 assert digest(p)==h
 linked.append({'path':str(p.relative_to(new)),'bytes':p.stat().st_size,'sha256':h})
receipt={'source_sha':SHA,'immutable_assets_from':UPSTREAM,'files':linked,'bytes_saved':sum(r['bytes'] for r in linked),'run_raw_modified':False}
(new/'source-dedup.json').write_text(json.dumps(receipt)+'\\n')
print(json.dumps({'linked_files':len(linked),'bytes_saved':receipt['bytes_saved']}))'''.replace('SHA',repr(sha)).replace('UPSTREAM',repr('e6a863c9481288105a745cca53594ba05e6a9a7a'))
    subprocess.run(['ssh','oracle-x86','python3 -c '+shlex.quote(script)],check=True)


def commands(sha,plan=ROOT/RECORD/'plan-r2.json'):
    p=json.loads(plan.read_text())
    assert len(p['runs'])==8 and p['max_concurrent']==8
    return [(r['name'],[v.replace('<SOURCE_SHA>',sha) for v in r['argv']]) for r in p['runs']]


def snapshot(names):
    script='''import pathlib,json
root=pathlib.Path.home()/'ugrp-sim/runs';rows={}
for name in NAMES:
 p=root/name;h=p/'health.json';e=p/'EXIT';log=p/'log.txt'
 try:health=json.loads(h.read_text()) if h.exists() else None
 except ValueError:health=None
 text=log.read_text() if log.exists() else ''
 rows[name]={'health':health,'exit':e.read_text().strip() if e.exists() else None,
 'log_exceptions':[s for s in text.splitlines() if s.startswith('Traceback') or 'Error:' in s or 'Exception:' in s]}
print(json.dumps(rows))'''.replace('NAMES',repr(names))
    r=subprocess.run(['ssh','oracle-x86','python3 -c '+shlex.quote(script)],text=True,capture_output=True,check=True)
    return json.loads(r.stdout)


def healthy(h):
    return bool(h and h['sim_s']>=10 and h['frames']>=3 and h['model_calls']>=2
        and all(r['commands']>10 and r['arm_delta_m']>.005 and r['base_delta_m']>.005
            and r['translation_commands']>0
            and {1,3,4,5}.issubset(r['servo_ids'])
            and r['state'] in ('align','align_start','pregrasp_descend','grasp','grasp_close','grasp_wait',
                'lift','low_lift','raise_high','raise','raise_wait','ready','wait_carry','carry','refix_decide','lower','hold',
                'wait_close','wait_lift','wait_lower','wait_open','cp_open')
            for r in h['robots'].values()) and len(h['robots'])==2)


def stop(name,sha,reason):
    script='''import pathlib,json,os,signal
p=pathlib.Path.home()/'ugrp-sim/runs'/NAME
if (p/'EXIT').exists():print('already exited');raise SystemExit(0)
r=json.loads((p/'driver.json').read_text());assert r['job']==NAME and r['source_sha']==SHA
pid=r['pid'];pgid=r['pgid'];cmd=(pathlib.Path('/proc')/str(pid)/'cmdline').read_bytes().split(b'\\0')
assert any(c in cmd for c in (b'scripts.run_s4_pair_live8_r2',)) and ('outputs/'+NAME+'/raw').encode() in cmd
assert os.getpgid(pid)==pgid and pgid!=os.getpgrp()
(p/'initial-stop.json').write_text(json.dumps({'reason':REASON,'source_sha':SHA,'pid':pid,'pgid':pgid,'classification':'INITIAL_CHECK_ABORT'}))
(p/'EXIT').write_text('143\\n');os.killpg(pgid,signal.SIGTERM)
print('stopped own job')'''.replace('NAME',repr(name)).replace('SHA',repr(sha)).replace('REASON',repr(reason))
    r=subprocess.run(['ssh','oracle-x86','python3 -c '+shlex.quote(script)],capture_output=True,text=True)
    return dict(returncode=r.returncode,stdout=r.stdout,stderr=r.stderr)


def initial_checks(names,sha,*,read=snapshot,terminate=stop,wait=time.sleep,clock=time.monotonic):
    started=clock();pending=set(names);result={};previous={}
    while pending and clock()-started<300:
        for name,row in read(sorted(pending)).items():
            h=row['health'];elapsed=clock()-started
            if row['log_exceptions'] or row['exit'] not in (None,'0') or h and h['status']=='HOST_ERROR':
                result[name]=dict(status='FAIL',checked_after_s=elapsed,observed=row,stop=terminate(name,sha,'initial exception/exit'));pending.remove(name);continue
            if healthy(h) and elapsed >= 180:
                prev=previous.get(name)
                if prev and h['sim_s']>prev['sim_s'] and h['frames']>prev['frames']:
                    result[name]=dict(status='PASS',checked_after_s=elapsed,first=prev,last=h,log_exceptions=row['log_exceptions']);pending.remove(name);continue
            if h and h.get('sim_s',0)>=1:previous.setdefault(name,h)
            if row['exit']=='0':
                # A valid early model/GO refusal is an experimental outcome,
                # never relabelled a host failure or silently re-run.
                result[name]=dict(status='TERMINAL_BEFORE_HEALTH',checked_after_s=elapsed,observed=row);pending.remove(name)
        if pending:wait(10)
    for name in pending:
        result[name]=dict(status='FAIL_TIMEOUT',checked_after_s=clock()-started,
            observed=read([name])[name],stop=terminate(name,sha,'no normal increasing frames and pair arm commands in5min'))
    return result


def resources():
    script="import os,json; m={k:int(v.split()[0]) for k,v in (s.split(':',1) for s in open('/proc/meminfo'))}; print(json.dumps({'loadavg':os.getloadavg(),'mem_available_GiB':m['MemAvailable']/1048576}))"
    r=subprocess.run(['ssh','-o','ConnectTimeout=10','oracle-x86','python3 -c '+shlex.quote(script)],capture_output=True,text=True,check=True)
    return json.loads(r.stdout)


def wait_resources(*,read=resources,wait=time.sleep):
    for _ in range(120):
        r=read()
        if r['loadavg'][0]<51 and r['mem_available_GiB']>=6:return r
        wait(30)
    raise TimeoutError('finite resource admission wait exhausted; no simulations submitted')


def main(argv=None):
    p=argparse.ArgumentParser();p.add_argument('--oracle-runner',type=Path,required=True)
    p.add_argument('--output',type=Path,required=True);p.add_argument('--submit',action='store_true')
    p.add_argument('--plan',type=Path,default=ROOT/RECORD/'plan-r2.json');a=p.parse_args(argv)
    sha=subprocess.check_output(['git','rev-parse','HEAD'],cwd=ROOT,text=True).strip();rows=commands(sha,a.plan)
    if not a.submit:print(json.dumps(rows));return 0
    if a.output.exists() or not a.oracle_runner.is_file():raise ValueError('new receipt and existing runner required')
    if subprocess.check_output(['git','status','--porcelain'],cwd=ROOT,text=True).strip():raise ValueError('commit source first')
    subprocess.run(['ssh','oracle-x86','test -r ~/ugrp-sim/s4live8-relay.json'],check=True)
    for name,_ in rows:subprocess.run(['ssh','oracle-x86',f'test ! -e ~/ugrp-sim/runs/{name}'],check=True)
    stage_source(sha)
    resources=wait_resources()
    def invoke(argv,**kwargs):
        kwargs['env']={**kwargs['env'],'LP_NUM_THREADS':'4'}
        return subprocess.run(argv,**kwargs)
    with ThreadPoolExecutor(max_workers=8) as pool:
        admissions=list(pool.map(lambda r:submit_one(a.oracle_runner,ROOT,*r,invoke=invoke),rows))
    receipt=dict(source_sha=sha,admissions=admissions,admission_resources=resources)
    a.output.parent.mkdir(parents=True,exist_ok=True);a.output.write_text(json.dumps(receipt,indent=2)+'\n')
    receipt['initial_checks']=initial_checks([r['name'] for r in admissions if not r['returncode']],sha)
    a.output.write_text(json.dumps(receipt,indent=2)+'\n')
    print(json.dumps({n:r['status'] for n,r in receipt['initial_checks'].items()}))
    return int(any(r['returncode'] for r in admissions) or any(r['status'].startswith('FAIL') for r in receipt['initial_checks'].values()))


if __name__=='__main__':raise SystemExit(main())
