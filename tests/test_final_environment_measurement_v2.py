"""Offline design, fake acquisition and abort tests. Never run native physics."""
import copy
import json
import socket
import sys
from types import SimpleNamespace

import numpy as np
import pytest

from harness import final_environment_measurement_v2 as env
from scripts import run_final_environment_measurement_v2 as run
from scripts import check_measurement_v2_identifiability as ident
from sim import workflow_manager as wm
from tests.test_zone_final_environment_runnable import FakePhysics


@pytest.fixture(autouse=True)
def offline_only(monkeypatch):
    for module in ('mujoco', 'torch', 'torchvision', 'sim.multi_masterpi_production'):
        monkeypatch.setitem(sys.modules, module, None)
    monkeypatch.setattr(socket.socket, 'connect', lambda *a: pytest.fail('network forbidden'))
    from harness.vision_loc_client import VisionWorkerClient
    monkeypatch.setattr(VisionWorkerClient, '__init__', lambda *a, **k: pytest.fail('worker forbidden'))


@pytest.fixture(scope='module')
def bundle():
    return env.bundle()


def test_v1_and_all_v87_pinned_sources_and_nine_bundles_preserved():
    record = env.read(env.ROOT / 'experiments/2026-10-01-final-env-measurement-v2/v87_preservation.json')
    for path, sha in record['files_sha256'].items():
        assert env.sha(env.ROOT / path) == sha, path
    for key, sha in record['bundles'].items():
        mid, check = key.split('/')
        assert env.digest(env.parent.bundle(mid, check=check)) == sha, key


def test_single_most_free_map_caps_excitation_and_sampling(bundle):
    plan = bundle['measurement']
    receipt = env.validate(plan)
    assert receipt['free_floor_area_m2'][env.MAP_ID] == pytest.approx(28.9675)
    assert receipt['spawn_wall_clearance_m'] == pytest.approx(.675)
    assert receipt['pose_samples_including_initial'] == 4601
    assert bundle['execution_bundle_id'] == 'zone-final-environment-v89'
    assert bundle['caps']['cases'] == 1 and bundle['caps']['total_including_reset_cap_s'] == 235
    assert bundle['controller_inputs'] == [] and not bundle['physical_ready']
    assert env.CONFIG in bundle['source_sha256']
    for axis in plan['axes']:
        rows = [s for s in plan['segments'] if s['axis'] == axis and s['phase'] == 'step']
        assert sorted(s['value'] for s in rows) == [-.03, -.02, -.01, .01, .02, .03]
        assert all(s['duration_s'] >= 5 * plan['max_design_drive_tau_s'] for s in rows)
        assert plan['design_drive_tau_s'][axis] / plan['eval_pose_period_s'] >= 10
    assert set(ident.prbs31()) == {-1, 1}
    cyclic = ident.prbs31() * 2
    assert len({tuple(cyclic[i:i + 5]) for i in range(31)}) == 31


@pytest.mark.parametrize('key,value', [('sim_cap_s', 241), ('reset_cap_s', 6),
    ('eval_pose_period_s', .2), ('command_lease_s', 2), ('robot_id', 'r2'),
    ('load_state', 'loaded'), ('spawn_xy_yaw', [2.2, -.85, 0]), ('map_id', 'unknown')])
def test_bad_contract_fails_before_backend(key, value, bundle, tmp_path):
    candidate = copy.deepcopy(bundle)
    candidate['measurement'][key] = value
    with pytest.raises(ValueError, match='contract changed'):
        run.run_case(candidate, tmp_path / 'out', seed=911,
                     backend_factory=lambda *a, **k: pytest.fail('backend forbidden'))
    assert not (tmp_path / 'out').exists()


@pytest.mark.parametrize('mutation', ['large_command', 'missing_sign', 'short_steps', 'pan', 'missing_prbs'])
def test_excitation_mutation_rejected(mutation):
    plan = env.protocol()
    if mutation == 'large_command':
        plan['segments'][0]['value'] = .5
    elif mutation == 'missing_sign':
        plan['segments'][2]['value'] = .01
    elif mutation == 'short_steps':
        plan['segments'][0]['duration_s'] = .25
    elif mutation == 'pan':
        plan['segments'][0]['axis'] = 'pan'
    else:
        plan['prbs']['bits'].pop()
    with pytest.raises(ValueError):
        env.validate(plan)


