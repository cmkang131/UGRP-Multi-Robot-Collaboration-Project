"""Synthetic VIS6 (recipe #1) checks only: no replay of the real dataset, no model calls, renderer or physics."""
import copy
import hashlib
import json
import math
import re
import sys
from pathlib import Path
from types import ModuleType

import numpy as np
import pytest

ROOT = Path(__file__).resolve().parents[1]
HERE = ROOT/'experiments/2026-09-26-vision-loc'
PLAN = ROOT/'experiments/2026-09-28-vis6-recipe1'
M1_FIXTURE = ROOT/'tests/fixtures/vision_loc_v5_off/owncam_localizer_m1.py.txt'
M1_SHA256 = '0304d7c491dfe6ae68cea6550f7a13e3c99e8e1d3f8e8b6c4b7b1d06893b1d63'
sys.path.insert(0, str(HERE))
sys.path.insert(0, str(PLAN))
import vis6_metrics as vm6  # noqa: E402
import vision_loc as vl  # noqa: E402
import vision_pf_v5 as pf5  # noqa: E402
import vision_pf_v6 as pf6  # noqa: E402
import vision_stall_v6 as vst  # noqa: E402

POSE = {1: 2000, 3: 740, 4: 2320, 5: 1320, 6: 1500}
STALL_CFG = vst.validate_stall({})


def m1_module():
    src = M1_FIXTURE.read_bytes()
    assert hashlib.sha256(src).hexdigest() == M1_SHA256, 'M1 fixture hash mismatch'
    mod = ModuleType('owncam_localizer_m1')
    mod.__file__ = str(M1_FIXTURE)
    exec(compile(src, str(M1_FIXTURE), 'exec'), mod.__dict__)
    return mod


M1 = m1_module()
MAP = json.loads((HERE/'maps/zone_wide_door_walls_v3_notags.json').read_text())
CAL = json.loads((HERE/'calibration_train.json').read_text())


def params(n=32):
    p = copy.deepcopy(M1.DEFAULT_PARAMS)
    p['particles'] = n
    return p


def make(vis6=None, n=32, seed=42, **kw):
    return pf6.make_vis6_pf(M1, MAP, params(n), {}, {}, CAL['sag'], seed, vis6=vis6, **kw)


def make5(n=32, seed=42):
    return pf5.make_robust_pf(M1, MAP, params(n), {}, {}, CAL['sag'], seed)


def start(loc, x=0.):
    loc.init_gaussian([x, 0., 0.], [.05, .03, .02])
    loc.command({'t': 0., 'kind': 'initial_servo_command', 'pulses': POSE})


def flat_scan(columns, row=200.):
    n = len(columns)
    return vl.ColumnObs(columns, np.full(n, vl.EDGE), np.full(n, row), np.full(n, row), np.full(n, vl.NONE),
                        np.full(n, np.nan), np.full(n, np.nan))


# ----------------------------------------------------------------------------- configuration
@pytest.mark.parametrize('bad', [[], {'foo': 1}, {'eta': 0}, {'eta': 1.5}, {'eta': float('nan')}, {'eta': True},
                                 {'gating': {'min_d_m': .05, 'min_yaw_rad': .1}},        # gating without 1c
                                 {'stall': {}, 'gating': {'min_d_m': .05}},
                                 {'stall': {}, 'gating': {'min_d_m': .05, 'min_yaw_rad': .1, 'mode': 'x'}},
                                 {'stall': {}, 'gating': {'min_d_m': 0, 'min_yaw_rad': .1}},
                                 {'stall': {'scales': [.25, 1.]}}, {'stall': {'scales': [0., .5, .75]}},
                                 {'stall': {'gain': 0}}, {'stall': {'bogus': 1}}, {'stall': {'blur_ksize': 4}},
                                 {'range': {'enabled': 1}}])
def test_bad_configs_rejected(bad):
    with pytest.raises(ValueError):
        pf6.validate_vis6(bad)


def test_range_hook_needs_a_provider_and_off_refuses_one():
    with pytest.raises(ValueError):
        make({'range': {'enabled': True}})
    with pytest.raises(ValueError):
        make({}, range_provider=lambda px, r: np.zeros(len(px)))


def test_stacking_on_rejected_report_heads_refused():
    with pytest.raises(ValueError):
        pf6.make_vis6_pf(M1, MAP, params(), {}, {}, CAL['sag'], 1, report_v5={'enabled': True}, vis6={'eta': .5})


# ----------------------------------------------------------------------------- OFF == VIS5
@pytest.mark.parametrize('off', [None, {}, {'eta': 1.}, {'range': {'enabled': False}}])
def test_off_is_the_vis5_filter_bit_for_bit(off):
    a, b = make5(), make(off)
    assert not hasattr(b, 'vis6')
    for loc in (a, b):
        start(loc)
        loc.command({'t': .05, 'kind': 'mecanum', 'forward': .1, 'left': .02, 'turn': .1, 'duration_s': .6})
    scan = flat_scan(a.columns)
    for t in (.1, .4, .6, .8, 1.):
        ra = a.update_obs(t, None if t < .2 else scan, a.servo)
        rb = b.update_obs(t, None if t < .2 else scan, b.servo)
        assert ra == rb
        assert np.array_equal(a.px, b.px) and np.array_equal(a.logw, b.logw)
        assert a.rng.bit_generator.state == b.rng.bit_generator.state


# ----------------------------------------------------------------------------- 1b
def test_eta_scales_the_applied_scan_loglik_exactly():
    a, b = make5(), make({'eta': .25})
    for loc in (a, b):
        start(loc)
    scan = flat_scan(a.columns)
    la, na = a.scan_loglik(scan, a.servo)
    lb, nb = b.scan_loglik(scan, b.servo)
    assert na == nb and np.allclose(lb, .25*la)
    a0, b0 = a.logw.copy(), b.logw.copy()
    a.apply_scan(.5, scan, a.servo)
    b.apply_scan(.5, scan, b.servo)
    assert np.allclose(b.logw - b0, .25*(a.logw - a0))


