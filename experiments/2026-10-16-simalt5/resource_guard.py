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
    result = subprocess.run(GCLOUD+['stop']+FLAGS, capture_output=True, text=True)
    (ROOT/'evidence/resource-cap-stop.json').write_text(json.dumps({
        'cap_end': True, 'returncode': result.returncode,
        'stdout': result.stdout, 'stderr': result.stderr}, indent=2)+'\n')
