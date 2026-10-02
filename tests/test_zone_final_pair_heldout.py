"""V90 collection admission/recording regressions; no native or model calls."""
import copy
import hashlib
import json
import sys
from types import SimpleNamespace

import pytest

from harness import zone_final_pair_contract as c
from harness import zone_final_pair_heldout as heldout
from harness import zone_final_pair_heldout_clearance as clearance
from harness.zone_final_pair_calibration import schedule
from harness.zone_final_pair_excitation import MAP_ID, UNLOADED_POSE
from scripts import run_final_pair_v3 as legacy_run
from scripts import run_final_pair_heldout as run
from scripts import run_final_pair_heldout as managed
from tests.test_zone_final_pair_v3 import FakePhysics, offline_only

BASELINE = c.ROOT / 'experiments/2026-10-01-calib-heldout-maps/v88_baseline.json'
EXPECTED_ROLE = {'collection_role': 'HELD_OUT_VALIDATION',
                 'training_eligible': False, 'teacher_only': True}


def case_bundle(map_id):
    return {**heldout.bundle(map_id, heldout.CHECK), 'case': heldout.cases(heldout.CHECK, map_id)[0]}


def args(tmp_path, map_id, check=heldout.CHECK):
    return ['--check', check, '--map-id', map_id, '--seed', '911',
            '--expected-source-sha', 'a'*40, '--output', str(tmp_path/'out')]


@pytest.mark.parametrize('map_id', heldout.MAPS)
@pytest.mark.parametrize('entry', [managed.main])
def test_check_only_plans_admit_only_new_heldout_without_backend(tmp_path, capsys, monkeypatch, map_id, entry):
    monkeypatch.setitem(sys.modules, 'sim.final_pair_heldout', None)
    assert entry(args(tmp_path, map_id)) == 0
    plan = json.loads(capsys.readouterr().out)
    assert plan['execution_bundle_id'] == heldout.BUNDLE_ID
    assert plan['runnable'] and plan['blocked_on'] == []
    assert plan['seed'] == 911 and plan['denominator'] == 1
    assert plan['cases'] == [{'id': map_id, 'map_id': map_id, 'checkpoint': None, 'sim_cap_s': 370.}]
    assert not plan['execution_started'] and not (tmp_path/'out').exists()
    assert {k: plan[k] for k in EXPECTED_ROLE} == EXPECTED_ROLE
    preflight = plan['clearance_preflight'][0]
    assert preflight['runtime_interlock'] == clearance.runtime_interlock()
    assert preflight['envelope_policy'] == 'ADVISORY'
    assert preflight['start_pose_check']['bodies']['r1']['start_xy_yaw'] == UNLOADED_POSE


@pytest.mark.parametrize('map_id', heldout.MAPS)
@pytest.mark.parametrize('check', ['calibration-fine', 'calibration-loaded'])
def test_fine_and_loaded_still_refused_before_output_or_backend(tmp_path, monkeypatch, map_id, check):
    monkeypatch.setitem(sys.modules, 'sim.final_pair_heldout', None)
    for entry in (legacy_run.main, managed.main):
        with pytest.raises(ValueError):
            entry(args(tmp_path, map_id, check))
    with pytest.raises(ValueError):
        heldout.bundle(map_id, check)
    assert not (tmp_path/'out').exists()


@pytest.mark.parametrize('check', ['p03', 'carry', 'calibration-unloaded'])
def test_new_workflow_cannot_select_training_or_student(tmp_path, check):
    with pytest.raises(ValueError, match='held-out map'):
        managed.main(args(tmp_path, MAP_ID, check))


@pytest.mark.parametrize('map_id', heldout.MAPS)
def test_seed_is_fixed_at_cli_case_and_direct_backend(tmp_path, map_id):
    from sim.final_pair_heldout import PhysicsBackend
    with pytest.raises(ValueError, match='seed 911'):
        run.main(args(tmp_path, map_id)+['--seed', '912'])
    bundle = case_bundle(map_id)
    with pytest.raises(ValueError, match='seed 911'):
        run.run_case(bundle, tmp_path/'case', seed=912, backend_factory=FakePhysics)
    with pytest.raises(ValueError, match='seed 911'):
        PhysicsBackend(bundle, tmp_path/'case', seed=912)
    assert not (tmp_path/'case').exists()


