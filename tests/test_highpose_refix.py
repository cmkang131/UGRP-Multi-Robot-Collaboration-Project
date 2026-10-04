"""v98 sigma-triggered set-down re-fix (zone_pair_highpose_refix), simulator-free.

Tier 1 (state machine): the real HighController + SigmaRefix + the fixed-enum status channel on RECORDED own frames
(tests/test_highpose_transit fixture). The v3 look + re-grasp after ``cp_open`` is a documented TEST STUB
(``M2Stub``): it reproduces the segment step, the grip epoch step of ``_queue_open_descent``, a fresh own fix report,
the close@k+1 barrier (as ``HighController._wait_close``: own report + fixed-enum GO), the floor close and
``wait_lift``; ``stub_look_s`` delays the close readiness (a longer own look); the real path (align entry re-look, pregrasp re-look, hover check, blind close)
is covered by its own tests. The own-sigma prediction is injected (``refix_predictor``).
Tier 2 (model, offline): the predictor on a real v98 PF (tests/highpose_relook_synthetic runtime): restored bit for
bit, and equal to issuing the same commands to the live PF. Not physics; no ground truth enters the controller.
"""
from __future__ import annotations

import hashlib
import math
import sys
from types import SimpleNamespace

import numpy as np
import pytest

from harness import zone_pair_highpose as pose
from harness import zone_pair_highpose_dr_checkpoint as dc
from harness import zone_pair_highpose_refix as rf
from harness import zone_pair_highpose_runtime as rt
from harness.zone_pair_grasp import PairGraspRelook
from harness.zone_pair_highpose_runtime import HighController
from harness.zone_pair_status import MAX_SEGMENTS, PairStatusChannel, PairStatusEndpoint, STATES
from scripts import study_owncam_pair_beam as legacy
from tests import test_highpose_transit as tr
from tests.test_highpose_transit import short_route  # noqa: F401  (autouse fixture)

from harness.zone_pair_grasp import CLOSE_WAIT_S  # noqa: E402  (real close barrier limit, 20 s)

C = rf.confirm_window_s()                                        # echo window (CHECKPOINT_REOBSERVE_S)
D = rf.decide_window_s()                                         # 8 s decision window (decision v4-1)
PASSAGE = {'id': 'door_1', 'axis_y_m': .05, 'x_range_m': [2.175, 2.225],
           'envelope': {'x_m': [-.6732, .6732], 'y_m': [-.2, .2]}, 'measured_free_width_m': .5}
ROUTE = [[1.0, .05], [1.4518, .05], [2.2, .05], [2.9482, .05], [2.9482, -.6667], [2.9482, -1.3833],
         [2.9482, -2.1], [3.7741, -2.1], [4.6, -2.1]]          # registered v98 route (beam centre)
BEFORE_DOOR = ROUTE[:3]                                          # stop 1 before the door
IN_DOOR = ROUTE[1:4]                                             # stop 1 = beam at the door centre
BEAM_GEOMETRY = {'center_m': [0., 0., .016], 'half_extents_m': [.3, .02, .016],       # registered v98 plan (static)
                 'grasps': {'end_neg': {'xyz_m': [-.27, 0., .024], 'yaw_rad': 0.},
                            'end_pos': {'xyz_m': [.27, 0., .024], 'yaw_rad': math.pi}}}


def plan(route, checkpoints=None):
    return {'route': [list(p) for p in route], 'passage': PASSAGE, 'checkpoint_segments': checkpoints or {}}


class M2Stub(legacy.PairStudent):
    """TEST STUB of the M2/V3 intermediate release and re-grasp (see module docstring)."""

    def _wait_open(self, now, arm_idle):          # = scripts/run_m2_pair.M2DoorStudent._wait_open
        if self.seg+1 >= len(self.segments):
            return super()._wait_open(now, arm_idle)

        def go(t):
            self.arm.queue({1: legacy.OPEN}, t, duration=.4, settle=.5)
            self.arm.queue({**self.hover, 1: legacy.OPEN}, t, duration=.6)
        self._wait('open', 'cp_open', now, go)

    def _cp_open(self, now, arm_idle):
        if not arm_idle:
            return
        self.seg += 1
        self.grip_epoch += 1                       # HighController._queue_open_descent
        self.high_raising = self.high_ready = False
        self.pose_anchors, self.transit = {}, None
        self.sigma, self.fix_t = self.sigma_after_look, now   # the stub look gives a fresh own fix
        self.arm.queue({**self.hover, 1: legacy.OPEN}, now, duration=.6)
        self.set('stub_hover', now)

    def _stub_hover(self, now, arm_idle):
        # STUB of HoverConfirm's hover check (2 distinct passing own frames) + the REAL re-fix hover@k+1 gate
        # (SigmaRefix.hover_barrier_gate); ``stub_look_s`` delays the own hover readiness (a longer own look).
        if not arm_idle or now < self.state_t+getattr(self, 'stub_look_s', 0.)-1e-9:
            return
        obs = self.look(now)
        if obs['frame_id'] != getattr(self, 'blind_hover_last_frame', None):
            self.blind_hover_streak = getattr(self, 'blind_hover_streak', 0)+1
        self.blind_hover_last_frame = obs['frame_id']
        if self.blind_hover_streak < 2 or not self.hover_barrier_gate(now, obs):
            return
        self.blind_hover_streak = 0
        self.arm.queue({**self.grasp_pose, 1: legacy.OPEN}, now, duration=.6)     # the fixed descent
        self.set('stub_wait_close', now)

    def _stub_wait_close(self, now, arm_idle):
        ready_at = self.state_t
        if not arm_idle:
            return
        # = HighController._wait_close (runtime): the inherited close barrier limit CLOSE_WAIT_S (20 s), counted from
        # the own close readiness (review delta2 P1-1: the stub used to wait forever, so tests passed what the real
        # controller cannot do)
        if now-ready_at > CLOSE_WAIT_S:
            return self.fail('BARRIER_CLOSE_TIMEOUT', now)
        decision = self.sync_for('close').authorize(now)
        if decision['phase'] == 'GO':
            self.log(self.rid, 'barrier_go', now, barrier='close')
            self.arm.queue({1: legacy.CLOSED}, decision['go_at_s'], duration=.5, settle=.4)
            return self.set('stub_regrasp', now)
        if now >= self.next_look-1e-9:
            self.next_look = now+legacy.LOOK_EVERY_S
            self.report('close', self.look(now), now, ready=True, reason='stub close readiness')

    def _stub_regrasp(self, now, arm_idle):
        if not arm_idle:
            return
        self.grip_closed_epoch = self.grip_epoch
        self._anchor('floor', self.look(now), now)
        self.set('wait_lift', now)


