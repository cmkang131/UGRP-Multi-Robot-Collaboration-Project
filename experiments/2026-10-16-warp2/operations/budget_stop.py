"""Finite owner-only watchdog; reserve existing cleanup and measured replay time."""
import datetime,json,os,signal,time
from pathlib import Path
r=Path('/home/ugrp/ugrp-sim');lease=r/'leases/warp2.json';source='521f258508ccc7d24d667a158a2b26a1b3740ee9'
allocation=json.loads((r/'runs/warp2/allocation.json').read_text());deadline=allocation['started_unix']+10800
# Workflow allocation, not a scientific acceptance threshold: the existing
# coordinator allows 60+30s child cleanup. Reserve another 90s for the observed
# sub-minute state-replay/hash delivery, all inside the user's 3h L4 cap.
stop_at=deadline-180
while lease.exists():
 state=json.loads(lease.read_text())
 if state.get('source')!=source or state.get('round')!='r3-521f2585':break
 if time.time()>=stop_at:
  root=r/'runs/warp2/r3-521f2585';jobs=json.loads((root/'jobs.json').read_text());current=jobs[-1]
  if 'ended' in current:break
  marker=dict(reason_category='cap_end',cap_kind='user_L4_wall_budget_including_cleanup',
   blocked_object='none:resource_budget',min_gap_m=None,gap_scope='workflow resource cap, not geometry',
   deadline_utc=datetime.datetime.fromtimestamp(deadline,datetime.timezone.utc).isoformat(),
   stop_utc=datetime.datetime.now(datetime.timezone.utc).isoformat(),job=current['name'],
   coordinator_pid=state['pid'],physics_failure_claim=False,
   reserve_basis='existing coordinator child cleanup 60+30s, replay/hash delivery reserved90s',raw_HOST_ERROR_retained=True)
  (root/'SUPERVISOR_CAP_END.json').write_text(json.dumps(marker,indent=2)+'\n')
  (Path(current['out'])/'SUPERVISOR_CAP_END.json').write_text(json.dumps(marker,indent=2)+'\n')
  words=Path(f"/proc/{state['pid']}/cmdline").read_bytes().split(b'\0')
  expected=[str(r/'src'/('warp2-'+source[:8])/'experiments/2026-10-16-warp2/operations/run_round.py').encode(),source.encode(),b'r3-521f2585']
  assert words[1:4]==expected, 'refuse to signal: owner cmdline changed'
  os.kill(state['pid'],signal.SIGINT);print(json.dumps(marker));break
 time.sleep(5)
