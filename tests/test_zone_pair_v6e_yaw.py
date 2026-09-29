"""v6e yaw flags: pair-mean plant yaw model (carry_pair_yaw) and own-RGB beam-edge relative yaw (carry_beam_edge).

No physics and no models. The recorded-frame replay reads the cal cohort raws under the primary checkout's outputs/
(skipped when they are absent); the committed fit rows carry the same replay for every cal case-robot.
"""
import json
import math
from pathlib import Path

import numpy as np
import pytest
from PIL import Image, ImageDraw

from harness import owncam_carry_v6e as v6e
from harness.own_beam_edge import BeamEdgeTracker, edge_line
from harness.owncam_pose_source import OwnCamPoseSource
from harness.zone_pair_v6_policy import POLICIES, PairPolicy, pair_policy
from tests.test_zone_pair_v6e import LEFT_CMD, V6, _axial_schedule, _lateral_schedule, _team, cloud

ROOT = Path(__file__).resolve().parents[1]
EXP = ROOT/'experiments/2026-09-29-pair-v6e-carry'
YAW = ('carry_pair_yaw', 'carry_beam_edge')
BASE = dict(posterior_relook=True, exact_fix_clock=True, grasp_range_entry=True, beam_wide_hue=True,
            align_fine_motion=True, carry_dr_model=True, carry_lateral_lag=True, own_image_ob=True, bounded_retreat=True)


# ------------------------------------------------------------ policies
def test_yaw_flags_are_off_everywhere_except_the_three_b_v6e_yaw_policies():
    on = {name for name, p in POLICIES.items() if any(getattr(p, f) for f in YAW)}
    assert on == {'b-v6e', 'b-v6e-pm', 'b-v6e-edge', 'b-v6g', 'b-v6g-l7'}
    base, full, pm, edge = (pair_policy(n) for n in ('b-v6e-base', 'b-v6e', 'b-v6e-pm', 'b-v6e-edge'))
    assert [getattr(full, f) for f in YAW] == [True, True]
    assert [getattr(pm, f) for f in YAW] == [True, False] and [getattr(edge, f) for f in YAW] == [False, True]
    rest = lambda p: {k: v for k, v in vars(p).items() if k not in YAW + ('name', 'carry_dr_general', 'carry_end_inset_m')}
    assert rest(full) == rest(pm) == rest(edge) == rest(base)      # one flag apart, nothing else moved
    assert not any(getattr(base, f) for f in YAW)
    # b-v6e-base is the 0.6.0 b-v6e (dr + lag + both place flags)
    assert vars(base) == {**vars(PairPolicy('b-v6e-base', **BASE))}


def test_yaw_flags_need_the_dr_profile(monkeypatch):
    from harness.zone_pair_executor import PairTeam
    for flag in YAW:
        monkeypatch.setitem(POLICIES, 'yaw-only', PairPolicy('yaw-only', posterior_relook=True, **{flag: True}))
        with pytest.raises(ValueError, match='carry_dr_model'):
            PairTeam({}, {}, {'motion_loaded': {}}, cancel_scheduled=lambda *a: None,
                     contact_profile='cargo_noslip_v1', policy='yaw-only')


def test_a_provider_stays_bound_to_one_variant():
    p = OwnCamPoseSource(V6['map'], V6['params'], seed=628)
    info = v6e.enable_provider(p, pair_yaw=True)
    assert info['variant'] == 'pm' and not hasattr(p, 'beam_edge')
    assert v6e.enable_provider(p, pair_yaw=True) is info
    for kw in ({}, {'beam_edge': True}, {'pair_yaw': True, 'beam_edge': True}):
        with pytest.raises(ValueError, match='fresh provider'):
            v6e.enable_provider(p, **kw)
    q = OwnCamPoseSource(V6['map'], V6['params'], seed=628)
    v6e.enable_provider(q)
    with pytest.raises(ValueError, match='fresh provider'):
        v6e.enable_provider(q, beam_edge=True)


