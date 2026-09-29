"""Opt-in own front-ultrasonic INPUT of the harness (wiring only, 2026-09-29).

The sensor model has its own suite (``tests/test_ultrasonic_range.py``). This
file checks the connection: the bundle switch, the per-robot own-only input
path, the recording, "off changes nothing" and read-only behaviour on the
physics. No controller uses the value; a successful run of these tests is NOT
evidence that a robot can use the sensor.
"""
from __future__ import annotations

import ast
import hashlib
import importlib.util
import inspect
import json
import math
from pathlib import Path
from types import SimpleNamespace

import numpy as np
import pytest

from harness import range_provider as rp
from harness import ultrasonic_input as ui
from harness import ultrasonic_map as um
from harness import ultrasonic_model as usm

ROOT = Path(__file__).resolve().parents[1]
HAS_MUJOCO = importlib.util.find_spec('mujoco') is not None
ROBOTS = ('r1', 'r2', 'r3')
WIRING_FILES = ('scripts/run_zone_study_sensors.py', 'harness/ultrasonic_input.py', 'sim/ultrasonic_input.py')
PREREG = ROOT / 'configs/zone_study_integration/pair_dev_DRAFT.json'


# --- the switch ----------------------------------------------------------------------------------

@pytest.mark.parametrize('value', [None, {}, {'ultrasonic_front': 'off'}])
def test_off_is_the_default_and_normalizes_to_nothing(value):
    assert ui.normalize_sensors(value) == {}
    assert not ui.is_on(value)
    assert ui.bundle_record(value) is None
    assert ui.result_record(value) is None
    assert ui.runtime_modules(value) == ()


@pytest.mark.parametrize('value', [{'ultrasonic_front': 'on'}, {'ultrasonic_front': True}, {'ultrasonic_rear': 'on_v1'},
                                   {'ultrasonic_front': 'on_v1', 'lidar': 'on_v1'}, 'on_v1', ['on_v1']])
def test_unknown_or_ambiguous_settings_are_refused_not_defaulted(value):
    with pytest.raises(ui.SensorConfigError):
        ui.normalize_sensors(value)


def test_on_v1_bundle_record_pins_model_spec_and_marks_the_run():
    record = ui.bundle_record({'ultrasonic_front': 'on_v1'})
    block = record['ultrasonic_front']
    assert block['profile'] == 'on_v1' and block['enabled'] is True
    assert block['sensor_model_id'] == usm.SENSOR_MODEL_ID
    assert block['spec_sha256'] == usm.spec_record(usm.DEFAULT_SPEC)['sha256']
    assert block['source'] == rp.source_label(usm.DEFAULT_SPEC)
    assert block['baseline_comparable'] is False and 'sensors-on' in block['comparison_note']
    assert block['crosstalk'] is False
    assert block['observation_fields'] == ['t', 'range_m', 'valid', 'status']
    assert block['observation_scope'] == 'own sensor only'
    assert 'none wired' in block['controller_use']
    body = {k: v for k, v in record.items() if k != 'sha256'}
    assert record['sha256'] == hashlib.sha256(json.dumps(body, sort_keys=True, separators=(',', ':')).encode()).hexdigest()
    assert ui.bundle_record({'ultrasonic_front': 'on_v1'}) == record          # deterministic
    modules = ui.runtime_modules({'ultrasonic_front': 'on_v1'})
    assert 'sim.ultrasonic_range' in modules and 'harness.ultrasonic_model' in modules


def test_a_changed_sensor_spec_changes_the_recorded_hash():
    other = usm.spec_record(usm.UltrasonicSpec(period_s=.07))['sha256']
    assert other != ui.bundle_record({'ultrasonic_front': 'on_v1'})['ultrasonic_front']['spec_sha256']


# --- the run bundle: off changes nothing, on is marked -------------------------------------------

@pytest.fixture(scope='module')
def adapter():
    if not HAS_MUJOCO:
        pytest.skip('the runner imports the simulator stack')
    from scripts import run_zone_study_sensors as module
    return module


