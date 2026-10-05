"""v98 door-axis align significance rule and loaded-gate check log (simulator-free).

Fixture numbers are the 6727751b ``align_to_carry`` probe's own values, recovered by replaying the recorded own frames
and own commands through the real v98 provider offline (replayed measured counts, resamples and repeat weights equal
the recorded ones): own estimate at the carry GO, own report sigma (world-y from the covariance, yaw), and the
recorded align commands. Ground truth is not used by the rule or by these tests.
"""
from __future__ import annotations

import copy
import math
import types

import numpy as np
import pytest

from harness import zone_final_pair_skill as skill
from harness import zone_own_guards as g
from harness import zone_pair_highpose as pose
from harness import zone_pair_highpose_carry_align as ca
from harness import zone_pair_highpose_runtime as rt
from harness.owncam_pose_source import PoseReport
from harness.zone_final_pair_guards import CommandGuard as PreviousGuard

# Loaded motion model of the registered DEV_PILOT calibration (sha256 398372ae..., params.motion_loaded).
MP = {'deadband': {'c0': [0., 0., 0.], 'u1': [0.026556708949971457, 0.028235672526345113, 0.031909184676893604]},
      'gain': [[1.3550711149042434, 0., 0.], [0., 0.9642052319923683, 0.], [0., 0., 0.9073154343172743]],
      'tau_axis_s': [0.9659095671490097, 0.9677901571181826, 0.6555100032553108],
      'tau_s': 0.9659095671490097, 'tau_stop_s': 0.08517977552355656}
ROUTE = [[1.0, .05], [1.4518000000000002, .05]]
# Own grasp estimate (64.7 s), own report sigma at GO (89.1 s; replay) and the recorded align commands of the probe.
CASE = {'r1': dict(est=[0.5171792793854988, 0.05399235912727049, 0.0007244008976337035], sigma_y=0.024287,
                   sigma_yaw=0.019862,
                   rec={'forward': -0.00010632475949521185, 'left': -0.004837350026406446,
                        'turn': -0.002162735291297562}),
        'r2': dict(est=[1.4969129565075623, 0.04047910950014037, 3.1384514083552872], sigma_y=0.022948,
                   sigma_yaw=0.017697,
                   rec={'forward': 0.00033518336334401765, 'left': -0.007402128609000595,
                        'turn': 0.004455553445701024})}


def report(sigma_y, sigma_yaw, initialized=True, std_xy=None):
    cov = ((sigma_y**2*.9, 0., 0.), (0., sigma_y**2, 0.), (0., 0., sigma_yaw**2))
    return PoseReport(t_est=88.94, initialized=initialized, x_m=0., y_m=0., yaw_rad=0., cov=cov,
                      std_xy_m=sigma_y*1.4 if std_xy is None else std_xy, std_yaw_rad=sigma_yaw)


class Base:
    door_schedule = skill.V3Controller.door_schedule


class Ctl(rt.HighController, Base):
    def __init__(self, rid, est, rep):
        self.rid, self.seg, self.grasp_estimate = rid, 0, list(est)
        self.v3_plan, self.v3_params = {'route': copy.deepcopy(ROUTE)}, {'motion_loaded': copy.deepcopy(MP)}
        self.door_plan = {'headings_rad': {'r1': 0., 'r2': math.pi}}
        self.claims, self.events = {}, []
        self.pf = types.SimpleNamespace(pair_plan=None)
        own = types.SimpleNamespace(last_report=rep, pose=types.SimpleNamespace(
            provider=types.SimpleNamespace(loc=types.SimpleNamespace(_pf=self.pf))))
        self.port = types.SimpleNamespace(own=own)

    def log(self, rid, kind, now, **detail):
        self.events.append({'robot_id': rid, 'event': kind, 'sim_s': now, **detail})


def parent(rid, est, t0=89.1):
    ctl = Ctl(rid, est, None)
    return Base.door_schedule(ctl, t0), ctl


def test_parent_reproduces_recorded_align_commands():
    for rid, c in CASE.items():
        sched, _ = parent(rid, c['est'])
        for k in ('forward', 'left', 'turn'):
            assert sched[0][2][k] == pytest.approx(c['rec'][k], rel=2e-2)


def test_mro_next_door_schedule_is_v3_controller():
    from scripts import run_m2_pair as m2
    cls = rt.controller_class(type('B', (skill.V3Controller, m2.M2DoorStudent), {}))
    owners = [k for k in cls.__mro__ if 'door_schedule' in vars(k)]
    assert owners[:2] == [rt.HighController, skill.V3Controller]


