"""Stationary recovery for a rejected own-camera sweep (no simulator input).

An initial PF estimate can be initialized but still too broad to certify any pan near the
spawn's west wall. Keep all collision margins, hold the issued posture, and let passive own
frames refine the estimate. Ten SIM seconds bounds the *cumulative* waiting per sweep; a
briefly clear path or a different target never replenishes it. This is not permission to move
through an inflated obstacle, nor a claim that a blocked estimate means physical contact.
"""
from __future__ import annotations

import math

from harness.zone_own_guards import GATE_LOADED, GATE_UNLOADED, OwnPose

SWEEP_REOBSERVE_S = 10.


class SweepRecheck:
    def __init__(self, *, loaded_profile=None):
        self.waited_s = 0.
        self.last_wait = None
        self.loaded_profile = GATE_LOADED if loaded_profile is None else loaded_profile

    def _account_wait(self, now):
        if self.last_wait is not None:
            self.waited_s += max(0., now - self.last_wait)
            self.last_wait = None

    def _wait(self, now):
        if self.waited_s >= SWEEP_REOBSERVE_S - 1e-9:
            return 'blocked'
        self.last_wait = now
        return 'wait'

    def check_gate(self, now, *, ready):
        """Gate dwell spends the same stationary-observation budget as arm/pan/restore."""
        self._account_wait(now)
        return 'clear' if ready else self._wait(now)

    def check(self, now, guard, current, target, pose, *, loaded):
        self._account_wait(now)
        # A missing/invalid belief is an observation wait, never a zero-sigma
        # geometry query. Preserve the same cumulative timeout and fail closed.
        if pose is None or not all(math.isfinite(float(v)) for v in
                (pose.x, pose.y, pose.yaw, pose.std_xy, pose.std_yaw)):
            return self._wait(now)
        if guard.transition_clear(current, target, pose, loaded=loaded):
            return 'clear'
        profile = self.loaded_profile if loaded else GATE_UNLOADED
        # The zero-sigma query ONLY decides whether to wait, never whether to issue motion.
        nominal = OwnPose(pose.x, pose.y, pose.yaw, 0., 0.)
        uncertain = pose.std_xy > profile.low_xy_m or pose.std_yaw > profile.low_yaw_rad
        if uncertain or guard.transition_clear(current, target, nominal, loaded=loaded):
            return self._wait(now)
        return 'blocked'


def reachable_pan(guard, current, candidates, pose, *, loaded):
    """Revalidate a stale queue using the unchanged full-path check; no unchecked current-pan fallback."""
    for pan in dict.fromkeys([*candidates, int(current[6])]):
        if guard.transition_clear(current, {6: pan}, pose, loaded=loaded):
            return int(pan)
    return None
