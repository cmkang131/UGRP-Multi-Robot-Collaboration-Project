"""Oracle-side GCE stop for the inherited cumulative GPU resource budget.

The deadline comes from the archived 20 GPU-h ledger plus observed VM start/
stop events. It is an estimated resource budget, never a policy/action limit.
No cloud credentials are copied to the execution VM.
"""
import argparse
from datetime import datetime
import json
from pathlib import Path
import subprocess
import time


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--root', type=Path, required=True)
    parser.add_argument('--stop-utc', required=True)
    args = parser.parse_args()
    deadline = datetime.fromisoformat(args.stop_utc).timestamp()
    # Exact user-authorized instance only; never use a gcp6 alias or default zone.
    base = [str(Path.home()/'bin/gcloud-p'), 'ugrp-sim-f-1016', 'compute', 'instances']
    instance = ['ugrp-act-l4-gcp6', '--zone=asia-northeast1-c', '--format=json']
    while time.time() < deadline:
        final = args.root/'VM_FINAL.json'
        if final.exists() and json.loads(final.read_text()).get('status') == 'TERMINATED':
            return
        time.sleep(min(15., max(0., deadline-time.time())))
    result = subprocess.run(base+['stop']+instance, capture_output=True, text=True)
    (args.root/'VM_BUDGET_STOP.json').write_text(json.dumps(dict(
        reason='HOST_RESOURCE_ESTIMATED_GLOBAL_GPU_BUDGET', stop_utc=args.stop_utc,
        exit_code=result.returncode, stdout=result.stdout, stderr=result.stderr), indent=2))
    final = subprocess.run(base+['describe']+instance, capture_output=True, text=True, check=True)
    (args.root/'VM_BUDGET_FINAL.json').write_text(final.stdout)
    if result.returncode or json.loads(final.stdout)['status'] != 'TERMINATED':
        raise RuntimeError('estimated cumulative GPU budget stop did not confirm TERMINATED')


if __name__ == '__main__':
    main()
