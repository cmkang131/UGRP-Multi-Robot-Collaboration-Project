import importlib.abc
import json
import os
from pathlib import Path
import subprocess
import sys
import time
import uuid

root = Path('/Users/changmin/projects/ugrp-wt/cap-t08a-beam-plan')
sys.path.insert(0, str(root))
from scripts import agent_lock
out = Path('/Users/changmin/projects/ugrp/outputs/beam-initial-pose-contract') / ('tests-' + time.strftime('%Y%m%d-%H%M%S') + '-' + uuid.uuid4().hex[:6])
out.mkdir(parents=True)
print('raw:', out, flush=True)
started = time.monotonic()
while True:
    try:
        receipt = agent_lock.acquire(agent_lock.DEFAULT_ROOT, owner='codex', branch='codex/beam-initial-pose-contract', purpose='T08a static/fake pytest only; 0 SIM', pid=os.getpid(), expected_minutes=2)
        break
    except RuntimeError:
        if time.monotonic() - started > 2400:
            raise
        time.sleep(1)
(out / 'lock.json').write_text(json.dumps(receipt, indent=2))
print('lock acquired', flush=True)
tests = ['tests/test_beam_initial_pose_plan.py',
         'tests/test_pair_passage_plan.py::test_default_plan_and_probe_cases_are_byte_identical_to_main',
         'tests/test_pair_passage_plan.py::test_opt_in_on_the_m2_door_map_returns_the_frozen_plan',
         'tests/test_pair_passage_plan.py::test_planner_constants_match_the_sources_they_mirror',
         'tests/test_zone_pair_executor.py::test_destination_route_reaches_zone_b_and_uses_bounded_segments']
code = '''
import importlib.abc, sys, socket
class Block(importlib.abc.MetaPathFinder):
    def find_spec(self, fullname, path=None, target=None):
        if fullname.split('.')[0] in {'mujoco', 'torch', 'openai', 'anthropic', 'google'}:
            raise AssertionError('No physics/model import: ' + fullname)
sys.meta_path.insert(0, Block())
def refuse(*args, **kwargs):
    raise AssertionError('No network calls')
socket.socket.connect = refuse
import pytest
sys.exit(pytest.main(sys.argv[1:]))
'''
cmd = [sys.executable, '-c', code, *tests, '-q', '--disable-warnings', '--junitxml=' + str(out/'junit.xml')]
try:
    with (out / 'pytest.log').open('w') as log:
        completed = subprocess.run(cmd, cwd=root, stdout=log, stderr=subprocess.STDOUT,
                                   env={**os.environ, 'OMP_NUM_THREADS':'1','OPENBLAS_NUM_THREADS':'1',
                                        'PYTHONPATH':str(root), 'PYTEST_DISABLE_PLUGIN_AUTOLOAD':'1'}, timeout=120)
    result = {'exit_code': completed.returncode, 'tests': tests, 'python': sys.version,
              'sim_s': 0, 'physics_model_imports_blocked': True, 'loadavg_after': os.getloadavg()}
    (out / 'result.json').write_text(json.dumps(result, indent=2))
    print((out/'pytest.log').read_text(), flush=True)
    print('result:', out, flush=True)
finally:
    held = agent_lock.status(agent_lock.DEFAULT_ROOT)
    if held and held.get('pid') == os.getpid():
        agent_lock.release(agent_lock.DEFAULT_ROOT, owner='codex')
sys.exit(completed.returncode)