@pytest.mark.parametrize('rid', ['r1', 'r2'])
def test_recorded_case_insignificant_align_is_zero_and_rest_unchanged(rid):
    c = CASE[rid]
    ref, ref_ctl = parent(rid, c['est'])
    ctl = Ctl(rid, c['est'], report(c['sigma_y'], c['sigma_yaw']))
    out = ctl.door_schedule(89.1)
    assert out[0][:2] == ref[0][:2] and out[0][2] == ca.ZERO           # same window, all-zero command
    assert out[1:] == ref[1:]                                          # planned leg unchanged
    assert ctl.pf.pair_plan['t0'] == ref_ctl.pf.pair_plan['t0'] and ctl.pf.pair_plan['t1'] == ref_ctl.pf.pair_plan['t1']
    assert np.array_equal(ctl.pf.pair_plan['own'], ref_ctl.pf.pair_plan['own'])
    sig = ctl.claims['door_align']['significance']
    assert sig['applied'] and not sig['would_keep_lateral'] and not sig['would_keep_yaw'] and sig['sigma_source'] == 'cov_yy'
    assert sig['parent_cmd'] == ref[0][2] and sig['would_cmd'] == ca.ZERO and sig['pair_neutral']
    assert [e['event'] for e in ctl.events] == [ca.ALIGN_EVENT]


def test_significant_offset_is_logged_but_loaded_align_stays_zero():
    """v2 pair neutral (2026-10-05, leg 6 @fcc5215f): a significant own offset no longer moves the loaded beam alone."""
    est = [0.5163, 0.0541 - .08, 0.02]                                 # 80 mm, 1.1 deg off the axis
    ref, ref_ctl = parent('r1', est)
    ctl = Ctl('r1', est, report(.02, math.radians(.3)))
    out = ctl.door_schedule(89.1)
    assert out[0][:2] == ref[0][:2] and out[0][2] == ca.ZERO and out[1:] == ref[1:]
    assert ctl.pf.pair_plan['t0'] == ref_ctl.pf.pair_plan['t0'] and ctl.pf.pair_plan['t1'] == ref_ctl.pf.pair_plan['t1']
    sig = ctl.claims['door_align']['significance']
    assert sig['would_keep_lateral'] and sig['would_keep_yaw'] and sig['would_cmd'] == ref[0][2] and sig['cmd'] == ca.ZERO


def test_partial_component_would_command_equals_parent_formula_with_that_component_zero():
    est = [0.5163, 0.0541, 0.03]                                       # dy -4 mm (noise), e_yaw -1.7 deg (significant)
    ctl = Ctl('r1', est, report(.024, math.radians(.5)))
    out = ctl.door_schedule(89.1)
    ref_yaw_only, _ = parent('r1', [est[0], ROUTE[0][1], est[2]])      # parent with dy = 0 exactly
    sig = ctl.claims['door_align']['significance']
    assert out[0][2] == ca.ZERO and sig['would_cmd'] == ref_yaw_only[0][2]
    assert sig['would_cmd']['turn'] != 0. and sig['would_cmd']['left'] == 0. and sig['would_cmd']['forward'] == 0.
    assert not sig['would_keep_lateral'] and sig['would_keep_yaw']


# align_to_carry@fcc5215f leg 6 (seg 5, 419.5 s): the recorded own inputs of each robot's door_align_gate event (v1).
LEG6 = {'r1': dict(dy=0.07577193165194451, e_yaw=0.0023991808351042643, sigma_y=0.034389678684163365,
                   sigma_yaw=0.020899771200884605, keep_lateral=True, keep_yaw=False,
                   parent={'forward': -0.0008340894005443194, 'left': 0.02081937187065634, 'turn': 0.003942040416305804}),
        'r2': dict(dy=0.04426164305041169, e_yaw=-0.014286002203427017, sigma_y=0.03911649268531114,
                   sigma_yaw=0.02097544993162596, keep_lateral=False, keep_yaw=False,
                   parent={'forward': -0.0015555675509619084, 'left': -0.015911300367500346, 'turn': -0.00961933251092436})}


