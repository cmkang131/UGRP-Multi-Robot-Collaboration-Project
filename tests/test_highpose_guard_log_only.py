"""v105 label: PAIR_COLLISION_GUARD log-only (user 2026-10-05 "걍 충돌 방지를 빼"). Simulator-free."""
from __future__ import annotations

import json

import pytest

from harness import zone_pair_highpose_contract as c
from harness import zone_pair_highpose_guard_log_only as lo
from harness import zone_pair_highpose_guardlog as gl
from harness.zone_final_pair_guards import CommandGuard as PreviousGuard, PairGeometry
from tests.test_highpose_guard_veto_log import R1, TOWARD, stand_in
from tests.test_highpose_guard_veto_log import parent_check as _parent


def parent_check(abort_reason=None, via_ep=False):
    if not via_ep:
        return _parent(abort_reason)
    def check(self, now, commands):
        self.ep.abort(now, abort_reason)
        return [{'kind': 'hold'}]
    return check


class _Ep:
    """abort as a class method, like PairExecution (the light-mode wrapper shadows it per check only)."""
    def __init__(self, ns):
        self.__dict__.update(vars(ns))

    def abort(self, t, reason):
        self.own.events.append({'sim_s': t, 'event': 'job_failed', 'detail': {'reason': reason}})


def light_stand_in(fixture):
    guard = stand_in(fixture)
    guard.ep = _Ep(guard.ep)
    guard.ep.log = lambda rid, kind, now, **d: guard.ep.events.append({'robot_id': rid, 'event': kind, 'sim_s': now, **d})
    return guard


def test_flag_is_log_only_and_recorded():
    assert c.COLLISION_GUARD_MODE == 'log_only'
    assert lo.record()['blocks'] is False and lo.record()['other_guards_changed'] is False


def test_would_be_veto_passes_and_is_logged(monkeypatch):
    monkeypatch.setattr(PreviousGuard, 'check', parent_check())
    guard = stand_in(R1)
    commands = [dict(TOWARD)]
    assert guard.check(8.7, commands) is commands                  # not blocked
    assert guard.ep.own.events == []                               # no job_failed
    [event] = guard.ep.events
    assert event['event'] == lo.EVENT and event['would_reason'] == 'PAIR_COLLISION_GUARD'
    [row] = event['would_veto']
    assert row['site'] == 'motion_clear' and row['command'] == TOWARD
    first = row['first_negative']
    assert (first['term'], first['wall_id']) == ('chassis', 'wall_west')
    assert first['clearance_mm'] == pytest.approx(-55.07013142952537, abs=1e-9)
    assert first['margin_terms']['sum_matches'] and row['start_relief_refusal']['refusal']['why'] == 'pair_worse_than_floor'
    json.dumps(guard.ep.events)
    assert guard.veto_trace is None and type(guard.sweep_guard()) is PairGeometry   # not installed outside check


def test_dev_light_logs_pose_uncertain_and_proceeds(monkeypatch):
    monkeypatch.setattr(PreviousGuard, 'check', parent_check('POSE_UNCERTAIN', via_ep=True))
    guard = light_stand_in(R1)
    commands = [dict(R1['cmd'])]
    assert guard.check(8.7, commands) is commands and guard.ep.own.events == []
    [event] = guard.ep.events
    assert event['event'] == c.DEV_LIGHT_EVENT and event['would_reason'] == 'POSE_UNCERTAIN'
    assert 'abort' not in vars(guard.ep)


def test_dev_light_keeps_hard_stops(monkeypatch):
    monkeypatch.setattr(PreviousGuard, 'check', parent_check('BARRIER_CLOSE_ABORT', via_ep=True))
    guard = light_stand_in(R1)
    assert guard.check(8.7, [dict(R1['cmd'])]) == [{'kind': 'hold'}]
    assert guard.ep.own.events[-1]['detail'] == {'reason': 'BARRIER_CLOSE_ABORT'}


def test_other_reasons_still_block_without_dev_light(monkeypatch):
    monkeypatch.setattr(c, 'DEV_LIGHT', False)
    monkeypatch.setattr(PreviousGuard, 'check', parent_check('POSE_UNCERTAIN'))
    guard = stand_in(R1)
    assert guard.check(8.7, [dict(R1['cmd'])]) == [{'kind': 'hold'}]
    assert guard.ep.own.events[-1]['detail'] == {'reason': 'POSE_UNCERTAIN'} and guard.ep.events == []


