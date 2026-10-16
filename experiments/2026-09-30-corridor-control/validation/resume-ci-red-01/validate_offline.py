"""Finite unlocked static/fake validation; no simulator/model/network imports.

Usage: existing-venv/python validate_offline.py NEW_ABSOLUTE_OUTPUT [pytest args]
The output directory must not exist. No runtime experiment is started.
"""
import contextlib
import hashlib
import importlib.abc
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys
import time

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))
os.chdir(ROOT)
from scripts.agent_lock import DEFAULT_ROOT, status

out = Path(sys.argv[1])
if not out.is_absolute():
    raise SystemExit('absolute primary outputs path required')
out.mkdir(parents=True, exist_ok=False)
shutil.copyfile(__file__, out / 'validate_offline.py')
pinned = json.loads((ROOT / 'experiments/2026-09-29-pair-v6e-carry/prereg_v6e.json').read_text())['v6_contract']['source_sha256']
sha = lambda path: hashlib.sha256(path.read_bytes()).hexdigest()
before = {p: sha(ROOT / p) for p in pinned}
assert before == pinned, 'pinned sources already differ'
# PR #328: local offline correctness tests do not own or wait for the host
# lock. Record concurrent load only; these durations are not benchmarks.
lock_at_start = status(DEFAULT_ROOT)
load_at_start = os.getloadavg()
print(json.dumps({'host_lock_required': False, 'concurrent_lock': lock_at_start}), flush=True)

class OfflineOnly(importlib.abc.MetaPathFinder):
    def find_spec(self, fullname, path=None, target=None):
        if fullname.split('.')[0] in ('mujoco', 'torch', 'openai', 'anthropic') or fullname.startswith('google.genai'):
            raise AssertionError('offline validation forbids import: ' + fullname)
sys.meta_path.insert(0, OfflineOnly())
def audit(event, args):
    if event in ('socket.connect', 'socket.getaddrinfo'):
        raise AssertionError('offline validation forbids network: ' + event)
sys.addaudithook(audit)
code = 1
mutation = None
mutation_checks = []
try:
    if os.environ.get('T10B_MUTATION'):
        from mutation_variants import install
        mutation = install(os.environ['T10B_MUTATION'])
    import pytest
    with (out / 'pytest.log').open('w') as log, contextlib.redirect_stdout(log), contextlib.redirect_stderr(log):
        code = int(pytest.main(['-q', '-p', 'no:cacheprovider', '--basetemp=' + str(out / 'tmp'), *sys.argv[2:]]))
    print((out / 'pytest.log').read_text(), flush=True)
    if code == 0 and os.environ.get('T10B_BATCH_MUTATIONS') == '1':
        from mutation_variants import VARIANTS
        for name in VARIANTS:
            destination = out / 'mutations' / name
            worker = subprocess.run([sys.executable, str(Path(__file__).with_name('mutation_worker.py')),
                                     name, str(destination)], text=True, capture_output=True)
            print(worker.stdout, flush=True)
            if worker.returncode:
                print(worker.stderr, flush=True)
                code = 1
            mutation_checks.append({'name': name, 'check_exit_code': worker.returncode,
                                    'receipt': str(destination / 'receipt.json')})
finally:
    after = {p: sha(ROOT / p) for p in pinned}
    files = ['harness/zone_corridor_control.py', 'harness/zone_corridor_control_plan.py',
             'harness/zone_corridor_contract.py', 'harness/zone_pair_status.py',
             'tests/test_zone_own_executor_corridor_control.py']
    receipt = {'pytest_args': sys.argv[2:], 'exit_code': code, 'python': sys.version,
               'host_lock_required': False, 'concurrent_lock_at_start': lock_at_start,
               'loadavg_at_start': load_at_start, 'loadavg_at_end': os.getloadavg(),
               'pinned_source_count': len(pinned),
               'pinned_sources_unchanged': before == after == pinned,
               'pinned_source_sha256': pinned, 'scope': 'fake/offline only; physics/render/model calls 0',
               'head_before_commit': subprocess.check_output(['git', 'rev-parse', 'HEAD'], text=True).strip(),
               'files_sha256': {p: sha(ROOT / p) for p in files}, 'mutation': mutation,
               'mutation_checks': mutation_checks}
    (out / 'receipt.json').write_text(json.dumps(receipt, indent=2) + '\n')
    assert receipt['pinned_sources_unchanged']
raise SystemExit(code)
