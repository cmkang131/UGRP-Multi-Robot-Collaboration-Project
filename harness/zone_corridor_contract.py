"""T10a: static corridor/bay checks and door-only runtime refusal, no traffic policy.

Inputs are an authored map, catalogue kinds, caller-selected role assignments
and proposed poses (metres/radians). No scenario, setup inventory, event,
referee, or P09 feasibility route is read. The caller must not supply GT poses.
Paths use straight translation and shortest yaw interpolation per segment.
All results concern conservative 2-D v3 envelopes, not contact/grasp success.
"""
from __future__ import annotations

import hashlib
import json
import math
from dataclasses import dataclass

from harness import static_keepouts as ko
from harness.zone_team_footprint import transform
from harness.zone_team_footprint_v3 import team_footprint

SCHEMA = 'ugrp.corridor_bay_static.v1'
ROBOTS = frozenset(('r1', 'r2', 'r3'))
STEP_M = .01
STEP_RAD = math.radians(1)


class UnsupportedCorridor(ValueError):
    """Explicit refusal, including legacy door-only executor construction."""


def require_door_runtime(static_map):
    """Refuse unsupported geometry; passing this check grants no run approval."""
    if not any(p.get('kind') == 'door' for p in static_map.get('passages', ())):
        raise UnsupportedCorridor('CORRIDOR_RUNTIME_UNSUPPORTED: T10b required')


def create_own_executor(robot_id, static_map, *args, **kwargs):
    """Safe opt-in factory; corridor runtime remains T10b's responsibility.

    Preserve the sealed legacy module byte-for-byte. In particular, never
    fabricate a door at the corridor centre to satisfy its door checkpoint.
    """
    require_door_runtime(static_map)
    from harness.zone_own_executor import ZoneOwnExecutor
    return ZoneOwnExecutor(robot_id, static_map, *args, **kwargs)


def _numbers(values, count):
    if len(values) != count or any(isinstance(v, bool) or not isinstance(v, (int, float))
                                   or not math.isfinite(v) for v in values):
        raise ValueError(f'expected {count} finite numbers')
    return tuple(float(v) for v in values)


def _rect(row):
    cx, cy = _numbers(row['center_m'], 2)
    hx, hy = _numbers(row['half_extents_m'], 2)
    yaw, = _numbers([row.get('yaw_rad', 0.)], 1)
    if min(hx, hy) <= 0:
        raise ValueError('rectangle extents must be positive')
    return cx, cy, hx, hy, yaw


def _result(ok=None, reason='not_requested', **extra):
    return {'status': 'unsupported' if ok is None else 'pass' if ok else 'blocked',
            'static_ok': ok, 'reason': reason, **extra}


@dataclass(frozen=True)
class Formation:
    kind: str
    assignment: tuple
    parts: tuple
    item_parts: tuple
    margin_m: float

    @property
    def robots(self):
        return tuple(robot for _, robot in self.assignment)

    def record(self):
        # Role choice is separate from geometry/controller identity.
        return {'kind': self.kind, 'role_assignment': dict(self.assignment),
                'robot_model': 'masterpi_v3', 'margin_m': self.margin_m,
                'envelope_status': 'conservative_static_not_physical_validation'}