# ----------------------------------------------------------------------------- 1a
def test_gate_rules():
    g = pf6.UpdateGate({'min_d_m': .05, 'min_yaw_rad': .1, 'min_servo_pulse': 10, 'mode': 'skip'})
    p = (740, 2320, 1320, 1500)
    d = g.decide(p)
    assert d == {'apply': True, 'weight': 1., 'reason': 'first'}
    g.commit(p, d)
    assert g.decide(p)['reason'] == 'static' and not g.decide(p)['apply']
    g.add_motion(.03, 0.)
    assert not g.decide(p)['apply']
    g.add_motion(.021, 0.)
    assert g.decide(p)['reason'] == 'moved'
    g.commit(p, g.decide(p))
    assert g.d == 0. and not g.decide(p)['apply']
    g.add_motion(0., -.11)
    assert g.decide(p)['reason'] == 'turned'
    g.commit(p, g.decide(p))
    assert g.decide((740, 2320, 1320, 1509))['reason'] == 'static'
    assert g.decide((740, 2320, 1320, 1510))['reason'] == 'view'
    assert pf6.UpdateGate(None).decide(p) == {'apply': True, 'weight': 1., 'reason': 'off'}


def test_discount_mode_weights_repeats_one_over_k_plus_one():
    g = pf6.UpdateGate({'min_d_m': .05, 'min_yaw_rad': .1, 'min_servo_pulse': 10, 'mode': 'discount'})
    p = (1, 2, 3, 4)
    g.commit(p, g.decide(p))
    ws = []
    for _ in range(3):
        d = g.decide(p)
        ws.append(d['weight'])
        g.commit(p, d)
    assert ws == [1/2, 1/3, 1/4]
    g.add_motion(.06, 0.)
    d = g.decide(p)
    g.commit(p, d)
    assert d['weight'] == 1. and g.repeats == 0


def test_gating_skips_repeated_scans_of_a_static_robot():
    cfg = {'stall': {}, 'gating': {'min_d_m': .05, 'min_yaw_rad': .1, 'min_servo_pulse': 10, 'mode': 'skip'}}
    loc = make(cfg)
    start(loc)
    scan = flat_scan(loc.columns)
    reps = [loc.update_obs(t, scan, loc.servo) for t in (.5, .7, .9, 1.1)]
    assert [r['measured'] for r in reps] == [True, False, False, False]
    assert loc.stats['gated_skips'] == 3 and loc.stats['scan_updates'] == 1
    assert reps[1]['vis6']['gate']['reason'] == 'static'
    # a new view (pan command) re-opens the gate once the arm has settled
    loc.command({'t': 1.2, 'kind': 'look', 'pan_pulse': 1600})
    assert not loc.update_obs(1.3, scan, loc.servo)['measured']       # unsettled
    assert loc.update_obs(2., scan, loc.servo)['vis6']['gate']['reason'] == 'view'


# ----------------------------------------------------------------------------- 1c detector
def render_floor(origin, rot, delta=(0., 0., 0.), texture='sine'):
    """Undistorted gray image of a textured floor seen from base pose ``delta`` (in the reference base frame)."""
    h, w = vl.HEIGHT, vl.WIDTH
    vv, uu = np.mgrid[0:h, 0:w].astype(float)
    ray = rot @ (vl.mp.K_INV @ np.stack([uu.ravel(), vv.ravel(), np.ones(uu.size)]))
    down = ray[2] < -1e-6
    lam = np.where(down, -origin[2]/np.where(down, ray[2], -1.), np.nan)
    qx, qy = origin[0] + ray[0]*lam, origin[1] + ray[1]*lam
    dx, dy, dyaw = delta
    c, s = math.cos(dyaw), math.sin(dyaw)
    wx, wy = c*qx - s*qy + dx, s*qx + c*qy + dy
    if texture == 'sine':
        img = 128 + 45*np.sin(2*math.pi*wx/.15)*np.cos(2*math.pi*wy/.13) + 20*np.sin(2*math.pi*(wx + wy)/.37)
    else:
        img = np.full(wx.shape, 128.)
    img = np.where(down, img, 60.)
    return img.reshape(h, w).astype(np.float32)


@pytest.fixture(scope='module')
def camera():
    loc = make()
    start(loc)
    return vst.camera_pose(loc.column_model_for(POSE))


@pytest.mark.parametrize('true_move,expect', [((0., 0., 0.), 'stall'), ((.03, 0., 0.), 'moving'),
                                              ((.004, 0., 0.), 'stall')])
def test_stall_test_on_a_synthetic_floor(camera, true_move, expect):
    origin, rot = camera
    i0 = render_floor(origin, rot)
    i1 = render_floor(origin, rot, true_move)
    res = vst.stall_test(i0, i1, origin, rot, (.03, 0., 0.), STALL_CFG)
    assert res['decision'] == expect, res
    assert res['pred_px'] >= STALL_CFG['min_pred_px']


def test_stall_test_abstains_without_texture_or_power(camera):
    origin, rot = camera
    flat = render_floor(origin, rot, texture='flat')
    res = vst.stall_test(flat, flat, origin, rot, (.03, 0., 0.), STALL_CFG)
    assert res['decision'] == 'unknown' and res['reason'] == 'few_textured_floor_points'
    tex = render_floor(origin, rot)
    res = vst.stall_test(tex, tex, origin, rot, (.0005, 0., 0.), STALL_CFG)
    assert res['decision'] == 'unknown' and res['reason'] == 'small_predicted_motion'


def test_projection_identity_and_turn(camera):
    origin, rot = camera
    u, v, q = vst.sample_points(render_floor(origin, rot), origin, rot, STALL_CFG)
    u0, v0 = vst.project(q, (0., 0., 0.), origin, rot)
    assert np.allclose(u0, u, atol=1e-6) and np.allclose(v0, v, atol=1e-6)
    u1, _ = vst.project(q, (0., 0., .05), origin, rot)
    # after a left turn a floor point seen at u was further left (smaller u) in the earlier view
    assert np.nanmedian(u1 - u) < -1.


