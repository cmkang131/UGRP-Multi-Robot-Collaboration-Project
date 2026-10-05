"""v98-only evidence log for ``PAIR_COLLISION_GUARD``: which command was blocked and which guard term blocked it.

Probe 3358372e (raise_high): r1 ended at 8.7 s with ``job_failed {reason: PAIR_COLLISION_GUARD}`` and nothing else.
The pair events of the record (``pair[0].robots.<rid>.events``) were empty, so the blocked command, the pose and
covariance the guard used and the term that failed (chassis or arm, which wall, how many mm, which margin terms)
could only be recovered by replaying the run offline.

This module only OBSERVES. ``RecordingGeometry`` is ``zone_final_pair_guards.PairGeometry`` whose five query
methods call ``super()`` and return its answer unchanged; they additionally remember, per ``check``, the first and
the worst negative chassis/arm clearance. ``zone_pair_highpose_runtime.CommandGuard`` installs it (class swap on the
geometry that ``sweep_guard()`` just built) and, when the check ended in ``PAIR_COLLISION_GUARD``, appends one event
``pair_collision_guard_veto`` to the pair events. Decisions, command lists, margins and floats are those of the
frozen guard (tests compare them bit for bit). Nothing but the robot's own pose estimate, own issued commands and the
static map enters the log: no peer pose, no measured joint, no world state.

Shared ``zone_pair_geometry``, ``zone_own_guards`` and ``zone_final_pair_guards`` stay byte-identical.
"""
from __future__ import annotations

import math
from typing import NamedTuple

import numpy as np

from harness import zone_own_guards as g
from harness.zone_final_pair_guards import PairGeometry
from harness.zone_own_guards import _rect_distance, body_spheres

ID = 'v98_pair_collision_guard_veto_log_v1'
EVENT = 'pair_collision_guard_veto'
TOLERANCE = 1e-12


def record() -> dict:
    return {'id': ID, 'event': EVENT, 'observation_only': True, 'decisions_changed': False,
            'shared_sources_modified': False,
            'fields': ['commands', 'start_pose', 'covariance', 'servo', 'site', 'first_negative', 'minimum']}


class Trace:
    """What the guard evaluated during ONE ``CommandGuard.check`` call (shared by every geometry built in it)."""

    def __init__(self):
        self.calls = 0
        self.origin = None                     # pose of the first clearance query (the unmoved pose)
        self.first = None                      # first negative query
        self.worst = None                      # most negative query
        self.sites = []                        # open 'motion_clear' | 'plan' | 'transition_clear' queries, outermost first
        self.failed_sites = []                 # sites that answered 'not clear' (inner before outer)
        self.plan_result = None
        self.reliefs = []                      # start-state relief admissions (zone_pair_highpose_start_relief)
        self.relief_refusal = None             # the last start-state relief that was refused, with its reason
        self.relief_notes = []                 # relief internal failures (the guard then keeps its old answer)

    def checkpoint(self):
        return (self.calls, self.origin, self.first, self.worst, len(self.failed_sites), self.plan_result)

    def rollback(self, point):
        """Forget the queries made since ``checkpoint`` (a command that start-state relief admitted)."""
        self.calls, self.origin, self.first, self.worst, failed, self.plan_result = point
        del self.failed_sites[failed:]

    def note(self, geo, kind, clearance, wall, servo, pose, loaded):
        index, self.calls = self.calls, self.calls + 1
        if self.origin is None:
            self.origin = pose
        if not clearance < 0.:
            return
        entry = {'kind': kind, 'index': index, 'clearance_m': clearance, 'wall_id': wall, 'pose': pose,
                 'servo': None if servo is None else dict(servo), 'loaded': bool(loaded), 'geo': geo,
                 'residual_seen': geo.residual, 'loaded_motion': geo._loaded_motion,
                 'site': '>'.join(self.sites) or None}
        if self.first is None:
            self.first = entry
        if self.worst is None or clearance < self.worst['clearance_m']:
            self.worst = entry


class RecordingGeometry(PairGeometry):
    """``PairGeometry`` that answers exactly like it and remembers negative clearances in ``self.trace``."""
    trace = None
    residual0 = None

    def chassis_clearance(self, pose):
        out = super().chassis_clearance(pose)
        self.trace.note(self, 'chassis', out[0], out[1], None, pose, False)
        return out

    def arm_clearance(self, servo, pose, *, loaded):
        out = super().arm_clearance(servo, pose, loaded=loaded)
        self.trace.note(self, 'arm', out[0], out[1], servo, pose, loaded)
        return out

    def _site(self, name, call, *args, **kwargs):
        self.trace.sites.append(name)
        try:
            out = call(*args, **kwargs)
        finally:
            self.trace.sites.pop()
        if out is False:
            self.trace.failed_sites.append(name)
        return out

    def motion_clear(self, servo, pose, cmd, *, loaded):
        return self._site('motion_clear', super().motion_clear, servo, pose, cmd, loaded=loaded)

    def transition_clear(self, current, target, pose, *, loaded):
        return self._site('transition_clear', super().transition_clear, current, target, pose, loaded=loaded)

    def plan(self, *args, **kwargs):
        out = self._site('plan', super().plan, *args, **kwargs)
        self.trace.plan_result = {'reason': out.get('reason'), 'transition_clear': out.get('transition_clear')}
        if out.get('reason') != 'clear' or not out.get('transition_clear', False):
            self.trace.failed_sites.append('plan')
        return out


