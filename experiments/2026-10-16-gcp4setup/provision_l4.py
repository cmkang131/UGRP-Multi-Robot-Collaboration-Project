"""Create gcp4 only after the budget test, then install fresh public packages."""
import datetime
import hashlib
import json
import os
from pathlib import Path
import shlex
import socket
import subprocess
import sys
import time

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
from scripts import gcpctl
from ops import ROOT, EVIDENCE, PROJECT, cloud

observations = json.loads((EVIDENCE/'test-observations.json').read_text())
assert any(x['status']=='STOPPING' for x in observations) and observations[-1]['status']=='TERMINATED'
assert json.loads((EVIDENCE/'instances-after-test.json').read_text()) == []
assert json.loads((EVIDENCE/'disks-after-test.json').read_text()) == []
budget=json.loads((EVIDENCE/'budget-create.json').read_text())
number=json.loads((EVIDENCE/'project.json').read_text())['projectNumber']
assert budget['budgetFilter']['projects']==['projects/'+number]
assert budget['budgetFilter']['creditTypesTreatment']=='INCLUDE_ALL_CREDITS'
assert budget['amount']['specifiedAmount']=={'currencyCode':'KRW','units':'1000'}
assert not budget['notificationsRule'].get('disableDefaultIamRecipients',False)
key=Path.home()/'.ssh/ugrp_gcp4'
assert not key.exists(), 'Do not overwrite an existing dedicated SSH key'
subprocess.run(['ssh-keygen','-q','-t','ed25519','-N','','-C','ugrp-gcp4','-f',str(key)],check=True)
assert key.stat().st_mode & 0o077 == 0
command=gcpctl.create_command('gcp4',key.with_suffix('.pub').read_text().strip())
assert not any(x.startswith('--max-run-duration') for x in command)
args=command[1:]
for flag in ['--account','--project']:
 i=args.index(flag); del args[i:i+2]
cloud('l4-create',*args)
config=Path.home()/'.ssh/config'
original=config.read_text()
assert not any(line.strip()=='Host gcp4' for line in original.splitlines())
block=gcpctl.SSH_CONFIG.format(host='gcp4',identity_file=str(key),config=gcpctl.CONFIG.resolve(),script=Path(gcpctl.__file__).resolve())
config.write_text(original.rstrip()+'\n\n'+block)
os.chmod(config,0o600)
for attempt in range(40):
 probe=subprocess.run(['ssh','-o','BatchMode=yes','-o','ConnectTimeout=10','gcp4','true'],capture_output=True,text=True)
 if probe.returncode==0: break
 time.sleep(5)
else: raise RuntimeError('SSH not ready; VM remains guarded')
sha=subprocess.check_output(['git','rev-parse','HEAD'],text=True).strip()
lease=dict(task='gcp4setup',pid=os.getpid(),owner_host=socket.gethostname(),source_sha=sha,
           started_utc=datetime.datetime.now(datetime.timezone.utc).isoformat(),expected_end_utc=(datetime.datetime.now(datetime.timezone.utc)+datetime.timedelta(hours=1)).isoformat())
subprocess.run(['ssh','gcp4','mkdir -p /home/ugrp/ugrp-sim/{setup,leases} && cat > /home/ugrp/ugrp-sim/leases/gcp4setup.json'],input=json.dumps(lease)+'\n',text=True,check=True)
files=[ROOT/n for n in ('setup_guest.sh','smoke.py','audit_guest.py')]
subprocess.run(['scp',*map(str,files),'gcp4:/home/ugrp/ugrp-sim/setup/'],check=True)
source={p.name:hashlib.sha256(p.read_bytes()).hexdigest() for p in files}
(EVIDENCE/'probe-source.json').write_text(json.dumps(dict(source_sha=sha,files_sha256=source),indent=2)+'\n')
remote='cd /home/ugrp/ugrp-sim/setup && nohup bash -c '+shlex.quote('bash setup_guest.sh > install.log 2>&1; rc=$?; echo "$rc" > install.EXIT; exit "$rc"')+' </dev/null > launch.log 2>&1 &'
subprocess.run(['ssh','gcp4',remote],check=True)
print('Fresh install launched; own lease retained; infrastructure watchdogs unchanged',flush=True)
