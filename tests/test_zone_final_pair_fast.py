"""V91 registration, exact schedule, isolation and slot-aware result records."""
import hashlib
import json
import re
import shlex
import subprocess
import sys
from types import SimpleNamespace

import pytest

from harness import zone_final_pair_contract as c
from harness import zone_final_pair_heldout as v90
from harness import zone_final_pair_fast as v91
from scripts import run_final_pair_fast as run
from scripts import agent_lock, agent_sim_slots
from tests.test_zone_final_pair_v3 import FakePhysics, offline_only

ROLE = {'collection_role': 'HELD_OUT_VALIDATION', 'training_eligible': False, 'teacher_only': True}


def bundle(map_id):
    return {**v91.bundle(map_id, 'calibration-unloaded'), 'case': v91.cases(v91.CHECK, map_id)[0]}


def args(out, map_id):
    return ['--check', 'calibration-unloaded', '--map-id', map_id,
            '--expected-source-sha', 'a'*40, '--output', str(out), '--seed', '911']


@pytest.mark.parametrize('map_id', v91.MAPS)
def test_registration_and_fake_collection_bytes_identical_to_v90(tmp_path, map_id):
    from scripts import run_final_pair_heldout as old_run
    new, old = bundle(map_id), {**v90.bundle(map_id, v90.CHECK), 'case': v90.cases(v90.CHECK, map_id)[0]}
    for key in ('measurement', 'timing', 'runtime_interlock', 'clearance_preflight',
                'render_profile', 'contact_profile', 'weld', 'sensors', 'seed', *ROLE):
        assert new[key] == old[key]
    assert new['execution_bundle_id'] == 'zone-final-pair-v91'
    assert new['workflow_version'] == '3.3.0'
    made = []
    def factory(*a, **kw):
        made.append(FakePhysics(*a, **kw))
        return made[-1]
    a = old_run.run_case(old, tmp_path/'old', seed=911, backend_factory=factory)
    b = run.run_case(new, tmp_path/'new', seed=911, backend_factory=factory)
    assert (tmp_path/'new/inputs/schedule.json').read_bytes() == (tmp_path/'old/inputs/schedule.json').read_bytes()
    assert c.base.sha(tmp_path/'new/inputs/schedule.json') == '8e9a126cfdcbc5961cacac4165b76ac65da3310aa40b758f0590d999917813db'
    assert made[0].actions == made[1].actions
    assert made[0].samples == made[1].samples and len(made[1].samples) == 7401
    assert made[0].frames == made[1].frames and len(made[1].frames) == 1851
    for result in (a, b):
        assert result['status'] == 'COLLECTED_UNQUALIFIED'
        assert {k: result[k] for k in ROLE} == ROLE
        assert result['physical_success'] is None


@pytest.mark.parametrize('mutation', ['v90', 'loaded', 'fine', 'weld', 'contact', 'render', 'seed',
                                     'role', 'teacher', 'training', 'timing', 'interlock', 'plan'])
def test_mutation_refused_before_backend_or_output(tmp_path, mutation):
    b = bundle(v91.MAPS[0])
    changes = {'v90': ('execution_bundle_id', 'zone-final-pair-v90'),
               'loaded': ('check', 'calibration-loaded'), 'fine': ('check', 'calibration-fine'),
               'weld': ('weld', 'on'), 'contact': ('contact_profile', 'default'),
               'render': ('render_profile', 'default'), 'seed': ('seed', 912),
               'role': ('collection_role', 'TRAINING'), 'teacher': ('teacher_only', False),
               'training': ('training_eligible', True)}
    if mutation in changes:
        k, v = changes[mutation]
        b[k] = v
    if mutation == 'timing': b['timing']['eval_pose_period_s'] = .2
    if mutation == 'interlock': b['runtime_interlock']['required'] = False
    if mutation == 'plan': b['measurement']['clearance']['minimum_m'] = .1
    with pytest.raises(ValueError):
        run.run_case(b, tmp_path/'case', seed=911, backend_factory=lambda *a, **kw: pytest.fail('backend reached'))
    from sim.final_pair_fast import PhysicsBackend
    with pytest.raises(ValueError):
        PhysicsBackend(b, tmp_path/'case', seed=911)
    assert not (tmp_path/'case').exists()


def fake_host(tmp_path, monkeypatch):
    import os
    original = run.subprocess.check_output
    def git(argv, **kw):
        if '--git-common-dir' in argv: return str(tmp_path/'.git')+'\n'
        if '--show-current' in argv: return 'codex/fast-test\n'
        return original(argv, **kw)
    monkeypatch.setattr(run.subprocess, 'check_output', git)
    monkeypatch.setattr(run, 'check_source', lambda _: None)
    monkeypatch.setattr(run.shutil, 'disk_usage', lambda _: SimpleNamespace(free=20*1024**3))
    monkeypatch.setattr(agent_lock, 'DEFAULT_ROOT', tmp_path/'locks')
    monkeypatch.setitem(sys.modules, 'sim.final_pair_fast', SimpleNamespace(PhysicsBackend=FakePhysics))
    agent_sim_slots.acquire_sim_slot(tmp_path/'locks', slot='sim-first', owner='codex',
        branch='codex/fast-test', purpose='fake', pid=os.getpid(), expected_minutes=1)
    agent_sim_slots.acquire_sim_slot(tmp_path/'locks', slot='sim-second', owner='codex',
        branch='codex/other', purpose='fake', pid=os.getpid(), expected_minutes=1)