def test_leg6_recorded_inputs_both_robots_zero_and_leg_unchanged():
    """(a) The two ends decided differently in v1 (r1 z 2.20 kept lateral, r2 z 1.13 zero); v2 commands 0 at both ends."""
    leg = (425.5, 444.8, {'forward': 0., 'left': 0.0622, 'turn': 0.})
    outs = {}
    for rid, c in LEG6.items():
        ctl = Ctl(rid, CASE[rid]['est'], report(c['sigma_y'], c['sigma_yaw']))
        ctl.claims['door_align'] = {'dy_m': c['dy'], 'e_yaw_rad': c['e_yaw']}
        sched = [(419.5, 425.5, dict(c['parent'])), leg]
        out = ca.gate_schedule(ctl, sched, 419.5)
        sig = ctl.claims['door_align']['significance']
        assert (sig['would_keep_lateral'], sig['would_keep_yaw']) == (c['keep_lateral'], c['keep_yaw'])
        assert abs(c['dy']) / c['sigma_y'] == pytest.approx({'r1': 2.20, 'r2': 1.13}[rid], abs=.01)
        assert out[0][:2] == (419.5, 425.5) and out[1] == leg and sig['cmd'] == ca.ZERO
        outs[rid] = out[0][2]
        assert [e['event'] for e in ctl.events] == [ca.ALIGN_EVENT] and ctl.events[0]['schema'] == ca.SCHEMA
    assert outs['r1'] == outs['r2'] == ca.ZERO


def _pf_micro():
    """Own localizer as the v98 provider builds it (calibration C motion/pair model, registered static map)."""
    import json
    from pathlib import Path
    from harness import owncam_localizer as m
    root = Path(__file__).resolve().parents[1]
    cal = json.loads((root/'experiments/2026-10-05-unloaded-gain-calibration-v101/products/C/'
                      'calibration_dev_pilot_unloaded_v101.json').read_text())
    sm = json.loads((root/'maps/zones/zone_wide_door_geometry_v3.json').read_text())
    sm.setdefault('landmarks', {'tags': []})
    params = {**copy.deepcopy(m.DEFAULT_PARAMS), **copy.deepcopy(cal['params'])}
    b, bfull = cal['pair_model']['b_rad_s'], cal['params']['motion_loaded']['yaw_bias_std_rad_s']

    def run(cmd, key, seconds=3.0, seed=3):
        loc = m.OwnCamLocalizer(sm, params, seed=seed)
        loc.load.loaded, loc.initialized = True, True
        r = np.random.default_rng(seed + 100)
        loc.px = np.array((2.5092, -1.46, -0.0025)) + r.normal(size=(loc.n, 3))*np.array((0.0272, 0.0344, 0.0209))
        loc.logw, loc.t = np.zeros(loc.n), 419.04
        loc._draw_plant_state(True)
        t = 419.5
        loc.predict_to(t)
        loc.set_extra_yaw_std(t, math.sqrt(max(b[key]**2 - bfull**2, 0.)))
        while t < 419.5 + seconds - 1e-9:
            loc.command({'t': t, 'kind': 'mecanum', 'forward': cmd[0], 'left': cmd[1], 'turn': cmd[2], 'duration_s': .15})
            t = round(t + .1, 6)
            loc.predict_to(t)
        d = (loc.px[:, 2] - loc.px[:, 2].mean() + math.pi) % (2*math.pi) - math.pi
        return math.degrees(d.std())
    return run


def test_pf_micro_zero_align_stays_small_one_sided_align_trips_gate():
    """(b) PF micro control (diagnosis pfmicro.py): with the leg-6 start belief, the one-sided r1 align under the provider
    fallback yaw rate (outside pair_plan, key '') passes the 3 deg loaded gate within 3 s; the v2 zero align does not
    (~1.23 deg; the prediction model's hold assumption gives ~1.44 deg at the end of the leg)."""
    run = _pf_micro()
    one_sided = (LEG6['r1']['parent']['forward'], 0.02081937187065634, 0.)    # recorded r1 command (turn zeroed in v1)
    assert run(one_sided, '') > 3.0
    zero_fallback, zero_pair = run((0., 0., 0.), ''), run((0., 0., 0.), 'pm')
    assert zero_fallback < 1.5 and zero_pair < 1.5
    assert math.degrees(g.GATE_LOADED.high_yaw_rad) == pytest.approx(3.0)


@pytest.mark.parametrize('rep', [None, report(.02, .01, initialized=False),
                                 report(.02, float('inf')), report(.02, float('nan'))])
def test_no_own_sigma_still_pair_neutral(rep):
    ref, _ = parent('r1', CASE['r1']['est'])
    ctl = Ctl('r1', CASE['r1']['est'], rep)
    out = ctl.door_schedule(89.1)
    assert out[0][2] == ca.ZERO and out[1:] == ref[1:]
    sig = ctl.claims['door_align']['significance']
    assert sig['reason'] == 'NO_OWN_SIGMA' and sig['would_cmd'] == ref[0][2]


