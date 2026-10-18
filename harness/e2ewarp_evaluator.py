"""EVALUATION-ONLY physical evaluator for the e2ewarp gate pipeline.

This module is the missing ``evaluator_factory`` capability of
``scripts/run_e2ewarp.py``. It runs *after* all controllers stopped and reads
only evaluation artifacts from the raw directory:

``evaluation-state.npz``
    ``qpos`` with shape ``(ticks, worlds, nq)`` and the fixed ``dt``.
``eval-geometry.json``
    Eval-only geometry/ledger written by the run's evaluation sink:
    robot base qpos addresses, cargo qpos addresses and pickup poses, the
    static-map zone rectangles, the door/gate aperture, the mission
    requirements, the expected ``evaluation-state.npz`` SHA-256 and per-world
    own-map evidence copied from ``localization.json``.

It never imports ``mujoco``, the runtime, a controller or a model client and
never reads an agent claim (``result.json``, ``mission-events.json``,
``physical-evaluation.json``, ...). A missing, corrupt, stale or inconsistent
input raises :class:`EvaluatorError`; it is never converted into success.

Output schema ``ugrp.e2ewarp.physical-evaluation.v1``::

    {
      "schema": "ugrp.e2ewarp.physical-evaluation.v1",
      "source_sha": "<40 hex>",
      "evaluation_state_sha256": "<64 hex>",
      "evaluation_state_filename": "evaluation-state.npz",
      "geometry_sha256": "<64 hex>",
      "nworld": <int>,
      "eval_only": true,
      "agent_claim_used": false,
      "worlds": [
        {"world_id": <int>,
         "physical_success": <bool>,          # base in zone B + cargo landing
         "first_to_end_transport": <bool>,    # pickup -> carried -> delivery
         "same_episode": <bool>,              # one contiguous, non-reset run
         "self_map_used": <bool>,             # own-map ledger evidence
         "zone_check": {...}, "gate_check": {...}, "self_map": {...},
         "reasons": [<failed check ids>]}
      ]
    }

Success is physical and geometry-derived:

* every required robot base is inside the destination zone rectangle
  (``base_requirement`` ``all`` or ``any``) at the final state;
* every required cargo body is inside that rectangle at the final state (and
  its landing footprint fits when the catalogue half extents are known);
* every robot/cargo that must arrive crossed the divider/door plane through the
  aperture, not through a wall, and the cargo footprint fits the aperture when
  it is known;
* the qpos stream is one monotone episode with finite states and no per-tick
  displacement above ``max_tick_step_m`` (a reset/teleport detector), and
* ``first_to_end_transport`` additionally requires the cargo to start at the
  recorded pickup pose, have its moving ticks attended by a robot inside the
  carry radius (``attended_motion_fraction``), and be delivered in the same
  episode.

``self_map_used`` is intentionally not derivable from qpos; it is computed from
the eval-only own-map ledger copied into ``eval-geometry.json`` by the run's
evaluation sink (inserted keyframes / occupied cells / ``map_correction_active``
reports). Forbidden ground-truth keys in that ledger fail the check closed.
"""
from __future__ import annotations

import hashlib
import json
import math
from pathlib import Path

import numpy as np

SCHEMA = 'ugrp.e2ewarp.physical-evaluation.v1'
GEOMETRY_SCHEMA = 'ugrp.e2ewarp.eval-geometry.v1'
STATE_FILE = 'evaluation-state.npz'
GEOMETRY_FILE = 'eval-geometry.json'

DEFAULT_POLICY = {
    'max_tick_step_m': .5,
    'initial_cargo_tolerance_m': .10,
    'initial_cargo_yaw_tolerance_rad': .35,
    'carry_radius_m': 1.0,
    'carry_motion_threshold_m': .02,
    'attended_motion_fraction': .5,
    'robot_half_width_m': .10,
    'gate_footprint_check': True,
    'require_own_gauge_pose': False,
}


class EvaluatorError(ValueError):
    """Fail-closed evaluator input/contract error. Never means success."""

    def __init__(self, code, detail=''):
        self.code, self.detail = code, str(detail)
        super().__init__(f'{code}:{self.detail}' if self.detail else code)


def _fail(code, detail=''):
    raise EvaluatorError(code, detail)


def sha256_file(path):
    digest = hashlib.sha256()
    with open(path, 'rb') as stream:
        for chunk in iter(lambda: stream.read(1 << 20), b''):
            digest.update(chunk)
    return digest.hexdigest()


def _hex(value, size, code):
    if not isinstance(value, str) or len(value) != size or any(c not in '0123456789abcdef' for c in value):
        _fail(code, f'expected {size} lowercase hex chars')
    return value


def _finite(value, code, detail=''):
    try:
        number = float(value)
    except (TypeError, ValueError):
        _fail(code, detail or 'not a number')
    if not math.isfinite(number):
        _fail(code, detail or 'not finite')
    return number