def test_floor_rows_from_observation():
    cols = np.array([10, 300, 600])
    obs = vl.ColumnObs(cols, np.array([vl.EDGE, vl.INTERVAL, vl.NONE]), np.array([100., 150., np.nan]),
                       np.array([100., vl.POS_INF, np.nan]), np.zeros(3, int), np.full(3, np.nan), np.full(3, np.nan))
    rows = vst.floor_min_rows(obs, margin_px=4.)
    assert rows[0] == 104. and rows[300] == vl.HEIGHT and rows[639] == vl.HEIGHT


def test_checker_size_matches_the_scene_source():
    xml = (ROOT/'sim/masterpi_scene_v2.xml').read_text()
    tex = re.search(r'<texture name="ground"[^>]*>', xml).group(0)
    mat = re.search(r'<material name="groundmat"[^>]*>', xml).group(0)
    assert 'builtin="checker"' in tex and 'texuniform' not in mat
    rep = [float(x) for x in re.search(r'texrepeat="([^"]+)"', mat).group(1).split()]
    arena = (ROOT/'sim/zone_arena.py').read_text()
    half = float(re.search(r"floor\.set\('size', '([0-9.]+) ", arena).group(1))
    assert rep == [vst.CHECKER['texrepeat']]*2 and 2*half == vst.CHECKER['plane_side_m']
    assert vst.CHECKER['square_m'] == pytest.approx(2*half/rep[0]/2) == pytest.approx(.571428, abs=1e-6)


# ----------------------------------------------------------------------------- 1c inside the PF
def run_forward(stall, monkeypatch, same_image=True):
    loc = make({'stall': {}} if stall else {'stall': {'min_points': 1000000, 'max_points': 1000000}})
    start(loc)
    loc.command({'t': .45, 'kind': 'mecanum', 'forward': .12, 'left': 0., 'turn': 0., 'duration_s': 2.})
    origin, rot = vst.camera_pose(loc.column_model_for(POSE))
    monkeypatch.setattr(vst, 'prepare', lambda img, k: img)
    imgs = [render_floor(origin, rot), render_floor(origin, rot, (0., 0., 0.) if same_image else (.03, 0., 0.))]
    loc.update_obs(.6, None, loc.servo, image=imgs[0])
    before = loc.px.copy()
    rep = loc.update_obs(.8, None, loc.servo, image=imgs[1])
    return loc, before, rep


def test_stall_pulls_the_prediction_back(monkeypatch):
    loc, before, rep = run_forward(True, monkeypatch)
    assert rep['vis6']['stall']['decision'] == 'stall', rep['vis6']
    assert rep['vis6']['stall']['pred_m'] > .01
    assert not np.allclose(loc.px, before) and np.linalg.norm(loc.vel) > 0.
    assert np.linalg.norm(np.mean(loc.px[:, :2] - before[:, :2], axis=0)) < .001
    assert loc.stats['stall_frames'] == 1 and rep['vis6']['motion'][0] < .001
    ref, before_ref, _ = run_forward(False, monkeypatch)
    assert np.mean(ref.px[:, 0] - before_ref[:, 0]) > .01


def test_stall_not_triggered_when_the_image_moves(monkeypatch):
    loc, before, rep = run_forward(True, monkeypatch, same_image=False)
    assert rep['vis6']['stall']['decision'] == 'moving'
    assert loc.stats['stall_frames'] == 0 and np.mean(loc.px[:, 0] - before[:, 0]) > .01


def test_stall_skipped_across_an_arm_change(monkeypatch):
    loc = make({'stall': {}})
    start(loc)
    monkeypatch.setattr(vst, 'prepare', lambda img, k: img)
    img = np.zeros((vl.HEIGHT, vl.WIDTH), np.float32)
    loc.update_obs(.6, None, loc.servo, image=img)
    loc.command({'t': .65, 'kind': 'look', 'pan_pulse': 1520})
    rep = loc.update_obs(.8, None, loc.servo, image=img)
    assert rep['vis6']['stall']['reason'] == 'not_a_static_arm_pair' and loc.stats['stall_tests'] == 0


# ----------------------------------------------------------------------------- recipe #2 hook
def test_range_hook_applies_eta_tempered_provider():
    calls = []

    def provider(px, reading):
        calls.append((reading, px.copy()))
        return -((px[:, 0] - reading['x'])/.05)**2

    loc = make({'eta': .5, 'range': {'enabled': True}}, n=200, range_provider=provider)
    start(loc)
    loc.predict_to(.1)
    w0 = loc.logw.copy()
    loc._normalize_and_resample = lambda: None           # inspect the raw weight change
    loc.update_range(.1, {'x': .02})
    (reading, px), = calls
    assert reading == {'x': .02} and np.array_equal(px, loc.px) and loc.stats['range_updates'] == 1
    assert np.allclose(loc.logw - w0, .5*(-((px[:, 0] - .02)/.05)**2))


# ----------------------------------------------------------------------------- metrics and rules
def test_frame_terms_values():
    r = vm6.frame_terms([.1, 0., .1], [[.01, 0, 0], [0, .04, 0], [0, 0, .01]], [0., 0., 0.])
    assert r['nees_xy'] == pytest.approx(1., rel=1e-5) and r['nees_yaw'] == pytest.approx(1., rel=1e-6)
    assert r['nll_xy'] == pytest.approx(.5 + .5*math.log((2*math.pi)**2*.0004), rel=1e-4)
    assert r['std_xy_m'] == pytest.approx(math.sqrt(.05))
    with pytest.raises(ValueError):
        vm6.frame_terms([0, 0, 0], [[0, 0, 0], [0, -1, 0], [0, 0, 0]], [0, 0, 0])


