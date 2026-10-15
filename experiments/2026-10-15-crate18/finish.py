"""Release only this verified round's reservations and leases."""
import json,subprocess,sys
from pathlib import Path
folder=Path(sys.argv[1]);rows=json.loads((folder/'plan.json').read_text());verification=json.loads((folder/'verification.json').read_text())
assert {r['run'] for r in verification}=={r['name'] for r in rows}
assert all(r['remote_manifest_verified'] and r['directly_viewed'] for r in verification)
code='''import fcntl,json,pathlib,time
b=pathlib.Path.home()/'ugrp-sim';names=NAMES;done=[]
with (b/'admission.lock').open('a') as lock:
 fcntl.flock(lock,fcntl.LOCK_EX)
 for name in names:
  assert (b/'runs'/name/'EXIT').exists()
  for p in pathlib.Path('/proc').glob('[0-9]*/cmdline'):
   try:a=p.read_bytes().decode(errors='replace')
   except OSError:continue
   if name in a and 'scripts.run_crate_teacher' in a:raise RuntimeError('still owned process '+p.parent.name)
  p=b/'admission-reservations'/(name+'.json');d=json.loads(p.read_text());assert d['owner'].startswith('crate18-')
  d.update(status='released',released_at_unix=time.time(),reason='full manifest + selected/decoded hashes + own RGB reviewed, no owned simulation PID');p.write_text(json.dumps(d)+'\\n')
  lease=b/'leases'/name
  if lease.exists():lease.unlink()
  done.append(name)
print(json.dumps({'released':done,'owned_live_processes':0}))
'''.replace('NAMES',repr([r['name'] for r in rows]))
r=subprocess.run(['ssh','-o','BatchMode=yes','gcp1','python3 -'],input=code,text=True,capture_output=True,check=True)
(folder/'lifecycle.json').write_text(r.stdout);print(r.stdout)