def _int(value, code, detail='', minimum=None):
    if type(value) is not int or (minimum is not None and value < minimum):
        _fail(code, detail or 'invalid integer')
    return value


def _dict(value, code, detail=''):
    if not isinstance(value, dict):
        _fail(code, detail or 'not an object')
    return value


def _list(value, code, detail=''):
    if not isinstance(value, list):
        _fail(code, detail or 'not a list')
    return value


def _pair(value, code, detail=''):
    if (not isinstance(value, (list, tuple)) or len(value) != 2):
        _fail(code, detail or 'expected [x, y]')
    return [_finite(value[0], code, detail), _finite(value[1], code, detail)]


def yaw_from_quat(w, x, y, z):
    """Planar yaw of a MuJoCo ``wxyz`` free-joint quaternion."""
    return math.atan2(2. * (w * z + x * y), 1. - 2. * (y * y + z * z))


def _angle_distance(first, second):
    return abs((float(first) - float(second) + math.pi) % (2. * math.pi) - math.pi)


def _policy(geometry):
    raw = geometry.get('policy') or {}
    _dict(raw, 'EVALUATOR_GEOMETRY_INVALID', 'policy')
    merged = dict(DEFAULT_POLICY)
    for key in DEFAULT_POLICY:
        if key in raw:
            if isinstance(DEFAULT_POLICY[key], bool):
                if not isinstance(raw[key], bool):
                    _fail('EVALUATOR_GEOMETRY_INVALID', 'policy.' + key)
                merged[key] = raw[key]
            else:
                merged[key] = _finite(raw[key], 'EVALUATOR_GEOMETRY_INVALID', 'policy.' + key)
                if merged[key] <= 0:
                    _fail('EVALUATOR_GEOMETRY_INVALID', 'policy.' + key + ' must be positive')
                if key == 'attended_motion_fraction' and merged[key] > 1:
                    _fail('EVALUATOR_GEOMETRY_INVALID', 'policy.' + key + ' must be <= 1')
    return merged


def _normalise_zones(value):
    zones = _dict(value, 'EVALUATOR_GEOMETRY_INVALID', 'zones')
    if not zones:
        _fail('EVALUATOR_GEOMETRY_INVALID', 'zones is empty')
    out = {}
    for name, record in zones.items():
        if not isinstance(name, str) or not name:
            _fail('EVALUATOR_GEOMETRY_INVALID', 'zone name')
        record = _dict(record, 'EVALUATOR_GEOMETRY_INVALID', 'zones.' + name)
        center = _pair(record.get('center_m'), 'EVALUATOR_GEOMETRY_INVALID', 'zones.' + name + '.center_m')
        half = _pair(record.get('half_extents_m'), 'EVALUATOR_GEOMETRY_INVALID', 'zones.' + name + '.half_extents_m')
        if half[0] <= 0 or half[1] <= 0:
            _fail('EVALUATOR_GEOMETRY_INVALID', 'zones.' + name + ' half extents must be positive')
        out[name] = {'center_m': center, 'half_extents_m': half}
    return out


def _normalise_gate(value):
    if value is None:
        return None
    gate = _dict(value, 'EVALUATOR_GEOMETRY_INVALID', 'gate')
    axis = gate.get('axis')
    if axis not in ('x', 'y'):
        _fail('EVALUATOR_GEOMETRY_INVALID', 'gate.axis must be x or y')
    return {
        'id': str(gate.get('id') or 'gate'),
        'axis': axis,
        'plane_m': _finite(gate.get('plane_m'), 'EVALUATOR_GEOMETRY_INVALID', 'gate.plane_m'),
        'center_lateral_m': _finite(gate.get('center_lateral_m'), 'EVALUATOR_GEOMETRY_INVALID',
                                    'gate.center_lateral_m'),
        'half_width_m': _finite(gate.get('half_width_m'), 'EVALUATOR_GEOMETRY_INVALID', 'gate.half_width_m'),
    }


