"""Time offline pytest locally using the exact dedicated CI module list.

Run from repository root with OMP_NUM_THREADS=1. No model/network/MuJoCo.
"""
import argparse
import hashlib
import json
import os
from pathlib import Path
import platform
import re
import shlex
import shutil
import socket
import subprocess
import sys
import time

ROOT = Path(__file__).resolve().parents[2]
OUT = Path(__file__).parent
sys.path.insert(0, str(ROOT))
sys.modules['mujoco'] = None


def forbidden(*args, **kwargs):
    raise AssertionError('review7 forbids network/model calls')


socket.socket.connect = socket.socket.connect_ex = forbidden
assert os.environ.get('OMP_NUM_THREADS') == '1'
assert Path.cwd() == ROOT
parser = argparse.ArgumentParser()
parser.add_argument('--scope', choices=('smoke', 'ci', 'related'), default='ci')
args = parser.parse_args()
import pytest
workflow = (ROOT / '.github/workflows/tests.yml').read_text()
job = workflow.split('  zone-multiturn-properties:\n', 1)[1].split('\n  tensorboard-export:', 1)[0]
timeout = int(re.search(r'timeout-minutes: (\d+)', job)[1])
command = re.search(r'run: (python -m pytest [^\n]+)', job)[1]
ci_args = shlex.split(command)[3:]
paths = [a for a in ci_args if a.endswith('.py')]
if args.scope == 'smoke':
    paths = ['tests/test_zone_study_multiturn_review7.py', 'tests/test_zone_study_multiturn_review6.py',
             'tests/test_zone_study_multiturn_model.py']
elif args.scope == 'related':
    ci_paths = set(paths)
    paths = sorted(str(p.relative_to(ROOT)) for p in (ROOT / 'tests').glob('test_zone_study*.py')
                   if str(p.relative_to(ROOT)) not in ci_paths)
    paths += ['tests/test_zone_event_scheduler.py', 'tests/test_zone_sim_cost.py']
pytest_args = (ci_args if args.scope == 'ci' else paths + ['--basetemp=./.pytest_tmp', '-q'])
prefix = OUT / ('review7-' + args.scope)
pytest_args += ['--junitxml=' + str(prefix) + '.xml']
if args.scope == 'smoke':
    pytest_args += ['-x']
start, load = time.perf_counter(), os.getloadavg()
exit_code = None
restored = []
try:
    if args.scope == 'related':
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
    exit_code = int(pytest.main(pytest_args))
finally:
    elapsed = time.perf_counter() - start
    shutil.rmtree(ROOT / '.pytest_tmp', ignore_errors=True)
    for p, expected in restored:
        assert hashlib.sha256(p.read_bytes()).hexdigest() == expected
        p.unlink()
    timing = {'scope': args.scope, 'command': pytest_args, 'exit_code': exit_code,
              'elapsed_s': elapsed, 'ci_job_timeout_s': timeout * 60,
              'within_30_minutes_locally': elapsed < 1800,
              'remote_ci_verified': False, 'includes_dependency_install': False,
              'python': sys.version, 'platform': platform.platform(),
              'load_start': load, 'load_end': os.getloadavg(),
              'model_calls': 0, 'physics_steps': 0,
              'temporary_directory_removed': not (ROOT / '.pytest_tmp').exists()}
    timing['temporary_sparse_fixtures_removed'] = len(restored)
    prefix.with_suffix('.timing.json').write_text(json.dumps(timing, indent=2) + '\n')
    print(json.dumps(timing, ensure_ascii=False))
sys.exit(exit_code)
