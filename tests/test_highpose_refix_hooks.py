"""#371 LLM decision hooks on the v98 sigma re-fix (zone_pair_highpose_refix.SigmaRefix), simulator-free.

Same tier-1 harness as tests/test_highpose_refix.py (real HighController + SigmaRefix + the fixed-enum status channel
on recorded own frames, M2Stub for the v3 release/re-grasp). ``LookStub`` adds a TEST STUB of the align re-look
return so the post-look window is exercised; the real re-look is covered by its own tests.
Invariant checked here: with no command the outcome is the sigma rule (rule_default), and a command can only make the
pair more conservative (set_down, look_again); continue/regrasp are refused when the rule says no.
v4 (coordinator 2026-10-05): 10 s decision and post-look windows in every condition, 'wait' and 'give_up' removed,
a fix-refresh look after the post-look window, re-fix look over
the dock look's eight directions (``DockProbe`` runs the REAL PairAlignRelook code with stubbed I/O).
"""
from __future__ import annotations

import math

import pytest

from harness import zone_pair_highpose_refix as rf
from harness.zone_pair_highpose_runtime import HighController
from scripts import study_owncam_pair_beam as legacy
from tests import test_highpose_refix as base
from tests.test_highpose_refix import BEFORE_DOOR, M2Stub, ev, opens, published, run, stub_states, team  # noqa: F401
from tests.test_highpose_transit import short_route  # noqa: F401  (autouse fixture)
from tests import test_highpose_transit as tr

C = rf.confirm_window_s()           # echo after a re-fix decision (1.2 s)
D = rf.decide_window_s()            # carry-stop decision window (10 s)
P = rf.post_look_window_s()         # post-look window (10 s)


def hooks(c, name=None):
    rows = c.__dict__.get('refix_hook_events', [])
    return [r for r in rows if name is None or r['event'] == name]


def on_tick(c, fn):
    """Call fn(c, now) before every own tick (the LLM layer submitting between ticks)."""
    orig = c.tick

    def tick(now):
        fn(c, now)
        return orig(now)
    c.tick = tick


def at_stop(c):
    return c.state == rf.DECIDE_STATE


def submit_once(choice, *, when=lambda c, now: at_stop(c), command='carry_decision'):
    out = []

    def fn(c, now):
        if not out and when(c, now):
            out.append(getattr(c, command)(choice, now))
    return fn, out


def decision(c):
    return c.__dict__.get('refix_hook_decisions', [])


# ---------------------------------------------------------------- rule default and events
def test_without_commands_the_rule_decides_and_every_event_is_emitted_in_order():
    _, ctls = team(BEFORE_DOOR, over={'r1': True})
    run(ctls, 140.)
    for c in ctls:
        assert c.failure is None and c.state == 'released'
        names = [r['event'] for r in hooks(c)]
        assert names == ['carry_leg_started', 'carry_stop_reached', 'setdown_started', 'setdown_completed',
                         'regrasp_result', 'carry_resumed', 'carry_leg_started'], names
        stop = hooks(c, 'carry_stop_reached')[0]
        assert stop['stop'] == 1 and stop['receipt'] == 'within' and stop['sigma_band'] == 'fix'
        assert stop['latch_until_s'] == pytest.approx(stop['decide_at_s']-rf.latch_margin_s())
        leg = hooks(c, 'carry_leg_started')[0]
        assert leg['n_segs'] == 2 and leg['planned_leg_s'] > 0
        assert hooks(c, 'regrasp_result')[0]['ok'] is True
        (rec,) = decision(c)
        assert rec['decided_by'] == 'rule_default' and rec['outcome'] == 'set_down' and not rec['commands']
    r1, r2 = ctls
    assert hooks(r1, 'carry_stop_reached')[0]['over_budget'] is True
    assert hooks(r1, 'carry_stop_reached')[0]['options'] == ['set_down']                # continue not offered
    assert hooks(r2, 'carry_stop_reached')[0]['options'] == list(rf.CARRY_CHOICES)
    assert decision(r1)[0]['rule_would_do'] == 'set_down' and decision(r1)[0]['refix_from'] == ['own_rule', 'partner']
    assert decision(r2)[0]['rule_would_do'] == 'continue' and decision(r2)[0]['refix_from'] == ['partner']


