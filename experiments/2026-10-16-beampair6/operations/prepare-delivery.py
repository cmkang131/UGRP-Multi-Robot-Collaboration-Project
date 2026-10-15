"""Copy small gcp2 summaries only; originals remain untouched."""
import pathlib,json,hashlib,shutil
r=pathlib.Path('/home/ugrp/ugrp-sim');ops=r/'ops-reviews/beampair6';out=ops/'delivery';out.mkdir(exist_ok=False)
names=['r1-summary.json','r1-rejection_table.json','r1-integrity.json','r1-first30.json','v2-validity-recheck.json','source-pin.json','environment.json','r1-DONE']
for n in names:shutil.copy2(ops/n,out/n)
shutil.copy2(r/'runs/beampair6-r1-08f12921/host-admission.json',out/'host-admission.json')
manifest=[]
for prefix,base in [('records',out),('playback',ops/'playback/beampair6-r1-8318726')]:
 for p in sorted(base.iterdir()):
  if p.is_file():manifest.append(dict(group=prefix,name=p.name,remote=str(p),bytes=p.stat().st_size,sha256=hashlib.sha256(p.read_bytes()).hexdigest()))
(ops/'retrieval-manifest.json').write_text(json.dumps(dict(files=manifest,N=len(manifest),scope='summary and representative playback only; not raw backup'),indent=2)+'\n')
print(json.dumps(dict(N=len(manifest),bytes=sum(x['bytes'] for x in manifest))))