def test_clearance_uses_wall_faces_footprint_bounds_and_invalid_data():
    static = env.parent.resolve(env.MAP_ID)[0]
    plan = env.protocol()
    # Divider face x=2.225, not its centre x=2.2. Radius is subtracted.
    assert env.clearance(static, (3.25, -.85), .35) == pytest.approx(.675)
    for xy in [(2.2, -.85), (2.9, -.85), (5.5, -.85), (float('nan'), 0.)]:
        with pytest.raises(ValueError):
            env.require_clearance(static, xy, plan)
    wrong = copy.deepcopy(static)
    wrong['obstacles'][0]['yaw_rad'] = .1
    with pytest.raises(ValueError, match='unsupported'):
        env.require_clearance(wrong, (3.25, -.85), plan)
    wrong = copy.deepcopy(static)
    wrong['obstacles'] = []
    with pytest.raises(ValueError, match='missing'):
        env.free_floor_area(wrong)


def test_wall_union_area_does_not_double_count_overlap():
    static = {'bounds_m': [0, 4, 0, 4], 'obstacles': [
        {'kind': 'wall', 'center_m': [1, 1], 'half_extents_m': [1, 1]},
        {'kind': 'wall', 'center_m': [2, 2], 'half_extents_m': [1, 1]}]}
    assert env.free_floor_area(static) == 9  # 16 - (4+4-1)


def test_v1_practical_ambiguity_and_v2_profiled_grid_separation():
    report = ident.report(env.protocol())
    assert report['passed']
    assert report['nominal_clearance']['minimum_m'] >= .35
    for axis in ('forward', 'left'):
        before, after = report['v1'][axis], report['v2'][axis]
        assert before['profiled_20pct_tau_alternative']['rms_m'] < ident.RESIDUAL_FLOOR_M
        assert after['profiled_20pct_tau_alternative']['rms_m'] > 5 * ident.RESIDUAL_FLOOR_M
        assert after['fisher_condition'] < before['fisher_condition'] / 10
    # A second known first-order plant prevents a check that only parrots the
    # report's constants. Removing long steps should destroy this separation.
    x = ident.assess(ident.design_segments(), .05, 2., 2., .08)
    assert x['practically_separated']
    degraded = ident.assess([(1., .03), (3., 0.), (1., -.03), (3., 0.)], .2, 2., 2., .08)
    assert not degraded['practically_separated']


def test_fake_schedule_exact_cap_no_eval_feedback_and_no_pan(bundle, tmp_path):
    owned = []
    class Backend(FakePhysics):
        def __init__(self, *a, **k):
            super().__init__(*a, **k)
            owned.append(self)
    result = run.run_case(bundle, tmp_path / 'run', seed=911, backend_factory=Backend)
    backend = owned[0]
    assert result['status'] == 'COLLECTED_UNQUALIFIED' and result['physical_success'] is None
    assert result['check_sim_s'] == 230 and result['reset_sim_s'] == 1
    assert backend.closed and len(backend.samples) == 4601 and len(backend.actions) == 4600
    assert np.diff(backend.samples) == pytest.approx(np.full(4600, .05))
    assert backend.frames[0] == 1 and backend.frames[-1] == 231 and len(backend.frames) == 47
    for i, (t, rid, action) in enumerate(backend.actions):
        assert rid == 'r1' and t == pytest.approx(1 + i * .05)
        assert action == env.action_at(bundle['measurement'], i)
        assert action['duration_s'] == .05 and action['turn'] == 0
    with pytest.raises(FileExistsError):
        run.run_case(bundle, tmp_path / 'run', seed=911, backend_factory=Backend)


