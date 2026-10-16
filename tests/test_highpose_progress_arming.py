"""v98 loaded no-progress check: carry-leg reset (A) + REQUIRED_MOVEMENT_M commanded motion before the first fix (B).

Diagnosis (align_to_carry@399bf87d, outputs/v98-progress-arming-diag-20261005): one 3.5 mm align command set the frozen
``MovedFixMonitor.move_t0``, the stationary re-grasp fix then armed the baseline, and loaded HIGH carry (no own fix) fired
``needs_check`` at 0.404 m -> POSE_UNCERTAIN_PROGRESS. These tests pin the fix and keep the frozen classes as they are.
"""
import json
import math
from pathlib import Path
from types import SimpleNamespace

import pytest

from harness import zone_own_guards as g
from harness import zone_pair_highpose_progress as progress
from harness.zone_final_pair_guards import MovedFixMonitor

FIXTURE = Path(__file__).parent / 'fixtures' / 'v98_progress_arming_align_to_carry_399bf87d.json'
REOBSERVING = ('pregrasp_look', 'align_relook_stop', 'align_relook', 'align_relook_return')


class Report:
    def __init__(self):
        self.last_fix_t = None


def mecanum(t, forward=0., left=0.):
    return {'t': t, 'kind': 'mecanum', 'forward': forward, 'left': left, 'turn': 0.}


def drive(monitor, row):
    monitor.drove(g.commanded_step_m(row))
    monitor.note_command(row)


def test_registered_constants_unchanged():
    assert (g.REQUIRED_MOVEMENT_M, g.STALL_COMMANDED_M, g.TRUSTED_FIX_AGE_S) == (.10, .40, .3)


def test_tiny_command_is_not_motion_until_required_movement():
    """B: 3.5 mm of commanded travel is not 'motion'; the move time is when the sum reaches REQUIRED_MOVEMENT_M."""
    m = progress.LegMovedFixMonitor(Report)
    drive(m, mecanum(298.0, forward=.035))                # 0.0035 m, the seg 4 align command
    assert m.move_t0 is None and m.move_accum_m == pytest.approx(.0035)
    t = 300.
    while m.move_t0 is None:
        t += .1
        drive(m, mecanum(t, forward=.2))                   # 0.02 m per control tick
    assert m.move_accum_m >= g.REQUIRED_MOVEMENT_M - 1e-12
    assert m.move_t0 == pytest.approx(t) and t == pytest.approx(300.5)
    m.reset()
    assert (m.move_t0, m.move_accum_m, m.baseline) == (None, 0., None)


@pytest.mark.parametrize('cls, armed', [(MovedFixMonitor, True), (progress.LegMovedFixMonitor, False)])
def test_seg4_sequence_frozen_fires_new_does_not(cls, armed):
    """Reproduce seg 4: tiny align command (298.0), stationary re-grasp fix (300.55), then 0.404 m HIGH carry, no fix."""
    rep = Report()
    m = cls(lambda: rep)
    drive(m, mecanum(298.0, forward=.035))
    rep.last_fix_t = 300.55
    m.trusted((3.0, -1.0), 1.2)
    assert (m.baseline is not None) is armed
    t = 328.4
    for _ in range(int(round(.4 / .02)) + 1):              # 0.42 m commanded, no trusted fix while loaded at HIGH
        t += .1
        drive(m, mecanum(t, forward=.2))
    assert m.needs_check() is armed                        # frozen class: POSE_UNCERTAIN_PROGRESS; v98: no evidence, no fire
    assert m.stalled() is False