def test_consistent_gaussian_has_nominal_coverage():
    rng = np.random.default_rng(0)
    cov = np.array([[.02, .006], [.006, .01]])
    e = rng.multivariate_normal([0, 0], cov, 4000)
    full = np.zeros((3, 3))
    full[:2, :2], full[2, 2] = cov, 1e-4
    rows = [{**vm6.frame_terms([x, y, 0.], full, [0., 0., 0.]), 'frame': i, 't': .2*i, 'groups': ['all']}
            for i, (x, y) in enumerate(e)]
    s = vm6.summarize({'ep': rows})
    assert abs(s['coverage95_xy'] - .95) < .015 and abs(s['anees_xy'] - 2.) < .12 and s['exceed3_xy'] < .01


def test_events_split_at_gaps():
    mk = lambda f, t, err: {'frame': f, 't': t, 'err_m': err, 'std_xy_m': .01}
    rows = [mk(0, 0., .5), mk(1, .2, .5), mk(2, .4, .01), mk(3, .6, .5), mk(5, 1., .5), mk(6, 2.5, .5)]
    assert vm6.events(rows) == {'events': 0, 'frames': 5, 'longest_frames': 0}


def test_select_calibrated_band_nll_and_ties():
    st = {'T0': {'coverage95_xy': .6, 'nll_xy': -5.}, 'a': {'coverage95_xy': .91, 'nll_xy': -2.},
          'b': {'coverage95_xy': .97, 'nll_xy': -3.}, 'c': {'coverage95_xy': .995, 'nll_xy': -9.}}
    assert vm6.select_calibrated(st, ['T0', 'a', 'b', 'c'])['chosen'] == 'b'
    st['a']['nll_xy'] = -3.
    assert vm6.select_calibrated(st, ['T0', 'a', 'b', 'c'])['chosen'] == 'a'
    assert vm6.select_calibrated({'T0': st['T0']}, ['T0'])['chosen'] is None


def test_validation_gate():
    base = {'coverage95_xy': .6, 'exceed3_xy': .2, 'door_pos_p90_m': .059, 'door_lat_p99_m': .043,
            'door_yaw_p90_deg': 2.6, 'sigma_xy_p90_loaded_m': .04, 'nll_xy_by_episode': {'a': -3., 'b': -2.},
            'events': 1, 'event_frames': 911, 'sigma_xy_p90_unloaded_m': .04}
    good = {**base, 'coverage95_xy': .94, 'exceed3_xy': .01, 'door_pos_p90_m': .061,
            'nll_xy_by_episode': {'a': -3.5, 'b': -2.}, 'events': 5, 'event_frames': 50}
    assert vm6.validation_gate(good, base)['pass']
    bad = {**good, 'door_lat_p99_m': .047, 'event_frames': 911, 'nll_xy_by_episode': {'a': -3.5, 'b': -1.}}
    f = vm6.validation_gate(bad, base)['failures']
    assert len(f) == 3 and any('door_lat_p99_m' in x for x in f)


def test_stall_diagnostic_counts():
    p = [{'decision': 'stall', 'dt': .2, 'pred_m': .03, 'gt_m': .0},      # TP
         {'decision': 'stall', 'dt': .2, 'pred_m': .03, 'gt_m': .025},    # false stall
         {'decision': 'unknown', 'dt': .2, 'pred_m': .03, 'gt_m': .001},  # missed positive
         {'decision': 'moving', 'dt': .2, 'pred_m': .03, 'gt_m': .03}]
    d = vm6.stall_diagnostic(p)
    assert d['positives'] == 2 and d['precision'] == .5 and d['recall'] == .5
    assert d['abstain_share_of_positives'] == .5


# ----------------------------------------------------------------------------- plan, CLI guards, input boundary
def test_plan_and_configs_regenerate_byte_for_byte(tmp_path):
    import make_plan_v6
    make_plan_v6.main(['--out', str(tmp_path)])
    assert (tmp_path/'plan_v6.json').read_bytes() == (PLAN/'plan_v6.json').read_bytes()
    names = sorted(p.name for p in (PLAN/'configs').glob('*.json'))
    assert names == sorted(p.name for p in (tmp_path/'configs').glob('*.json')) and len(names) == 30
    for n in names:
        assert (tmp_path/'configs'/n).read_bytes() == (PLAN/'configs'/n).read_bytes()
        pf6.validate_vis6(json.loads((PLAN/'configs'/n).read_text())['vis6'])


def test_replay_refuses_test_split_and_seed_rule():
    import replay_v6
    with pytest.raises(SystemExit):
        replay_v6.require_dev(['vl3-test-s951'])
    replay_v6.require_dev(['vl3-dev-s945'])
    assert replay_v6.pf_seed('vl3-dev-s945', 0) == 945 and replay_v6.pf_seed('vl3-dev-s945', 3) == 945003


@pytest.mark.parametrize('name', ['vision_pf_v6.py', 'vision_stall_v6.py'])
def test_runtime_modules_do_not_touch_eval_or_simulator(name):
    src = (HERE/name).read_text()
    code = '\n'.join(line for line in src.splitlines() if not line.lstrip().startswith('#'))
    code = re.sub(r'"""[\s\S]*?"""', '', code)
    for word in ('eval_only', 'teacher', 'mujoco', 'frames_eval', 'gt_trajectory', 'open('):
        assert word not in code, f'{name} mentions {word}'


