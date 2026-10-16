"""Finite Mac-side 4h guard for this explicitly authorized L4 allocation."""
import datetime
import json
from pathlib import Path
import subprocess
import time

ROOT = Path(__file__).resolve().parent
GCLOUD = ['gcloud', 'compute', 'instances']
FLAGS = ['ugrp-act-l4-gcp2', '--zone', 'asia-northeast3-a',
         '--account', 'changmin5781@gmail.com', '--project', 'ugrp-sim-b-1014']
deadline = datetime.datetime.fromisoformat('2026-10-15T18:02:37.522+00:00').timestamp()+14400
(ROOT/'guard.pid').write_text(str(__import__('os').getpid()))
while time.time() < deadline:
    if (ROOT/'guard-finished').exists():
        break
    time.sleep(min(30, max(0, deadline-time.time())))
else:
    # The allocation is ours, but another lease always blocks a VM stop.
    check = subprocess.run(['ssh', '-i', '/Users/changmin/.ssh/ugrp_gcp2',
        '-o', 'IdentitiesOnly=yes', '-o', 'ConnectTimeout=10', 'ugrp@34.64.179.69',
        'python3 /home/ugrp/ugrp-sim/runs/warp1/simalt_lease_audit.py warp1'],
        capture_output=True, text=True)
    audit = json.loads(check.stdout) if check.returncode == 0 else {}
    if not audit.get('may_stop_after_own_work_exits', False):
        (ROOT/'resource-cap-stop.json').write_text(json.dumps({
            'cap_end': True, 'stop_blocked_by_other_lease_or_ssh_error': True,
            'stdout': check.stdout, 'stderr': check.stderr}, indent=2)+'\n')
        raise SystemExit('L4 stop requires lease/process ownership check')
    result = subprocess.run(GCLOUD+['stop']+FLAGS, capture_output=True, text=True)
    (ROOT/'resource-cap-stop.json').write_text(json.dumps({
        'cap_end': True, 'returncode': result.returncode,
        'stdout': result.stdout, 'stderr': result.stderr}, indent=2)+'\n')
