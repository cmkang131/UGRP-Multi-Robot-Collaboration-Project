"""Ship one immutable snapshot to shared.git, clone by direct reference only."""
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
import json
import subprocess
import shlex
import sys

ROOT=Path(__file__).resolve().parents[2]
SHA=subprocess.check_output(['git','rev-parse','HEAD'],cwd=ROOT,text=True).strip()
BASE='/home/ugrp/ugrp-sim'
SSH=['ssh','-o','BatchMode=yes','-o','ConnectTimeout=15']

def one(host,arm,pack):
    shared=BASE+'/git-shared.git';dest=BASE+'/src/'+SHA
    command=f'''set -eu
    git --git-dir={shared} config gc.auto 0
    git --git-dir={shared} config maintenance.auto false
    git --git-dir={shared} index-pack --stdin
    test -f {shared}/shallow && cat {shared}/shallow || true
    echo {SHA} >> {shared}/shallow
    sort -u {shared}/shallow -o {shared}/shallow
    git --git-dir={shared} update-ref refs/heads/beamact3c {SHA}
    git clone --no-local --reference {shared} --single-branch --branch beamact3c {shared} {dest}
    cd {dest}
    git checkout --detach {SHA}
    test -z "$(git status --porcelain)"
    cat .git/objects/info/alternates
    systemctl is-active ugrp-idle-guard.timer
    '''
    with pack.open('rb') as stream:
        result=subprocess.run([*SSH,host,command],stdin=stream,stdout=subprocess.PIPE,stderr=subprocess.STDOUT,text=True)
    print(host,result.returncode,result.stdout,flush=True)
    if result.returncode:raise RuntimeError('deploy failed '+host)
    launch=f'''cd {dest} && mkdir -p {BASE}/ops-reviews/beamact3c && nohup env PYTHONPATH={dest} /home/ugrp/ugrp-rl1b-act-env/bin/python experiments/2026-10-16-beamact3/C1-managed.py --arm {arm} > {BASE}/ops-reviews/beamact3c/{arm}-managed.log 2>&1 < /dev/null &'''
    # Background under a new session, independent of this SSH transport.
    command='python3 -c '+shlex.quote('import subprocess; p=subprocess.Popen('+repr(['bash','-c',launch.replace(' &','')])+',start_new_session=True,stdin=subprocess.DEVNULL,stdout=subprocess.DEVNULL,stderr=subprocess.DEVNULL);print(p.pid)')
    result=subprocess.run([*SSH,host,command],capture_output=True,text=True,check=True)
    print(host,'managed launcher',result.stdout,flush=True)
    return dict(host=host,arm=arm,source_sha=SHA,source=dest,launcher_pid=result.stdout.strip(),reference=shared)

if __name__=='__main__':
    pack=ROOT/'outputs/e2e18-admin'/('C1-source-'+SHA+'.pack')
    objects=subprocess.check_output(['git','rev-list','--objects','--no-walk',SHA],cwd=ROOT)
    with pack.open('wb') as stream:
        subprocess.run(['git','pack-objects','--stdout'],cwd=ROOT,input=objects,stdout=stream,check=True)
    print('pack',pack.stat().st_size,flush=True)
    with ThreadPoolExecutor(2) as pool:
        jobs=[pool.submit(one,h,a,pack) for h,a in [('gcp5','C1'),('gcp6','C2')]]
        rows=[j.result() for j in jobs]
    (ROOT/'experiments/2026-10-16-beamact3/C1-deployment.json').write_text(json.dumps(rows,indent=2)+'\n')
