"""Own front ultrasonic range: model, SIM rays, map prediction, provider (#221, 2026-09-28).

No MuJoCo physics step anywhere: ``mj_step``/``mj_step1``/``mj_step2`` are
replaced by a failing stub for this module; scenes are built from XML and only
``mj_forward`` / ``mj_ray`` / ``mj_multiRay`` run.
"""
from __future__ import annotations

import ast
import importlib.util
import json
import math
from dataclasses import replace
from pathlib import Path

import numpy as np
import pytest

from harness import range_provider as rp
from harness import ultrasonic_map as um
from harness import ultrasonic_model as usm

ROOT = Path(__file__).resolve().parents[1]
HAS_MUJOCO = importlib.util.find_spec('mujoco') is not None
EXACT = replace(usm.DEFAULT_SPEC, dropout_prob=0., outlier_prob=0., noise_sigma0_m=0., noise_rel=0.)
NEW_FILES = ('harness/ultrasonic_model.py', 'harness/ultrasonic_map.py', 'harness/range_provider.py',
             'sim/ultrasonic_range.py', 'harness/ultrasonic_carry.py', 'scripts/analyze_ultrasonic_carry_height.py')
BEAM_POSE = (1.0, -1.2)
# Recorded M2 carry: beam body z at the door crossing 0.0607-0.061 m (experiments/2026-09-26-zone-m2-pair).
LIFTED_BEAM_BODY_Z_M = .061


# --- physics-step guard ------------------------------------------------------------------------

@pytest.fixture(scope='module', autouse=True)
def no_physics_step():
    if not HAS_MUJOCO:
        yield
        return
    import mujoco
    saved = {name: getattr(mujoco, name) for name in ('mj_step', 'mj_step1', 'mj_step2')}

    def forbidden(*args, **kwargs):
        raise AssertionError('this suite forbids MuJoCo physics stepping')

    for name in saved:
        setattr(mujoco, name, forbidden)
    try:
        yield
    finally:
        for name, fn in saved.items():
            setattr(mujoco, name, fn)


# --- pure model ----------------------------------------------------------------------------------

def test_ray_pattern_covers_axis_edges_and_cardinal_directions():
    dirs, alpha = usm.ray_pattern()
    assert len(dirs) == 1 + 4 * sum(range(1, 7)) == 85
    assert np.allclose(np.linalg.norm(dirs, axis=1), 1.)
    assert math.isclose(alpha.max(), math.radians(15.))
    edge = dirs[np.isclose(alpha, alpha.max())]
    for want in ((0, 0, 1), (0, 0, -1), (0, 1, 0), (0, -1, 0)):
        lateral = edge[:, 1:] / np.linalg.norm(edge[:, 1:], axis=1, keepdims=True)
        assert np.isclose(lateral @ np.array(want[1:], float), 1.).any()
    assert math.isclose(float(usm.directivity(math.radians(15.))), .5)
    assert float(usm.directivity(math.radians(15.5))) == 0.


def test_first_echo_is_nearest_ray_above_threshold():
    alpha = np.radians([0., 10., 15.])
    # nearest ray hits at grazing incidence (floor-like) -> ignored
    assert usm.first_echo([1.0, .8, .2], alpha, np.radians([0., 0., 80.])) == .8
    assert usm.first_echo([-1., -1., -1.], alpha, np.zeros(3)) is None
    assert usm.first_echo([4.2, 4.3, 4.4], alpha, np.zeros(3)) is None      # beyond max range


def test_reading_noise_is_deterministic_quantised_and_sized():
    a = [usm.noisy_reading(0., 1., usm.reading_rng(7, 'r1', k)) for k in range(400)]
    b = [usm.noisy_reading(0., 1., usm.reading_rng(7, 'r1', k)) for k in range(400)]
    other = [usm.noisy_reading(0., 1., usm.reading_rng(7, 'r2', k)) for k in range(400)]
    assert [x.as_dict() for x in a] == [x.as_dict() for x in b]
    assert [x.as_dict() for x in a] != [x.as_dict() for x in other]
    valid = [x.range_m for x in a if x.valid]
    assert all(abs(v * 1000 - round(v * 1000)) < 1e-6 for v in valid)
    near = np.array([v for v in valid if abs(v - 1.) < .1])
    sigma = usm.DEFAULT_SPEC.sigma_m(1.)
    assert abs(near.mean() - 1.) < 3 * sigma / math.sqrt(len(near))
    assert .7 * sigma < near.std() < 1.3 * sigma
    assert 0 < sum(not x.valid for x in a) < 30            # 2 % dropout


