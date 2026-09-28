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


def test_blind_zone_no_echo_and_dropout_have_distinct_statuses():
    rng = lambda: usm.reading_rng(1, 'r1', 0)
    blind = usm.noisy_reading(0., .015, rng(), EXACT)
    assert not blind.valid and blind.status == usm.BLIND
    none = usm.noisy_reading(0., None, rng(), EXACT)
    assert not none.valid and none.status == usm.NO_ECHO
    good = usm.noisy_reading(3.5, .5, rng(), EXACT)
    assert good.valid and good.range_m == .5 and good.t == 3.5 and good.status == usm.OK
    assert set(good.as_dict()) == {'t', 'range_m', 'valid', 'status'}
    assert none.as_dict()['range_m'] is None
    # a dropout is reported like the real sensor shows it (no_echo); the cause is diagnostic only
    drop = replace(EXACT, dropout_prob=1.)
    r, cause = usm.noisy_reading_with_cause(0., .5, rng(), drop)
    assert (r.status, cause) == (usm.NO_ECHO, usm.DROPOUT)
    with pytest.raises(ValueError):
        usm.RangeReading(0., .5, True, usm.NO_ECHO)


def test_noise_is_indexed_by_tick_and_seed_is_condition_free():
    s = usm.DEFAULT_SPEC
    assert usm.reading_tick(1.2, s) == 20 and usm.reading_tick(1.2 + 1e-7, s) == 20
    a = usm.sensor_seed(11, 'r1')
    assert a == usm.sensor_seed(11, 'r1') != usm.sensor_seed(11, 'r2') != usm.sensor_seed(12, 'r1')
    assert a > 2 ** 32                                      # full 64-bit seed, no truncation
    x = usm.reading_rng(a, 'r1', 5).random()
    assert x == usm.reading_rng(a, 'r1', 5).random() != usm.reading_rng(a, 'r1', 5, usm.CROSSTALK_STREAM).random()
    assert usm.reading_rng(a, 'r1', 5).random() != usm.reading_rng(a + 2 ** 40, 'r1', 5).random()


def test_crosstalk_phase_drifts_slowly_and_is_shared_by_the_pair():
    s = replace(usm.DEFAULT_SPEC, crosstalk=True)
    ph = [usm.crosstalk_phase(3, ('r1', 'r2'), k, s) for k in range(2000)]
    back = [usm.crosstalk_phase(3, ('r2', 'r1'), k, s) for k in range(2000)]
    assert all(abs(a + b) < 1e-9 or abs(abs(a + b) - s.period_s) < 1e-9 for a, b in zip(ph, back))
    steps = [abs(b - a) for a, b in zip(ph, ph[1:]) if abs(b - a) < s.period_s / 2]
    assert max(steps) <= s.crosstalk_clock_tol * s.period_s + 6 * s.crosstalk_jitter_s
    # bursts: the crosstalk window (~4 ms for a 0.69 m gap) is crossed by consecutive readings
    hit = [usm.crosstalk_range(.69, p, s) is not None and usm.crosstalk_range(.69, p, s) < .69 for p in ph]
    runs, run = [], 0
    for h in hit + [False]:
        run = run + 1 if h else (runs.append(run) or 0) if run else 0
    assert runs and max(runs) >= 3


def test_crosstalk_arrival_window():
    s = usm.DEFAULT_SPEC
    assert math.isclose(usm.crosstalk_range(.7, 0., s), .35)
    assert usm.crosstalk_range(.7, -.01, s) is None                 # arrived before our trigger
    assert usm.crosstalk_range(.7, .05, s) is None                  # after the 4 m listening window


# --- static map prediction -----------------------------------------------------------------------

WALL_MAP = {'obstacles': [{'id': 'w', 'center_m': [1.025, 0.], 'half_extents_m': [.025, 2.], 'height_m': .10}]}