def test_continue_is_refused_when_the_sigma_rule_asks_for_a_set_down():
    _, ctls = team(BEFORE_DOOR, over={'r1': True})
    fn, got = submit_once('continue')
    on_tick(ctls[0], fn)
    run(ctls, 140.)
    assert got[0]['accepted'] is False and got[0]['own_status'] == rf.OVER_BUDGET
    for c in ctls:
        assert c.failure is None and c.refix_count == 1                      # the rule outcome stands
    assert decision(ctls[0])[0]['decided_by'] == 'rule_default'


@pytest.mark.parametrize('who', [0, 1])
def test_llm_set_down_where_the_rule_continues_sets_both_robots_down(who):
    bus, ctls = team(BEFORE_DOOR)
    fn, got = submit_once('set_down')
    on_tick(ctls[who], fn)
    run(ctls, 140.)
    me, other = ctls[who], ctls[1-who]
    assert got[0]['accepted'] is True and got[0]['own_status'] == 'LATCHED'
    for c in ctls:
        assert c.failure is None and c.state == 'released' and c.refix_count == 1, (c.rid, c.failure)
        assert len(opens(c)) == 2 and len(ev(c, 'refix_released')) == 1        # both look (v6-1)
    assert decision(me)[0]['decided_by'] == 'llm' and decision(me)[0]['rule_would_do'] == 'continue'
    assert decision(me)[0]['refix_from'] == ['own_llm', 'partner']
    assert decision(other)[0]['decided_by'] == 'rule_default' and decision(other)[0]['refix_from'] == ['partner']
    assert published(bus, other.rid, 'uncertain')                            # the partner echoes


@pytest.mark.parametrize('who', [0, 1])
def test_set_down_at_the_latch_cutoff_still_reaches_the_partner_in_either_tick_order(who):
    _, ctls = team(BEFORE_DOOR)

    def last_accepted(c, now):
        # the last tick at or before the cutoff
        return at_stop(c) and now+.1 > c.refix_decision['hook']['cutoff']+1e-8
    fn, got = submit_once('set_down', when=last_accepted)
    on_tick(ctls[who], fn)
    run(ctls, 140.)
    assert got[0]['accepted'] is True
    for c in ctls:
        assert c.failure is None and c.refix_count == 1, (c.rid, c.failure)


def test_set_down_after_the_cutoff_is_refused_and_the_rule_applies():
    _, ctls = team(BEFORE_DOOR)

    def late(c, now):
        return at_stop(c) and now > c.refix_decision['hook']['cutoff']+1e-8 and not c.refix_decision['decided']
    fn, got = submit_once('set_down', when=late)
    on_tick(ctls[0], fn)
    run(ctls, 90.)
    assert got[0]['own_status'] == rf.DEADLINE_PASSED
    for c in ctls:
        assert c.failure is None and getattr(c, 'refix_count', 0) == 0 and len(opens(c)) == 1


def test_one_shot_latch_and_closed_rejections():
    _, ctls = team(BEFORE_DOOR)
    r1 = ctls[0]
    got = []

    def fn(c, now):
        if c.state == 'carry' and not got:
            got.append(c.carry_decision('set_down', now))                     # not at a stop
            got.append(c.post_look_decision('regrasp', now))                  # no look window
        if at_stop(c) and len(got) == 2:
            got.append(c.carry_decision('stop_now', now))                     # not in the closed choice set
            got.append(c.carry_decision('wait', now))                         # removed in v4 (decision v4-2)
            got.append(c.carry_decision('set_down', now))
            got.append(c.carry_decision('continue', now))                     # a latch is pending
    on_tick(r1, fn)
    run(ctls, 140.)
    assert [g['own_status'] for g in got] == [rf.NOT_AT_STOP, rf.NOT_AFTER_LOOK, rf.UNKNOWN_CHOICE,
                                               rf.UNKNOWN_CHOICE, 'LATCHED', rf.ALREADY_LATCHED]
    assert set(g['own_status'] for g in r1.refix_hook_commands) <= set(rf.REJECT_REASONS) | {'LATCHED'}


def test_wait_is_not_in_the_vocabulary_and_the_rule_decides():
    _, ctls = team(BEFORE_DOOR, over={'r2': True})
    fn, got = submit_once('wait')
    on_tick(ctls[0], fn)
    run(ctls, 140.)
    assert got[0]['accepted'] is False and got[0]['own_status'] == rf.UNKNOWN_CHOICE
    assert 'wait' not in rf.CARRY_CHOICES and 'WAIT_USED' not in rf.REJECT_REASONS
    for c in ctls:
        assert c.failure is None and c.refix_count == 1
        assert 'waited' not in decision(c)[0] and 'wait_used' not in c.refix_decision['hook']
    assert decision(ctls[0])[0]['outcome'] == 'set_down' and decision(ctls[0])[0]['refix_from'] == ['partner']