def test_blind_zone_and_no_echo_are_invalid():
    rng = lambda: usm.reading_rng(1, 'r1', 0)
    assert not usm.noisy_reading(0., .015, rng(), EXACT).valid
    assert not usm.noisy_reading(0., None, rng(), EXACT).valid
    good = usm.noisy_reading(3.5, .5, rng(), EXACT)
    assert good.valid and good.range_m == .5 and good.t == 3.5
    assert set(good.as_dict()) == {'t', 'range_m', 'valid'}
    assert usm.noisy_reading(0., None, rng(), EXACT).as_dict()['range_m'] is None


def test_crosstalk_arrival_window():
    s = usm.DEFAULT_SPEC
    assert math.isclose(usm.crosstalk_range(.7, 0., s), .35)
    assert usm.crosstalk_range(.7, -.01, s) is None                 # arrived before our trigger
    assert usm.crosstalk_range(.7, .05, s) is None                  # after the 4 m listening window


# --- static map prediction -----------------------------------------------------------------------

WALL_MAP = {'obstacles': [{'id': 'w', 'center_m': [1.025, 0.], 'half_extents_m': [.025, 2.], 'height_m': .10}]}


def test_map_prediction_wall_head_on_oblique_and_beyond_visibility():
    face = 1.0
    sensor_x = usm.DEFAULT_SPEC.mount_x_m
    head_on = um.expected_range(WALL_MAP, (0., 0., 0.), EXACT)
    assert math.isclose(head_on.range_m, face - sensor_x, abs_tol=1e-9)
    # 10 deg: a 10 deg ring ray meets the wall head-on -> perpendicular distance
    yaw = math.radians(10.)
    perp = face - sensor_x * math.cos(yaw)
    assert math.isclose(um.expected_range(WALL_MAP, (0., 0., yaw), EXACT).range_m, perp, abs_tol=1e-9)
    # 30 deg: outside the cone's head-on rays; the 15 deg edge ray at 15 deg incidence still echoes
    yaw = math.radians(30.)
    perp = face - sensor_x * math.cos(yaw)
    assert math.isclose(um.expected_range(WALL_MAP, (0., 0., yaw), EXACT).range_m,
                        perp / math.cos(math.radians(15.)), abs_tol=1e-9)
    # 40 deg: edge ray at 25 deg incidence is too weak -> no echo (specular miss)
    assert not um.expected_range(WALL_MAP, (0., 0., math.radians(40.)), EXACT).echo


def test_map_prediction_low_wall_and_range_limits():
    low = {'obstacles': [{'id': 'kerb', 'center_m': [.6, 0.], 'half_extents_m': [.02, 1.], 'height_m': .02}]}
    # 20 mm kerb below the 54 mm sensor: rays at <= 15 deg reach 20 mm only beyond 0.127 m
    r = um.expected_range(low, (0., 0., 0.), EXACT)
    assert r.echo and r.range_m > .5
    assert not um.expected_range({'obstacles': []}, (0., 0., 0.), EXACT).echo      # floor alone: grazing
    far = {'obstacles': [{'id': 'w', 'center_m': [4.2, 0.], 'half_extents_m': [.025, 3.], 'height_m': .1}]}
    assert not um.expected_range(far, (0., 0., 0.), EXACT).echo


def test_consistency_and_likelihood_are_asymmetric():
    exp = um.ExpectedRange(1.0, usm.DEFAULT_SPEC.sigma_m(1.))
    assert um.range_consistency(1.005, True, exp) == um.CONSISTENT
    assert um.range_consistency(.40, True, exp) == um.SHORTER
    assert um.range_consistency(1.5, True, exp) == um.LONGER
    assert um.range_consistency(None, False, exp) == um.MISSING_ECHO
    assert um.range_consistency(.4, True, um.ExpectedRange(None, None)) == um.UNEXPECTED_ECHO
    assert um.range_consistency(None, False, um.ExpectedRange(None, None)) == um.BOTH_NONE
    ll = lambda z: um.range_log_likelihood(z, True, exp)
    assert ll(1.0) > ll(.4) > ll(1.5)          # unmapped object in front is more plausible than seeing through a wall
    assert um.range_log_likelihood(None, False, exp) < um.range_log_likelihood(None, False, um.ExpectedRange(None, None))