def test_map_prediction_wall_head_on_oblique_and_beyond_visibility():
    face = 1.0
    sensor_x = usm.DEFAULT_SPEC.face_x_m
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
    assert r.echo and r.range_m >= .58 - usm.DEFAULT_SPEC.face_x_m - 1e-9
    assert not um.expected_range({'obstacles': []}, (0., 0., 0.), EXACT).echo      # floor alone: grazing
    far = {'obstacles': [{'id': 'w', 'center_m': [4.2, 0.], 'half_extents_m': [.025, 3.], 'height_m': .1}]}
    assert not um.expected_range(far, (0., 0., 0.), EXACT).echo


def test_consistency_and_likelihood_are_asymmetric_but_soft_and_bounded():
    exp = um.ExpectedRange(1.0, usm.DEFAULT_SPEC.sigma_m(1.))
    assert um.range_consistency(1.005, True, exp) == um.CONSISTENT
    assert um.range_consistency(1.05, True, exp) == um.CONSISTENT          # map error (2 cm sigma) absorbs 5 cm
    assert um.range_consistency(.40, True, exp) == um.SHORTER
    assert um.range_consistency(1.5, True, exp) == um.LONGER
    assert um.range_consistency(None, False, exp) == um.MISSING_ECHO
    assert um.range_consistency(.4, True, um.ExpectedRange(None, None)) == um.UNEXPECTED_ECHO
    assert um.range_consistency(None, False, um.ExpectedRange(None, None)) == um.BOTH_NONE
    assert um.range_consistency(None, False, exp, status='blind') == um.BLIND_READING
    ll = lambda z: um.range_log_likelihood(z, True, exp)
    ref = math.log(1. / (usm.DEFAULT_SPEC.max_range_m - usm.DEFAULT_SPEC.min_range_m))
    assert ll(1.0) > ll(.4) > ll(1.5)          # unmapped object in front is more plausible than a long reading
    assert all(abs(ll(z) - ref) <= 2. + 1e-9 for z in (.05, .4, 1., 1.05, 1.5, 3.9))       # bounded evidence
    assert ll(1.05) > ll(1.2) > ref - 2. - 1e-9
    # no knife-edge: the invalid-reading likelihood is continuous in the detection probability
    inv = lambda p: um.range_log_likelihood(None, False, um.ExpectedRange(None, None, p, 1.5))
    assert abs(inv(.49) - inv(.51)) < .05
    assert um.range_log_likelihood(None, False, exp) < um.range_log_likelihood(None, False, um.ExpectedRange(None, None))


def test_visibility_edge_is_soft_in_the_map_model():
    """Yaw sweep across the specular visibility edge: p_detect and the invalid LL change smoothly."""
    pts = []
    for yaw in np.arange(30., 42., .5):
        e = um.expected_range(WALL_MAP, (0., 0., math.radians(yaw)), EXACT)
        pts.append((e.p_detect, um.range_log_likelihood(None, False, e)))
    p = [a for a, _ in pts]
    assert p[0] > .5 > p[-1]
    assert max(abs(b - a) for (_, a), (_, b) in zip(pts, pts[1:])) < 1.


def test_expected_range_uses_real_zone_map_walls_and_door_posts():
    static = json.loads((ROOT / 'maps/zones/zone_wide_door_tags_v2.json').read_text())
    ids = {b['id'] for b in um.static_boxes(static)}
    assert {'wall_divider_1', 'post_door_1_lo'} <= ids
    r = um.expected_range(static, (1.6, -2.5, 0.), EXACT)
    assert math.isclose(r.range_m, 2.175 - (1.6 + .084), abs_tol=1e-9)


# --- provider, history, conditions ---------------------------------------------------------------

