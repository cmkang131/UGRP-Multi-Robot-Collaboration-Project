import hashlib,json,sys,tarfile
from pathlib import Path
root=Path('/home/ugrp/ugrp-sim/runs/warp8');files=[]
for receipt in sorted(root.glob('*.receipt.json')):
 name=receipt.name.removesuffix('.receipt.json')
 for path in sorted(root.rglob('*')):
  if not path.is_file():continue
  rel=path.relative_to(root)
  belongs=rel.parts[0]==name or (len(rel.parts)==1 and path.name.startswith(name+'.'))
  if belongs and (path.name.endswith(('.json','.jsonl','.json.zst','.jsonl.zst'))):files.append(path)
assert files and len(files)==len(set(files))
manifest=root/'beam40-r1.transfer-source.json'
manifest.write_text(json.dumps({str(p.relative_to(root)):dict(bytes=p.stat().st_size,sha256=hashlib.sha256(p.read_bytes()).hexdigest()) for p in files},indent=2)+'\n')
with tarfile.open(fileobj=sys.stdout.buffer,mode='w|gz') as tar:
 for path in [*files,manifest]:tar.add(path,arcname=str(path.relative_to(root)),recursive=False)