def test_expected_range_uses_real_zone_map_walls_and_door_posts():
    static = json.loads((ROOT / 'maps/zones/zone_wide_door_tags_v2.json').read_text())
    ids = {b['id'] for b in um.static_boxes(static)}
    assert {'wall_divider_1', 'post_door_1_lo'} <= ids
    r = um.expected_range(static, (1.6, -2.5, 0.), EXACT)
    assert math.isclose(r.range_m, 2.175 - (1.6 + .078), abs_tol=1e-9)


# --- provider, history, conditions ---------------------------------------------------------------

def test_provider_reports_time_age_source_sigma_and_limits():
    p = rp.OwnUltrasonicRangeProvider()
    assert p.report(0.).t_meas is None
    assert rp.check_range_limits(p.report(0.), 0., rp.RangeLimits()) == ['no_reading']
    p.on_reading(usm.RangeReading(1.00, .500, True))
    p.on_reading(usm.RangeReading(1.06, float('nan'), False))
    rep = p.report(1.10)
    assert (rep.t_meas, rep.valid) == (1.06, False) and math.isclose(rep.age_s, .04)
    assert rep.last_valid_t == 1.00 and rep.source.startswith(rp.SOURCE_PREFIX + ':')
    assert rp.check_range_limits(rep, 1.10, rp.RangeLimits()) == ['invalid']
    p.on_reading(usm.RangeReading(1.12, .480, True))
    rep = p.report(1.50)
    assert rep.valid and rep.range_m == .480 and math.isclose(rep.sigma_m, usm.DEFAULT_SPEC.sigma_m(.48))
    assert rp.check_range_limits(rep, 1.50, rp.RangeLimits(max_age_s=.2)) == ['stale']
    assert p.report(1.03).t_meas == 1.00            # a report never uses a later reading
    assert [r.t for r in p.history(1.12, .1)] == [1.06, 1.12]
    with pytest.raises(ValueError):
        p.on_reading(usm.RangeReading(1.0, .5, True))
    assert set(rep.as_dict()) == {'t_meas', 'age_s', 'valid', 'range_m', 'sigma_m', 'min_range_m',
                                  'max_range_m', 'last_valid_t', 'source'}


def test_history_file_has_only_reading_fields(tmp_path):
    path = tmp_path / 'r1' / 'ultrasonic.jsonl'
    with rp.RangeHistoryWriter(path, 'r1', run_meta={'run_id': 'unit'}) as w:
        w.append(usm.RangeReading(.0, .5, True))
        w.append(usm.RangeReading(.06, float('nan'), False))
    header, rows = rp.read_history(path)
    assert header['spec_sha256'] == usm.spec_record()['sha256'] and header['robot_id'] == 'r1'
    assert [r.as_dict() for r in rows] == [{'t': 0., 'range_m': .5, 'valid': True},
                                           {'t': .06, 'range_m': None, 'valid': False}]
    with pytest.raises(FileExistsError):
        rp.RangeHistoryWriter(path, 'r1')


def test_same_provider_config_in_all_four_conditions():
    from harness.zone_study_contract import MAIN_CONDITIONS
    assert len(MAIN_CONDITIONS) == 4
    configs = {name: rp.provider_config_for_condition(name) for name in MAIN_CONDITIONS}
    assert len({json.dumps(c, sort_keys=True) for c in configs.values()}) == 1
    with pytest.raises(ValueError):
        rp.provider_config_for_condition('no_such_condition')


def test_controller_side_modules_never_import_the_simulator():
    for name in ('harness/ultrasonic_model.py', 'harness/ultrasonic_map.py', 'harness/range_provider.py',
                 'harness/ultrasonic_carry.py'):
        tree = ast.parse((ROOT / name).read_text())
        mods = {a.name for n in ast.walk(tree) if isinstance(n, ast.Import) for a in n.names}
        mods |= {n.module or '' for n in ast.walk(tree) if isinstance(n, ast.ImportFrom)}
        assert not any(m == 'mujoco' or m.startswith(('sim', 'mujoco.')) for m in mods), name