def test_variant_bias_comes_from_the_cal_fit_file():
    fit = json.loads((ROOT/v6e.PAIR_FIT).read_text())
    for kw, key in (({'pair_yaw': True}, 'pm'), ({'beam_edge': True}, 'edge'), ({'pair_yaw': True, 'beam_edge': True}, 'pm+edge')):
        p = OwnCamPoseSource(V6['map'], V6['params'], seed=628)
        info = v6e.enable_provider(p, **kw)
        assert p.loc.params['motion_loaded']['yaw_bias_std_rad_s'] == fit['b_rad_s'][key] == info['yaw_bias_std_rad_s']
        assert (getattr(p, 'beam_edge', None) is not None) == ('beam_edge' in kw)
        assert info['pair_fit']['source'] == v6e.PAIR_FIT and len(info['pair_fit']['file_sha256']) == 64
    plain = OwnCamPoseSource(V6['map'], V6['params'], seed=628)
    assert set(v6e.enable_provider(plain)) == {'source', 'file_sha256', 'profile_sha256'}     # yaw flags off: record unchanged
    assert 'grid' in fit['not_read'] and 'held-out' in fit['not_read']
    assert all(name.startswith('pair-stage-probes-') for name in (i['raw'] for i in fit['inputs']))
    assert min(fit['b_rad_s'].values()) > 0 and fit['b_rad_s']['pm+edge'] < fit['registered_v6e_b_rad_s']


# ------------------------------------------------------------ flag 1: pair-mean plant model, plan-derived partner
def test_partner_command_is_derived_from_the_plan_and_the_role_only(monkeypatch):
    from harness.zone_pair_executor import carry_role_sign
    from tests.test_zone_pair_executor import active
    host = _team(monkeypatch, 'pm-plan', {**BASE, 'carry_pair_yaw': True})
    for schedule in (_axial_schedule, _lateral_schedule):
        legs = {rid: schedule(host, rid) for rid in ('r1', 'r2')}
        for rid, other in (('r1', 'r2'), ('r2', 'r1')):
            start, end, own = legs[rid]
            plan = active(host)[rid].own.pose.loc.pair_plan
            assert (plan['t0'], plan['t1']) == (start, end)
            assert list(plan['own']) == [own['forward'], own['left'], own['turn']]
            # the partner vector equals the OTHER robot's own schedule command: same plan function, other role sign
            o = legs[other][2]
            assert list(plan['partner']) == [o['forward'], o['left'], o['turn']]
            assert list(plan['partner']) == [-v for v in plan['own']] or not any(plan['own'])
    assert carry_role_sign('r1') == -carry_role_sign('r2')
    claim = active(host)['r1'].controller.claims['segments'][-1]
    assert claim['pair_partner_command']['source'].startswith('route plan + role sign')


def test_door_schedule_is_byte_identical_for_every_policy_without_the_yaw_flags(monkeypatch):
    """The carry commands equal the literal registered expression; the yaw flags change neither them nor the times."""
    from scripts import run_m2_pair as m2
    hosts = {n: _team(monkeypatch, n, f) for n, f in (('off', {}), ('base', BASE), ('pm', {**BASE, 'carry_pair_yaw': True}),
                                                       ('edge', {**BASE, 'carry_beam_edge': True}))}
    route = hosts['off'].pairs.sessions[-1]['plan']['route']
    for rid, sign in (('r1', 1.), ('r2', -1.)):
        (ax0, ax1), (lat0, lat1) = route[1:3], route[3:5]
        literal_axial = {'forward': sign*math.copysign(m2.study.SPEED_M_S, ax1[0] - ax0[0])/m2.study.FORWARD_GAIN,
                         'left': 0., 'turn': 0.}
        literal_lateral = {'forward': 0., 'left': sign*math.copysign(m2.study.SPEED_M_S, lat1[1] - lat0[1])/m2.study.LEFT_GAIN,
                           'turn': 0.}
        assert _axial_schedule(hosts['off'], rid)[2] == literal_axial
        assert _lateral_schedule(hosts['off'], rid)[2] == literal_lateral
        for name in ('pm', 'edge'):
            assert _axial_schedule(hosts[name], rid) == _axial_schedule(hosts['base'], rid)
            assert _lateral_schedule(hosts[name], rid) == _lateral_schedule(hosts['base'], rid)
        assert _axial_schedule(hosts['off'], rid) == _axial_schedule(hosts['base'], rid)     # lag flag is lateral only