def recording(geo, trace, cls=RecordingGeometry):
    """Install the recorder on a freshly built geometry; anything but the exact ``PairGeometry`` is left alone."""
    if trace is None or type(geo) is not PairGeometry:
        return geo
    geo.__class__ = cls
    geo.trace, geo.residual0 = trace, geo.residual
    return geo


def _mm(value):
    return None if value is None else float(value) * 1000.


def _terms(geo, pose, lever):
    """The four margin terms in force at a pose (``zone_final_pair_guards.margin``), plus the margin geo returns."""
    base, residual = g.BASE_MARGIN_M, geo.residual
    sxy, syaw = min(pose.std_xy, g.SIGMA_CAP_XY_M), min(pose.std_yaw, g.SIGMA_CAP_YAW_RAD) * lever
    total = geo.margin(pose, lever)
    return {'base_mm': _mm(base), 'residual_mm': _mm(geo.residual0), 'motion_pad_mm': _mm(residual - geo.residual0), 'sigma_xy_mm': _mm(sxy), 'sigma_yaw_lever_mm': _mm(syaw),
            'lever_m': float(lever), 'total_mm': _mm(total),
            'sum_matches': abs(base + residual + sxy + syaw - total) <= TOLERANCE}


class Pair(NamedTuple):
    """One body-point/obstacle pair of the guard, exactly as ``chassis_clearance``/``arm_clearance`` evaluate it."""
    kind: str            # 'chassis' | 'body' | 'beam'
    index: int           # chassis point or sphere index
    wall: str
    clearance: float     # distance - radius - margin: the number the guard compares with 0
    raw: float           # distance to the wall box minus the sphere radius (0 inside the box: _rect_distance clamps)
    signed: float        # the same, but -depth for a centre inside the box (a pair the clamp cannot tell apart)
    lever: float
    geom: tuple          # (base x, base y, base z or None, radius, world x, world y)


def _depth(box, x, y):
    """Distance from a point inside a wall box to its nearest face (>= 0 inside, < 0 outside)."""
    (cx, cy), (hx, hy) = box['center'], box['half']
    dx, dy = x - cx, y - cy
    c, s = (math.cos(box['yaw']), math.sin(box['yaw'])) if box['yaw'] else (1., 0.)
    lx, ly = c * dx + s * dy, -s * dx + c * dy
    return min(hx - abs(lx), hy - abs(ly))


def _signed(box, x, y, raw):
    return raw if raw > 0. else -max(_depth(box, x, y), 0.)


def chassis_pairs(geo, pose):
    """Every chassis point against every wall: the very sum ``SweepGuard.chassis_clearance`` minimises."""
    (x0, x1), hy = g.CHASSIS_X_M, g.CHASSIS_Y_M
    pts = [(x, y) for x in np.linspace(x0, x1, 6) for y in (-hy, hy)] + [(x, y) for x in (x0, x1)
                                                                       for y in np.linspace(-hy, hy, 5)]
    out, c, s = [], math.cos(pose.yaw), math.sin(pose.yaw)
    for index, (bx, by) in enumerate(pts):
        mx, my = pose.x + c * bx - s * by, pose.y + s * bx + c * by
        lever = math.hypot(bx, by)
        margin = geo.margin(pose, lever)
        for box in geo.boxes:
            raw = _rect_distance(box, mx, my)
            out.append(Pair('chassis', index, box['id'], raw - margin, raw, _signed(box, mx, my, raw), lever,
                            (float(bx), float(by), None, 0., float(mx), float(my))))
    return out


def arm_pairs(geo, servo, pose, loaded):
    """Every body sphere (and, loaded, every bar sphere) against every wall it is not above: ``arm_clearance``."""
    out, c, s = [], math.cos(pose.yaw), math.sin(pose.yaw)
    groups = [('body', body_spheres(servo, loaded=False, mount_xyz_m=geo.mount), 0.)]
    if loaded:
        groups.append(('beam', geo.beam_spheres(servo), 1.))
    for part, spheres, with_radius in groups:
        for index, (bx, by, bz, r) in enumerate(spheres):
            mx, my = pose.x + c * bx - s * by, pose.y + s * bx + c * by
            lever = math.hypot(bx, by) + r * with_radius
            margin = geo.margin(pose, lever)
            for box in geo.boxes:
                if bz - r >= box['height'] + margin:
                    continue                                    # passes over this wall
                raw = _rect_distance(box, mx, my)
                out.append(Pair(part, index, box['id'], raw - r - margin, raw - r, _signed(box, mx, my, raw) - r,
                                lever, (float(bx), float(by), float(bz), float(r), float(mx), float(my))))
    return out


