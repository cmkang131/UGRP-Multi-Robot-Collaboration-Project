"""gcp2 final metadata: retain v1, add exact acquisition commands and all41 video."""
import json,hashlib,shutil,sys
from pathlib import Path
b=Path(sys.argv[1]);out=b/'delivery-final-v2';shutil.copytree(b/'delivery-final',out)
read=lambda p:json.loads(p.read_text())
write=lambda p,x:p.write_text(json.dumps(x,indent=2)+'\n')
home=Path('/home/ugrp/ugrp-sim');py=home/'ugrp/.venv-warp/bin/python';renderer=home/'src/drivecheck-renderer-5974a181';ops=home/'ops-reviews/mapbuild3'
physical=dict(prepare=[str(py),str(home/'src/mapbuild3-76da1162/scripts/mapbuild3_prepare.py'),'--spawn-overlap-check-v1','--renderer-source',str(renderer),'--output',str(b/'NEW-prepare')],
 capture=[str(py),str(home/'src/mapbuild3-eb3ae01d/scripts/mapbuild3_capture.py'),'--mapbuild3-v1','--queue',str(ops/'queue-r1c.json'),'--fixture',str(b/'prepare-r1b'),'--renderer-source',str(renderer),'--renderer-receipt',str(ops/'renderer-receipt.json'),'--output',str(b/'NEW-capture')],
 environment=dict(MUJOCO_GL='osmesa',OMP_NUM_THREADS='1',OPENBLAS_NUM_THREADS='1'),host='gcp5',scope='new output paths required; original source snapshots and queue preserved; no new physical execution')
f=read(out/'rejection_table.json');f['physical_reproduction']=physical;f['final_playback']=str(b/'analysis-r1/playback-r2/receipts.json');write(out/'rejection_table.json',f)
for filename in ('summary.json','next-queue.json'):
 x=read(out/filename);x['rejection_table']=str(out/'rejection_table.json');write(out/filename,x)
write(out/'physical-reproduction.json',physical)
shutil.copyfile(b/'analysis-r1/playback-r2/receipts.json',out/'playback-receipts.json')
write(out/'SHA256SUMS.json',{p.name:hashlib.sha256(p.read_bytes()).hexdigest() for p in out.iterdir() if p.is_file() and p.name!='SHA256SUMS.json'})
print(out)