def _normalise_worlds(value, nworld):
    worlds = _list(value, 'EVALUATOR_GEOMETRY_INVALID', 'worlds')
    if len(worlds) != nworld:
        _fail('EVALUATOR_GEOMETRY_INVALID', 'worlds length != nworld')
    out = []
    for expected, record in enumerate(worlds):
        record = _dict(record, 'EVALUATOR_GEOMETRY_INVALID', 'worlds[]')
        world_id = _int(record.get('world_id'), 'EVALUATOR_GEOMETRY_INVALID', 'world_id', minimum=0)
        if world_id != expected:
            _fail('EVALUATOR_GEOMETRY_INVALID', 'world ids must be exactly 0..nworld-1 in order')
        robots = _list(record.get('robots'), 'EVALUATOR_GEOMETRY_INVALID', 'worlds[].robots')
        if not robots:
            _fail('EVALUATOR_GEOMETRY_INVALID', 'world has no robots')
        robot_rows, seen = [], set()
        for robot in robots:
            robot = _dict(robot, 'EVALUATOR_GEOMETRY_INVALID', 'worlds[].robots[]')
            robot_id = robot.get('id')
            if not isinstance(robot_id, str) or not robot_id or robot_id in seen:
                _fail('EVALUATOR_GEOMETRY_INVALID', 'robot id must be unique non-empty string')
            seen.add(robot_id)
            robot_rows.append({
                'id': robot_id,
                'base_qpos_adr': _int(robot.get('base_qpos_adr'), 'EVALUATOR_GEOMETRY_INVALID',
                                      robot_id + '.base_qpos_adr', minimum=0),
            })
        cargo_rows = []
        for cargo in _list(record.get('cargo', []), 'EVALUATOR_GEOMETRY_INVALID', 'worlds[].cargo'):
            cargo = _dict(cargo, 'EVALUATOR_GEOMETRY_INVALID', 'worlds[].cargo[]')
            item_id = cargo.get('id')
            if not isinstance(item_id, str) or not item_id:
                _fail('EVALUATOR_GEOMETRY_INVALID', 'cargo id must be non-empty string')
            half = cargo.get('half_extents_m')
            if half is not None:
                half = _pair(half, 'EVALUATOR_GEOMETRY_INVALID', item_id + '.half_extents_m')
                if half[0] <= 0 or half[1] <= 0:
                    _fail('EVALUATOR_GEOMETRY_INVALID', item_id + ' half extents must be positive')
            cargo_rows.append({
                'id': item_id,
                'kind': str(cargo.get('kind') or ''),
                'qpos_adr': _int(cargo.get('qpos_adr'), 'EVALUATOR_GEOMETRY_INVALID',
                                 item_id + '.qpos_adr', minimum=0),
                'initial_xy_m': _pair(cargo.get('initial_xy_m'), 'EVALUATOR_GEOMETRY_INVALID',
                                      item_id + '.initial_xy_m'),
                'half_extents_m': half,
                'initial_yaw_rad': _finite(cargo.get('initial_yaw_rad', 0.),
                                           'EVALUATOR_GEOMETRY_INVALID', item_id + '.initial_yaw_rad'),
            })
        out.append({'world_id': world_id, 'robots': robot_rows, 'cargo': cargo_rows})
    return out


def _normalise_mission(value, zones, gate):
    mission = _dict(value, 'EVALUATOR_GEOMETRY_INVALID', 'mission')
    destination = mission.get('destination_zone')
    if destination not in zones:
        _fail('EVALUATOR_GEOMETRY_INVALID', 'mission.destination_zone is not a known zone')
    base_requirement = mission.get('base_requirement', 'all')
    if base_requirement not in ('all', 'any'):
        _fail('EVALUATOR_GEOMETRY_INVALID', 'mission.base_requirement')
    required_robots = _list(mission.get('required_robots', []), 'EVALUATOR_GEOMETRY_INVALID',
                            'mission.required_robots')
    if any(not isinstance(robot, str) or not robot for robot in required_robots):
        _fail('EVALUATOR_GEOMETRY_INVALID', 'mission.required_robots entries')
    cargo_ids = _list(mission.get('cargo_ids', []), 'EVALUATOR_GEOMETRY_INVALID', 'mission.cargo_ids')
    if any(not isinstance(item, str) or not item for item in cargo_ids):
        _fail('EVALUATOR_GEOMETRY_INVALID', 'mission.cargo_ids entries')
    require_cargo = mission.get('require_cargo', True)
    if not isinstance(require_cargo, bool):
        _fail('EVALUATOR_GEOMETRY_INVALID', 'mission.require_cargo')
    if require_cargo and not cargo_ids:
        _fail('EVALUATOR_MISSION_INVALID', 'cargo_ids required for a transport gate')
    require_gate = mission.get('require_gate', gate is not None)
    if not isinstance(require_gate, bool):
        _fail('EVALUATOR_GEOMETRY_INVALID', 'mission.require_gate')
    if require_gate and gate is None:
        _fail('EVALUATOR_GEOMETRY_INVALID', 'mission requires a gate but none was exported')
    return {
        'destination_zone': destination,
        'base_requirement': base_requirement,
        'required_robots': required_robots,
        'cargo_ids': cargo_ids,
        'require_cargo': require_cargo,
        'require_gate': require_gate,
    }