def test_provider_reports_time_age_source_sigma_and_limits():
    p = rp.OwnUltrasonicRangeProvider()
    assert p.report(0.).t_meas is None
    assert rp.check_range_limits(p.report(0.), 0., rp.RangeLimits()) == ['no_reading']
    p.on_reading(usm.RangeReading(1.00, .500, True))
    p.on_reading(usm.invalid(1.06, usm.NO_ECHO))
    rep = p.report(1.10)
    assert (rep.t_meas, rep.valid) == (1.06, False) and math.isclose(rep.age_s, .04)
    assert rep.last_valid_t == 1.00 and rep.source.startswith(rp.SOURCE_PREFIX + ':')
    assert rp.check_range_limits(rep, 1.10, rp.RangeLimits()) == ['invalid'] and rep.status == usm.NO_ECHO
    assert rep.last_valid_range_m == .5
    p.on_reading(usm.RangeReading(1.12, .480, True))
    rep = p.report(1.50)
    assert rep.valid and rep.range_m == .480 and math.isclose(rep.sigma_m, usm.DEFAULT_SPEC.sigma_m(.48))
    assert rp.check_range_limits(rep, 1.50, rp.RangeLimits(max_age_s=.2)) == ['stale']
    assert p.report(1.03).t_meas == 1.00            # a report never uses a later reading
    assert [r.t for r in p.history(1.12, .1)] == [1.06, 1.12]
    with pytest.raises(ValueError):
        p.on_reading(usm.RangeReading(1.0, .5, True))
    assert set(rep.as_dict()) == {'t_meas', 'age_s', 'valid', 'range_m', 'sigma_m', 'min_range_m',
                                  'max_range_m', 'last_valid_t', 'source', 'status', 'last_valid_range_m'}
    p.on_reading(usm.invalid(1.60, usm.BLIND))
    assert rp.check_range_limits(p.report(1.6), 1.6, rp.RangeLimits()) == ['blind']


def test_sdk_values_map_to_statuses():
    assert rp.reading_from_sdk(0., 99999).status == usm.SENSOR_ABSENT
    assert rp.reading_from_sdk(0., 12).status == usm.BLIND
    assert rp.reading_from_sdk(0., 5000).status == usm.NO_ECHO
    assert rp.reading_from_sdk(0., 4001).status == usm.NO_ECHO
    ok = rp.reading_from_sdk(1., 694)
    assert ok.valid and ok.range_m == .694
    p = rp.OwnUltrasonicRangeProvider()
    for k, v in enumerate((99999, 12, 5000, 694)):
        p.on_reading(rp.reading_from_sdk(float(k), v))            # never raises on raw SDK values


def test_history_file_has_only_reading_fields(tmp_path):
    path = tmp_path / 'r1' / 'ultrasonic.jsonl'
    seed = usm.sensor_seed(11, 'r1')
    with rp.RangeHistoryWriter(path, 'r1', noise_seed=seed, run_meta={'run_id': 'unit'}) as w:
        w.append(usm.RangeReading(.0, .5, True))
        w.append(usm.invalid(.06, usm.BLIND))
    header, rows = rp.read_history(path)
    assert header['spec_sha256'] == usm.spec_record()['sha256'] and header['robot_id'] == 'r1'
    assert header['noise_seed'] == str(seed) and 'tick' in header['noise_index_rule']
    assert [r.as_dict() for r in rows] == [{'t': 0., 'range_m': .5, 'valid': True, 'status': 'ok'},
                                           {'t': .06, 'range_m': None, 'valid': False, 'status': 'blind'}]
    with pytest.raises(FileExistsError):
        rp.RangeHistoryWriter(path, 'r1', noise_seed=seed)
    with pytest.raises(TypeError):
        rp.RangeHistoryWriter(tmp_path / 'x.jsonl', 'r1')              # the seed is mandatory


def test_same_provider_config_in_all_four_conditions():
    from harness.zone_study_contract import MAIN_CONDITIONS
    assert len(MAIN_CONDITIONS) == 4
    configs = {name: rp.provider_config_for_condition(name) for name in MAIN_CONDITIONS}
    assert len({json.dumps(c, sort_keys=True) for c in configs.values()}) == 1
    assert 'episode_seed' in next(iter(configs.values()))['noise_seed_rule']
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