class Ctl(rf.SigmaRefix, HighController, M2Stub):
    __init__ = tr.Controller.__init__
    observation, look = tr.Controller.observation, tr.Controller.look


@pytest.fixture(autouse=True)
def stub_states(monkeypatch):
    monkeypatch.setitem(legacy.STATUS_OF, 'cp_open', 'put_down')         # = run_m2_pair.STATUS_OF
    monkeypatch.setitem(legacy.STATUS_OF, 'stub_regrasp', 'aligning')
    monkeypatch.setitem(legacy.STATUS_OF, 'stub_wait_close', 'aligning')
    monkeypatch.setitem(legacy.STATUS_OF, 'stub_hover', 'aligning')


def pred(over, sxy=.06):
    return {'over': over, 'reasons': ['gate_xy'] if over else [], 'std_xy_m': sxy, 'std_yaw_rad': .02,
            'door_pl_m': None, 'budget_xy_m': rf.budget(2000)[0]}


def team(route, *, over=None, post_over=None, checkpoints=None, sigma=None):
    """over/post_over: rid -> bool or callable(stop) for the decision / post-re-fix check."""
    bus = PairStatusChannel('high-refix')
    ctls = [Ctl(r, bus, tuple(.1 for _ in route[1:])) for r in ('r1', 'r2')]
    for c in ctls:
        c.ep.tick('ready', 0.)
        c.v3_plan = plan(route, checkpoints)
        c.calls = []
        c.sigma = (sigma or {}).get(c.rid, (.042, math.radians(1.4)))
        c.sigma_after_look = (.025, math.radians(.8))
        c.fix_t = -30.

        def predictor(ctl, legs, now, lead_hold_s=0., _c=c):
            post = ctl.state == 'wait_carry'
            _c.calls.append({'legs': list(legs), 't': now, 'post': post, 'seg': ctl.seg, 'lead_hold_s': lead_hold_s})
            table = post_over if post else over
            v = (table or {}).get(ctl.rid, False)
            return pred(v(legs[0]) if callable(v) else v)
        c.refix_predictor = predictor
    return bus, ctls


def run(ctls, until):
    for i in range(int(round(until/.1))+1):
        run_one(ctls, round(i*.1, 8))
    return ctls


def run_one(ctls, now):
    for c in ctls:
        sxy, syaw = c.sigma
        # void_at_stop: the real provider's begin_relocalization at checkpoint_high_stop sets last_fix_t None
        voided = getattr(c, 'void_at_stop', False) and getattr(c, 'checkpoint_fix_after', None) is not None
        fix = None if voided else c.fix_t
        if voided and getattr(c, 'sigma_after_stop', None) is not None:
            sxy, syaw = c.sigma_after_stop
        c.port.own.last_report = SimpleNamespace(t_est=now, initialized=True, last_fix_t=fix, std_xy_m=sxy,
                                                 std_yaw_rad=syaw, x_m=1.2, y_m=.05, yaw_rad=0.)
        if c.state not in ('failed', 'released', 'done'):
            c.tick(now)
    for c in ctls:
        if c.state != 'failed':
            c.arm.tick(now)


def ev(c, name):
    return [e for e in c.events if e['event'] == name]


def opens(c):
    """Times at which the issued grip pulse changes to OPEN (one per release)."""
    out, prev = [], legacy.CLOSED
    for t, a in c.issued_log:
        if a.get('servo_id') == 1:
            if a['pulse'] == legacy.OPEN and prev != legacy.OPEN:
                out.append(t)
            prev = a['pulse']
    return out


def published(bus, rid, state):
    return [m['sent_at_s'] for m in bus.log if m['robot_id'] == rid and m['state'] == state]