@pytest.mark.parametrize('over', [None, {'r1': True}])
def test_every_stop_holds_the_same_10_s_window_and_the_rule_is_recorded_at_entry(over):
    # decision v4-1: rule-only, continue or set-down, both robots execute at t_end + D; the rule decided at entry
    _, ctls = team(BEFORE_DOOR, over=over)
    run(ctls, 140.)
    for c in ctls:
        assert c.failure is None and c.state == 'released', (c.rid, c.failure)
        d = c.refix_decision
        (rec,) = decision(c)
        assert rec['decided_by'] == 'rule_default' and rec['executed_s'] == pytest.approx(d['t_end']+D, abs=.11)
        assert rec['rule_decided_s'] == rec['decided_s'] == d['hook']['entered_s'] < d['t_end']+.2
        assert ev(c, 'refix_decision')[0]['t'] == pytest.approx(d['t_end']+D, abs=.11)
        assert c.calls[0]['lead_hold_s'] == pytest.approx(rf.lead_hold_s(d['t_end'], d['hook']['entered_s']))
        assert c.calls[0]['lead_hold_s'] == pytest.approx(D+rf.STOP_TAIL_S, abs=.11)
    assert decision(ctls[0])[0]['executed_s'] == decision(ctls[1])[0]['executed_s']


def test_an_llm_set_down_is_recorded_when_applied_and_executed_at_the_window_end():
    _, ctls = team(BEFORE_DOOR)
    fn, got = submit_once('set_down')
    on_tick(ctls[1], fn)
    run(ctls, 140.)
    rec = decision(ctls[1])[0]
    t_end = ctls[1].refix_decision['t_end']
    assert rec['decided_by'] == 'llm' and rec['decided_s'] == rec['commands'][0]['applied_s']
    assert rec['decided_s'] < t_end+1. and rec['executed_s'] == pytest.approx(t_end+D, abs=.11)
    for c in ctls:
        assert c.failure is None and c.refix_count == 1


# ---------------------------------------------------------------- post-look window
STUB_LOOK_S = 8.6                     # one full dock look (note V6: eight pans measured 8.4 s)
STUB_REFRESH_LOOK_S = .8+.6+.6+.3     # = zone_pair_highpose_timing.ALIGN_ENTRY_RELOOK_S (one direction)


class LookStub(M2Stub):
    """TEST STUB: cp_open -> an instant own look with a fresh fix -> ``align_relook_return`` -> align -> close@k+1.
    The fix checks are age-based like the real ``_align_fix_checks`` (fix gap < MAX_FIX_GAP_S = 6 s)."""

    def _cp_open(self, now, arm_idle):
        if not arm_idle:
            return
        self.seg += 1
        self.grip_epoch += 1
        self.high_raising = self.high_ready = False
        self.pose_anchors, self.transit = {}, None
        self._stub_look(now)

    def _stub_look(self, now):
        # Review delta2 P1-1: a look takes time (it used to be instant, so a look_again added only the 10 s window).
        # Full dock look STUB_LOOK_S (measured eight-pan dock look 8.4 s + return), the one-direction post-look
        # refresh STUB_REFRESH_LOOK_S (= timing.ALIGN_ENTRY_RELOOK_S, one pan move+settle and return). The fix
        # arrives at the end of the look. ``stub_first_look_s`` overrides the first look of a robot.
        self.looks = getattr(self, 'looks', 0)+1
        if self.looks == 1 and getattr(self, 'stub_first_look_s', None) is not None:
            look_s = self.stub_first_look_s
        else:
            look_s = STUB_REFRESH_LOOK_S if getattr(self, 'refix_refresh_look', False) else STUB_LOOK_S
        self.align_look_started_at = now
        self.stub_look_until = now+look_s
        self.set('stub_looking', now)

    def _stub_looking(self, now, arm_idle):
        if now < self.stub_look_until-1e-9:
            return
        self.sigma, self.fix_t = self.sigma_after_look, now
        self.set('align_relook_return', now)

    def _align_fix_checks(self, now):
        from harness.zone_pair_align import MAX_FIX_GAP_S
        return {'fix_gap': 0 <= now-self.fix_t < MAX_FIX_GAP_S-1e-8}

    def _align_relook_return(self, now, arm_idle):
        self.set('align', now)

    def _begin_align_relook(self, now, reason):
        self.relook_reasons = getattr(self, 'relook_reasons', [])+[reason]
        self._stub_look(now)

    def _align(self, now, arm_idle):
        self.arm.queue({**self.hover, 1: legacy.OPEN}, now, duration=.6)
        self.set('stub_hover', now)                 # hover@k+1 barrier (real gate), descent, close@k+1, then the close