def _bundle(adapter, sensors='<absent>'):
    runner = adapter.runner
    prereg = runner.load_prereg(PREREG)
    if sensors != '<absent>':
        prereg['sensors'] = sensors
    if adapter.sensors_of(prereg):
        with adapter.sensors_enabled():
            return runner.run_bundle(prereg, prereg['episodes'][0])[0]
    return runner.run_bundle(prereg, prereg['episodes'][0])[0]


def test_off_bundle_is_unchanged_and_carries_no_sensor_source(adapter):
    absent = _bundle(adapter)
    assert 'sensors' not in absent
    assert not any('ultrasonic' in name or name == 'harness/range_provider.py' or 'sensors' in name
                   for name in absent['runtime_files_sha256'])
    for explicit in (None, {}, {'ultrasonic_front': 'off'}):
        assert json.dumps(_bundle(adapter, explicit), sort_keys=True, default=str) == json.dumps(absent, sort_keys=True, default=str)


def test_off_leaves_the_pinned_runner_untouched(adapter):
    """Sensors off: main() is the unpatched runner; nothing stays patched after an on-run either."""
    runner = adapter.runner
    before = {n: getattr(runner, n) for n in ('StudyTeamHost', 'run_bundle', 'runtime_files', 'run_trial', 'write_outputs')}
    with adapter.sensors_enabled():
        assert runner.StudyTeamHost is adapter.SensorStudyTeamHost and runner.run_bundle is not before['run_bundle']
    assert {n: getattr(runner, n) for n in before} == before


def test_on_bundle_differs_only_by_the_sensor_block_and_its_sources(adapter):
    off, on = _bundle(adapter), _bundle(adapter, {'ultrasonic_front': 'on_v1'})
    assert on['sensors'] == ui.bundle_record({'ultrasonic_front': 'on_v1'})
    added = set(on['runtime_files_sha256']) - set(off['runtime_files_sha256'])
    assert {'harness/ultrasonic_input.py', 'sim/ultrasonic_input.py', 'sim/ultrasonic_range.py',
            'harness/ultrasonic_model.py', 'scripts/run_zone_study_sensors.py'} <= added
    assert set(off['runtime_files_sha256']) <= set(on['runtime_files_sha256'])
    assert {k: v for k, v in on.items() if k not in ('sensors', 'runtime_files_sha256')} == \
           {k: v for k, v in off.items() if k != 'runtime_files_sha256'}
    assert all(on['runtime_files_sha256'][k] == v for k, v in off['runtime_files_sha256'].items())
    from harness.zone_study_contract import digest
    assert digest(on) != digest(off)                      # a different bundle hash: never mistaken for the baseline


def test_the_adapter_refuses_unknown_sensor_settings(adapter):
    with pytest.raises(ui.SensorConfigError):
        _bundle(adapter, {'ultrasonic_front': 'on_v2'})


def test_bundle_is_condition_independent(adapter):
    """The bundle (and so the sensor block) is built before any condition is chosen; the host never sees one."""
    assert 'condition' not in inspect.signature(adapter.runner.run_bundle).parameters
    assert 'condition' not in inspect.signature(adapter.SensorStudyTeamHost._attach).parameters
    from harness.zone_study_contract import MAIN_CONDITIONS
    configs = {c: rp.provider_config_for_condition(c) for c in MAIN_CONDITIONS}
    assert len({json.dumps(v, sort_keys=True) for v in configs.values()}) == 1


# --- own-only input path and recording -----------------------------------------------------------

def _rows(path):
    return [json.loads(line) for line in Path(path).read_text().splitlines()]


