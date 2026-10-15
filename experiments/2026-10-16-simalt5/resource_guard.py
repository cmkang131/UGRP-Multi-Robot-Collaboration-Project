"""Finite Mac-side 3h guard for this explicitly authorized L4 allocation."""
import datetime
import json
from pathlib import Path
import subprocess
import time

ROOT = Path(__file__).resolve().parent
GCLOUD = ['gcloud', 'compute', 'instances']
FLAGS = ['ugrp-act-l4-gcp2', '--zone', 'asia-northeast3-a',
         '--account', 'changmin5781@gmail.com', '--project', 'ugrp-sim-b-1014']
deadline = datetime.datetime.fromisoformat('2026-10-15T16:45:52.759+00:00').timestamp()+10800
(ROOT/'guard.pid').write_text(str(__import__('os').getpid()))
while time.time() < deadline:
    if (ROOT/'guard-finished').exists():
        break
    time.sleep(min(30, max(0, deadline-time.time())))
else:
    # The allocation is ours, but another lease always blocks a VM stop.
    check = subprocess.run(['ssh', '-i', '/Users/changmin/.ssh/ugrp_gcp2',
        '-o', 'IdentitiesOnly=yes', '-o', 'ConnectTimeout=10', 'ugrp@34.64.179.69',
        'find /home/ugrp/ugrp-sim/leases -maxdepth 1 -type f ! -name simalt5.json -print'],
        capture_output=True, text=True)
    if check.returncode or check.stdout.strip():
        (ROOT/'evidence/resource-cap-stop.json').write_text(json.dumps({
            'cap_end': True, 'stop_blocked_by_other_lease_or_ssh_error': True,
            'stdout': check.stdout, 'stderr': check.stderr}, indent=2)+'\n')
        raise SystemExit('L4 stop requires lease/process ownership check')
    result = subprocess.run(GCLOUD+['stop']+FLAGS, capture_output=True, text=True)
    (ROOT/'evidence/resource-cap-stop.json').write_text(json.dumps({
        'cap_end': True, 'returncode': result.returncode,
        'stdout': result.stdout, 'stderr': result.stderr}, indent=2)+'\n')
