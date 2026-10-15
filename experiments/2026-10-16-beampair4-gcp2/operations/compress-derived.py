from pathlib import Path
import hashlib,subprocess,json
root=Path('/home/ugrp/ugrp-sim/ops-reviews/beampair4-gcp2')
def digest(p):
 h=hashlib.sha256()
 with p.open('rb') as f:
  for b in iter(lambda:f.read(1<<20),b''):h.update(b)
 return h.hexdigest()
rows=[]
for d in ('baseline-analysis','r3-analysis','r3-failure-timeline'):
 for p in (root/d).iterdir():
  if p.suffix not in ('.json','.jsonl','.csv') or p.stat().st_size<=65536:continue
  decoded=digest(p);size=p.stat().st_size;z=Path(str(p)+'.zst')
  if not z.exists():subprocess.run(['zstd','-q','--keep',str(p)],check=True)
  h=hashlib.sha256();proc=subprocess.Popen(['zstd','-qdc',str(z)],stdout=subprocess.PIPE)
  for b in iter(lambda:proc.stdout.read(1<<20),b''):h.update(b)
  assert proc.wait()==0 and h.hexdigest()==decoded
  rows.append(dict(original=str(p),decoded_sha256=decoded,original_bytes=size,path=str(z),sha256=digest(z),bytes=z.stat().st_size,roundtrip_verified=True))
  assert digest(p)==decoded;p.unlink()
(root/'derived-compression-manifest.json').write_text(json.dumps(rows,indent=2)+'\n')
print('Lossless derived compression verified',len(rows))
