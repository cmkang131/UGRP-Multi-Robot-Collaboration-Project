"""v98 re-fix hover@k+1 pair barrier on the REAL HoverConfirm hover check (review delta2 P1-1, decision A, 2026-10-05).

The gate is ``SigmaRefix.hover_barrier_gate``; the hover check, its 2-frame streak and the bounded retries are the
unchanged ``HoverConfirm._pregrasp_descend``. The barrier object is a fake with a scripted phase (the pair-level
behaviour with the real status channel is in tests/test_highpose_refix*.py)."""
from __future__ import annotations

import pytest

from harness import zone_pair_highpose_blind_close as blind
from harness import zone_pair_highpose_refix as rf
from tests.test_highpose_blind_close import PATH, Ctl as BlindCtl


class Barrier:
    def __init__(self):
        self.phase, self.calls = 'WAIT', 0

    def authorize(self, now):
        self.calls += 1
        return {'phase': self.phase, 'go_at_s': now}


class Ctl(BlindCtl):
    hover_barrier_gate = rf.SigmaRefix.hover_barrier_gate

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


def test_a_failing_hover_check_while_waiting_withdraws_readiness_and_fails_after_the_bounded_retries():
    ctl = Ctl()
    t = hover(ctl)
    for i in range(20):
        tick(ctl, t+.05*i)
    n = len(ctl.reports)
    last_pass = t+.05*19
    ctl.preclose = False
    tick(ctl, last_pass+.5)
    assert ctl.failed is None and len(ctl.reports) == n     # no ready report from a failing frame
    tick(ctl, last_pass+blind.HOVER_CONFIRM_MAX_S+.05)
    assert ctl.failed == 'PREGRASP_HOVER_UNCONFIRMED' and len(ctl.arm.queued) == 1


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
    assert '조정자 승인' in r['decision']
    from harness.zone_pair_status import STATES
    assert {f'approach_ready_{k}' for k in range(1, 8)} <= STATES      # existing wire values, protocol unchanged
    from scripts import run_pair_highpose as runner
    for code in (rf.HOVER_TIMEOUT, rf.HOVER_ABORT):
        assert runner.failure_cause(code)['code'] == 'PAIR_BARRIER_WAIT'