def test_predicted_over_budget_triggers_one_pair_refix_and_resets_sigma():
    # decision v6-1: both robots release, look and re-grasp (the v4 path; keep-hold withdrawn)
    bus, ctls = team(BEFORE_DOOR, over={'r1': True})
    run(ctls, 140.)
    for c in ctls:
        assert c.failure is None and c.state == 'released', (c.rid, c.failure, c.state)
        d = ev(c, 'refix_decision')
        assert len(d) == 1 and d[0]['stop'] == 1 and d[0]['refix'] is True
        assert d[0]['own']['horizon_legs'] == [1]
        assert getattr(c, 'refix_count', 0) == 1
        down, rel, up = ev(c, 'refix_set_down'), ev(c, 'refix_released'), ev(c, 'refix_resumed_high')
        assert len(down) == len(rel) == len(up) == 1 and down[0]['t'] < rel[0]['t'] < up[0]['t']
        assert down[0]['sigma_before']['std_xy_m'] == pytest.approx(.042)
        assert up[0]['horizon_check']['horizon_legs'] == [1] and not up[0]['horizon_check']['prediction']['over']
        assert up[0]['sigma_after']['std_xy_m'] == pytest.approx(.025)                     # reset by the look
        assert len(opens(c)) == 2 and opens(c)[0] < up[0]['t']           # released at the stop and at delivery
        assert pose.at_high(c.port.own.servo) is False                     # delivered on the floor
        # approach@1 = the hover@k+1 pair barrier on the existing wire values (review delta2 P1-1, decision A)
        assert set(c.ep.barriers) == {'carry@0', 'lower@0', 'open@0', 'approach@1', 'close@1', 'lift@1', 'carry@1', 'lower@1',
                                      'open@1'}
        assert max(int(k.split('@')[1]) for k in c.ep.barriers) == 1 < MAX_SEGMENTS
        assert not ev(c, 'checkpoint_high_stop')                          # the HIGH stop path was not taken
    r1, r2 = ctls
    assert ev(r1, 'refix_decision')[0]['own']['request'] and not ev(r2, 'refix_decision')[0]['own']['request']
    assert ev(r2, 'refix_decision')[0]['partner_request']
    t_end = ev(r1, 'refix_decision')[0]['t_end']
    assert published(bus, 'r1', 'uncertain') and min(published(bus, 'r1', 'uncertain')) >= t_end-1e-8
    assert published(bus, 'r2', 'uncertain')                              # r2 echoes the agreed decision
    assert max(published(bus, 'r2', 'uncertain')) <= t_end+D+C+.1
    d1, entered = ev(r1, 'refix_decision')[0], r1.refix_decision['hook']['entered_s']
    assert d1['own']['lead_hold_s'] == pytest.approx(rf.lead_hold_s(t_end, entered))   # rest of this stop predicted
    assert d1['t'] == pytest.approx(t_end+D, abs=.11)                                  # executed at the window end


class ReceiptCtl(Ctl):
    """Ctl whose stub release / re-grasp also keep the own grasp receipt as the real parent does.

    The open mirrors ``PairGraspRelook.on_issued_command`` (an issued grip pulse >= 2000 clears the receipt) and the
    re-grasp mirrors ``PairGraspRelook._grasp`` (receipt minted with the current ``seg``; zone_pair_grasp.py). The
    HIGH stops use the real ``HighController`` checkpoint with ``carry_grasp_receipt`` (#363 496da4ea)."""

    def _cp_open(self, now, arm_idle):
        if arm_idle:
            PairGraspRelook.on_issued_command(self, {'kind': 'arm', 'servo_id': 1, 'pulse': legacy.OPEN, 't': now})
        return super()._cp_open(now, arm_idle)

    def _stub_regrasp(self, now, arm_idle):
        super()._stub_regrasp(now, arm_idle)
        if self.state == 'wait_lift':
            self.beam_grasp_receipt = {'segment': self.seg, 'frame_id': 0, 'sha256': 'stub', 'source': 'stub regrasp'}


def test_after_a_refix_both_robots_read_carrying_on_every_later_leg(monkeypatch):
    # #363 author request (issuecomment-5983294916): with the receipt carry of 496da4ea, the re-fix (open + re-grasp,
    # outside checkpoint()) must leave carrying_beam true for both robots on every later leg, HIGH stops included.
    monkeypatch.setattr(sys.modules[__name__], 'Ctl', ReceiptCtl)
    _, ctls = team(ROUTE[:5], over={'r1': lambda leg: leg == 1})                # re-fix at stop 1 only
    for c in ctls:
        c.beam_grasp_receipt = {'segment': 0, 'frame_id': 0, 'sha256': 'first', 'source': 'test'}
    legs = {c.rid: {} for c in ctls}
    for i in range(int(round(320./.1))+1):
        run_one(ctls, round(i*.1, 8))
        for c in ctls:
            if c.state == 'carry':
                legs[c.rid].setdefault(c.seg, []).append(bool(PairGraspRelook.beam_grasp_confirmed.fget(c)))
    for c in ctls:
        assert c.failure is None and c.state == 'released', (c.rid, c.failure)
        assert c.refix_count == 1 and len(ev(c, 'checkpoint_high_stop')) == 2            # stops 2 and 3 at HIGH
        assert sorted(legs[c.rid]) == [0, 1, 2, 3] and all(all(v) for v in legs[c.rid].values()), legs[c.rid]
        carried = ev(c, rt.GRASP_RECEIPT_CARRIED_EVENT)
        assert [e['segment'] for e in carried] == [2, 3] and {e['minted_segment'] for e in carried} == {1}
        assert c.beam_grasp_receipt['sha256'] == 'stub'                                  # minted by the re-grasp


def test_both_robots_decide_at_the_same_stop_with_the_same_route_point():
    _, ctls = team(BEFORE_DOOR, over={'r2': True})
    run(ctls, 140.)
    stops = [(e['stop'], e['refix'], e['t_end']) for c in ctls for e in ev(c, 'refix_decision')]
    assert len(stops) == 2 and len(set(stops)) == 1
    assert [c.schedule[-1][1] for c in ctls][0] == pytest.approx(ctls[1].schedule[-1][1])


def test_no_request_keeps_the_high_stop_and_costs_one_window():
    _, ctls = team(BEFORE_DOOR)
    run(ctls, 90.)
    for c in ctls:
        assert c.failure is None and c.state == 'released'
        d = ev(c, 'refix_decision')[0]
        assert d['refix'] is False and not ev(c, 'refix_set_down')
        stop = ev(c, 'checkpoint_high_stop')[0]
        assert D <= stop['t']-d['t_end'] <= D+1.                          # 10 s window + barrier rendezvous
        assert len(ev(c, dc.DR_EVENT)) == 1 and len(opens(c)) == 1          # DR receipt, released only at delivery


