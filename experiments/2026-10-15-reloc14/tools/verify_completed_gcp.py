from pathlib import Path
import subprocess,json,hashlib,time
R=Path('/home/ugrp/ugrp-sim');records=[]
for p in sorted(R.glob('runs/reloc14-*')):
 if not (p/'EXIT').exists() or not (p/'SHA256SUMS').exists():continue
 check=subprocess.run(['sha256sum','-c','--quiet','SHA256SUMS'],cwd=p,capture_output=True,text=True)
 row=dict(run=p.name,exit=(p/'EXIT').read_text().strip(),manifest_sha256=hashlib.sha256((p/'SHA256SUMS').read_bytes()).hexdigest(),file_N=len((p/'SHA256SUMS').read_text().splitlines()),verified=check.returncode==0,error=check.stderr[:1500])
 if row['verified']:
  reservation=R/'admission-reservations'/(p.name+'.json');lease=R/'leases'/p.name
  if reservation.exists():
   j=json.loads(reservation.read_text());assert j.get('owner')=='reloc14';j.update(status='released',released_at_unix=time.time(),reason='EXIT and entire GCP original manifest verified');reservation.write_text(json.dumps(j,indent=2)+'\n')
  lease.unlink(missing_ok=True);row['lease_released']=True
 records.append(row)
Path('/tmp/reloc14-integrity.json').write_text(json.dumps(records,indent=2)+'\n');print(json.dumps(records))