class LookCtl(rf.SigmaRefix, HighController, LookStub):
    __init__ = tr.Controller.__init__
    observation, look = tr.Controller.observation, tr.Controller.look


@pytest.fixture
def look_team(monkeypatch):
    monkeypatch.setitem(legacy.STATUS_OF, 'align_relook_return', 'aligning')
    monkeypatch.setitem(legacy.STATUS_OF, 'stub_looking', 'aligning')
    monkeypatch.setattr(base, 'Ctl', LookCtl)

    def make(attached=True, **kw):
        bus, ctls = team(BEFORE_DOOR, over={'r1': True}, **kw)
        for c in ctls:
            assert isinstance(c, LookCtl)
            c.refix_llm_attached = attached
        return bus, ctls
    return make


def post(c):
    return (c.__dict__.get('refix_look') or {}).get('decisions', [])


def in_window(c, now):
    w = c._post_look_window()
    return c.state == 'align_relook_return' and w is not None and not w.get('resolved')


def test_post_look_rule_default_is_regrasp_after_the_window_with_a_fix_refresh(look_team):
    _, ctls = look_team()
    run(ctls, 190.)
    for c in ctls:
        assert c.failure is None and c.state == 'released', (c.rid, c.failure)
        (rec,) = post(c)
        assert rec['decided_by'] == 'rule_default' and rec['choice'] == 'regrasp' and rec['held_s'] == pytest.approx(P, abs=.11)
        assert rec['fix_still_fresh'] is False                               # 10 s > the 6 s fix gap
        assert c.relook_reasons == ['refix_post_look_refresh'] and c.looks == 2
        names = [r['event'] for r in hooks(c)]
        assert names[2:7] == ['setdown_started', 'setdown_completed', 'relook_result', 'regrasp_result', 'carry_resumed']
        assert hooks(c, 'relook_result')[0]['level'] == 'fix' and hooks(c, 'relook_result')[0]['sigma_band'] == 'fix'
        assert hooks(c, 'regrasp_result')[0]['post_look_offered'] is True
        assert c.refix_look['fix_pan'] is None                               # the stub look has no pan
        assert c.refix_refresh_look is False                                  # cleared when the refresh returned


def test_the_post_look_window_opens_in_every_condition_for_the_same_time(look_team):
    _, rule_only = look_team(attached=False)
    run(rule_only, 190.)
    _, attached = look_team(attached=True)
    run(attached, 190.)
    for a, b in zip(rule_only, attached):
        assert a.failure is None and b.failure is None
        assert post(a)[0]['held_s'] == post(b)[0]['held_s'] == pytest.approx(P, abs=.11)
        assert ev(a, 'refix_resumed_high')[0]['t'] == pytest.approx(ev(b, 'refix_resumed_high')[0]['t'])


def test_post_look_regrasp_latch_is_recorded_early_and_executed_at_the_window_end(look_team):
    _, ctls = look_team()
    fn, got = submit_once('regrasp', when=in_window, command='post_look_decision')
    on_tick(ctls[0], fn)
    run(ctls, 190.)
    assert got[0]['accepted']
    rec = post(ctls[0])[0]
    assert rec['decided_by'] == 'llm' and rec['held_s'] == pytest.approx(P, abs=.11)
    assert rec['decided_s'] < rec['executed_s']-P+.5
    assert ctls[0].failure is None and ctls[0].state == 'released'