def test_fix_after_real_motion_arms_and_stall_still_detected():
    """With a fix after real motion the check still works: a later fix that did not move the baseline is a stall."""
    rep = Report()
    m = progress.LegMovedFixMonitor(lambda: rep)
    for i in range(6):                                     # 0.12 m commanded
        drive(m, mecanum(10. + .1*i, forward=.2))
    assert m.move_t0 == pytest.approx(10.4)
    rep.last_fix_t = 11.0
    m.trusted((1.0, 0.0), 2.0)
    assert m.baseline is not None and m.armed_count == 1
    for i in range(21):                                    # 0.42 m more, robot does not move (fixes at the same place)
        drive(m, mecanum(12. + .1*i, forward=.2))
    assert m.needs_check() is True                         # over 0.40 m without a newer trusted estimate
    rep.last_fix_t = 14.5
    m.trusted((1.0, 0.0), 2.0)
    assert m.stalled() is True and m.needs_check() is False


class FakeEp:
    def __init__(self):
        self.controller = SimpleNamespace(state='align', seg=4)
        self.own = SimpleNamespace(robot_id='r2', last_report=Report())
        self.logs = []

    def log(self, rid, event, now, **kw):
        self.logs.append((rid, event, now, kw))


def test_leg_reset_once_per_carry_leg():
    """A: the first guard check of each carry leg resets the monitor; nothing else does."""
    guard = SimpleNamespace(ep=FakeEp(), approach=False)
    progress.install(guard)
    m = guard.monitor
    assert isinstance(m, progress.LegMovedFixMonitor) and m.report_source() is guard.ep.own.last_report
    m.baseline, m.move_t0, m.move_accum_m = (0., 0., 1., 0.), 298., .12
    assert progress.leg_reset(guard, 300.) is False        # not carrying a leg yet (align)
    guard.ep.controller.state = 'carry'
    assert progress.leg_reset(guard, 328.4) is True
    assert (m.baseline, m.move_t0, m.move_accum_m, m.leg_resets) == (None, None, 0., 1)
    rid, event, now, kw = guard.ep.logs[-1]
    assert (rid, event, now, kw['seg']) == ('r2', progress.LEG_RESET_EVENT, 328.4, 4)
    assert kw['before'] == {'armed': True, 'move_t0': 298., 'move_accum_m': .12}
    m.baseline = (0., 0., 1., 0.)
    assert progress.leg_reset(guard, 330.) is False        # same leg: no second reset
    assert m.baseline is not None
    guard.ep.controller.seg = 5
    assert progress.leg_reset(guard, 360.) is True and m.baseline is None and m.leg_resets == 2
    guard.approach = True
    guard.ep.controller.seg = 6
    assert progress.leg_reset(guard, 400.) is False        # unloaded approach keeps the registered monitor behaviour


def test_runtime_guard_uses_v98_progress():
    import inspect
    from harness import zone_pair_highpose_runtime as rt
    assert 'progress.install(self)' in inspect.getsource(rt.CommandGuard.__init__)
    src = inspect.getsource(rt.CommandGuard.check)
    assert src.index('progress.leg_reset(self, now)') < src.index('super().check(now, commands)')


def replay(cls, robot, route, leg_reset):
    """Feed the recorded own commands and loaded gate checks to a monitor in guard order; first fire or None."""
    rep = Report()
    m = cls(lambda: rep)
    cmds, checks = robot['commands'], robot['loaded_gate_checks']
    ci, segment, leg_seg, last_ev = 0, None, None, None
    for t, state, seg, fix_age, std_xy, low_xy, x, y, t_est in checks:
        while ci < len(cmds) and cmds[ci][0] < t - 1e-6:
            ct, kind, fwd, left = cmds[ci]
            drive(m, {'t': ct, 'kind': kind, 'forward': fwd, 'left': left})
            ci += 1
        if state in REOBSERVING:
            continue
        if leg_reset and state == 'carry' and seg != leg_seg:
            m.reset()
            leg_seg = seg
        if segment != seg:
            m.reset()
            segment, last_ev = seg, None
        if (t_est != last_ev and fix_age is not None and fix_age <= g.TRUSTED_FIX_AGE_S and std_xy <= low_xy):
            rep.last_fix_t = t_est - fix_age
            target = route[min(seg + 1, len(route) - 1)]
            m.trusted((x, y), math.dist((x, y), target[:2]))
            last_ev = t_est
        if m.stalled() or m.needs_check():
            return t, seg, round(m.commanded_m - m.baseline[3], 4)
    return None


