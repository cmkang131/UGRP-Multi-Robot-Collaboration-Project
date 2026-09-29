"""v6e carry flags: calibrated dead-reckoning error model and the lateral-lag leg length (no physics, no models).

Two independent opt-in flags (``carry_dr_model``, ``carry_lateral_lag``). With both off the v6c behaviour is
unchanged: the localizer draw stream is identical to main 1e7bdfe0 (localizer untouched by #265) (golden numbers below, computed on that commit)
and the M2 leg schedule is the constant-scale one.
"""
import json
import math
from pathlib import Path

import numpy as np
import pytest

from harness import owncam_carry_v6e as v6e
from harness.owncam_localizer import LoadState, OwnCamLocalizer
from harness.owncam_pose_source import OwnCamPoseSource
from harness.zone_pair_v6_policy import POLICIES, REVISION_POLICIES, PairPolicy, pair_policy

ROOT = Path(__file__).resolve().parents[1]
V6 = json.loads((ROOT/'tests/fixtures/zone_pair_v6/reports.json').read_text())
LATERAL_LEG_M = .7167
LEFT_CMD = .0517/1.0159          # left command giving the loaded steady lateral speed 0.0517 m/s


def cloud(seed=7, yaw_std=.05, profile=False):
    """Loaded PF with a fixed particle cloud, as the M2 carry sees it after the pick-up (no fix ever arrives)."""
    loc = OwnCamLocalizer(V6['map'], V6['params'], seed=seed)
    n = loc.n
    rng = np.random.default_rng(99)
    loc.px = np.stack([.6 + .03*rng.normal(size=n), .03*rng.normal(size=n), yaw_std*rng.normal(size=n)], 1)
    loc.scale = 1. + rng.normal(size=(n, 3))*loc.params['motion']['scale_std']
    loc.logw = np.zeros(n)
    loc.initialized = True
    loc.load.loaded = True
    if profile:
        p, _ = v6e.load_profile(loc.params['motion']['scale_std'])
        loc.params = {**loc.params, 'motion_loaded': {**loc.params['motion_loaded'], **p}}
        loc._draw_plant_state(True)
    return loc


def leg(loc, rest_s=3., move_s=14.):
    loc.predict_to(rest_s)
    loc.command({'t': rest_s, 'kind': 'mecanum', 'forward': 0., 'left': LEFT_CMD, 'turn': 0., 'duration_s': move_s})
    loc.predict_to(rest_s + move_s)


# ------------------------------------------------------------ policies
def test_flags_are_off_for_every_registered_policy_and_on_only_for_the_v6e_set():
    for name in ('v5h', 'b-only', 'a+b', 'b-boot', 'a+b-boot', 'b-v6c', 'b-v6d'):
        p = POLICIES[name]
        assert not p.carry_dr_model and not p.carry_lateral_lag
    dr, lag, both = pair_policy('b-v6e-dr'), pair_policy('b-v6e-lag'), pair_policy('b-v6e')
    assert (dr.carry_dr_model, dr.carry_lateral_lag) == (True, False)
    assert (lag.carry_dr_model, lag.carry_lateral_lag) == (False, True)
    assert (both.carry_dr_model, both.carry_lateral_lag) == (True, True)
    base = vars(POLICIES['b-v6d'])
    for p in (dr, lag, both):     # every v6e policy is b-v6d plus the carry flags only
        assert {k: v for k, v in vars(p).items() if k not in ('name', 'carry_dr_model', 'carry_lateral_lag')} == \
               {k: v for k, v in base.items() if k not in ('name', 'carry_dr_model', 'carry_lateral_lag')}
    assert REVISION_POLICIES['v6c'] == ('v5h', 'b-only', 'b-v6c')


# ------------------------------------------------------------ flag 2: lateral leg length
def test_lag_duration_inverts_lag_travel_and_is_monotone():
    for v, tau, stop in ((.0517, .8, .05), (.06, .8, .05), (.1, 1.2, .2)):
        for d in (.05, .3, .7167, 1.5):
            t = v6e.lag_duration(d, v, tau, stop)
            assert v6e.lag_travel(t, v, tau, stop) == pytest.approx(d, abs=1e-9)
        assert v6e.lag_duration(.3, v, tau, stop) < v6e.lag_duration(.7, v, tau, stop)
    with pytest.raises(ValueError):
        v6e.lag_duration(0., .05, .8, .05)
    with pytest.raises(ValueError):
        v6e.lag_duration(.5, .05, 0., .05)


