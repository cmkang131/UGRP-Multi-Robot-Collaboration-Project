"""v84 fake/offline admission and acquisition tests; no physics or inference."""
import copy
import json
import socket
import sys
from pathlib import Path

import numpy as np
import pytest

from harness import zone_final_environment as env
from scripts import run_final_environment_checks as run
from sim import workflow_manager as wm

MAPS = tuple(env.registry()['maps'])


@pytest.fixture(autouse=True)
def offline_only(monkeypatch):
    for module in ('mujoco', 'torch', 'torchvision', 'sim.multi_masterpi_production'):
        monkeypatch.setitem(sys.modules, module, None)
    monkeypatch.setattr(socket.socket, 'connect', lambda *a: pytest.fail('network forbidden'))
    from harness.vision_loc_client import VisionWorkerClient
    monkeypatch.setattr(VisionWorkerClient, '__init__', lambda *a, **k: pytest.fail('real worker forbidden'))


@pytest.mark.parametrize('map_id', MAPS)
def test_registered_maps_resolve_and_new_bundle_is_runnable_without_sealing(map_id):
    static, row, cal = env.resolve(map_id)
    assert static['robot_model'] == 'masterpi_v3'
    assert static['wall_profile']['height_m'] == .4
    assert 'landmarks' not in static
    assert env.provider_spec(map_id)['maps'] == list(MAPS)
    assert env.provider_spec(map_id)['provider_id'] == env.PROVIDER_ID
    b = env.bundle(map_id)
    assert b['execution_bundle_id'] == 'zone-final-environment-v84'
    assert b['runnable'] is True and b['status'] == 'DRAFT_UNSEALED'
    assert b['research_result'] is False and b['physical_ready'] is False
    assert cal['status'] == 'DRAFT_UNMEASURED' and cal['measurements'] is None
    assert cal['camera']['sag'] is None and all(v is None for v in cal['motion'].values())
    assert {row['file'], row['parent_file'], row['calibration_contract'], env.REGISTRY, env.WORKFLOW,
            'harness/vision_pose_source_p03.py', 'harness/zone_study_pose_delay_p03.py',
            'sim/zone_final_v3_scene.py', 'sim/final_environment_checks.py',
            'experiments/2026-09-26-vision-loc/vision_loc.py'} <= set(b['source_sha256'])


@pytest.mark.parametrize('map_id', ['../zone_wide_door_final_v3', 'zone_wide_door_geometry_v2', 'missing'])
def test_provider_allowlist_refuses_other_maps(map_id):
    with pytest.raises(ValueError, match='allow-listed'):
        env.provider_spec(map_id)


def copied_contract(tmp_path):
    b = env.bundle(MAPS[0])
    for rel in b['source_sha256']:
        p = tmp_path / rel
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_bytes((env.ROOT / rel).read_bytes())
    return tmp_path


@pytest.mark.parametrize('field', ['file', 'parent_file', 'calibration_contract'])
def test_changed_map_parent_or_calibration_contract_is_refused(tmp_path, field):
    root = copied_contract(tmp_path)
    row = env.registry(root=root)['maps'][MAPS[0]]
    path = root / row[field]
    path.write_bytes(path.read_bytes() + b'\n')
    with pytest.raises(ValueError, match='hash mismatch'):
        env.resolve(MAPS[0], root=root)


def test_wrong_v2_robot_cannot_pass_even_with_recomputed_file_hash(tmp_path):
    root = copied_contract(tmp_path)
    reg = env.registry(root=root)
    row = reg['maps'][MAPS[0]]
    path = root / row['file']
    value = env.read(path)
    value['robot_model'] = 'masterpi_v2'
    run.write(path, value)
    row.update(sha256=env.sha(path), static_map_sha256=env.digest(value))
    run.write(root / env.REGISTRY, reg)
    with pytest.raises(ValueError, match='identity mismatch'):
        env.resolve(MAPS[0], root=root)


def test_missing_measurements_never_fall_back_to_v2(tmp_path):
    with pytest.raises(ValueError, match='MEASURED_V3_CALIBRATION_REQUIRED'):
        env.measured_calibration(None, None, MAPS[0])
    old = env.ROOT / 'experiments/2026-09-26-zone-m1-owncam/calibration_m1_dev.json'
    with pytest.raises(ValueError, match='combination mismatch'):
        env.measured_calibration(old, env.sha(old), MAPS[0])


