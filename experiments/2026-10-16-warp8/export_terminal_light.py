"""gcp3: stream immutable terminal lightweight logs only; never write source artifacts."""
import argparse
import datetime as dt
import hashlib
import io
import json
from pathlib import Path
import socket
import sys
import tarfile

assert socket.gethostname().split('.')[0]=='ugrp-act-l4-gcp3'
p=argparse.ArgumentParser();p.add_argument('--tags',required=True);a=p.parse_args();tags=a.tags.split(',');assert tags and len(tags)==len(set(tags))
root=Path('/home/ugrp/ugrp-sim/runs/warp8');selected=[];receipts={}
for tag in tags:
 assert tag not in ('.','..') and Path(tag).name==tag
 receipt=json.loads((root/(tag+'.receipt.json')).read_text());cmdline=Path('/proc')/str(receipt['pid'])/'cmdline'
 assert not cmdline.exists() or str(root/tag).encode() not in cmdline.read_bytes().split(b'\0')
 receipts[tag]=receipt
 for path in sorted(root.rglob('*')):
  if not path.is_file() or path.is_symlink():continue
  rel=path.relative_to(root)
  if (rel.parts[0]==tag or (len(rel.parts)==1 and path.name.startswith(tag+'.'))) and path.name.endswith(('.json','.jsonl','.json.zst','.jsonl.zst','.log','.log.zst')):selected.append(path)
assert selected and len(selected)==len(set(selected));entries={}
with tarfile.open(fileobj=sys.stdout.buffer,mode='w|gz') as tar:
 for path in selected:
  before=path.stat();data=path.read_bytes();after=path.stat();assert before.st_mtime_ns==after.st_mtime_ns and len(data)==before.st_size==after.st_size
  relative=str(path.relative_to(root));item=tarfile.TarInfo(relative);item.size=len(data);item.mode=0o644;tar.addfile(item,io.BytesIO(data));entries[relative]=dict(bytes=len(data),sha256=hashlib.sha256(data).hexdigest())
 manifest=dict(utc=dt.datetime.now(dt.timezone.utc).isoformat(),source_host='gcp3',tags=tags,receipts=receipts,files=entries,exporter_sha256=hashlib.sha256(Path(__file__).read_bytes()).hexdigest(),scope='terminal metadata/log CPU copy; no videos, RGB, NPZ or credentials; source bytes unchanged')
 data=(json.dumps(manifest,indent=2)+'\n').encode();item=tarfile.TarInfo(tags[0]+'.transfer-source.json');item.size=len(data);item.mode=0o644;tar.addfile(item,io.BytesIO(data))