@pytest.mark.parametrize('failure', [False, True])
def test_slot_execution_preserves_host_start_end_roles_and_partial_hashes(tmp_path, monkeypatch, failure):
    fake_host(tmp_path, monkeypatch)
    if failure:
        class Broken(FakePhysics):
            def advance_to(self, t):
                raise ValueError('CLEARANCE_ABORT: test')
        monkeypatch.setitem(sys.modules, 'sim.final_pair_fast', SimpleNamespace(PhysicsBackend=Broken))
    map_id = v91.MAPS[0]
    out = tmp_path/'outputs/run'
    assert run.main(args(out, map_id)+['--execute', '--lock-owner', 'codex', '--sim-slot', 'sim-first']) == int(failure)
    records = {p: json.loads((out/p).read_text()) for p in (
        'plan.json', 'result.json', f'{map_id}/bundle.json', f'{map_id}/result.json')}
    for record in records.values():
        assert {k: record[k] for k in ROLE} == ROLE
    for name in ('plan.json', 'result.json', f'{map_id}/result.json'):
        for key in ('host_start',) if name == 'plan.json' else ('host_start', 'host_end'):
            host = records[name][key]
            assert len(host['loadavg']) == 3
            assert [h['name'] for h in host['concurrent_holders']] == ['sim-first', 'sim-second']
    case = records[f'{map_id}/result.json']
    assert case['partial_data_retained'] is failure
    assert case['collection_data_status'] == ('PARTIAL_INVALID_HOST_ERROR' if failure else 'UNQUALIFIED')
    hashes = json.loads((out/map_id/'artifacts.sha256.json').read_text())
    assert hashes['result.json'] == c.base.sha(out/map_id/'result.json')


def test_slot_cannot_bypass_runner_branch_or_legacy_lock_admission(tmp_path, monkeypatch):
    fake_host(tmp_path, monkeypatch)
    for flags in ([], ['--sim-slot', 'sim-second']):
        with pytest.raises(ValueError, match='live owned'):
            run.main(args(tmp_path/'outputs/no', v91.MAPS[0])+['--execute', '--lock-owner', 'codex']+flags)
    assert not (tmp_path/'outputs/no').exists()


def test_v91_source_closure_and_workflow():
    from sim import workflow_manager as wm
    from scripts.run_ci_tests import TEST_PATTERNS, collect_test_files
    value = bundle(v91.MAPS[0])
    for path in ('sim/final_pair_fast_guard.py', 'scripts/agent_lock.py', 'scripts/agent_sim_slots.py', v91.REGISTRY, v91.WORKFLOW,
                 v90.REGISTRY, v90.WORKFLOW):
        assert value['source_sha256'][path] == c.base.sha(c.ROOT/path)
    row, _ = wm._row(c.ROOT, v91.WORKFLOW_ID)
    assert row['version'] == '3.3.0'
    planned = wm.plan(c.ROOT, v91.WORKFLOW_ID, args(c.ROOT/'outputs/unused', v91.MAPS[0])+['--sim-slot', 'sim-test'])
    assert planned['command'][1:3] == ['-m', 'scripts.run_final_pair_fast']
    assert not planned['execution_started']
    for path in ('tests/test_zone_final_pair_fast.py', 'tests/test_final_pair_fast_guard.py',
                 'tests/test_final_pair_fast_replay.py', 'tests/test_agent_sim_slots.py', 'tests/test_review_355.py'):
        assert collect_test_files(c.ROOT, TEST_PATTERNS).count(path) == 1


def test_frozen_sources_and_handoff_prefix_preserved_and_new_commands_parse():
    receipt = json.loads((c.ROOT/'experiments/2026-10-03-calib-fast-guard/preservation.json').read_text())
    for name, sha in receipt['unchanged_sha256'].items():
        assert c.base.sha(c.ROOT/name) == sha, name
    data = (c.ROOT/'PHYSICS_HANDOFF.md').read_bytes()
    size = receipt['handoff_prefix']['bytes']
    assert hashlib.sha256(data[:size]).hexdigest() == receipt['handoff_prefix']['sha256']
    blocks = re.findall(r'```bash\n(.*?)\n```', data[size:].decode(), re.S)
    assert len(blocks) == 1
    block = blocks[0]
    subprocess.run(['bash', '-n'], input=block, text=True, check=True)
    assert '--pid $$' in block and 'wait "$CORRIDOR_PID"' in block and 'wait "$DOOR_PID"' in block
    assert 'trap cleanup EXIT' in block
    maps = []
    for command in block.replace('\\\n', ' ').splitlines():
        if 'scripts.sim_cli workflow run' not in command:
            continue
        words = shlex.split(command)
        if words[-1] == '&':
            words.pop()
        start = words.index('scripts.sim_cli')
        assert words[start+1:start+5] == ['workflow', 'run', 'zone-final-pair-heldout-v91', '--']
        parsed = run.parser().parse_args(words[start+5:])
        assert parsed.execute and parsed.seed == 911 and parsed.lock_owner == 'codex'
        assert parsed.sim_slot.startswith('sim-codex-v91-') and parsed.expected_source_sha == '$FINAL_SHA'
        maps.append(parsed.map_id)
    assert set(maps) == set(v91.MAPS)
