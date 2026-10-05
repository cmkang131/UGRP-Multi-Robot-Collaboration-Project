"""v6g: carry_dr_general (lateral breakaway ramp + distance-proportional cross-axis drift + refit yaw biases) and the opt-in
route end inset. Everything is off by default; the registered and v6e behaviours must not move."""
import json
import math
from pathlib import Path

import numpy as np
import pytest

from harness import owncam_carry_v6e as v6e
from harness import pair_stage_probe as sp
from harness.owncam_pose_source import OwnCamPoseSource
from harness.zone_pair_executor import make_plan
from harness.zone_pair_v6_policy import POLICIES, PairPolicy, pair_policy
from tests.test_zone_pair_v6e import LEFT_CMD, V6, cloud

ROOT = Path(__file__).resolve().parents[1]
GEN = {'slope_to_yaw_ratio': 1.01, 'b_rad_s': {'pm': .0019, 'edge': .0019, 'pm+edge': .0017},
       'deadband_cmd': {'c0': [0., .006, 0.], 'u1': [0., .02, 0.]}, 'drift_ratio_std': .01}


@pytest.fixture
def general_fit(tmp_path, monkeypatch):
    f = tmp_path/'general.json'
    f.write_text(json.dumps(GEN))
    monkeypatch.setattr(v6e, 'GENERAL_FIT', str(f))
    return f


def _loc(**mp):
    loc = cloud(seed=3, yaw_std=0., profile=True)
    loc.params = {**loc.params, 'motion_loaded': {**loc.params['motion_loaded'], **mp}}
    loc._draw_plant_state(True)
    loc.px[:] = 0.
    loc.px[:, 2] = 0.
    return loc


def _run(loc, forward=0., left=0., seconds=14.):
    loc.command({'t': 0., 'kind': 'mecanum', 'forward': forward, 'left': left, 'turn': 0., 'duration_s': seconds})
    loc.predict_to(seconds + 2.)
    return loc


# ------------------------------------------------------------ policies
def test_general_flag_and_inset_are_on_only_for_the_v6g_policies():
    on = {n for n, p in POLICIES.items() if p.carry_dr_general}
    assert on == {'b-v6g', 'b-v6g-l7', 'b-v6h1'}
    assert {n: p.carry_end_inset_m for n, p in POLICIES.items() if p.carry_end_inset_m} == {'b-v6g-l7': .10}
    e, g, l7 = (pair_policy(n) for n in ('b-v6e', 'b-v6g', 'b-v6g-l7'))
    skip = ('name', 'carry_dr_general', 'carry_end_inset_m')
    assert {k: v for k, v in vars(g).items() if k not in skip} == {k: v for k, v in vars(e).items() if k not in skip}
    assert {k: v for k, v in vars(l7).items() if k not in skip} == {k: v for k, v in vars(e).items() if k not in skip}
    assert not e.carry_dr_general and e.carry_end_inset_m == 0.
    assert (g.carry_dr_general, g.carry_end_inset_m) == (True, 0.) and (l7.carry_dr_general, l7.carry_end_inset_m) == (True, .10)


def test_general_needs_the_dr_profile(monkeypatch):
    from harness.zone_pair_executor import PairTeam
    monkeypatch.setitem(POLICIES, 'gen-only', PairPolicy('gen-only', posterior_relook=True, carry_dr_general=True))
    with pytest.raises(ValueError, match='carry_dr_model'):
        PairTeam({}, {}, {'motion_loaded': {}}, cancel_scheduled=lambda *a: None,
                 contact_profile='cargo_noslip_v1', policy='gen-only')