def _normalise_self_map(value, nworld):
    self_map = _dict(value, 'EVALUATOR_GEOMETRY_INVALID', 'self_map')
    if self_map.get('source') != 'localization.json':
        _fail('EVALUATOR_GEOMETRY_INVALID', 'self_map.source must be localization.json')
    _hex(self_map.get('rows_sha256'), 64, 'EVALUATOR_GEOMETRY_INVALID')
    worlds = _list(self_map.get('worlds'), 'EVALUATOR_GEOMETRY_INVALID', 'self_map.worlds')
    if len(worlds) != nworld:
        _fail('EVALUATOR_GEOMETRY_INVALID', 'self_map.worlds length != nworld')
    out = []
    for expected, record in enumerate(worlds):
        record = _dict(record, 'EVALUATOR_GEOMETRY_INVALID', 'self_map.worlds[]')
        world_id = _int(record.get('world_id'), 'EVALUATOR_GEOMETRY_INVALID', 'self_map world_id', minimum=0)
        if world_id != expected:
            _fail('EVALUATOR_GEOMETRY_INVALID', 'self_map world ids must be 0..nworld-1 in order')
        robots = _dict(record.get('robots'), 'EVALUATOR_GEOMETRY_INVALID', 'self_map.worlds[].robots')
        rows = {}
        for robot_id, counts in robots.items():
            if not isinstance(robot_id, str) or not robot_id:
                _fail('EVALUATOR_GEOMETRY_INVALID', 'self_map robot id')
            counts = _dict(counts, 'EVALUATOR_GEOMETRY_INVALID', 'self_map.' + robot_id)
            row = {
                'observations': _int(counts.get('observations', 0), 'EVALUATOR_GEOMETRY_INVALID',
                                     robot_id + '.observations', minimum=0),
                'inserted_frames': _int(counts.get('inserted_frames', 0), 'EVALUATOR_GEOMETRY_INVALID',
                                        robot_id + '.inserted_frames', minimum=0),
                'occupied_cells_max': _int(counts.get('occupied_cells_max', 0), 'EVALUATOR_GEOMETRY_INVALID',
                                           robot_id + '.occupied_cells_max', minimum=0),
                'map_correction_active_rows': _int(counts.get('map_correction_active_rows', 0),
                                                   'EVALUATOR_GEOMETRY_INVALID',
                                                   robot_id + '.map_correction_active_rows', minimum=0),
                'own_gauge_pose_rows': _int(counts.get('own_gauge_pose_rows', 0),
                                            'EVALUATOR_GEOMETRY_INVALID',
                                            robot_id + '.own_gauge_pose_rows', minimum=0),
                'gt_fields_present': _list(counts.get('gt_fields_present', []),
                                           'EVALUATOR_GEOMETRY_INVALID', robot_id + '.gt_fields_present'),
            }
            if any(not isinstance(key, str) or not key for key in row['gt_fields_present']):
                _fail('EVALUATOR_GEOMETRY_INVALID', robot_id + '.gt_fields_present entries')
            rows[robot_id] = row
        out.append({'world_id': world_id, 'robots': rows})
    return {'source': 'localization.json', 'rows_sha256': self_map['rows_sha256'], 'worlds': out}


def validate_geometry(geometry):
    """Validate and normalise ``eval-geometry.json``; fail closed on anything else."""
    geometry = _dict(geometry, 'EVALUATOR_GEOMETRY_INVALID', 'root')
    if geometry.get('schema') != GEOMETRY_SCHEMA:
        _fail('EVALUATOR_GEOMETRY_INVALID', 'schema must be ' + GEOMETRY_SCHEMA)
    if geometry.get('eval_only') is not True:
        _fail('EVALUATOR_GEOMETRY_INVALID', 'eval_only must be true')
    source_sha = _hex(geometry.get('source_sha'), 40, 'EVALUATOR_SOURCE_SHA_INVALID')
    state_sha = _hex(geometry.get('evaluation_state_sha256'), 64, 'EVALUATOR_GEOMETRY_INVALID')
    dt = _finite(geometry.get('dt'), 'EVALUATOR_GEOMETRY_INVALID', 'dt')
    if dt <= 0:
        _fail('EVALUATOR_GEOMETRY_INVALID', 'dt must be positive')
    nworld = _int(geometry.get('nworld'), 'EVALUATOR_GEOMETRY_INVALID', 'nworld', minimum=1)
    zones = _normalise_zones(geometry.get('zones'))
    gate = _normalise_gate(geometry.get('gate'))
    worlds = _normalise_worlds(geometry.get('worlds'), nworld)
    mission = _normalise_mission(geometry.get('mission'), zones, gate)
    self_map = _normalise_self_map(geometry.get('self_map'), nworld)
    return {
        'schema': GEOMETRY_SCHEMA,
        'source_sha': source_sha,
        'evaluation_state_sha256': state_sha,
        'dt': dt,
        'nworld': nworld,
        'zones': zones,
        'gate': gate,
        'worlds': worlds,
        'mission': mission,
        'self_map': self_map,
        'policy': _policy(geometry),
        'eval_only': True,
    }


