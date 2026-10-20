"""Contract-v1 navigation-gate composition (two robots, wide door, no static map).

First physical gate (2026-10-18 GPU E2E contract v1, step 2):

    two robots start in the west pickup room, pass the divider's *wide* door
    (1.00 m, two lanes) and reach the zone B floor marking, driven only by own
    RGB + own issued wheel pulses + self-centric memory.

Episode construction (setup-only, never a controller input):
- scenario ``s7_pair_with_solo_v7`` -> map ``zone_wide_two_doors_final_v3``
  (wide door at y = -2.625, 1.00 m, two lanes; the contract scenario names
  ``divider_wide_door``).
- r3 is pruned from the XML: the gate is a two-robot scene.
- cargo is not spawned for the navigation gate; the loaded long-beam carry is
  gate 2.
- the pair lane spawn is y = -2.375 (r1) / -2.875 (r2); from those spawns the
  zone B marking is visible through the wide door (0.620 / 0.894 of the paint
  rectangle, setup/eval geometry check
  outputs/e2e18-admin/nav-gate/visibility-check.json). The default spawn rows
  (-2.25/-0.85/0.55) leave zone B invisible from the two driven rows: there the
  adapter's bounded SEARCH turns in place (20 sim s) and holds with
  ``search_timeout`` once the budget is spent, instead of holding immediately
  with ``no_destination``.

Odometry calibration: ``OwnCommandOdometry`` requires *measured* metres and
degrees per percent-second. The constants are read from a calibration artifact
produced by an eval-only GPU calibration run; a missing/unmeasured artifact
fails closed. No default constants are invented here.

Gate modes (2026-10-19 user approval; default OFF):
- ``v1_search`` (default): frozen gate-1/r5 condition, ``gpu_calib_v1`` band and
  the bounded in-place SEARCH. Unchanged.
- ``v230_fwd24``: ``gpu_calib_v230`` (H 110-114 / S>=100 / V 30-230, min
  component 600) plus a bounded forward acquisition of at most 2.4 m before the
  same in-place SEARCH. The 2.4 m replaces the earlier 1.7 m proposal and is a
  user-approved acquisition limit, not a calibrated constant. The mode is bound
  into the queue and into the run environment; results from the two modes are
  separate conditions and are never pooled.
- ``v230_r5`` (2026-10-20 decision; default OFF): ``v230_r4``'s order-sheet slot
  with a **two-stage** activation. Through the wide door the follower aims at the
  component centre (offset 0, the aim r2 passed the door with); the slot turns on
  only when the visible destination component's bottom row projects onto the
  floor at <= 1.5 m with the measured camera model, and the applied offset is
  then clamped to +-15 deg. The 0.52 m projection claim and the 1.0 m path
  fail-safe are unchanged. r4 pushed r1 into the divider's north jamb before the
  door, so the slot timing (not the claim) is the only changed input.
"""
from __future__ import annotations

from harness.e2ewarp_selfnav import (ACQUIRE_CONFIRM_TICKS, ACQUIRE_MIN_HEIGHT_NORM,
                                     ARRIVAL_ODOM_PROJECTION, SLOT_LEFT, SLOT_OFFSET_LIMIT_DEG,
                                     SLOT_RIGHT, SLOT_STAGE2_GROUND_M, SLOTS)

import hashlib
import json
import os
import xml.etree.ElementTree as ET
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
NAV_SCENARIO = 's7_pair_with_solo_v7'
ROBOTS = ('r1', 'r2')
#: Wide-door pair lane, south row. Two 0.50 m lanes inside the 1.00 m door.
LANE_Y = {'r1': -2.375, 'r2': -2.875}
DESTINATION_ZONE = 'B'
DESTINATION_KIND = 'zone_B'
SIM_BUDGET_S = 60.
MAX_SIM_BUDGET_S = 120.
MAX_REL_SPREAD = 0.20
CALIBRATION_SCHEMA = 'ugrp.e2ewarp.nav_calibration.v1'
CALIBRATION_ENV = 'E2EWARP_NAV_CALIBRATION'
CALIBRATION_PATH = ROOT / 'configs/e2ewarp/nav_gate_calibration.json'
_ADMITTED = None