# --- existing bundles unchanged ------------------------------------------------------------------

def test_new_modules_are_outside_existing_bundle_closures():
    from harness.rgb_execution_bundle import source_closure
    closure = source_closure(root=ROOT)
    assert not set(NEW_FILES) & set(closure)
    from scripts import run_zone_study_integration as runner
    pre = runner.load_prereg(ROOT / 'configs/zone_study_integration/pair_dev_DRAFT.json')
    bundle = runner.run_bundle(pre, pre['episodes'][0])[0]
    assert not set(NEW_FILES) & set(bundle['runtime_files_sha256'])


def test_spec_matches_the_sim_appearance_geometry():
    from sim.masterpi_geometry import NOMINAL_ULTRASONIC_X_M
    assert usm.DEFAULT_SPEC.mount_x_m == NOMINAL_ULTRASONIC_X_M
    src = (ROOT / 'sim/masterpi_dynamics_v2.py').read_text()
    assert '{0.054 - WHEEL_RADIUS_M:.6f}" size=".010 .006"' in src and usm.DEFAULT_SPEC.mount_z_floor_m == .054


# --- MuJoCo rays in the real pair-carry scene ----------------------------------------------------

def _scene(cargo):
    import mujoco
    from sim.multi_masterpi_production import build_multi_robot_xml
    from sim.zone_tagged_cargo_scene import TaggedCargoZoneScene
    scene = TaggedCargoZoneScene.from_tagged_cargo('zone_wide_door_tags_v2', 11, cargo=cargo,
                                                   goal={'A': {'cyan': 1}}, contact_profile='local_contact_fine')
    model = mujoco.MjModel.from_xml_string(scene.transform(build_multi_robot_xml(None)))
    return scene, model, mujoco.MjData(model)


def _free(model, data, joint, x, y, z, yaw):
    import mujoco
    j = mujoco.mj_name2id(model, mujoco.mjtObj.mjOBJ_JOINT, joint)
    q = model.jnt_qposadr[j]
    data.qpos[q:q + 7] = [x, y, z, math.cos(yaw / 2), 0, 0, math.sin(yaw / 2)]


def _robot(model, data, rid, x, y, yaw):
    _free(model, data, f'{rid}__base_free', x, y, .0325, yaw)


def _park_others(model, data, *rids):
    for i, rid in enumerate(rids):
        _robot(model, data, rid, 4.8, .9 - .45 * i, 0.)


@pytest.fixture(scope='module')
def beam_scene():
    if not HAS_MUJOCO:
        pytest.skip('mujoco is not installed')
    from sim.zone_cargo import instances
    beam = {'item_id': 'beam', 'kind': 'long_beam', 'pose': [*BEAM_POSE, 0.]}
    scene, model, data = _scene([beam])
    return scene, model, data, instances([beam])[0]


def _beam(model, data, inst, z=.0005, yaw=0.):
    _free(model, data, inst.joint, BEAM_POSE[0], BEAM_POSE[1], z, yaw)


def test_sim_wall_matches_static_map_prediction(beam_scene):
    import mujoco
    from sim.ultrasonic_range import MujocoUltrasonic
    scene, model, data, inst = beam_scene
    _beam(model, data, inst)
    _park_others(model, data, 'r2', 'r3')
    sensor = MujocoUltrasonic(model, data, 'r1', seed=3, spec=EXACT)
    for yaw_deg in (0., 10., 30.):
        pose = (1.6, -2.5, math.radians(yaw_deg))
        _robot(model, data, 'r1', *pose)
        mujoco.mj_forward(model, data)
        o, _ = sensor.pose()
        assert np.allclose(o, [*usm.sensor_pose(*pose)[0][:2], .054], atol=1e-6)
        sim = sensor.true_first_echo()
        exp = um.expected_range(scene.config['static_map'], pose, EXACT).range_m
        assert abs(sim - exp) < .004        # wall tags stand 1-2 mm proud of the wall face
    _robot(model, data, 'r1', 1.6, -2.5, math.radians(40.))
    mujoco.mj_forward(model, data)
    assert sensor.true_first_echo() is None
    assert not sensor.measure(0.).valid