def test_yaw_flag_run_counters_are_recorded_per_robot(monkeypatch):
    host = _team(monkeypatch, 'pm-edge-rec', {**BASE, 'carry_pair_yaw': True, 'carry_beam_edge': True})
    rec = host.pairs.records()[-1]
    assert set(rec['carry_yaw_v6e']) == {'r1', 'r2', 'r3'} or set(rec['carry_yaw_v6e']) >= {'r1', 'r2'}
    for row in rec['carry_yaw_v6e'].values():
        assert row['partner_plan_matched'] == 0 and row['beam_edge']['applied'] == 0
    assert rec['carry_dr_v6e']['r1']['variant'] == 'pm+edge'
    off = _team(monkeypatch, 'off-rec', BASE)
    assert 'carry_yaw_v6e' not in off.pairs.records()[-1]


def test_pair_mean_cancels_the_antisymmetric_yaw_coupling_and_leaves_xy_alone():
    """Mirrored partner command: yaw target = mean of the two plants' targets (0 for a mirrored pair), x/y unchanged."""
    own = np.array([0., LEFT_CMD, 0.])
    off, on = cloud(profile=True), cloud(profile=True)
    on.pair_plan = {'t0': 3., 't1': 17., 'own': own, 'partner': -own}
    for loc in (off, on):
        loc.predict_to(3.)
        loc.command({'t': 3., 'kind': 'mecanum', 'forward': 0., 'left': LEFT_CMD, 'turn': 0., 'duration_s': 14.})
        loc.predict_to(9.)
    gain = np.asarray(on.params['motion_loaded']['gain'], float)
    assert off.cmd_partner is None and on.cmd_partner is not None and on.pair_matched == 1
    assert off.vel[2] != 0.                                   # the registered plant turns while translating
    assert abs(on.vel[2]) < 1e-12                             # ... the pair mean does not
    assert on.vel[:2] == pytest.approx(off.vel[:2], abs=0, rel=0)
    assert off.vel[2] == pytest.approx(gain[2] @ own*(1. - math.exp(-6./.8)), rel=1e-3)
    # after the leg the plan no longer applies (another own command is not the planned one)
    on.command({'t': 9., 'kind': 'mecanum', 'forward': .1, 'left': 0., 'turn': 0., 'duration_s': .15})
    assert on.cmd_partner is None and on.pair_unmatched == 1
    # an unloaded robot never uses the plan
    unl = cloud(profile=True)
    unl.pair_plan = {'t0': 0., 't1': 99., 'own': own, 'partner': -own}
    unl.predict_to(3.)
    unl.command({'t': 3., 'kind': 'mecanum', 'forward': 0., 'left': LEFT_CMD, 'turn': 0., 'duration_s': 14.})
    unl.load.loaded = False
    unl.predict_to(6.)
    assert unl.vel[2] != 0.


def test_flags_off_localizer_stream_is_unchanged_by_the_plan_hooks():
    from tests.test_zone_pair_v6e import leg
    a, b = cloud(), cloud()
    b.pair_plan = None
    leg(a), leg(b)
    assert np.array_equal(a.px, b.px) and float(a.rng.random()) == float(b.rng.random())
    c = cloud()
    c.pair_plan = {'t0': 100., 't1': 101., 'own': np.zeros(3), 'partner': np.zeros(3)}   # a plan that never matches
    leg(c)
    assert np.array_equal(a.px, c.px)