# --- gate modes (default OFF) -------------------------------------------------
# `v1_search` is the frozen gate-1/r5 condition and the default: gpu_calib_v1
# (H 110-114 / S>=100 / V 30-110 / min component 600) plus the bounded in-place
# SEARCH.  `v230_fwd24` is the mode approved by the user on 2026-10-19 after the
# V<=230 window analysis: the same hue/saturation/min-component with the V
# ceiling raised to 230, and a bounded forward acquisition of at most 2.4 m
# (replacing Claude's earlier 1.7 m proposal) before the same in-place SEARCH.
# Selecting the mode is explicit and fail-closed: the queue records every
# field, and prepare/execute must run with the same E2EWARP_NAV_GATE_MODE.
GATE_MODE_ENV = 'E2EWARP_NAV_GATE_MODE'
GATE_MODE_V1 = 'v1_search'
GATE_MODE_V230_FWD24 = 'v230_fwd24'
#: 2026-10-19 approval C (acquisition quality) + B (distance-based arrival,
#: pending the method choice).  ``v230_r2`` is the *same* band/forward condition
#: as ``v230_fwd24`` plus: a minimum patch height pre-filter, three consecutive
#: accepted detections before switching to following, and re-advancing inside
#: the same 2.4 m cap when the target is lost.  The two B candidates stay
#: default OFF and are selected only through the explicit arrival flags below.
GATE_MODE_V230_R2 = 'v230_r2'
#: 2026-10-19 decision ① (`v230_r3`): the same C acquisition quality and the same
#: B arming event/0.52 m geometry as ``v230_r2``, but the arrival claim is the
#: *projection* of the own-odometry displacement onto the armed own-memory
#: bearing direction (``odom_projection`` mode) instead of the integrated path
#: length.  The r2 Step B run failed exactly on that distinction (path 0.52 m
#: vs x reach 0.31-0.40 m).  The mode is default OFF and is the only mode that
#: admits the projection arrival option; 0.52 m and the 1.0 m path fail-safe are
#: frozen constants, not flags.
GATE_MODE_V230_R3 = 'v230_r3'
#: 2026-10-19 r4 step ② (`v230_r4`): byte-identical claim to r3 (same band, C
#: acquisition quality, 2.4 m forward cap, 0.52 m projection onto the armed
#: component-centre bearing, 1.0 m path fail-safe) plus an **order-sheet
#: per-robot slot** (`left`/`right`).  The slot makes each robot follow the
#: centre of its own half of the visible destination marking, so the pair stops
#: converging on one point (r3's two robots came within 0.168 m of each other).
#: It is realised from the robot's own camera component bbox only: no map, no
#: GT and no changed claim definition.  Default OFF; only this mode writes the
#: slot markers into the queue and the order sheet.
GATE_MODE_V230_R4 = 'v230_r4'
#: 2026-10-20 r5 (`v230_r5`): r4's order-sheet slot, but the slot aim is applied
#: only after the visible destination component's bottom row projects onto the
#: floor at <= 1.5 m (two-stage).  Through the wide door the follower aims at the
#: component centre (offset 0); after activation the applied offset is clamped to
#: +-15 deg.  Claim, band, cap and C constants are r4-identical.  The 1.5 m is a
#: design value from the authored geometry (door x=2.2, zone B near edge x=4.3),
#: not a fit to the r4 result.  Default OFF; only this mode writes the stage-2
#: markers into the queue.
GATE_MODE_V230_R5 = 'v230_r5'
#: Modes that carry the order-sheet slot (r4/r5).  r4 keeps its frozen
#: always-on slot; r5 resolves the slot through the stage-2 ground gate.
SLOT_GATE_MODES = (GATE_MODE_V230_R4, GATE_MODE_V230_R5)
#: r1 keeps the authored north lane (LANE_Y -2.375) and r2 the south lane
#: (-2.875).  Facing the destination (+x east), robot-left is +y (north), so the
#: north-lane robot owns the left half of the marking and the south-lane robot
#: the right half.  This mapping is derived from the already-authored lane
#: assignment; it is not a new tuned constant.
SLOT_BY_ROBOT = {'r1': SLOT_LEFT, 'r2': SLOT_RIGHT}
ARRIVAL_ENV = 'E2EWARP_NAV_ARRIVAL'
ARRIVAL_ODOM_M_ENV = 'E2EWARP_NAV_ARRIVAL_ODOM_M'
ARRIVAL_GROUND_M_ENV = 'E2EWARP_NAV_ARRIVAL_GROUND_M'
#: User-approved forward acquisition cap (2026-10-19), replacing the 1.7 m
#: proposal.  It is a control limit, not a calibrated constant.
FORWARD_ACQUISITION_CAP_M = 2.4
GATE_MODES = {
    GATE_MODE_V1: dict(zone_profile='gpu_calib_v1',
                       acquisition_mode='search_in_place',
                       forward_cap_m=0.0,
                       zone_min_component=600,
                       bearing_convention='positive_right'),
    GATE_MODE_V230_FWD24: dict(zone_profile='gpu_calib_v230',
                               acquisition_mode='forward_then_search',
                               forward_cap_m=FORWARD_ACQUISITION_CAP_M,
                               zone_min_component=600,
                               # Controller turn is +left; the unmirrored
                               # camera puts robot-left on image-left.  The
                               # legacy image-column bearing would turn away
                               # (preflight evidence: PREFLIGHT_AMENDMENT.md).
                               bearing_convention='positive_left'),
    # C constants (`ACQUIRE_MIN_HEIGHT_NORM`, `ACQUIRE_CONFIRM_TICKS`) are
    # evidence-based: see harness/e2ewarp_selfnav.py and
    # experiments/2026-10-19-nav-v230-r2/C_HEIGHT_EVIDENCE.json.  `0.04` was
    # rejected because normal detections at the approved 2.4 m stop point are
    # 0.025-0.0375 tall, and the first tick reaching 0.04 is past the cap.
    GATE_MODE_V230_R2: dict(zone_profile='gpu_calib_v230',
                            acquisition_mode='forward_then_search',
                            forward_cap_m=FORWARD_ACQUISITION_CAP_M,
                            zone_min_component=600,
                            bearing_convention='positive_left',
                            acquire_min_height_norm=ACQUIRE_MIN_HEIGHT_NORM,
                            acquire_confirm_ticks=ACQUIRE_CONFIRM_TICKS,
                            forward_reacquire=True),
    # r3 differs from r2 only in the arrival claim definition (and in nothing
    # else): the same band, the same 2.4 m forward acquisition, the same C gate.
    # The projection arrival option is bound through ARRIVAL_ENV and validated
    # below; the 0.52 m projection and the 1.0 m path fail-safe are frozen.
    GATE_MODE_V230_R3: dict(zone_profile='gpu_calib_v230',
                            acquisition_mode='forward_then_search',
                            forward_cap_m=FORWARD_ACQUISITION_CAP_M,
                            zone_min_component=600,
                            bearing_convention='positive_left',
                            acquire_min_height_norm=ACQUIRE_MIN_HEIGHT_NORM,
                            acquire_confirm_ticks=ACQUIRE_CONFIRM_TICKS,
                            forward_reacquire=True),
    # r4 = r3 + the order-sheet slot aim (see SLOT_BY_ROBOT).  The claim, band,
    # cap and C constants are identical, so any r3/r4 difference is the slot.
    GATE_MODE_V230_R4: dict(zone_profile='gpu_calib_v230',
                            acquisition_mode='forward_then_search',
                            forward_cap_m=FORWARD_ACQUISITION_CAP_M,
                            zone_min_component=600,
                            bearing_convention='positive_left',
                            acquire_min_height_norm=ACQUIRE_MIN_HEIGHT_NORM,
                            acquire_confirm_ticks=ACQUIRE_CONFIRM_TICKS,
                            forward_reacquire=True,
                            slots=True),
    # r5 = r4 + the two-stage slot timing (see SLOT_STAGE2_GROUND_M and
    # SLOT_OFFSET_LIMIT_DEG in harness/e2ewarp_selfnav.py).  Everything else is
    # identical to r4, so any r4/r5 difference is the slot activation timing.
    GATE_MODE_V230_R5: dict(zone_profile='gpu_calib_v230',
                            acquisition_mode='forward_then_search',
                            forward_cap_m=FORWARD_ACQUISITION_CAP_M,
                            zone_min_component=600,
                            bearing_convention='positive_left',
                            acquire_min_height_norm=ACQUIRE_MIN_HEIGHT_NORM,
                            acquire_confirm_ticks=ACQUIRE_CONFIRM_TICKS,
                            forward_reacquire=True,
                            slots=True,
                            slot_stage2_ground_m=SLOT_STAGE2_GROUND_M,
                            slot_offset_limit_deg=SLOT_OFFSET_LIMIT_DEG),
}
DEFAULT_GATE_MODE = GATE_MODE_V1
#: Modes that carry the C acquisition-quality block.  Every other mode stays
#: byte-identical to its frozen condition (no new queue markers are written).
ACQUISITION_QUALITY_MODES = (GATE_MODE_V230_R2, GATE_MODE_V230_R3, GATE_MODE_V230_R4,
                             GATE_MODE_V230_R5)