# ------------------------------------------------------------ localizer: breakaway ramp
def test_ramp_stops_tiny_commands_and_leaves_leg_commands_untouched():
    ramp = {'deadband': {'c0': [0., .006, 0.], 'u1': [0., .02, 0.]}}
    tiny = _run(_loc(**ramp), left=.006)
    plain_tiny = _run(_loc(), left=.006)
    assert abs(np.mean(tiny.px[:, 1])) < .05*abs(np.mean(plain_tiny.px[:, 1])) and abs(np.mean(plain_tiny.px[:, 1])) > .02
    mid = _run(_loc(**ramp), left=.0105)                      # halfway up the ramp: ~ half the linear response
    plain_mid = _run(_loc(), left=.0105)
    assert .3 < np.mean(mid.px[:, 1])/np.mean(plain_mid.px[:, 1]) < .7
    big = _run(_loc(**ramp), left=LEFT_CMD)                   # a planned leg command is beyond u1: identical particles
    plain_big = _run(_loc(), left=LEFT_CMD)
    assert np.array_equal(big.px, plain_big.px)
    # the other axes stay linear (u1 <= c0)
    fwd = _run(_loc(**ramp), forward=.006)
    plain_fwd = _run(_loc(), forward=.006)
    assert np.array_equal(fwd.px, plain_fwd.px)


def test_ramp_is_off_without_the_key():
    a, b = _run(_loc(), left=.008), _run(_loc(), left=.008)
    assert np.array_equal(a.px, b.px) and a.drift is None


# ------------------------------------------------------------ localizer: distance-proportional drift ratio
def test_drift_ratio_spreads_the_cross_axis_in_proportion_to_the_travel():
    def lateral_sd(std, seconds):
        loc = _loc(drift_ratio_std=std)
        loc = _run(loc, forward=.0382, seconds=seconds)
        return float(np.std(loc.px[:, 1])), float(np.mean(loc.px[:, 0]))
    base14, x14 = lateral_sd(0., 14.)
    d14, _ = lateral_sd(.01, 14.)
    d7, x7 = lateral_sd(.01, 7.)
    extra = lambda sd, base: math.sqrt(max(sd**2 - base**2, 0.))
    assert extra(d14, base14) == pytest.approx(.01*x14, rel=.35)             # sigma_y ~ ratio * forward travel
    assert extra(d14, base14) > 1.6*extra(d7, lateral_sd(0., 7.)[0])         # grows with the distance, not the clock
    # nothing moves, nothing drifts
    loc = _loc(drift_ratio_std=.01)
    loc.predict_to(20.)
    assert float(np.std(loc.px[:, 1])) == 0.


def test_drift_ratio_travels_with_resampled_particles_and_is_redrawn_for_resets_and_cleared_on_release():
    loc = _loc(drift_ratio_std=.01)
    assert loc.drift.shape == (loc.n, 2) and abs(np.std(loc.drift) - .01) < .002
    loc.logw = np.where(np.arange(loc.n) < 5, 0., -50.)
    loc._normalize_and_resample()
    assert loc.drift.shape == (loc.n, 2) and len(np.unique(loc.drift[:, 0])) < 20         # the 5 survivors
    idx = np.arange(100)
    loc._reset_plant_state(idx)
    assert len(np.unique(loc.drift[idx, 0])) == 100
    loc._draw_plant_state(False)
    assert loc.drift is None


# ------------------------------------------------------------ provider / fit file
def test_enable_provider_general_reads_the_general_fit_and_binds_one_provider(general_fit):
    p = OwnCamPoseSource(V6['map'], V6['params'], seed=628)
    info = v6e.enable_provider(p, pair_yaw=True, beam_edge=True, general=True)
    mp = p.loc.params['motion_loaded']
    assert mp['deadband'] == GEN['deadband_cmd'] and mp['drift_ratio_std'] == GEN['drift_ratio_std']
    assert mp['yaw_bias_std_rad_s'] == GEN['b_rad_s']['pm+edge'] and info['general_fit']['source'] == str(general_fit)
    assert p.beam_edge.ratio == pytest.approx(GEN['slope_to_yaw_ratio'])
    assert p.carry_yaw_fallback['b']['pm'] == GEN['b_rad_s']['pm']              # the fallback table follows the general fit
    assert v6e.enable_provider(p, pair_yaw=True, beam_edge=True, general=True) is info
    with pytest.raises(ValueError, match='fresh provider'):
        v6e.enable_provider(p, pair_yaw=True, beam_edge=True)
    q = OwnCamPoseSource(V6['map'], V6['params'], seed=628)
    v6e.enable_provider(q, pair_yaw=True, beam_edge=True)
    assert 'deadband' not in q.loc.params['motion_loaded'] and 'drift_ratio_std' not in q.loc.params['motion_loaded']
    with pytest.raises(ValueError, match='fresh provider'):
        v6e.enable_provider(q, pair_yaw=True, beam_edge=True, general=True)


