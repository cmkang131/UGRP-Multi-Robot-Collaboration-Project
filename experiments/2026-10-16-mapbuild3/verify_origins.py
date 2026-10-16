"""gcp2: prepare/compare read-only origin file hashes for the used audit inputs."""
import argparse,hashlib,json,subprocess
from pathlib import Path
p=argparse.ArgumentParser();p.add_argument('phase',choices=['prepare','verify']);p.add_argument('--base',type=Path,required=True);a=p.parse_args();ops=a.base/'ops-reviews/mapbuild3';root=a.base/'runs/mapbuild3/audit-r3'
path=root/'input-sha256.json';expected=json.loads(path.read_text() if path.exists() else subprocess.check_output(['zstd','-q','-dc',str(path)+'.zst']))
groups={'act':{},'warp':{}}
for path,h in expected.items():
 for group,prefix,target in [('act',str(ops/'audit-input-act')+'/',str(a.base/'runs')+'/'),('warp',str(ops/'audit-input-warp')+'/',str(a.base/'runs/warp8')+'/')]:
  if path.startswith(prefix):groups[group][target+path[len(prefix):]]=h
if a.phase=='prepare':
 for group,values in groups.items():(ops/('hash-inputs-'+group+'.txt')).write_text(''.join(k+'\n' for k in sorted(values)))
else:
 report={}
 for group,values in groups.items():
  actual={}
  for line in (ops/('origin-hashes-'+group+'.txt')).read_text().splitlines():
   h,path=line.split(None,1);actual[path.lstrip('*')]=h
  bad=[k for k,v in values.items() if actual.get(k)!=v];assert not bad,bad
  report[group]=dict(files=len(values),mismatches=bad,source_prefix='gcp2 L4 /runs' if group=='act' else 'gcp3 /runs/warp8',raw_origin_hash_receipt=str(ops/('origin-hashes-'+group+'.txt')))
 (a.base/'runs/mapbuild3/origin-hash-verification.json').write_text(json.dumps(report,indent=2)+'\n');print(json.dumps(report))