#: Modes that admit (and require) the r3/r4/r5 projection arrival claim.
PROJECTION_GATE_MODES = (GATE_MODE_V230_R3, GATE_MODE_V230_R4, GATE_MODE_V230_R5)


def gate_robots(solo_robot=None):
    """Execution robot set for this queue: the pair, or one solo diagnostic robot."""
    if solo_robot is None:
        return tuple(ROBOTS)
    solo_robot = str(solo_robot)
    if solo_robot not in ROBOTS:
        raise ValueError('NAV_SOLO_ROBOT_UNKNOWN:' + solo_robot)
    return (solo_robot,)


def slot_assignment(robots=None):
    """Per-robot order-sheet slot for the r4 mode (fail closed on unknown robots)."""
    robots = tuple(robots or ROBOTS)
    missing = [r for r in robots if r not in SLOT_BY_ROBOT]
    if missing:
        raise ValueError('NAV_SLOT_ROBOT_UNKNOWN:' + ','.join(missing))
    return {r: SLOT_BY_ROBOT[r] for r in robots}


def arrival_selection():
    """Resolve the B arrival option from its explicit environment (fail closed).

    Default is the frozen bottom band, so a process without these variables is
    byte-for-byte the old condition.  Both distance candidates are *default OFF*
    and exist only for the approved v230_r2 condition; an unknown value or a
    bad constant fails closed instead of silently falling back.
    """
    from harness.e2ewarp_selfnav import (ARRIVAL_BOTTOM_BAND, ARRIVAL_GROUND_DISTANCE,
                                         ARRIVAL_GROUND_DISTANCE_M, ARRIVAL_MODES,
                                         ARRIVAL_ODOM_PROJECTION_M, ARRIVAL_ODOM_RESIDUAL,
                                         ARRIVAL_ODOM_RESIDUAL_M,
                                         ARRIVAL_PROJECTION_PATH_CAP_M)
    mode = os.environ.get(ARRIVAL_ENV, ARRIVAL_BOTTOM_BAND)
    if mode not in ARRIVAL_MODES:
        raise ValueError('NAV_ARRIVAL_MODE_UNKNOWN:' + str(mode))
    odom = float(os.environ.get(ARRIVAL_ODOM_M_ENV, ARRIVAL_ODOM_RESIDUAL_M))
    ground = float(os.environ.get(ARRIVAL_GROUND_M_ENV, ARRIVAL_GROUND_DISTANCE_M))
    if mode == ARRIVAL_ODOM_RESIDUAL and not odom > 0.0:
        raise ValueError('NAV_ARRIVAL_ODOM_RESIDUAL_INVALID')
    if mode == ARRIVAL_GROUND_DISTANCE and not ground > 0.0:
        raise ValueError('NAV_ARRIVAL_GROUND_DISTANCE_INVALID')
    # r3: the projection threshold (0.52 m, B_A geometry) and the 1.0 m path
    # fail-safe are frozen constants; there is deliberately no environment
    # override, so a result cannot re-tune the claim after the fact.
    return dict(mode=mode, odom_residual_m=odom, ground_distance_m=ground,
                projection_m=ARRIVAL_ODOM_PROJECTION_M,
                projection_path_cap_m=ARRIVAL_PROJECTION_PATH_CAP_M)