def test_look_again_once_then_refused(look_team):
    _, ctls = look_team()
    r1 = ctls[0]
    got = []

    def fn(c, now):
        if in_window(c, now) and len(got) < 2 and len(post(c)) == len(got):
            got.append(c.post_look_decision('look_again', now))
    on_tick(r1, fn)
    run(ctls, 200.)
    assert [g['own_status'] for g in got] == ['LATCHED', rf.LOOK_AGAIN_USED]
    assert r1.relook_reasons == ['refix_look_again', 'refix_post_look_refresh'] and r1.looks == 3
    assert [p['choice'] for p in post(r1)] == ['look_again', 'regrasp']
    assert [r['level'] for r in hooks(r1, 'relook_result')] == ['fix', 'fix']
    assert r1.failure is None and r1.state == 'released'


def test_look_again_plus_a_shorter_partner_look_waits_at_the_hover_and_the_pair_closes_together(look_team):
    # Review delta2 P1-1 (fixed by decision A). r1: full first look (8.6 s), window, look_again (8.6 s), window, refresh;
    # r2: first look finds the fix in one direction (2.3 s), window, refresh. The skew 6.3 + 8.6 + 10 = 24.9 s exceeds
    # CLOSE_WAIT_S; r2 now waits at the hover@k+1 barrier and the pair closes and lifts together.
    from harness.zone_pair_grasp import CLOSE_WAIT_S
    _, ctls = look_team()
    r1, r2 = ctls
    r2.stub_first_look_s = STUB_REFRESH_LOOK_S
    got = []

    def fn(c, now):
        if in_window(c, now) and not got:
            got.append(c.post_look_decision('look_again', now))
    on_tick(r1, fn)
    run(ctls, 220.)
    assert got[0]['own_status'] == 'LATCHED'
    assert (STUB_LOOK_S-STUB_REFRESH_LOOK_S)+STUB_LOOK_S+rf.POST_LOOK_WINDOW_S > CLOSE_WAIT_S
    for c in ctls:
        assert c.failure is None and c.state == 'released', (c.rid, c.failure)
    hover = [e for e in ev(r2, 'barrier_go') if e['barrier'] == rf.HOVER_BARRIER]
    assert len(hover) == 1 and hover[0]['waited_s'] > CLOSE_WAIT_S
    go = {c.rid: [e['t'] for e in ev(c, 'barrier_go') if e['barrier'] in ('close', 'lift')] for c in ctls}
    assert go['r1'] == go['r2'] and len(go['r1']) == 2


def test_look_again_is_refused_after_one_per_robot_per_case():
    # decision v6-2: one per stop (LOOK_AGAIN_USED), one per robot per case (LOOK_AGAIN_CASE_LIMIT); own count only
    class Probe(rf.SigmaRefix):
        rid, seg, state = 'r1', 3, 'align_relook_return'

        def log(self, *a, **k):
            pass
    p = Probe()
    p.refix_look = {'window': {'opened_s': 0., 'pending': None}, 'look_again_used': 0}
    p.refix_look_again_total = 1
    assert p.post_look_decision('look_again', 1.)['own_status'] == rf.LOOK_AGAIN_CASE_LIMIT
    p.refix_look_again_total, p.refix_look['look_again_used'] = 0, 1
    assert p.post_look_decision('look_again', 1.)['own_status'] == rf.LOOK_AGAIN_USED
    p.refix_look_again_total, p.refix_look['look_again_used'] = 0, 0
    assert p.post_look_decision('look_again', 1.)['own_status'] == 'LATCHED'
    assert rf.LOOK_AGAIN_CASE_LIMIT in rf.REJECT_REASONS


def test_give_up_is_not_in_the_first_cohort_vocabulary(look_team):
    _, ctls = look_team()
    fn, got = submit_once('give_up', when=in_window, command='post_look_decision')
    on_tick(ctls[0], fn)
    run(ctls, 190.)
    assert got[0]['own_status'] == rf.UNKNOWN_CHOICE and 'give_up' not in rf.POST_LOOK_CHOICES
    assert not hasattr(rf, 'GIVE_UP')
    for c in ctls:
        assert c.failure is None and c.state == 'released'


def test_regrasp_is_refused_while_the_own_sigma_is_over_the_budget(look_team):
    _, ctls = look_team()
    r1 = ctls[0]
    got = []

    def fn(c, now):
        if in_window(c, now) and not got:
            c.sigma = (.0700, math.radians(1.))                               # over the derived 67.4 mm budget
            c.port.own.last_report.std_xy_m = .0700
            got.append(c.post_look_decision('regrasp', now))
            got.append(c.post_look_decision('look_again', now))
    on_tick(r1, fn)
    run(ctls, 200.)
    assert [g['own_status'] for g in got] == [rf.LOOK_OVER_BUDGET, 'LATCHED']
    assert [p['choice'] for p in post(r1)] == ['look_again', 'regrasp']
    assert r1.failure is None and r1.state == 'released'