def test_refix_at_the_doorway_stop_is_allowed():
    # coordinator decision 2(a), 2026-10-04: the stop with the beam in the door is a set-down + look stop too
    _, ctls = team(IN_DOOR, over={'r1': True})
    run(ctls, 140.)
    for c in ctls:
        assert c.failure is None and c.state == 'released', (c.rid, c.failure)
        d = ev(c, 'refix_decision')
        assert len(d) == 1 and d[0]['stop'] == 1 and d[0]['refix'] and d[0]['own']['horizon_legs'] == [1]
        assert c.refix_count == 1 and len(opens(c)) == 2 and not ev(c, 'checkpoint_high_stop')


def test_refix_count_is_bounded_by_the_intermediate_stops():
    route = ROUTE[:5]                                     # stops 1, 2 (door), 3
    _, ctls = team(route, over={'r1': True, 'r2': True})
    run(ctls, 320.)
    eligible = [j for j in range(1, len(route)-1) if rf.eligible(plan(route), j)]
    assert eligible == [1, 2, 3]
    for c in ctls:
        assert c.failure is None and c.state == 'released', (c.rid, c.failure)
        assert c.refix_count == len(eligible) == len(ev(c, 'refix_set_down'))
        assert [e['stop'] for e in ev(c, 'refix_decision')] == eligible     # once per stop, never repeated
        assert c.seg == len(route)-2 < MAX_SEGMENTS


def test_window_skew_fails_closed_with_the_beam_at_high(monkeypatch):
    # r2's leg ends 3 s later (> C): r2 decides at its own t_end + D, after r1's echo deadline t_end + D + C, so r1
    # never sees an echo in time -> REFIX_DISAGREEMENT, beam still at HIGH.
    monkeypatch.setattr(legacy, 'build_schedule', lambda rid, t: [(t, t+.2+(3. if rid == 'r2' else 0.),
                                                                     {'forward': .01, 'left': 0., 'turn': 0.})])
    _, ctls = team(BEFORE_DOOR, over={'r1': True})
    run(ctls, 90.)
    r1, r2 = ctls
    assert r1.failure == rf.DISAGREE and r2.failure == 'PARTNER_ABORT'
    for c in ctls:
        assert len(opens(c)) == 0 and pose.at_high(c.port.own.servo)       # nothing lowered, nothing released


@pytest.mark.parametrize('checkpoints', [{'before_door': 1}, None])
def test_own_dr_report_over_budget_requests_a_refix_at_any_stop_instead_of_aborting(checkpoints):
    # the prediction says "fine" but r2's own report is already over the derived DR receipt budget (67.4 mm)
    _, ctls = team(BEFORE_DOOR, checkpoints=checkpoints, sigma={'r2': (.0700, math.radians(1.6))})
    run(ctls, 140.)
    for c in ctls:
        assert c.failure is None and c.state == 'released', (c.rid, c.failure)
        assert c.refix_count == 1 and not ev(c, dc.OVER_EVENT) and not ev(c, 'checkpoint_high_stop')
    assert ev(ctls[1], 'refix_decision')[0]['own']['dr_receipt_over'] is True
    assert ev(ctls[0], 'refix_decision')[0]['own']['dr_receipt_over'] is False


@pytest.mark.parametrize('over', [False, True])
def test_voided_fix_receipt_at_the_high_stop_continues_or_refixes_never_times_out(over):
    # Author's finding at 1f7fb800 (align_to_carry, 110 s): begin_relocalization at the HIGH stop sets last_fix_t None;
    # the old receipt waited for a fix that cannot come and hit HIGH_CHECKPOINT_REOBSERVE_TIMEOUT at sigma 36/39 mm.
    # With dr_voided_receipt (e4c30dfb) + this mixin: in budget -> DR receipt at the HIGH stop and the carry goes on;
    # over budget -> the pair re-fixes. Neither ends in the re-observe wait.
    sxy = .0700 if over else .0388
    _, ctls = team(BEFORE_DOOR, sigma={'r1': (.0364, math.radians(1.15)), 'r2': (sxy, math.radians(1.2))})
    for c in ctls:
        c.void_at_stop = True
    run(ctls, 140.)
    for c in ctls:
        assert c.failure is None and c.state == 'released', (c.rid, c.failure)
        assert not ev(c, dc.OVER_EVENT)
        if over:
            assert c.refix_count == 1 and not ev(c, 'checkpoint_high_stop') and not ev(c, dc.DR_EVENT)
        else:
            assert getattr(c, 'refix_count', 0) == 0 and len(opens(c)) == 1
            stop, got = ev(c, 'checkpoint_high_stop')[0], ev(c, dc.DR_EVENT)
            assert len(got) == 1 and got[0]['fix_receipt_voided'] and got[0]['fix_t'] is None
            assert got[0]['t']-stop['t'] < rf.confirm_window_s()+.2        # at the minimum stop, not 8 s
            assert any(e['event'] == 'barrier_go' and e['barrier'] == 'carry' and e['t'] > got[0]['t']
                       for e in c.events)


def test_post_refix_horizon_still_over_budget_aborts_at_high_before_the_leg():
    _, ctls = team(BEFORE_DOOR, over={'r1': True}, post_over={'r2': True})
    run(ctls, 140.)
    r1, r2 = ctls
    assert r2.failure == rf.INFEASIBLE and r1.failure == 'PARTNER_ABORT'
    up = ev(r2, 'refix_resumed_high')[0]
    assert up['horizon_check']['prediction']['over'] is True
    assert 'carry@1' not in r2.ep.barriers and pose.at_high(r2.port.own.servo)