def gate_mode(name=None):
    """Resolve the gate mode from an explicit name or the environment.

    Unknown names and unknown environment values fail closed; the default is
    the frozen v1 gate, so a process without the variable is byte-for-byte the
    old condition.
    """
    name = DEFAULT_GATE_MODE if name is None and GATE_MODE_ENV not in os.environ \
        else (name or os.environ.get(GATE_MODE_ENV))
    if name not in GATE_MODES:
        raise ValueError('NAV_GATE_MODE_UNKNOWN:' + str(name))
    value = dict(GATE_MODES[name])
    value['name'] = name
    return value


def pair_lane_spawns(scene_spawns):
    """Two-robot setup spawns in the wide-door lane, x/z/yaw from the scene.

    The scene authors three spawn rows; r1/r2 keep their own z and yaw but move
    to the two wide-door lanes. r3 is dropped from the setup spawns.
    """
    if not isinstance(scene_spawns, dict) or not set(scene_spawns) >= set(ROBOTS):
        raise ValueError('scene spawns must contain r1 and r2')
    out = {}
    for rid in ROBOTS:
        pose = list(scene_spawns[rid])
        if len(pose) != 4:
            raise ValueError('spawn must be x,y,z,yaw')
        out[rid] = [float(pose[0]), float(LANE_Y[rid]), float(pose[2]), float(pose[3])]
    return out


def prune_robots(xml, keep=ROBOTS):
    """Drop every named element of a robot that is not in ``keep``.

    The zone scene builder requires the three production robots on input
    (``sim/research_dispatch_arena.py`` raises 'expected three production
    robots'), so the two-robot gate prunes r3 from the *final* XML, after all
    scene/hardware/contact transforms. Bodies, actuators, welds and any other
    named element with the dropped prefix are removed; nothing else changes.
    """
    keep = tuple(str(k).strip().lower() for k in keep)
    prefixes = tuple(p + '__' for p in ('r1', 'r2', 'r3') if p not in keep)
    root = ET.fromstring(xml)
    removed = []
    for parent in list(root.iter()):
        for child in list(parent):
            name = str(child.get('name') or '')
            references = any(prefix in str(value) for value in child.attrib.values()
                             for prefix in prefixes)
            if any(name.startswith(prefix) for prefix in prefixes) or references:
                removed.append(name or child.tag)
                parent.remove(child)
    if not removed:
        raise ValueError('no robot prefix was pruned; check the XML names')
    return ET.tostring(root, encoding='unicode')


def nav_orders(scenario_orders):
    """Orders this two-robot navigation gate can select (pair orders only)."""
    if not isinstance(scenario_orders, (list, tuple)):
        raise ValueError('scenario orders must be a list')
    out = []
    for order in scenario_orders:
        if not isinstance(order, dict):
            raise ValueError('order must be a mapping')
        if str(order.get('destination_zone', '')).upper() != DESTINATION_ZONE:
            continue
        if int(order.get('required_robots', 0)) != 2:
            continue
        out.append(dict(order))
    if not out:
        raise ValueError('navigation gate requires a two-robot order to zone B')
    return out


