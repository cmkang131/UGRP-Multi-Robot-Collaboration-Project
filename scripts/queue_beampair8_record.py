"""Finite gcp2-only CPU recording queue; leases and global40 admission."""
import argparse
import datetime
import hashlib
import json
import os
from pathlib import Path
import shutil
import statistics
import subprocess
import time

from harness.grasp_act_data import read_json, write_json
from harness.beampair_recording import existing, command_identity

ROOT=Path('/home/ugrp/ugrp-sim')
PY=ROOT/'ugrp/.venv-sim/bin/python'
TASK='beampair8'


def now():return datetime.datetime.now(datetime.timezone.utc).isoformat()


def load_optional(p):
    try:return read_json(p)
    except (FileNotFoundError,json.JSONDecodeError):return {}


def processes():
    rows=[]
    for p in Path('/proc').glob('[0-9]*/cmdline'):
        try:cmd=p.read_bytes().replace(b'\0',b' ').decode()
        except (FileNotFoundError,PermissionError):continue
        if any(x in cmd.split(' ',1)[0] for x in ('python','mujoco','ffmpeg')):
            rows.append(dict(pid=int(p.parent.name),command=cmd[:300]))
    return rows


def run(config):
    cfg=read_json(config);sha=cfg['source_sha'];src=ROOT/'src'/sha
    assert subprocess.check_output(['git','rev-parse','HEAD'],cwd=src,text=True).strip()==sha
    assert not subprocess.check_output(['git','status','--porcelain'],cwd=src)
    table=Path(cfg['rejection_table'])
    assert table.is_file() and hashlib.sha256(table.read_bytes()).hexdigest()==cfg['rejection_table_sha256']
    assert cfg['status']=='APPROVED_PINNED'
    plan=read_json(cfg['plan']);assert hashlib.sha256(Path(cfg['plan']).read_bytes()).hexdigest()==cfg['plan_sha256']
    if cfg['stage']=='record':
        proof=read_json(cfg['identity_proof'])
        assert proof['passed'] and proof['source_sha']==sha and len(proof['runs'])==4
        assert read_json(cfg['storage_budget'])['ok']
    batch=Path(cfg['batch']);batch.mkdir(exist_ok=False)
    write_json(batch/'RUN_META.json',dict(**{'class':'dev'},pr=cfg.get('pr'),branch='claude/beampair8',sha=sha,batch=batch.name))
    lease=ROOT/'leases/beampair8.json';started=now()
    def claim(concurrency):
        write_json(lease,dict(task=TASK,pid=os.getpid(),started=started,expected_end='finite queue; max8h per run then analysis',
            concurrency=concurrency,source_sha=sha,batch=str(batch)))
    claim(0)
    pending=list(cfg['episodes']);active=[];done=[];stopped=False;wave_passed=False;launched=0
    env={**os.environ,'PYTHONPATH':str(src),'MUJOCO_GL':'osmesa','OMP_NUM_THREADS':'1',
        'OPENBLAS_NUM_THREADS':'1','MKL_NUM_THREADS':'1','LP_NUM_THREADS':'1'}
    def admit():
        others={p.name:load_optional(p) for p in (ROOT/'leases').glob('*.json') if p!=lease}
        reserved=sum(int(v.get('concurrency',0)) for v in others.values())
        procs=processes();free=shutil.disk_usage(ROOT).free
        available=next(int(l.split()[1])*1024 for l in Path('/proc/meminfo').read_text().splitlines() if l.startswith('MemAvailable:'))
        value=dict(other_leases=others,other_reserved=reserved,processes=procs,free_bytes=free,
            own_requested=cfg['max_parallel'],loadavg=os.getloadavg(),available_memory_bytes=available,time_utc=now())
        write_json(batch/'admission.json',value)
        assert free>=cfg['disk_floor_bytes']+(len(pending)+len(active))*cfg['per_run_budget_bytes']
        assert available>=6*1024**3
        return reserved+cfg['max_parallel']<=40 and len(procs)+cfg['max_parallel']<=40
    def stop(reason):
        nonlocal stopped
        stopped=True;write_json(batch/'SUBMISSION_STOP.json',dict(reason=reason,time_utc=now()))
    try:
        while not admit():time.sleep(5)
        claim(cfg['max_parallel'])
        while pending or active:
            while pending and len(active)<cfg['max_parallel'] and not stopped and (wave_passed or launched<cfg['max_parallel']):
                index=pending[0];e=plan['episodes'][index]
                # Recheck other reservations immediately before each mutation.
                others={p.name:load_optional(p) for p in (ROOT/'leases').glob('*.json') if p!=lease}
                assert sum(int(v.get('concurrency',0)) for v in others.values())+cfg['max_parallel']<=40
                d=ROOT/'runs'/f"beampair8-{cfg['stage']}-{e['seed']}-{sha[:8]}";d.mkdir(exist_ok=False)
                write_json(d/'RUN_META.json',dict(**{'class':'dev'},pr=cfg.get('pr'),branch='claude/beampair8',sha=sha,batch=batch.name))
                (d/'SOURCE_SHA').write_text(sha+'\n')
                cmd=['timeout','--signal=INT','8h',str(PY),'-m','scripts.run_beampair8','--plan',cfg['plan'],
                    '--episode',str(index),'--out',str(d/'raw'),'--dependency-root',str(ROOT/'src/26f84d0f0ada1c33473c83cca2d3415ce51bd247')]
                log=(d/'log.txt').open('x');p=subprocess.Popen(cmd,cwd=src,env=env,stdout=log,stderr=subprocess.STDOUT,start_new_session=True)
                write_json(d/'PROCESS.json',dict(pid=p.pid,command=cmd,started_utc=now(),episode=index,seed=e['seed']))
                active.append(dict(p=p,log=log,d=d,seed=e['seed'],episode=index));pending.pop(0);launched+=1
            for item in active[:]:
                code=item['p'].poll()
                if code is None:continue
                item['log'].close();d=item['d'];r=load_optional(existing(d/'raw','result.json'))
                a=load_optional(d/'recording-admission.json')
                category='HOST_ERROR' if code or not r or r.get('status')=='HOST_ERROR' else 'cap_end' if r.get('cap_end') else 'success' if r.get('physical_success') else 'teacher_failure'
                row=dict(seed=item['seed'],episode=item['episode'],path=str(d),exit=code,category=category,admitted=a.get('admitted',False),sim_s=r.get('sim_s'))
                (d/'EXIT').write_text(str(code)+'\n');write_json(d/'EXIT.json',row)
                if cfg['stage']=='identity' and category=='success':
                    before=ROOT/'runs'/f"beampair7-gate-r2-{item['seed']}-835ccef2"
                    row['identity']=command_identity(before,d);write_json(d/'identity.json',row['identity'])
                    if not row['identity']['passed']:stop(dict(category='recording_changes_commands',seed=item['seed']))
                if category=='HOST_ERROR':stop(dict(category=category,seed=item['seed']))
                if category=='teacher_failure' and cfg['stage']=='record':stop(dict(category=category,seed=item['seed'],note='inspect failure before more submission; active finite runs finish'))
                done.append(row);active.remove(item)
            if not wave_passed and launched>=cfg['max_parallel'] and not active:
                speeds=[]
                for row in done:
                    r=load_optional(existing(Path(row['path'])/'raw','result.json'))
                    if r.get('first30_speed'):speeds.append(r['first30_speed']['wall_per_sim'])
                    elif r.get('sim_s',0)>=30:stop('missing_first30')
                timing=dict(N=len(speeds),median=statistics.median(speeds) if speeds else None,values=speeds,block_threshold=6.)
                write_json(batch/'first30-speed.json',timing)
                if speeds and timing['median']>6.:stop(dict(category='SPEED_GATE_FAIL',timing=timing))
                else:wave_passed=True
            write_json(batch/'progress.json',dict(completed=done,running=[x['seed'] for x in active],not_started=pending,stopped=stopped))
            if stopped and not active:break
            time.sleep(2)
    finally:
        for item in active:item['p'].wait();item['log'].close()
        write_json(batch/'DONE.json',dict(completed=done,not_started=pending,stopped=stopped,finished_utc=now()))
        claim(0)
    if cfg['stage']=='identity':
        proof=dict(passed=len(done)==4 and all(x.get('identity',{}).get('passed') for x in done),source_sha=sha,runs=done)
        write_json(Path(cfg['identity_output']),proof)


if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('config',type=Path);run(p.parse_args().config)