def test_each_robot_gets_only_its_own_readings_and_they_are_recorded(tmp_path):
    seeds = {rid: usm.sensor_seed(700, rid) for rid in ROBOTS}
    inp = ui.OwnRangeInput(ROBOTS, 'on_v1', noise_seeds=seeds, out_dir=tmp_path, run_meta={'trial_seed': 700})
    inp.feed('r1', usm.RangeReading(.0, 1.2345, True, usm.OK))
    inp.feed('r2', usm.invalid(.0, usm.NO_ECHO))
    inp.feed('r1', usm.RangeReading(.06, 1.2, True, usm.OK))
    assert inp.provider('r1').report(.06).range_m == 1.2
    assert inp.provider('r2').report(.06).status == usm.NO_ECHO and not inp.provider('r2').report(.06).valid
    assert inp.provider('r3').report(.06).t_meas is None                      # r3 never saw r1's or r2's data
    assert inp.provider('r1') is not inp.provider('r2')
    inp.close()
    assert inp.rows() == {'r1': 2, 'r2': 1, 'r3': 0}
    header, rows = rp.read_history(tmp_path / 'robots' / 'r1' / 'inputs' / ui.HISTORY_FILE)
    assert header['noise_seed'] == str(seeds['r1']) and header['robot_id'] == 'r1'
    assert header['spec_sha256'] == usm.spec_record(usm.DEFAULT_SPEC)['sha256']
    assert [r.as_dict() for r in rows] == [{'t': 0., 'range_m': 1.2345, 'valid': True, 'status': 'ok'},
                                          {'t': .06, 'range_m': 1.2, 'valid': True, 'status': 'ok'}]
    for path in (tmp_path / 'robots').rglob(ui.HISTORY_FILE):
        for row in _rows(path)[1:]:
            assert set(row) == set(ui.OBSERVATION_FIELDS)                       # nothing about what was hit


def test_noise_seeds_are_required_for_every_robot(tmp_path):
    with pytest.raises(ui.SensorConfigError):
        ui.OwnRangeInput(ROBOTS, 'on_v1', noise_seeds={'r1': 1})
    with pytest.raises(ui.SensorConfigError):
        ui.OwnRangeInput(ROBOTS, 'off', noise_seeds={r: 1 for r in ROBOTS})


def test_report_surface_names_no_target():
    provider = rp.OwnUltrasonicRangeProvider()
    provider.on_reading(usm.RangeReading(.0, 1.0, True, usm.OK))
    keys = set(provider.report(.0).as_dict())
    assert keys == {'t_meas', 'age_s', 'valid', 'range_m', 'sigma_m', 'min_range_m', 'max_range_m', 'last_valid_t',
                    'source', 'status', 'last_valid_range_m'}
    assert not any(word in key for key in keys for word in ('geom', 'body', 'hit', 'name', 'xyz', 'pose'))
    assert set(usm.RangeReading.__dataclass_fields__) == {'t', 'range_m', 'valid', 'status'}


def test_range_report_helper_is_none_when_off_and_reports_own_provider_when_on():
    plain = SimpleNamespace()
    assert ui.range_report(plain, 1.0) is None
    provider = rp.OwnUltrasonicRangeProvider()
    provider.on_reading(usm.RangeReading(.5, .8, True, usm.OK))
    report = ui.range_report(SimpleNamespace(range_provider=provider), 1.0)
    assert report.range_m == .8 and report.age_s == pytest.approx(.5)


def test_no_controller_or_skill_reads_the_range():
    """Wiring only: the value is not used by any skill, controller or study input builder."""
    allowed = {ROOT / name for name in WIRING_FILES} | {ROOT / 'harness/range_provider.py'}
    offenders = []
    for path in list((ROOT / 'harness').glob('*.py')) + list((ROOT / 'sim').glob('*.py')) + list((ROOT / 'scripts').glob('*.py')):
        if path in allowed or path.name.startswith('ultrasonic') or path.name in ('range_provider.py',):
            continue
        text = path.read_text()
        tree = ast.parse(text)
        names = {n.attr for n in ast.walk(tree) if isinstance(n, ast.Attribute)} | \
                {n.id for n in ast.walk(tree) if isinstance(n, ast.Name)}
        if names & {'range_report', 'range_provider', 'range_rig', 'OwnRangeInput', 'OwnUltrasonicRig'}:
            offenders.append(str(path.relative_to(ROOT)))
    assert offenders == []


def test_harness_input_module_never_imports_the_simulator():
    tree = ast.parse((ROOT / 'harness/ultrasonic_input.py').read_text())
    mods = {a.name for n in ast.walk(tree) if isinstance(n, ast.Import) for a in n.names}
    mods |= {n.module or '' for n in ast.walk(tree) if isinstance(n, ast.ImportFrom)}
    assert not any(m == 'mujoco' or m.startswith(('sim', 'mujoco.')) for m in mods)