def build_geometry(*, source_sha, evaluation_state_sha256, dt, worlds, zones, mission,
                   self_map, gate=None, policy=None):
    """Build ``eval-geometry.json`` from eval-only run metadata (pure helper).

    The run calls this inside its evaluation sink after controllers stopped. It
    accepts plain data only; no simulator object or agent claim is read here.
    """
    document = {
        'schema': GEOMETRY_SCHEMA,
        'eval_only': True,
        'source_sha': source_sha,
        'evaluation_state_sha256': evaluation_state_sha256,
        'dt': dt,
        'nworld': len(worlds),
        'zones': zones,
        'gate': gate,
        'worlds': worlds,
        'mission': mission,
        'self_map': self_map,
        'policy': dict(DEFAULT_POLICY if policy is None else policy),
    }
    return validate_geometry(document)


def _read_json(path):
    try:
        with open(path, 'r') as stream:
            return json.load(stream)
    except (OSError, UnicodeDecodeError, json.JSONDecodeError) as exc:
        _fail('EVALUATOR_INPUT_CORRUPT', f'{path.name}:{type(exc).__name__}')


def _read_state(path):
    try:
        with np.load(path, allow_pickle=False) as data:
            if 'qpos' not in data.files or 'dt' not in data.files:
                _fail('EVALUATOR_INPUT_CORRUPT', f'{path.name}:qpos/dt missing')
            qpos = np.asarray(data['qpos'], dtype=np.float64)
            dt = np.asarray(data['dt'], dtype=np.float64)
    except EvaluatorError:
        raise
    except Exception as exc:  # zip/format/object-array corruption must fail closed
        _fail('EVALUATOR_INPUT_CORRUPT', f'{path.name}:{type(exc).__name__}')
    if dt.size != 1:
        _fail('EVALUATOR_INPUT_CORRUPT', f'{path.name}:dt is not scalar')
    return qpos, float(dt.reshape(-1)[0])


def _check_state(qpos, dt, geometry):
    if qpos.ndim != 3:
        _fail('EVALUATOR_STATE_SHAPE_INVALID', 'qpos must be (ticks, worlds, nq)')
    ticks, worlds, nq = qpos.shape
    if worlds != geometry['nworld']:
        _fail('EVALUATOR_WORLD_SET_MISMATCH', f'state worlds={worlds} geometry worlds={geometry["nworld"]}')
    if ticks < 2:
        _fail('EVALUATOR_STATE_TOO_SHORT', f'ticks={ticks}')
    if not np.isfinite(qpos).all():
        _fail('EVALUATOR_STATE_NOT_FINITE', 'qpos contains NaN/Inf')
    if abs(dt - geometry['dt']) > 1e-9:
        _fail('EVALUATOR_DT_MISMATCH', f'state dt={dt} geometry dt={geometry["dt"]}')
    addresses = [robot['base_qpos_adr'] for world in geometry['worlds'] for robot in world['robots']]
    addresses += [cargo['qpos_adr'] for world in geometry['worlds'] for cargo in world['cargo']]
    if not addresses:
        _fail('EVALUATOR_GEOMETRY_INVALID', 'no qpos addresses')
    if len(set(addresses)) != len(addresses):
        _fail('EVALUATOR_GEOMETRY_INVALID', 'duplicate qpos addresses')
    if max(addresses) + 7 > nq:
        _fail('EVALUATOR_STATE_SHAPE_INVALID', f'nq={nq} too small for qpos addresses')
    return ticks, worlds, nq


def _trajectory(qpos, world, address):
    block = qpos[:, world, address:address + 7]
    return np.asarray(block[:, :2], dtype=np.float64), np.asarray(block[:, 3:7], dtype=np.float64)


def _yaw_series(quaternions):
    return np.asarray([yaw_from_quat(*row) for row in quaternions], dtype=np.float64)


def _steps(trajectory):
    if len(trajectory) < 2:
        return 0.
    return float(np.max(np.linalg.norm(np.diff(trajectory, axis=0), axis=1)))


def _continuity(trajectory, limit):
    step = _steps(trajectory)
    return step <= limit, step


def _zone(trajectory, zone):
    x, y = float(trajectory[-1][0]), float(trajectory[-1][1])
    dx, dy = abs(x - zone['center_m'][0]), abs(y - zone['center_m'][1])
    hx, hy = zone['half_extents_m']
    return {
        'center_m': [x, y],
        'inside': dx <= hx and dy <= hy,
        'margin_m': float(min(hx - dx, hy - dy)),
    }


