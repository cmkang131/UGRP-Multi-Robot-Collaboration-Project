"""Mac pipe only: immutable allowlisted gcp2 data -> gcp6, no credentials copied."""
import datetime
import json
from pathlib import Path
import subprocess
import time

from ops import ROOT, EVIDENCE

source = json.loads((EVIDENCE/'gcp2-training-reference-host.json').read_text())['result']
ip = source['networkInterfaces'][0]['accessConfigs'][0]['natIP']
ssh_source = ['ssh','-i',str(Path.home()/'.ssh/ugrp_gcp2'),'-o','IdentitiesOnly=yes',
              '-o','BatchMode=yes','ugrp@'+ip]
base = '/home/ugrp/ugrp-sim'
data = 'ops-reviews/actdiag/infer-final-v1/dataset-view'
stages = 'ops-reviews/beamact2/data-v1/stages.json.zst'
manifest = json.loads((EVIDENCE/'source-data-manifest.json').read_text())
assert manifest['dataset_manifest_sha256'] == 'a0f5d8a1c6c9b6c4988122ae40bf412c4c705f3c34740d8d7a91c93fef58d6cd'
prepare = f'test ! -e {base}/{data} && test ! -e {base}/{stages} && command -v zstd && df -B1 {base}'
r = subprocess.run(['ssh','gcp6',prepare],capture_output=True,text=True,check=True)
free = int(r.stdout.splitlines()[-1].split()[3])
assert free > manifest['total_bytes'] + 8*1024**3, 'preserve project disk floor'
started = time.time()
with (EVIDENCE/'data-stream-source.log').open('w') as a, (EVIDENCE/'data-stream-target.log').open('w') as b:
    sender = subprocess.Popen(ssh_source+[
        f'set -o pipefail; tar -C {base} -cf - {data} {stages} | zstd -T2 -1 -c'],stdout=subprocess.PIPE,stderr=a)
    receiver = subprocess.Popen(['ssh','gcp6',f'set -o pipefail; zstd -d -c | tar -C {base} -xpf -'],
                                stdin=sender.stdout,stdout=b,stderr=b)
    sender.stdout.close()
    sent, received = sender.wait(), receiver.wait()
record = dict(started_utc=datetime.datetime.fromtimestamp(started,datetime.timezone.utc).isoformat(),
              elapsed_s=time.time()-started,sender_exit=sent,receiver_exit=received,
              source='gcp2 L4:'+base+'/'+data,target='gcp6:'+base+'/'+data,
              logical_bytes=manifest['total_bytes'],mac_raw_bytes_saved=0,private_keys_copied=0)
(EVIDENCE/'data-stream.json').write_text(json.dumps(record,indent=2)+'\n')
assert sent == received == 0
script = (ROOT/'data_manifest.py').read_text()
r = subprocess.run(['ssh','gcp6','python3 - '+base+'/setup/target-data-manifest.json'],
                   input=script,capture_output=True,text=True,check=True)
print(r.stdout,flush=True)
r = subprocess.run(['ssh','gcp6','cat '+base+'/setup/target-data-manifest.json'],capture_output=True,text=True,check=True)
target = json.loads(r.stdout)
(EVIDENCE/'target-data-manifest.json').write_text(r.stdout)
assert source is not None and manifest['files'].keys() == target['files'].keys()
assert all((v['sha256'],v['bytes']) == (target['files'][k]['sha256'],target['files'][k]['bytes'])
           for k,v in manifest['files'].items())
# Source stats must remain unchanged throughout transmission. Never stop gcp2.
probe = """import json
from pathlib import Path
b=Path('/home/ugrp/ugrp-sim')
m=json.loads((b/'setup/gcp6setup-transfer/source-manifest.json').read_text())
assert all((b/k).stat().st_size==v['bytes'] and (b/k).stat().st_mtime_ns==v['mtime_ns'] for k,v in m['files'].items())
print('SOURCE_UNCHANGED')
"""
r = subprocess.run(ssh_source+['python3 -'],input=probe,capture_output=True,text=True,check=True)
assert r.stdout.strip() == 'SOURCE_UNCHANGED'
subprocess.run(ssh_source+['rm /home/ugrp/ugrp-sim/leases/gcp6setup-transfer.json'],check=True)
record.update(all_files_sha256_equal=True,source_stats_unchanged=True,source_own_lease_removed=True,
              source_vm_stop_attempted=False,files_n=manifest['files_n'])
(EVIDENCE/'data-transfer-verification.json').write_text(json.dumps(record,indent=2)+'\n')
print(json.dumps(record),flush=True)
