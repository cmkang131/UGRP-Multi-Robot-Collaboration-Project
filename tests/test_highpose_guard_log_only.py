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
    moving = any(cm['kind'] == 'mecanum' and any(cm.get(k, 0.) for k in ('forward', 'left', 'turn')) for cm in commands)
    assert event['moving'] is moving and 'parent_commands' in event      # #383 P3: motion vs hold under a soft stop


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


def test_case_end_needs_every_robot_pair_job_ended():
    from types import SimpleNamespace as NS
    from scripts import run_pair_highpose as runner
    look, pair = {'kind': 'look_around'}, {'kind': 'pair_carry'}
    rt_ = lambda **jobs: NS(actors={r: NS(jobs_done=j) for r, j in jobs.items()})
    assert runner.jobs_ended_all(rt_(r1=[look, pair], r2=[pair])) is True
    assert runner.jobs_ended_all(rt_(r1=[look, pair], r2=[look])) is False
    assert runner.jobs_ended_all(rt_(r1=[pair])) is False
    assert runner.jobs_ended_all(NS(actors={})) is False


def test_align_relook_no_fix_resumes_in_light_mode(monkeypatch):
    from harness.zone_pair_highpose_runtime import LightFail
    queued = []
    class B(_Base):
        state, align_resume_name = 'align_relook', 'cp_align'
        arm = type('A', (), {'queue': lambda self, *a, **k: queued.append(a)})()
        def set(self, state, now, **d):
            self.state = state
    ctl = type('C', (LightFail, B), {})()
    import harness.owncam_pair_beam_v2 as pb
    monkeypatch.setattr(pb, 'pose_of', lambda name: {'name': name})
    ctl.fail('ALIGN_RELOOK_NO_FIX', 5.)
    assert ctl.state == 'align_relook_return' and ctl.failed == [] and queued
    assert ctl.logged[-1]['would_reason'] == 'ALIGN_RELOOK_NO_FIX'


def test_align_relook_fix_expired_resumes_align_in_light_mode():
    from harness.zone_pair_highpose_runtime import LightFail
    class B(_Base):
        state, align_started_at, align_look_started_at = 'align_relook_return', 1., 4.
        def set(self, state, now, **d):
            self.state = state
    ctl = type('C', (LightFail, B), {})()
    ctl.fail('ALIGN_RELOOK_FIX_EXPIRED', 5.)
    assert ctl.state == 'align' and ctl.failed == [] and ctl.state_t == 1. and ctl.align_look_total_s == 1.


def test_align_timeout_opens_a_new_window_in_light_mode():
    from harness.zone_pair_highpose_runtime import LightFail
    class B(_Base):
        state, state_t, align_started_at = 'align', 10., 10.
    ctl = type('C', (LightFail, B), {})()
    ctl.fail('ALIGN_TIMEOUT', 70.)
    assert ctl.failed == [] and ctl.state == 'align' and ctl.state_t == ctl.align_started_at == 70.


def test_partial_fix_provider_follows_the_flag(monkeypatch):
    import harness.zone_pair_highpose_partial_fix as pfix
    import harness.vision_pose_source_highpose as vph
    from harness import zone_pair_highpose_runtime as rt_
    seen = {}
    def fake_init(self, static, cal, sha, *, seed, provider_factory=None):
        seen['factory'] = provider_factory
        raise StopIteration
    monkeypatch.setattr(rt_, 'bind', lambda f, **k: fake_init)
    for flag, want in ((True, pfix.build_provider), (False, vph.build_provider)):
        monkeypatch.setattr(c, 'PARTIAL_FIX', flag)
        with pytest.raises(StopIteration):
            rt_.Runtime(None, None, None, seed=0)
        assert seen['factory'] is want


def test_extra_dev_seed_for_full_case_only_in_dev_light(monkeypatch):
    from scripts import run_pair_highpose as runner
    assert runner.seed_admission(912, None, c.DEV_PILOT)['extra_dev_seed']['pooled'] is False
    monkeypatch.setattr(c, 'DEV_LIGHT', False)
    with pytest.raises(Exception):
        runner.seed_admission(912, None, c.DEV_PILOT)
    assert runner.seed_admission(912, 'align_to_carry', c.DEV_PILOT)['extra_dev_seed'] is not None


def test_run_case_uses_the_shared_seed_rule(monkeypatch):
    """2026-10-05 light8: run_case refused seed 912 (it called require_dev_seed directly). It now uses seed_admission."""
    from scripts import run_pair_highpose as runner
    bundle = {'admission_mode': c.DEV_PILOT}           # no map_id: stops right after the seed rule
    with pytest.raises(KeyError):
        runner.run_case(bundle, None, seed=912, backend_factory=None)
    monkeypatch.setattr(c, 'DEV_LIGHT', False)
    with pytest.raises(ValueError, match='SEED_911'):
        runner.run_case(bundle, None, seed=912, backend_factory=None)


def _relook_ctl(state, monkeypatch, queued):
    from harness.zone_pair_highpose_runtime import LightFail
    class B(_Base):
        align_resume_name, align_started_at, align_look_started_at = 'cp_align', 1., 4.
        arm = type('A', (), {'queue': lambda self, *a, **k: queued.append(a)})()
        def set(self, state, now, **d):
            self.state = state
    import harness.owncam_pair_beam_v2 as pb
    monkeypatch.setattr(pb, 'pose_of', lambda name: {'name': name})
    ctl = type('C', (LightFail, B), {})()
    ctl.state = state
    return ctl


