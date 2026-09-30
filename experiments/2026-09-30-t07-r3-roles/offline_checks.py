"""Run only offline tests under the shared host lock; preserve every attempt."""
import json
import hashlib
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import time

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))
from scripts.run_ci_tests import local_lock_root, run_locked
from scripts import agent_lock

DEFAULT = [
    'tests/test_zone_pair_role_exchange.py',
    'tests/test_zone_pair_executor.py', 'tests/test_zone_pair_status.py',
    'tests/test_zone_pair_review.py', 'tests/test_zone_pair_review2.py',
    'tests/test_zone_pair_review3.py', 'tests/test_zone_pair_review4.py',
    'tests/test_zone_pair_review5.py', 'tests/test_zone_pair_review6.py',
    'tests/test_zone_pair_review7.py',
    'tests/test_zone_pair_v6e.py', 'tests/test_zone_pair_v6e_yaw.py',
    'tests/test_zone_study_integration.py', 'tests/test_zone_study_integration_pair.py',
]

if __name__ == '__main__':
    os.chdir(ROOT)
    raw = Path('/Users/changmin/projects/ugrp/outputs/t07-r3-roles')
    raw.mkdir(parents=True, exist_ok=True)
    out = Path(tempfile.mkdtemp(prefix='offline-', dir=raw))
    env = dict(os.environ, OMP_NUM_THREADS='1', OPENBLAS_NUM_THREADS='1', VECLIB_MAXIMUM_THREADS='1',
               PYTHONPATH=str(ROOT) + os.pathsep + str(Path(__file__).parent))
    command = [sys.executable, '-m', 'pytest', '-q', '-p', 'offline_guard',
               *(sys.argv[1:] or DEFAULT), f'--junitxml={out / "junit.xml"}',
               f'--basetemp={out / "tmp"}']
    (out / 'command.json').write_text(json.dumps(command, indent=2) + '\n')
    sources = set(subprocess.check_output(['git', 'diff', '--name-only'], text=True).splitlines())
    sources.update(subprocess.check_output(['git', 'ls-files', '--others', '--exclude-standard'], text=True).splitlines())
    hashes = {name: hashlib.sha256((ROOT / name).read_bytes()).hexdigest()
              for name in sorted(sources) if (ROOT / name).is_file()}
    (out / 'source_sha256.json').write_text(json.dumps(hashes, indent=2) + '\n')
    print(out, flush=True)
    lock_root = local_lock_root()
    waits, deadline = [], time.monotonic() + 60
    while lock_root and agent_lock.status(lock_root) and time.monotonic() < deadline:
        if not waits:
            print('Waiting up to 60 seconds for the shared lock; no tests started.', flush=True)
        waits.append({'at': time.time(), 'lock': agent_lock.status(lock_root)})
        time.sleep(1)
    (out / 'lock_waits.json').write_text(json.dumps(waits, indent=2) + '\n')
    code = run_locked(command, env, lock_root)
    (out / 'result.json').write_text(json.dumps({'exit_code': code, 'python': sys.version,
                                               'head': subprocess.check_output(['git', 'rev-parse', 'HEAD'], text=True).strip()},
                                              indent=2) + '\n')
    raise SystemExit(code)
