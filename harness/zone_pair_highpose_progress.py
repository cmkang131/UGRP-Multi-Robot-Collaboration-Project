"""v98 loaded no-progress check: reset per carry leg (A) + motion means REQUIRED_MOVEMENT_M of own commanded travel (B).

Coordinator decision 2026-10-05 after the align_to_carry@399bf87d diagnosis (``outputs/v98-progress-arming-diag-20261005``):
the loaded pair's ``MovedFixMonitor`` (``zone_final_pair_guards``, p2f semantics: the first trusted fix must follow the first
issued move) was armed in seg 4 only, because one 3.5 mm align ``mecanum`` command (298.0 s) set ``move_t0`` (any step > 0)
and the stationary re-grasp fix (300.55 s) then counted as "after motion". Loaded HIGH carry gives no trusted fix (fix age
40.8 s at the stop), so 0.404 m of commanded carry travel fired ``needs_check`` -> ``POSE_UNCERTAIN_PROGRESS`` (341.5 s). seg 2
had no ``mecanum`` row in the same window, so it was never armed; earlier passes were "never armed", not "checked".

Two changes, both in this v98-only file (the shared guards stay byte-identical to origin/main):

A. ``leg_reset``: at the first guard check of every carry leg (controller state ``carry`` in a segment not yet reset) the
   monitor is reset, like Nav2 ``SimpleProgressChecker::reset()`` that ``ControllerServer`` calls on every new path. The pair
   guard's own reset on a segment change runs only at its first loaded check of that segment (late, inside the re-grasp align
   after a set-down), so a baseline from the stationary re-grasp could survive into the leg.
B. ``LegMovedFixMonitor``: "motion" for the first-fix rule is own commanded planar travel accumulated since the last reset of at
   least the existing ``REQUIRED_MOVEMENT_M`` (0.10 m, Nav2 ``required_movement_radius`` scaled to this robot) -- the same
   constant the monitor already uses for "moved". No new constant, no guard limit changed (``STALL_COMMANDED_M`` 0.40 m and
   ``TRUSTED_FIX_AGE_S`` 0.3 s unchanged).

Stated as a fact, not hidden (README, PR, later preregistration): during loaded HIGH carry there is no independent own-camera
fix, so after A + B the loaded no-progress (stall) check has effectively no evidence there and does not fire. Passing a carry
leg is NOT evidence that a stall would have been detected. Own-camera visual odometry slip checks (option C) are #366, after E2E.
"""
from __future__ import annotations

import math

from harness import zone_own_guards as g
from harness.zone_final_pair_guards import MovedFixMonitor

LEG_RESET_EVENT = 'progress_monitor_leg_reset'


def _finite_time(t):
    return isinstance(t, (int, float)) and not isinstance(t, bool) and math.isfinite(t)


class LegMovedFixMonitor(MovedFixMonitor):
    """``MovedFixMonitor`` whose first move is REQUIRED_MOVEMENT_M of accumulated own commanded travel since reset (B)."""

    def __init__(self, report_source, approach=lambda: False):
        super().__init__(report_source, approach)
        self.move_accum_m = 0.
        self.leg_resets = 0

    def note_command(self, row):
        if self.move_t0 is not None:
            return
        step, t = g.commanded_step_m(row), row.get('t')
        if step > 0 and _finite_time(t):
            self.move_accum_m += float(step)
            if self.move_accum_m >= g.REQUIRED_MOVEMENT_M - 1e-12:
                self.move_t0 = float(t)

    def reset(self):
        super().reset()
        self.move_accum_m = 0.


def install(guard):
    """Replace the guard's loaded monitor with ``LegMovedFixMonitor`` (same report source and approach flag)."""
    guard.monitor = LegMovedFixMonitor(lambda: guard.ep.own.last_report, lambda: guard.approach)
    guard.progress_leg_reset_seg = None
    return guard.monitor


def leg_reset(guard, now):
    """A: reset the loaded monitor once at the start of each carry leg (first guard check in state ``carry`` of a segment)."""
    # Keyed on the controller segment, not on a state edge: every carry leg has its own seg, so a leg start is never missed
    # when no guard check runs in the states between legs (wait_lower, wait_carry). A guard built without __init__ (tests)
    # has no monitor and is left alone.
    monitor = getattr(guard, 'monitor', None)
    ctl = getattr(guard.ep, 'controller', None)
    if monitor is None or getattr(guard, 'approach', True) or getattr(ctl, 'state', None) != 'carry':
        return False
    seg = getattr(ctl, 'seg', None)
    if seg == getattr(guard, 'progress_leg_reset_seg', None):
        return False
    before = {'armed': monitor.baseline is not None, 'move_t0': monitor.move_t0,
              'move_accum_m': round(float(getattr(monitor, 'move_accum_m', 0.)), 4)}
    monitor.reset()
    guard.progress_leg_reset_seg = seg
    if hasattr(monitor, 'leg_resets'):
        monitor.leg_resets += 1
    guard.ep.log(guard.ep.own.robot_id, LEG_RESET_EVENT, now, seg=seg, before=before,
                 rule='Nav2 SimpleProgressChecker reset per new path; motion = REQUIRED_MOVEMENT_M commanded',
                 high_carry_stall_evidence='none (no own-camera fix while loaded at HIGH)')
    return True