def load_calibration(path=None):
    """Load measured own-command odometry calibration; fail closed otherwise."""
    raw = path or os.environ.get(CALIBRATION_ENV) or CALIBRATION_PATH
    path = Path(raw)
    if not path.is_file():
        raise ValueError('NAV_CALIBRATION_MISSING:' + str(path))
    payload = json.loads(path.read_text())
    if payload.get('schema') != CALIBRATION_SCHEMA:
        raise ValueError('NAV_CALIBRATION_SCHEMA_MISMATCH')
    if payload.get('measured') is not True:
        raise ValueError('NAV_CALIBRATION_NOT_MEASURED')
    constants = payload.get('constants') or {}
    forward = constants.get('forward_m_per_pct_s')
    yaw = constants.get('yaw_deg_per_pct_s')
    for name, value in (('forward_m_per_pct_s', forward), ('yaw_deg_per_pct_s', yaw)):
        if isinstance(value, bool) or not isinstance(value, (int, float)) or not value > 0.0:
            raise ValueError('NAV_CALIBRATION_CONSTANT_INVALID:' + name)
    if int(payload.get('measured_n') or 0) <= 0:
        raise ValueError('NAV_CALIBRATION_MEASURED_N_REQUIRED')
    per_robot = payload.get('per_robot') or {}
    if set(per_robot) != set(ROBOTS):
        raise ValueError('NAV_CALIBRATION_PER_ROBOT_REQUIRED')
    for rid, row in per_robot.items():
        for name in ('forward_m_per_pct_s', 'yaw_deg_per_pct_s'):
            value = row.get(name)
            if isinstance(value, bool) or not isinstance(value, (int, float)) or not value > 0.0:
                raise ValueError(f'NAV_CALIBRATION_PER_ROBOT_INVALID:{rid}:{name}')
    for name, key in (('forward', 'forward_m_per_pct_s'), ('yaw', 'yaw_deg_per_pct_s')):
        values = [float(per_robot[rid][key]) for rid in ROBOTS]
        mean = sum(values) / len(values)
        if (max(values) - min(values)) / mean > MAX_REL_SPREAD:
            raise ValueError('NAV_CALIBRATION_INCONSISTENT:' + name)
    source_sha = str(payload.get('source_sha') or '')
    if len(source_sha) != 40 or any(c not in '0123456789abcdef' for c in source_sha):
        raise ValueError('NAV_CALIBRATION_SOURCE_SHA_REQUIRED')
    record = dict(payload)
    record['sha256'] = hashlib.sha256(path.read_bytes()).hexdigest()
    record['path'] = str(path)
    return record


def navigation_factory(robot_id, static=None, **kwargs):
    """Hash-bound factory entry expected by ``--mode nav`` manifests.

    Uses only the calibration record admitted by ``validate_calibration_binding``
    (same bytes, same constants); a file changed after admission cannot alter the
    run (no re-read / TOCTOU).  The appearance band and the acquisition policy
    come from the explicit gate mode (default: the frozen v1 gate).
    """
    from harness.e2ewarp_selfnav import (GpuCalibZoneDetector, OPTION, OwnCommandOdometry,
                                        SelfCentricNavigation)
    calibration = kwargs.pop('calibration', None)
    if kwargs:
        raise ValueError('unexpected navigation factory kwargs: ' + ','.join(sorted(kwargs)))
    if calibration is not None:
        record = calibration
    elif _ADMITTED is not None:
        record = _ADMITTED
    else:
        raise ValueError('NAV_CALIBRATION_NOT_ADMITTED')
    mode = gate_mode()
    constants = record['constants']
    arrival = arrival_selection()
    from harness.e2ewarp_selfnav import (ARRIVAL_BOTTOM_BAND, ARRIVAL_GROUND_DISTANCE,
                                         ARRIVAL_ODOM_PROJECTION, ARRIVAL_ODOM_RESIDUAL)
    if arrival['mode'] != ARRIVAL_BOTTOM_BAND and mode['name'] not in ACQUISITION_QUALITY_MODES:
        raise ValueError('NAV_ARRIVAL_REQUIRES_V230_R2')
    # r3/r4 are the only modes that admit the projection claim, and inside them
    # the projection claim is the only admitted arrival mode (fail closed on a
    # process that forgot the flag).
    if mode['name'] in PROJECTION_GATE_MODES and arrival['mode'] != ARRIVAL_ODOM_PROJECTION:
        raise ValueError('NAV_ARRIVAL_REQUIRES_V230_R3')
    if arrival['mode'] == ARRIVAL_ODOM_PROJECTION and mode['name'] not in PROJECTION_GATE_MODES:
        raise ValueError('NAV_ARRIVAL_REQUIRES_V230_R3')
    if mode['name'] in SLOT_GATE_MODES:
        # The r4/r5 order sheet must name this robot's slot; a run that lost it
        # would silently be r3 (or r4 with different markers).
        slots = (static or {}).get('slots') or {}
        if not isinstance(slots, dict) or slots.get(robot_id) not in SLOTS:
            raise ValueError('NAV_SLOT_REQUIRED:' + str(robot_id))
        if slots.get(robot_id) != SLOT_BY_ROBOT[robot_id]:
            raise ValueError('NAV_SLOT_MISMATCH:' + str(robot_id))
    extra = {}
    if mode['name'] in ACQUISITION_QUALITY_MODES:
        extra.update(acquire_min_height_norm=mode['acquire_min_height_norm'],
                     acquire_confirm_ticks=mode['acquire_confirm_ticks'],
                     forward_reacquire=mode['forward_reacquire'],
                     arrival_mode=arrival['mode'],
                     arrival_odom_residual_m=arrival['odom_residual_m'],
                     arrival_ground_distance_m=(arrival['ground_distance_m']
                                                if arrival['mode'] == ARRIVAL_GROUND_DISTANCE
                                                else None))
        if arrival['mode'] == ARRIVAL_ODOM_PROJECTION:
            extra.update(arrival_projection_m=arrival['projection_m'],
                         arrival_projection_path_cap_m=arrival['projection_path_cap_m'])
        if mode['name'] == GATE_MODE_V230_R5:
            # r5 two-stage slot: fixed code constants, bound into the run so a
            # process cannot silently run r4 timing under an r5 queue.
            extra.update(slot_stage2_ground_m=mode['slot_stage2_ground_m'])
    return SelfCentricNavigation(
        robot_id, static, option=OPTION,
        detector=GpuCalibZoneDetector(profile=mode['zone_profile'],
                                       bearing_convention=mode['bearing_convention']),
        odometry=OwnCommandOdometry(forward_m_per_pct_s=constants['forward_m_per_pct_s'],
                                    yaw_deg_per_pct_s=constants['yaw_deg_per_pct_s']),
        destination_kind=DESTINATION_KIND,
        acquisition_mode=mode['acquisition_mode'],
        forward_cap_m=mode['forward_cap_m'], **extra)


