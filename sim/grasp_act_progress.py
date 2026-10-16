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


class GoalProgress:
    """Goal-error window using the currently observed goal.

    Like Nav2's translation/rotation progress window, with monotone goal error
    instead of arbitrary displacement so oscillation is not credited. This
    remains an estimate, not measured physical progress. Peer motion may allow
    a bounded wait but cannot certify that this robot moved.
    """
    allowance_s = 3.
    required_movement_m = .01
    required_angle_rad = .05

    def __init__(self):
        self.reset()

    def reset(self):
        self.since = None
        self.best_distance = self.best_angle = None
        self.retried = False

    def observe_goal(self, pose, goal, heading, now):
        distance = math.dist(pose[:2], goal)
        angle = abs(math.atan2(math.sin(heading-pose[2]), math.cos(heading-pose[2])))
        if (self.since is None or self.best_distance-distance > self.required_movement_m
                or self.best_angle-angle > self.required_angle_rad):
            self.best_distance = distance if self.best_distance is None else min(self.best_distance, distance)
            self.best_angle = angle if self.best_angle is None else min(self.best_angle, angle)
            self.since = now
            self.retried = False
            return None
        if now-self.since < self.allowance_s-1e-8:
            return None
        if self.retried:
            return 'handoff'
        self.retried = True
        self.since = now
        return 'replan'