@pytest.mark.parametrize('failure', ['reset_cap', 'wall', 'disk', 'clock'])
def test_failure_aborts_stops_and_preserves_failed_denominator(bundle, tmp_path, failure):
    owned = []
    class Backend(FakePhysics):
        def __init__(self, *a, **k):
            super().__init__(*a, **k)
            owned.append(self)
        def reset(self, cap):
            self.now = 6 if failure == 'reset_cap' else 1
            return self.now
        def advance_to(self, now):
            if failure == 'wall':
                raise ValueError('CLEARANCE_ABORT')
            super().advance_to(now + (.001 if failure == 'clock' else 0))
        def capture(self):
            if failure == 'disk':
                raise OSError(28, 'full')
            super().capture()
    result = run.run_case(bundle, tmp_path / 'bad', seed=911, backend_factory=Backend)
    assert result['status'] == 'HOST_ERROR' and not result['protocol_complete']
    assert owned[0].closed and len(owned[0].actions) <= 1
    assert result['failure']['class'] == ('ENOSPC' if failure == 'disk' else 'HOST_ERROR')


def test_workflow_new_check_plan_and_ci_registration(capsys, tmp_path):
    from scripts.run_ci_tests import collect_test_files, TEST_PATTERNS
    assert collect_test_files(env.ROOT, TEST_PATTERNS).count('tests/test_final_environment_measurement_v2.py') == 1
    row, _ = wm._row(env.ROOT, env.WORKFLOW_ID)
    assert row['version'] == '2.21.0'
    planned = wm.plan(env.ROOT, env.WORKFLOW_ID, ['--check', env.CHECK, '--expected-source-sha', 'a' * 40])
    assert not planned['execution_started']
    assert planned['command'][1:3] == ['-m', 'scripts.run_final_environment_measurement_v2']
    run.main(['--check', env.CHECK, '--expected-source-sha', 'a' * 40, '--output', str(tmp_path / 'raw')])
    value = json.loads(capsys.readouterr().out)
    assert not value['execution_started'] and value['caps']['total_including_reset_cap_s'] == 235
    assert not (tmp_path / 'raw').exists()


def test_wrong_source_refused_before_physics(monkeypatch, tmp_path):
    def refuse(sha):
        raise ValueError('expected source SHA differs from HEAD')
    monkeypatch.setattr(run, 'check_source', refuse)
    monkeypatch.setitem(sys.modules, 'sim.final_environment_measurement_v2', None)
    with pytest.raises(ValueError, match='source SHA'):
        run.main(['--check', env.CHECK, '--expected-source-sha', 'a' * 40,
                  '--output', str(tmp_path / 'raw'), '--execute', '--lock-owner', 'claude'])
    assert not (tmp_path / 'raw').exists()


@pytest.mark.parametrize('lock_valid', [False, True])
def test_managed_cli_owned_lock_receipt_and_no_overwrite(monkeypatch, tmp_path, lock_valid):
    from scripts import agent_lock
    from sim import final_environment_measurement_v2 as physics
    monkeypatch.setattr(run, 'check_source', lambda sha: sha)
    def git(argv, **kwargs):
        if argv == ['git', 'rev-parse', '--path-format=absolute', '--git-common-dir']:
            return str(tmp_path / '.git')
        if argv == ['git', 'branch', '--show-current']:
            return 'claude/measurement-v89'
        pytest.fail(str(argv))
    monkeypatch.setattr(run.subprocess, 'check_output', git)
    monkeypatch.setattr(run.shutil, 'disk_usage', lambda p: SimpleNamespace(free=20 * 1024 ** 3))
    monkeypatch.setattr(agent_lock, 'status', lambda p: {'pid_alive': lock_valid,
        'owner': 'claude', 'branch': 'claude/measurement-v89'})
    monkeypatch.setattr(physics, 'PhysicsBackend', FakePhysics)
    out = tmp_path / 'outputs/new'
    argv = ['--check', env.CHECK, '--expected-source-sha', 'a' * 40,
            '--output', str(out), '--execute', '--lock-owner', 'claude']
    if not lock_valid:
        with pytest.raises(ValueError, match='owned host lock'):
            run.main(argv)
        assert not out.exists()
        return
    assert run.main(argv) == 0
    result = env.read(out / 'result.json')
    assert result['denominator'] == 1 and result['source_unchanged'] and result['physical_success'] is None
    with pytest.raises(FileExistsError):
        run.main(argv)


