import contextlib
import hashlib
import importlib.abc
import importlib.metadata
import json
import os
from pathlib import Path
import platform
import shutil
import subprocess
import sys
import time

ROOT = Path('/Users/changmin/projects/ugrp-wt/cap-t10a-corridor')
sys.path.insert(0, str(ROOT))
from scripts.agent_lock import DEFAULT_ROOT, acquire, release, status

out = Path(sys.argv[1])
out.mkdir(parents=True, exist_ok=False)
shutil.copyfile(__file__, out / 'validation_driver.py')
source_paths = ['harness/zone_corridor_contract.py', 'tests/test_zone_own_executor_corridor_contract.py']
preserved = ['harness/zone_own_executor.py', 'harness/zone_team_footprint.py',
             'harness/zone_team_footprint_v3.py', 'harness/rgb_execution_bundle.py',
             'experiments/2026-09-29-pair-v6e-carry/prereg_v6e.json',
             'configs/simulation_workflows.json']
for pattern in ('configs/zone_study_scenarios/s*.json', 'configs/zone_study_scenarios_v2/s*.json',
                'maps/zones/*.json', 'maps/zones_final/*.json'):
    preserved.extend(str(p.relative_to(ROOT)) for p in ROOT.glob(pattern))

def hashes(paths):
    return {p: hashlib.sha256((ROOT/p).read_bytes()).hexdigest() for p in sorted(paths)}

head = subprocess.check_output(['git', 'rev-parse', 'HEAD'], cwd=ROOT, text=True).strip()
branch = subprocess.check_output(['git', 'branch', '--show-current'], cwd=ROOT, text=True).strip()
assert branch == 'codex/corridor-bay-contract'
before, new_before = hashes(preserved), hashes(source_paths)
started = time.monotonic()
while True:
    try:
        lock = acquire(DEFAULT_ROOT, owner='codex', branch=branch, purpose='T10a static fake tests; no physics/model',
                       pid=os.getpid(), expected_minutes=3)
        break
    except RuntimeError:
        held = status(DEFAULT_ROOT)
        print(json.dumps({'waiting_for_lock': held, 'elapsed_s': round(time.monotonic()-started, 1)}), flush=True)
        if time.monotonic()-started > 1200:
            raise SystemExit('lock wait expired; tests not started')
        time.sleep(15)

print('Acquired own lock; starting nonphysical tests', flush=True)
class StaticOnly(importlib.abc.MetaPathFinder):
    def find_spec(self, fullname, path=None, target=None):
        if fullname.split('.')[0] in ('mujoco', 'torch', 'openai', 'anthropic') or fullname.startswith('google.genai'):
            raise AssertionError('static test forbids: '+fullname)
sys.meta_path.insert(0, StaticOnly())
def audit(event, args):
    if event in ('socket.connect', 'socket.getaddrinfo'):
        raise AssertionError('static test forbids network: '+event)
sys.addaudithook(audit)
exit_code = 1
receipt = {'base_sha': head, 'branch': branch, 'new_source_sha256': new_before,
           'preserved_sha256': before, 'lock': lock, 'python': sys.version,
           'platform': platform.platform(), 'scope': 'static/fake only', 'sim_cap_s': 0}
try:
    import pytest
    with (out/'pytest.log').open('w') as log, contextlib.redirect_stdout(log), contextlib.redirect_stderr(log):
        exit_code = pytest.main(['-q', '-p', 'no:cacheprovider',
            '--basetemp='+str(out/'pytest_tmp'),
            '--deselect=tests/test_zone_own_executor.py::test_team_host_feeds_each_executor_only_its_own_camera',
            'tests/test_zone_own_executor_corridor_contract.py',
            'tests/test_zone_own_executor.py', 'tests/test_zone_pair_registered_source.py',
            'tests/test_zone_hard_routes.py'])
    print((out/'pytest.log').read_text(), flush=True)
    from harness.zone_corridor_contract import CorridorContract
    data = json.loads((ROOT/'maps/zones_final/zone_wide_corridor_final_v1.json').read_text())
    c = CorridorContract(data, robot_model='masterpi_v3')
    pair = c.formation('long_beam', {'end_neg': 'r1', 'end_pos': 'r2'})
    solo = c.formation('cyan', {'west': 'r3'})
    stop = (3.2, .625, 0.)
    crossing = [(1.5, 1.175, 0.), (4.6, 1.175, 0.)]
    escape = [(3.2, 1.175, 0.), stop]
    proposals = {'qualification': 'authored static proposals; no runtime/physics/E2E evidence',
        'pair': c.check(pair, forward_path=crossing, reverse_path=crossing[::-1],
                        bay_pose=(3.1, .625, 0.), placements=[(pair, (3.0625, 1.175, 0.)), (solo, stop)]),
        'solo_bay': c.check(solo, bay_pose=stop, evacuation_path=escape, reentry_path=escape[::-1])}
    (out/'static_proposals.json').write_text(json.dumps(proposals, indent=2, ensure_ascii=False)+'\n')
    receipt.update(test_exit_code=int(exit_code), preserved_unchanged=before == hashes(preserved),
                   new_source_unchanged=new_before == hashes(source_paths),
                   local_physics_steps=0, local_model_calls=0, local_render_calls=0,
                   pytest=importlib.metadata.version('pytest'))
    assert receipt['preserved_unchanged'] and receipt['new_source_unchanged']
finally:
    held = status(DEFAULT_ROOT)
    assert held['pid'] == os.getpid() and held['branch'] == branch
    receipt['released_lock'] = release(DEFAULT_ROOT, owner='codex')
    receipt['artifact_sha256'] = {p.name: hashlib.sha256(p.read_bytes()).hexdigest()
                                  for p in out.iterdir() if p.is_file()}
    (out/'receipt.json').write_text(json.dumps(receipt, indent=2, ensure_ascii=False)+'\n')
    print(json.dumps({'output': str(out), 'exit_code': int(exit_code), 'lock_released': True}), flush=True)
raise SystemExit(int(exit_code))