@pytest.mark.parametrize('check', c.CHECKS[2:])
def test_two_door_plan_bundle_and_schedule_preserved(tmp_path, capsys, check, monkeypatch):
    frozen = json.loads(BASELINE.read_text())['checks'][check]
    from tests.test_review_352 import BASE_BYTES
    # V91 changed only host-lock admission in the old source closure. Compare
    # the historical bundle bytes with that one receipt explicitly normalized.
    original_sha = c.base.sha
    monkeypatch.setattr(c.base, 'sha', lambda path:
        '709db3d87e4d2369171aba10ce3c64b7c8be254e2de7115ae608a022b1783dce'
        if path == c.ROOT/'scripts/agent_lock.py' else original_sha(path))
    assert legacy_run.main(args(tmp_path, MAP_ID, check)) == 0
    plan_bytes = capsys.readouterr().out.encode()
    bundle_bytes = (json.dumps(c.bundle(MAP_ID, check), ensure_ascii=False,
                               indent=2, allow_nan=False) + '\n').encode()
    assert hashlib.sha256(plan_bytes).hexdigest() == BASE_BYTES[check]['plan']
    assert hashlib.sha256(bundle_bytes).hexdigest() == BASE_BYTES[check]['bundle']
    path = tmp_path/'schedule.json'
    run.write(path, schedule(check))
    assert path.stat().st_size == frozen['schedule_bytes']
    assert c.base.sha(path) == frozen['schedule_file_sha256']


@pytest.mark.parametrize('map_id', heldout.MAPS)
def test_fake_acquisition_records_same_bytes_samples_and_validation_role(tmp_path, map_id):
    from sim.final_pair_heldout import make_scene
    bundle = case_bundle(map_id)
    scene = make_scene(bundle, seed=911)  # configuration only; no compilation/render
    assert scene._render_profile_name == 'floor_light_v1'
    assert scene.config['static_map'] == c.resolve(map_id)[0]
    assert scene.config['setup_only']['measurement_reset']['authored_xy_yaw'] == UNLOADED_POSE
    made = []
    def factory(*a, **kw):
        made.append(FakePhysics(*a, **kw))
        return made[-1]
    out = tmp_path/'case'
    result = run.run_case(bundle, out, seed=911, backend_factory=factory)
    backend = made[0]
    assert result['status'] == 'COLLECTED_UNQUALIFIED' and result['protocol_complete']
    assert result['collection_data_status'] == 'UNQUALIFIED'
    assert not result['student_control'] and result['physical_success'] is None
    assert {k: result[k] for k in EXPECTED_ROLE} == EXPECTED_ROLE
    assert backend.closed and backend.deadline == backend.now == 371.
    assert len(backend.samples) == 7401 and len(backend.frames) == 1851
    assert backend.samples == [1.+i*.05 for i in range(7401)]
    assert backend.frames == backend.samples[::4]
    assert backend.actions == [(1.+round(e['t']/.05)*.05, e['robot_id'], e['action'])
                               for e in schedule(heldout.CHECK)]
    frozen = json.loads(BASELINE.read_text())['checks'][heldout.CHECK]
    assert c.base.sha(out/'inputs/schedule.json') == frozen['schedule_file_sha256']
    for filename in ('bundle.json', 'result.json'):
        saved = json.loads((out/filename).read_text())
        assert {k: saved[k] for k in EXPECTED_ROLE} == EXPECTED_ROLE
    expected_measurement = copy.deepcopy(json.loads(BASELINE.read_text())['checks'][heldout.CHECK]
                                        ['bundle_without_source_hashes']['measurement'])
    expected_measurement['map_id'] = map_id
    assert bundle['measurement'] == expected_measurement
    assert bundle['runtime_interlock'] == clearance.runtime_interlock()


@pytest.mark.parametrize('mutation', ['weld', 'profile', 'role', 'teacher', 'seed', 'map',
                                     'check', 'timing', 'interlock', 'measurement', 'case', 'old_id'])
