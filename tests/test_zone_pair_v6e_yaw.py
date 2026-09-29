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
    assert on == {'b-v6e', 'b-v6e-pm', 'b-v6e-edge'}
    base, full, pm, edge = (pair_policy(n) for n in ('b-v6e-base', 'b-v6e', 'b-v6e-pm', 'b-v6e-edge'))
    assert [getattr(full, f) for f in YAW] == [True, True]
    assert [getattr(pm, f) for f in YAW] == [True, False] and [getattr(edge, f) for f in YAW] == [False, True]
    rest = lambda p: {k: v for k, v in vars(p).items() if k not in YAW + ('name',)}
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
    tr, first, last = fit.track(d, top['robot'], rb, c['entry_sim_s'], tex, ratio)
    ka, kb = int(np.argmin(np.abs(tt - first))), int(np.argmin(np.abs(tt - last)))
    gt = fit.wrap(fit.rel_yaw(trace[kb], top['robot']) - fit.rel_yaw(trace[ka], top['robot']))
    assert abs(gt) > math.radians(1.)                          # the leg really turns the robot against the beam
    assert tr.total_rad == pytest.approx(gt, abs=.003)          # own-RGB estimate of the change vs eval-only GT
    assert tr.total_rad == pytest.approx(top['edge'], abs=1e-9)  # bit-for-bit the committed replay row