def test_executors_never_touch_the_diagnostic_api():
    """Only the reading (measure/due) may reach a controller; diagnostics stay in tests/analysis."""
    allowed = {'sim/ultrasonic_range.py', 'scripts/analyze_ultrasonic_carry_height.py'}
    bad = []
    for path in list((ROOT / 'harness').glob('*.py')) + list((ROOT / 'scripts').glob('*.py')) + list((ROOT / 'sim').glob('*.py')):
        rel = str(path.relative_to(ROOT))
        if rel in allowed:
            continue
        tree = ast.parse(path.read_text())
        names = {n.attr for n in ast.walk(tree) if isinstance(n, ast.Attribute)}
        if names & {'measure_diagnostic', 'true_first_echo', 'noisy_reading_with_cause'} or (
                'MujocoUltrasonic' in path.read_text() and 'cast' in names):
            bad.append(rel)
    assert not bad


def test_spec_matches_the_sim_appearance_geometry():
    from sim.masterpi_geometry import NOMINAL_ULTRASONIC_X_M
    assert usm.DEFAULT_SPEC.mount_x_m == NOMINAL_ULTRASONIC_X_M
    src = (ROOT / 'sim/masterpi_dynamics_v2.py').read_text()
    assert 'name="ultrasonic_left" type="cylinder"' in src and usm.DEFAULT_SPEC.face_forward_m == .006
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


def _arm(model, data, rid, pulses):
    from scripts.analyze_ultrasonic_carry_height import set_arm
    return set_arm(model, data, rid, pulses)


SEED = usm.sensor_seed(11, 'r1')


def test_sim_wall_matches_static_map_prediction(beam_scene):
    import mujoco
    from sim.ultrasonic_range import MujocoUltrasonic
    scene, model, data, inst = beam_scene
    _beam(model, data, inst)
    _park_others(model, data, 'r2', 'r3')
    sensor = MujocoUltrasonic(model, data, 'r1', seed=SEED, spec=EXACT)
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
    reading = sensor.measure(0.)
    assert not reading.valid and reading.status == usm.NO_ECHO


def test_beam_on_floor_is_below_the_sensor_but_inside_the_cone(beam_scene):
    """Floor beam spans z 0.5-32.5 mm; the sensor axis is at 54 mm. Gaps are from the transducer face."""
    import mujoco
    from sim.ultrasonic_range import MujocoUltrasonic
    scene, model, data, inst = beam_scene
    _beam(model, data, inst, yaw=math.pi / 2)            # long side facing the robot (face at x = 0.98)
    _park_others(model, data, 'r2', 'r3')
    sensor = MujocoUltrasonic(model, data, 'r1', seed=SEED, spec=EXACT)
    face = BEAM_POSE[0] - .02
    seen = {}
    for gap in (.05, .07, .10, .20, .50, 1.0, 1.5):
        _robot(model, data, 'r1', face - gap - usm.DEFAULT_SPEC.face_x_m, BEAM_POSE[1], 0.)
        mujoco.mj_forward(model, data)
        r = sensor.true_first_echo()
        seen[gap] = r is not None and abs(r - gap) < .01
    # Near: the bar top is 21.5 mm below the axis, reachable only >= 8 cm from the face (15 deg edge).
    # Far: the largest ray-free gap inside the cone is ~2.2 deg (ring spacing), so a 32 mm bar is lost
    # beyond ~0.8 m where it subtends less than ~2.2 deg below the axis (ray-resolution limit, documented).
    assert seen == {.05: False, .07: False, .10: True, .20: True, .50: True, 1.0: True, 1.5: False}


