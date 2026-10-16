"""gcp3 IO-only snapshot of a live first30 prefix; stdout tar, no source writes."""
import argparse
import datetime as dt
import hashlib
import io
import json
from pathlib import Path
import sys
import tarfile

p=argparse.ArgumentParser()
p.add_argument('--batch',default='beam40-r2')
p.add_argument('--worlds',default='0,28')
a=p.parse_args()
assert a.batch not in ('.','..') and Path(a.batch).name==a.batch
root=Path('/home/ugrp/ugrp-sim/runs/warp8')/a.batch
assert (root/'first30-speed.json').is_file(), 'do not label an unfinished first30 complete'
selected={f'world-{int(i):03d}' for i in a.worlds.split(',')}
started=dt.datetime.now(dt.timezone.utc).isoformat()
entries={};skipped=[]
with tarfile.open(fileobj=sys.stdout.buffer,mode='w|gz') as archive:
 for path in sorted(root.rglob('*')):
  if not path.is_file():continue
  rel=path.relative_to(root)
  metadata=path.name.endswith(('.json','.jsonl','.json.zst','.jsonl.zst'))
  media=(rel.parts[0] in selected or path.stem.removesuffix('-states') in selected) and path.suffix in ('.jpg','.png','.xml','.npz')
  if not (metadata or media):continue
  try:
   before=path.stat(); value=path.read_bytes(); after=path.stat()
  except FileNotFoundError:
   skipped.append(str(rel));continue
  item=tarfile.TarInfo(a.batch+'/'+str(rel));item.size=len(value);item.mtime=before.st_mtime;item.mode=0o644
  archive.addfile(item,io.BytesIO(value))
  entries[str(rel)]=dict(bytes=len(value),sha256=hashlib.sha256(value).hexdigest(),source_size_before=before.st_size,source_size_after=after.st_size,changed_during_read=before.st_mtime_ns!=after.st_mtime_ns)
 manifest=dict(exporter_sha256=hashlib.sha256(Path(__file__).read_bytes()).hexdigest(),batch=a.batch,source_host='gcp3',started=started,ended=dt.datetime.now(dt.timezone.utc).isoformat(),files=entries,skipped=skipped,scope='live per-file prefixes; no source mutations; final incomplete JSONL row excluded only by downstream decoder; not full-run backup')
 value=(json.dumps(manifest,indent=2)+'\n').encode();item=tarfile.TarInfo(a.batch+'/snapshot-manifest.json');item.size=len(value);item.mode=0o644;archive.addfile(item,io.BytesIO(value))