def test_the_post_look_hold_is_not_counted_as_look_time():
    class Parent:
        def align_relook_expired(self, now):
            return now-self.align_look_started_at >= 8.

    class Probe(rf.SigmaRefix, Parent):
        pass
    p = Probe()
    p.align_look_started_at = 0.
    p.refix_look = {'window': {'opened_s': 7.5, 'resolved': False}}
    assert p.align_relook_expired(9.) is False                               # 9 - 1.5 s hold = 7.5 s of look
    p.refix_look['window']['resolved'] = True
    assert p.align_relook_expired(9.) is True


def test_production_class_routes_the_hooked_methods_through_sigma_refix_to_the_real_align_relook():
    from harness import zone_pair_align
    from tests.test_highpose_grasp_view import representative_class
    mro = representative_class().__mro__

    from harness.zone_pair_highpose_runtime import LightFail

    def owners(name):      # v105 DEV light: LightFail.fail only filters soft reasons and delegates to super()
        return [k for k in mro if name in k.__dict__ and k is not LightFail]
    for name in ('_align_relook_return', 'align_relook_expired', '_cp_open', '_wait_lower', '_lift', 'fail',
                 '_align_relook_stop', '_align_relook', 'align_look_choices'):
        assert owners(name)[0] is rf.SigmaRefix, (name, owners(name)[:3])
    # the rebound copies replace exactly the next owner (decision v4-4): nothing between SigmaRefix and PairAlignRelook
    for name in ('_align_relook_stop', '_align_relook', 'align_relook_expired'):
        assert owners(name)[1] is zone_pair_align.PairAlignRelook, (name, owners(name)[:3])
    for name in ('_align_relook_return', 'align_relook_expired', '_align_fix_checks', '_begin_align_relook'):
        real = [k for k in owners(name) if k is not rf.SigmaRefix]
        assert real and real[0].__module__ in (zone_pair_align.__name__, 'harness.zone_pair_highpose_posture_defer'), \
            (name, [k.__module__ for k in real])
    # tick: DeferRelook is in front and may return without super(); SigmaRefix compares with its own last state
    assert [k.__name__ for k in owners('tick')][:2] == ['DeferRelook', 'SigmaRefix']


def test_own_belief_is_a_closed_summary_without_numbers():
    from types import SimpleNamespace as NS
    b = rf.own_belief(NS(std_xy_m=.030, std_yaw_rad=math.radians(1.), last_fix_t=None), 10.)
    assert b == {'sigma_xy_band': 'fix', 'sigma_yaw_band': 'within', 'fix_age_bucket': 'none',
                 'dr_budget_remaining_bucket': 'gt_50pct', 'over_budget': False}
    b = rf.own_belief(NS(std_xy_m=.060, std_yaw_rad=math.radians(1.), last_fix_t=8.), 10.)
    assert (b['sigma_xy_band'], b['fix_age_bucket'], b['dr_budget_remaining_bucket']) == ('budget', 'lt_6s', 'lt_25pct')
    b = rf.own_belief(NS(std_xy_m=.070, std_yaw_rad=math.radians(3.), last_fix_t=-100.), 10.)
    assert b == {'sigma_xy_band': 'over', 'sigma_yaw_band': 'over', 'fix_age_bucket': 'ge_60s',
                 'dr_budget_remaining_bucket': 'none', 'over_budget': True}
    assert rf.own_belief(None, 0.)['sigma_xy_band'] == 'unknown'
    assert all(isinstance(v, (str, bool)) for v in b.values())


def test_stop_record_has_condition_latency_and_band():
    _, ctls = team(BEFORE_DOOR)
    for c in ctls:
        c.refix_condition = 'peer_nl'
    fn, got = submit_once('set_down')
    on_tick(ctls[0], fn)
    run(ctls, 140.)
    rec = decision(ctls[0])[0]
    assert rec['condition'] == 'peer_nl' and rec['sigma_band'] == 'fix' and rec['decided_by'] == 'llm'
    assert rec['latency_s'] == pytest.approx(.1, abs=1e-6)       # submitted on the entry tick, applied on the next
    assert decision(ctls[1])[0]['latency_s'] is None
    assert set(rf.record()['llm_hooks']['record_fields']) <= set(rec)


