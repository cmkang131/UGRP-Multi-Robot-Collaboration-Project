"""One remote CUDA step, small evidence retrieval, then guarded stop of gcp5."""
import hashlib
import json
from pathlib import Path
import subprocess
import sys
import time

sys.path.insert(0,str(Path(__file__).resolve().parents[2]))
from scripts import gcpctl
from ops import ROOT, EVIDENCE, cloud


def remote(name, command):
    started=time.time()
    r=subprocess.run(['ssh','-o','BatchMode=yes','gcp5',command],capture_output=True,text=True)
    record=dict(command=['ssh','gcp5',command],returncode=r.returncode,elapsed_s=time.time()-started,stdout=r.stdout,stderr=r.stderr)
    (EVIDENCE/(name+'.json')).write_text(json.dumps(record,indent=2)+'\n')
    if r.returncode: raise RuntimeError(f'{name}: {r.stderr[-1500:]} {r.stdout[-1500:]}')
    print(name,'PASS',flush=True)
    return r.stdout


assert remote('installation', 'test "$(cat /home/ugrp/ugrp-sim/setup/install.EXIT)" = 0; cat /home/ugrp/ugrp-sim/setup/install.EXIT').strip()=='0'
remote('smoke-command', 'cd /home/ugrp/ugrp-sim/setup && /home/ugrp/ugrp-sim/ugrp/.venv-warp/bin/python smoke.py smoke-result.json > smoke.log 2>&1')
remote('audit-command', 'cd /home/ugrp/ugrp-sim/setup && sudo python3 audit_guest.py guest-audit.json')
files=['smoke-result.json','guest-audit.json','warp-freeze.txt','cpu-freeze.txt','act-freeze.txt','dataset-verification.json','training-summary.json']
checks=remote('retrieval-hashes', 'cd /home/ugrp/ugrp-sim/setup && sha256sum '+' '.join(files+['setup_guest.sh','smoke.py','audit_guest.py','training_smoke.py','pin_act_codec.sh']))
subprocess.run(['scp',*[f'gcp5:/home/ugrp/ugrp-sim/setup/{p}' for p in files],str(EVIDENCE)+'/'],check=True)
expected={line.split()[1]:line.split()[0] for line in checks.splitlines()}
for name in files:
    assert hashlib.sha256((EVIDENCE/name).read_bytes()).hexdigest()==expected[name]
for name in ['setup_guest.sh','smoke.py','audit_guest.py','training_smoke.py','pin_act_codec.sh']:
    assert hashlib.sha256((ROOT/name).read_bytes()).hexdigest()==expected[name]
training=json.loads((EVIDENCE/'training-summary.json').read_text())
assert training['status']=='PASS' and training['steps_completed']==50 and training['readback_verified'] and training['optimizer_reloaded']
assert set((EVIDENCE/'act-freeze.txt').read_text().splitlines())==set((EVIDENCE/'act-freeze-reference.txt').read_text().splitlines())
assert json.loads((EVIDENCE/'dataset-verification.json').read_text())['all_sha256_match']
audit=json.loads((EVIDENCE/'guest-audit.json').read_text())
assert not audit['known_credential_paths_present']
assert audit['idle_timer']['stdout'].strip()=='active'
startup=gcpctl.STARTUP.read_text()
assert audit['idle_guard']==startup.split("<<'G'\n",1)[1].split('\nG\n',1)[0]+'\n'
assert json.loads((EVIDENCE/'smoke-result.json').read_text())['status']=='PASS'
probe=subprocess.run([sys.executable,'scripts/gcpctl.py','stop','gcp5'],capture_output=True,text=True)
(EVIDENCE/'stop-defers-during-setup.json').write_text(json.dumps(dict(returncode=probe.returncode,stdout=probe.stdout,stderr=probe.stderr),indent=2)+'\n')
assert probe.returncode==75
remote('before-stop-audit', 'find /home/ugrp/ugrp-sim/leases -maxdepth 1 -type f -printf "%f\\n"; ps -u ugrp -o pid,comm,args; nvidia-smi --query-compute-apps=pid,process_name,used_gpu_memory --format=csv,noheader')
remote('release-own-lease', 'test "$(find /home/ugrp/ugrp-sim/leases -maxdepth 1 -type f -printf "%f\\n")" = gcp5setup.json && ! pgrep -u ugrp -x "python[0-9.]*|mujoco|ffmpeg" >/dev/null && rm /home/ugrp/ugrp-sim/leases/gcp5setup.json && test -z "$(ls -A /home/ugrp/ugrp-sim/leases)"')
r=subprocess.run([sys.executable,'scripts/gcpctl.py','stop','gcp5'],capture_output=True,text=True)
(EVIDENCE/'l4-stop.json').write_text(json.dumps(dict(returncode=r.returncode,stdout=r.stdout,stderr=r.stderr),indent=2)+'\n')
assert r.returncode==0
vm=cloud('l4-final','compute','instances','describe','ugrp-act-l4-gcp5','--zone=asia-northeast3-a')
assert vm['status']=='TERMINATED'
assert 'maxRunDuration' not in vm['scheduling'] and 'terminationTime' not in vm['scheduling']
assert not vm.get('serviceAccounts')
metadata={item['key']:item['value'] for item in vm['metadata']['items']}
assert metadata['block-project-ssh-keys']=='true' and metadata['startup-script']==startup
cloud('instances-final','compute','instances','list')
cloud('disks-final','compute','disks','list')
cloud('l4-disk-final','compute','disks','describe','ugrp-act-l4-gcp5','--zone=asia-northeast3-a')
(EVIDENCE/'verification.json').write_text(json.dumps(dict(retrieved_hashes_verified=True,source_hashes_verified=True,idle_guard_exact=True,credentials_absent=True,own_lease_removed=True,other_jobs_before_stop=False,runtime_cap_absent=True,vm_terminated=True,act_versions_exact=True,dataset_all_hashes_match=True,training_steps=50,training_save_reload=True),indent=2)+'\n')
print('gcp5 GPU infrastructure verified and TERMINATED',flush=True)
