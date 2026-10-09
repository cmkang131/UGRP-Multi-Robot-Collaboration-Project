"""Offline OwnMapNavigator plan-to-command adapter; no new map admission.

S2/S3/S4 and this adapter share the heading selector. An embedding host still
owns the measured pulse/coast/fresh-feedback schedule and physical admission.
"""
import math

from harness.path_heading_policy import DEFAULT
from harness.zone_solo_cyan_path_heading import select_waypoint
from harness.zone_solo_cyan_pulse_cal import action_of


def command(plan, own_pose, profiles, *, robot_id, loaded=False,
            heading_mode=DEFAULT, legacy_action=None):
    if heading_mode == 'off':
        return legacy_action  # don't inspect off inputs or rewrite their bytes
    if heading_mode != DEFAULT:
        raise ValueError('unknown heading_mode')
    if plan.get('coordinate_frame') != f'{robot_id}/own_odom':
        raise ValueError('own plan frame required')
    if len(own_pose) != 3 or not all(math.isfinite(v) for v in own_pose):
        raise ValueError('finite own pose estimate required')
    path = plan.get('path_m', [])
    if plan.get('status') not in ('goal_approach', 'goal_reobserve', 'frontier') or not path:
        return dict(kind='hold')
    if any(len(p) != 2 or not all(math.isfinite(v) for v in p) for p in path):
        raise ValueError('finite own path required')
    point = next((p for p in path if math.dist(own_pose[:2], p) >= .035), path[-1])
    final_yaw = plan.get('heading_rad', own_pose[2])
    if math.dist(own_pose[:2], path[-1]) <= .03 and abs(
            math.atan2(math.sin(own_pose[2]-final_yaw), math.cos(own_pose[2]-final_yaw))) <= .06:
        return dict(kind='hold')
    p, _ = select_waypoint(profiles, loaded, own_pose, point, path[-1], goal_yaw=final_yaw)
    return dict(kind='hold') if p is None else action_of(p)
