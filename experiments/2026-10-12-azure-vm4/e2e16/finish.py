from pathlib import Path
import sys,subprocess,time,json,fcntl,os
name=sys.argv[1];base=Path.home()/'ugrp-sim';run=base/'runs'/name
assert name in [f'e2e-usstall-{g}-s{s}' for s in range(61001,61004) for g in ('a','b')] and (run/'EXIT').exists()
subprocess.run(['python3',str(base/'e2e-usstall-export-lite.py'),str(run)],check=True)
for attempt in range(6):
 p=subprocess.run(['python3','/usr/local/lib/ugrp-storage/scripts/compress_json_traces.py',str(run),'--execute'],capture_output=True,text=True)
 if p.returncode==0:break
 time.sleep(10)
else:raise SystemExit('COMPRESSION_NOT_FINISHED: '+p.stderr)
(base/(name+'-compression.json')).write_text(p.stdout)
with (base/'.e2e-usstall-archive.lock').open('a') as lock:
 fcntl.flock(lock,fcntl.LOCK_EX)
 for attempt in range(24):
  (base/'leases'/name).touch()
  p=subprocess.run(['python3','/usr/local/lib/ugrp-storage/scripts/azure_shutdown.py','archive-one','--run',name],capture_output=True,text=True)
  if p.returncode==0:break
  time.sleep(10)
 else:raise SystemExit('ARCHIVE_NOT_FINISHED: '+p.stderr)
proof=json.loads((base/'lifecycle/archives'/(name+'.json')).read_text());assert proof['verified']
(base/'e2e-usstall-finished').mkdir(exist_ok=True)
(base/'e2e-usstall-finished'/(name+'.json')).write_text(json.dumps({'name':name,'proof':proof,'finished_unix':time.time()},indent=2)+'\n')
(base/'leases'/name).unlink(missing_ok=True)
print(json.dumps({'name':name,'verified':True,'path':proof.get('native_arm_path',proof.get('path'))}))