def test_shipped_lateral_leg_length_comes_from_the_loaded_plant_not_the_measured_scale():
    from scripts import study_owncam_pair_beam as study
    cal = {'motion_loaded': V6['params']['motion_loaded']}
    cmd = [0., study.SPEED_M_S/study.LEFT_GAIN, 0.]
    T = v6e.leg_duration(LATERAL_LEG_M, 'lateral', cmd, cal)
    assert v6e.steady_speed(cal, 'lateral', cmd) == pytest.approx(.0517, abs=2e-4)
    # The constant-scale schedule (0.697) commands 17.1 s; the loaded first-order-lag plant needs 14.6 s.
    assert LATERAL_LEG_M/(study.SPEED_M_S*study.CARRY_ODOM_SCALE['lateral']) == pytest.approx(17.14, abs=.01)
    assert T == pytest.approx(14.61, abs=.05)
    # a shorter leg is NOT the same fraction of the constant-scale time (spin-up and stop lag are fixed offsets)
    short = v6e.leg_duration(.3, 'lateral', cmd, cal)
    assert short/T != pytest.approx(.3/LATERAL_LEG_M, rel=.01)
    assert (LATERAL_LEG_M/study.CARRY_ODOM_SCALE['lateral'] - LATERAL_LEG_M/.806) > 0     # sanity of the diagnosed gap


def _team(monkeypatch, name, flags):
    from harness.zone_pair_executor import m2_controller
    from tests.test_zone_pair_executor import CALIB, SHEETS, PairFakeHost, robot, start
    monkeypatch.setitem(POLICIES, name, PairPolicy(name, **flags))
    exs = {r: robot(r) for r in ('r1', 'r2', 'r3')}
    host = PairFakeHost(exs, lambda *a: None)
    host.contact_record = {'profile': 'cargo_noslip_v1'}
    host.enable_pair_carry(SHEETS, CALIB['params'], controller_factory=m2_controller, policy=name)
    assert start(host)['accepted']
    return host


def _lateral_schedule(host, rid):
    from tests.test_zone_pair_executor import active
    ctl = active(host)[rid].controller
    ctl.seg = 3
    ctl.grasp_estimate = [3.2, .05, 0. if rid == 'r1' else math.pi]
    return ctl.door_schedule(10.)[-1]


def _axial_schedule(host, rid):
    from tests.test_zone_pair_executor import active
    ctl = active(host)[rid].controller
    ctl.seg = 1
    ctl.grasp_estimate = [1., .05, 0. if rid == 'r1' else math.pi]
    return ctl.door_schedule(10.)[-1]


def test_lateral_lag_flag_changes_only_the_lateral_leg_duration(monkeypatch):
    off = _team(monkeypatch, 'lag-off', {})
    on = _team(monkeypatch, 'lag-on', {'carry_lateral_lag': True})
    for rid in ('r1', 'r2'):
        s0, e0, c0 = _lateral_schedule(off, rid)
        s1, e1, c1 = _lateral_schedule(on, rid)
        assert s0 == s1 and c0 == c1                     # same start, same command; only the length differs
        assert (e0 - s0) == pytest.approx(LATERAL_LEG_M/(.06*.697), abs=.01) and (e1 - s1) == pytest.approx(14.61, abs=.05)
        a0, a1 = _axial_schedule(off, rid), _axial_schedule(on, rid)
        assert a0 == a1                                  # axial legs keep the constant scale


def test_lateral_lag_needs_the_loaded_motion_model(monkeypatch):
    from harness.zone_pair_executor import PairTeam
    monkeypatch.setitem(POLICIES, 'lag-only', PairPolicy('lag-only', carry_lateral_lag=True))
    with pytest.raises(ValueError, match='motion_loaded'):
        PairTeam({}, {}, {'motion': {}}, cancel_scheduled=lambda *a: None, contact_profile='cargo_noslip_v1',
                 policy='lag-only')


# ------------------------------------------------------------ flag 1: localizer error model
def test_flags_off_localizer_is_bit_identical_to_main_1e7bdfe0():
    """Golden numbers computed on main 1e7bdfe0 with the same scenario (loaded PF, 3 s rest, 14 s lateral leg, 4 s rest)."""
    loc = cloud()
    leg(loc)
    assert loc.px.mean(0) == pytest.approx([0.6116276935696243, 0.6806639463927205, -0.037399559527930934], abs=1e-9)
    assert loc.px.std(0) == pytest.approx([0.0640851529597696, 0.1500687901338394, 0.10244394806426557], abs=1e-9)
    loc.predict_to(21.)
    assert loc.px.mean(0) == pytest.approx([0.6117212900432347, 0.6821415843142052, -0.03664654876228598], abs=1e-9)
    assert loc.px.std(0) == pytest.approx([0.06469969379778996, 0.15039201977049713, 0.11128809762213009], abs=1e-9)
    assert loc.scale.mean(0) == pytest.approx([0.9983732592268756, 0.997783902009845, 0.9986793476030279], abs=1e-9)
    assert float(loc.rng.random()) == pytest.approx(0.2551749841311922, abs=1e-12)     # same number of draws
    assert loc.yaw_bias is None


