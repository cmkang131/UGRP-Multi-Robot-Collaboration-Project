#!/usr/bin/env python3
"""VM3/4 only: submit registered repair cells from one committed source."""
import argparse
import json
import os
from pathlib import Path
import re
import shlex
import shutil
import socket
import subprocess
import time

HERE=Path(__file__).resolve().parent
ROOT=HERE.parents[1]
DEADLINE=1791822360


def active():
    result=[]
    for p in Path('/proc').iterdir():
        if not p.name.isdigit():continue
        try:
            argv=(p/'cmdline').read_bytes().split(b'\0')
            if b'scripts.run_e2e_ownmap_live' in argv and b'--execute' in argv:result.append(int(p.name))
        except (OSError,ProcessLookupError):pass
    return result


def main():
    p=argparse.ArgumentParser();p.add_argument('--sha',required=True)
    p.add_argument('--host',choices=('azure3','azure4'),required=True)
    p.add_argument('--registration',choices=('repair','native'),default='repair')
    p.add_argument('--plan',action='store_true');a=p.parse_args()
    cells=[r for r in json.loads((HERE/f'boundary-{a.registration}-registration.json').read_text())['cells'] if r['host']==a.host]
    assert len(cells)==(3 if a.registration=='native' else 6 if a.host=='azure3' else 5)
    assert len({r['name'] for r in cells})==len(cells)
    if a.plan:print(json.dumps(cells));return
    assert socket.gethostname().split('.')[0]=='ugrp-sim-'+a.host
    assert len(active())+len(cells)<=6, 'VM_BATCH_SIX_RUN_CAP'
    assert subprocess.check_output(['git','rev-parse','HEAD'],cwd=ROOT,text=True).strip()==a.sha
    assert not subprocess.check_output(['git','status','--porcelain'],cwd=ROOT).strip()
    assert os.getpriority(os.PRIO_PROCESS,0)==0
    base=Path.home()/'ugrp-sim'
    for host in ('x86','arm','mac'):
        b=base/f'e2e-idle-repair-budget-{host}.json'
        assert time.time()-b.stat().st_mtime<300 and json.loads(b.read_text())['ok']
    subprocess.run(['python3','/usr/local/lib/ugrp-storage/scripts/azure_shutdown.py','admit'],check=True)
    line=next(s for s in (HERE/'azure-pair.sh').read_text().splitlines() if s.startswith('COMMON=('))
    common=shlex.split(line[len('COMMON=('):-1])
    common=[v.replace('$SHA',a.sha).replace('$B',str(base)) for v in common]
    # Preserve the previous running cell's immutable receipt.
    common[common.index('--relay-receipt')+1]=str(base/'relays/e2e-idle/b.json')
    remaining=min(25200,int(DEADLINE-time.time()-300),int(28800-float(Path('/proc/uptime').read_text().split()[0])-600))
    assert remaining>600
    common[common.index('--wall-cap-s')+1]=str(remaining)
    env={**os.environ,**dict(MUJOCO_GL='osmesa',OMP_NUM_THREADS='1',LP_NUM_THREADS='1',OPENBLAS_NUM_THREADS='1',MKL_NUM_THREADS='1')}
    subprocess.run([str(ROOT/'.venv-sim/bin/python'),'-c','from scripts.run_e2e_azure_batch import prepare_native; prepare_native()'],cwd=ROOT,env=env,check=True)
    for cell in cells:
        assert len(active())<6, 'VM_SIX_RUN_CAP'
        while True:
            mem=int(next(x.split()[1] for x in Path('/proc/meminfo').read_text().splitlines() if x.startswith('MemAvailable:')))*1024
            if mem>=6*2**30 and os.getloadavg()[0]<51:break
            time.sleep(10)
        assert shutil.disk_usage(base).free >= 8*2**30
        remaining=min(25200,int(DEADLINE-time.time()-300),int(28800-float(Path('/proc/uptime').read_text().split()[0])-600))
        assert remaining>600
        common[common.index('--wall-cap-s')+1]=str(remaining)
        run=base/'runs'/cell['name'];run.mkdir()
        (base/'leases'/cell['name']).touch()
        meta=dict(cell,pr=453,sha=a.sha,branch='codex/e2e-idle',batch='e2e17-'+a.registration,submitted_unix=time.time(),wall_cap_s=remaining,storage_budget_bytes=4*2**30)
        meta['class']='dev'
        (run/'RUN_META.json').write_text(json.dumps(meta)+'\n');(run/'SOURCE_SHA').write_text(a.sha+'\n')
        (run/'resource-admission.json').write_text(json.dumps(dict(loadavg=os.getloadavg(),mem_available_bytes=mem,free_bytes=shutil.disk_usage(base).free,active_pids=active()))+'\n')
        workflow={213:'e2e-boundary-native-v213',211:'e2e-boundary-repair-v211',208:'e2e-explore-deadlock-v208',207:'e2e-vomask-turn-v207'}[cell['bundle']]
        command=[str(ROOT/'.venv-sim/bin/python'),'-m','scripts.sim_cli','workflow','run',workflow,'--timeout',str(remaining),'--',*common,'--seed',str(cell['seed']),'--output',str(run/'raw'),'--explore-deadlock',cell['deadlock'],'--boundary-association',cell['association'],'--boundary-retry',cell['retry'],'--boundary-coverage',cell.get('coverage','off'),'--execute']
        with (run/'launch.log').open('wb') as log:
            proc=subprocess.Popen(['python3','/usr/local/lib/ugrp-storage/scripts/remote_run_finish.py','--source',str(ROOT),'--run',str(run),'--',*command],cwd=ROOT,env=env,stdin=subprocess.DEVNULL,stdout=log,stderr=subprocess.STDOUT,start_new_session=True)
        print(json.dumps(dict(run=cell['name'],supervisor_pid=proc.pid,sha=a.sha,workflow=workflow)),flush=True)


if __name__=='__main__':main()
