"""Stationary recovery for a rejected own-camera sweep (no simulator input).

An initial PF estimate can be initialized but still too broad to certify any pan near the
spawn's west wall. Keep all collision margins, hold the issued posture, and let passive own
frames refine the estimate. Ten SIM seconds bounds the *cumulative* waiting per sweep; a
briefly clear path or a different target never replenishes it. This is not permission to move
through an inflated obstacle, nor a claim that a blocked estimate means physical contact.
"""
from __future__ import annotations

from harness.zone_own_guards import GATE_LOADED, GATE_UNLOADED, OwnPose

SWEEP_REOBSERVE_S = 10.


class SweepRecheck:
    def __init__(self):
        self.waited_s = 0.
        self.last_wait = None

    def check(self, now, guard, current, target, pose, *, loaded):
        if self.last_wait is not None:
            self.waited_s += max(0., now - self.last_wait)
            self.last_wait = None
        if guard.transition_clear(current, target, pose, loaded=loaded):
            return 'clear'
        profile = GATE_LOADED if loaded else GATE_UNLOADED
        # The zero-sigma query ONLY decides whether to wait, never whether to issue motion.
        nominal = OwnPose(pose.x, pose.y, pose.yaw, 0., 0.)
        uncertain = pose.std_xy > profile.low_xy_m or pose.std_yaw > profile.low_yaw_rad
        if self.waited_s < SWEEP_REOBSERVE_S - 1e-9 and (uncertain or
                guard.transition_clear(current, target, nominal, loaded=loaded)):
            self.last_wait = now
            return 'wait'
        return 'blocked'


def reachable_pan(guard, current, candidates, pose, *, loaded):
    """Revalidate a stale queue using the unchanged full-path check; no unchecked current-pan fallback."""
    for pan in dict.fromkeys([*candidates, int(current[6])]):
        if guard.transition_clear(current, {6: pan}, pose, loaded=loaded):
            return int(pan)
    return None
