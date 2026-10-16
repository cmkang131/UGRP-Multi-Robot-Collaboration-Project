"""Finite lock-owned static/fake validation; no simulator/model/network imports.

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
from scripts.agent_lock import DEFAULT_ROOT, acquire, release, status

out = Path(sys.argv[1])
if not out.is_absolute():
    raise SystemExit('absolute primary outputs path required')
out.mkdir(parents=True, exist_ok=False)
shutil.copyfile(__file__, out / 'validate_offline.py')
pinned = json.loads((ROOT / 'experiments/2026-09-29-pair-v6e-carry/prereg_v6e.json').read_text())['v6_contract']['source_sha256']
sha = lambda path: hashlib.sha256(path.read_bytes()).hexdigest()
before = {p: sha(ROOT / p) for p in pinned}
assert before == pinned, 'pinned sources already differ'
start, last_notice = time.monotonic(), -100.
while True:
    try:
        lock = acquire(DEFAULT_ROOT, owner='codex', branch='codex/corridor-yield-control',
                       purpose='T10b fake/offline tests; no physics/render/model',
                       pid=os.getpid(), expected_minutes=5)
        break
    except RuntimeError:
        if time.monotonic() - last_notice >= 30:
            print(json.dumps({'waiting_for_lock': status(DEFAULT_ROOT)}), flush=True)
            last_notice = time.monotonic()
        if time.monotonic() - start > 1200:
            raise SystemExit('lock wait expired; tests not started')
        time.sleep(.5)
print(json.dumps({'lock_acquired': lock}), flush=True)

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
try:
    import pytest
    with (out / 'pytest.log').open('w') as log, contextlib.redirect_stdout(log), contextlib.redirect_stderr(log):
        code = int(pytest.main(['-q', '-p', 'no:cacheprovider', '--basetemp=' + str(out / 'tmp'), *sys.argv[2:]]))
    print((out / 'pytest.log').read_text(), flush=True)
finally:
    assert status(DEFAULT_ROOT)['pid'] == os.getpid()
    released = release(DEFAULT_ROOT, owner='codex')
    after = {p: sha(ROOT / p) for p in pinned}
    files = ['harness/zone_corridor_control.py', 'harness/zone_corridor_control_plan.py',
             'harness/zone_corridor_contract.py', 'harness/zone_pair_status.py',
             'tests/test_zone_own_executor_corridor_control.py']
    receipt = {'pytest_args': sys.argv[2:], 'exit_code': code, 'python': sys.version,
               'lock': lock, 'released': released, 'pinned_source_count': len(pinned),
               'pinned_sources_unchanged': before == after == pinned,
               'pinned_source_sha256': pinned, 'scope': 'fake/offline only; physics/render/model calls 0',
               'head_before_commit': subprocess.check_output(['git', 'rev-parse', 'HEAD'], text=True).strip(),
               'files_sha256': {p: sha(ROOT / p) for p in files}}
    (out / 'receipt.json').write_text(json.dumps(receipt, indent=2) + '\n')
    assert receipt['pinned_sources_unchanged']
raise SystemExit(code)
