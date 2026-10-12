"""RPP lookahead/rotate-to-heading rules on the existing measured pulse port.

Nav2 Jazzy's radial first-point search and stateless rotation sign; no turn
hysteresis. Continuous curvature/acceleration is NOT a calibrated mixed-axis
pulse: tracking uses a positive forward pulse then fresh feedback. This is a
lookahead/heading port, not a full ROS RPP velocity controller. References and
the explicit grid-point (rather than circle-interpolated) choice are recorded
in experiments/2026-10-11-e2e10-rpp-lookahead/summary.json.
"""
import math
import numpy as np
from harness.zone_solo_cyan_path_heading import select
from harness.zone_solo_cyan_pulse_cal import action_of

OPTION = 'rpp_v1'
PARAMS = dict(lookahead_dist=.6, min_lookahead_dist=.3, max_lookahead_dist=.9,
              lookahead_time=1.5, use_velocity_scaled_lookahead_dist=False,
              use_rotate_to_heading=True, rotate_to_heading_min_angle=.785)


def lookahead_distance(issued_speed=0., *, velocity_scaled=False):
    if not math.isfinite(issued_speed):
        raise ValueError('finite issued-command speed required')
    if not velocity_scaled:
        return PARAMS['lookahead_dist']
    return min(PARAMS['max_lookahead_dist'], max(PARAMS['min_lookahead_dist'],
               abs(issued_speed)*PARAMS['lookahead_time']))


def carrot(path, pose, distance):
    return next((p for p in path if math.dist(pose[:2], p) >= distance), path[-1])


def command(plan, pose, profiles, *, robot_id, rotate_min_angle=None):
    if rotate_min_angle is not None and (not math.isfinite(rotate_min_angle) or not 0<rotate_min_angle<=math.pi):
        raise ValueError('finite positive path rotation threshold required')
    if plan.get('coordinate_frame') != f'{robot_id}/own_odom':
        raise ValueError('own plan frame required')
    if len(pose) != 3 or not all(math.isfinite(v) for v in pose):
        raise ValueError('finite own pose required')
    path = plan.get('path_m', [])
    if not path or plan.get('status') not in ('goal_approach','goal_reobserve','frontier'):
        return dict(kind='hold'), dict(reason='no_path', path_follow=OPTION)
    if any(len(p) != 2 or not all(math.isfinite(v) for v in p) for p in path):
        raise ValueError('finite own path required')
    distance = lookahead_distance()
    point = carrot(path, pose, distance)
    c, s = math.cos(pose[2]), math.sin(pose[2])
    error = np.array([[c,s],[-s,c]]) @ (np.asarray(point)-pose[:2])
    goal_distance = math.dist(pose[:2], path[-1])
    yaw = pose[2]-plan.get('heading_rad',pose[2])
    if goal_distance <= .03 and abs(math.atan2(math.sin(yaw),math.cos(yaw))) <= .06:
        p, score = None, dict(phase='goal_reached')
    else:
        p, score = select(profiles,False,error,yaw,goal_distance,
            path_rotate_min_angle=PARAMS['rotate_to_heading_min_angle'] if rotate_min_angle is None else rotate_min_angle,final_alignment_m=.03)
    return (dict(kind='hold') if p is None else action_of(p)), dict(
        path_follow=OPTION, lookahead_m=distance, carrot_m=list(point),
        carrot_distance_m=math.dist(pose[:2],point), **score)


def install(goal, option='off'):
    if option == 'off':
        return goal
    if option != OPTION:
        raise ValueError('UNKNOWN_PATH_FOLLOW')
    goal.heading_host.path_follow = option
    return goal
