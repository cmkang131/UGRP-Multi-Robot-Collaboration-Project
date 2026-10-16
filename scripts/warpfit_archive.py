"""Own warpfit outputs only: verify old manifests, associate draft PR, compress losslessly."""
from pathlib import Path
import json,hashlib,subprocess,sys,datetime
root=Path(sys.argv[1]).resolve()
if str(root) not in ['/home/ugrp/ugrp-sim/runs/warpfit','/home/ugrp/ugrp-sim/ops-reviews/warpfit/raw']:
 raise ValueError('only own raw root')
def sha(p):return hashlib.sha256(p.read_bytes()).hexdigest()
def dump(p,x):p.write_text(json.dumps(x,indent=2)+'\n')
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
for p in sorted(root.rglob('*')):
 if p.suffix not in ('.json','.jsonl') or p.stat().st_size<=65536:continue
 before=sha(p);n=p.stat().st_size;out=p.with_name(p.name+'.zst')
 if out.exists():raise ValueError('archive exists '+str(out))
 subprocess.run(['zstd','-q','-3',str(p),'-o',str(out)],check=True)
 restored=subprocess.check_output(['zstd','-q','-dc',str(out)])
 if hashlib.sha256(restored).hexdigest()!=before:raise ValueError('restore mismatch '+str(out))
 compressed.append(dict(path=str(p.relative_to(root)),bytes=n,sha256=before,archive=str(out.relative_to(root)),archive_bytes=out.stat().st_size,archive_sha256=sha(out),restored_sha256_verified=True))
 p.unlink()
dump(root/'archive-receipt.json',dict(created_utc=datetime.datetime.now(datetime.timezone.utc).isoformat(),original_run_manifests_verified=verified,metadata_association=metadata,compressed=compressed,old_manifests='original SHA256.json retains pre-association logical bytes; preserved RUN_META.before-pr-association.json resolves original hash; final file hashes below'))
# The inventory itself can be >64KiB; keep this map compressed by construction.
files={str(p.relative_to(root)):dict(bytes=p.stat().st_size,sha256=sha(p)) for p in sorted(root.rglob('*')) if p.is_file() and p.name not in ['final-inventory.json.zst']}
payload=(json.dumps(files,sort_keys=True)+'\n').encode()
proc=subprocess.run(['zstd','-q','-3','-c'],input=payload,stdout=subprocess.PIPE,check=True)
p=root/'final-inventory.json.zst';p.write_bytes(proc.stdout)
assert subprocess.check_output(['zstd','-q','-dc',str(p)])==payload
print(json.dumps(dict(files=len(files),bytes=sum(r['bytes'] for r in files.values()),inventory_sha256=sha(p),verified_original_manifests=len(verified),associated=len(metadata),compressed=len(compressed))))
