"""Run the offline review6 suite from the repository root; no model/physics."""
from pathlib import Path
import hashlib
import json
import shutil
import socket
import subprocess
import sys

ROOT = Path.cwd()
sys.path.insert(0, str(ROOT))
sys.modules['mujoco'] = None

def forbidden(*args, **kwargs):
    raise AssertionError('review6 forbids network/model calls')
socket.socket.connect = socket.socket.connect_ex = forbidden
import pytest
restored = []
try:
    for version in ('v3', 'v4', 'v5'):
        folder = ROOT / 'experiments/2026-09-26-zone-study-offline-smoke' / version
        p = folder / 'example_trial_record.json.gz'
        if not p.exists():
            data = subprocess.check_output(['git', 'show', 'HEAD:' + str(p.relative_to(ROOT))])
            expected = json.loads((folder / 'raw_index.json').read_text())['committed'][p.name]
            assert hashlib.sha256(data).hexdigest() == expected
            with p.open('xb') as handle:
                handle.write(data)
            restored.append((p, expected))
    paths = sorted(str(p.relative_to(ROOT)) for p in (ROOT / 'tests').glob('test_zone_study*.py'))
    paths += ['tests/test_zone_event_scheduler.py', 'tests/test_zone_sim_cost.py']
    exit_code = pytest.main(paths + ['--basetemp=./.pytest_tmp', '-q',
         '--junitxml=experiments/2026-09-27-zone-study-multiturn/review6-regression.xml'])
finally:
    shutil.rmtree(ROOT / '.pytest_tmp', ignore_errors=True)
    for p, expected in restored:
        assert hashlib.sha256(p.read_bytes()).hexdigest() == expected
        p.unlink()
    print('Cleanup: .pytest_tmp removed; temporary sparse fixtures removed:', len(restored))
sys.exit(exit_code)