# ------------------------------------------------------------ flag 2: beam edge
def band(slope, y0=120, width=640, height=480, thick=45):
    """Synthetic own frame: dark floor, a yellow-green band whose lower edge has ``slope`` (px/px) through (320, y0)."""
    im = Image.new('RGB', (width, height), (40, 40, 40))
    dr = ImageDraw.Draw(im)
    lo = lambda x: y0 + slope*(x - 320)
    dr.polygon([(0, lo(0) - thick), (width, lo(width) - thick), (width, lo(width)), (0, lo(0))], fill=(150, 200, 30))
    return np.asarray(im)


def test_edge_line_recovers_the_slope_and_centre_height_of_a_synthetic_band():
    for slope in (-.06, 0., .03, .08):
        got = edge_line(band(slope))
        assert got is not None and got[0] == pytest.approx(slope, abs=2e-3) and got[1] == pytest.approx(120, abs=1.5)
    assert edge_line(np.full((480, 640, 3), 40, np.uint8)) is None              # no band: no measurement


def feed(tr, slopes, *, t0=0., dt=.6, servo=None, loaded=True):
    servo = servo or {1: 2000, 3: 740, 4: 2320, 5: 1320, 6: 1500}
    out = []
    for i, s in enumerate(slopes):
        out.append(tr.observe(t0 + i*dt, band(s), servo, loaded))
    return out


def test_tracker_increments_telescope_to_one_smoothed_measurement():
    tr = BeamEdgeTracker(1.)
    slopes = [0.]*8 + list(np.linspace(0., .05, 20)) + [.05]*6
    inc = feed(tr, slopes, dt=.6)
    assert sum(x for x in inc if x) == pytest.approx(tr.total_rad) and tr.total_rad == pytest.approx(.05, abs=3e-3)
    assert not any(inc[:6])                                    # settle 3 s + reference frames: nothing applied yet
    # a ratio of 0.5 doubles the yaw for the same slope change; noise does not accumulate
    tr2 = BeamEdgeTracker(.5)
    rng = np.random.default_rng(3)
    feed(tr2, [.02 + .0005*rng.normal() for _ in range(80)], dt=.6)
    assert abs(tr2.total_rad) < .004


def test_tracker_restarts_on_arm_change_unload_and_glitch():
    tr = BeamEdgeTracker(1.)
    feed(tr, [0.]*10 + [.02]*6)
    total = tr.total_rad
    assert total == pytest.approx(.02, abs=2e-3)
    # arm servo changes: the reference restarts, the shift already handed to the PF is kept and nothing is applied for 3 s
    inc = feed(tr, [.05]*4, t0=20., servo={1: 2000, 3: 700, 4: 2320, 5: 1320, 6: 1500})
    assert not any(inc) and tr.total_rad == total
    tr2 = BeamEdgeTracker(1.)
    feed(tr2, [0.]*10)
    assert feed(tr2, [0.]*3, t0=20., loaded=False) == [None]*3 and tr2._ref_slope is None
    # one glitch frame is removed by the median of three; a jump that persists is rejected by the step limit
    tr3 = BeamEdgeTracker(1.)
    feed(tr3, [0.]*10)
    feed(tr3, [.2, 0., 0.], t0=20.)
    assert tr3.stats['rejected'] == 0 and abs(tr3.total_rad) < 1e-9
    feed(tr3, [.2, .2, .2], t0=30.)
    assert tr3.stats['rejected'] >= 1 and abs(tr3.total_rad) < 1e-9


def test_pose_source_applies_the_increment_only_with_the_flag():
    p = OwnCamPoseSource(V6['map'], V6['params'], seed=628)
    v6e.enable_provider(p, beam_edge=True)
    loc = p.loc
    loc.px = np.zeros((loc.n, 3)); loc.initialized = True; loc.load.loaded = True
    loc.logw = np.zeros(loc.n)
    y0 = loc.px[:, 2].copy()
    loc.apply_relative_yaw(1., .01)
    assert np.allclose(loc.px[:, 2] - y0, .01) and float(np.std(loc.px[:, 2])) == 0.


