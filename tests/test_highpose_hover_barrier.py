"""v98 re-fix hover@k+1 pair barrier on the REAL HoverConfirm hover check (review delta2 P1-1, decision A, 2026-10-05).

The gate is ``SigmaRefix.hover_barrier_gate`` and a failed frame calls ``SigmaRefix.hover_barrier_withdraw`` (review
delta3 P1-1); the hover check, its 2-frame streak and the bounded retries are the unchanged
``HoverConfirm._pregrasp_descend``. The first half uses a fake barrier with a scripted phase. The second half
(``wire`` tests) uses the REAL ``PairStatusChannel``/``PairStatusEndpoint`` and the real ``PairStudent.report``; the
long-wait test also wires the real resting-beam track (recorded frames, review delta3 P2-1). Stand-ins are named in
each test: the pair guard's pose/frame gates and the arm."""
from __future__ import annotations

from types import SimpleNamespace

import pytest

from harness import zone_pair_beam_track as resting
from harness import zone_pair_highpose_blind_close as blind
from harness import zone_pair_highpose_refix as rf
from harness.zone_pair_status import PairStatusChannel, PairStatusEndpoint
from scripts.study_owncam_pair_beam import PairStudent
from tests import test_highpose_blind_close as tb
from tests.test_highpose_blind_close import PATH, Ctl as BlindCtl


class Barrier:
    def __init__(self):
        self.phase, self.calls = 'WAIT', 0

    def authorize(self, now):
        self.calls += 1
        return {'phase': self.phase, 'go_at_s': now}


class Ctl(BlindCtl):
    hover_barrier_gate = rf.SigmaRefix.hover_barrier_gate
    hover_barrier_withdraw = rf.SigmaRefix.hover_barrier_withdraw

    def __init__(self, refix=True, **kw):
        super().__init__(**kw)
        self.seg, self.reports, self.barrier = 2, [], Barrier()
        if refix:
            self.refix_resume = True

    def look(self, now):
        return {'frame_id': round(now*20), 'sha256': 'x', 'sim_time': now}

    def report(self, key, obs, now, ready=True, reason=''):
        self.reports.append((key, obs['frame_id'], ready))

    def sync_for(self, key):
        assert key == rf.HOVER_BARRIER_WIRE
        return self.barrier


def hover(ctl, t0=10.):
    ctl._queue_open_descent(t0)
    return t0+1.5


def tick(ctl, t):
    ctl._pregrasp_descend(round(t, 4), True)


def kinds(ctl):
    return [k for k, _ in ctl.logs]


def test_without_a_refix_the_hover_path_is_unchanged():
    ctl = Ctl(refix=False)
    t = hover(ctl)
    tick(ctl, t), tick(ctl, t+.05)
    assert ctl.blind_phase == 'descend' and len(ctl.arm.queued) == 1+len(PATH) and not ctl.reports


def test_waits_at_the_hover_then_needs_a_fresh_confirmation_after_the_go():
    ctl = Ctl()
    t = hover(ctl)
    for i in range(40):                                     # 2 s of passing frames while the partner is not ready
        tick(ctl, t+.05*i)
    assert ctl.blind_phase == 'hover' and len(ctl.arm.queued) == 1 and ctl.failed is None
    assert ctl.reports and all(k == rf.HOVER_BARRIER_WIRE and ready for k, _, ready in ctl.reports)
    assert len({f for _, f, _ in ctl.reports}) == len(ctl.reports)        # one report per new own frame
    ctl.barrier.phase = 'GO'
    t_go = t+.05*40
    tick(ctl, t_go)
    assert ctl.blind_phase == 'hover' and len(ctl.arm.queued) == 1        # GO alone does not descend
    assert ctl.refix_hover['go_s'] == t_go and ctl.blind_hover_streak == 0
    tick(ctl, t_go)                                         # the GO frame again: not a new confirmation
    assert ctl.blind_phase == 'hover'
    tick(ctl, t_go+.05)
    assert ctl.blind_phase == 'hover'                       # one new passing frame of the required two
    tick(ctl, t_go+.1)
    assert ctl.blind_phase == 'descend' and len(ctl.arm.queued) == 1+len(PATH)
    assert kinds(ctl).count('refix_hover_barrier_wait') == 1 and kinds(ctl).count('refix_hover_reconfirmed') == 1
    go = [v for k, v in ctl.logs if k == 'barrier_go']
    assert go[0]['barrier'] == rf.HOVER_BARRIER and go[0]['wire'] == 'approach@2'


