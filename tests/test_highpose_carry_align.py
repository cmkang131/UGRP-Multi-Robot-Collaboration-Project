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
    assert sig['applied'] and not sig['keep_lateral'] and not sig['keep_yaw'] and sig['sigma_source'] == 'cov_yy'
    assert sig['parent_cmd'] == ref[0][2]
    assert [e['event'] for e in ctl.events] == [ca.ALIGN_EVENT]


def test_significant_offset_keeps_parent_command_bit_identical():
    est = [0.5163, 0.0541 - .08, 0.02]                                 # 80 mm, 1.1 deg off the axis
    ref, _ = parent('r1', est)
    ctl = Ctl('r1', est, report(.02, math.radians(.3)))
    out = ctl.door_schedule(89.1)
    assert out == ref
    assert out[0][2] is not ca.ZERO and ctl.claims['door_align']['significance']['keep_lateral']


def test_partial_component_equals_parent_formula_with_that_component_zero():
    est = [0.5163, 0.0541, 0.03]                                       # dy -4 mm (noise), e_yaw -1.7 deg (significant)
    ctl = Ctl('r1', est, report(.024, math.radians(.5)))
    out = ctl.door_schedule(89.1)
    ref_yaw_only, _ = parent('r1', [est[0], ROUTE[0][1], est[2]])      # parent with dy = 0 exactly
    assert out[0][2] == ref_yaw_only[0][2]
    assert out[0][2]['turn'] != 0. and out[0][2]['left'] == 0. and out[0][2]['forward'] == 0.
    sig = ctl.claims['door_align']['significance']
    assert not sig['keep_lateral'] and sig['keep_yaw']


@pytest.mark.parametrize('rep', [None, report(.02, .01, initialized=False),
                                 report(.02, float('inf')), report(.02, float('nan'))])
def test_no_own_sigma_keeps_parent(rep):
    ref, _ = parent('r1', CASE['r1']['est'])
    ctl = Ctl('r1', CASE['r1']['est'], rep)
    assert ctl.door_schedule(89.1) == ref
    assert ctl.claims['door_align']['significance']['reason'] == 'NO_OWN_SIGMA'


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
