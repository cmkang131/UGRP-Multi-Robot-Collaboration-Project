"""Finite gcp2-only result closure; no GUI, evaluation overview is posthoc."""
import argparse,datetime,json,platform,subprocess,time
from pathlib import Path
if platform.system()!='Linux':raise RuntimeError('gcp2 only')
p=argparse.ArgumentParser();p.add_argument('--out',type=Path,required=True);a=p.parse_args();a.out.mkdir(exist_ok=False)
root=Path('/home/ugrp/ugrp-sim/runs/warp1')
deadline=datetime.datetime.fromisoformat('2026-10-15T21:57:00+00:00').timestamp()
pending=['policy-qual-n1-seed4','policy-qual-n1-seed0','policy-qual-n16-seed0'];rows=[]
while pending and time.time()<deadline:
 for name in pending[:]:
  run=root/name;summary=json.loads((run/'summary.json').read_text())
  if summary['status']=='running' or not (run/'world0-states.npz').exists():continue
  cmd=['/home/ugrp/ugrp-sim/runs/simalt3/warp-env/bin/python','/home/ugrp/ugrp-sim/warp1-records/make_playback.py','--run',str(run),'--out',str(root/('playback-'+name))]
  result=subprocess.run(cmd,stdout=subprocess.PIPE,stderr=subprocess.STDOUT,text=True)
  rows.append(dict(run=name,command=cmd,exit_code=result.returncode,output=result.stdout[-4000:]));pending.remove(name)
  (a.out/'closure.json').write_text(json.dumps(dict(rows=rows,pending=pending),indent=2)+'\n')
 if pending:time.sleep(15)
(a.out/'closure.json').write_text(json.dumps(dict(rows=rows,pending=pending,deadline_utc='2026-10-15T21:57:00+00:00'),indent=2)+'\n')