def test_the_physics_hook_is_one_guarded_read_only_call_and_pinned_sources_are_untouched():
    """The adapter reads after each physics step; the pinned host/executor/runner do not mention the sensor."""
    tree = ast.parse((ROOT / 'scripts/run_zone_study_sensors.py').read_text())
    cls = next(n for n in tree.body if isinstance(n, ast.ClassDef) and n.name == 'SensorStudyTeamHost')
    fn = next(n for n in cls.body if isinstance(n, ast.FunctionDef) and n.name == '_physics_until')
    assert [ast.unparse(s) for s in fn.body if not isinstance(s, ast.If)][-1:] == ['super()._physics_until(t_end)']
    guarded = [n for n in fn.body if isinstance(n, ast.If)]
    assert len(guarded) == 1 and ast.unparse(guarded[0].test) == 'self.range_rig is not None'
    assert [ast.unparse(s) for s in guarded[0].body] == ['self.range_rig.tick(float(self.world.data.time))']
    for name in ('harness/zone_own_executor.py', 'harness/zone_own_team_host.py', 'scripts/run_zone_study_integration.py'):
        text = (ROOT / name).read_text()
        assert not any(word in text for word in ('ultrasonic', 'range_rig', 'range_provider', 'sensors'))


# --- MuJoCo: real rays on the study scene ----------------------------------------------------------

def _scene():
    import mujoco
    from sim.multi_masterpi_production import build_multi_robot_xml
    from sim.zone_tagged_cargo_scene import TaggedCargoZoneScene
    scene = TaggedCargoZoneScene.from_tagged_cargo('zone_wide_door_tags_v2', 11, cargo=[], goal={'A': {'cyan': 1}},
                                                   contact_profile='local_contact_fine')
    model = mujoco.MjModel.from_xml_string(scene.transform(build_multi_robot_xml(None)))
    return scene, model


def _place(model, data, rid, x, y, yaw, z=.0325):
    import mujoco
    j = mujoco.mj_name2id(model, mujoco.mjtObj.mjOBJ_JOINT, f'{rid}__base_free')
    q = model.jnt_qposadr[j]
    data.qpos[q:q + 7] = [x, y, z, math.cos(yaw / 2), 0, 0, math.sin(yaw / 2)]


def _world(placements):
    import mujoco
    scene, model = _scene()
    data = mujoco.MjData(model)
    for rid, pose in placements.items():
        _place(model, data, rid, *pose)
    mujoco.mj_forward(model, data)
    return scene, model, data


PLACEMENTS = {'r1': (1.6, -2.5, 0.), 'r2': (4.8, .9, 0.), 'r3': (4.8, .45, 0.)}


def _rig(model, data, tmp_path=None, seed=700):
    from sim.ultrasonic_input import OwnUltrasonicRig
    inp = ui.OwnRangeInput(ROBOTS, 'on_v1', noise_seeds={r: usm.sensor_seed(seed, r) for r in ROBOTS},
                           out_dir=tmp_path)
    return OwnUltrasonicRig(model, data, ROBOTS, episode_seed=seed, range_input=inp)


@pytest.mark.skipif(not HAS_MUJOCO, reason='mujoco is not installed')
def test_rig_reads_the_wall_ahead_within_noise_and_is_periodic(tmp_path):
    scene, model, data = _world(PLACEMENTS)
    rig = _rig(model, data, tmp_path)
    expected = um.expected_range(scene.config['static_map'], PLACEMENTS['r1'], usm.DEFAULT_SPEC).range_m
    taken = [rig.tick(i * .001) for i in range(501)]                         # 0.5 SIM s at a 1 ms cadence
    assert sum(taken) == 3 * 9                                              # t = 0, .06, ... .48 per robot
    history = rig.provider('r1').history(.5, 1.)
    assert [round(r.t, 3) for r in history][:3] == [0., .06, .12]
    assert all(b.t - a.t >= usm.DEFAULT_SPEC.period_s - 1e-9 for a, b in zip(history, history[1:]))
    valid = [r.range_m for r in history if r.valid]
    assert len(valid) >= 7 and all(abs(v - expected) < .15 for v in valid)
    rig.close()
    assert rig.record()['history_rows'] == {'r1': 9, 'r2': 9, 'r3': 9}
    assert rig.record()['sites'] == {'r1': None, 'r2': None, 'r3': None}     # v2 body mount