def test_changed_registration_is_rejected_before_any_owner(tmp_path, mutation):
    from sim.final_pair_heldout import PhysicsBackend
    bundle = case_bundle(heldout.MAPS[0])
    if mutation == 'weld': bundle['weld'] = 'on'
    elif mutation == 'profile': bundle['render_profile'] = 'default'
    elif mutation == 'role': bundle['training_eligible'] = True
    elif mutation == 'teacher': bundle['teacher_only'] = False
    elif mutation == 'seed': bundle['seed'] = 912
    elif mutation == 'map': bundle['map_id'] = MAP_ID
    elif mutation == 'check': bundle['check'] = 'p03'
    elif mutation == 'timing': bundle['timing']['eval_pose_period_s'] = .2
    elif mutation == 'interlock': bundle['runtime_interlock']['required'] = False
    elif mutation == 'measurement': bundle['measurement']['command_lease_s'] = .1
    elif mutation == 'case': bundle['case']['map_id'] = MAP_ID
    elif mutation == 'old_id': bundle['execution_bundle_id'] = c.BUNDLE_ID
    with pytest.raises(ValueError):
        run.run_case(bundle, tmp_path/'case', seed=911,
                     backend_factory=lambda *a, **k: pytest.fail('backend reached'))
    with pytest.raises(ValueError):
        PhysicsBackend(bundle, tmp_path/'case', seed=911)
    assert not (tmp_path/'case').exists()


@pytest.mark.parametrize('map_id', heldout.MAPS)
@pytest.mark.parametrize('fault', ['wall', 'nan', 'missing'])
def test_same_abort_interlock_preserves_partial_invalid_heldout(tmp_path, monkeypatch, map_id, fault):
    from tests.test_zone_final_pair_review_fixes import fake_guard
    bundle = case_bundle(map_id)
    guard = fake_guard(monkeypatch)
    guard.bundle = bundle
    guard.scene.config['static_map'] = c.resolve(map_id)[0]
    out = tmp_path/'case'
    guard._append = lambda path, row: run.write(out/path, row)
    made = []
    class Physics(FakePhysics):
        def eval_sample(self):
            super().eval_sample()
            if len(self.samples) == 2:
                if fault == 'wall': guard.world.data.geom_xpos[0, 0] = 10.
                elif fault == 'nan': guard.world.data.geom_xpos[0, 2] = float('nan')
                else: guard.world.model.ngeom = 0
            guard.collection_guard()
            run.write(out/'eval_only/partial.json', {'t': self.now})
    def factory(*a, **kw):
        made.append(Physics(*a, **kw))
        return made[-1]
    result = run.run_case(bundle, out, seed=911, backend_factory=factory)
    assert result['status'] == 'HOST_ERROR' and not result['protocol_complete']
    assert result['collection_data_status'] == 'PARTIAL_INVALID_HOST_ERROR'
    assert result['partial_data_retained'] and made[0].closed
    assert len(made[0].samples) == 2 and guard.held == ['r1', 'r2']
    assert {k: result[k] for k in EXPECTED_ROLE} == EXPECTED_ROLE
    hashes = json.loads((out/'artifacts.sha256.json').read_text())
    for path in ('eval_only/partial.json', 'eval_only/clearance_abort.jsonl'):
        assert hashes[path] == c.base.sha(out/path)


def test_managed_fake_execution_keeps_role_in_top_level_result(tmp_path, monkeypatch):
    # Replace only admissions that depend on this test's temporary fake host.
    from scripts import agent_lock
    original = run.subprocess.check_output
    def git(argv, **kw):
        if '--git-common-dir' in argv: return str(tmp_path/'.git')+'\n'
        if '--show-current' in argv: return 'codex/fake-heldout\n'
        return original(argv, **kw)
    monkeypatch.setattr(run.subprocess, 'check_output', git)
    monkeypatch.setattr(run, 'check_source', lambda _: None)
    monkeypatch.setattr(run.shutil, 'disk_usage', lambda _: SimpleNamespace(free=20*1024**3))
    monkeypatch.setattr(agent_lock, 'status', lambda _: {
        'pid_alive': True, 'owner': 'codex', 'branch': 'codex/fake-heldout'})
    monkeypatch.setitem(sys.modules, 'sim.final_pair_heldout', SimpleNamespace(PhysicsBackend=FakePhysics))
    out = tmp_path/'outputs/run'
    assert managed.main(args(tmp_path, heldout.MAPS[0])+[
        '--execute', '--lock-owner', 'codex', '--output', str(out)]) == 0
    for name in ('plan.json', 'result.json'):
        value = json.loads((out/name).read_text())
        assert {k: value[k] for k in EXPECTED_ROLE} == EXPECTED_ROLE


