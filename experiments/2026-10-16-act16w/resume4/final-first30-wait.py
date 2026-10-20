"""Finite first30 diagnostic composition; no physics or model calls."""
from pathlib import Path
from datetime import datetime, timezone
import json
import os
import subprocess
import time

B = Path('/home/ugrp/ugrp-sim')
R = B / 'runs/act16w-native-experiment-r1'
S = B / 'src/34d53cfaadc093ac957bbfffc780a76f372041f9'
lease = B / 'leases/act16w-final-first30-wait.json'
with lease.open('x') as stream:
    json.dump(dict(task='act16w-final-first30-wait', pid=os.getpid(), concurrency=0,
                   start_utc=datetime.now(timezone.utc).isoformat(),
                   expected_end='existing first30 frames or controller completion; no wall cap'), stream)
try:
    while True:
        ready = []
        for world in sorted((R / 'final40').glob('group-*/evaluation/owner/world-*')):
            plan = world / 'plan.json'
            if plan.exists() and (world / 'review-own/000300.jpg').exists():
                ready.append((json.loads(plan.read_text())['seed'], world))
        if ready:
            seed, world = min(ready)
            out = R / f'final-first30-{seed}'
            subprocess.run([str(B / 'runs/simalt3/warp-env/bin/python'),
                str(S / 'scripts/act16w_own_first30.py'), '--world-root', str(world),
                '--out', str(out), '--label', f'final_A_{seed}'],
                cwd=B / 'src/f0db6b1abb842ea65b71c433738210254f300a7c',
                env={**os.environ, 'LP_NUM_THREADS': '1', 'OPENBLAS_NUM_THREADS': '1'}, check=True)
            (R / 'final-first30-selection.json').write_text(json.dumps(dict(seed=seed, out=str(out),
                rule='lowest seed with actual complete61 first30 frames at inspection; diagnostic only, no selection/tuning')) + '\n')
            break
        if json.loads((R / 'summary.json').read_text())['status'] not in ('FINAL40', 'FINAL40_REFERENCE_SETUP'):
            break
        time.sleep(10)
finally:
    if lease.exists() and json.loads(lease.read_text())['pid'] == os.getpid():
        lease.unlink()