# ------------------------------------------------------------ recorded-frame replay
FIT_ROWS = json.loads((EXP/'carry_pair_fit_rows.json').read_text()) if (EXP/'carry_pair_fit_rows.json').exists() else []
OUTPUTS = Path('/Users/changmin/projects/ugrp/outputs')


def test_committed_replay_rows_reproduce_the_relative_yaw_correlation_and_residual():
    rows = [r for r in FIT_ROWS if r['d_rel_gt'] is not None]
    assert len(rows) >= 40
    s, y = np.array([r['d_slope_total'] for r in rows]), np.array([r['d_rel_gt'] for r in rows])
    ratio = json.loads((ROOT/v6e.PAIR_FIT).read_text())['slope_to_yaw_ratio']
    assert np.corrcoef(s, y)[0, 1] > .99
    assert np.std(s/ratio - y) < .002                          # rad; over-a-leg residual well below the 3 degree gate


@pytest.mark.skipif(not (OUTPUTS/'pair-stage-probes-ece38792-cal/cases.jsonl').exists(), reason='cal raw not present')
def test_tracker_on_recorded_frames_matches_the_recorded_replay_rows():
    import sys
    sys.path.insert(0, str(EXP))
    import fit_carry_pair_yaw as fit
    top = max((r for r in FIT_ROWS if r['raw'] == 'ece38792-cal' and r['d_rel_gt'] is not None), key=lambda r: abs(r['d_rel_gt']))
    root = OUTPUTS/'pair-stage-probes-ece38792-cal'
    c = next(c for c in map(json.loads, open(root/'cases.jsonl')) if c['cell'] == top['cell'] and c['leg'] == top['leg']
             and c['seed'] == 911 and not c.get('host_error'))
    d = fit.case_dir('ece38792-cal', c['case_id'])
    trace = [json.loads(x) for x in open(d/'eval_only/trace.jsonl')]
    rb = json.load(open(d/'robots.json'))
    tt = np.array([x['t'] for x in trace])
    tex = max(c['exit_sim_s'].values()) if c.get('exit_sim_s') else trace[-1]['t']
    ratio = json.loads((ROOT/v6e.PAIR_FIT).read_text())['slope_to_yaw_ratio']
    tr = fit.track(d, top['robot'], rb, c['entry_sim_s'], tex, ratio)
    rel = np.unwrap([fit.rel_yaw(x, top['robot']) for x in trace])
    gt = fit.gt_rel_change(tt, rel, tr.ref_t, tr.eff_t)
    assert abs(gt) > math.radians(1.)                          # the leg really turns the robot against the beam
    assert tr.total_rad == pytest.approx(gt, abs=.003)          # own-RGB estimate of the change vs eval-only GT
    assert tr.total_rad == pytest.approx(top['edge'], abs=1e-9)  # bit-for-bit the committed replay row
    assert tr.stats['no_edge'] == 0 and tr.available(tr.last_ok_t)


# ------------------------------------------------------------ edge-line robustness (stray pixels, non-line boundary)
def test_edge_line_ignores_isolated_coloured_pixels_above_the_band():
    img = band(.03).copy()
    rng = np.random.default_rng(5)
    for c in range(140, 500, 4):                                # one stray yellow-green pixel above the band in every column
        img[rng.integers(45, 60), c] = (150, 200, 30)
    got = edge_line(img)
    assert got is not None and got[0] == pytest.approx(.03, abs=2e-3) and got[1] == pytest.approx(120, abs=1.5)


def test_edge_line_rejects_a_boundary_that_is_not_a_line():
    img = np.asarray(Image.new('RGB', (640, 480), (40, 40, 40))).copy()
    for c in range(0, 640):
        lo = 120 + (60 if 250 < c < 420 else 0)                 # a wedge of band hanging down: boundary jumps 60 px
        img[lo - 45:lo, c] = (150, 200, 30)
    assert edge_line(img) is None
    img2 = np.asarray(Image.new('RGB', (640, 480), (40, 40, 40))).copy()
    img2[100:110, :] = (150, 200, 30)                            # a thin stripe (10 px): shorter than a beam band
    assert edge_line(img2) is None


