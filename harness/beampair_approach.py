"""Opt-in approach repair, using the pinned teacher's checked paths/perception.

The route reference uses arc progress (Nav2 path pruning / pure pursuit), not
decreasing straight-line goal error during a necessary detour. Reobserve named
stale blockers before retrying, as in Nav2 mark/clear recovery; never delete an
obstacle on expiry. See experiments/2026-10-15-beampair4/README.md.
"""
from copy import deepcopy

MODE = 'beampair_approach_v1'
BOUNDED_MODE = 'beampair_approach_v2'


class CheckedArc:
    """Signed displacement projected on this tick's route, in one own frame.

    A replanned path cannot itself earn progress: both successive poses are
    projected on the same path. Subtract reversals before comparing the best
    cumulative arc, so oscillation earns no new credit.
    """
    def __init__(self):
        self.previous = None
        self.arc = self.best = 0.

    def advance(self, pose, path, minimum, project):
        progressed = False
        if self.previous is not None and len(path) >= 2:
            self.arc += project(pose[:2], path)[2] - project(self.previous, path)[2]
            if self.arc-self.best > minimum:
                self.best = self.arc
                progressed = True
        self.previous = tuple(pose[:2])
        return progressed


def stale_blockers(teacher, world):
    """First failed candidate checks identify actual stale blocking landmarks."""
    obs = world['visibility'][teacher.rid].get('observations', {})
    evidence = {}
    # These are the checks that rejected the current search, not a second
    # collision model. Include a stale 'current_geometry' wall too: its mean
    # can be wrong even when its uncertainty label is not memory_margin.
    logs = teacher.goal_set_log[-1:]
    for event in logs:
        for c in event.get('candidates', []):
            ds = c.get('failure_audit') or [d for d in c.get('collision_audit', []) if d.get('blocked')]
            for d in ds:
                key = d.get('id', d.get('object'))
                m = obs.get(key)
                if (m is not None and m['kind'] in ('wall', 'cargo') and key != 'beam_1'
                        and m['seen_t'] < world['t']-1e-8):
                    evidence.setdefault(key, dict(measurement=deepcopy(m), check=deepcopy(d)))
    return evidence


class ApproachRepairMixin:
    def _route(self, world, goal, heading, now):
        if self.approach_repair == 'off' or self.search19_body_active:
            return super()._route(world, goal, heading, now)
        from sim.grasp_act_search21 import route_progress, route_projection
        original = self.progress.observe_goal
        def observe(pose, target, yaw, at):
            if len(self.path) < 2:
                return original(pose, target, yaw, at)
            if self.approach_repair == BOUNDED_MODE:
                tracker = getattr(self, '_approach_checked_arc', None)
                if tracker is None:
                    tracker = self._approach_checked_arc = CheckedArc()
                event = original(pose, target, yaw, at)
                if tracker.advance(pose, self.path, self.progress.required_movement_m, route_projection):
                    self.progress.since = at
                    self.progress.retried = False
                    return None
                # Preserve original visible goal/heading improvements through
                # search and replans. R1 lost this credit on a stale fixed path
                # and falsely handed r2 off at14.4 SIMs; no time limit changed.
                return event
            # Reuse the existing 1 cm / 3 SIMs monotone checked-route observer;
            # no new acceptance/timing constant. Original 8318620 advanced
            # 0.340193 m on its fixed path while goal error grew 0.2397->0.4775m.
            return route_progress(self, world, target, yaw, at)
        self.progress.observe_goal = observe
        before = len(getattr(self, 'progress_log', []))
        try:
            return super()._route(world, goal, heading, now)
        finally:
            self.progress.observe_goal = original
            for row in getattr(self, 'progress_log', [])[before:]:
                row.update(reason_category=row['reason'],blocked_object='none:progress_window',
                           min_gap_m=None,gap_scope='not_geometric; visible_goal_heading_and_checked_arc')

    def _plan_approach(self, world, now):
        valid = super()._plan_approach(world, now)
        if (self.approach_repair == 'off' or valid or self.outcome is not None
                or self.reobserver.active is not None or world['beam'] is None
                or world['visibility'][self.rid]['visible_probes'] < 5):
            return valid
        evidence = stale_blockers(self, world)
        if evidence and self.reobserver.begin('obstacle',
                {k:v['measurement'] for k,v in evidence.items()}, world, self, now):
            # Use the existing MAX_ENCOUNTERS=2 and LIMIT_S=2.8; this finite
            # perception action replaces a competing generic empty-set fan.
            # No success, clearance, obstacle expiry or timer extension is
            # inferred from looking. Every retry must pass the original checks.
            self.search21_recovery = None
            self.approach_blocked_since = None
            for key, v in evidence.items():
                self.approach_repair_log.append(dict(t=now, event='stale_blocker_reobserve',
                    reason_category='stale_blocker_requires_fresh_measurement',
                    blocked_object=key, min_gap_m=v['check'].get('gap_m'),
                    margin_m=v['check'].get('margin_m'),
                    gap_scope='original_candidate_check', seen_t=v['measurement']['seen_t']))
        return valid

    def diagnostic(self):
        d = super().diagnostic()
        d.update(approach_repair=self.approach_repair, approach_repair_log=self.approach_repair_log)
        return d