def test_clear_command_logs_nothing(monkeypatch):
    far = {**R1, 'pose': (-.6, .55, 0., .01, .003)}
    monkeypatch.setattr(PreviousGuard, 'check', parent_check())
    guard, commands = stand_in(far), [dict(R1['cmd'])]
    assert guard.check(8.7, commands) is commands and guard.ep.events == []


# ---------------------------------------------------------------- DEV light v2 (before_control, controller fail)
def test_before_control_soft_abort_proceeds_and_logs(monkeypatch):
    def before(self, now):
        self.ep.abort(now, 'PAIR_SCHEDULED_REOBSERVE_LIMIT')
        return False
    monkeypatch.setattr(PreviousGuard, 'before_control', before, raising=False)
    guard = light_stand_in(R1)
    assert guard.before_control(9.0) is True and guard.ep.own.events == []
    [event] = guard.ep.events
    assert event['event'] == c.DEV_LIGHT_EVENT and event['site'] == 'CommandGuard.before_control'
    assert 'abort' not in vars(guard.ep)


def test_before_control_hard_abort_still_stops(monkeypatch):
    def before(self, now):
        self.ep.abort(now, 'PAIR_RELOOK_WHILE_GRIPPED')
        return False
    monkeypatch.setattr(PreviousGuard, 'before_control', before, raising=False)
    guard = light_stand_in(R1)
    assert guard.before_control(9.0) is False
    assert guard.ep.own.events[-1]['detail'] == {'reason': 'PAIR_RELOOK_WHILE_GRIPPED'}


def test_repeated_soft_stop_is_logged_once_per_window(monkeypatch):
    monkeypatch.setattr(PreviousGuard, 'check', parent_check('POSE_UNCERTAIN', via_ep=True))
    guard = light_stand_in(R1)
    for i in range(c.DEV_LIGHT_LOG_EVERY + 1):
        guard.check(8.7 + i * .05, [dict(R1['cmd'])])
    assert [e['occurrence'] for e in guard.ep.events] == [1, c.DEV_LIGHT_LOG_EVERY + 1]


class _Base:
    rid, state, seg = 'r1', 'wait_carry', 2

    def __init__(self):
        self.logged, self.failed, self.transit = [], [], []

    def log(self, rid, kind, now, **d):
        self.logged.append({'event': kind, **d})

    def fail(self, reason, now):
        self.failed.append(reason)

    def _transit_abort(self, reason, now):
        self.transit.append(reason)


def test_controller_soft_fail_retries_and_hard_fail_fails():
    from harness.zone_pair_highpose_runtime import LightFail
    ctl = type('C', (LightFail, _Base), {})()
    assert ctl.fail('HIGH_CARRY_EDGE_REFERENCE_TIMEOUT', 5.) is None and ctl.failed == []
    assert ctl._transit_abort('HIGH_CHECKPOINT_DR_BUDGET_EXCEEDED', 5.) is None and ctl.transit == []
    assert [e['would_reason'] for e in ctl.logged] == ['HIGH_CARRY_EDGE_REFERENCE_TIMEOUT', 'HIGH_CHECKPOINT_DR_BUDGET_EXCEEDED']
    ctl.fail('BARRIER_CLOSE_ABORT', 5.)
    ctl._transit_abort('LIFT_GRIP_NOT_COMMANDED_CLOSED', 5.)
    assert ctl.failed == ['BARRIER_CLOSE_ABORT'] and ctl.transit == ['LIFT_GRIP_NOT_COMMANDED_CLOSED']


def test_controller_fail_unchanged_without_dev_light(monkeypatch):
    from harness.zone_pair_highpose_runtime import LightFail
    monkeypatch.setattr(c, 'DEV_LIGHT', False)
    ctl = type('C', (LightFail, _Base), {})()
    ctl.fail('HIGH_CARRY_EDGE_REFERENCE_TIMEOUT', 5.)
    assert ctl.failed == ['HIGH_CARRY_EDGE_REFERENCE_TIMEOUT'] and ctl.logged == []


def test_hard_reasons_are_not_soft():
    for reason in ('BARRIER_CLOSE_ABORT', 'PARTNER_ABORT', 'LOADED_BASE_MOTION_REQUIRES_HIGH', 'PAIR_RELOOK_WHILE_GRIPPED',
                   'HIGH_CARRY_VIEW_REQUIRED', 'LIFT_GRIP_NOT_COMMANDED_CLOSED', 'OWN_COMMAND_HISTORY_MISMATCH'):
        assert reason not in c.DEV_LIGHT_SOFT_STOPS