# ----------------------------------------------------------------------------- adversarial review regressions
def assert_inert_matches(candidate):
    baseline = make5()
    for loc in (baseline, candidate):
        start(loc)
        loc.command({'t': .05, 'kind': 'mecanum', 'forward': .1, 'left': .02, 'turn': .1, 'duration_s': 2.})
    scan = flat_scan(baseline.columns)
    image = np.zeros((vl.HEIGHT, vl.WIDTH, 3), np.uint8)
    for t in (.1, .4, .6, .8, 1., 1.3, 1.6):
        if t == .4:
            for loc in (baseline, candidate):
                loc.logw[:] = -1000.
                loc.logw[0] = 0.
        if t == .8:
            for loc in (baseline, candidate):
                loc.command({'t': .7, 'kind': 'look', 'pan_pulse': 1600})
        if t == 1.3:
            for loc in (baseline, candidate):
                loc.load.loaded = True
        obs = None if t < .2 else scan
        ra = baseline.update_obs(t, obs, baseline.servo)
        rb = candidate.update_obs(t, obs, candidate.servo, image=image)
        rb.pop('vis6', None)
        assert ra == rb, f'inert report mismatch at {t}'
        for attr in ('px', 'logw', 'scale', 'stuck', 'vel'):
            assert np.array_equal(getattr(baseline, attr), getattr(candidate, attr)), attr
        assert baseline.rng.bit_generator.state == candidate.rng.bit_generator.state
    assert baseline.stats['resamples'] > 0
    assert candidate.stats['stall_tests'] > 0 and candidate.stats['stall_frames'] == 0


def inert():
    return make({'eta': 1., 'stall': {'min_pred_px': 100., 'min_points': 1000000, 'max_points': 1000000}})


def test_on_but_inert_vis6_equals_vis5_through_resampling_arm_and_load():
    assert_inert_matches(inert())


def test_inert_equivalence_catches_mutated_report(monkeypatch):
    loc = inert()
    estimate = loc.estimate
    monkeypatch.setattr(loc, 'estimate', lambda: {**estimate(), 'x': estimate()['x'] + 1.})
    with pytest.raises(AssertionError, match='inert report mismatch'):
        assert_inert_matches(loc)


def test_skip_timeout_discount_is_bounded_and_skips_are_counted():
    cfg = pf6.validate_vis6({'stall': {}, 'gating': {'min_d_m': .1, 'min_yaw_rad': .1}})['gating']
    gate = pf6.UpdateGate(cfg)
    gate.commit(None, gate.decide(None, 0.), 0.)
    for t in (.2, .4, .6):
        decision = gate.decide(None, t)
        assert not decision['apply']
        gate.commit(None, decision, t)
    decision = gate.decide(None, 2.)
    assert decision == {'apply': True, 'weight': .2, 'reason': 'timeout'}
    gate.commit(None, decision, 2.)
    assert not gate.decide(None, 2.1)['apply']
    assert gate.decide(None, 4.)['reason'] == 'timeout'
    assert gate.decide(None, 4.)['weight'] < decision['weight']


def forced_stall(monkeypatch, n=256, **options):
    cfg = {'stall': {}, 'gating': {'min_d_m': 1., 'min_yaw_rad': 3., 'max_interval_s': 2.}, **options}
    loc = make(cfg, n=n)
    start(loc)
    monkeypatch.setattr(vst, 'prepare', lambda image, k: image)
    monkeypatch.setattr(vst, 'stall_test', lambda *a: {'decision': 'stall'})
    monkeypatch.setattr(loc, 'scan_loglik', lambda *a: (np.zeros(loc.n), 10))
    # apply_scan intentionally uses the raw superclass likelihood: isolate it for this motion test.
    monkeypatch.setattr(loc, 'apply_scan', lambda *a: None)
    loc.command({'t': .4, 'kind': 'mecanum', 'forward': .12, 'left': 0., 'turn': 0., 'duration_s': 10.})
    return loc


def test_false_stall_sequence_cannot_freeze_filter_or_process_spread(monkeypatch):
    loc = forced_stall(monkeypatch)
    image = np.zeros((vl.HEIGHT, vl.WIDTH), np.float32)
    scan = flat_scan(loc.columns)
    first = loc.update_obs(.6, scan, loc.servo, image=image)
    sigma0 = first['std_xy_m']
    rows = [loc.update_obs(.6 + .2*k, scan, loc.servo, image=image) for k in range(1, 22)]
    assert all(r['vis6']['stall']['decision'] == 'stall' for r in rows)
    assert sum(r['vis6']['stall']['capped'] for r in rows) == 16
    assert loc.stats['gated_timeouts'] >= 2
    assert rows[4]['std_xy_m'] > sigma0    # spread grows even before the cap opens
    assert rows[-1]['std_xy_m'] > sigma0
    assert rows[5]['vis6']['motion'][0] > 0.
    assert rows[5]['vis6']['motion_by_verdict']['stall'][0] > 0.
    assert any(r['measured'] and r['vis6']['gate']['weight'] < 1. for r in rows)


def test_stall_recomputes_map_penalty_across_intermediate_commands(monkeypatch):
    loc = forced_stall(monkeypatch, n=32, stall={'gain': 1.})
    loc.px[:] = [0., 0., 0.]
    loc.scale[:] = 1.
    for key in ('motion',):
        loc.params[key] = {**loc.params[key], 'noise_rel': [0., 0., 0.], 'noise_abs': [0., 0., 0.],
                           'scale_walk': 0.}
    image = np.zeros((vl.HEIGHT, vl.WIDTH), np.float32)
    loc.update_obs(.6, None, loc.servo, image=image)
    before = loc.px.copy()
    boundary = before[0, 0] + .002
    # Only the uncorrected command path crosses this synthetic wall.
    monkeypatch.setattr(loc, '_map_logprior', lambda px: np.where(px[:, 0] > boundary, -8., 0.))
    loc.command({'t': .7, 'kind': 'mecanum', 'forward': .12, 'left': 0., 'turn': 0., 'duration_s': 2.})
    assert np.any(loc._map_residue < 0.)
    monkeypatch.setattr(loc, '_normalize_and_resample', lambda: None)
    prior = loc.logw - loc._map_residue
    loc.update_obs(.8, None, loc.servo, image=image)
    assert np.allclose(loc.px, before)
    assert np.allclose(loc.logw, prior)