def gate_queue_fields(seed, calibration=None, sim_budget_s=SIM_BUDGET_S, robots=None):
    """Scene/adaptor markers written by ``--prepare --mode nav`` (audit only)."""
    record = calibration or load_calibration()
    mode = gate_mode()
    robots = tuple(robots or ROBOTS)
    fields = dict(nav_scene=NAV_SCENARIO, nav_map='zone_wide_two_doors_final_v3',
                nav_robots=list(robots), nav_spawn_y={r: LANE_Y[r] for r in robots},
                nav_destination_kind=DESTINATION_KIND,
                nav_static_map_input=False, nav_cargo_spawned=False,
                nav_sim_budget_s=float(sim_budget_s), nav_leader_rotation=True,
                nav_gate_mode=mode['name'],
                nav_zone_profile=mode['zone_profile'],
                nav_acquisition=mode['acquisition_mode'],
                nav_forward_cap_m=float(mode['forward_cap_m']),
                nav_zone_min_component=int(mode['zone_min_component']),
                nav_bearing_convention=mode['bearing_convention'],
                nav_calibration=dict(path=record['path'], sha256=record['sha256'],
                                     source_sha=record['source_sha'],
                                     constants=dict(record['constants'])))
    if len(robots) == 1:
        fields['nav_solo_robot'] = robots[0]
    if mode['name'] in ACQUISITION_QUALITY_MODES:
        arrival = arrival_selection()
        fields.update(nav_acquire_min_height_norm=float(mode['acquire_min_height_norm']),
                      nav_acquire_confirm_ticks=int(mode['acquire_confirm_ticks']),
                      nav_forward_reacquire=bool(mode['forward_reacquire']),
                      nav_arrival_mode=arrival['mode'],
                      nav_arrival_odom_residual_m=float(arrival['odom_residual_m']),
                      nav_arrival_ground_distance_m=float(arrival['ground_distance_m']))
        if mode['name'] in PROJECTION_GATE_MODES:
            # r3/r4-only frozen markers: the projection threshold and its
            # fail-safe path cap.  v230_r2 queues stay byte-identical.
            fields.update(nav_arrival_odom_projection_m=float(arrival['projection_m']),
                          nav_arrival_projection_path_cap_m=float(arrival['projection_path_cap_m']))
        if mode['name'] in SLOT_GATE_MODES:
            # Order-sheet per-robot slot (r4/r5).  v1/fwd24/r2/r3 queues carry
            # no slot marker at all, so their bytes are unchanged.
            fields.update(nav_slots=slot_assignment(robots))
        if mode['name'] == GATE_MODE_V230_R5:
            # r5-only two-stage slot markers (threshold and clamp are frozen code
            # constants; r4 queues stay byte-identical without them).
            fields.update(nav_slot_stage2_ground_m=float(mode['slot_stage2_ground_m']),
                          nav_slot_offset_limit_deg=float(mode['slot_offset_limit_deg']))
    return fields


