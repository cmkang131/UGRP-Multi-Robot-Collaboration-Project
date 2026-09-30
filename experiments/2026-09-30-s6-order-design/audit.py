"""T11 evaluator-only static counterexamples. No scene, renderer or controller.

Run from the repository root with PYTHONPATH=.; --output refuses overwrites.
An angular sample that clears is not a continuous or physical success proof.
The analytic radius bound in approach_report covers the whole heading circle
for the legacy proxies; final-v3 complete arm/contact geometry is unsupported.
"""
from __future__ import annotations

import argparse
import hashlib
import importlib.abc
import json
import math
from pathlib import Path
import socket
import sys


class StaticOnly(importlib.abc.MetaPathFinder):
    def find_spec(self, fullname, path=None, target=None):
        if fullname.split('.')[0] in {'mujoco', 'torch', 'openai', 'google', 'glfw'}:
            raise RuntimeError(f'T11 static audit forbids {fullname}')
        return None


def forbidden(*args, **kwargs):
    raise RuntimeError('T11 static audit forbids network/render')


from harness import static_keepouts as ko
from harness import zone_map_schematic as ms
from harness import zone_team_footprint as tf
from harness.zone_scenario_feasibility import (
    carry_route, check_free_robot_access, item_rects, scenario_items,
)
from sim.masterpi_geometry_v3 import OFFICIAL_TOTAL_LENGTH_M, OFFICIAL_TOTAL_WIDTH_M, YAW_AXIS_X_M
from sim.zone_cargo import CATALOGUE, GRASP_RADIUS_M

ROOT = Path(__file__).resolve().parents[2]
SCENARIO = 'configs/zone_study_scenarios_v2/s6_novel_relation_v2.json'
MAP = 'maps/zones_final/zone_wide_two_doors_final_v1.json'
SOURCE_FILES = (
    SCENARIO, MAP, 'harness/static_keepouts.py', 'harness/zone_team_footprint.py',
    'harness/zone_scenario_feasibility.py', 'harness/zone_map_schematic.py',
    'harness/zone_study_scenarios.py', 'harness/zone_study_inputs.py',
    'harness/zone_study_contract.py', 'sim/zone_cargo.py',
    'sim/masterpi_geometry_v3.py', 'sim/masterpi_robot_models.py',
    'sim/masterpi_model_v3.py',
)


def enable_static_guard():
    """Opt-in process guard; merely importing this audit does not affect other tests."""
    sys.meta_path.insert(0, StaticOnly())
    socket.socket.connect = forbidden
    socket.create_connection = forbidden
    ms.render_schematic = forbidden


def inputs():
    return json.loads((ROOT / SCENARIO).read_text()), json.loads((ROOT / MAP).read_text())


def source_hashes():
    paths = set(SOURCE_FILES)
    for directory in ('configs/zone_study_scenarios', 'configs/zone_study_scenarios_v2'):
        paths.update(str(p.relative_to(ROOT)) for p in (ROOT / directory).glob('s[1-6]*.json'))
    return {p: hashlib.sha256((ROOT / p).read_bytes()).hexdigest() for p in sorted(paths)}


def can_station(heading, radius=GRASP_RADIUS_M, center=(1.45, -.85)):
    if not all(math.isfinite(v) for v in (heading, radius, *center)) or radius <= 0:
        raise ValueError('finite heading and positive finite radius required')
    return (center[0] - radius * math.cos(heading), center[1] - radius * math.sin(heading), heading)


def approach_report(scenario, static_map):
    items = scenario_items(scenario)
    can = next(item for item in items if item.item_id == 'can_1')
    obstacles = ko.keepout_rects(static_map, perimeter=True) + tuple(
        r for item in items if item.item_id != 'can_1' for r in item_rects(item.kind, item.pose)
    )
    legacy = tf.carrier_polygons((0., 0., 0.))
    # Drawing rectangle is a sensitivity proxy, NOT a measured v3 footprint.
    v3_proxy = [tf.centred_rect(0., 0., OFFICIAL_TOTAL_LENGTH_M / 2, OFFICIAL_TOTAL_WIDTH_M / 2)]
    profiles = {
        'disc_017': ([ko.disc_footprint(.17)], GRASP_RADIUS_M),
        'disc_021': ([ko.disc_footprint(.21)], GRASP_RADIUS_M),
        'legacy_chassis_arm': (legacy, GRASP_RADIUS_M),
        'v3_drawing_rectangle_only': (v3_proxy, GRASP_RADIUS_M + YAW_AXIS_X_M),
    }
    rows = {}
    for name, (parts, radius) in profiles.items():
        good = []
        cardinal = {}
        for degree in range(360):
            pose = can_station(math.radians(degree), radius, can.pose[:2])
            clear = all(ko.pose_clear(pose, part, obstacles, bounds=static_map['bounds_m']) for part in parts)
            if clear:
                good.append(degree)
            if degree % 90 == 0:
                cardinal[str(degree)] = {'base_pose_m_rad': list(pose), 'station_clear': clear}
        # A circle centred on can bounds the entire rotated robot at ALL headings.
        orbit_radius = max(math.hypot(x - radius, y) for p in parts for x, y in p)
        nearest = min(ko.rect_distance(can.pose[:2], r) for r in obstacles)
        rows[name] = {
            'station_radius_m': radius, 'clear_heading_samples_deg': good,
            'cardinal': cardinal, 'sample_count': 360,
            'all_heading_proxy_clear_by_radius_bound': orbit_radius < nearest,
            'can_centred_envelope_radius_m': orbit_radius,
            'nearest_obstacle_distance_from_can_m': nearest,
            'spawn_to_station_route': 'unmeasured', 'physical_grasp': 'unmeasured',
        }
    stations, findings = check_free_robot_access(static_map, items)
    return {'profiles': rows, 'legacy_station_check': stations['can_1'],
            'legacy_findings': [f.code for f in findings if f.item_id == 'can_1'],
            'final_v3_complete_footprint': 'unsupported: arm posture/collision envelope not measured'}


