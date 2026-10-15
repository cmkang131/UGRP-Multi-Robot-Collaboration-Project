"""Finite Mac SSH relay only. No local model/data loading, rendering or GUI."""
import argparse
from datetime import datetime, timezone
import json
from pathlib import Path
import subprocess
import shlex
import time

L4=['ssh','-o','BatchMode=yes','-i','/Users/changmin/.ssh/ugrp_gcp2','ugrp@34.64.52.225']
CPU=['ssh','-o','BatchMode=yes','gcp2']
BASE='/home/ugrp/ugrp-sim/ops-reviews/beamact2'


def query(host,code):
    # All supplied code is a fixed project-authored string, never user/provider
    # content. No credentials, model bytes or large raw logs are printed.
    result=subprocess.run([*host,'python3 -'],input=code,text=True,capture_output=True,check=True)
    return json.loads(result.stdout)


def relay_command(directory, send):
    code=f'''import datetime,json,os,pathlib,subprocess
lease=pathlib.Path('/home/ugrp/ugrp-sim/leases/beamact2-transfer.json')
with lease.open('x') as f:
 json.dump(dict(task='beamact2-transfer',pid=os.getpid(),started=datetime.datetime.now(datetime.timezone.utc).isoformat(),expected_end=(datetime.datetime.now(datetime.timezone.utc)+datetime.timedelta(minutes=20)).isoformat(),concurrency=0),f)
try:
 subprocess.run({['tar','-C',directory,'-cf' if send else '-xf','-','.'] if send else ['tar','-C',directory,'-xf','-']!r},check=True)
finally:
 lease.unlink()
'''
    return 'python3 -c '+shlex.quote(code)


def main():
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('--cpu-source',required=True)
    a=p.parse_args()
    if not a.cpu_source.startswith('/home/ugrp/ugrp-sim/src/'):
        raise ValueError('pinned CPU checkout required')
    started=time.monotonic()
    while True:
        status=query(L4,f'''import json,pathlib
r=pathlib.Path({BASE!r})
s=json.loads((r/'training-supervisor.json').read_text())
v={{'status':s['status'],'model':s.get('model'),'model_sha256':s.get('model_sha256')}}
for stage in ('main','smoke'):
 p=r/'train'/stage/'summary.json'
 if p.exists():
  q=json.loads(p.read_text());v.update(stage=stage,step=q['steps_completed'],stage_status=q['status'],readback=q['readback_verified']);break
print(json.dumps(v))
''')
        print(datetime.now(timezone.utc).isoformat(),'training',json.dumps(status),flush=True)
        if status['status']=='complete':break
        if status['status']!='running':raise RuntimeError('remote training failed; no evaluation submitted')
        if time.monotonic()-started>7*3600:raise TimeoutError('finite controller budget; no new batch')
        time.sleep(30)
    model=status['model']
    if not model.startswith(BASE+'/train/main/step-010000/'):
        raise ValueError('fixed final model only')
    target=BASE+'/model-v1'
    subprocess.run([*CPU,f'test ! -e {target} && mkdir -p {target}'],check=True)
    sender=subprocess.Popen([*L4,relay_command(model,True)],stdout=subprocess.PIPE)
    receiver=subprocess.Popen([*CPU,relay_command(target,False)],stdin=sender.stdout)
    sender.stdout.close()
    if receiver.wait() or sender.wait():raise RuntimeError('model relay failed')
    check=query(CPU,f'''import hashlib,json,pathlib
p=pathlib.Path({target!r});h=json.loads((p/'SHA256.json').read_text())
assert all(hashlib.sha256((p/k).read_bytes()).hexdigest()==v for k,v in h.items())
print(json.dumps(dict(model_sha256=h['model.safetensors'],files=len(h))))
''')
    if check['model_sha256']!=status['model_sha256']:raise ValueError('relayed model mismatch')
    print('model relay SHA verified',json.dumps(check),flush=True)
    command=f'''cd {a.cpu_source} && PYTHONPATH=. /home/ugrp/ugrp-sim/ugrp/.venv-sim/bin/python experiments/2026-10-16-beamact2/run_eval.py --model {target} --output {BASE}/heldout20-v1'''
    # Synchronous SSH owns only this finite remote supervisor. Its lease and
    # manager clean up its descendants; no task outside beamact2 is signalled.
    subprocess.run([*CPU,command],check=True)
    subprocess.run([*CPU,f'cd {a.cpu_source} && PYTHONPATH=. /home/ugrp/ugrp-sim/ugrp/.venv-sim/bin/python -m scripts.analyze_beamact2 --root {BASE}/heldout20-v1'],check=True)
    summary=query(CPU,f'''import json,pathlib
s=json.loads(pathlib.Path({BASE!r}+'/heldout20-v1/summary.json').read_text())
print(json.dumps({{k:s[k] for k in ('n','N','complete','funnel','reason_distribution','failure_stage_distribution')}}))
''')
    print('evaluation raw recount',json.dumps(summary),flush=True)


if __name__=='__main__':main()