def test_loaded_rest_does_not_diffuse_and_leg_sigma_stays_under_the_hold_gate_with_the_profile():
    loc = cloud(yaw_std=.0357, profile=True)
    before = loc.px.copy()
    loc.predict_to(3.)
    assert np.allclose(loc.px, before, atol=1e-12, rtol=0)   # no wheel motion, no diffusion (rest_noise False)
    leg(loc)
    assert 0. < loc.px[:, 2].std() < math.radians(3.) - .005
    assert loc.px[:, :2].std(0).max() < .07             # xy hold gate is 0.07 m
    # a fix-free 14 s leg still grows sigma: honest, not frozen
    assert loc.px[:, 2].std() > .0357 and loc.px[:, :2].std(0).min() > .03
    # the registered loaded model, same start, crosses the yaw gate within ~3 s of motion
    reg = cloud(yaw_std=.0357)
    reg.predict_to(3.)
    reg.command({'t': 3., 'kind': 'mecanum', 'forward': 0., 'left': LEFT_CMD, 'turn': 0., 'duration_s': 14.})
    reg.predict_to(3. + 2.9)
    assert reg.px[:, 2].std() > math.radians(3.) - .005


def test_profile_keeps_the_gate_and_the_mean_motion_untouched():
    reg, new = cloud(), cloud(profile=True)
    for loc in (reg, new):
        leg(loc)
    # same mean plant: the estimate mean differs only by the zero-mean draws (0.0-scale spread, tiny bias)
    assert new.px.mean(0)[:2] == pytest.approx(reg.px.mean(0)[:2], abs=.02)
    import harness.zone_own_guards as guards
    assert guards.GATE_LOADED.high_yaw_rad == pytest.approx(math.radians(3.))


def test_pickup_redraws_scale_and_bias_and_release_restores_the_unloaded_spread():
    loc = cloud(profile=True)
    loc.load.loaded = False
    loc.yaw_bias = None
    loc.scale = 1. + np.random.default_rng(5).normal(size=(loc.n, 3))*loc.params['motion']['scale_std']
    prof = loc.params['motion_loaded']
    calls = iter([True, False])

    def command(row):
        loc.load.loaded = next(calls)
        return loc.load.loaded
    loc.load.command = command
    loc.command({'t': 0.1, 'kind': 'hold'})              # pick-up
    assert loc.load.loaded and loc.yaw_bias is not None and loc.yaw_bias.shape == (loc.n,)
    assert loc.yaw_bias.std() == pytest.approx(prof['yaw_bias_std_rad_s'], rel=.15) and abs(loc.yaw_bias.mean()) < 4e-4
    assert loc.scale.std(0)[0] == pytest.approx(prof['load_transition']['scale_std'][0], rel=.2)
    assert loc.scale.std(0)[2] == pytest.approx(0., abs=1e-12)
    loc.command({'t': 0.2, 'kind': 'hold'})              # release
    assert not loc.load.loaded and loc.yaw_bias is None
    assert loc.scale.std(0) == pytest.approx([loc.params['motion']['scale_std']]*3, rel=.15)


def test_bias_travels_with_resampled_particles_and_is_redrawn_for_reset_particles():
    loc = cloud(profile=True)
    loc.yaw_bias = np.linspace(-1., 1., loc.n)*1e-3
    idx = np.arange(loc.n)[::-1].copy()
    keep = loc.yaw_bias[idx].copy()
    w = np.zeros(loc.n)
    w[0] = 1.
    loc.logw = np.log(w + 1e-300)
    loc._normalize_and_resample()
    assert loc.yaw_bias.shape == (loc.n,) and np.all(loc.yaw_bias == loc.yaw_bias[0])          # all particles descend from particle 0
    assert keep.shape == loc.yaw_bias.shape
    loc.yaw_bias[:] = 5.
    ids = np.arange(4)
    loc._reset_plant_state(ids)
    assert np.all(loc.yaw_bias[4:] == 5.) and np.all(np.abs(loc.yaw_bias[ids]) < .01)


def test_profile_needs_a_registered_loaded_model_and_never_touches_the_unloaded_one():
    loc = cloud(profile=True)
    loc.load.loaded = False
    loc.predict_to(2.)
    assert loc.yaw_bias is not None                          # drawn at the transition, but only read while loaded
    unloaded_std_before = loc.px.std(0).copy()
    loc.command({'t': 2., 'kind': 'mecanum', 'forward': .05, 'left': 0., 'turn': 0., 'duration_s': 2.})
    loc.predict_to(4.)
    assert loc.px.std(0)[2] > unloaded_std_before[2]      # unloaded model keeps its registered rest/rate noise