def test_a_failing_reconfirmation_after_the_go_fails_closed_without_descending():
    ctl = Ctl()
    t = hover(ctl)
    tick(ctl, t), tick(ctl, t+.05)
    ctl.barrier.phase = 'GO'
    tick(ctl, t+60.)                                        # long wait, then the GO
    ctl.preclose = False                                    # the hover check no longer passes
    tick(ctl, t+60.05)
    assert ctl.failed is None                               # the unchanged bounded retries, counted from the GO
    tick(ctl, t+60.+blind.HOVER_CONFIRM_MAX_S+.05)
    assert ctl.failed == 'PREGRASP_HOVER_UNCONFIRMED' and len(ctl.arm.queued) == 1
    assert all(ready for _, _, ready in ctl.reports)        # after the GO nothing is withdrawn (bounded retries abort)
    assert 'refix_hover_ready_withdrawn' not in kinds(ctl)


def test_a_failing_hover_check_while_waiting_withdraws_readiness_at_once_and_fails_after_the_bounded_retries():
    ctl = Ctl()
    t = hover(ctl)
    for i in range(20):
        tick(ctl, t+.05*i)
    n = len(ctl.reports)
    assert n and all(ready for _, _, ready in ctl.reports)
    last_pass = t+.05*19
    ctl.preclose = False
    tick(ctl, last_pass+.5)
    assert ctl.failed is None
    # review delta3 P1-1: the failing frame reports ready=False for the same barrier, on the failing frame itself
    assert ctl.reports[n:] == [(rf.HOVER_BARRIER_WIRE, round((last_pass+.5)*20), False)]
    assert ctl.refix_hover['ready'] is False and ctl.refix_hover['withdrawn'] == 1
    withdrawn = [v for k, v in ctl.logs if k == 'refix_hover_ready_withdrawn']
    assert len(withdrawn) == 1 and withdrawn[0]['code'] == 'PREGRASP_HOVER_UNCONFIRMED' and withdrawn[0]['count'] == 1
    tick(ctl, last_pass+.55)                                # further failing frames: no repeated wire row
    assert len(ctl.reports) == n+1 and ctl.failed is None
    ctl.preclose = True                                     # passing again: 2 new frames, then ready is reported again
    tick(ctl, last_pass+.6), tick(ctl, last_pass+.65)
    assert ctl.reports[-1][2] is True and len(ctl.reports) == n+2 and ctl.refix_hover['ready'] is True
    ctl.preclose = False                                    # and a later failing run withdraws once more
    tick(ctl, last_pass+.7)
    assert ctl.reports[-1][2] is False and ctl.refix_hover['withdrawn'] == 2
    tick(ctl, last_pass+.65+blind.HOVER_CONFIRM_MAX_S+.05)
    assert ctl.failed == 'PREGRASP_HOVER_UNCONFIRMED' and len(ctl.arm.queued) == 1


def test_a_failing_frame_before_any_ready_report_or_outside_a_refix_sends_nothing():
    ctl = Ctl()
    t = hover(ctl)
    ctl.preclose = False
    tick(ctl, t), tick(ctl, t+.05)
    assert ctl.reports == [] and 'refix_hover_ready_withdrawn' not in kinds(ctl)
    plain = Ctl(refix=False)                                # not a re-fix re-grasp: the unchanged path, no wire at all
    t = hover(plain)
    tick(plain, t)
    plain.preclose = False
    tick(plain, t+.05)
    assert plain.reports == [] and 'refix_hover_ready_withdrawn' not in kinds(plain) and plain.failed is None


