"""gcp2 CPU: stage and verify terminal lightweight log copy before adding new batch paths."""
import argparse
import datetime as dt
import hashlib
import json
import os
from pathlib import Path
import shutil
import socket
import subprocess
import sys
import tarfile
import tempfile

assert socket.gethostname().split('.')[0]=='ugrp-sim-gcp2'
p=argparse.ArgumentParser();p.add_argument('--tags',required=True);p.add_argument('--label',required=True);a=p.parse_args();tags=a.tags.split(',')
assert tags and len(tags)==len(set(tags)) and all(t not in ('.','..') and Path(t).name==t for t in tags)
assert a.label not in ('.','..') and Path(a.label).name==a.label
r=Path('/home/ugrp/ugrp-sim');root=r/'runs/warp8';ops=r/'ops-reviews/warp8';transfers=ops/'transfers';transfers.mkdir(parents=True,exist_ok=True)
assert shutil.disk_usage(r).free>=8*1024**3  # Existing storage-plan floor, not a physical acceptance threshold.
out=ops/'terminal-recounts'/a.label;assert not out.exists();lease=r/'leases/warp8-terminal-recount.json';assert not lease.exists()
for tag in tags:assert not (root/tag).exists() and not list(root.glob(tag+'.*')), 'preserve existing batch evidence'
lease.write_text(json.dumps(dict(task='warp8',pid=os.getpid(),started_at=dt.datetime.now(dt.timezone.utc).isoformat(),expected_end=(dt.datetime.now(dt.timezone.utc)+dt.timedelta(minutes=15)).isoformat(),purpose='lightweight-log CPU transfer/recount; no GPU/physics/model')))
staging=Path(tempfile.mkdtemp(prefix=a.label+'-',dir=transfers));received={}
try:
 with tarfile.open(fileobj=sys.stdin.buffer,mode='r|gz') as tar:
  for member in tar:
   rel=Path(member.name);assert member.isfile() and not rel.is_absolute() and '..' not in rel.parts
   assert rel.parts[0] in tags or (len(rel.parts)==1 and any(member.name.startswith(tag+'.') for tag in tags))
   target=staging/rel;assert not target.exists();target.parent.mkdir(parents=True,exist_ok=True);data=tar.extractfile(member).read();assert len(data)==member.size;target.write_bytes(data);received[str(rel)]=dict(bytes=len(data),sha256=hashlib.sha256(data).hexdigest())
 manifest_name=tags[0]+'.transfer-source.json';manifest=json.loads((staging/manifest_name).read_text());assert manifest['tags']==tags
 assert manifest['files']=={k:v for k,v in received.items() if k!=manifest_name}, 'source/CPU SHA mismatch or incomplete payload'
 for relative,expected in manifest['files'].items():
  path=staging/relative
  with path.open('rb') as stream:actual=dict(bytes=path.stat().st_size,sha256=hashlib.file_digest(stream,'sha256').hexdigest())
  assert actual==expected, 'CPU staged-file SHA mismatch: '+relative
 targets=list(staging.iterdir());assert all(not (root/p.name).exists() for p in targets)
 for path in targets:path.rename(root/path.name)
 staging.rmdir()
 receipt=dict(utc=dt.datetime.now(dt.timezone.utc).isoformat(),source_host='gcp3',analysis_host='gcp2_CPU',tags=tags,source_SHA_equal_N=len(manifest['files']),copied_bytes=sum(v['bytes'] for v in received.values()),source_manifest=str(root/manifest_name),receiver_sha256=hashlib.sha256(Path(__file__).read_bytes()).hexdigest(),original_CPU_batches_overwritten=False)
 (transfers/(a.label+'.json')).write_text(json.dumps(receipt,indent=2)+'\n')
 subprocess.run(['python3',str(r/'ops-reviews/warp8-collect_gate.py'),'--root',str(root),'--out',str(out)],check=True)
 print(json.dumps(receipt))
finally:
 assert json.loads(lease.read_text())['pid']==os.getpid();lease.unlink()