def test_tracker_availability_and_reference_times():
    tr = BeamEdgeTracker(1.)
    assert not tr.available(0.)
    feed(tr, [0.]*10)
    assert tr.ref_t is not None and tr.eff_t is not None and tr.ref_t < tr.eff_t
    assert tr.available(tr.last_ok_t + 1.9) and not tr.available(tr.last_ok_t + 2.5)     # stale after 2 s
    empty = np.full((480, 640, 3), 40, np.uint8)
    out = tr.observe(30., empty, {1: 2000, 3: 740, 4: 2320, 5: 1320, 6: 1500}, True)
    assert out is None and not tr.available(30.) and tr.stats['no_edge'] >= 1


# ------------------------------------------------------------ availability fallback of the yaw bias
def _flagged_provider(pair=True, edge=True):
    p = OwnCamPoseSource(V6['map'], V6['params'], seed=628)
    v6e.enable_provider(p, pair_yaw=pair, beam_edge=edge)
    loc = p.loc
    n = loc.n
    loc.px = np.zeros((n, 3)); loc.scale = np.ones((n, 3)); loc.logw = np.zeros(n)
    loc.initialized = True; loc.load.loaded = True
    loc._draw_plant_state(True)
    return p


def test_fallback_std_is_the_quadrature_gap_to_the_available_estimator():
    p = _flagged_provider()
    cfg = p.carry_yaw_fallback
    b = cfg['b']
    assert b['pm+edge'] == cfg['b_full'] and b[''] == pytest.approx(.002331418995960997)
    full, key = v6e.fallback_std(cfg, True, True)
    assert full == 0. and key == 'pm+edge'
    no_edge, key = v6e.fallback_std(cfg, True, False)
    assert key == 'pm' and no_edge == pytest.approx(math.sqrt(b['pm']**2 - b['pm+edge']**2))
    no_pm, key = v6e.fallback_std(cfg, False, True)
    assert key == 'edge' and no_pm == pytest.approx(math.sqrt(max(b['edge']**2 - b['pm+edge']**2, 0.)))
    none, key = v6e.fallback_std(cfg, False, False)
    assert key == '' and none == pytest.approx(math.sqrt(b['']**2 - b['pm+edge']**2)) and none > no_edge
    # variants without a flag never count that flag as available
    edge_only = _flagged_provider(pair=False, edge=True).carry_yaw_fallback
    assert v6e.fallback_std(edge_only, True, True)[1] == 'edge'


def test_update_availability_widens_the_filter_when_the_edge_or_the_plan_is_missing():
    p = _flagged_provider()
    loc = p.loc
    cfg = p.carry_yaw_fallback
    v6e.update_availability(p, 1.)                              # no edge reference yet: pair-mean level only
    assert loc.extra_std == pytest.approx(v6e.fallback_std(cfg, True, False)[0]) and loc.yaw_extra is not None
    # edge tracked (good frames): fallback cleared
    for i in range(12):
        p.beam_edge.observe(1. + i*.6, band(0.), {1: 2000, 3: 740, 4: 2320, 5: 1320, 6: 1500}, True)
    t = 1. + 11*.6
    assert p.beam_edge.available(t)
    v6e.update_availability(p, t)
    assert loc.extra_std == 0. and loc.yaw_extra is None
    # mask emptied (beam not seen): after the stale time the pair-mean level returns
    empty = np.full((480, 640, 3), 40, np.uint8)
    for i in range(6):
        p.beam_edge.observe(t + .6*(i + 1), empty, {1: 2000, 3: 740, 4: 2320, 5: 1320, 6: 1500}, True)
    t2 = t + 3.6
    v6e.update_availability(p, t2)
    assert loc.extra_std == pytest.approx(v6e.fallback_std(cfg, True, False)[0])
    # partner plan mismatch while moving: registered level, and it is held for PM_HOLD_S (no per-pulse flapping)
    loc.cmd, loc.cmd_expires, loc.t, loc.cmd_partner = np.array([0., .05, 0.]), t2 + 5., t2, None
    v6e.update_availability(p, t2)
    assert loc.extra_std == pytest.approx(v6e.fallback_std(cfg, False, False)[0])
    loc.cmd_expires = -1.
    v6e.update_availability(p, t2 + .5)
    assert loc.extra_std == pytest.approx(v6e.fallback_std(cfg, False, False)[0])
    v6e.update_availability(p, t2 + v6e.PM_HOLD_S + .1)
    assert loc.extra_std == pytest.approx(v6e.fallback_std(cfg, True, False)[0])
    # unloaded: nothing extra
    loc.load.loaded = False
    v6e.update_availability(p, t2 + 10.)
    assert loc.extra_std == 0.


