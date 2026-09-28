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
    loc = make({'stall': {}} if stall else {'eta': .999999})
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
    assert np.allclose(loc.px, before) and np.allclose(loc.vel, 0.)
    assert loc.stats['stall_frames'] == 1 and rep['vis6']['motion'][0] == pytest.approx(0., abs=1e-12)
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
    assert vm6.events(rows) == {'events': 4, 'frames': 5, 'longest_frames': 2}


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
            'events': 12}
    good = {**base, 'coverage95_xy': .94, 'exceed3_xy': .01, 'door_pos_p90_m': .061,
            'nll_xy_by_episode': {'a': -3.5, 'b': -2.}, 'events': 5}
    assert vm6.validation_gate(good, base)['pass']
    bad = {**good, 'door_lat_p99_m': .047, 'events': 12, 'nll_xy_by_episode': {'a': -3.5, 'b': -1.}}
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
    assert names == sorted(p.name for p in (tmp_path/'configs').glob('*.json')) and len(names) == 29
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
