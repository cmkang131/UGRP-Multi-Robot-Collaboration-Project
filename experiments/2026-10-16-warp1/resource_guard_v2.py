"""One finite4h allocation guard; stop ONLY warp1 outputs, preserve other tasks."""
import datetime as dt
import json
import os
from pathlib import Path
import signal
import subprocess
import time

ROOT=Path(__file__).resolve().parent
REMOTE='/home/ugrp/ugrp-sim/runs/warp1'
SSH=['ssh','-i','/Users/changmin/.ssh/ugrp_gcp2','-o','IdentitiesOnly=yes',
     '-o','ConnectTimeout=10','ugrp@34.64.179.69']
START=dt.datetime.fromisoformat('2026-10-15T18:02:37.522+00:00').timestamp()
DEADLINE=START+4*3600  # explicit user limit
# simalt observed stop55.517s + SIGINT grace30s + two SSH10s =105.517s,
# rounded up to120s for the administrative shutdown window, not a task gate.
HEADROOM=120


def owned_output(args):
    """Source/adapter paths never establish ownership. Match actual output only."""
    if '--out' in args:
        index=args.index('--out')+1
        if index<len(args):
            value=Path(args[index]).resolve()
            if value==Path(REMOTE).resolve() or value.is_relative_to(Path(REMOTE).resolve()):return str(value)
    if args and Path(args[0]).name.startswith('ffmpeg') and len(args)>1:
        value=Path(args[-1]).resolve()
        if value.is_relative_to(Path(REMOTE).resolve()):return str(value.parent)
    return None


def remote_stop(force=False):
    # Send standard-library source on stdin. No credentials/code agent goes to VM.
    source=Path(__file__).read_text()
    helper=source[source.index('def owned_output'):source.index('\ndef remote_stop')]
    program='from pathlib import Path\nimport os,signal,json,time\nREMOTE='+repr(REMOTE)+'\nFORCE='+repr(force)+'\n'+helper+'''
rows=[]
for path in Path('/proc').iterdir():
 if not path.name.isdigit() or int(path.name)==os.getpid():continue
 try:
  if path.stat().st_uid!=os.getuid():continue
  args=[x.decode() for x in (path/'cmdline').read_bytes().split(b'\\0') if x]
  if not args:continue
  executable=Path(args[0]).name
  if not executable.startswith(('python','mujoco','ffmpeg','timeout')):continue
  out=owned_output(args)
  if out is None:continue
  rows.append(dict(pid=int(path.name),executable=executable,out=out))
 except (FileNotFoundError,PermissionError,ProcessLookupError):continue
for row in rows:
 try:
  if row['executable']=='timeout':
   os.kill(row['pid'],signal.SIGKILL) # only redundant owned watchdog containers
  else:
   folder=Path(row['out']);folder.mkdir(parents=True,exist_ok=True)
   (folder/'SUPERVISOR_STOP.json').write_text(json.dumps(dict(reason='resource_cap4h',category='cap_end'))+'\\n')
   os.kill(row['pid'],signal.SIGKILL if FORCE else signal.SIGINT)
   if not FORCE:os.kill(row['pid'],signal.SIGCONT)
 except ProcessLookupError:pass
print(json.dumps(dict(stage='own_stop_requested',rows=rows)))
'''
    return subprocess.run(SSH+['python3 -'],input=program,capture_output=True,text=True,timeout=30)


def main():
    (ROOT/'guard-v2.pid').write_text(str(os.getpid()))
    while time.time()<DEADLINE-HEADROOM:
        if (ROOT/'guard-v2-finished').exists():return
        time.sleep(min(15,max(0,DEADLINE-HEADROOM-time.time())))
    stopped=remote_stop()
    (ROOT/'resource-cap-own-stop.json').write_text(json.dumps(dict(returncode=stopped.returncode,
        stdout=stopped.stdout,stderr=stopped.stderr,cap_end=True),indent=2)+'\n')
    # Give the driver a bounded flush window, then audit ownership again.
    time.sleep(30)
    forced=remote_stop(force=True)
    (ROOT/'resource-cap-force-stop.json').write_text(json.dumps(dict(returncode=forced.returncode,
        stdout=forced.stdout,stderr=forced.stderr,cap_end=True),indent=2)+'\n')
    audit=subprocess.run(SSH+['python3 /home/ugrp/ugrp-sim/runs/warp1/simalt_lease_audit.py warp1'],
        capture_output=True,text=True,timeout=30)
    row=json.loads(audit.stdout) if audit.returncode==0 else {}
    result=dict(cap_end=True,audit=row,stop_blocked_by_other_task=True)
    if row.get('may_stop_after_own_work_exits') and not row.get('processes'):
        cmd=['gcloud','compute','instances','stop','ugrp-act-l4-gcp2','--zone','asia-northeast3-a',
             '--account','changmin5781@gmail.com','--project','ugrp-sim-b-1014']
        stop=subprocess.run(cmd,capture_output=True,text=True,timeout=max(1,DEADLINE-time.time()))
        result.update(stop_blocked_by_other_task=False,returncode=stop.returncode,stdout=stop.stdout,stderr=stop.stderr)
    (ROOT/'resource-cap-stop.json').write_text(json.dumps(result,indent=2)+'\n')


if __name__=='__main__':main()