def test_record_lists_the_hooks():
    rec = rf.record()['llm_hooks']
    assert rec['events'] == list(rf.HOOK_EVENTS) and rec['never_blocks_tick'] is True
    assert rec['reject_reasons'] == list(rf.REJECT_REASONS)
    assert rec['latch_margin_s'] == pytest.approx(.2)
    assert rec['carry_choices'] == ['continue', 'set_down'] and rec['stop_window_s'] == 10.
    assert rec['post_look_choices'] == ['regrasp', 'look_again'] and rec['post_look_window_s'] == 10.
    assert 'give_up_code' not in rec
    top = rf.record()
    assert top['id'] == 'v98_sigma_refix_v6' and top['bundle_revision_required']['required'] is True
    assert top['decide_window_s'] == 10. and top['stop_hold_s'] == pytest.approx(11.7)
    assert top['no_look_regrasp']['implemented'] is False and top['keep_hold']['implemented'] is False
    assert top['refresh_look']['max_directions'] == 1
    assert top['look_again_caps'] == {'per_stop': 1, 'per_robot_per_case': 1, 'codes': [rf.LOOK_AGAIN_USED,
                                      rf.LOOK_AGAIN_CASE_LIMIT], 'note': top['look_again_caps']['note']}
    assert top['refix_look']['pans'] == [1500, 1230, 970, 700, 1770, 2030, 2300]


def test_constants_follow_their_sources():
    from harness.zone_pair_highpose_timing import CHECKPOINT_REOBSERVE_S
    from harness import zone_pair_highpose_relook as dock
    assert rf.STOP_TAIL_S == pytest.approx(CHECKPOINT_REOBSERVE_S+.5) and rf.confirm_window_s() == CHECKPOINT_REOBSERVE_S
    assert rf.REFIX_LOOK_PANS == tuple(dict.fromkeys(dock.DOCK_LOOK_PANS)) and rf.REFIX_MAX_DIRECTIONS == 7
    assert rf.REFIX_MAX_LOOK_S == dock.LOOK_S == 9.
    # the v3 re-fix look path (stop + .8+.6 first pan, 6 x (.4+.6), .6+.3 return) fits the measured dock bound
    assert .8+.6+6*(.4+.6)+.6+.3 < rf.REFIX_MAX_LOOK_S


# ---------------------------------------------------------------- re-fix look directions (decision v4-4)
from types import SimpleNamespace as _NS  # noqa: E402

from harness.zone_pair_align import MAX_DIRECTIONS as V3_DIRECTIONS, PairAlignRelook  # noqa: E402

# the offline ranking of r1 at stop 4 (sigma_refix_model diag): scores of the parent's ranked list in score order
RANKED = [{'pan': p, 'observability_score': s} for p, s in
          ((1500, 192.), (1770, 192.), (1230, 192.), (970, 192.), (2030, 185.), (700, 189.), (2300, 155.))]


class _Base:
    policy = _NS(posterior_relook=True, beam_relative=False)

    def __init__(self, ranked=RANKED):
        self.ranked, self.logged, self.states, self.failure, self.seg, self.rid = list(ranked), [], [], None, 1, 'r1'
        self.state, self.port = 'align', _NS(own=_NS(last_report=_NS(t_est=0., fix_age_s=99., last_fix_t=None, std_xy_m=.06,
                                                                      std_yaw_rad=.02), servo={1: 2000, 6: 1500}))
        self.arm = _NS(queue=lambda *a, **k: None, until=0., events=[])
        self.driver, self.status = None, None

    def align_look_choices(self):
        return [r for r in self.ranked if r['pan'] not in getattr(self, 'relook_excluded', ())]

    def align_stop_ready(self, now):
        return True

    def log(self, rid, kind, now, **kw):
        self.logged.append((kind, kw))

    def set(self, state, now, **kw):
        self.state = state
        self.states.append(state)

    def fail(self, reason, now):
        self.failure, self.state = reason, 'failed'


class DockProbe(rf.SigmaRefix, PairAlignRelook, _Base):
    def _begin_provider_look(self, now):
        pass

    def _align_fix_checks(self, now):
        return {'stub_fix': False}                                           # no fix anywhere: every direction tried