@pytest.mark.parametrize('resample,inject', [(False, False), (True, False), (True, True)])
def test_range_keeps_camera_pair_and_particle_ancestry(monkeypatch, resample, inject):
    loc = make({'stall': {}, 'range': {'enabled': True}}, range_provider=lambda px, r: np.zeros(len(px)),
               robust={'recovery': {'alpha_slow': .01, 'alpha_fast': .1, 'uniform_share': 1.}})
    start(loc)
    monkeypatch.setattr(vst, 'prepare', lambda image, k: image)
    monkeypatch.setattr(vst, 'stall_test', lambda *a: {'decision': 'stall'})
    image = np.zeros((vl.HEIGHT, vl.WIDTH), np.float32)
    loc.update_obs(.6, None, loc.servo, image=image)
    previous = loc._px_prev.copy()
    loc.params['roughen'] = [0., 0., 0.]
    if resample:
        loc.logw[:] = -1000.
        loc.logw[0] = 0.
    if inject:
        loc._inject = .5
    loc.update_range(.6, {})
    n_new = loc.diag.get('injected', 0)
    if resample:
        assert np.allclose(loc._px_prev[:loc.n-n_new], previous[0])
    else:
        assert np.array_equal(loc._px_prev, previous)
    if inject:
        assert n_new > 0
        assert np.array_equal(loc._px_prev[-n_new:], loc.px[-n_new:])
    rep = loc.update_obs(.8, None, loc.servo, image=image)
    assert rep['vis6']['stall']['decision'] == 'stall'
    assert loc.stats['stall_tests'] == 1


def test_floor_palette_and_invalid_boundary_do_not_create_stall_samples(camera, monkeypatch):
    import cv2
    raw = np.full((vl.HEIGHT, vl.WIDTH, 3), [60, 55, 51], np.uint8)
    raw[300:, 200:450] = [150, 150, 15]  # cyan cargo
    monkeypatch.setattr(vst.mp, 'undistort', lambda x: x)
    gray = vst.prepare(raw)
    assert np.isnan(gray[350, 300])
    assert vst.floor_color_mask(raw)[250, 300]
    assert not vst.floor_color_mask(raw)[350, 300]
    # Uniform floor next to NaNs must not become textured at the mask boundary.
    assert len(vst.sample_points(gray, *camera, STALL_CFG)[0]) == 0


def test_mixed_stationary_and_moving_floor_points_abstain(camera, monkeypatch):
    origin, rot = camera
    points = 200
    monkeypatch.setattr(vst, 'sample_points', lambda *a: (np.arange(points), np.zeros(points, int), np.zeros((points, 2))))
    calls = iter([np.r_[np.zeros(100), np.full(100, abs(1-s)*10.)] if s == 0 else
                  np.r_[np.full(100, s*10.), np.full(100, abs(1-s)*10.)] for s in STALL_CFG['scales']])
    monkeypatch.setattr(vst, '_bilinear', lambda *a: next(calls))
    monkeypatch.setattr(vst, 'project', lambda q, d, *a: (np.arange(points) + d[0]*1000, np.zeros(points)))
    image = np.zeros((vl.HEIGHT, vl.WIDTH), np.float32)
    res = vst.stall_test(image, image, origin, rot, (.03, 0, 0), STALL_CFG)
    assert res['decision'] == 'unknown' and res['reason'] == 'mixed_point_motion'


def test_recovery_fit_uses_untempered_likelihood():
    a, b = make({'eta': 1., 'stall': {}}), make({'eta': .25})
    for loc in (a, b):
        start(loc)
        loc.apply_scan(.5, flat_scan(loc.columns), loc.servo)
    assert a.diag['fit'] == b.diag['fit']
    assert not np.array_equal(a.logw, b.logw)


def test_event_frames_rule_allows_splitting_and_requires_unloaded_sigma_bound():
    baseline = {'coverage95_xy': .6, 'exceed3_xy': .2, 'door_pos_p90_m': .059, 'door_lat_p99_m': .043,
                'door_yaw_p90_deg': 2.6, 'sigma_xy_p90_loaded_m': .04, 'sigma_xy_p90_unloaded_m': .04,
                'nll_xy_by_episode': {'ep': -2.}, 'events': 1, 'event_frames': 911}
    candidate = {**baseline, 'coverage95_xy': .95, 'exceed3_xy': .01, 'events': 10, 'event_frames': 50}
    assert vm6.validation_gate(candidate, baseline)['pass']
    assert not vm6.validation_gate({**candidate, 'event_frames': 700}, baseline)['pass']
    assert not vm6.validation_gate({**candidate, 'sigma_xy_p90_unloaded_m': .071}, baseline)['pass']
    zero = {**baseline, 'events': 0, 'event_frames': 0}
    assert vm6.validation_gate({**candidate, 'event_frames': 0}, zero)['pass']
    assert not vm6.validation_gate({**candidate, 'event_frames': 1}, zero)['pass']
    rows = [{'frame': k, 't': k*.2, 'err_m': .5 if k != 5 else .01, 'std_xy_m': .01} for k in range(11)]
    assert vm6.events(rows) == {'events': 1, 'frames': 10, 'longest_frames': 10}


def test_yaw_stall_diagnostic_and_wrapped_nll():
    d = vm6.stall_diagnostic([{'decision': 'stall', 'dt': .2, 'pred_m': 0., 'gt_m': .00001,
                              'pred_yaw_rad': .05, 'gt_yaw_rad': .001}])
    assert d['positives'] == 1 and d['precision'] == 1. and d['recall'] == 1.
    d = vm6.stall_diagnostic([{'decision': 'stall', 'dt': .2, 'pred_m': 0., 'gt_m': 0.,
                              'pred_yaw_rad': .05, 'gt_yaw_rad': .05}])
    assert d['precision'] == 0.
    r = vm6.frame_terms([0, 0, 3.], np.diag([.01, .01, 100.]), [0, 0, 0])
    assert r['nll_yaw'] == pytest.approx(math.log(2*math.pi))