def pivot_pose(start, local_pivot, delta):
    if len(local_pivot) != 2 or not all(math.isfinite(v) for v in (*start, *local_pivot, delta)):
        raise ValueError('finite pose, pivot XY and angle required')
    px, py = tf.transform([local_pivot], start)[0]
    c, s = math.cos(start[2] + delta), math.sin(start[2] + delta)
    return (px - c * local_pivot[0] + s * local_pivot[1],
            py - s * local_pivot[0] - c * local_pivot[1], start[2] + delta)


def pivot_report(scenario, static_map):
    items = scenario_items(scenario)
    beam = next(item for item in items if item.item_id == 'beam_1')
    walls = ko.keepout_rects(static_map, perimeter=True)
    cargo = {item.item_id: item_rects(item.kind, item.pose) for item in items if item.item_id != 'beam_1'}
    bay = next(b for b in ms.pickup_bays(static_map) if b['bay_id'] == 'P2')
    slot = next(s for s in bay['slots'] if s['slot_id'] == 'P2-2')
    grip = next(g for g in CATALOGUE['long_beam'].grasps if g.role == 'end_pos')
    pivots = {'end_pos_contact': grip.grip_xyz[:2], 'centre': (0., 0.)}
    result = []
    for name, pivot in pivots.items():
        for direction in (-1, 1):
            for margin in (0., .03):
                footprint = tf.team_footprint('long_beam', margin=margin)
                poses = [pivot_pose(beam.pose, pivot, math.radians(direction * d)) for d in range(91)]
                collisions = {}
                for label, rects in {'walls': walls, **cargo}.items():
                    hits = [direction * d for d, pose in enumerate(poses)
                            if not tf.pose_clear(pose, footprint, rects, bounds=static_map['bounds_m'])]
                    collisions[label] = {'hit_samples': len(hits), 'first_hit_deg': hits[0] if hits else None}
                containment = {}
                for label, region in (('P2', bay), ('P2-2', slot)):
                    containment[label] = all(tf.polygons_inside_rect(footprint.at(pose), region['center_m'],
                                                                     region['half_extents_m']) for pose in poses)
                end = poses[-1]
                stations = {role: [*tf.transform([offset[:2]], end)[0], end[2] + offset[2]]
                            for role, offset in footprint.stations.items()}
                result.append({'pivot': name, 'delta_deg': direction * 90, 'margin_m': margin,
                               'fixed_world_point_m': list(tf.transform([pivot], beam.pose)[0]),
                               'end_beam_pose_m_rad': list(end), 'end_base_poses_m_rad': stations,
                               'obstacle_sweep': collisions, 'all_samples_inside': containment,
                               'sample_step_deg': 1, 'continuous_physical_clearance': 'unmeasured'})
    return result


def route_report(scenario, static_map):
    items = scenario_items(scenario)
    out = {}
    for item in items:
        obstacles = tuple(r for other in items if other.item_id != item.item_id
                          for r in item_rects(other.kind, other.pose))
        route = carry_route(static_map, item, obstacles=obstacles)
        authored = tf.swept_clear(item.pose, route.path[0], item.footprint(),
                                  ko.keepout_rects(static_map, perimeter=True) + obstacles,
                                  bounds=static_map['bounds_m']) if route.path else False
        out[item.item_id] = {'verdict': route.verdict, 'reason_ko': route.reason_ko,
                             'path_m_rad': route.path, 'authored_start_to_first_sweep': authored,
                             'includes_other_initial_cargo': True, 'spawn_approach': 'unmeasured'}
    return out


def main():
    enable_static_guard()
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output', type=Path, required=True)
    args = parser.parse_args()
    if args.output.exists():
        raise FileExistsError(args.output)
    before = source_hashes()
    scenario, static_map = inputs()
    report = {'scope': 'evaluator_only_static_counterexamples', 'local_sim_seconds': 0,
              'student_trials': 0, 'local_model_calls': 0, 'source_sha256': before,
              'approaches': approach_report(scenario, static_map),
              'pivots': pivot_report(scenario, static_map), 'routes': route_report(scenario, static_map),
              'lower_regrasp': 'unsupported: placement/path/roles not defined',
              'final_v3_physics': 'unmeasured'}
    if source_hashes() != before:
        raise RuntimeError('source changed during audit')
    args.output.parent.mkdir(parents=True, exist_ok=True)
    with args.output.open('x') as stream:
        json.dump(report, stream, ensure_ascii=False, indent=2, allow_nan=False)
        stream.write('\n')
    print(json.dumps({'output': str(args.output), 'routes': {k: v['verdict'] for k, v in report['routes'].items()},
                      'local_sim_seconds': 0}, ensure_ascii=False))


if __name__ == '__main__':
    main()