def test_beam_on_floor_is_below_the_sensor_but_inside_the_cone(beam_scene):
    """Floor beam spans z 0.5-32.5 mm; the sensor axis is at 54 mm."""
    import mujoco
    from sim.ultrasonic_range import MujocoUltrasonic
    scene, model, data, inst = beam_scene
    _beam(model, data, inst, yaw=math.pi / 2)            # long side facing the robot (face at x = 0.98)
    _park_others(model, data, 'r2', 'r3')
    sensor = MujocoUltrasonic(model, data, 'r1', seed=3, spec=EXACT)
    face = BEAM_POSE[0] - .02
    seen = {}
    for gap in (.05, .07, .10, .20, .50, 1.0, 1.5):
        _robot(model, data, 'r1', face - gap - .078, BEAM_POSE[1], 0.)
        mujoco.mj_forward(model, data)
        r = sensor.true_first_echo()
        seen[gap] = r is not None and abs(r - gap) < .01
    # Near: the bar top is 21.5 mm below the axis, reachable only >= 8.2 cm away (15 deg edge).
    # Far: the 2.5 deg ring spacing loses a 32 mm bar beyond ~1.2 m (ray-resolution limit, documented).
    assert seen == {.05: False, .07: False, .10: True, .20: True, .50: True, 1.0: True, 1.5: False}


def test_grasp_pose_sees_partner_and_the_held_load_is_never_excluded(beam_scene):
    """Carry formation: r1 at end_neg facing +x, r2 at end_pos facing -x (beam grasp geometry)."""
    import mujoco
    from sim.ultrasonic_range import MujocoUltrasonic
    from sim.zone_cargo import GRASP_RADIUS_M
    scene, model, data, inst = beam_scene
    _park_others(model, data, 'r3')
    grip = .30 - .03
    x1, x2 = BEAM_POSE[0] - grip - GRASP_RADIUS_M, BEAM_POSE[0] + grip + GRASP_RADIUS_M
    _robot(model, data, 'r1', x1, BEAM_POSE[1], 0.)
    _robot(model, data, 'r2', x2, BEAM_POSE[1], math.pi)
    _beam(model, data, inst)
    mujoco.mj_forward(model, data)
    r1 = MujocoUltrasonic(model, data, 'r1', seed=3, spec=EXACT)
    partner_front = x2 - .0925 - (x1 + .078)
    reading, diag = r1.measure_diagnostic(0.)
    # over the floor beam onto r2 (its chassis or its forward arm), never the beam at 47 mm
    assert diag['echo_geom'].startswith('r2__') and .4 < diag['true_first_echo_m'] < partner_front + .01
    # lifted as in the recorded M2 carry: bar 61-93 mm, 7 mm above the axis, end face 47 mm ahead
    _beam(model, data, inst, z=LIFTED_BEAM_BODY_Z_M)
    mujoco.mj_forward(model, data)
    end_face = BEAM_POSE[0] - .30 - (x1 + .078)
    _, diag = r1.measure_diagnostic(0.)
    # the held load is a separate body and is seen exactly like the physical sensor would see it
    assert diag['echo_geom'] == inst.body + '__bar' and abs(diag['true_first_echo_m'] - end_face) < .005
    import inspect
    assert 'exclude' not in inspect.signature(r1.measure).parameters          # no API to hide the load
    assert 'exclude' not in inspect.signature(r1.cast).parameters