def test_s3_refuses_accuracy_regression_even_with_better_nll():
    limits = {'door_pos_p90_m': .003, 'door_lat_p99_m': .003, 'door_yaw_p90_deg': .2}
    base = dict.fromkeys(limits, .05)
    stats = {'a': {**base, 'nll_xy': -2.}, 'b': {**base, 'door_pos_p90_m': .1, 'nll_xy': -20.}}
    assert vm6.select_gating(stats, ['a', 'b'], base, limits)['chosen'] == 'a'


def unit_fixture(tmp_path):
    import replay_v6 as replay
    cfg = tmp_path/'T0.json'
    cfg.write_text('{}')
    estimates = tmp_path/'ep.estimates.jsonl'
    estimates.write_text('{}\n')
    plan = {'configs_sha256': {'T0': replay.vio.sha_file(cfg)}, 'module_sha256': {'a.py': 'abc'}}
    meta = {'candidate': 'T0', 'episode': 'vl-dev-s909', 'seed_index': 0, 'pf_seed': 909, 'plan_sha256': 'plan',
            'failure': None, 'git_dirty': False, 'git_head': 'head', 'module_sha256': plan['module_sha256'],
            'config': {'sha256': plan['configs_sha256']['T0']}, 'frames': 1, 'frames_written': 1,
            'estimates_sha256': replay.vio.sha_file(estimates)}
    path = tmp_path/'ep.meta.json'
    return replay, cfg, estimates, plan, meta, path


@pytest.mark.parametrize('key,value', [('failure', 'HOST_ERROR'), ('git_dirty', True), ('git_head', None),
    ('module_sha256', {'a.py': 'changed'}), ('plan_sha256', 'old'), ('config', {'sha256': 'changed'}),
    ('frames_written', 0), ('estimates_sha256', 'changed'), ('seed_index', 1)])
def test_unit_provenance_rejects_tampering(tmp_path, key, value):
    replay, cfg, estimates, plan, meta, path = unit_fixture(tmp_path)
    meta[key] = value
    path.write_text(json.dumps(meta))
    with pytest.raises(SystemExit):
        replay.verify_unit(path, estimates, plan, 'plan', 'T0', 'vl-dev-s909', 0)


def test_unit_provenance_and_same_stem_config_guard(tmp_path):
    replay, cfg, estimates, plan, meta, path = unit_fixture(tmp_path)
    path.write_text(json.dumps(meta))
    assert replay.verify_unit(path, estimates, plan, 'plan', 'T0', 'vl-dev-s909', 0)['git_head'] == 'head'
    replay.verify_config(plan, 'T0', cfg)
    cfg.write_text('{"eta": .5}')
    with pytest.raises(SystemExit):
        replay.verify_config(plan, 'T0', cfg)
    path.unlink()
    with pytest.raises(SystemExit):
        replay.verify_unit(path, estimates, plan, 'plan', 'T0', 'vl-dev-s909', 0)


@pytest.mark.parametrize('key', ['xyyaw', 'std_xy_m', 'std_yaw_rad', 'measured'])
def test_reproduce_checks_covariance_reports_and_measurement_flag(key):
    import replay_v6
    row = {'frame': 1, 't': .2, 'vision': {'xyyaw': [0, 0, 0], 'std_xy_m': .02,
                                        'std_yaw_rad': .03, 'measured': True}}
    assert replay_v6.same_estimate(row, row)
    changed = copy.deepcopy(row)
    changed['vision'][key] = None
    assert not replay_v6.same_estimate(row, changed)


def evaluation_fixture(tmp_path):
    from types import SimpleNamespace
    import replay_v6 as replay
    episode = 'vl-dev-s909'
    plan = {'split': {'fit': [episode], 'validation': []}, 'configs_sha256': {'T0': 'config'},
            'module_sha256': {'runtime': 'source'}}
    plan_path = tmp_path/'plan.json'
    plan_path.write_text(json.dumps(plan))
    for seed in (0, 1, 2):
        d = tmp_path/'T0'/f'seed{seed}'
        d.mkdir(parents=True)
        rows = [{'frame': i, 't': .2*i, 'loaded': False, 'phase': 'move', 'skill_phase': 'move',
                 'vision': {'xyyaw': [0, 0, 0], 'cov': np.diag([.001, .001, .001]).tolist(),
                            'vis6': {'stall': {'decision': 'stall', 'pred_m': .03, 'pred_yaw_rad': 0.,
                                               'prev_t': .2*(i-1)}} if i else {}}}
                for i in range(3)]
        estimates = d/f'{episode}.estimates.jsonl'
        estimates.write_text(''.join(json.dumps(r)+'\n' for r in rows))
        meta = {'candidate': 'T0', 'episode': episode, 'seed_index': seed, 'pf_seed': replay.pf_seed(episode, seed),
                'plan_sha256': replay.vio.sha_file(plan_path), 'failure': None, 'git_dirty': False,
                'git_head': 'head', 'module_sha256': plan['module_sha256'], 'config': {'sha256': 'config'},
                'frames': 3, 'frames_written': 3, 'estimates_sha256': replay.vio.sha_file(estimates)}
        (d/f'{episode}.meta.json').write_text(json.dumps(meta))
    args = SimpleNamespace(plan=plan_path, episodes=[episode], candidates=['T0'], seeds=[0, 1, 2],
                           root=tmp_path, output=tmp_path/'metrics.json', allow_missing=False)
    return replay, args, episode


def test_evaluate_checks_metadata_and_detector_uses_only_unique_seed0_pairs(tmp_path, monkeypatch):
    replay, args, episode = evaluation_fixture(tmp_path)
    read = replay.vl.read_jsonl
    monkeypatch.setattr(replay.vl, 'read_jsonl', lambda path: [{'frame': i, 'gt': [0, 0, 0]} for i in range(3)]
                        if path.name == 'frames_eval.jsonl' else read(path))
    replay.evaluate(args)
    metrics = json.loads(args.output.read_text())
    assert metrics['candidates']['T0']['fit']['stall_diagnostic']['pairs'] == 2
    assert metrics['provenance']['git_head'] == 'head'
    args.output.unlink()
    path = tmp_path/'T0/seed1'/f'{episode}.meta.json'
    meta = json.loads(path.read_text())
    meta['git_head'] = 'different-commit'
    path.write_text(json.dumps(meta))
    with pytest.raises(SystemExit, match='mixed git_head'):
        replay.evaluate(args)
    assert not args.output.exists()


