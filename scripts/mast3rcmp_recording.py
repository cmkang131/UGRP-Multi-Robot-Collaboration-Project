"""Resume-safe finite recording comparison; no wall budget or truth input.

Only mast3rcmp-owned paths are created. Existing output refuses a second run.
"""
import hashlib
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys
from datetime import datetime, timezone


def main():
    root = Path('/home/ugrp/ugrp-sim/mast3rcmp')
    lease = Path('/home/ugrp/ugrp-sim/leases/mast3rcmp2.json')
    if lease.exists() or (root/'runs/recording-r2/probe').exists():
        raise RuntimeError('existing_lease_or_run_requires_inspection_not_resubmission')
    lease.write_text(json.dumps(dict(task='mast3rcmp2',pid=os.getpid(),
        started=datetime.now(timezone.utc).isoformat(),expected_end='finite 401 frames; no wall cap'))+'\n')
    try:
        manifest = root/'main-input-manifest.json'
        prepared = root/'main-prepared'
        subprocess.run([sys.executable,str(root/'mast3rcmp_prepare.py'),
            '--manifest',str(manifest),'--manifest-sha256',hashlib.sha256(manifest.read_bytes()).hexdigest(),
            '--root',str(root/'main-source'),'--output',str(prepared)],check=True)
        shutil.copyfile(root/'practice-drive-off/config.yaml',prepared/'config.yaml')
        return subprocess.call([sys.executable,str(root/'mast3rcmp_launch.py'),
            '--repo',str(root/'MASt3R-SLAM'),'--entry',str(root/'MASt3R-SLAM/mast3rcmp_main.py'),
            '--prepared',str(prepared),'--output',str(root/'runs/recording-r2')])
    finally:
        lease.unlink()


if __name__ == '__main__':
    raise SystemExit(main())