def test_a_longer_own_look_within_the_close_limit_delays_the_pair_close_and_lift_together():
    # v6-1: both look; the pair re-grasps together at the close@1 barrier, set by the longer look (r1 +15 s < 20 s)
    _, ctls = team(BEFORE_DOOR, over={'r1': True})
    ctls[0].stub_look_s = 15.
    run(ctls, 170.)
    for c in ctls:
        assert c.failure is None and c.state == 'released', (c.rid, c.failure)
        assert len(ev(c, 'refix_released')) == 1 and len(opens(c)) == 2
    go = {c.rid: [e['t'] for e in ev(c, 'barrier_go') if e['barrier'] in ('close', 'lift')] for c in ctls}
    assert go['r1'] == go['r2'] and len(go['r1']) == 2
    assert go['r1'][0]-ev(ctls[0], 'refix_released')[0]['t'] >= 15.


def test_a_look_more_than_20s_longer_waits_at_the_hover_barrier_and_the_pair_closes_together():
    # Review delta2 P1-1 fixed by decision (A): r1 looks 25 s longer (> CLOSE_WAIT_S). r2 waits at the hover@k+1 barrier
    # (before the blind descent), both pass a fresh hover confirmation after the GO, and the pair closes and lifts
    # together; close@1 arrival skew is the descent difference only.
    _, ctls = team(BEFORE_DOOR, over={'r1': True})
    ctls[0].stub_look_s = 25.
    run(ctls, 200.)
    for c in ctls:
        assert c.failure is None and c.state == 'released', (c.rid, c.failure)
    hover = {c.rid: [e for e in ev(c, 'barrier_go') if e['barrier'] == rf.HOVER_BARRIER] for c in ctls}
    assert len(hover['r1']) == len(hover['r2']) == 1 and hover['r1'][0]['t'] == hover['r2'][0]['t']
    assert hover['r2'][0]['waited_s'] >= 25.-1. and hover['r1'][0]['wire'] == 'approach@1'
    go = {c.rid: [e['t'] for e in ev(c, 'barrier_go') if e['barrier'] in ('close', 'lift')] for c in ctls}
    assert go['r1'] == go['r2'] and len(go['r1']) == 2
    for c in ctls:
        assert len(ev(c, 'refix_hover_reconfirmed')) == 1
        assert ev(c, 'refix_hover_reconfirmed')[0]['t'] > hover[c.rid][0]['t']        # fresh confirmation after GO


def test_a_partner_slower_than_the_derived_hover_limit_stops_the_pair_cleanly():
    # hover@k+1 limit = the partner's own limits from the open GO to its close readiness (123.94 s, recorded terms)
    assert rf.hover_barrier_limit_s() == pytest.approx(123.94)
    _, ctls = team(BEFORE_DOOR, over={'r1': True})
    ctls[0].stub_look_s = rf.hover_barrier_limit_s()+10.
    run(ctls, 320.)
    r1, r2 = ctls
    assert r2.failure == rf.HOVER_TIMEOUT and r1.failure == 'PARTNER_ABORT'
    t = ev(r2, 'refix_hover_barrier_timeout')[0]
    assert t['waited_s'] > rf.hover_barrier_limit_s() and t['limit_s'] == rf.hover_barrier_limit_s()
    for c in ctls:                       # both released the beam at the stop, none descended or closed again
        assert len(ev(c, 'refix_released')) == 1 and not [e for e in ev(c, 'barrier_go') if e['barrier'] == 'close']


def test_keep_hold_is_withdrawn_and_recorded():
    k = rf.record()['keep_hold']
    assert k['implemented'] is False and 'v6-1' in k['decision'] and len(k['why_withdrawn']) == 4
    assert not hasattr(rf, 'KEEP_STATE') and 'refix_keep_hold' not in rf.EVENTS
    assert len(rf.record()['no_look_regrasp']['blocking_gates']) == 5


def test_status_vocabulary_is_unchanged_and_the_window_state_is_owned_by_the_mixin():
    assert rf.REQUEST_STATUS in STATES and rf.DECIDE_STATE not in legacy.STATUS_OF
    assert 'tick' in vars(rf.SigmaRefix)


def test_mixin_placement_in_the_v98_class():
    from harness.zone_final_pair_skill import V3Controller
    from harness.zone_pair_highpose_posture_defer import DeferRelook
    from scripts import run_m2_pair as m2
    cls = rt.controller_class(type('B', (V3Controller, m2.M2DoorStudent), {}))
    mro = cls.__mro__
    assert mro[1] is DeferRelook and mro[2] is rf.SigmaRefix and mro[3] is HighController
    assert '_wait_lower' in vars(HighController) and '_wait_open' in vars(HighController)


# ------------------------------------------------------------------ record-derived: align_to_carry@1f7fb800, 101.9 s
# Values copied from the recorded run (no simulator access in the test). Source:
# outputs/v98-dev-probe-align_to_carry-1f7fb800/zone_wide_door_geometry_v3/student_record.json
# sha256 a609368e4e7b44361ea2cc011c0ad668aef4351466e17b9ebef6a75d9fdda2e2.
# * last loaded_gate_check before the stop (pair.robots.<rid>.events, sim 101.3 s, report_t_est 101.14): own std_xy,
#   std_yaw, fix_age_s;
# * provider lifecycle begin_relocalization (robots.<rid>.provider.provider.lifecycle, cutoff 101.74 = stop 101.9 -
#   0.16 s delay): previous_fix_t, the belief covariance kept through the reset ('before'.std), last_scan_t -> None.
# Timeline in the record: leg end (wait_lower) 101.4, lower barrier + checkpoint_high_stop 101.9, then the old rule
# waited for a fix and failed r1 HIGH_CHECKPOINT_REOBSERVE_TIMEOUT at 110.0 (r2 PARTNER_ABORT).
RECORD_1F7F = {
    'r1': {'gate': {'std_xy_m': .0364, 'std_yaw_rad': .020076, 'fix_age_s': 49.19},
           'reloc': {'previous_fix_t': 51.95000000015704,
                     'cov': [[.00079077, 1.953e-05, -6.925e-05], [1.953e-05, .0005548, 8.682e-05],
                             [-6.925e-05, 8.682e-05, .00040865]]}},
    'r2': {'gate': {'std_xy_m': .0388, 'std_yaw_rad': .019699, 'fix_age_s': 43.09},
           'reloc': {'previous_fix_t': 58.05000000018617,
                     'cov': [[.00073073, 5.23e-06, -1.85e-06], [5.23e-06, .00080111, .00025383],
                             [-1.85e-06, .00025383, .00039468]]}}}