def test_the_derived_limit_ends_the_wait_with_its_own_code():
    ctl = Ctl()
    t = hover(ctl)
    tick(ctl, t), tick(ctl, t+.05)
    start = ctl.refix_hover['started_s']
    tick(ctl, start+rf.hover_barrier_limit_s())
    assert ctl.failed is None
    tick(ctl, start+rf.hover_barrier_limit_s()+.05)
    assert ctl.failed == rf.HOVER_TIMEOUT and len(ctl.arm.queued) == 1
    assert 'refix_hover_barrier_timeout' in kinds(ctl)


def test_a_barrier_abort_stops_with_its_own_code():
    ctl = Ctl()
    t = hover(ctl)
    tick(ctl, t)
    ctl.barrier.phase = 'ABORT'
    tick(ctl, t+.05)
    assert ctl.failed == rf.HOVER_ABORT and len(ctl.arm.queued) == 1


def test_limit_terms_record_and_cause_labels():
    terms = rf.hover_barrier_limit_terms()
    assert terms == {'align_state_limit_s': 60., 'post_look_windows_s': 20., 'look_budget_s': 40., 'hover_move_s': 1.,
                     'hover_settle_s': .3, 'hover_confirm_max_s': 1., 'descent_s': pytest.approx(1.14),
                     'grid_slack_s': .5}
    assert rf.hover_barrier_limit_s() == pytest.approx(123.94)
    r = rf.record()['hover_barrier']
    assert r['limit_s'] == rf.hover_barrier_limit_s() and r['codes'] == [rf.HOVER_TIMEOUT, rf.HOVER_ABORT]
    assert set(r['events']) >= set(rf.HOVER_EVENTS) and 'refix_hover_ready_withdrawn' in r['events']
    assert '조정자 승인' in r['decision']
    from harness.zone_pair_status import STATES
    assert {f'approach_ready_{k}' for k in range(1, 8)} <= STATES      # existing wire values, protocol unchanged
    from scripts import run_pair_highpose as runner
    for code in (rf.HOVER_TIMEOUT, rf.HOVER_ABORT):
        assert runner.failure_cause(code)['code'] == 'PAIR_BARRIER_WAIT'


def test_the_record_lists_the_partner_budget_and_the_own_reference_age_separately():
    r = rf.record()['hover_barrier']['limits_two_different_things']
    assert r['partner_budget_sum_s']['value_s'] == rf.hover_barrier_limit_s() == pytest.approx(123.94)
    assert r['own_reference_age_s']['value_s'] == resting.MAX_AGE_S == blind.limits()['anchor_max_age_s'] == 30.
    assert 'HOVER_TIMEOUT' in r['partner_budget_sum_s']['means'] and 'live partner' in r['partner_budget_sum_s']['means']
    assert 'PREGRASP_HOVER_UNCONFIRMED' in r['own_reference_age_s']['means']
    assert 'does not renew' in r['own_reference_age_s']['means'] and 'not lengthened' in r['effective_wait_s']
    assert rf.record()['hover_barrier']['limit_terms'] == rf.hover_barrier_limit_terms()      # the sum is unchanged
    import json
    json.dumps(rf.record()['hover_barrier'])


# ---- wire: the REAL status channel (review delta3 P1-1) --------------------------------------------------------
# Real: PairStatusChannel, PairStatusEndpoint, PairStudent.report (-> _StatusBarrier.report/authorize), the real
# HoverConfirm._pregrasp_descend and SigmaRefix gate/withdraw. Stand-ins: the hover check result (``preclose``), the arm
# queue, the video frames (fresh ids/times, a hex digest).

def grid(t0, t1):
    n = round((t1-t0)/.05)
    return [round(t0+i*.05, 4) for i in range(n)]


