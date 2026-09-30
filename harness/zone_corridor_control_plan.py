"""T10b actor-side plan admission. Static proposals are not measured poses.

This module deliberately has no scenario/inventory/P09 or runtime host input.
Existing T10a and sealed source files remain unchanged. Loaded cyan and beam
corridor legs are supported here; pickup, release, unloaded return and pair
pivoting require separate controllers.
"""
from __future__ import annotations

from dataclasses import asdict, dataclass
import hashlib
import json
import math

from harness.zone_corridor_contract import CorridorContract, UnsupportedCorridor, _numbers
from harness.zone_pair_status import MAX_SEGMENTS
from sim.zone_model_conventions import station_offset

PROFILE = 'corridor_own_rgb_control_v1'
MEMORY_PROFILE = 'corridor_issued_commands_v1'


def digest(value):
    return hashlib.sha256(json.dumps(value, sort_keys=True, separators=(',', ':'),
                                     allow_nan=False).encode()).hexdigest()


def angle(value):
    return (value + math.pi) % (2 * math.pi) - math.pi


@dataclass(frozen=True)
class Geometry:
    """Allowlisted static geometry passed to the observer, never the input dict."""
    bounds: tuple
    walls: tuple
    corridor: tuple
    bay: tuple | None
    robot_model: str = 'masterpi_v3'


@dataclass(frozen=True)
class ControlConfig:
    tick_s: float = .05
    frame_ttl_s: float = .15
    passage_timeout_s: float = 240.
    wait_timeout_s: float = 30.
    progress_timeout_s: float = 10.
    pair_start_timeout_s: float = 2.
    clear_hold_s: float = .3
    clear_frames: int = 3
    exit_frames: int = 3
    max_standoffs: int = 2
    position_tolerance_m: float = .012
    yaw_tolerance_rad: float = .015
    max_position_error_m: float = .015
    max_yaw_error_rad: float = .01
    speed_m_s: float = .035
    yaw_rate_rad_s: float = .10
    base_speed_m_s: float = .05
    progress_epsilon_m: float = .002

    def __post_init__(self):
        for key, value in asdict(self).items():
            if key in ('clear_frames', 'exit_frames', 'max_standoffs'):
                if type(value) is not int or value < 1:
                    raise ValueError('positive integer config required: ' + key)
            elif type(value) not in (float, int) or not math.isfinite(value) or value <= 0:
                raise ValueError('positive finite config required: ' + key)
        if self.tick_s > .05 or self.frame_ttl_s > .15:
            raise ValueError('motion lease/frame TTL exceeds fixed status safety cadence')
        if self.speed_m_s > .035 or self.yaw_rate_rad_s > .10 or self.base_speed_m_s > .05:
            raise ValueError('unvalidated speed increase')
        if self.passage_timeout_s > 900:
            raise ValueError('passage timeout exceeds per-cell diagnostic cap')


class CorridorPlan:
    """Immutable public proposal plus a private copy of static T10a geometry.

    A refuge is optional: a failed bay certificate NEVER invalidates the
    crossing or makes a pair squeeze into a bay. Only a solo actor may execute
    the optional refuge policy in v1. Pair translation is fixed-heading and
    uses the existing carry_ready_N/carry_go_N barriers, at most eight stations.
    """
    def __init__(self, static_map, *, kind, roles, path, direction, refuge_path=None,
                 robot_model='masterpi_v3'):
        if kind not in ('cyan', 'long_beam'):
            raise UnsupportedCorridor('LOAD_CONTROLLER_UNSUPPORTED')
        self.contract = CorridorContract(static_map, robot_model=robot_model)
        self.formation = self.contract.formation(kind, roles)
        self.path = tuple(_numbers(p, 3) for p in path)
        if not 2 <= len(self.path) <= MAX_SEGMENTS:
            raise UnsupportedCorridor('PATH_STATION_COUNT_UNSUPPORTED')
        if any(a == b for a, b in zip(self.path, self.path[1:])):
            raise ValueError('duplicate consecutive station')
        self.direction = direction
        result = self.contract.passage_path(self.formation, self.path, direction)
        if result['static_ok'] is not True:
            raise UnsupportedCorridor('PASSAGE_REFUSED:' + result['reason'])
        self.pair = len(self.formation.robots) == 2
        if self.pair and any(abs(angle(p[2] - self.path[0][2])) > 1e-9 for p in self.path):
            raise UnsupportedCorridor('PAIR_PIVOT_CONTROLLER_UNSUPPORTED')
        self.geometry = Geometry(self.contract.bounds, self.contract.walls,
                                 self.contract.corridor, self.contract.bay)
        self.refuge_path = None
        self.refuge_index = None
        self.refuge_reason = 'NO_REFUGE_PROPOSAL'
        if refuge_path is not None:
            proposed = self.contract._path(refuge_path, self.formation.parts)
            if proposed[0] not in self.path[1:-1]:
                raise ValueError('refuge must start at an interior route station')
            stop = self.contract.bay_stop(self.formation, proposed[-1])
            outward = self.contract.bay_motion(self.formation, proposed, proposed[-1])
            inward = self.contract.bay_motion(self.formation, proposed[::-1], proposed[-1], reentry=True)
            if not all(r['static_ok'] is True for r in (stop, outward, inward)):
                self.refuge_reason = 'REFUGE_STATICALLY_BLOCKED'
            elif self.pair:
                self.refuge_reason = 'PAIR_REFUGE_POLICY_UNSUPPORTED'
            else:
                self.refuge_path = proposed
                self.refuge_index = self.path.index(proposed[0])
                self.refuge_reason = 'SOLO_REFUGE_STATICALLY_ADMITTED'
        self.stations = {rid: tuple(station_offset({'robot_model': 'masterpi_v3'}, kind, role))
                         for role, rid in self.formation.assignment}
        self.route_record = {'profile': PROFILE, 'geometry_sha256': self.contract.geometry_sha256,
                             'kind': kind, 'direction': direction, 'path': self.path,
                             'refuge_path': self.refuge_path, 'refuge_reason': self.refuge_reason,
                             'formation_margin_m': self.formation.margin_m}
        self.route_sha256 = digest(self.route_record)
        self.assignment_sha256 = digest(dict(self.formation.assignment))

    def record(self):
        return {**self.route_record, 'route_sha256': self.route_sha256,
                'role_assignment': dict(self.formation.assignment),
                'role_assignment_sha256': self.assignment_sha256,
                'physics_verified': False, 'runtime_admission': 'offline_controller_only'}
