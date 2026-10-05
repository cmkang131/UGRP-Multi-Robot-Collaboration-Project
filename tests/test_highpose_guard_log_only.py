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