class WireCtl(Ctl):
    def __init__(self, rid, bus):
        super().__init__()
        self.rid, self.ep, self.seq = rid, PairStatusEndpoint(bus, rid), 0

    def look(self, now):
        return {'frame_id': round(now*20), 'sim_time': now, 'sha256': 'a'*64}

    report = PairStudent.report

    def sync_for(self, key):
        return self.ep.sync_for(f'{key}@{self.seg}')

    def fail(self, reason, now):
        super().fail(reason, now)
        self.ep.fail(reason, now)

    def step(self, now):
        if self.failed:
            return
        self.ep.tick('aligning', now)                       # the own phase of this stretch (zone_pair_status)
        if any(v['state'] == 'abort' for v in self.ep.channel.partner_view(self.rid, now).values()):
            return self.fail('PARTNER_ABORT', now)
        if self.blind_phase == 'hover':
            self._pregrasp_descend(now, True)


def team(order):
    bus = PairStatusChannel('hover-wire')
    ctls = {rid: WireCtl(rid, bus) for rid in order}
    for ctl in ctls.values():
        hover(ctl)
    return bus, ctls


def drive(ctls, times, failing=None, fail_from=None, fail_until=None):
    """Step every robot on each 0.05 s tick in dict order; ``failing`` fails its own hover check in [from, until)."""
    for t in times:
        for rid, ctl in ctls.items():
            ctl.preclose = not (rid == failing and fail_from-1e-9 <= t < fail_until-1e-9)
            ctl.step(t)


def wire_states(bus, rid):
    return [(m['sent_at_s'], m['state']) for m in bus.log if m['robot_id'] == rid]


@pytest.mark.parametrize('order', [('r1', 'r2'), ('r2', 'r1')])
@pytest.mark.parametrize('failing', ['r1', 'r2'])
def test_wire_a_failed_frame_cancels_the_readiness_so_the_partner_gets_no_go_and_both_go_together_later(order, failing):
    other = 'r2' if failing == 'r1' else 'r1'
    bus, ctls = team(order)
    # both are hover ready at 11.55 (the old one-sided GO was at 11.80, its descent at 11.90); one robot fails from 11.60
    drive(ctls, grid(11.5, 12.0), failing, 11.6, 12.0)
    assert {rid: c.blind_phase for rid, c in ctls.items()} == {'r1': 'hover', 'r2': 'hover'}
    assert all(c.refix_hover['go_s'] is None and len(c.arm.queued) == 1 and c.failed is None for c in ctls.values())
    assert not any('_go_' in m['state'] for m in bus.log)             # nobody, the partner included, got the GO
    assert (11.6, 'not_ready') in wire_states(bus, failing)           # the cancellation is on the wire at the failing frame
    assert ctls[failing].refix_hover['withdrawn'] == 1 and ctls[other].refix_hover['withdrawn'] == 0
    withdrawn = [v for k, v in ctls[failing].logs if k == 'refix_hover_ready_withdrawn']
    assert len(withdrawn) == 1 and withdrawn[0]['frame_id'] == round(11.6*20)
    assert [v['accepted'] for k, v in ctls[failing].logs if k == 'barrier_report' and not v['ready']] == [True]
    # the frame passes again from 12.0: after 2 new frames the readiness is reported again and both GO together
    drive(ctls, grid(12.0, 13.0), failing, 12.0, 12.0)
    go = {rid: c.refix_hover['go_s'] for rid, c in ctls.items()}
    assert go[failing] is not None and go[failing] == go[other] == pytest.approx(12.3)
    assert all(c.blind_phase == 'descend' and len(c.arm.queued) == 1+len(PATH) and c.failed is None
               for c in ctls.values())
    assert all(kinds(c).count('refix_hover_reconfirmed') == 1 for c in ctls.values())
    assert not any(m['state'] == 'abort' for m in bus.log) and not bus.rejected


def test_wire_the_old_behaviour_without_the_withdrawal_gave_a_one_sided_go(monkeypatch):
    """The review delta3 P1-1 counterexample, kept as a guard that this test setup detects it: with the withdrawal
    switched off (the pre-fix behaviour) only the partner gets the GO at 11.80 and descends at 11.90."""
    monkeypatch.setattr(WireCtl, 'hover_barrier_withdraw', lambda self, now, obs, code: None)
    bus, ctls = team(('r1', 'r2'))
    drive(ctls, grid(11.5, 12.0), 'r1', 11.6, 12.0)
    assert ctls['r1'].refix_hover['go_s'] is None and ctls['r2'].refix_hover['go_s'] == pytest.approx(11.8)
    assert ctls['r2'].blind_phase == 'descend' and ctls['r1'].blind_phase == 'hover'