def test_workflow_is_discoverable_and_plan_does_not_execute():
    row, _ = wm._row(env.ROOT, 'zone-final-environment-check')
    assert row['version'] == '2.17.0'
    plan = wm.plan(env.ROOT, row['id'], ['--check', 'p01', '--expected-source-sha', 'a' * 40])
    assert plan['execution_started'] is False
    assert plan['command'][1:3] == ['-m', 'scripts.run_final_environment_checks']
    assert plan['output'] == '<record>/artifacts'
    # Existing workflow definitions remain exactly the rows in the pinned file.
    old = env.read(env.ROOT / wm.CATALOG)
    combined, _ = wm.catalog(env.ROOT)
    assert combined['workflows'][:len(old['workflows'])] == old['workflows']


def test_catalog_fragment_cannot_override_an_existing_id(tmp_path):
    (tmp_path / 'configs/simulation_workflows.d').mkdir(parents=True)
    (tmp_path / 'runner.py').write_text('')
    row = {'id': 'one', 'version': '1', 'entry': 'runner.py', 'runner': 'runner',
           'output_flag': '--out', 'output_kind': 'directory', 'required_inputs': [], 'side_effect': 'test'}
    catalog = {'schema': 'ugrp.local_workflow_catalog.v1', 'workflows': [row]}
    run.write(tmp_path / wm.CATALOG, catalog)
    original_hash = env.sha(tmp_path / wm.CATALOG)
    assert wm.catalog(tmp_path)[1] == original_hash
    run.write(tmp_path / 'configs/simulation_workflows.d/duplicate.json', catalog)
    with pytest.raises(ValueError, match='distinct'):
        wm.catalog(tmp_path)
    catalog['workflows'][0]['id'] = 'two'
    run.write(tmp_path / 'configs/simulation_workflows.d/duplicate.json', catalog)
    assert wm.catalog(tmp_path)[1] != original_hash
    assert env.sha(tmp_path / wm.CATALOG) == original_hash


class FakePhysics:
    def __init__(self, bundle, out, *, seed):
        self.bundle, self.seed = bundle, seed
        self.now, self.deadline, self.closed = 0., None, False
        self.actions, self.frames, self.samples = [], [], []

    def reset(self, cap):
        assert cap == 5.
        self.now = 1.
        return self.now

    def set_deadline(self, deadline):
        self.deadline = deadline

    def advance_to(self, now):
        assert self.now <= now <= self.deadline
        self.now = now

    def issue(self, rid, action):
        self.actions.append((self.now, rid, copy.deepcopy(action)))

    def capture(self):
        self.frames.append(self.now)

    def eval_sample(self):
        self.samples.append(self.now)
        # Return deliberately tempting truth: the schedule MUST ignore it.
        return {'pose_gt': [-999, 999, 999], 'success': True, 'partner_private_state': 'go'}

    def close(self):
        self.closed = True


@pytest.mark.parametrize('check,cap', [('p01', 30.), ('calibration', 120.)])
def test_fake_acquisition_exact_caps_commands_and_cleanup(tmp_path, check, cap):
    b = env.bundle(MAPS[0], check=check)
    owned = []
    def factory(*args, **kw):
        owned.append(FakePhysics(*args, **kw))
        return owned[-1]
    result = run.run_case(b, tmp_path / check, seed=911, backend_factory=factory)
    backend = owned[0]
    assert result['protocol_complete'] and result['status'] == 'COLLECTED_UNQUALIFIED'
    assert result['physical_success'] is None and result['research_result'] is False
    assert result['reset_sim_s'] == 1. and result['check_sim_s'] == cap
    assert backend.now == backend.deadline == 1. + cap and backend.closed
    assert backend.frames[0] == 1. and backend.frames[-1] == 1. + cap
    assert len(backend.samples) == int(cap / .05) + 1
    if check == 'p01':
        assert backend.actions == []
    else:
        protocol = env.read(env.ROOT / 'configs/final_environment_measurement_v1.json')
        expected = [(e['t'] + 1., 'r1', a) for e in protocol['events'] for a in e['actions']]
        assert backend.actions == expected
    hashes = env.read(tmp_path / check / 'artifacts.sha256.json')
    assert hashes['result.json'] == env.sha(tmp_path / check / 'result.json')