def _record_sigma(cov):
    return math.sqrt(cov[0][0]+cov[1][1]), math.sqrt(cov[2][2])        # std_xy as the provider reports it


def test_record_1f7fb800_checkpoint_continues_on_a_voided_dr_receipt_with_the_real_predictor(tmp_path, monkeypatch):
    """Recorded sigma + the recorded begin_relocalization transition drive the decision and the HIGH stop receipt;
    the horizon prediction is the real ``predict`` on a real v98 PF started from the recorded covariance."""
    from tests import highpose_relook_synthetic as syn
    runtime = syn.build(syn.admitted_copy(tmp_path, monkeypatch), seed=911)
    try:
        mp = runtime.providers['r1'].provider.calibration['params']['motion_loaded']
        pfs = {}
        for rid, x, yaw in (('r1', ROUTE[1][0]-.4732, 0.), ('r2', ROUTE[1][0]+.4732, math.pi)):
            pf = runtime.providers[rid].provider.loc._pf
            cov = np.asarray(RECORD_1F7F[rid]['reloc']['cov'])
            pf.init_gaussian(np.array([x, ROUTE[1][1], yaw]), np.sqrt(np.diag(cov)))   # correlations dropped
            pf.load.loaded = True
            pf._draw_plant_state(True)
            pfs[rid] = pf
        _, ctls = team(BEFORE_DOOR)
        for c in ctls:
            g, r = RECORD_1F7F[c.rid]['gate'], RECORD_1F7F[c.rid]['reloc']
            c.sigma = (g['std_xy_m'], g['std_yaw_rad'])                     # own report up to the stop
            c.fix_t = -g['fix_age_s']                                       # fix ~49 / 43 s old at the leg end
            c.void_at_stop = True                                           # begin_relocalization -> last_fix_t None
            c.sigma_after_stop = _record_sigma(r['cov'])                    # belief kept through the reset
            c.refix_predictor = (lambda ctl, legs, now, lead_hold_s=0.: rf.predict(
                pfs[ctl.rid], plan(BEFORE_DOOR), ctl.rid, legs, mp, door=rf.door_of(plan(BEFORE_DOOR)),
                lead_hold_s=lead_hold_s))
        run(ctls, 80.)
    finally:
        runtime.close()
    for c in ctls:
        assert c.failure is None and c.state == 'released', (c.rid, c.failure)
        d = ev(c, 'refix_decision')[0]
        assert d['refix'] is False and not d['own']['dr_receipt_over']
        assert d['own']['prediction']['std_xy_m'] <= dc.BUDGET_XY_M and not d['own']['prediction']['over']
        got = ev(c, dc.DR_EVENT)
        assert len(got) == 1 and got[0]['fix_receipt_voided'] and got[0]['fix_t'] is None
        assert got[0]['std_xy_m'] == pytest.approx(_record_sigma(RECORD_1F7F[c.rid]['reloc']['cov'])[0])
        assert not ev(c, dc.OVER_EVENT)
        assert any(e['event'] == 'barrier_go' and e['barrier'] == 'carry' and e['t'] > got[0]['t'] for e in c.events)
    # the pre-fix rule on the same recorded report waits (-> the recorded 8 s timeout); the shipped rule gives a DR receipt
    rep = SimpleNamespace(t_est=11.3, initialized=True, last_fix_t=None, std_xy_m=_record_sigma(RECORD_1F7F['r1']['reloc']['cov'])[0],
                          std_yaw_rad=_record_sigma(RECORD_1F7F['r1']['reloc']['cov'])[1], x_m=0., y_m=0., yaw_rad=0.)
    assert dc.decide(rep, 11.3, 10., 10., C)[0] == "dr"


# ------------------------------------------------------------------ geometry and budget (pinned derivation)
def test_budget_and_door_alert_limit_follow_the_derivation():
    from harness.zone_own_guards import GATE_LOADED
    assert (rf.GATE_XY_M, rf.GATE_YAW_RAD) == (GATE_LOADED.high_xy_m, GATE_LOADED.high_yaw_rad)
    assert rf.GATE_XY_M == .07 and rf.GATE_YAW_RAD == pytest.approx(math.radians(3.))
    bxy, byaw = rf.budget(2000)
    assert bxy == pytest.approx(.07*(1-1.645/math.sqrt(2000))) and byaw == pytest.approx(math.radians(3.)*(1-1.645/math.sqrt(2000)))
    assert rf.door_alert_limit(plan(ROUTE)) == pytest.approx(.110)
    assert 1.96*.0561 <= .110+1e-9 < 1.96*.0562                            # sigma_y limit ~56 mm (yaw term 0)


def test_eligibility_and_horizon_on_the_registered_route():
    p = plan(ROUTE)
    assert [j for j in range(len(ROUTE)) if rf.eligible(p, j)] == [1, 2, 3, 4, 5, 6, 7]   # decision 2(a)
    assert rf.horizon(p, 1) == [1] and rf.horizon(p, 2) == [2] and rf.horizon(p, 7) == [7]
    assert not rf.eligible(p, 0) and not rf.eligible(p, len(ROUTE)-1)       # start and delivery are not re-fixes