def test_peer_robot_is_detected_and_crosstalk_is_optional(beam_scene):
    import mujoco
    from sim.ultrasonic_range import MujocoUltrasonic
    scene, model, data, inst = beam_scene
    _beam(model, data, inst, z=.0005)
    _free(model, data, inst.joint, 4.8, -2.9, .0005, 0.)                # beam out of the way
    _park_others(model, data, 'r3')
    _robot(model, data, 'r1', .0, -1.2, 0.)
    _robot(model, data, 'r2', .9, -1.2, math.pi)
    mujoco.mj_forward(model, data)
    chassis_gap = (.9 - .0925) - .078
    base = replace(usm.DEFAULT_SPEC, dropout_prob=0., outlier_prob=0.)
    off1 = MujocoUltrasonic(model, data, 'r1', seed=5, spec=base)
    off2 = MujocoUltrasonic(model, data, 'r2', seed=5, spec=base)
    _, diag = off1.measure_diagnostic(0.)
    gap = diag['true_first_echo_m']
    assert diag['echo_geom'].startswith('r2__') and chassis_gap - .2 < gap <= chassis_gap + .01
    off1.seq = 0
    off = [off1.measure(k * .06, peers=[off2]).range_m for k in range(60)]
    on1 = MujocoUltrasonic(model, data, 'r1', seed=5, spec=replace(base, crosstalk=True))
    on2 = MujocoUltrasonic(model, data, 'r2', seed=5, spec=replace(base, crosstalk=True))
    on = [on1.measure(k * .06, peers=[on2]) for k in range(400)]
    assert max(abs(v - gap) for v in off) < .05
    # A peer pulse only matters when it arrives before our own echo: with free-running phases that is
    # a window of about (2 * gap) / c out of the 60 ms period (~6 %); later arrivals are masked.
    short = [r for r in on if not r.valid or r.range_m < gap - .05]
    assert 5 <= len(short) <= 60
    # peer turned away: its transmit cone misses us -> no crosstalk
    _robot(model, data, 'r2', .9, -1.2, math.pi / 2)
    mujoco.mj_forward(model, data)
    on1.seq = 0
    true = on1.true_first_echo()
    turned = [on1.measure_diagnostic(k * .06, peers=[on2])[1]['crosstalk_m'] for k in range(30)]
    assert turned == [None] * 30 and true is not None


def test_own_arm_is_excluded_and_readings_carry_no_sim_state():
    if not HAS_MUJOCO:
        pytest.skip('mujoco is not installed')
    import mujoco
    from sim.ultrasonic_range import SENSOR_GEOM_GROUPS, MujocoUltrasonic
    _, model, data = _scene([])
    _robot(model, data, 'r1', .3, -1.2, 0.)
    _park_others(model, data, 'r2', 'r3')
    for joint, value in (('r1__shoulder', -.15), ('r1__elbow', -1.5), ('r1__wrist_pitch', 1.5)):
        data.qpos[model.jnt_qposadr[mujoco.mj_name2id(model, mujoco.mjtObj.mjOBJ_JOINT, joint)]] = value
    mujoco.mj_forward(model, data)
    sensor = MujocoUltrasonic(model, data, 'r1', seed=1, spec=EXACT)
    origin, R = sensor.pose()
    dirs = np.ascontiguousarray(sensor.local_dirs @ R.T)
    n = len(dirs)
    geom, dist = np.zeros(n, np.int32), np.zeros(n)
    mujoco.mj_multiRay(model, data, origin, dirs.ravel(), SENSOR_GEOM_GROUPS, 1, -1, geom, dist, None, n, 5.)
    raw = {mujoco.mj_id2name(model, mujoco.mjtObj.mjOBJ_GEOM, int(g)) for g in geom if g >= 0}
    assert any(name.startswith('r1__') for name in raw)          # without exclusion the gripper blocks the cone
    reading, diag = sensor.measure_diagnostic(2.0)
    assert not any(h.startswith('r1__') for h in diag['hit_geoms'])
    assert reading.valid and abs(reading.range_m - (2.175 - (.3 + .078))) < .004
    assert set(reading.as_dict()) == {'t', 'range_m', 'valid'}
    assert sensor.due(2.05) is False and sensor.due(2.06) is True


def test_sim_readings_are_seed_deterministic():
    if not HAS_MUJOCO:
        pytest.skip('mujoco is not installed')
    import mujoco
    from sim.ultrasonic_range import MujocoUltrasonic
    _, model, data = _scene([])
    _robot(model, data, 'r1', 1.6, -2.5, 0.)
    _park_others(model, data, 'r2', 'r3')
    mujoco.mj_forward(model, data)
    a = MujocoUltrasonic(model, data, 'r1', seed=9)
    b = MujocoUltrasonic(model, data, 'r1', seed=9)
    c = MujocoUltrasonic(model, data, 'r1', seed=10)
    ra = [a.measure(k * .06).as_dict() for k in range(50)]
    rb = [b.measure(k * .06).as_dict() for k in range(50)]
    rc = [c.measure(k * .06).as_dict() for k in range(50)]
    assert ra == rb and ra != rc


def test_suite_is_in_the_portable_ci_list():
    import fnmatch
    from scripts.run_ci_tests import TEST_PATTERNS
    assert any(fnmatch.fnmatch('tests/test_ultrasonic_range.py', pat) for pat in TEST_PATTERNS)