def test_scene_uses_authored_reset_and_keeps_static_map_and_other_robots():
    from sim.final_environment_measurement_v2 import MeasurementScene
    from sim.zone_final_v3_scene import FinalV3Scene
    from sim.zone_arena import DEFAULT_GOAL
    spec = {'map': env.MAP_ID, 'seed': 911, 'goal': DEFAULT_GOAL, 'extra_boxes': {}, 'team_cargo': []}
    previous = FinalV3Scene.from_spec(spec, 'local_contact_fine')
    new = MeasurementScene.from_spec(spec, 'local_contact_fine')
    assert new.config['static_map'] == previous.config['static_map']
    assert new.config['setup_only']['objects'] == previous.config['setup_only']['objects']
    for rid in ('r2', 'r3'):
        assert new.config['setup_only']['spawns'][rid] == previous.config['setup_only']['spawns'][rid]
    x, y, z, yaw = new.config['setup_only']['spawns']['r1']
    assert [x, y, yaw] == env.protocol()['spawn_xy_yaw']
    assert z == previous.config['setup_only']['spawns']['r1'][2]


def fake_native_owner(tmp_path, monkeypatch):
    from sim.final_environment_measurement_v2 import PhysicsBackend
    backend = PhysicsBackend.__new__(PhysicsBackend)
    backend.out, backend.plan = tmp_path, env.protocol()
    backend.bundle = {'map_sha256': env.parent.digest(env.parent.resolve(env.MAP_ID)[0])}
    backend.streams, backend._last_guard_xy, backend.pose_sample_index = {}, None, 0
    backend.scene = SimpleNamespace(config={'static_map': env.parent.resolve(env.MAP_ID)[0]})
    base = SimpleNamespace(xpos=np.array([3.25, -.85, .032]), xmat=np.eye(3).ravel())
    model = SimpleNamespace(ngeom=1, geom_rbound=np.array([.1]), neq=0, eq_type=[])
    data = SimpleNamespace(time=0., body=lambda name: base, geom_xpos=np.array([[3.25, -.85, .032]]),
                           ncon=0, contact=[], eq_active=[])
    backend.world = SimpleNamespace(model=model, data=data, close=lambda: None, robot=lambda rid: rid)
    held = []
    backend.ports = {'r1': SimpleNamespace(hold=lambda now: held.append(now), tick=lambda now: None)}
    monkeypatch.setitem(sys.modules, 'mujoco', SimpleNamespace(mjtObj=SimpleNamespace(mjOBJ_GEOM=1),
        mj_id2name=lambda *a: 'r1__chassis', mjtEq=SimpleNamespace(mjEQ_WELD=1)))
    return backend, base, held


@pytest.mark.parametrize('failure', ['wall', 'nan', 'envelope', 'jump'])
def test_private_guard_holds_and_never_corrects_or_continues(tmp_path, monkeypatch, failure):
    backend, base, held = fake_native_owner(tmp_path, monkeypatch)
    backend.guard(check_geometry=True)
    if failure == 'wall':
        base.xpos[0] = 2.9
    elif failure == 'nan':
        base.xpos[0] = np.nan
    elif failure == 'envelope':
        backend.world.model.geom_rbound[0] = .6
    else:
        base.xpos[0] += .02
    with pytest.raises(ValueError):
        backend.guard(check_geometry=True)
    assert held and backend.world.data.time == 0.
    backend.close()
    failure_row = json.loads((tmp_path / 'eval_only/clearance_abort.jsonl').read_text())
    assert failure_row['reason']
    if failure == 'nan':
        assert failure_row['base_xy_m'][0] is None


def test_eval_pose_is_separate_from_camera_and_guard_checks_each_substep(tmp_path, monkeypatch):
    backend, base, held = fake_native_owner(tmp_path, monkeypatch)
    backend.eval_sample()
    backend.dt, backend.deadline = .025, .05
    steps = []
    def step(rid):
        steps.append(rid)
        backend.world.data.time += .025
    backend.world._physics_step_for = step
    backend.advance_to(.05)
    backend.eval_sample()
    backend.close()
    rows = [json.loads(s) for s in (tmp_path / 'eval_only/r1/pose.jsonl').read_text().splitlines()]
    assert [r['t'] for r in rows] == [0., .05] and [r['sample_index'] for r in rows] == [0, 1]
    assert len(steps) == 2 and not (tmp_path / 'robots/r1/rgb').exists()
