"""Own warpfit outputs only: verify old manifests, associate draft PR, compress losslessly."""
from pathlib import Path
import json,hashlib,subprocess,sys,datetime,os,fcntl
root=Path(sys.argv[1]).resolve()
analysis_only=str(root)=='/home/ugrp/ugrp-sim/ops-reviews/warpfit-ownhost'
if str(root) not in ['/home/ugrp/ugrp-sim/runs/warpfit','/home/ugrp/ugrp-sim/ops-reviews/warpfit/raw'] and not analysis_only:
 raise ValueError('only own raw root')
def sha(p):return hashlib.sha256(p.read_bytes()).hexdigest()
lock=(root/'.warpfit-archive.lock').open('a+')
fcntl.flock(lock,fcntl.LOCK_EX|fcntl.LOCK_NB)
# Fixed matrix: original N16 diagnostic16 + box repeat4 + cleared drive4 +
# N64 final12. An unsubmitted or interrupted queue is never archive-complete.
phases=[] if analysis_only else [('R2-retry1',16),('R2-box-repeat2',4),('R2-drive-clear-v1',4),('R3',12)]
if analysis_only:
 summary=json.loads((root/'report-final-v1/summary.json').read_text())
 if summary['status'] not in ('complete','comparison_complete_with_rejections'):
  raise ValueError('unfinished analysis report')
for phase,count in phases:
 attempts=json.loads((root/phase/'attempts.json').read_text())
 if len(attempts)!=count or any(r['status'] not in ('complete','HOST_ERROR') for r in attempts):
  raise ValueError('unfinished queue '+phase)
for p in root.glob('R*/**/result.json'):
 if json.loads(p.read_text()).get('status') not in ('complete','HOST_ERROR'):
  raise ValueError('unfinished result '+str(p))
def dump(p,x):
 temporary=p.with_name(p.name+'.tmp')
 with temporary.open('w') as stream:
  stream.write(json.dumps(x,separators=(',',':'))+'\n');stream.flush();os.fsync(stream.fileno())
 os.replace(temporary,p)
verified=[];metadata=[]
for p in sorted(root.glob('R*/**/SHA256.json')):
 x=json.loads(p.read_text())
 # Per-run manifests contain a flat mapping. Managed files use another schema.
 if not isinstance(x,dict) or any(not isinstance(v,str) or len(v)!=64 for v in x.values()):continue
 for name,value in x.items():
  q=p.parent/name
  if not q.is_file() or sha(q)!=value:raise ValueError('original manifest mismatch: '+str(q))
 verified.append(str(p.relative_to(root)))
for p in sorted(root.glob('R*/**/RUN_META.json')):
 x=json.loads(p.read_text())
 if x.get('batch')!='warpfit':raise ValueError('foreign metadata '+str(p))
 r=json.loads((p.parent/'result.json').read_text()) if (p.parent/'result.json').exists() else {}
 selected=('/primitive-v1/' in r.get('fixture','') and r.get('round') in (2,3)) or (r.get('engine')=='cpu' and r.get('completed'))
 if x.get('pr') is None or (selected and x.get('class')!='milestone'):
  old=p.with_name('RUN_META.before-pr-association.json');old.write_bytes(p.read_bytes())
  before=sha(p);x.update(pr=562,note='draft PR associated after finite benchmark; original metadata preserved')
  if selected:x['class']='milestone'
  dump(p,x);metadata.append(dict(path=str(p.relative_to(root)),before_sha256=before,after_sha256=sha(p)))
compressed=[]
receipt=dict(created_utc=datetime.datetime.now(datetime.timezone.utc).isoformat(),
 original_run_manifests_verified=verified,metadata_association=metadata,compressed=compressed,
 old_manifests='original SHA256.json retains pre-association logical bytes; preserved RUN_META.before-pr-association.json resolves original hash; final file hashes below')
dump(root/'archive-receipt.json',receipt)
for p in sorted(root.rglob('*')):
 if p.is_symlink():raise ValueError('symlink in own archive root '+str(p))
 if p.suffix not in ('.json','.jsonl') or p.stat().st_size<=65536:continue
 if p.name=='archive-receipt.json':continue
 before=sha(p);n=p.stat().st_size;out=p.with_name(p.name+'.zst')
 if out.exists():raise ValueError('archive exists '+str(out))
 subprocess.run(['zstd','-q','-3','-T1',str(p),'-o',str(out)],check=True)
 restored=subprocess.check_output(['zstd','-q','-dc',str(out)])
 if hashlib.sha256(restored).hexdigest()!=before:raise ValueError('restore mismatch '+str(out))
 compressed.append(dict(path=str(p.relative_to(root)),bytes=n,sha256=before,archive=str(out.relative_to(root)),archive_bytes=out.stat().st_size,archive_sha256=sha(out),restored_sha256_verified=True))
 # Durable mapping and restored-content check BEFORE removing an original.
 dump(root/'archive-receipt.json',receipt)
 if sha(p)!=before:raise ValueError('source changed before removal '+str(p))
 p.unlink()
if (root/'archive-receipt.json').stat().st_size>65536:
 p=root/'archive-receipt.json';data=p.read_bytes();out=root/'archive-receipt-full.json.zst'
 out.write_bytes(subprocess.check_output(['zstd','-q','-3','-c'],input=data))
 assert subprocess.check_output(['zstd','-q','-dc',str(out)])==data
 dump(p,dict(details_file=out.name,details_sha256=sha(out),restored_sha256=hashlib.sha256(data).hexdigest(),
             original_run_manifests_verified=len(verified),associated=len(metadata),compressed=len(compressed)))
# The inventory itself can be >64KiB; keep this map compressed by construction.
files={str(p.relative_to(root)):dict(bytes=p.stat().st_size,sha256=sha(p)) for p in sorted(root.rglob('*')) if p.is_file() and p.name not in ['final-inventory.json.zst']}
payload=(json.dumps(files,sort_keys=True)+'\n').encode()
proc=subprocess.run(['zstd','-q','-3','-c'],input=payload,stdout=subprocess.PIPE,check=True)
p=root/'final-inventory.json.zst';p.write_bytes(proc.stdout)
assert subprocess.check_output(['zstd','-q','-dc',str(p)])==payload
print(json.dumps(dict(files=len(files),bytes=sum(r['bytes'] for r in files.values()),inventory_sha256=sha(p),verified_original_manifests=len(verified),associated=len(metadata),compressed=len(compressed))))