def _limit(pairs):
    """The pair the guard's strict ``<`` scan ends on (first of equal values), or (inf, None)."""
    best, hit = math.inf, None
    for pair in pairs:
        if pair.clearance < best:
            best, hit = pair.clearance, pair
    return best, hit


def _hit(pair):
    bx, by, bz, r, mx, my = pair.geom
    out = {'wall_id': pair.wall, 'raw': pair.raw, 'lever': pair.lever, 'point_world_m': [mx, my]}
    if pair.kind == 'chassis':
        out['point_base_m'] = [bx, by]
    else:
        out.update(part=pair.kind, sphere_index=pair.index, sphere_radius_m=r, sphere_center_base_m=[bx, by, bz])
    return out


def _chassis_limit(geo, pose):
    best, pair = _limit(chassis_pairs(geo, pose))
    return best, None if pair is None else _hit(pair)


def _arm_limit(geo, servo, pose, loaded):
    best, pair = _limit(arm_pairs(geo, servo, pose, loaded))
    return best, None if pair is None else _hit(pair)


def _describe(entry, origin):
    geo, pose = entry['geo'], entry['pose']
    saved = geo.residual, geo._loaded_motion
    geo.residual, geo._loaded_motion = entry['residual_seen'], entry['loaded_motion']
    try:
        if entry['kind'] == 'chassis':
            value, hit = _chassis_limit(geo, pose)
        else:
            value, hit = _arm_limit(geo, entry['servo'], pose, entry['loaded'])
        terms = None if hit is None else _terms(geo, pose, hit['lever'])
    finally:
        geo.residual, geo._loaded_motion = saved
    moved = None if origin is None else math.hypot(pose.x - origin.x, pose.y - origin.y)
    out = {'term': entry['kind'], 'query_index': entry['index'], 'site': entry['site'],
           'clearance_mm': _mm(entry['clearance_m']), 'wall_id': entry['wall_id'],
           'pose': {'x_m': pose.x, 'y_m': pose.y, 'yaw_rad': pose.yaw, 'std_xy_m': pose.std_xy,
                    'std_yaw_rad': pose.std_yaw},
           'moved_from_start_mm': _mm(moved),
           'yaw_offset_rad': None if origin is None else pose.yaw - origin.yaw,
           'mirror_matches': abs(value - entry['clearance_m']) <= TOLERANCE, 'margin_terms': terms}
    if hit is not None:
        out.update(raw_mm=_mm(hit['raw']), **{k: v for k, v in hit.items() if k not in ('raw', 'lever', 'wall_id')})
    if entry['kind'] == 'arm':
        out['servo_pwm'] = {str(k): v for k, v in sorted(entry['servo'].items())}
        out['loaded'] = entry['loaded']
    return out


def _report(report):
    if report is None:
        return None
    cov = getattr(report, 'cov', None)
    out = {k: getattr(report, k, None) for k in ('x_m', 'y_m', 'yaw_rad', 'std_xy_m', 'std_yaw_rad', 'fix_age_s', 't_est')}
    out['cov'] = None if cov is None else [[float(v) for v in row] for row in cov]
    return out


def log_veto(guard, now, commands, events_before, trace):
    """Append the veto event when this check ended the job with PAIR_COLLISION_GUARD. Never raises into the run."""
    own = guard.ep.own
    try:
        failed = [e for e in own.events[events_before:] if e.get('event') == 'job_failed'
                  and e.get('detail', {}).get('reason') == 'PAIR_COLLISION_GUARD']
        if not failed:
            return None
        detail = {'log_id': ID, 'reason': 'PAIR_COLLISION_GUARD', 'commands': commands,
                  'estimate': _report(own.last_report), 'servo_pwm': {str(k): v for k, v in sorted(own.servo.items())},
                  'loaded': bool(guard.carrying_beam), 'approach': bool(guard.approach),
                  'queries': trace.calls, 'recorded': trace.origin is not None,
                  'site': (trace.first or {}).get('site') or (trace.failed_sites[-1] if trace.failed_sites else None),
                  'failed_sites': list(trace.failed_sites), 'plan': trace.plan_result,
                  'first_negative': None if trace.first is None else _describe(trace.first, trace.origin),
                  'start_relief': trace.relief_refusal, 'relief_notes': list(trace.relief_notes),
                  'minimum_is_first_negative': trace.worst is trace.first,
                  'minimum': None if trace.worst is None or trace.worst is trace.first
                  else _describe(trace.worst, trace.origin)}
        guard.ep.log(own.robot_id, EVENT, now, **detail)
        return detail
    except Exception as exc:                                  # evidence only: a log failure never changes the run
        guard.ep.log(own.robot_id, EVENT, now, log_id=ID, reason='PAIR_COLLISION_GUARD', log_error=repr(exc),
                     commands=commands)
        return None