class CorridorContract:
    def __init__(self, static_map, *, robot_model=None, corridor_id='corridor_1', bay_id='bay_1', clearance_m=.01):
        self.clearance, = _numbers([clearance_m], 1)
        if self.clearance < 0:
            raise ValueError('clearance must be nonnegative')
        self.bounds = _numbers(static_map['bounds_m'], 4)
        if self.bounds[0] >= self.bounds[1] or self.bounds[2] >= self.bounds[3]:
            raise ValueError('invalid map bounds')
        # No model fallback: missing v3 geometry must stay unsupported.
        selected_model = static_map.get('robot_model', robot_model)
        if selected_model != 'masterpi_v3' or robot_model not in (None, selected_model):
            raise UnsupportedCorridor('MASTERPI_V3_REQUIRED')
        if static_map.get('terrain'):
            raise UnsupportedCorridor('TERRAIN_TRAVERSAL_UNSUPPORTED')
        passages = static_map.get('passages', ())
        ids = [p['id'] for p in passages]
        if len(ids) != len(set(ids)):
            raise ValueError('duplicate passage id')
        corridor = next((p for p in passages if p['id'] == corridor_id), None)
        bay = next((p for p in passages if p['id'] == bay_id), None)
        if corridor is None or corridor.get('kind') != 'corridor':
            raise UnsupportedCorridor('CORRIDOR_NOT_FOUND')
        if corridor.get('axis') != 'x':
            raise UnsupportedCorridor('ONLY_EAST_WEST_CORRIDOR_SUPPORTED')
        if bay is not None and (bay.get('kind') != 'passing_bay' or bay.get('opens_to') != corridor_id):
            raise ValueError('bay must open to selected corridor')
        self.corridor = _rect(corridor)
        self.bay = None if bay is None else _rect(bay)
        if self.corridor[4] or (self.bay is not None and self.bay[4]):
            raise UnsupportedCorridor('ROTATED_PASSAGE_UNSUPPORTED')
        width, = _numbers([corridor['width_m']], 1)
        if not math.isclose(width, 2 * self.corridor[3], abs_tol=1e-9):
            raise ValueError('corridor width disagrees with extents')
        self.walls = tuple(_rect(o) for o in static_map.get('obstacles', ()))
        self.corridor_id, self.bay_id = corridor_id, bay_id
        public = {'bounds': self.bounds, 'walls': self.walls, 'corridor': self.corridor,
                  'bay': self.bay, 'robot_model': 'masterpi_v3', 'clearance_m': self.clearance}
        self.geometry_sha256 = hashlib.sha256(json.dumps(public, sort_keys=True).encode()).hexdigest()

    def formation(self, kind, role_assignment, *, margin_m=.03):
        margin, = _numbers([margin_m], 1)
        if margin < 0:
            raise ValueError('margin must be nonnegative')
        fp = team_footprint({'robot_model': 'masterpi_v3'}, kind, margin=margin)
        if set(role_assignment) != set(fp.roles):
            raise ValueError('all catalogue carrier roles are required')
        assignment = tuple(sorted(role_assignment.items()))
        robots = tuple(role_assignment.values())
        if len(robots) != len(set(robots)) or not set(robots) <= ROBOTS:
            raise ValueError('role assignment requires distinct r1/r2/r3')
        freeze = lambda parts: tuple(tuple(tuple(v) for v in p) for p in parts)
        return Formation(kind, assignment, freeze(fp.parts), freeze(fp.item_parts), margin)

    def _clear(self, pose, parts, pad=0.):
        return all(ko.pose_clear(pose, list(p), self.walls, bounds=self.bounds,
                                 margin=self.clearance + pad) for p in parts)

    def _samples(self, path, parts):
        """Inflate samples enough to cover every intervening point, including yaw.

        Each point moves at most translation + radius * abs(yaw) per segment.
        Half that bound to the nearest sample is covered by an axis-aligned
        wall/boundary inflation. This is conservative, not endpoint-only QA.
        """
        radius = max(math.hypot(x, y) for p in parts for x, y in p)
        if len(path) == 1:
            yield path[0], 0.
        for a, b in zip(path, path[1:]):
            delta = (b[2] - a[2] + math.pi) % (2 * math.pi) - math.pi
            distance = math.dist(a[:2], b[:2])
            n = max(1, math.ceil(distance / STEP_M), math.ceil(abs(delta) / STEP_RAD))
            pad = (distance + radius * abs(delta)) / (2 * n)
            # Oriented obstacle inflation needs sqrt(2) for arbitrary local axes.
            pad *= math.sqrt(2)
            for i in range(n + 1):
                t = i / n
                yield (a[0] + (b[0] - a[0]) * t, a[1] + (b[1] - a[1]) * t,
                       a[2] + delta * t), pad

    def _path(self, path, parts):
        if path is None:
            return None
        poses = tuple(_numbers(p, 3) for p in path)
        if len(poses) < 2:
            raise ValueError('path requires at least two poses')
        return poses

    def _sweep(self, path, parts):
        return all(self._clear(p, parts, pad) for p, pad in self._samples(path, parts))

    def _lane_sweep(self, path, parts):
        cx, cy, hx, hy, _ = self.corridor
        for pose, pad in self._samples(path, parts):
            lo, hi, bottom, top = self._extent(pose, parts)
            if hi + pad >= cx - hx and lo - pad <= cx + hx:
                if bottom - pad < cy - hy + self.clearance or top + pad > cy + hy - self.clearance:
                    return False
        return self._sweep(path, parts)

    def _extent(self, pose, parts):
        points = [v for p in parts for v in transform(p, pose)]
        return min(x for x, _ in points), max(x for x, _ in points), \
            min(y for _, y in points), max(y for _, y in points)

    def _corridor_pose(self, pose, parts):
        lo, hi, bottom, top = self._extent(pose, parts)
        cx, cy, hx, hy, _ = self.corridor
        return (cx - hx <= lo <= hi <= cx + hx
                and cy - hy + self.clearance <= bottom <= top <= cy + hy - self.clearance)

    def passage_path(self, formation, path, direction):
        if direction not in ('west_to_east', 'east_to_west'):
            raise ValueError('unknown direction')
        path = self._path(path, formation.parts)
        if path is None:
            return _result(reason='pose_path_not_supplied', direction=direction)
        start, end = self._extent(path[0], formation.parts), self._extent(path[-1], formation.parts)
        cx, cy, hx, hy, _ = self.corridor
        west, east = (start, end) if direction == 'west_to_east' else (end, start)
        crossed = west[1] < cx - hx and east[0] > cx + hx
        # A route around the passage, or a mouth visit, is not a crossing.
        for face in (cx - hx, cx, cx + hx):
            hits = []
            for a, b in zip(path, path[1:]):
                if a[0] != b[0] and min(a[0], b[0]) <= face <= max(a[0], b[0]):
                    t = (face - a[0]) / (b[0] - a[0])
                    hits.append(cy - hy <= a[1] + t * (b[1] - a[1]) <= cy + hy)
            crossed = crossed and any(hits)
        swept = self._lane_sweep(path, formation.parts)
        return _result(crossed and swept, 'full_formation_crossing' if crossed and swept
                       else 'not_full_crossing' if not crossed else 'formation_sweep_blocked',
                       direction=direction, swept_clear=swept, full_crossing=crossed,
                       path_m_rad=path)

    def bay_stop(self, formation, pose):
        if self.bay is None or pose is None:
            return _result(reason='bay_or_stop_pose_not_supplied')
        pose = _numbers(pose, 3)
        lo, hi, bottom, top = self._extent(pose, formation.parts)
        cx, cy, hx, hy, _ = self.bay
        gap = min(lo - (cx - hx), cx + hx - hi, bottom - (cy - hy), cy + hy - top)
        clear = self._clear(pose, formation.parts)
        ok = gap >= self.clearance and clear
        return _result(ok, 'whole_formation_inside_bay' if ok else 'bay_extent_or_wall_blocked',
                       boundary_gap_m=gap, required_clearance_m=self.clearance,
                       width_m=top - bottom, length_m=hi - lo)

    def bay_motion(self, formation, path, stop_pose, *, reentry=False):
        path = self._path(path, formation.parts)
        if self.bay is None or stop_pose is None or path is None:
            return _result(reason='bay_motion_not_supplied')
        stop_pose = _numbers(stop_pose, 3)
        bay_end, corridor_end = (path[0], path[-1]) if reentry else (path[-1], path[0])
        # Exact linkage prevents separately valid but disconnected certificates.
        linked = bay_end == stop_pose and self._corridor_pose(corridor_end, formation.parts)
        stop = self.bay_stop(formation, stop_pose)['static_ok']
        sweep = self._sweep(path, formation.parts)
        return _result(linked and stop and sweep,
                       'bay_motion_clear' if linked and stop and sweep else 'bay_motion_blocked',
                       endpoint_linked=linked, swept_clear=sweep, path_m_rad=path)

    def bay_rotation(self, formation, path):
        path = self._path(path, formation.parts)
        if self.bay is None or path is None:
            return _result(reason='bay_rotation_not_supplied')
        if any(p[:2] != path[0][:2] for p in path):
            return _result(reason='only_fixed_centre_rotation_supported')
        if all(math.isclose((p[2] - path[0][2]) % (2 * math.pi), 0., abs_tol=1e-12) for p in path):
            return _result(reason='rotation_not_requested')
        cx, cy, hx, hy, _ = self.bay
        for pose, pad in self._samples(path, formation.parts):
            lo, hi, bottom, top = self._extent(pose, formation.parts)
            gap = min(lo - (cx - hx), cx + hx - hi, bottom - (cy - hy), cy + hy - top)
            if gap < self.clearance + pad or not self._clear(pose, formation.parts, pad):
                return _result(False, 'bay_rotation_extent_or_wall_blocked')
        return _result(True, 'whole_formation_bay_rotation')

    def item_rotation(self, formation, path):
        path = self._path(path, formation.item_parts)
        if path is None:
            return _result(reason='rotation_not_supplied')
        if any(p[:2] != path[0][:2] for p in path):
            return _result(reason='only_fixed_centre_rotation_supported')
        if all(math.isclose((p[2] - path[0][2]) % (2 * math.pi), 0., abs_tol=1e-12) for p in path):
            return _result(reason='rotation_not_requested')
        return _result(self._sweep(path, formation.item_parts), 'item_only_rotation_sweep',
                       formation_swept_clear=self._sweep(path, formation.parts), path_m_rad=path)

    def simultaneous_occupancy(self, placements):
        """Static joint poses only. No partner/yielder selection or timing policy."""
        if not placements:
            return _result(reason='joint_poses_not_supplied', simultaneous_passing='unsupported')
        robots = [r for f, _ in placements for r in f.robots]
        if len(robots) > 3:
            return _result(reason='TEAM_SIZE_EXCEEDED: two pairs require four robots',
                           robot_count=len(robots), simultaneous_passing='unsupported')
        if len(set(robots)) != len(robots):
            return _result(reason='ROBOT_ASSIGNED_TWICE', simultaneous_passing='unsupported')
        posed = [(f, _numbers(p, 3)) for f, p in placements]
        clear = all(self._clear(p, f.parts) for f, p in posed)
        polys = [[transform(part, p) for part in f.parts] for f, p in posed]
        overlap = any(ko.polygons_overlap(a, b) for i, group in enumerate(polys)
                      for other in polys[i + 1:] for a in group for b in other)
        return _result(clear and not overlap, 'joint_static_poses_only', robot_count=len(robots),
                       simultaneous_passing='unsupported')

    def check(self, formation, *, forward_path=None, reverse_path=None, bay_pose=None,
              evacuation_path=None, reentry_path=None, rotation_path=None, bay_rotation_path=None,
              placements=(), disc_radius_m=.17):
        radius, = _numbers([disc_radius_m], 1)
        if radius <= 0:
            raise ValueError('disc radius must be positive')
        cx, cy, hx, _, _ = self.corridor
        disc = (tuple(ko.disc_footprint(radius)),)
        disc_path = ((cx - hx - radius - self.clearance - .01, cy, 0.),
                     (cx + hx + radius + self.clearance + .01, cy, 0.))
        return {'schema': SCHEMA, 'geometry_sha256': self.geometry_sha256,
                'formation': formation.record(), 'runtime_support': 'unsupported_T10b_required',
                'disc_passage': _result(self._lane_sweep(disc_path, disc), 'disc_only_centreline', radius_m=radius),
                'item_rotation': self.item_rotation(formation, rotation_path),
                'pose_paths': {'west_to_east': self.passage_path(formation, forward_path, 'west_to_east'),
                               'east_to_west': self.passage_path(formation, reverse_path, 'east_to_west')},
                'bay': {'stop': self.bay_stop(formation, bay_pose),
                        'evacuation': self.bay_motion(formation, evacuation_path, bay_pose),
                        'reentry': self.bay_motion(formation, reentry_path, bay_pose, reentry=True),
                        'rotation': self.bay_rotation(formation, bay_rotation_path)},
                'simultaneous_occupancy': self.simultaneous_occupancy(placements),
                'physics_verified': False, 'sim_cap_s': 0}
