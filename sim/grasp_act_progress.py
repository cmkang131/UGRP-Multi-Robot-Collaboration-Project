"""Nav2-style positional progress timer and a bounded recovery retry.

Only the teacher's issued-command pose is accepted, never simulator state.
Replanning discards the cached route, not observed obstacles or safety margins.
"""
import math


class ApproachProgress:
    required_movement_m = .01
    allowance_s = 3.

    def __init__(self):
        self.reset()

    def reset(self):
        self.anchor = None
        self.since = None
        self.retried = False

    def observe(self, xy, now):
        if self.anchor is None or math.dist(xy, self.anchor) > self.required_movement_m:
            self.anchor = tuple(xy)
            self.since = now
            self.retried = False
            return None
        if now - self.since < self.allowance_s - 1e-8:
            return None
        if self.retried:
            return 'handoff'
        self.retried = True
        self.since = now
        return 'replan'