def test_wire_a_failure_exactly_at_the_commit_tick_is_the_remaining_exposure_and_ends_in_an_abort():
    """Residual, not a fix claim: the GO is decided on the control grid (zone_pair_status, frozen). A failing frame
    that lands only on the GO tick, with the partner ticked first, finds the GO already consumed by the partner: the
    withdrawal is too late. Measured: the partner descends alone for about 0.1 s of its own confirmation plus the
    failing robot's bounded retries, then the abort ends both (no silent close)."""
    bus, ctls = team(('r2', 'r1'))                                      # partner (r2) ticks first at every instant
    drive(ctls, grid(11.5, 11.8), 'r1', 11.8, 11.85)                    # ready at 11.55, GO tick 11.8 comes next
    drive(ctls, grid(11.8, 11.85), 'r1', 11.8, 11.85)
    assert ctls['r2'].refix_hover['go_s'] == pytest.approx(11.8)       # the partner consumed the GO first
    assert ctls['r1'].refix_hover['go_s'] is None and (11.8, 'not_ready') in wire_states(bus, 'r1')
    drive(ctls, grid(11.85, 13.2), 'r1', 11.85, 99.)                    # r1's own frame keeps failing
    assert ctls['r2'].blind_phase == 'descend'                         # the one-sided descent happened ...
    assert ctls['r1'].failed == 'PREGRASP_HOVER_UNCONFIRMED'           # ... and is ended by the failing robot's abort
    assert ctls['r2'].failed == 'PARTNER_ABORT'
    abort_at = {m['robot_id']: m['sent_at_s'] for m in bus.log if m['state'] == 'abort'}
    one_sided_s = abort_at['r1']-ctls['r2'].refix_hover['descend_s']
    assert 0. < one_sided_s <= blind.HOVER_CONFIRM_MAX_S+.05 and abort_at['r2'] > abort_at['r1']   # measured 0.85 s
    assert not any(m['state'].startswith('close_') for m in bus.log)   # nobody reached the close barrier


def test_wire_a_one_frame_failure_on_the_commit_tick_leaves_the_partner_descended_and_waiting():
    """Residual, second branch (measured, not fixed): the failing frame recovers right after the partner consumed the
    GO. The frozen ``authorize`` needs both robots' latest wire state to be ``approach_ready``; the partner's is already
    past it, so the recovered robot never gets a GO and stays at the hover while the partner has descended. This stub has
    no close barrier: in the run the partner then waits at ``close@k+1`` for CLOSE_WAIT_S (20 s, runtime) and stops with
    BARRIER_CLOSE_TIMEOUT -> abort; nothing closes. Fixing it needs a change in zone_pair_status (frozen)."""
    bus, ctls = team(('r2', 'r1'))
    drive(ctls, grid(11.5, 11.85), 'r1', 11.8, 11.85)                   # one failing frame, on the GO tick
    drive(ctls, grid(11.85, 40.), 'r1', 99., 99.)                       # r1 passes again from 11.85 on
    assert ctls['r2'].refix_hover['go_s'] == pytest.approx(11.8) and ctls['r2'].blind_phase == 'descend'
    assert ctls['r1'].refix_hover['go_s'] is None and ctls['r1'].blind_phase == 'hover' and ctls['r1'].failed is None
    assert ctls['r1'].refix_hover['ready'] is True                      # it did report ready again ...
    assert [m['state'] for m in bus.log if '_go_' in m['state']] == ['approach_go_2']       # ... but no second GO
    assert not any(m['state'].startswith('close_') or m['state'] == 'abort' for m in bus.log)


# ---- long wait with the real resting-beam track (review delta3 P2-1) -------------------------------------------