def test_invalid_cap_is_rejected_before_backend(tmp_path):
    b = env.bundle(MAPS[0])
    b['caps']['per_case_sim_cap_s'] = 31.
    with pytest.raises(ValueError, match='SIM cap'):
        run.run_case(b, tmp_path / 'bad', seed=1, backend_factory=lambda *a, **k: pytest.fail('factory'))


def test_frame_failure_retains_host_error_and_closes_owned_world(tmp_path):
    class Broken(FakePhysics):
        def capture(self):
            raise OSError(28, 'synthetic disk full')
    backend = Broken({}, tmp_path, seed=1)
    result = run.run_case(env.bundle(MAPS[0]), tmp_path / 'failed', seed=1,
                          backend_factory=lambda *a, **kw: backend)
    assert result['status'] == 'HOST_ERROR' and not result['protocol_complete']
    assert result['failure']['class'] == 'ENOSPC'
    assert backend.closed and result['physical_success'] is None
    assert env.read(tmp_path / 'failed/result.json') == result


def test_real_backend_advance_rejects_deadline_with_fake_world():
    from types import SimpleNamespace
    from sim.final_environment_checks import PhysicsBackend
    backend = PhysicsBackend.__new__(PhysicsBackend)
    backend.dt, backend.deadline, backend.ports = .01, .05, {}
    world = SimpleNamespace(data=SimpleNamespace(time=0.), robot=lambda rid: rid)
    def step(rid):
        assert rid == 'r1'
        world.data.time += .01
    world._physics_step_for = step
    backend.world = world
    backend.advance_to(.05)
    assert backend.now == pytest.approx(.05)
    with pytest.raises(ValueError, match='deadline'):
        backend.advance_to(.06)
    assert backend.now == pytest.approx(.05)


def test_world_step_cap_covers_constructor_and_can_advance_to_check_deadline():
    from types import SimpleNamespace
    from sim.zone_final_v3_scene import cap_world_steps
    world = SimpleNamespace(data=SimpleNamespace(time=0.), model=SimpleNamespace(opt=SimpleNamespace(timestep=.01)))
    world._physics_step_for = lambda: setattr(world.data, 'time', world.data.time + .01)
    cap_world_steps(world, .02)
    world._physics_step_for()
    world._physics_step_for()
    with pytest.raises(RuntimeError, match='SIM_CAP_EXCEEDED'):
        world._physics_step_for()
    assert world.data.time == .02
    world._final_environment_deadline = .03
    world._physics_step_for()
    assert world.data.time == .03


def test_p03_plan_is_honest_about_missing_calibration_and_chain(capsys, tmp_path):
    assert run.main(['--check', 'p03', '--expected-source-sha', 'a' * 40,
                     '--output', str(tmp_path / 'not-created')]) == 0
    plan = json.loads(capsys.readouterr().out)
    assert plan['runnable'] is False and not plan['execution_started']
    assert plan['caps']['total_sim_cap_s'] == 360
    assert plan['blocked_on'] == ['measured_final_v3_calibration', 'qualified_final_v3_pair_chain_adapter']
    assert not (tmp_path / 'not-created').exists()


def test_final_scene_uses_standard_resolver_and_v3_spawn_hook(monkeypatch):
    from sim.zone_final_v3_scene import FinalV3Scene, CargoZoneScene
    from sim import zone_final_v3_scene as scene_module
    scene = FinalV3Scene.__new__(FinalV3Scene)
    scene.selection = 'zones/' + MAPS[1]
    scene.cargo, scene.config, scene.inventory = (), {}, []
    calls = []
    def base(self):
        parent = env.resolve(MAPS[1])[0]['base_map']['map_id']
        assert self.selection == 'zones/' + parent
        self.config = {'static_map': env.read(env.ROOT / 'maps/zones' / (parent + '.json')),
                       'setup_only': {'objects': {}, 'spawns': {}}}
        calls.append('base')
    monkeypatch.setattr(CargoZoneScene, '_resolve', base)
    monkeypatch.setattr(scene_module, 'apply_spawn_layout', lambda config: calls.append('v3_spawn'))
    scene._read = lambda path: calls.append(str(path))
    scene._verify_camera = lambda: calls.append('camera')
    scene._resolve()
    assert scene.config['robot_model'] == 'masterpi_v3'
    assert scene.config['static_map'] == env.resolve(MAPS[1])[0]
    assert calls[0:2] == ['base', 'v3_spawn'] and calls[-1] == 'camera'