def test_golden_replay_align_to_carry_399bf87d():
    """Recorded run: the frozen semantics fire for r2 on leg 5 (seg 4, 341.5 s, ~0.40 m); A + B fire for neither robot."""
    data = json.loads(FIXTURE.read_text())
    assert FIXTURE.stat().st_size < 1 << 20
    route = data['route']
    fired = replay(MovedFixMonitor, data['robots']['r2'], route, leg_reset=False)
    assert fired is not None and fired[1] == 4 and fired[0] == pytest.approx(341.5, abs=.06) and fired[2] >= .40
    for rid in ('r1', 'r2'):
        assert replay(progress.LegMovedFixMonitor, data['robots'][rid], route, leg_reset=True) is None


def test_required_movement_boundary_and_invalid_rows():
    """B boundary: 0.0999 m is not motion; the row that reaches 0.10 m sets move_t0; a fix at that time is ignored."""
    rep = Report()
    m = progress.LegMovedFixMonitor(lambda: rep)
    for bad in ({'t': None, 'kind': 'mecanum', 'forward': .5}, {'t': float('nan'), 'kind': 'mecanum', 'forward': .5},
                {'t': True, 'kind': 'mecanum', 'forward': .5}, {'t': 1.0, 'kind': 'hold'}, {'t': 1.0, 'kind': 'arm', 'servo_id': 3}):
        m.note_command(bad)
    assert (m.move_t0, m.move_accum_m) == (None, 0.)
    m.note_command(mecanum(2.0, forward=.999))            # 0.0999 m
    assert m.move_t0 is None
    m.note_command(mecanum(2.1, forward=.001))            # reaches 0.1000 m
    assert m.move_t0 == pytest.approx(2.1)
    rep.last_fix_t = 2.1
    m.trusted((0., 0.), 1.)
    assert m.baseline is None and m.ignored_count == 1     # not strictly after the move
    rep.last_fix_t = 2.15
    m.trusted((0., 0.), 1.)
    assert m.baseline is not None and m.armed_count == 1


def test_not_the_pair_guard_monitor_class():
    """PairCommandGuard.on_command calls note_command for zone_pair_guards.MovedFixMonitor; ours must not be one (no double count)."""
    from harness import zone_pair_guards
    assert not issubclass(progress.LegMovedFixMonitor, zone_pair_guards.MovedFixMonitor)
    assert issubclass(progress.LegMovedFixMonitor, MovedFixMonitor)


def test_bare_guard_without_monitor_is_left_alone():
    guard = SimpleNamespace(ep=FakeEp(), approach=False)
    guard.ep.controller.state = 'carry'
    assert progress.leg_reset(guard, 1.) is False and guard.ep.logs == []


def test_seg0_near_miss_is_reset_at_leg_start():
    """seg 0 (0.372 m armed): a baseline armed by align motion + the pre-grasp fix is dropped when the leg starts."""
    guard = SimpleNamespace(ep=FakeEp(), approach=False)
    guard.ep.controller.seg = 0
    rep = guard.ep.own.last_report
    m = progress.install(guard)
    for i in range(6):
        drive(m, mecanum(40. + .1*i, forward=.2))           # 0.12 m align motion
    rep.last_fix_t = 62.15
    m.trusted((0.2, 0.0), 1.5)
    assert m.baseline is not None
    guard.ep.controller.state = 'carry'
    assert progress.leg_reset(guard, 86.6) is True
    for i in range(30):                                    # 0.60 m of HIGH carry, no fix
        drive(m, mecanum(86.7 + .1*i, forward=.2))
    assert m.needs_check() is False and m.stalled() is False