def _landing(trajectory, yaw, half, zone):
    """Axis-aligned bounding box of the rotated cargo footprint inside a zone."""
    if half is None:
        row = _zone(trajectory, zone)
        row['footprint_half_m'] = [0., 0.]
        return row
    hx = half[0] * abs(math.cos(yaw)) + half[1] * abs(math.sin(yaw))
    hy = half[0] * abs(math.sin(yaw)) + half[1] * abs(math.cos(yaw))
    x, y = float(trajectory[-1][0]), float(trajectory[-1][1])
    dx, dy = abs(x - zone['center_m'][0]), abs(y - zone['center_m'][1])
    zx, zy = zone['half_extents_m']
    return {
        'center_m': [x, y],
        'inside': dx + hx <= zx and dy + hy <= zy,
        'margin_m': float(min(zx - dx - hx, zy - dy - hy)),
        'footprint_half_m': [float(hx), float(hy)],
    }


def _lateral_half(yaw, half, gate):
    if half is None:
        return 0.
    # Rectangle half extent projected on the gate's lateral axis.
    if gate['axis'] == 'x':
        return half[0] * abs(math.sin(yaw)) + half[1] * abs(math.cos(yaw))
    return half[0] * abs(math.cos(yaw)) + half[1] * abs(math.sin(yaw))


def _gate_check(trajectory, yaw_series, gate, half, policy, required):
    coordinates = trajectory[:, 0] if gate['axis'] == 'x' else trajectory[:, 1]
    lateral = trajectory[:, 1] if gate['axis'] == 'x' else trajectory[:, 0]
    signed = coordinates - gate['plane_m']
    forward = []
    for index in range(1, len(signed)):
        before, after = float(signed[index - 1]), float(signed[index])
        if before < 0. <= after:
            span = after - before
            fraction = (-before / span) if span > 0 else 1.
            crossing = float(lateral[index - 1] + (lateral[index] - lateral[index - 1]) * fraction)
            half_lateral = 0.
            if policy['gate_footprint_check']:
                half_lateral = _lateral_half(float(yaw_series[index]), half, gate)
            forward.append({
                'tick': index,
                'lateral_m': crossing,
                'half_extent_m': float(half_lateral),
                'aperture_margin_m': float(gate['half_width_m'] - abs(crossing - gate['center_lateral_m'])
                                          - half_lateral),
            })
    crossed = bool(forward)
    via = crossed and all(row['aperture_margin_m'] >= -1e-9 for row in forward)
    return {
        'required': bool(required),
        'crossed': crossed,
        'via_aperture': bool(via),
        'forward_crossings': forward,
    }


def _self_map_row(geometry_world, self_world, robot_ids, policy):
    rows = {}
    used = []
    for robot_id in robot_ids:
        evidence = self_world['robots'].get(robot_id)
        if evidence is None:
            _fail('EVALUATOR_SELF_MAP_EVIDENCE_MISSING', f'world {geometry_world["world_id"]} robot {robot_id}')
        row = dict(evidence)
        content = (row['inserted_frames'] > 0 or row['occupied_cells_max'] > 0
                   or row['map_correction_active_rows'] > 0)
        pose_ok = (not policy['require_own_gauge_pose']) or row['own_gauge_pose_rows'] > 0
        ok = (row['observations'] > 0 and content and pose_ok and not row['gt_fields_present'])
        row['used'] = bool(ok)
        rows[robot_id] = row
        used.append(ok)
    return rows, used