class TrackCtl(WireCtl):
    """r1 on the REAL v98 resting-beam track (recorded standoff + hover frames of the DEV probe, issued commands fed).
    Stand-ins: the pair guard's pose/frame gates (``preclose_check`` is the guard's ``beam_track.estimate`` step)."""

    def __init__(self, rid, bus, track, frame, servo):
        super().__init__(rid, bus)
        self.blind_track, self.frame, self.frame_servo = track, frame, {**servo, 1: 2000}
        self.port = SimpleNamespace(own=SimpleNamespace(servo=dict(self.frame_servo)))
        self.preclose = None

    def look(self, now):
        return {**self.frame, 'sim_time': now, 'frame_id': round(now*1000)}

    def preclose_check(self, now, obs):
        return self.blind_track.estimate(now, obs, dict(self.frame_servo), self.seg) is not None


def test_a_hover_wait_longer_than_the_30_s_reference_age_fails_closed_with_the_reason_recorded():
    seg = 2
    track = tb.new_track()
    standoff, standoff_servo = tb.obs_of('standoff')
    assert track.observe_standoff(standoff, standoff_servo, seg)
    frame, frame_servo = tb.obs_of('hover')
    tb.feed(track, standoff_servo, frame['sim_time'])
    t0 = track.beam['anchor_time_s']
    bus = PairStatusChannel('hover-long-wait')
    ctl, partner = TrackCtl('r1', bus, track, frame, frame_servo), PairStatusEndpoint(bus, 'r2')
    ctl.seg = seg
    hover(ctl)

    def at(age):
        t = round(t0+age, 4)
        partner.tick('aligning', t)                         # a live partner that is still busy, never ready
        ctl.step(t)
        return t
    # at the hover from 1.1 s after the anchor; the partner stays busy for a long time (the hover wait goes on)
    for age in (1.1, 1.15, 6., 6.05, 12., 12.05, 18., 18.05, 24., 24.05, 29.8, 29.85, 29.9):
        at(age)
    assert ctl.failed is None and ctl.blind_phase == 'hover' and ctl.refix_hover['go_s'] is None
    assert ctl.refix_hover['ready'] is True and ctl.refix_hover['reports'] >= 4
    checks = [v for k, v in ctl.logs if k == 'blind_hover_check']
    assert checks[-1]['ok'] and checks[-1]['reference']['expired'] is False
    assert checks[-1]['reference']['age_s'] == pytest.approx(29.9) and checks[-1]['reference']['max_age_s'] == 30.
    # a hover partial image never renews the reference: the age keeps counting although the beam is still seen
    assert track.beam['anchor_time_s'] == t0
    waited = checks[-1]['reference']['age_s']-1.1
    assert waited < rf.hover_barrier_limit_s()               # the partner budget (123.94 s) is nowhere near used up
    at(30.1)                                                  # the reference is older than 30 s: the track refuses
    assert ctl.failed is None and ctl.refix_hover['ready'] is False and ctl.refix_hover['withdrawn'] == 1
    refused = [v for k, v in ctl.logs if k == 'blind_hover_check'][-1]
    assert refused['ok'] is False and refused['code'] == 'PREGRASP_HOVER_UNCONFIRMED'     # recorded, not silent
    assert refused['reference']['expired'] is True and refused['reference']['age_s'] == pytest.approx(30.1)
    assert (round(t0+30.1, 4), 'not_ready') in wire_states(bus, 'r1')                       # readiness cancelled at once
    at(30.15)
    assert ctl.failed is None                                                               # bounded retries first
    at(29.9+blind.HOVER_CONFIRM_MAX_S+.05)
    assert ctl.failed == 'PREGRASP_HOVER_UNCONFIRMED' and len(ctl.arm.queued) == 1
    kinds_seen = kinds(ctl)
    assert 'refix_hover_barrier_timeout' not in kinds_seen and ctl.failed != rf.HOVER_TIMEOUT
    assert not any('_go_' in m['state'] for m in bus.log) and bus.latest['r1']['state'] == 'abort'
    assert bus.partner_view('r2', round(t0+31.0, 4))['r1']['state'] == 'abort'
    from scripts import run_pair_highpose as runner
    assert runner.failure_cause(ctl.failed)['code'] == 'HOVER_NOT_CONFIRMED'              # evaluation-side label