def test_summary_flags_the_door_only_while_the_chassis_overlaps_it():
    door = rf.door_of(plan(ROUTE))
    inside = [(1., 0, 2.20, 0., .05, .02, .01, .06)]                     # sigma_y 60 mm in the door
    outside = [(1., 0, 1.80, 0., .05, .02, .01, .06)]
    assert rf.summarize(inside, 2000, door=door)['reasons'] == ['door_pl']
    assert rf.summarize(outside, 2000, door=door)['reasons'] == []


# ------------------------------------------------------------------ tier 2: the predictor on a real v98 PF
def _digest(pf):
    h = hashlib.sha256()
    for k in sorted(vars(pf)):
        v = vars(pf)[k]
        if callable(v) or k == 'rng':
            continue
        h.update(k.encode())
        h.update(np.ascontiguousarray(v).tobytes() if isinstance(v, np.ndarray) else repr(v).encode())
    h.update(repr(pf.rng.bit_generator.state).encode())
    return h.hexdigest()


@pytest.fixture
def live_pf(tmp_path, monkeypatch):
    from tests import highpose_relook_synthetic as syn
    runtime = syn.build(syn.admitted_copy(tmp_path, monkeypatch), seed=3)
    src = runtime.providers['r1'].provider
    pf = src.loc._pf
    pf.init_gaussian(np.array([.9786, .05, 0.]), np.array([.03, .03, .012]))
    pf.load.loaded = True
    pf._draw_plant_state(True)                                           # the loaded plant draw at the grasp
    yield pf, src.calibration['params']['motion_loaded']
    runtime.close()


def _issue_like_predict(pf, legs, mp, lead=0.):
    """The same command sequence ``predict`` uses, issued to the live PF (what the carry would do)."""
    from scripts.run_m2_pair import DOOR_ALIGN_S
    t = float(pf.t)
    if lead > 0.:
        pf.command({'t': t, 'kind': 'hold'})
        t = rf_advance(pf, t, t+lead)
    for i, k in enumerate(legs):
        p = rf.leg_plan(plan(ROUTE), k, 'r1', mp)
        pf.command({'t': t, 'kind': 'hold'})
        t = rf_advance(pf, t, t+DOOR_ALIGN_S+.5)
        u = np.asarray(p['u'], float)
        pf.pair_plan = {'t0': t, 't1': t+p['duration_s'], 'own': u.copy(), 'partner': -u.copy()}
        pf.command({'t': t, 'kind': 'mecanum', 'forward': p['u'][0], 'left': p['u'][1], 'turn': p['u'][2],
                    'duration_s': p['duration_s']})
        t = rf_advance(pf, t, t+p['duration_s'])
        pf.command({'t': t, 'kind': 'hold'})
        if i < len(legs)-1:
            t = rf_advance(pf, t, t+rf.STOP_HOLD_S)
    return pf.estimate()


def rf_advance(pf, t, until):
    while t < until-1e-9:
        t = min(until, round(t+rf.PREDICT_STEP_S, 9))
        pf.predict_to(t)
        pf.estimate()
    return t


def test_predict_restores_the_live_pf_bit_for_bit_and_forecasts_the_same_model(live_pf):
    pf, mp = live_pf
    before, state = _digest(pf), pf.pf_consistency['state']
    out = rf.predict(pf, plan(ROUTE), 'r1', [0, 1], mp, door=rf.door_of(plan(ROUTE)))
    assert _digest(pf) == before and pf.pf_consistency['state'] is state     # closure state kept in place
    assert out['steps'] > 0 and out['end_std_xy_m'] > .03
    live = _issue_like_predict(pf, [0, 1], mp)
    assert live['std_xy_m'] == pytest.approx(out['end_std_xy_m'], abs=1e-6)  # identical draws, identical model


def test_predict_with_the_rest_of_the_stop_forecasts_the_same_model(live_pf):
    # v4: the 10 s window + HIGH stop minimum + rendezvous of the CURRENT stop are predicted before the first leg
    pf, mp = live_pf
    lead = rf.lead_hold_s(float(pf.t), float(pf.t))
    assert lead == pytest.approx(rf.DECIDE_WINDOW_S+rf.STOP_TAIL_S) == pytest.approx(11.7)
    before = _digest(pf)
    without = rf.predict(pf, plan(ROUTE), 'r1', [0], mp)
    out = rf.predict(pf, plan(ROUTE), 'r1', [0], mp, lead_hold_s=lead)
    assert _digest(pf) == before
    assert out['steps'] == without['steps']+round(lead/rf.PREDICT_STEP_S)
    live = _issue_like_predict(pf, [0], mp, lead=lead)
    assert live['std_xy_m'] == pytest.approx(out['end_std_xy_m'], abs=1e-6)


def test_mutation_without_restore_is_detected(live_pf, monkeypatch):
    pf, mp = live_pf
    before = _digest(pf)
    monkeypatch.setattr(rf, '_restore', lambda pf, snap: None)
    rf.predict(pf, plan(ROUTE), 'r1', [0], mp)
    assert _digest(pf) != before


def test_leg_plan_matches_the_v3_door_schedule(live_pf):
    from harness.zone_final_pair_skill import V3Controller
    pf, mp = live_pf
    for k in range(len(ROUTE)-1):
        for rid in ('r1', 'r2'):
            ns = SimpleNamespace(v3_plan=plan(ROUTE), v3_params={'motion_loaded': mp}, seg=k, rid=rid,
                                 grasp_estimate=[0., ROUTE[k][1], 0. if rid == 'r1' else math.pi],
                                 door_plan={'headings_rad': {'r1': 0., 'r2': math.pi}}, claims={},
                                 port=SimpleNamespace(own=SimpleNamespace(pose=SimpleNamespace(
                                     provider=SimpleNamespace(loc=SimpleNamespace(_pf=SimpleNamespace()))))))
            sched = V3Controller.door_schedule(ns, 10.)
            p = rf.leg_plan(plan(ROUTE), k, rid, mp)
            (t0, t1, cmd) = sched[-1]
            assert t1-t0 == pytest.approx(p['duration_s'], abs=1e-9)
            assert [cmd['forward'], cmd['left'], cmd['turn']] == pytest.approx(p['u'], abs=1e-12)