@pytest.mark.parametrize('state, after', [('align_relook', 'align_relook_return'), ('align_relook_return', 'align'),
                                          ('align_relook_stop', 'align')])
def test_align_relook_timeout_resumes_instead_of_holding(monkeypatch, state, after):
    """#383 P2-a: light5 held ALIGN_RELOOK_TIMEOUT x751 to the cap; it now leaves the relook state."""
    queued = []
    ctl = _relook_ctl(state, monkeypatch, queued)
    ctl.fail('ALIGN_RELOOK_TIMEOUT', 5.)
    assert ctl.state == after and ctl.failed == []
    assert bool(queued) == (state == 'align_relook')


def test_approach_timeout_progresses_and_repeat_limit_fails():
    """A tick loop with the frozen approach time limit: the state keeps running in new windows (not every tick), and
    the same soft reason more than DEV_LIGHT_REPEAT_LIMIT times becomes a real, logged failure."""
    from harness.zone_pair_highpose_runtime import LightFail
    limit_s = 10.
    class B(_Base):
        state, state_t = 'approach', 0.
        def tick(self, now):
            if now - self.state_t > limit_s:
                return self.fail('APPROACH_TIMEOUT', now)
    ctl = type('C', (LightFail, B), {})()
    soft = 0
    for k in range(1, 1001):          # 100 SIM s at 0.1 s
        before = ctl.state_t
        ctl.tick(k * .1)
        soft += ctl.state_t != before
    assert ctl.failed == [] and 8 <= soft <= 10            # one new window per 10 s, not one event per tick
    for k in range(1001, 3001):
        ctl.tick(k * .1)
        if ctl.failed:
            break
    assert ctl.failed == ['APPROACH_TIMEOUT']
    rows = [e for e in ctl.logged if e['event'] == 'dev_light_repeat_limit']
    assert rows and rows[0]['occurrences'] == c.DEV_LIGHT_REPEAT_LIMIT + 1


def test_scheduled_reobserve_limit_is_hard_at_the_controller():
    from harness.zone_pair_highpose_runtime import LightFail
    ctl = type('C', (LightFail, _Base), {})()
    ctl.state = 'align'
    ctl.fail('PAIR_SCHEDULED_REOBSERVE_LIMIT', 5.)
    assert ctl.failed == ['PAIR_SCHEDULED_REOBSERVE_LIMIT']
    assert 'PAIR_SCHEDULED_REOBSERVE_LIMIT' in c.DEV_LIGHT_SOFT_STOPS     # still soft in CommandGuard.before_control


def test_formal_mode_refused_while_dev_only_flags_are_on(monkeypatch):
    """#383 P1: module defaults are DEV values, so a formal (MEASURED_SIM) run must be refused, not recorded as on."""
    assert c.dev_only_flags()
    with pytest.raises(ValueError, match=c.DEV_ONLY_FLAGS_BLOCK):
        c.require_dev_only_flags(c.MEASURED_SIM)
    monkeypatch.setattr(c, 'registry', lambda: {'runnable': True})     # even a runnable registry is refused
    with pytest.raises(ValueError, match=c.DEV_ONLY_FLAGS_BLOCK):
        c.require_runnable({'admission_mode': c.MEASURED_SIM, 'runnable': True})
    c.require_dev_only_flags(c.DEV_PILOT)
    for name, value in (('DEV_LIGHT', False), ('PARTIAL_FIX', False), ('COLLISION_GUARD_MODE', 'enforce')):
        monkeypatch.setattr(c, name, value)
    assert c.dev_only_flags() == []
    c.require_dev_only_flags(c.MEASURED_SIM)


def test_student_run_case_refuses_formal_mode_before_anything(tmp_path, monkeypatch):
    from scripts import run_pair_highpose as runner
    made = []
    monkeypatch.setattr(c, 'calibration_for', lambda *a, **k: None)
    monkeypatch.setattr(c, 'require_runnable', lambda *a, **k: None)   # its own check is tested above
    with pytest.raises(ValueError, match=c.DEV_ONLY_FLAGS_BLOCK):
        runner.student_run_case({'admission_mode': c.MEASURED_SIM, 'map_id': 'm'}, tmp_path/'x', seed=911,
                                backend_factory=lambda *a, **k: made.append(1))
    assert not made and not (tmp_path/'x').exists()


def test_staged_runtime_uses_the_same_provider_choice(monkeypatch):
    """#383 P2-c: stage probes go through the partial-fix branch too (the bundle's partial_fix record is what runs)."""
    import harness.zone_pair_highpose_partial_fix as pfix
    import harness.vision_pose_source_highpose as vph
    from harness import zone_pair_highpose_runtime as rt_
    from harness import zone_pair_highpose_staging as staging
    class Used(Exception):
        pass
    monkeypatch.setattr(pfix, 'build_provider', lambda *a, **k: (_ for _ in ()).throw(Used('partial')))
    monkeypatch.setattr(vph, 'build_provider', lambda *a, **k: (_ for _ in ()).throw(Used('plain')))
    monkeypatch.setattr(rt_, 'bind', lambda f, **k: (lambda self, *a, provider_factory, **kw: provider_factory()))
    for flag, want in ((True, 'partial'), (False, 'plain')):
        monkeypatch.setattr(c, 'PARTIAL_FIX', flag)
        with pytest.raises(Used, match=want):
            staging.StagedRuntime(None, None, None, seed=0, stage='align_to_carry', staging={'priors': {}})