def test_the_extra_yaw_error_widens_the_yaw_spread_and_is_off_by_default():
    def spread(extra):
        p = _flagged_provider()
        loc = p.loc
        loc.set_extra_yaw_std(0., extra)
        loc.command({'t': 0., 'kind': 'mecanum', 'forward': 0., 'left': LEFT_CMD, 'turn': 0., 'duration_s': 30.})
        loc.predict_to(20.)
        return float(np.std(loc.px[:, 2]))
    assert spread(.002) > spread(0.)*1.05
    assert _flagged_provider().loc.yaw_extra is None
    # resampling carries the extra error with the particles; a kidnap reset redraws it
    p = _flagged_provider()
    p.loc.set_extra_yaw_std(0., .002)
    assert p.loc.yaw_extra.shape == (p.loc.n,)
    p.loc.logw = np.where(np.arange(p.loc.n) < 5, 0., -50.)
    p.loc._normalize_and_resample()
    assert p.loc.yaw_extra.shape == (p.loc.n,)


# ------------------------------------------------------------ analysis names of old raws
def test_old_b_v6e_raws_are_analysed_as_b_v6e_base():
    from harness.pair_stage_probe import canonical_policy
    assert canonical_policy('b-v6e', '0.6.0') == 'b-v6e-base' and canonical_policy('b-v6e', '0.5.0') == 'b-v6e-base'
    assert canonical_policy('b-v6e', '0.7.0') == 'b-v6e' and canonical_policy('b-v6e', '0.7.1') == 'b-v6e'
    assert canonical_policy('b-v6e-pm', '0.6.0') == 'b-v6e-pm' and canonical_policy('b-v6d', '0.6.0') == 'b-v6d'
    assert canonical_policy('b-v6e', None) == 'b-v6e-base'


@pytest.mark.skipif(not (OUTPUTS/'pair-stage-probes-d08818ef-cal2/manifest.json').exists(), reason='cal-2 raw not present')
def test_view_builder_names_old_raws_base_and_new_raws_plain(tmp_path):
    import importlib.util
    spec = importlib.util.spec_from_file_location('views', ROOT/'scripts/build_pair_stage_probe_views.py')
    views = importlib.util.module_from_spec(spec); spec.loader.exec_module(views)
    raw = OUTPUTS/'pair-stage-probes-d08818ef-cal2'
    manifest = json.loads((raw/'manifest.json').read_text())
    row = json.loads(next(l for l in open(raw/'cases.jsonl')))
    assert manifest['probe_version'] == '0.6.0' and row['pair_policy'] == 'b-v6e'
    name, view = views.case_view(raw, row, manifest)
    assert view['policy'] == 'b-v6e-base' and name.startswith('E0-')
    name2, view2 = views.case_view(raw, row, {**manifest, 'probe_version': '0.7.0'})
    assert view2['policy'] == 'b-v6e' and name2.startswith('E-')