def _evaluate_world(qpos, world, geometry, self_world):
    policy = geometry['policy']
    mission = geometry['mission']
    zone = geometry['zones'][mission['destination_zone']]
    gate = geometry['gate']
    robots = {robot['id']: robot for robot in world['robots']}
    required = list(mission['required_robots']) or list(robots)
    missing = [robot_id for robot_id in required if robot_id not in robots]
    if missing:
        _fail('EVALUATOR_WORLD_SET_MISMATCH', 'required robots missing: ' + ','.join(missing))
    cargo_rows = {cargo['id']: cargo for cargo in world['cargo']}
    reasons = []
    teleports = []
    robot_rows, gate_rows = [], []
    same_episode = True

    robot_trajectories, robot_yaws = {}, {}
    for robot_id, robot in robots.items():
        trajectory, quaternions = _trajectory(qpos, world['world_id'], robot['base_qpos_adr'])
        robot_trajectories[robot_id] = trajectory
        robot_yaws[robot_id] = _yaw_series(quaternions)
        ok, step = _continuity(trajectory, policy['max_tick_step_m'])
        if not ok:
            same_episode = False
            teleports.append({'entity': robot_id, 'kind': 'robot', 'max_tick_step_m': step})
        robot_rows.append({
            'id': robot_id,
            'center_m': trajectory[-1].tolist(),
            'base_qpos_adr': robot['base_qpos_adr'],
            **{k: v for k, v in _zone(trajectory, zone).items()},
        })
    cargo_entities = {}
    for item_id, cargo in cargo_rows.items():
        trajectory, quaternions = _trajectory(qpos, world['world_id'], cargo['qpos_adr'])
        cargo_entities[item_id] = {'trajectory': trajectory, 'yaws': _yaw_series(quaternions)}
        ok, step = _continuity(trajectory, policy['max_tick_step_m'])
        if not ok:
            same_episode = False
            teleports.append({'entity': item_id, 'kind': 'cargo', 'max_tick_step_m': step})

    # Base requirement: every required robot or at least one of them.
    if mission['base_requirement'] == 'all':
        base_candidates = [row for row in robot_rows if row['id'] in required]
        bases_ok = all(row['inside'] for row in base_candidates)
        for row in base_candidates:
            if not row['inside']:
                reasons.append('base_outside_zone:' + row['id'])
    else:
        base_candidates = [row for row in robot_rows if row['id'] in required]
        bases_ok = any(row['inside'] for row in base_candidates)
        if not bases_ok:
            reasons.append('no_base_inside_zone')

    # Gate: required robots must cross through the aperture if the zone is east.
    if gate is None or not mission['require_gate']:
        gate_rows = [{'id': robot_id, 'required': False} for robot_id in required]
        base_gate_ok = True
    else:
        crossed_in = 0
        inside_by_id = {row['id']: row['inside'] for row in robot_rows}
        for robot_id in required:
            row = _gate_check(robot_trajectories[robot_id], robot_yaws[robot_id], gate,
                              [policy['robot_half_width_m']] * 2, policy, True)
            row['id'] = robot_id
            gate_rows.append(row)
            if row['via_aperture']:
                crossed_in += 1
        if mission['base_requirement'] == 'all':
            base_gate_ok = crossed_in == len(required)
            for row in gate_rows:
                if not row['via_aperture']:
                    reasons.append(('gate_not_crossed:' if not row['crossed']
                                    else 'gate_outside_aperture:') + row['id'])
        else:
            # The robot that is inside the zone must be the one that crossed the
            # door; another robot crossing elsewhere cannot vouch for it.
            base_gate_ok = any(row['via_aperture'] and inside_by_id.get(row['id']) is True
                               for row in gate_rows)
            if not base_gate_ok:
                reasons.append('no_base_inside_zone_through_gate')

    cargo_checks, cargo_inside, cargo_gate_ok, transport_ok = [], True, True, True
    for item_id in mission['cargo_ids']:
        cargo = cargo_rows.get(item_id)
        if cargo is None:
            _fail('EVALUATOR_CARGO_MISSING', item_id)
        trajectory = cargo_entities[item_id]['trajectory']
        yaw = cargo_entities[item_id]['yaws']
        initial = np.asarray(cargo['initial_xy_m'], dtype=np.float64)
        initial_distance = float(np.linalg.norm(trajectory[0] - initial))
        initial_yaw_distance = _angle_distance(yaw[0], cargo['initial_yaw_rad'])
        initial_ok = (initial_distance <= policy['initial_cargo_tolerance_m']
                      and initial_yaw_distance <= policy['initial_cargo_yaw_tolerance_rad'])
        landing = _landing(trajectory, float(yaw[-1]), cargo['half_extents_m'], zone)
        distances = [np.linalg.norm(robot_trajectories[robot_id] - trajectory, axis=1)
                     for robot_id in required if robot_id in robot_trajectories]
        nearest_series = np.min(np.stack(distances), axis=0) if distances else np.full(len(trajectory), np.inf)
        near = float(np.min(nearest_series))
        motion = np.linalg.norm(np.diff(trajectory, axis=0), axis=1)
        moving = motion > policy['carry_motion_threshold_m']
        attended = nearest_series[1:] <= policy['carry_radius_m']
        carried_fraction = float(attended[moving].mean()) if moving.any() else 0.
        carried = carried_fraction >= policy['attended_motion_fraction']
        gate_row = _gate_check(trajectory, yaw, gate,
                               cargo['half_extents_m'], policy, True) if gate is not None and mission['require_gate'] else {
            'required': False, 'crossed': False, 'via_aperture': True, 'forward_crossings': []}
        gate_row = {'id': item_id, **gate_row}
        cargo_checks.append({
            'id': item_id,
            'kind': cargo['kind'],
            'initial_xy_m': cargo['initial_xy_m'],
            'first_xy_m': trajectory[0].tolist(),
            'initial_distance_m': initial_distance,
            'initial_yaw_rad': cargo['initial_yaw_rad'],
            'first_yaw_rad': float(yaw[0]),
            'initial_yaw_distance_rad': initial_yaw_distance,
            'initial_ok': bool(initial_ok),
            'carried': bool(carried),
            'carried_motion_fraction': carried_fraction,
            'nearest_robot_m': near,
            **landing,
            'gate': gate_row,
        })
        cargo_inside = cargo_inside and landing['inside']
        cargo_gate_ok = cargo_gate_ok and (not gate_row['required'] or gate_row['via_aperture'])
        if not initial_ok:
            reasons.append('cargo_not_at_pickup:' + item_id)
        if not carried:
            reasons.append('cargo_not_carried:' + item_id)
        if not landing['inside']:
            reasons.append('cargo_outside_zone:' + item_id)
        if gate_row['required'] and not gate_row['via_aperture']:
            reasons.append(('cargo_gate_not_crossed:' if not gate_row['crossed']
                            else 'cargo_gate_outside_aperture:') + item_id)
        transport_ok = transport_ok and initial_ok and carried and landing['inside'] and (
            not gate_row['required'] or gate_row['via_aperture'])

    if not same_episode:
        reasons.append('episode_not_contiguous')
    cargo_ok = cargo_inside or not mission['require_cargo']
    physical_success = bool(same_episode and bases_ok and cargo_ok and base_gate_ok and cargo_gate_ok)
    first_to_end = bool(same_episode and transport_ok and cargo_ok)
    if not mission['require_cargo']:
        # Base-arrival-only gate (future nav mode): transport is not claimed.
        first_to_end = False

    self_rows, used = _self_map_row(world, self_world, required, policy)
    if mission['base_requirement'] == 'any' and used:
        self_map_used = any(used)
    else:
        self_map_used = all(used) if used else False
    if not self_map_used:
        reasons.append('self_map_not_used')
    return {
        'world_id': world['world_id'],
        'physical_success': physical_success,
        'first_to_end_transport': first_to_end,
        'same_episode': same_episode,
        'self_map_used': bool(self_map_used),
        'zone_check': {
            'destination_zone': mission['destination_zone'],
            'center_m': zone['center_m'],
            'half_extents_m': zone['half_extents_m'],
            'base_requirement': mission['base_requirement'],
            'required_robots': required,
            'bases_inside': bool(bases_ok),
            'cargo_inside': bool(cargo_ok),
            'robots': robot_rows,
            'cargo': cargo_checks,
        },
        'gate_check': {
            'required': bool(gate is not None and mission['require_gate']),
            'gate': gate,
            'ok': bool(base_gate_ok and cargo_gate_ok),
            'robots': gate_rows,
            'cargo': [row['gate'] for row in cargo_checks],
        },
        'self_map': {'used': bool(self_map_used), 'robots': self_rows},
        'continuity': {'same_episode': same_episode, 'teleports': teleports,
                       'max_tick_step_m': policy['max_tick_step_m']},
        'reasons': reasons,
    }