@pytest.mark.skipif(not HAS_MUJOCO, reason='mujoco is not installed')
def test_matched_noise_for_matched_seed_time_and_robot_regardless_of_call_pattern():
    """Two 'conditions' (independent rigs, different tick call patterns) draw identical readings."""
    _, model, data = _world(PLACEMENTS)
    a, b = _rig(model, data), _rig(model, data)
    for i in range(301):
        a.tick(i * .001)
    for i in range(301):                                                      # repeated calls at the same and earlier times
        b.tick(i * .001)
        b.tick(i * .001)
        b.tick(max(0., i * .001 - .03))
    for rid in ROBOTS:
        assert [r.as_dict() for r in a.provider(rid).history(.3, 1.)] == [r.as_dict() for r in b.provider(rid).history(.3, 1.)]
    other = _rig(model, data, seed=701)
    for i in range(301):
        other.tick(i * .001)
    assert [r.as_dict() for r in a.provider('r1').history(.3, 1.)] != [r.as_dict() for r in other.provider('r1').history(.3, 1.)]


@pytest.mark.skipif(not HAS_MUJOCO, reason='mujoco is not installed')
def test_rig_never_steps_or_forwards_and_leaves_the_state_untouched(monkeypatch):
    import mujoco
    _, model, data = _world(PLACEMENTS)
    rig = _rig(model, data)
    before = (data.qpos.copy(), data.qvel.copy(), data.xpos.copy(), data.xmat.copy(), data.ncon, data.time, data.qacc_warmstart.copy())

    def forbidden(*args, **kwargs):
        raise AssertionError('the sensor must not advance or recompute the physics')
    for name in ('mj_step', 'mj_step1', 'mj_step2', 'mj_forward', 'mj_fwdPosition', 'mj_kinematics'):
        monkeypatch.setattr(mujoco, name, forbidden)
    for i in range(200):
        rig.tick(i * .001)
    after = (data.qpos, data.qvel, data.xpos, data.xmat, data.ncon, data.time, data.qacc_warmstart)
    for x, y in zip(before, after):
        assert np.array_equal(np.asarray(x), np.asarray(y))


@pytest.mark.skipif(not HAS_MUJOCO, reason='mujoco is not installed')
def test_physics_is_identical_with_and_without_the_sensor():
    """Contacts, weights and collisions are unaffected: same qpos/qvel/contacts after real steps."""
    import mujoco
    runs = []
    for with_sensor in (False, True):
        _, model, data = _world(PLACEMENTS)
        rig = _rig(model, data) if with_sensor else None
        ncon = 0
        for _ in range(1400):
            mujoco.mj_step(model, data)
            if rig is not None:
                rig.tick(float(data.time))
            ncon += int(data.ncon)
        runs.append((data.qpos.copy(), data.qvel.copy(), data.xpos.copy(), ncon, float(data.time)))
    for x, y in zip(*runs):
        assert np.array_equal(np.asarray(x), np.asarray(y))
    assert runs[1][4] > .3                                             # 0.35 SIM s of real physics
    assert rig.provider('r1').report(runs[1][4]).t_meas >= .24         # the sensor did read during the run


def test_sensor_code_is_independent_of_the_render_profile():
    """Rays use model collision groups; the sensor modules never touch a renderer, camera or vis settings."""
    for name in ('sim/ultrasonic_range.py', 'sim/ultrasonic_input.py'):
        text = (ROOT / name).read_text()
        assert not any(word in text for word in ('Renderer', 'mjv_', 'mjr_', 'model.vis', 'cam_', 'render('))


