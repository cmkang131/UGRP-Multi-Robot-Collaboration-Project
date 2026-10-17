"""Allowlisted dataset only, streamed through Mac SSH; private keys stay on Mac."""
import hashlib
import json
from pathlib import Path
import shlex
import subprocess
import time
from ops import EVIDENCE

source=json.loads((EVIDENCE/'gcp2-l4-ssh.json').read_text())
root='/home/ugrp/ugrp-sim/ops-reviews/actdiag/infer-final-v1/dataset-view'
reference='/home/ugrp/ugrp-sim/setup/gcp5setup-source/dataset-sha256.json'
r=subprocess.run(source+['cat '+reference],capture_output=True,text=True,check=True)
manifest=json.loads(r.stdout)
assert manifest['manifest_sha256']=='a0f5d8a1c6c9b6c4988122ae40bf412c4c705f3c34740d8d7a91c93fef58d6cd'
(EVIDENCE/'dataset-sha256.json').write_text(r.stdout)
# Dereference only files enumerated by the immutable dataset view. No home/archive copy.
assert all(not Path(x['path']).is_absolute() and '..' not in Path(x['path']).parts for x in manifest['files'])
files='\n'.join(x['path'] for x in manifest['files'])+'\n'
subprocess.run(source+['cat > /home/ugrp/ugrp-sim/setup/gcp5setup-source/files.txt'],input=files,text=True,check=True)
subprocess.run(['ssh','gcp5','mkdir -p '+root+' && test -z "$(ls -A '+root+')"'],check=True)
started=time.time()
# zstd is already available on source. Never stage raw dataset on Mac.
send='set -o pipefail; cd '+root+' && tar --dereference -cf - -T /home/ugrp/ugrp-sim/setup/gcp5setup-source/files.txt | zstd -T2 -1'
recv='set -o pipefail; cd '+root+' && zstd -d | tar -xf -'
a=subprocess.Popen(source+['bash -c '+shlex.quote(send)],stdout=subprocess.PIPE)
b=subprocess.Popen(['ssh','gcp5','bash -c '+shlex.quote(recv)],stdin=a.stdout)
a.stdout.close(); rc_b=b.wait();rc_a=a.wait()
if rc_a or rc_b:raise RuntimeError(f'transfer failed {rc_a=} {rc_b=}')
subprocess.run(['scp',str(EVIDENCE/'dataset-sha256.json'),'gcp5:/home/ugrp/ugrp-sim/setup/'],check=True)
code='''import json,hashlib,time
from pathlib import Path
b=Path('/home/ugrp/ugrp-sim/setup'); ref=json.loads((b/'dataset-sha256.json').read_text());d=Path(ref['root']);start=time.time();checked=0
for x in ref['files']:
 p=d/x['path'];h=hashlib.sha256()
 with p.open('rb') as f:
  for block in iter(lambda:f.read(8*1024**2),b''):h.update(block)
 assert p.stat().st_size==x['bytes'] and h.hexdigest()==x['sha256'],str(p)
 checked+=1
actual={str(p.relative_to(d)) for p in d.rglob('*') if p.is_file()}
assert actual=={x['path'] for x in ref['files']}
result=dict(status='PASS',files=checked,bytes=ref['bytes'],manifest_sha256=ref['manifest_sha256'],all_sha256_match=True,wall_s=time.time()-start)
(b/'dataset-verification.json').write_text(json.dumps(result,indent=2)+'\\n');print(json.dumps(result))
'''
r=subprocess.run(['ssh','gcp5','python3 -'],input=code,text=True,capture_output=True,check=True)
(EVIDENCE/'dataset-verification.json').write_text(r.stdout)
(EVIDENCE/'dataset-transfer.json').write_text(json.dumps(dict(status='PASS',seconds=time.time()-started,source='gcp2 L4:'+root,target='gcp5:'+root,raw_staged_on_mac=False,credentials_copied=False),indent=2)+'\n')
print(r.stdout,flush=True)