def test_real_grasp_pose_sees_the_own_gripper_and_lift_sees_the_partner(beam_scene):
    """Carry formation with the REAL arm poses (calibrated IK), own arm and held load never excluded."""
    import mujoco
    from harness import ultrasonic_carry as uc
    from sim.ultrasonic_range import MujocoUltrasonic
    from sim.zone_cargo import GRASP_RADIUS_M
    scene, model, data, inst = beam_scene
    _park_others(model, data, 'r3')
    grip = .30 - .03
    x1, x2 = BEAM_POSE[0] - grip - GRASP_RADIUS_M, BEAM_POSE[0] + grip + GRASP_RADIUS_M
    _robot(model, data, 'r1', x1, BEAM_POSE[1], 0.)
    _robot(model, data, 'r2', x2, BEAM_POSE[1], math.pi)
    for rid in ('r1', 'r2'):
        _arm(model, data, rid, uc.grasp_pose())
    _beam(model, data, inst)
    mujoco.mj_forward(model, data)
    r1 = MujocoUltrasonic(model, data, 'r1', seed=SEED, spec=EXACT)
    _, diag = r1.measure_diagnostic(0.)
    # the physical sensor sees its own gripper descending in front of it (review P1)
    assert diag['echo_is_own_arm'] and diag['echo_geom'].startswith('r1__') and diag['true_first_echo_m'] < .12
    # lifted to the recommended carry height: the own gripper/wrist and the bar leave the cone
    lift = uc.lift_ik(uc.recommended_carry_tool_z())
    for rid in ('r1', 'r2'):
        _arm(model, data, rid, lift['pulses'])
    _beam(model, data, inst, z=uc.expected_bar_bottom(lift['tool_z_m']))
    mujoco.mj_forward(model, data)
    _, diag = r1.measure_diagnostic(0.)
    assert not diag['echo_is_own_arm'] and diag['echo_geom'].startswith('r2__')
    # M2 lift height: the held bar's end face is the first echo (the load is never excluded)
    m2 = uc.lift_ik(uc.M2_LIFT_TOOL_Z_M)
    _arm(model, data, 'r1', m2['pulses'])
    _beam(model, data, inst, z=LIFTED_BEAM_BODY_Z_M)
    mujoco.mj_forward(model, data)
    end_face = BEAM_POSE[0] - .30 - (x1 + usm.DEFAULT_SPEC.face_x_m)
    _, diag = r1.measure_diagnostic(0.)
    assert diag['echo_geom'] == inst.body + '__bar' and abs(diag['true_first_echo_m'] - end_face) < .005
    import inspect
    for fn in (r1.measure, r1.cast, MujocoUltrasonic):
        assert not any('exclude' in p for p in inspect.signature(fn).parameters)   # no API to hide arm/load


def test_peer_robot_is_detected_and_crosstalk_comes_in_bursts(beam_scene):
    import mujoco
    from sim.ultrasonic_range import MujocoUltrasonic
    scene, model, data, inst = beam_scene
    _free(model, data, inst.joint, 4.8, -2.9, .0005, 0.)                # beam out of the way
    _park_others(model, data, 'r3')
    _robot(model, data, 'r1', .0, -1.2, 0.)
    _robot(model, data, 'r2', .9, -1.2, math.pi)
    for rid in ('r1', 'r2'):
        _arm(model, data, rid, {1: 1500, 3: 500, 4: 2500, 5: 1500, 6: 1500})   # folded up, out of the cone
    mujoco.mj_forward(model, data)
    chassis_gap = (.9 - .0925) - usm.DEFAULT_SPEC.face_x_m
    base = replace(usm.DEFAULT_SPEC, dropout_prob=0., outlier_prob=0.)
    s1, s2 = usm.sensor_seed(5, 'r1'), usm.sensor_seed(5, 'r2')
    off1 = MujocoUltrasonic(model, data, 'r1', seed=s1, spec=base)
    off2 = MujocoUltrasonic(model, data, 'r2', seed=s2, spec=base)
    _, diag = off1.measure_diagnostic(0.)
    gap = diag['true_first_echo_m']
    assert diag['echo_geom'].startswith('r2__') and chassis_gap - .2 < gap <= chassis_gap + .01
    off = [off1.measure(k * .06, peers=[off2]).range_m for k in range(60)]
    assert max(abs(v - gap) for v in off) < .05
    on1 = MujocoUltrasonic(model, data, 'r1', seed=s1, spec=replace(base, crosstalk=True))
    on2 = MujocoUltrasonic(model, data, 'r2', seed=s2, spec=replace(base, crosstalk=True))
    short = [(lambda r: not r.valid or r.range_m < gap - .05)(on1.measure(k * .06, peers=[on2])) for k in range(3000)]
    runs, run = [], 0
    for h in short + [False]:
        if h:
            run += 1
        elif run:
            runs.append(run)
            run = 0
    # phase-correlated interference: corrupted readings arrive in bursts that a 3-reading debounce cannot filter
    assert runs and max(runs) >= 3
    # peer turned away: its transmit cone misses us -> no crosstalk
    _robot(model, data, 'r2', .9, -1.2, math.pi / 2)
    mujoco.mj_forward(model, data)
    turned = [on1.measure_diagnostic(k * .06, peers=[on2])[1]['crosstalk_m'] for k in range(30)]
    assert turned == [None] * 30 and on1.true_first_echo() is not None


