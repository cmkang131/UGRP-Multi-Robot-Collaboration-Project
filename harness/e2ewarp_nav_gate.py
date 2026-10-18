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
  (-2.25/-0.85/0.55) leave zone B invisible from the two driven rows and the
  controller would hold forever with ``no_destination``.

Odometry calibration: ``OwnCommandOdometry`` requires *measured* metres and
degrees per percent-second. The constants are read from a calibration artifact
produced by an eval-only GPU calibration run; a missing/unmeasured artifact
fails closed. No default constants are invented here.
"""
from __future__ import annotations

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
CALIBRATION_SCHEMA = 'ugrp.e2ewarp.nav_calibration.v1'
CALIBRATION_ENV = 'E2EWARP_NAV_CALIBRATION'
CALIBRATION_PATH = ROOT / 'configs/e2ewarp/nav_gate_calibration.json'


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
    source_sha = str(payload.get('source_sha') or '')
    if len(source_sha) != 40 or any(c not in '0123456789abcdef' for c in source_sha):
        raise ValueError('NAV_CALIBRATION_SOURCE_SHA_REQUIRED')
    record = dict(payload)
    record['sha256'] = hashlib.sha256(path.read_bytes()).hexdigest()
    record['path'] = str(path)
    return record


def navigation_factory(robot_id, static=None, **kwargs):
    """Hash-bound factory entry expected by ``--mode nav`` manifests."""
    from harness.e2ewarp_selfnav import (GpuCalibZoneDetector, OPTION, OwnCommandOdometry,
                                        SelfCentricNavigation)
    calibration = kwargs.pop('calibration', None)
    if kwargs:
        raise ValueError('unexpected navigation factory kwargs: ' + ','.join(sorted(kwargs)))
    record = calibration or load_calibration()
    constants = record['constants']
    return SelfCentricNavigation(
        robot_id, static, option=OPTION,
        detector=GpuCalibZoneDetector(),
        odometry=OwnCommandOdometry(forward_m_per_pct_s=constants['forward_m_per_pct_s'],
                                    yaw_deg_per_pct_s=constants['yaw_deg_per_pct_s']),
        destination_kind=DESTINATION_KIND)


def gate_queue_fields(seed, calibration=None):
    """Scene/adaptor markers written by ``--prepare --mode nav`` (audit only)."""
    record = calibration or load_calibration()
    return dict(nav_scene=NAV_SCENARIO, nav_map='zone_wide_two_doors_final_v3',
                nav_robots=list(ROBOTS), nav_spawn_y=dict(LANE_Y),
                nav_destination_kind=DESTINATION_KIND,
                nav_static_map_input=False, nav_cargo_spawned=False,
                nav_sim_budget_s=SIM_BUDGET_S, nav_leader_rotation=True,
                nav_calibration=dict(path=record['path'], sha256=record['sha256'],
                                     source_sha=record['source_sha'],
                                     constants=dict(record['constants'])))


def validate_gate_queue(queue):
    """Re-check the nav-gate scene/budget before any physics import."""
    if queue.get('nav_scene') != NAV_SCENARIO:
        raise ValueError('NAV_GATE_SCENE_MISMATCH')
    if queue.get('nav_map') != 'zone_wide_two_doors_final_v3':
        raise ValueError('NAV_GATE_MAP_MISMATCH')
    if tuple(queue.get('nav_robots') or ()) != ROBOTS:
        raise ValueError('NAV_GATE_ROBOTS_REQUIRED')
    if dict(queue.get('nav_spawn_y') or {}) != LANE_Y:
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
    return queue


def validate_calibration_binding(queue):
    """The artifact read by the factory must be the one the queue admitted."""
    record = load_calibration()
    admitted = (queue.get('nav_calibration') or {}).get('sha256')
    if record['sha256'] != admitted:
        raise ValueError('NAV_CALIBRATION_CHANGED')
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