@pytest.mark.parametrize('map_id', MAPS)
def test_actual_static_scene_resolution_needs_no_physics(map_id):
    from sim.zone_final_v3_scene import FinalV3Scene
    from sim.zone_arena import DEFAULT_GOAL
    scene = FinalV3Scene.from_spec({'map': map_id, 'seed': 911, 'goal': DEFAULT_GOAL}, 'local_contact_fine')
    assert scene.config['static_map'] == env.resolve(map_id)[0]
    assert scene.config['robot_model'] == 'masterpi_v3'
    assert len(scene.config['setup_only']['spawns']) == 3
    assert scene.config['station_convention']['arm_mount_x_m'] > 0.


def test_world_factory_applies_final_scene_contact_and_v3_robot_hooks(monkeypatch):
    from types import SimpleNamespace
    from sim.zone_final_v3_scene import FinalV3Scene, build_world
    from sim import zone_cargo_contact
    scene = FinalV3Scene.__new__(FinalV3Scene)
    scene.selection = 'zones/' + MAPS[0]
    scene.config = {'static_map': env.resolve(MAPS[0])[0], 'robot_model': 'masterpi_v3'}
    calls = []
    scene.transform = lambda xml: calls.append('scene') or xml + '|scene'
    def robot_transform(xml, **kwargs):
        calls.append(('v3_robot', kwargs))
        return xml + '|v3'
    scene.robot_transform = robot_transform
    monkeypatch.setattr(zone_cargo_contact, 'apply', lambda xml, profile: calls.append(profile) or xml + '|contact')
    def hardware(values):
        assert values == {}  # uncalibrated v2 wheelbase/track must be removed
        return {'wheelbase_m': 111, 'track_m': 222, 'v3_marker': True}
    monkeypatch.setitem(sys.modules, 'sim.masterpi_model_v3', SimpleNamespace(v3_hardware=hardware))
    class FakeWorld:
        def _physics_step_for(self):
            self.data.time += .01
        def __init__(self, *, xml_transform, **kwargs):
            self.data = SimpleNamespace(time=0.)
            self.model = SimpleNamespace(opt=SimpleNamespace(timestep=.01))
            self.physical_params = {'wheelbase_m': 999, 'track_m': 888}
            self.calibration_parameters = ()
            self.xml = xml_transform('raw')
            # The cap is already installed during this constructor reset.
            assert self._final_environment_deadline == 5.
            self._physics_step_for()
    monkeypatch.setitem(sys.modules, 'sim.multi_masterpi_production',
                        SimpleNamespace(MultiMasterPiProductionV2=FakeWorld))
    world = build_world(scene, 'cargo_noslip_v1')
    assert world.xml == 'raw|scene|contact|v3'
    assert calls[:2] == ['scene', 'cargo_noslip_v1']
    assert calls[2][0] == 'v3_robot'
    assert world.physical_params == {'wheelbase_m': 111, 'track_m': 222, 'v3_marker': True}


def synthetic_measurement(tmp_path):
    """TEST ONLY: not a measured asset and never installed in the registry."""
    from tests.test_vision_pose_source import CALIB
    _, row, contract = env.resolve(MAPS[0])
    rec = {'origin_m': [.15, 0., .2], 'rotation': [[0., 0., 1.], [-1., 0., 0.], [0., -1., 0.]]}
    value = {'schema': 'ugrp.final_environment_measured_calibration.v1', 'status': 'MEASURED_SIM',
             'contract_sha256': row['calibration_contract_sha256'], 'maps': contract['maps'],
             'robot_model': 'masterpi_v3', 'render_profile': 'default',
             'source_sha': 'a' * 40, 'measurement_manifest_sha256': 'b' * 64,
             'params': copy.deepcopy(CALIB['params']), 'pan_base_yaw': {'loaded': 0., 'unloaded': 0.},
             'camera_models': {state: {'740,2320,1320,1500': rec} for state in ('loaded', 'unloaded')}}
    path = tmp_path / 'SYNTHETIC-TEST-ONLY.json'
    run.write(path, value)
    return path, value