def test_new_workflow_source_closure_and_ci_registration():
    from sim import workflow_manager as wm
    from scripts.run_ci_tests import TEST_PATTERNS, collect_test_files
    assert collect_test_files(c.ROOT, TEST_PATTERNS).count('tests/test_zone_final_pair_heldout.py') == 1
    row, _ = wm._row(c.ROOT, heldout.WORKFLOW_ID)
    assert row['version'] == heldout.WORKFLOW_VERSION
    assert wm._row(c.ROOT, c.WORKFLOW_ID)[0]['version'] == '3.1.0'
    for map_id in heldout.MAPS:
        bundle = heldout.bundle(map_id, heldout.CHECK)
        _, static_row, _ = c.resolve(map_id)
        for path in (heldout.REGISTRY, heldout.WORKFLOW, static_row['file'],
                     'scripts/run_final_pair_heldout.py', 'harness/zone_final_pair_heldout.py',
                     'harness/zone_final_pair_heldout_clearance.py', 'sim/final_pair_heldout.py',
                     'harness/zone_final_pair_calibration.py', 'harness/zone_final_pair_excitation.py',
                     clearance.CLEARANCE_REVIEW):
            assert bundle['source_sha256'][path] == c.base.sha(c.ROOT/path)
        planned = wm.plan(c.ROOT, heldout.WORKFLOW_ID, [
            '--check', heldout.CHECK, '--map-id', map_id, '--expected-source-sha', 'a'*40])
        assert planned['command'][1:3] == ['-m', 'scripts.run_final_pair_heldout']
        assert not planned['execution_started']


@pytest.mark.parametrize('map_id', heldout.MAPS)
def test_v88_entry_and_direct_backend_still_reject_heldout(tmp_path, map_id):
    from sim.final_pair_v3 import PhysicsBackend
    with pytest.raises(ValueError, match='two-door'):
        legacy_run.main(args(tmp_path, map_id))
    with pytest.raises(ValueError):
        legacy_run.run_case(case_bundle(map_id), tmp_path/'old-case', seed=911,
                            backend_factory=lambda *a, **kw: pytest.fail('backend reached'))
    with pytest.raises(ValueError):
        PhysicsBackend(case_bundle(map_id), tmp_path/'old-backend', seed=911)
    assert not (tmp_path/'out').exists()
    assert not (tmp_path/'old-case').exists()
    assert not (tmp_path/'old-backend').exists()


@pytest.mark.parametrize('key,bad', [('collection_role', 'TRAINING'),
                                   ('training_eligible', True), ('teacher_only', False)])
def test_role_drift_in_code_and_registry_is_detected(tmp_path, capsys, monkeypatch, key, bad):
    original_read = c.base.read
    monkeypatch.setattr(heldout, 'ROLE', {**heldout.ROLE, key: bad})
    def changed_registry(path):
        value = original_read(path)
        return {**value, key: bad} if path == c.ROOT/heldout.REGISTRY else value
    monkeypatch.setattr(c.base, 'read', changed_registry)
    with pytest.raises(AssertionError):
        test_check_only_plans_admit_only_new_heldout_without_backend(
            tmp_path, capsys, monkeypatch, heldout.MAPS[0], managed.main)


@pytest.mark.parametrize('map_id', heldout.MAPS)
def test_dedicated_backend_admits_heldout_and_cleans_failed_construction(tmp_path, monkeypatch, map_id):
    from sim import final_pair_heldout as backend
    from sim import zone_final_v3_scene
    seen, closed = [], []
    def refuse_native_world(scene, profile, **kwargs):
        seen.append((scene.config['static_map'], profile, kwargs['seed']))
        raise RuntimeError('test stopped before native world construction')
    monkeypatch.setattr(zone_final_v3_scene, 'build_world', refuse_native_world)
    monkeypatch.setattr(backend.PhysicsBackend, 'close', lambda self: closed.append(self.bundle))
    bundle = case_bundle(map_id)
    with pytest.raises(RuntimeError, match='before native world construction'):
        backend.PhysicsBackend(bundle, tmp_path/'unused', seed=911)
    assert seen == [(c.resolve(map_id)[0], 'cargo_noslip_v1', 911)]
    assert closed == [bundle]
    assert backend.PhysicsBackend.collection_guard is backend.V88Backend.collection_guard
