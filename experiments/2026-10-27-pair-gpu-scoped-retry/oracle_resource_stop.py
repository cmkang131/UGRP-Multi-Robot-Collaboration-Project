"""Oracle timer for the predeclared C host-resource prefix; no treatment edits."""
import argparse
from datetime import datetime
import json
from pathlib import Path
import subprocess
import time


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('--root', type=Path, required=True)
    p.add_argument('--deadline-utc', required=True)
    a = p.parse_args()
    deadline = datetime.fromisoformat(a.deadline_utc).timestamp()
    while time.time() < deadline:
        time.sleep(min(15., max(0., deadline-time.time())))
    command = [str(Path.home()/'bin/gcloud-p'), 'ugrp-sim-f-1016', 'compute', 'ssh',
        'ugrp@ugrp-act-l4-gcp6', '--zone=asia-northeast1-c', '--tunnel-through-iap',
        '--command=python3 -B /home/ugrp/ugrp-sim/runs/pair-gpu-scoped-20261027/ops/stop_owned_arm.py --arm arm_c --execute']
    result = subprocess.run(command, capture_output=True, text=True)
    with (a.root/'results/C-resource-stop-receipt.json').open('x') as stream:
        json.dump(dict(command=command, requested_deadline_utc=a.deadline_utc,
            exit_code=result.returncode, stdout=result.stdout, stderr=result.stderr), stream, indent=2)
    print(result.stdout, flush=True)
    if result.returncode:
        raise RuntimeError('owned C resource stop failed: '+result.stderr)


if __name__ == '__main__':
    main()
