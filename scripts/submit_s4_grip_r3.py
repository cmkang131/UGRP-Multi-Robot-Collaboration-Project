"""Eight parallel jobs plus bounded early checks; no unattended submission."""
import argparse
from concurrent.futures import ThreadPoolExecutor
import json
import os
from pathlib import Path
import shlex
import subprocess
import time
from scripts.run_s4_grip_r3 import ROOT,PLAN
from scripts.submit_s4_grip_batch import submit_one


def commands(sha):
    p=json.loads(PLAN.read_text())
    if len(p['runs'])!=8 or p['max_concurrent']>10:raise ValueError('registered eight-job batch required')
    return [(r['name'],[v.replace('<SOURCE_SHA>',sha) for v in r['argv']]) for r in p['runs']]


def healthy(h):
    if h.get('status')=='ERROR':return False
    return (h.get('sim_time',0)>=10 and h.get('frames',0)>=3 and h.get('issued_commands',0)>=10
            and {1,3,4,5}.issubset(h.get('servo_ids',[])) and h.get('arm_displacement_m',0)>.005
            and h.get('phase') in ('POST_GRASP_MONITOR','REOBSERVE','COMPLETE'))


def snapshot(names):
    script='''import pathlib,json
root=pathlib.Path.home()/'ugrp-sim/runs';rows={}
for name in NAMES:
 p=root/name;h=p/'health.json';e=p/'EXIT'
 try:health=json.loads(h.read_text()) if h.exists() else None
 except ValueError:health=None
 rows[name]={'health':health,'exit':e.read_text().strip() if e.exists() else None}
print(json.dumps(rows))'''.replace('NAMES',repr(names))
    r=subprocess.run(['ssh','oracle-x86','python3 -c '+shlex.quote(script)],text=True,capture_output=True,check=True)
    return json.loads(r.stdout)


def stop(name,sha,reason):
    # Driver receipt plus live argv and pgid must all identify this exact job.
    script='''import pathlib,json,os,signal,time
p=pathlib.Path.home()/'ugrp-sim/runs'/NAME
if (p/'EXIT').exists():print('already exited');raise SystemExit(0)
r=json.loads((p/'driver.json').read_text());assert r['job']==NAME and r['source_sha']==SHA
pid=r['pid'];pgid=r['pgid'];argv=pathlib.Path('/proc')/str(pid)/'cmdline'
cmd=argv.read_bytes().split(b'\\0');assert b'scripts.run_s4_grip_r3' in cmd and NAME.encode() in cmd
assert os.getpgid(pid)==pgid and pgid!=os.getpgrp()
(p/'initial-stop.json').write_text(json.dumps({'reason':REASON,'source_sha':SHA,'pid':pid,'pgid':pgid,'classification':'INITIAL_CHECK_ABORT'}))
(p/'EXIT').write_text('143\\n');os.killpg(pgid,signal.SIGTERM)
print('stopped own job')'''.replace('NAME',repr(name)).replace('SHA',repr(sha)).replace('REASON',repr(reason))
    r=subprocess.run(['ssh','oracle-x86','python3 -c '+shlex.quote(script)],capture_output=True,text=True)
    return dict(returncode=r.returncode,stdout=r.stdout,stderr=r.stderr)


def initial_checks(names,sha,*,read=snapshot,terminate=stop,wait=time.sleep,clock=time.monotonic):
    started=clock();pending=set(names);result={};previous={}
    while pending and clock()-started<240:
        rows=read(sorted(pending))
        for name,row in rows.items():
            h=row.get('health');elapsed=clock()-started
            if h and healthy(h):
                prev=previous.get(name)
                if prev and h['sim_time']>prev['sim_time'] and h['frames']>prev['frames']:
                    result[name]=dict(status='PASS',checked_after_s=elapsed,first=prev,last=h,exit=row['exit']);pending.remove(name);continue
            if h and h.get('status')=='ERROR' or row.get('exit') not in (None,'0'):
                result[name]=dict(status='FAIL',checked_after_s=elapsed,observed=row,stop=terminate(name,sha,'initial log/exit failure'));pending.remove(name);continue
            if h and h.get('sim_time',0)>=2:previous.setdefault(name,h)
            if row.get('exit')=='0' and h and healthy(h):
                # A complete trial has explicit span/commands plus two prior
                # warmup captures even if the whole job ended between polls.
                result[name]=dict(status='PASS_COMPLETED',checked_after_s=elapsed,last=h,exit='0');pending.remove(name)
        if pending:wait(10)
    for name in pending:
        result[name]=dict(status='FAIL_TIMEOUT',checked_after_s=clock()-started,
            stop=terminate(name,sha,'no normal advancing grasp/lift within 4 minutes'))
    return result


def main(argv=None):
    p=argparse.ArgumentParser();p.add_argument('--oracle-runner',type=Path);p.add_argument('--output',type=Path)
    p.add_argument('--submit',action='store_true');a=p.parse_args(argv)
    sha=subprocess.check_output(['git','rev-parse','HEAD'],cwd=ROOT,text=True).strip();rows=commands(sha)
    if not a.submit:print(json.dumps(rows));return 0
    if not a.oracle_runner or not a.oracle_runner.is_file() or not a.output or a.output.exists():raise ValueError('runner and new local output required')
    if subprocess.check_output(['git','status','--porcelain'],cwd=ROOT,text=True).strip():raise ValueError('commit frozen source first')
    for name,_ in rows:subprocess.run(['ssh','oracle-x86',f'test ! -e ~/ugrp-sim/runs/{name}'],check=True)
    from scripts.submit_s4_pair_batch import stage_source
    stage_source(sha)
    with ThreadPoolExecutor(max_workers=8) as pool:
        admissions=list(pool.map(lambda row:submit_one(a.oracle_runner,*row),rows))
    receipt=dict(source_sha=sha,admissions=admissions)
    a.output.parent.mkdir(parents=True,exist_ok=True);a.output.write_text(json.dumps(receipt,indent=2)+'\n')
    admitted=[r['name'] for r in admissions if not r['returncode']]
    receipt['initial_checks']=initial_checks(admitted,sha)
    a.output.write_text(json.dumps(receipt,indent=2)+'\n')
    return int(any(r['returncode'] for r in admissions) or any(r['status'].startswith('FAIL') for r in receipt['initial_checks'].values()))


if __name__=='__main__':raise SystemExit(main())