def test_final_provider_reuses_p03_lifecycle_and_exactly_one_delay(tmp_path):
    from harness.vision_pose_source_final import build_provider
    from harness.vision_loc_client import InProcessWorker
    from tests.test_vision_pose_source import SEARCH_POSE
    path, cal = synthetic_measurement(tmp_path)
    worker = InProcessWorker(lambda *a: pytest.fail('no frame inference in this lifecycle test'))
    delayed = build_provider(env.resolve(MAPS[0])[0], cal['params'], 911,
                             calibration=path, calibration_sha256=env.sha(path), worker=worker)
    try:
        delayed.init_prior([-.8, -.85, 0], source='synthetic authored own dock')
        delayed.on_command({'t': 0., 'kind': 'initial_servo_command', 'pulses': SEARCH_POSE})
        delayed.report(.2)
        pf = delayed.provider.loc._pf
        particles = pf.px.copy()
        delayed.begin_relocalization(.2, SEARCH_POSE)
        assert delayed.provider.loc._pf is pf
        np.testing.assert_array_equal(pf.px, particles)
        assert delayed.delay['wrapper_count'] == 1 and delayed.delay['effective_sim_s'] == .16
        with pytest.raises(RuntimeError, match='prior'):
            delayed.init_prior([0, 0, 0], source='forbidden late GT')
        cm = pf.column_model_for(SEARCH_POSE)
        np.testing.assert_array_equal(cm.origin, [.15, 0, .2])
        with pytest.raises(ValueError, match='UNMEASURED_V3_CAMERA_POSTURE'):
            pf.column_model_for({**SEARCH_POSE, 6: 700})
    finally:
        delayed.close()
    assert delayed.provider._closed


def test_measurement_hash_gate_precedes_worker_or_pf(tmp_path):
    from harness.vision_pose_source_final import FinalVisionPoseSource
    path, cal = synthetic_measurement(tmp_path)
    with pytest.raises(ValueError, match='hash mismatch'):
        FinalVisionPoseSource(env.resolve(MAPS[0])[0], cal['params'], calibration=path,
                              calibration_sha256='0' * 64)


def test_final_provider_only_consumes_own_rgb_after_delay_and_uses_fixed_v3_camera(tmp_path):
    from harness import vision_loc_protocol as vp
    from harness.vision_pose_source_final import build_provider
    from harness.vision_loc_client import InProcessWorker
    from tests.test_vision_pose_source import SEARCH_POSE, FRAME, _reply
    path, cal = synthetic_measurement(tmp_path)
    obs = vp.check_reply(_reply(), seq=0, bgr_sha256='a' * 64, n_columns=len(vp.columns()))[1]
    calls = []
    def inference(seq, own_bgr):
        np.testing.assert_array_equal(own_bgr, FRAME[..., ::-1])
        calls.append(seq)
        return copy.deepcopy(obs)
    delayed = build_provider(env.resolve(MAPS[0])[0], cal['params'], 911,
                             calibration=path, calibration_sha256=env.sha(path),
                             worker=InProcessWorker(inference))
    try:
        delayed.init_prior([-.8, -.85, 0.], source='synthetic static own dock')
        delayed.on_command({'t': 0., 'kind': 'initial_servo_command', 'pulses': SEARCH_POSE})
        delayed.on_frame(.4, FRAME)
        delayed.report(.55)
        assert calls == []
        delayed.report(.57)
        assert calls == [0]
        assert delayed.provider.loc._pf.last_scan_t == .4
        timing = delayed.timing[-1]
        assert timing['available_sim_s'] == pytest.approx(.56)
        delayed.on_frame(.6, FRAME, captured_sim_s=.4)  # duplicate cannot become another fix
        delayed.report(.8)
        assert calls == [0]
        delayed.on_command({'t': .9, 'kind': 'look', 'pan_pulse': 700})
        delayed.on_frame(1.4, FRAME)
        assert delayed.report(1.57).initialized is False
        assert 'UNMEASURED_V3_CAMERA_POSTURE' in delayed.provider.failure['reason']
        count = len(calls)
        delayed.on_frame(1.8, FRAME)
        delayed.report(2.)
        assert len(calls) == count
    finally:
        delayed.close()