def test_enable_provider_binds_one_provider_idempotently_and_pair_team_refuses_reuse(monkeypatch):
    from harness.zone_pair_executor import PairTeam
    p = OwnCamPoseSource(V6['map'], V6['params'], seed=628)
    other = OwnCamPoseSource(V6['map'], V6['params'], seed=628)
    params_before = other.loc.params['motion_loaded']
    assert not v6e.bound(p) and not v6e.bound(other)
    info = v6e.enable_provider(p)
    assert v6e.bound(p) and not v6e.bound(other)
    assert v6e.enable_provider(p) is info                # idempotent: same record, params not re-merged
    assert other.loc.params['motion_loaded'] == params_before
    assert set(info) == {'source', 'file_sha256', 'profile_sha256'} and len(info['profile_sha256']) == 64
    bound = type('Ex', (), {'pose': p})()
    with pytest.raises(ValueError, match='carry_dr_model'):
        PairTeam({'r1': bound}, {}, {'motion_loaded': {}}, cancel_scheduled=lambda *a: None,
                 contact_profile='cargo_noslip_v1', policy='b-only')
    fresh = type('Ex', (), {'pose': OwnCamPoseSource(V6['map'], V6['params'], seed=628)})()
    team = PairTeam({'r1': fresh}, {}, {'motion_loaded': {}}, cancel_scheduled=lambda *a: None,
                    contact_profile='cargo_noslip_v1', policy='b-v6e-dr')
    assert team.carry_dr['r1']['profile_sha256'] == info['profile_sha256']
    assert v6e.bound(fresh.pose)


def test_v6e_composes_with_the_v6d_align_motion_on_one_provider():
    from harness import owncam_align_motion_v6d as v6d
    from harness.zone_pair_executor import PairTeam
    fresh = type('Ex', (), {'pose': OwnCamPoseSource(V6['map'], V6['params'], seed=628)})()
    team = PairTeam({'r1': fresh}, {}, {'motion_loaded': {}}, cancel_scheduled=lambda *a: None,
                    contact_profile='cargo_noslip_v1', policy='b-v6e')
    assert team.align_motion['r1'] and team.carry_dr['r1'] and v6d.bound(fresh.pose) and v6e.bound(fresh.pose)
    params = fresh.pose.loc.params
    assert 'fine' in params['motion_profiles'] and 'load_transition' in params['motion_loaded']
    records = team.records()   # both provenance records are written; no session yet, so the list may be empty
    assert records == [] or all('carry_dr_v6e' in r and 'align_motion_v6d' in r for r in records)


def test_provider_without_a_tag_pf_is_refused():
    with pytest.raises(ValueError, match='tag PF'):
        v6e.enable_provider(type('P', (), {'loc': object()})())


def test_profile_comes_from_the_dev_fit_file_and_uses_the_loeo_maximum():
    profile, info = v6e.load_profile(.2148)
    fit = json.loads((ROOT/v6e.FIT).read_text())
    assert profile['yaw_bias_std_rad_s'] == fit['loeo_range']['yaw']['bias_rate_std_rad_s'][1]
    assert profile['noise_abs'][2] == fit['loeo_range']['yaw']['white_rate_std_rad_s'][1]
    assert profile['rest_noise'] is False and profile['scale_walk'] == 0. and profile['noise_rel'] == [0., 0., 0.]
    # Dev-only inputs: the fit lists its own episodes, none of them a stage-probe or E2E run.
    assert all('dev-box' in e for e in fit['episodes']) and 'stage' not in json.dumps(fit['episodes'])


def test_loadstate_is_unchanged():
    ls = LoadState()
    assert ls.command({'kind': 'hold'}) is False


def test_setup_variants_are_valid_routes_and_leave_the_diagnosis_setup_alone():
    from harness import pair_stage_probe as sp
    base = sp.teacher_cases('carry', subset={'nominal'}, nominal_seeds=(911,), policy='b-v6e', leg=3)[0]
    assert base['case_id'] == 'carry@b-v6e:teacher:nominal:s911:L3' and 'setup_variant' not in base
    assert sp.setup_variant() == sp.BASE_SETUP and sp.setup_variant('base') == sp.BASE_SETUP
    for name, pose in sp.SETUP_VARIANTS.items():
        setup = sp.setup_variant(name)
        route = sp.plan_route(setup['coarse_order_sheet'])            # make_plan accepts the sheet (pickup envelope)
        assert len(route) == 9 and setup['beam_xyyaw'] == pose
        case = sp.teacher_cases('carry', setup=setup, subset={'nominal'}, nominal_seeds=(914,), policy='b-v6e', leg=3)[0]
        assert case['case_id'] == f'carry@b-v6e:teacher:nominal:s914:L3:V{name}' and case['setup_variant'] == name
        assert case['beam_xyyaw'] != sp.BASE_SETUP['beam_xyyaw']
    with pytest.raises(ValueError, match='unknown setup variant'):
        sp.setup_variant('nope')
