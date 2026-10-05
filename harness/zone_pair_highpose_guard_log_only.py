"""v98-only: ``PAIR_COLLISION_GUARD`` as a LOG-ONLY check (user decision 2026-10-05 17:2x KST,
"걍 충돌 방지를 빼. 충돌 하면 다시 생각하면 되잖아").

With ``contract.COLLISION_GUARD_MODE == 'log_only'`` the guard geometry built inside ``CommandGuard.check`` answers
"clear" at the outermost ``motion_clear`` / ``transition_clear`` / ``plan`` query, so the check never sets
``PAIR_COLLISION_GUARD``. The real (frozen + start-relief) answer is still computed and, when it would have vetoed,
recorded in ``trace.would_veto`` (site, command, first negative clearance with margin terms) and logged as
``pair_collision_guard_log_only``. Nested queries (inside ``plan``) keep their real answers. Physics contact is
unchanged; every other guard (POSE_UNCERTAIN, GLOBAL_ENVELOPE_BLOCKED, PREGRASP_BEAM_UNSAFE, GO barrier, stops) is
unchanged. Geometry used outside ``check`` (planners) is unchanged. Frozen shared sources stay byte-identical.
"""
from __future__ import annotations

from harness import zone_pair_highpose_guardlog as log
from harness import zone_pair_highpose_start_relief as start_relief

ID = 'pair_collision_guard_log_only_v1'
EVENT = 'pair_collision_guard_log_only'
DECISION = 'user 2026-10-05 17:2x KST: "걍 충돌 방지를 빼. 충돌 하면 다시 생각하면 되잖아"'


def record() -> dict:
    return {'id': ID, 'event': EVENT, 'mode': 'log_only', 'decision': DECISION, 'blocks': False,
            'other_guards_changed': False, 'physics_contact_changed': False, 'shared_sources_modified': False}


class LogOnlyGeometry(start_relief.StartReliefGeometry):
    _depth = 0

    def _outer(self, name, call, args, kwargs, cleared, info):
        self._depth += 1
        try:
            out = call(*args, **kwargs)
        finally:
            self._depth -= 1
        if self._depth or cleared(out):
            return out
        row = {'site': name, **info}
        try:
            row['first_negative'] = (None if self.trace.first is None
                                     else log._describe(self.trace.first, self.trace.origin))
        except Exception as exc:
            row['first_negative'] = {'error': repr(exc)}
        row['failed_sites'] = list(self.trace.failed_sites)
        if self.trace.relief_refusal is not None:
            row['start_relief_refusal'] = self.trace.relief_refusal
        self.trace.would_veto = getattr(self.trace, 'would_veto', []) + [log_plain(row)]
        return True if name != 'plan' else {**out, 'reason': 'clear', 'transition_clear': True,
                                            'log_only_real_reason': out.get('reason'),
                                            'log_only_real_transition_clear': out.get('transition_clear')}

    def motion_clear(self, servo, pose, cmd, *, loaded):
        return self._outer('motion_clear', super().motion_clear, (servo, pose, cmd), {'loaded': loaded},
                           bool, {'command': dict(cmd), 'loaded': bool(loaded)})

    def transition_clear(self, current, target, pose, *, loaded):
        return self._outer('transition_clear', super().transition_clear, (current, target, pose), {'loaded': loaded},
                           bool, {'target': {str(k): v for k, v in dict(target).items()}, 'loaded': bool(loaded)})

    def plan(self, *args, **kwargs):
        return self._outer('plan', super().plan, args, kwargs,
                           lambda o: o.get('reason') == 'clear' and o.get('transition_clear', False),
                           {'loaded': bool(kwargs.get('loaded'))})


def log_plain(value):
    return start_relief._plain(value)


def install(geo, trace):
    return log.recording(geo, trace, LogOnlyGeometry)


def log_would_veto(guard, now, commands, trace):
    rows = getattr(trace, 'would_veto', None)
    if not rows:
        return None
    own = guard.ep.own
    try:
        guard.ep.log(own.robot_id, EVENT, now, log_id=ID, would_reason='PAIR_COLLISION_GUARD', commands=commands,
                     estimate=log._report(own.last_report), loaded=bool(guard.carrying_beam), would_veto=rows)
    except Exception as exc:
        guard.ep.log(own.robot_id, EVENT, now, log_id=ID, log_error=repr(exc))
    return rows