def test_unusable_covariance_falls_back_to_std_xy():
    rep = report(.024, .01, std_xy=.035)
    rep = PoseReport(**{**rep.__dict__, 'cov': ()})
    assert ca.own_sigmas(rep) == (.035, .01, 'std_xy_m')


def test_z_is_the_two_sided_95_percent_normal_quantile():
    assert math.erf(ca.Z/math.sqrt(2.)) == pytest.approx(.95, abs=1e-12)


# ---------------------------------------------------------------- loaded-gate check log
class FakeEp:
    def __init__(self, state='carry', std_yaw=math.radians(3.02), gate_state='ok', approach_state='carry'):
        self.terminal = False
        self.events = []
        gate = g.UncertaintyGate(g.GATE_LOADED)
        gate.state = gate_state
        rep = PoseReport(t_est=92.04, initialized=True, x_m=.5163, y_m=.0527, yaw_rad=0., cov=(),
                         std_xy_m=.033931, std_yaw_rad=std_yaw, fix_age_s=42.84)
        self.own = types.SimpleNamespace(robot_id='r1', gate=gate, last_report=rep, events=[], servo={**pose.HIGH, 1: 1500})
        self.controller = types.SimpleNamespace(state=approach_state, seg=0, beam_grasp_confirmed=True)

    def log(self, rid, kind, now, **detail):
        self.events.append({'robot_id': rid, 'event': kind, 'sim_s': now, **detail})


MOVE = [{'kind': 'mecanum', 'forward': -0.0001, 'left': -0.0048, 'turn': -0.0022, 'duration_s': .15}]


def guard_for(ep):
    guard = object.__new__(rt.CommandGuard)
    guard.ep = ep
    return guard


def test_gate_log_records_sigmas_thresholds_and_classification():
    ep = FakeEp()
    ca.log_gate_check(guard_for(ep), 92.2, MOVE, [{'kind': 'hold'}])
    (row,) = ep.events
    assert row['event'] == ca.GATE_EVENT and row['report_t_est'] == 92.04
    # task B caveat 3: the own report mean is logged with every check (log only)
    assert (row['report_x_m'], row['report_y_m'], row['report_yaw_rad']) == (.5163, .0527, 0.)
    assert row['std_xy_m'] == pytest.approx(.03393) and row['std_yaw_deg'] == pytest.approx(3.02)
    assert (row['high_xy_m'], row['low_xy_m'], row['high_yaw_rad'], row['low_yaw_rad']) == (
        g.GATE_LOADED.high_xy_m, g.GATE_LOADED.low_xy_m, g.GATE_LOADED.high_yaw_rad, g.GATE_LOADED.low_yaw_rad)
    assert row['classify'] == 'high' and row['profile'] == 'loaded' and row['moving'] and not row['passed']


def test_gate_log_only_for_loaded_checks_with_commands():
    ep = FakeEp(approach_state='approach')
    ca.log_gate_check(guard_for(ep), 50., MOVE, MOVE)
    ep2 = FakeEp()
    ca.log_gate_check(guard_for(ep2), 90., [{'kind': 'hold'}], [{'kind': 'hold'}])
    assert ep.events == [] and ep2.events == []


def test_gate_log_never_raises():
    ep = FakeEp()
    ep.own.gate = None
    ca.log_gate_check(guard_for(ep), 90., MOVE, MOVE)
    assert ep.events[0]['log_error'] == 'AttributeError'


def test_command_guard_check_logs_after_the_unchanged_decision(monkeypatch):
    seen = []

    def frozen(self, now, commands):
        seen.append(copy.deepcopy(commands))
        return [{'kind': 'hold'}] if now > 92. else commands

    monkeypatch.setattr(PreviousGuard, 'check', frozen)
    ep = FakeEp(std_yaw=math.radians(1.2))
    guard = guard_for(ep)
    assert guard.check(91.0, copy.deepcopy(MOVE)) == MOVE
    assert guard.check(92.2, copy.deepcopy(MOVE)) == [{'kind': 'hold'}]
    assert seen == [MOVE, MOVE]
    rows = [e for e in ep.events if e['event'] == ca.GATE_EVENT]
    assert [r['passed'] for r in rows] == [True, False] and rows[0]['classify'] == 'low'


def test_runtime_records_the_rule():
    assert ca.record()['gate_thresholds_changed'] is False and ca.record()['z'] == ca.Z
    assert ca.record()['pair_neutral'] is True and ca.record()['lateral_correction_while_loaded'] is False
    assert ca.ID == 'v98_carry_align_pair_neutral_v2' and ca.SCHEMA.endswith('.v2')