def test_record_names_the_unchanged_status_and_thresholds():
    r = rf.record()
    assert r['new_status_value'] is False and r['request_status'] == 'uncertain'
    assert r['gate_xy_m'] == .07 and r['dr_receipt_budget_xy_m'] == dc.BUDGET_XY_M == rf.budget(2000)[0]  # one derivation
    assert r['dr_receipt_budget_yaw_rad'] == dc.BUDGET_YAW_RAD == rf.budget(2000)[1]
    assert set(r['codes']) == {rf.DISAGREE, rf.PARTNER_UNSEEN, rf.INFEASIBLE}
    assert r['look_move']['executed'] is False and r['look_move']['reserved_code'] == rf.LOOK_MOVE_FAIL


def test_budget_derivation_uses_the_registered_particle_count(live_pf):
    pf, _ = live_pf
    assert pf.n == dc.N_PARTICLES == 2000
    assert rf.budget is dc.budget and rf.mc_margin is dc.mc_margin


def test_look_move_plan_on_the_registered_route(tmp_path, monkeypatch):
    """Offline model (static map, hover posture, sigma 70.7 mm / 1.7 deg): pins why the move is not executed."""
    from harness.zone_final_pair_guards import PairGeometry
    from harness.zone_own_guards import OwnPose
    from harness.zone_pair_align import ranked_look_pans
    from tests import highpose_relook_synthetic as syn
    from scripts.study_owncam_pair_beam import ROLES
    p = {**plan(ROUTE), 'beam_geometry': BEAM_GEOMETRY}
    runtime = syn.build(syn.admitted_copy(tmp_path, monkeypatch), seed=0)
    try:
        hover = {1: legacy.OPEN, 3: 807, 4: 1897, 5: 2187, 6: 1500}
        out = {}
        for j in (1, 4, 5, 6):
            for rid, dx, yaw in (('r1', -.4732, 0.), ('r2', .4732, math.pi)):
                actor, src = runtime.actors[rid], runtime.providers[rid].provider
                src.recovery_v6 = True
                guard = PairGeometry(actor.guard, BEAM_GEOMETRY, ROLES[rid])
                pose0 = OwnPose(ROUTE[j][0]+dx, ROUTE[j][1], yaw, math.hypot(.05, .05), math.radians(1.7))

                def rank(q, _a=actor, _g=guard, _s=src):
                    rep = SimpleNamespace(initialized=True, x_m=q.x, y_m=q.y, yaw_rad=q.yaw, std_xy_m=q.std_xy,
                                          std_yaw_rad=q.std_yaw, t_est=0., last_fix_t=None, fix_age_s=99.)
                    return ranked_look_pans(_a.map, rep, hover, _g, _s, recovery_v6=True)
                out[(j, rid)] = rf.look_move_plan(p, j, rid, pose0, hover, guard, src.get_motion_params(), rank=rank)
    finally:
        runtime.close()
    assert out[(4, 'r1')]['ok'] and out[(4, 'r1')]['distance_m'] == pytest.approx(.65)
    assert out[(4, 'r1')]['start_clearance_m'] < 0 <= out[(4, 'r1')]['d_clear_m']       # start relief floor
    assert out[(4, 'r1')]['back_u'] == pytest.approx([-v for v in out[(4, 'r1')]['out_u']])  # returns on the same command
    for j in (5, 6):
        assert out[(j, 'r1')] == {**out[(j, 'r1')], 'ok': False, 'reason': 'no_view_within_clearance'}
    assert out[(1, 'r2')]['reason'] == 'toward_own_grip' and out[(1, 'r1')]['distance_m'] == pytest.approx(.05)


def test_p03_checkpoint_record_counts_a_floor_refix_with_its_own_kind():
    from scripts import run_pair_highpose as runner
    robots = {rid: {'events': [{'event': 'state', 'state': 'carry', 'seg': 0},
                               {'event': 'refix_set_down', 'seg': 0, 'stop': 1, 't': 20.},
                               {'event': 'refix_resumed_high', 'seg': 1, 't': 61.}]} for rid in ('r1', 'r2')}
    out = runner.checkpoint_record({'pair': [{'plan': {'checkpoint_segments': {'before_door': 1}}, 'robots': robots}]},
                                   'before_door')
    assert out['status'] == 'SEQUENCE_OBSERVED_UNQUALIFIED' and out['physical_success'] is None
    assert all(r['high_reobserved'][0]['receipt'] == 'floor_refix' for r in out['robots'].values())


def test_floor_refix_receipt_logs_the_own_estimate_for_the_eval_only_scorer():
    # Review delta2 P2-6: refix_resumed_high (the floor re-fix receipt) carries the own mean, covariance field and report
    # time like the DR receipts. Log only: the stub report has no covariance, so cov is None (scorer: NO_ESTIMATE).
    _, ctls = team(BEFORE_DOOR, over={'r1': True})
    run(ctls, 170.)
    for c in ctls:
        up = ev(c, 'refix_resumed_high')
        assert len(up) == 1
        e = up[0]
        assert (e['x_m'], e['y_m'], e['yaw_rad']) == (1.2, .05, 0.) and e['cov'] is None
        assert e['report_t_est'] == pytest.approx(e['t']) and e['std_xy_m'] == pytest.approx(c.sigma[0])
