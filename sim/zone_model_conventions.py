"""Static station/dock conventions selected by a scene's robot model."""
from __future__ import annotations

import copy
import math

from sim.masterpi_robot_models import LEGACY_SCENE_ROBOT_MODEL, station_grasp_convention
from sim.zone_start_dock import spawn_layout as legacy_spawn_layout


def convention(scene_or_static):
    config = getattr(scene_or_static, 'config', scene_or_static)
    return station_grasp_convention(config.get('robot_model', LEGACY_SCENE_ROBOT_MODEL))


def station_offset(scene_or_static, kind, role):
    from harness.zone_team_footprint import grasps
    radius = convention(scene_or_static)['station_radius_m']
    for grasp in grasps(kind):
        if grasp.role == role:
            x, y, _ = grasp.grip_xyz
            yaw = grasp.approach_yaw
            return x - radius * math.cos(yaw), y - radius * math.sin(yaw), yaw
    raise ValueError(f'{kind} has no grasp role {role!r}')


def spawn_layout(static):
    profile = convention(static)
    if profile['robot_model'] == 'masterpi_v2':
        return legacy_spawn_layout(static)
    # Keep the authored arm-axis column: move the v3 chassis back by its mount.
    parent = copy.deepcopy(static)
    dock = parent.pop('start_dock', None)
    parent['map_id'] = static['parent_scene']['map_id']
    value = legacy_spawn_layout(parent)
    if dock is not None:
        value.update(spawn_x=dock['spawn_x_m'], spawn_rows_y=tuple(dock['spawn_rows_y_m']))
    value['spawn_x'] -= profile['arm_mount_x_m']
    return value


def apply_spawn_layout(config):
    spec = spawn_layout(config['static_map'])
    if sorted(p[1] for p in config['setup_only']['spawns'].values()) != sorted(spec['spawn_rows_y']):
        raise ValueError('v3 dock requires unchanged seeded row assignment')
    for pose in config['setup_only']['spawns'].values():
        pose[0] = spec['spawn_x']


def static_spawn_keepouts(static):
    from sim.zone_start_dock import static_spawn_keepouts as legacy_keepouts
    profile = convention(static)
    if profile['robot_model'] == 'masterpi_v2':
        return legacy_keepouts(static)
    spec = spawn_layout(static)
    # Includes the forward arm mount conservatively; not a measured v3 envelope.
    radius = .17 + profile['arm_mount_x_m']
    return [{'id': f'spawn_row_{i}', 'center_m': [float(spec['spawn_x']), float(y)],
             'radius_m': radius, 'source': 'static_layout_idle_spawn_masterpi_v3'}
            for i, y in enumerate(spec['spawn_rows_y'])]