def test_own_arm_is_seen_chassis_is_not_and_readings_carry_no_sim_state():
    if not HAS_MUJOCO:
        pytest.skip('mujoco is not installed')
    import mujoco
    from sim.ultrasonic_range import MujocoUltrasonic
    _, model, data = _scene([])
    _robot(model, data, 'r1', .3, -1.2, 0.)
    _park_others(model, data, 'r2', 'r3')
    for joint, value in (('r1__shoulder', -.15), ('r1__elbow', -1.5), ('r1__wrist_pitch', 1.5)):
        data.qpos[model.jnt_qposadr[mujoco.mj_name2id(model, mujoco.mjtObj.mjOBJ_JOINT, joint)]] = value
    mujoco.mj_forward(model, data)
    sensor = MujocoUltrasonic(model, data, 'r1', seed=SEED, spec=EXACT)
    names = lambda ids: {mujoco.mj_id2name(model, mujoco.mjtObj.mjOBJ_BODY, b) for b in ids}
    assert names(sensor.chassis_side) == {'r1__robot', 'r1__wheel_fl_body', 'r1__wheel_fr_body',
                                          'r1__wheel_rl_body', 'r1__wheel_rr_body'}
    assert 'r1__gripper' in names(sensor.arm_bodies) and 'r1__arm_base' in names(sensor.arm_bodies)
    reading, diag = sensor.measure_diagnostic(2.0)
    # the folded gripper hangs in front of the sensor: the physical sensor sees it, so does the SIM
    assert diag['echo_is_own_arm'] and diag['true_first_echo_m'] < .2
    assert reading.status in (usm.OK, usm.BLIND)             # closer than 2 cm -> blind, never 'clear'
    assert not any(h.startswith('r1__ultrasonic') for h in diag['hit_geoms'])     # rays start at the face
    assert set(reading.as_dict()) == {'t', 'range_m', 'valid', 'status'}
    assert sensor.due(2.05) is False and sensor.due(2.06) is True
    with pytest.raises(TypeError):
        MujocoUltrasonic(model, data, 'r1')                  # the noise seed is mandatory


def test_sim_readings_are_seed_deterministic_and_tick_matched():
    if not HAS_MUJOCO:
        pytest.skip('mujoco is not installed')
    import mujoco
    from sim.ultrasonic_range import MujocoUltrasonic
    _, model, data = _scene([])
    _robot(model, data, 'r1', 1.6, -2.5, 0.)
    _park_others(model, data, 'r2', 'r3')
    mujoco.mj_forward(model, data)
    a = MujocoUltrasonic(model, data, 'r1', seed=usm.sensor_seed(9, 'r1'))
    b = MujocoUltrasonic(model, data, 'r1', seed=usm.sensor_seed(9, 'r1'))
    c = MujocoUltrasonic(model, data, 'r1', seed=usm.sensor_seed(10, 'r1'))
    ra = [a.measure(k * .06).as_dict() for k in range(50)]
    rb = [b.measure(k * .06).as_dict() for k in range(0, 50, 2)]          # fewer calls, same times
    rc = [c.measure(k * .06).as_dict() for k in range(50)]
    assert ra[::2] == rb and ra != rc


def test_suite_is_in_the_portable_ci_list():
    import fnmatch
    from scripts.run_ci_tests import TEST_PATTERNS
    assert any(fnmatch.fnmatch('tests/test_ultrasonic_range.py', pat) for pat in TEST_PATTERNS)