def test_invalid_unit_refused_before_gt_access(tmp_path, monkeypatch):
    replay, args, episode = evaluation_fixture(tmp_path)
    (tmp_path/'T0/seed0'/f'{episode}.meta.json').unlink()
    monkeypatch.setattr(replay.vl, 'read_jsonl', lambda p: pytest.fail('GT/data access before provenance validation'))
    with pytest.raises(SystemExit, match='missing run metadata'):
        replay.evaluate(args)


def test_run_refuses_wrong_plan_before_loading_inputs(tmp_path, monkeypatch):
    from types import SimpleNamespace
    import replay_v6
    plan = tmp_path/'plan.json'
    plan.write_text(json.dumps({'configs_sha256': {'T0': 'not-the-hash'}}))
    config = tmp_path/'T0.json'
    config.write_text('{}')
    monkeypatch.setattr(replay_v6.mp, 'load_m1_calibration', lambda: pytest.fail('inputs must not be loaded'))
    args = SimpleNamespace(episodes=['vl-dev-s909'], plan=plan, candidate=None, config=config)
    with pytest.raises(SystemExit, match='config hash'):
        replay_v6.run(args)


def test_run_refuses_dirty_sources(monkeypatch):
    from types import SimpleNamespace
    import replay_v6
    monkeypatch.setattr(replay_v6, 'git_head', lambda: 'head')
    monkeypatch.setattr(replay_v6.subprocess, 'run', lambda *a, **kw: SimpleNamespace(stdout=' M runtime.py\n'))
    with pytest.raises(SystemExit, match='clean committed worktree'):
        replay_v6.clean_source_head()


def test_unit_shell_ignores_historical_failed_lines_but_detects_current_failure(tmp_path):
    import os
    import subprocess
    fakebin = tmp_path/'bin'
    fakebin.mkdir()
    for name, text in {'pmset': '#!/bin/sh\necho "AC Power"\n',
                       'df': '#!/bin/sh\nprintf "Filesystem blocks used available\\nfake 200 20 180\\n"\n',
                       'fakepython': '#!/bin/sh\nexit "${FAKE_EXIT:-0}"\n'}.items():
        path = fakebin/name
        path.write_text(text)
        path.chmod(0o755)
    out = tmp_path/'out'
    out.mkdir()
    (out/'load.txt').write_text('prior invocation FAILED\n')
    env = {**os.environ, 'PATH': str(fakebin)+os.pathsep+os.environ['PATH'],
           'VL_PY': str(fakebin/'fakepython'), 'VL_JOBS': '1'}
    cmd = ['bash', str(PLAN/'run_units_v6.sh'), str(out), 'T0', '0', 'vl-dev-s909']
    ok = subprocess.run(cmd, env=env, capture_output=True, text=True)
    assert ok.returncode == 0, ok.stderr
    bad = subprocess.run(cmd, env={**env, 'FAKE_EXIT': '7'}, capture_output=True, text=True)
    assert bad.returncode == 1 and 'unit FAILED' in bad.stderr


def test_archived_frozen_plan_and_configs_keep_original_hashes():
    original = PLAN/'pre_review_0687c620'
    plan = json.loads((PLAN/'plan_v6.json').read_text())
    assert hashlib.sha256((original/'plan_v6.json').read_bytes()).hexdigest() == plan['supersedes_plan_sha256']
    old = json.loads((original/'plan_v6.json').read_text())
    assert len(old['configs_sha256']) == 29
    for name, digest in old['configs_sha256'].items():
        assert hashlib.sha256((original/'configs'/f'{name}.json').read_bytes()).hexdigest() == digest


@pytest.mark.parametrize('gain', [.5, 1.])
def test_stall_preserves_particle_motion_spread_and_replaces_per_particle_map_residue(monkeypatch, gain):
    loc = make({'stall': {'gain': gain}}, n=4)
    start(loc)
    loc.px[:] = [0., 0., 0.]
    loc._px_prev = loc.px.copy()
    delta = np.array([.01, .02, .03, .04])
    loc.px[:, 0] = delta
    loc._map_steps[:] = 4
    loc._map_residue[:] = [0., -8., -16., -24.]
    prior = np.full(loc.n, -math.log(loc.n))
    loc.logw = prior + loc._map_residue
    loc._prev_frame = {'t': .6, 'img': np.zeros((480, 640), np.float32), 'arm': pf6.arm_pose(loc.servo),
                       'loaded': False, 'settled': True}
    monkeypatch.setattr(vst, 'prepare', lambda image, k: image)
    monkeypatch.setattr(vst, 'stall_test', lambda *a: {'decision': 'stall'})
    monkeypatch.setattr(loc, '_map_logprior', lambda px: np.where(px[:, 0] > .015, -8., 0.))
    loc._stall_step(.8, None, loc.servo, loc._prev_frame['img'])
    expected = delta - gain*delta.mean()
    assert np.allclose(loc.px[:, 0], expected)
    assert np.var(loc.px[:, 0]) == pytest.approx(np.var(delta))
    assert np.allclose(loc.logw, prior + 4*np.where(expected > .015, -8., 0.))


@pytest.mark.parametrize('bad', [
    {'stall': {'max_consecutive_stall': 0}}, {'stall': {'max_consecutive_stall': True}},
    {'stall': {}, 'gating': {'min_d_m': .05, 'min_yaw_rad': .1, 'max_interval_s': 0}},
    {'stall': {'trim_fraction': .5}}, {'stall': {'mixed_min_share': 0}},
])
def test_new_config_bounds(bad):
    with pytest.raises(ValueError):
        pf6.validate_vis6(bad)