def test_general_without_yaw_flags_keeps_the_registered_yaw_bias(general_fit):
    p = OwnCamPoseSource(V6['map'], V6['params'], seed=628)
    v6e.enable_provider(p, general=True)
    mp = p.loc.params['motion_loaded']
    assert mp['deadband'] and mp['yaw_bias_std_rad_s'] == v6e.load_profile(p.loc.params['motion']['scale_std'])[0]['yaw_bias_std_rad_s']


def test_the_committed_general_fit_has_the_keys_the_provider_reads():
    fit = json.loads((ROOT/v6e.GENERAL_FIT).read_text())
    assert set(fit['deadband_cmd']) == {'c0', 'u1'} and fit['deadband_cmd']['u1'][1] > fit['deadband_cmd']['c0'][1] > 0
    assert fit['deadband_cmd']['c0'][0] == fit['deadband_cmd']['c0'][2] == 0. and fit['deadband_cmd']['u1'][0] == 0.
    assert 0. < fit['drift_ratio_std'] < .05 and set(fit['b_rad_s']) == {'pm', 'edge', 'pm+edge'}
    assert .9 < fit['slope_to_yaw_ratio'] < 1.2 and fit['inputs']


# ------------------------------------------------------------ route end inset
def _static():
    return json.loads((ROOT/'maps'/'zones'/f'{sp.MAP_ID}.json').read_text())


def test_end_inset_moves_only_the_last_route_point():
    sheet = sp.setup_variant('cal')['coarse_order_sheet']
    plain = make_plan(_static(), sheet, 'B')
    zero = make_plan(_static(), sheet, 'B', 0.)
    inset = make_plan(_static(), sheet, 'B', .10)
    assert plain['route'] == zero['route'] and 'end_inset_m' not in plain and plain == zero
    assert inset['route'][:-1] == plain['route'][:-1]                         # every earlier leg is unchanged
    assert plain['route'][-1] == pytest.approx([4.6, -2.1]) and inset['route'][-1] == pytest.approx([4.5, -2.1])
    assert inset['end_inset_m'] == .10 and inset['keepouts'] == plain['keepouts'] and inset['prestations'] == plain['prestations']
    for bad in (-.1, .31, float('nan'), 'x'):
        with pytest.raises(ValueError):
            make_plan(_static(), sheet, 'B', bad)


def test_stage_probe_routes_follow_the_policy_inset_and_only_for_the_l7_policy():
    setup = sp.setup_variant('cal')
    base = sp.plan_route(setup['coarse_order_sheet'])
    for policy, last in (('b-v6e', 4.6), ('b-v6g', 4.6), ('b-v6g-l7', 4.5)):
        case = sp.teacher_cases('carry', setup=setup, subset={'nominal'}, nominal_seeds=(911,), policy=policy, leg=7)[0]
        assert case['case_id'].startswith(f'carry@{policy}:') and case['route'][-1][0] == pytest.approx(last)
        assert case['route'][:-1] == [list(p) for p in base[:-1]]
    with pytest.raises(ValueError):
        sp.plan_route(setup['coarse_order_sheet'], end_inset_m=.6)
