"""One-shot finite cancellation of this task's pending R2 jobs after N1 saves."""
from pathlib import Path
import json
import os
import signal
import time

r=Path('/home/ugrp/ugrp-sim/runs/warp2/r2-54563a38')
lease=Path('/home/ugrp/ugrp-sim/leases/warp2.json')
info=json.loads(lease.read_text());pid=info['pid']
assert info['round']=='r2-54563a38'
assert b'warp2-run-round-r2.py' in Path(f'/proc/{pid}/cmdline').read_bytes()
deadline=json.loads((r.parent/'allocation.json').read_text())['started_unix']+10800
while time.time()<deadline:
    p=r/'n1/summary.json'
    if p.exists():
        result=json.loads(p.read_text())
        if result['status']!='running':
            (r/'CANCEL_PENDING_AFTER_N1.json').write_text(json.dumps(dict(
                reason_category='pending_jobs_replaced_by_shared_heterogeneous_backend_round3',
                n1_status=result['status'],n1_counts=result['counts'],physical_failure_claim=False,
                blocked_object='none:scheduling_replacement',min_gap_m=None,
                gap_scope='software scheduling, no geometric cause'),indent=2)+'\n')
            if Path(f'/proc/{pid}/cmdline').exists():os.kill(pid,signal.SIGINT)
            break
    if not Path(f'/proc/{pid}/cmdline').exists():break
    time.sleep(.25)
