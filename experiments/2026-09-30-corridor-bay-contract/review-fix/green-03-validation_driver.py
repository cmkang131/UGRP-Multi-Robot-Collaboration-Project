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

ROOT = Path('/Users/changmin/projects/ugrp-wt/cap-t10a-corridor')
sys.path.insert(0, str(ROOT))
os.chdir(ROOT)
from scripts.agent_lock import DEFAULT_ROOT, acquire, release, status

out = Path(sys.argv[1])
out.mkdir(parents=True, exist_ok=False)
shutil.copyfile(__file__, out / 'validation_driver.py')
prereg = json.loads((ROOT / 'experiments/2026-09-29-pair-v6e-carry/prereg_v6e.json').read_text())
pinned = prereg['v6_contract']['source_sha256']
def hashes():
    return {p: hashlib.sha256((ROOT / p).read_bytes()).hexdigest() for p in pinned}
before = hashes()
assert before == pinned, [p for p in pinned if before[p] != pinned[p]]
start = time.monotonic()
last_owner = None
print(json.dumps({'driver_pid': os.getpid()}), flush=True)
while True:
    try:
        lock = acquire(DEFAULT_ROOT, owner='codex', branch='codex/corridor-bay-contract',
                       purpose='PR310 static/fake regression; no physics/render/model',
                       pid=os.getpid(), expected_minutes=4)
        break
    except RuntimeError:
        held = status(DEFAULT_ROOT)
        if held != last_owner:
            print(json.dumps({'waiting': held}), flush=True)
            last_owner = held
        if time.monotonic() - start > 1200:
            raise SystemExit(3)
        time.sleep(.5)

class StaticOnly(importlib.abc.MetaPathFinder):
    def find_spec(self, fullname, path=None, target=None):
        if fullname.split('.')[0] in ('mujoco', 'torch', 'openai', 'anthropic') or fullname.startswith('google.genai'):
            raise AssertionError('no-physics validation forbids import: ' + fullname)
sys.meta_path.insert(0, StaticOnly())
def audit(event, args):
    if event in ('socket.connect', 'socket.getaddrinfo'):
        raise AssertionError('no-network validation: ' + event)
sys.addaudithook(audit)
code = 1
try:
    print('Acquired lock; running tests', flush=True)
    import pytest
    args = ['-q', '-p', 'no:cacheprovider', '--basetemp=' + str(out / 'tmp'), *sys.argv[2:]]
    with (out / 'pytest.log').open('w') as log, contextlib.redirect_stdout(log), contextlib.redirect_stderr(log):
        code = int(pytest.main(args))
    print((out / 'pytest.log').read_text(), flush=True)
finally:
    assert status(DEFAULT_ROOT)['pid'] == os.getpid()
    released = release(DEFAULT_ROOT, owner='codex')
    receipt = {'args': sys.argv[2:], 'exit_code': code, 'python': sys.version,
               'lock': lock, 'released': released, 'pinned_sources_unchanged': hashes() == before == pinned,
               'pinned_sources_count': len(pinned), 'pinned_source_sha256': pinned,
               'scope': 'static/fake; physics/render/model calls 0',
               'head': subprocess.check_output(['git', 'rev-parse', 'HEAD'], text=True).strip(),
               'merged_main': subprocess.check_output(['git', 'rev-parse', 'origin/main'], text=True).strip()}
    receipt['files_sha256'] = {str(p.relative_to(ROOT)): hashlib.sha256(p.read_bytes()).hexdigest()
        for p in [ROOT/'harness/zone_corridor_contract.py', ROOT/'sim/workflow_manager.py',
                  ROOT/'sim/zone_study_admission.py', ROOT/'tests/test_simulation_workflow_manager.py',
                  ROOT/'tests/test_zone_own_executor_corridor_contract.py']}
    (out / 'receipt.json').write_text(json.dumps(receipt, indent=2) + '\n')
    assert receipt['pinned_sources_unchanged']
raise SystemExit(code)