def _walk(p, phase):
    p.refix_phase = phase
    p.state, p.align_look_started_at, p.align_look_total_s = 'align_relook_stop', 0., 0.
    p._align_relook_stop(0., True)
    visited = [p.active_relook_pan]
    for i in range(10):
        if p.state == 'failed':
            break
        p.look = lambda now: {'sim_time': 1.e9, 'frame_id': 'f', 'sha256': 'x'}
        p._align_relook(1.+i, True)
        if p.state != 'failed':
            visited.append(p.active_relook_pan)
    return visited


def test_refix_look_tries_the_dock_directions_in_dock_order_with_the_real_align_code():
    p = DockProbe()
    assert _walk(p, 'looking') == [1500, 1230, 970, 700, 1770, 2030, 2300]
    assert p.failure == 'ALIGN_RELOOK_NO_FIX'
    sel = [kw for k, kw in p.logged if k == 'align_view_selection'][0]['candidates']
    assert [r['order'] for r in sel] == ['refix_dock_look']*7


def test_post_look_refresh_looks_in_one_direction_starting_at_the_fix_pan():
    # decision v6-2: the refresh after the 10 s window tries ONE direction, the pan that gave the look fix first
    p = DockProbe()
    p.refix_look, p.refix_refresh_look = {'fix_pan': 970}, True
    assert _walk(p, 'regrasping') == [970] and p.failure == 'ALIGN_RELOOK_NO_FIX'
    sel = [kw for k, kw in p.logged if k == 'align_view_selection'][0]['candidates']
    assert sel[0]['pan'] == 970 and {r['order'] for r in sel} == {'refix_refresh'}
    q = DockProbe(ranked=[r for r in RANKED if r['pan'] != 970])             # fix pan now guard-refused
    q.refix_look, q.refix_refresh_look = {'fix_pan': 970}, True
    assert _walk(q, 'regrasping') == [1500]
    n = DockProbe()                                                          # no recorded fix pan: dock order first
    n.refix_look, n.refix_refresh_look = {'fix_pan': None}, True
    assert _walk(n, 'regrasping') == [1500]
    r = DockProbe()                                                          # a look_again keeps the full dock look
    r.refix_look, r.refix_refresh_look = {'fix_pan': 970}, False
    assert _walk(r, 'looking') == [1500, 1230, 970, 700, 1770, 2030, 2300]


def test_outside_the_refix_the_v3_ranked_three_directions_are_unchanged():
    p = DockProbe()
    assert _walk(p, None) == [r['pan'] for r in RANKED[:V3_DIRECTIONS]] and p.failure == 'ALIGN_RELOOK_NO_FIX'


def test_refix_look_keeps_the_guard_filter_and_drops_nothing_else():
    p = DockProbe(ranked=[r for r in RANKED if r['pan'] not in (700, 2030)])         # guard-refused pans
    assert _walk(p, 'regrasping') == [1500, 1230, 970, 1770, 2300]


def test_refix_look_time_bound_is_the_dock_bound_only_in_the_refix_phases():
    p = DockProbe()
    p.state, p.align_look_started_at, p.align_look_total_s = 'align_relook', 0., 0.
    p.refix_phase = 'looking'
    assert p.align_relook_expired(8.5) is False and p.align_relook_expired(9.) is True
    p.refix_phase = None
    assert p.align_relook_expired(8.) is True                              # v3 MAX_LOOK_S unchanged elsewhere


def test_refix_choices_use_the_execution_sweep_guard_without_the_clearance_weight(monkeypatch):
    from harness import zone_pair_align
    seen = {}

    def fake_rank(static_map, report, servo, guard, provider, *, recovery_v6=False, excluded=(), safety_pose=None):
        seen.update(recovery_v6=recovery_v6, guard=guard, excluded=set(excluded))
        return list(RANKED)
    monkeypatch.setattr(zone_pair_align, 'ranked_look_pans', fake_rank)
    p = DockProbe()
    p.port.own.map, p.port.own.pose = 'map', 'pose'
    p.refix_sweep_guard = lambda: 'v98-sweep-guard'
    p.relook_excluded = {970}
    p.refix_phase = 'looking'
    assert [r['pan'] for r in p.align_look_choices()] == [1500, 1230, 970, 700, 1770, 2030, 2300]
    assert seen == {'recovery_v6': False, 'guard': 'v98-sweep-guard', 'excluded': {970}}