@pytest.mark.skipif(not HAS_MUJOCO, reason='mujoco is not installed')
def test_attach_gives_each_executor_only_its_own_provider_and_writes_the_history(adapter, tmp_path):
    scene, model, data = _world(PLACEMENTS)
    host = adapter.SensorStudyTeamHost.__new__(adapter.SensorStudyTeamHost)
    host.world = SimpleNamespace(model=model, data=data)
    host.robots = {rid: SimpleNamespace(executor=SimpleNamespace(range_provider=None)) for rid in ROBOTS}
    adapter._RUN.update(sensors={'ultrasonic_front': 'on_v1'}, episode={'episode_id': 'e', 'trial_seed': 700})
    try:
        host._attach(tmp_path / 'own_frames')
        with pytest.raises(RuntimeError):
            adapter.SensorStudyTeamHost._attach(host, tmp_path / 'wrong_name')
    finally:
        adapter._RUN.clear()
    rig = host.range_rig
    providers = [host.robots[rid].executor.range_provider for rid in ROBOTS]
    assert providers == [rig.provider(rid) for rid in ROBOTS] and len({id(p) for p in providers}) == 3
    rig.tick(0.)
    rig.close()
    for rid in ROBOTS:
        header, rows = rp.read_history(tmp_path / 'robots' / rid / 'inputs' / ui.HISTORY_FILE)
        assert header['noise_seed'] == str(usm.sensor_seed(700, rid)) and len(rows) == 1
        assert header['run_meta'] == {'profile': 'on_v1', 'episode': 'e', 'trial_seed': 700}


@pytest.mark.skipif(not HAS_MUJOCO, reason='mujoco is not installed')
def test_host_subclass_reads_once_per_physics_call_after_the_parent_steps(adapter, tmp_path, monkeypatch):
    """The adapter's hook: parent physics first, then one own read at the new SIM time; off host (rig None) reads nothing."""
    import mujoco
    _, model, data = _world(PLACEMENTS)

    def parent_step(self, t_end):
        while data.time < t_end - 1e-9:
            mujoco.mj_step(model, data)
    monkeypatch.setattr(adapter.runner.StudyTeamHost, '_physics_until', parent_step)
    host = adapter.SensorStudyTeamHost.__new__(adapter.SensorStudyTeamHost)
    host.world = SimpleNamespace(model=model, data=data)
    host.range_rig = _rig(model, data, tmp_path)
    step = float(model.opt.timestep)
    t = 0.
    for _ in range(1200):                                # one physics step per call, as StudyTeamHost.advance_to does
        t += step
        host._physics_until(t)
    assert host.range_rig.input.rows() == {'r1': 5, 'r2': 5, 'r3': 5}          # 0.3 SIM s / 60 ms
    plain = adapter.SensorStudyTeamHost.__new__(adapter.SensorStudyTeamHost)
    plain.world = SimpleNamespace(model=model, data=data)
    plain._physics_until(float(data.time) + step)         # range_rig is the class default None: no read, no error
    host.range_rig.close()


@pytest.mark.skipif(not HAS_MUJOCO, reason='mujoco is not installed')
def test_v3_robots_use_their_chassis_fixed_sensor_site():
    """MasterPi v3 scenes expose r*__v3_ultrasonic_site; the rig uses it (static: mj_forward only)."""
    import mujoco
    from sim.multi_masterpi_production import build_multi_robot_xml
    from sim.ultrasonic_input import sensor_site
    from sim.zone_masterpi_v3_scene import MAP_IDS
    from sim.zone_own_scene_provider import own_scene
    from tests.test_zone_masterpi_v3_scene import spec
    scene = own_scene(spec(MAP_IDS[0]), 'cargo_noslip_v1')
    hardware = {'track_m': .133, 'wheelbase_m': .1188}
    xml = scene.robot_transform(scene.transform(build_multi_robot_xml(hardware)), hardware=hardware, calibrated_keys=set())
    model = mujoco.MjModel.from_xml_string(xml)
    data = mujoco.MjData(model)
    mujoco.mj_forward(model, data)
    assert {r: sensor_site(model, r) for r in ROBOTS} == {r: f'{r}__v3_ultrasonic_site' for r in ROBOTS}
    rig = _rig(model, data)
    assert rig.tick(0.) == 3 and all(rig.provider(r).report(0.).t_meas == 0. for r in ROBOTS)
    assert rig.record()['sites'] == {r: f'{r}__v3_ultrasonic_site' for r in ROBOTS}
