import datetime as dt,hashlib,json,os,subprocess,sys,tarfile
from pathlib import Path
r=Path('/home/ugrp/ugrp-sim'); ops=r/'ops-reviews/warp8'; ops.mkdir(exist_ok=True)
lease=r/'leases/warp8-recount.json'; assert not lease.exists()
lease.write_text(json.dumps(dict(task='warp8',stage='R1_raw_recount',pid=os.getpid(),started_at=dt.datetime.now(dt.timezone.utc).isoformat(),expected_end=(dt.datetime.now(dt.timezone.utc)+dt.timedelta(minutes=15)).isoformat(),gpu=False)))
root=r/'runs/warp8'; root.mkdir(exist_ok=True)
try:
 files={}
 with tarfile.open(fileobj=sys.stdin.buffer,mode='r|gz') as archive:
  for item in archive:
   rel=Path(item.name)
   assert item.isfile() and not rel.is_absolute() and '..' not in rel.parts
   assert 'r2' not in rel.parts[0] and (rel.parts[0].startswith('beam40-') or rel.parts[0].startswith('releaseA'))
   target=root/rel; assert not target.exists(),str(target)
   target.parent.mkdir(parents=True,exist_ok=True); stream=archive.extractfile(item); value=stream.read(); assert len(value)==item.size; target.write_bytes(value)
   files[str(target)]=dict(bytes=len(value),sha256=hashlib.sha256(value).hexdigest())
 (ops/'R1-light-transfer.json').write_text(json.dumps(dict(files=files,source_host='gcp3',analysis_host='gcp2_CPU',scope='finished run metadata/raw JSON, no raw videos or simulator execution'),indent=2)+'\n')
 subprocess.run(['python3',str(r/'ops-reviews/warp8-collect_gate.py'),'--root',str(root),'--out',str(ops/'R1-recount')],check=True)
 print(json.dumps({'copied_files':len(files),'copied_bytes':sum(x['bytes'] for x in files.values())}))
finally:
 lease.unlink()