def validate_gate_queue(queue):
    """Re-check the nav-gate scene/budget before any physics import."""
    if queue.get('nav_scene') != NAV_SCENARIO:
        raise ValueError('NAV_GATE_SCENE_MISMATCH')
    if queue.get('nav_map') != 'zone_wide_two_doors_final_v3':
        raise ValueError('NAV_GATE_MAP_MISMATCH')
    robots = tuple(queue.get('nav_robots') or ())
    if robots not in (ROBOTS,) + tuple((r,) for r in ROBOTS):
        raise ValueError('NAV_GATE_ROBOTS_REQUIRED')
    if dict(queue.get('nav_spawn_y') or {}) != {r: LANE_Y[r] for r in robots}:
        raise ValueError('NAV_GATE_SPAWN_LANE_MISMATCH')
    if queue.get('nav_destination_kind') != DESTINATION_KIND:
        raise ValueError('NAV_GATE_DESTINATION_MISMATCH')
    if queue.get('nav_static_map_input') is not False or queue.get('nav_cargo_spawned') is not False:
        raise ValueError('NAV_GATE_INPUT_BOUNDARY')
    budget = queue.get('nav_sim_budget_s')
    if isinstance(budget, bool) or not isinstance(budget, (int, float)) or not 0. < budget <= MAX_SIM_BUDGET_S:
        raise ValueError('NAV_GATE_SIM_BUDGET_INVALID')
    if float(queue.get('sim_budget_s', -1.)) != float(budget):
        raise ValueError('NAV_GATE_SIM_BUDGET_MISMATCH')
    record = queue.get('nav_calibration') or {}
    if len(str(record.get('sha256') or '')) != 64:
        raise ValueError('NAV_GATE_CALIBRATION_SHA_REQUIRED')
    if float((record.get('constants') or {}).get('forward_m_per_pct_s', 0.)) <= 0.:
        raise ValueError('NAV_GATE_CALIBRATION_CONSTANTS_REQUIRED')
    # Explicit gate-mode binding.  A legacy queue without these markers is
    # admitted only as the frozen v1 gate; a queue prepared for the approved
    # v230_fwd24 mode must carry all four markers and must match the process
    # environment (so prepare and execute cannot silently disagree).
    mode = gate_mode()
    admitted = queue.get('nav_gate_mode', GATE_MODE_V1)
    if admitted != mode['name']:
        raise ValueError('NAV_GATE_MODE_MISMATCH')
    expected = GATE_MODES[admitted]
    if queue.get('nav_zone_profile', expected['zone_profile']) != mode['zone_profile']:
        raise ValueError('NAV_GATE_ZONE_PROFILE_MISMATCH')
    if queue.get('nav_acquisition', expected['acquisition_mode']) != mode['acquisition_mode']:
        raise ValueError('NAV_GATE_ACQUISITION_MISMATCH')
    try:
        forward_cap = float(queue.get('nav_forward_cap_m', 0.0))
    except (TypeError, ValueError):
        raise ValueError('NAV_GATE_FORWARD_CAP_INVALID') from None
    if abs(forward_cap - float(mode['forward_cap_m'])) > 1e-9:
        raise ValueError('NAV_GATE_FORWARD_CAP_MISMATCH')
    try:
        min_component = int(queue.get('nav_zone_min_component', 600))
    except (TypeError, ValueError):
        raise ValueError('NAV_GATE_MIN_COMPONENT_INVALID') from None
    if min_component != int(mode['zone_min_component']):
        raise ValueError('NAV_GATE_MIN_COMPONENT_MISMATCH')
    if queue.get('nav_bearing_convention', expected['bearing_convention']) != \
            mode['bearing_convention']:
        raise ValueError('NAV_GATE_BEARING_CONVENTION_MISMATCH')
    # C acquisition-quality markers: required and exact for the approved
    # v230_r2/v230_r3 modes, absent for every frozen mode (so a v1/v230_fwd24
    # queue is byte-identical to its old condition).
    if mode['name'] in ACQUISITION_QUALITY_MODES:
        try:
            min_height = float(queue['nav_acquire_min_height_norm'])
            confirm = int(queue['nav_acquire_confirm_ticks'])
        except (KeyError, TypeError, ValueError):
            raise ValueError('NAV_ACQUIRE_QUALITY_MARKERS_REQUIRED') from None
        if abs(min_height - float(mode['acquire_min_height_norm'])) > 1e-9:
            raise ValueError('NAV_ACQUIRE_MIN_HEIGHT_MISMATCH')
        if confirm != int(mode['acquire_confirm_ticks']):
            raise ValueError('NAV_ACQUIRE_CONFIRM_TICKS_MISMATCH')
        if bool(queue.get('nav_forward_reacquire')) != bool(mode['forward_reacquire']):
            raise ValueError('NAV_FORWARD_REACQUIRE_MISMATCH')
        arrival = arrival_selection()
        if queue.get('nav_arrival_mode') != arrival['mode']:
            raise ValueError('NAV_ARRIVAL_MODE_MISMATCH')
        if arrival['mode'] == ARRIVAL_ODOM_PROJECTION:
            # r3/r4: the projection claim only exists in these modes, and its
            # frozen threshold/fail-safe markers must match the code constants.
            if mode['name'] not in PROJECTION_GATE_MODES:
                raise ValueError('NAV_ARRIVAL_REQUIRES_V230_R3')
            if abs(float(queue.get('nav_arrival_odom_projection_m', -1.0))
                   - float(arrival['projection_m'])) > 1e-9:
                raise ValueError('NAV_ARRIVAL_ODOM_PROJECTION_MISMATCH')
            if abs(float(queue.get('nav_arrival_projection_path_cap_m', -1.0))
                   - float(arrival['projection_path_cap_m'])) > 1e-9:
                raise ValueError('NAV_ARRIVAL_PROJECTION_PATH_CAP_MISMATCH')
        else:
            if mode['name'] in PROJECTION_GATE_MODES:
                raise ValueError('NAV_ARRIVAL_REQUIRES_V230_R3')
            if abs(float(queue.get('nav_arrival_odom_residual_m', -1.0))
                   - float(arrival['odom_residual_m'])) > 1e-9:
                raise ValueError('NAV_ARRIVAL_ODOM_RESIDUAL_MISMATCH')
            if abs(float(queue.get('nav_arrival_ground_distance_m', -1.0))
                   - float(arrival['ground_distance_m'])) > 1e-9:
                raise ValueError('NAV_ARRIVAL_GROUND_DISTANCE_MISMATCH')
    else:
        if queue.get('nav_arrival_mode', 'bottom_band') != 'bottom_band':
            raise ValueError('NAV_ARRIVAL_REQUIRES_V230_R2')
        if arrival_selection()['mode'] not in ('bottom_band',):
            raise ValueError('NAV_ARRIVAL_REQUIRES_V230_R2')
    # r4/r5 order-sheet slots and the solo diagnostic are slot-mode markers.
    if mode['name'] in SLOT_GATE_MODES:
        if dict(queue.get('nav_slots') or {}) != slot_assignment(robots):
            raise ValueError('NAV_SLOTS_REQUIRED')
    elif queue.get('nav_slots') is not None:
        raise ValueError('NAV_SLOTS_REQUIRE_V230_R4')
    if mode['name'] == GATE_MODE_V230_R5:
        # The two-stage threshold and clamp are frozen code constants; the queue
        # must carry the exact values and no other mode may carry them.
        try:
            stage2 = float(queue['nav_slot_stage2_ground_m'])
            limit = float(queue['nav_slot_offset_limit_deg'])
        except (KeyError, TypeError, ValueError):
            raise ValueError('NAV_SLOT_STAGE2_MARKERS_REQUIRED') from None
        if abs(stage2 - float(mode['slot_stage2_ground_m'])) > 1e-9:
            raise ValueError('NAV_SLOT_STAGE2_GROUND_MISMATCH')
        if abs(limit - float(mode['slot_offset_limit_deg'])) > 1e-9:
            raise ValueError('NAV_SLOT_OFFSET_LIMIT_MISMATCH')
    elif (queue.get('nav_slot_stage2_ground_m') is not None
          or queue.get('nav_slot_offset_limit_deg') is not None):
        raise ValueError('NAV_SLOT_STAGE2_REQUIRE_V230_R5')
    if len(robots) == 1:
        if mode['name'] not in SLOT_GATE_MODES:
            raise ValueError('NAV_SOLO_REQUIRES_V230_R4')
        if queue.get('nav_solo_robot') != robots[0]:
            raise ValueError('NAV_SOLO_MARKER_MISMATCH')
    elif queue.get('nav_solo_robot') is not None:
        raise ValueError('NAV_SOLO_MARKER_MISMATCH')
    return queue


def validate_calibration_binding(queue):
    """The artifact read by the factory must be the one the queue admitted."""
    global _ADMITTED
    record = load_calibration()
    admitted = (queue.get('nav_calibration') or {}).get('sha256')
    if record['sha256'] != admitted:
        raise ValueError('NAV_CALIBRATION_CHANGED')
    _ADMITTED = record
    return record


def eval_geometry(scene, spawns, robot_qpos_adr):
    """Eval-only geometry written next to the raw state (never a controller input)."""
    static = scene.config['static_map']
    zone = static['regions']['zone_' + DESTINATION_ZONE]
    return dict(schema='ugrp.e2ewarp.nav_eval_geometry.v1', eval_only=True,
                scene_id=scene.config.get('scenario_setup', {}).get('scenario_id', NAV_SCENARIO),
                map_id=static.get('map_id'), source_sha=None,
                spawns={k: list(v) for k, v in spawns.items()},
                robot_qpos_adr={k: int(v) for k, v in robot_qpos_adr.items()},
                destination=dict(kind=DESTINATION_KIND, zone=DESTINATION_ZONE,
                                 center_m=list(zone['center_m']),
                                 half_extents_m=list(zone['half_extents_m'])))
