"""Final stable raw audit after all physics/review/collector writers have exited."""
import hashlib
import json
from pathlib import Path
import subprocess
import sys

ROOT=Path('/home/ugrp/ugrp-sim/runs/simalt4')
OUT=ROOT/'final-evidence'
sys.path.insert(0,str(ROOT/'scripts'))
from simalt_host import gcp2_identity
gcp2_identity()

def sha(p):return hashlib.sha256(p.read_bytes()).hexdigest()

for pidfile in ROOT.glob('*.pid'):
    pid=pidfile.read_text().strip()
    state=subprocess.run(['ps','-p',pid,'-o','stat='],capture_output=True,text=True).stdout.strip()
    if state and not state.startswith('Z'):
        raise RuntimeError('owned writer still active: '+str(pidfile)+' '+state)

files=[x for x in ROOT.rglob('*') if x.is_file() and not x.is_relative_to(OUT)
       and not x.is_relative_to(ROOT/'mujoco313') and '__pycache__' not in x.parts]
rows=[{'path':str(f),'bytes':f.stat().st_size,'sha256':sha(f)} for f in sorted(files)]
failures=[r['path'] for r in rows if sha(Path(r['path']))!=r['sha256']]
if failures:raise RuntimeError('raw changed during final audit: '+repr(failures))
manifest=OUT/'raw-manifest-final.json'
manifest.write_text(json.dumps(rows,indent=2)+'\n')
original=sha(manifest)
subprocess.run(['zstd','-q',str(manifest)],check=True)
stored=Path(str(manifest)+'.zst')
if hashlib.sha256(subprocess.check_output(['zstd','-dc',str(stored)])).hexdigest()!=original:
    raise RuntimeError('manifest restore mismatch')
manifest.unlink()
(OUT/'SHA256SUMS-final').write_text(''.join(r['sha256']+'  '+r['path']+'\n' for r in rows))
prior={}
for line in (OUT/'SHA256SUMS').read_text().splitlines():
    value,path=line.split('  ',1);prior[path]=value
changed=[r['path'] for r in rows if r['path'] in prior and r['sha256']!=prior[r['path']]]
result={'files':len(rows),'passed':len(rows),'failed':failures,'canonical':True,
        'writers_active':0,'supersedes':'collector pre-completion-log snapshot raw-verification.json',
        'changed_since_collector_snapshot':changed,
        'manifest':{'stored':str(stored),'uncompressed_sha256':original,
                    'stored_sha256':sha(stored),'restored_hash_verified':True}}
(OUT/'raw-verification-final.json').write_text(json.dumps(result,indent=2)+'\n')
print(json.dumps(result))