def evaluate(*, raw):
    """Evaluate one raw directory; returns the ``physical-evaluation`` document."""
    raw = Path(raw)
    if not raw.is_dir():
        _fail('EVALUATOR_INPUT_MISSING', f'raw directory:{raw}')
    state_path = raw / STATE_FILE
    geometry_path = raw / GEOMETRY_FILE
    if not state_path.is_file():
        _fail('EVALUATOR_INPUT_MISSING', STATE_FILE)
    if not geometry_path.is_file():
        _fail('EVALUATOR_INPUT_MISSING', GEOMETRY_FILE)
    geometry = validate_geometry(_read_json(geometry_path))
    qpos, dt = _read_state(state_path)
    actual_sha = sha256_file(state_path)
    if actual_sha != geometry['evaluation_state_sha256']:
        _fail('EVALUATOR_STATE_SHA_MISMATCH',
              f'{actual_sha} != {geometry["evaluation_state_sha256"]}')
    # Replace the recorded SHA with the freshly measured one only after it matched.
    _check_state(qpos, dt, geometry)
    worlds = []
    self_by_id = {row['world_id']: row for row in geometry['self_map']['worlds']}
    for world in geometry['worlds']:
        worlds.append(_evaluate_world(qpos, world, geometry, self_by_id[world['world_id']]))
    return {
        'schema': SCHEMA,
        'source_sha': geometry['source_sha'],
        'evaluation_state_sha256': actual_sha,
        'evaluation_state_filename': STATE_FILE,
        'geometry_sha256': sha256_file(geometry_path),
        'nworld': geometry['nworld'],
        'eval_only': True,
        'agent_claim_used': False,
        'success_definition': ('final base in destination zone + cargo landing in zone + door-aperture '
                               'crossing + one contiguous episode'),
        'policy': geometry['policy'],
        'worlds': worlds,
    }


def evaluator_factory(*, raw):
    """Manifest entry ``harness.e2ewarp_evaluator:evaluator_factory``.

    Called only after controllers stop, with the run's raw directory. Any
    missing/corrupt/stale input raises :class:`EvaluatorError`; it never returns
    a partial or claimed success.
    """
    return evaluate(raw=raw)


__all__ = ['EvaluatorError', 'SCHEMA', 'GEOMETRY_SCHEMA', 'STATE_FILE', 'GEOMETRY_FILE',
           'DEFAULT_POLICY', 'build_geometry', 'validate_geometry', 'evaluate', 'evaluator_factory',
           'sha256_file', 'yaw_from_quat']
