"""Opt-in RPP pulse cadence, stable replanning and remembered search sectors.

RPP curvature/goal scaling controls the rate of EXISTING calibrated pulses,
not new PWM/durations or mixed-axis dynamics. The one inter-frame continuation
uses only the last own image/map and the actually issued pulse's prediction.
It still passes through the body skill's RGB/range/map filters before dispatch.
"""
import copy
import math
import numpy as np
from harness.active_wall_mapping import compose as tf_compose, inverse, wrap
from harness.self_odom_grid import transform
from harness.zone_solo_cyan_pulse_cal import profile_key

OPTION = 'regulated_v1'
VERSIONS = {'e2e18-v350':351, 'e2e18-v354':356}
PARAMS = dict(replan_s=1., goal_change_m=.05, approach_scaling_m=.6,
              curvature_min_radius_m=.9, cruise_period_s=.2, slow_period_s=.4,
              max_rgb_age_s=.4, max_extra_per_frame=1, gaze_deadband_deg=12.,
              search_explore_s=8., search_no_progress_s=5., sector_rad=math.pi/3,
              search_memory_s=120.)


def enabled(tr):
    return getattr(tr, 'approach_efficiency', 'off') == OPTION


def compose(bundle, option='off'):
    if option == 'off': return ()
    parent=bundle['execution_bundle_id'];version=VERSIONS.get(parent)
    if option != OPTION or version is None:
        raise ValueError('APPROACH_EFFICIENCY_REQUIRES_REGISTERED_RULE_PARENT')
    bundle.update(approach_efficiency_parent=parent,
                  approach_efficiency_parameters=copy.deepcopy(PARAMS),
                  execution_bundle_id=f'e2e18-v{version}', schema=f'ugrp.e2e_ownmap_live.v{version}',
                  workflow_version=f'7.{version-107}.0')
    bundle['e2e_options']['approach_efficiency'] = option
    return ('harness/e2e_approach_efficiency.py',
            f'configs/simulation_workflows.d/e2e18_v{version}.json')


def parent_for_validation(bundle):
    version=VERSIONS.get(bundle.get('approach_efficiency_parent'))
    if (version is None or bundle['execution_bundle_id'] != f'e2e18-v{version}'
            or bundle['e2e_options'].get('approach_efficiency') != OPTION
            or bundle.get('approach_efficiency_parameters') != PARAMS):
        raise ValueError('REGISTERED_APPROACH_EFFICIENCY_REQUIRED')
    old = copy.deepcopy(bundle)
    old['execution_bundle_id'] = old.pop('approach_efficiency_parent')
    old.pop('approach_efficiency_parameters'); old['e2e_options'].pop('approach_efficiency')
    return old


def pulse_period(body_carrot, goal_distance, path_length):
    """Nav2 RPP curvatureConstraint + approachVelocityConstraint, rate port.

    Slow only on a bend or the final .6 m of integrated path. The .4 s floor
    speed is the historical one-pulse-per-image rate. No pulse is stretched.
    """
    x, y = body_carrot
    curvature = 2*y/max(x*x+y*y, 1e-9)
    scale = min(1., 1/max(abs(curvature)*PARAMS['curvature_min_radius_m'], 1e-9))
    if path_length < PARAMS['approach_scaling_m']:
        scale = min(scale, goal_distance/PARAMS['approach_scaling_m'])
    return min(PARAMS['slow_period_s'], PARAMS['cruise_period_s']/max(scale, .01))


def navigation_path(tr, rid, now, state, costmap, pose, target):
    """1 Hz replan; invalidate immediately on changed goal or blocked path."""
    ex = tr.robots[rid].goal.explorer
    if not enabled(tr): return ex.navigator.plan_to(costmap, pose, target[:2])
    tf = ex.map_to_odom
    goal = tf_compose(inverse(tf), target)
    cache = state.get('efficient_path')
    reused = False
    path = []
    if cache and now-cache['t'] < PARAMS['replan_s'] and math.dist(cache['goal'][:2], goal[:2]) < PARAMS['goal_change_m']:
        path = transform(cache['path'], tf).tolist()
        i = min(range(len(path)), key=lambda i: math.dist(path[i], pose[:2]))
        path = [list(pose[:2]), *path[i+1:]]
        # Costmap native resolution check, including connecting segments.
        def clear(a, b):
            n = max(1, math.ceil(math.dist(a,b)/(costmap.resolution/2)))
            for u in np.linspace(0,1,n+1):
                cell = costmap.world_to_map(np.asarray(a)*(1-u)+np.asarray(b)*u)
                if cell is None or costmap.costs[cell[1],cell[0]] >= 253: return False
            return True
        reused = len(path)>1 and all(clear(a,b) for a,b in zip(path,path[1:]))
    if not reused:
        path = ex.navigator.plan_to(costmap, pose, target[:2])
        if path:
            state['efficient_path'] = dict(t=now, goal=goal.tolist(), path=transform(path,inverse(tf)).tolist())
        else: state.pop('efficient_path', None)
    tr.robots[rid].carrier_approach['path_reused'] = reused
    return path


def prepare_cruise(tr, rid, now, state, command, diag, costmap, map_pose, path):
    if not enabled(tr): return
    state.pop('efficient_cruise', None)
    rpp = diag.get('rpp', {})
    if (diag['status'] != 'navigate_pregrasp' or rpp.get('phase') != 'forward_path'
            or not diag.get('projected_clear') or command.get('forward', 0) <= 0): return
    period = pulse_period(rpp['body_error_m'], diag['distance_m'],
                          sum(math.dist(a,b) for a,b in zip(path,path[1:])))
    diag['regulated_pulse_period_s'] = period
    if period >= PARAMS['max_rgb_age_s']-1e-8: return
    profile = tr.profiles[profile_key(command, False)]
    state['efficient_cruise'] = dict(frame=state['frame'], command=copy.deepcopy(command),
        period=max(period, profile['times'][-1]), offered_at=now, issued_at=None,
        extra=0, costmap=costmap, map_pose=np.asarray(map_pose).copy(), profile=profile)


def issued(tr, rid, action, now):
    """Acknowledges actual dispatch, never a proposal discarded by a body gate."""
    if not enabled(tr): return
    state = tr.approach.get(rid, {}); cruise = state.get('efficient_cruise')
    if not cruise: return
    if action == cruise['command'] and abs(now-cruise['offered_at']) < 1e-8:
        cruise['issued_at'] = now
        cruise['map_pose'] = tf_compose(cruise['map_pose'], cruise['profile']['mean_delta'])
    else:
        # Camera, stop, detour, turn, or any later external command invalidates
        # the prediction. A rejected first proposal never arms continuation.
        state.pop('efficient_cruise', None)


def continuation(tr, rid, now, state):
    if not enabled(tr): return None
    c = state.get('efficient_cruise'); r = tr.robots[rid]
    if not c or c['issued_at'] is None or c['extra'] >= PARAMS['max_extra_per_frame']: return None
    obs = r.last_obs or {}
    age = now-obs.get('sim_time', -math.inf)
    if (tr.state != 'align' or state.get('fine') or not 0 <= age <= PARAMS['max_rgb_age_s']+1e-8
            or r.servo.get(1, 0)<1900 or now < getattr(r,'camera_settle_until',-1.)
            or any(robot == rid for _,robot,_ in tr.queue)):
        state.pop('efficient_cruise', None); return None
    if now-c['issued_at'] < c['period']-1e-8: return None
    from harness.public_navigation.follower import projected_clear
    from harness.public_navigation_recovery import issued_twist
    if not projected_clear(c['costmap'],c['map_pose'],issued_twist(c['command'])):
        state.pop('efficient_cruise', None); return None
    c['extra'] += 1; c['offered_at'] = now
    tr.event(now,'own_approach_cruise_continuation',robot_id=rid,frame_id=c['frame'],
             observation_age_s=age,period_s=c['period'],source='own_issued_calibrated_pulse_prediction')
    state['motion_until'] = now+c['command']['duration_s']
    return False, [copy.deepcopy(c['command'])]


def gaze_needed(tr, rid, grip):
    if not enabled(tr) or tr.approach.get(rid,{}).get('fine'): return True
    from harness.e2e_pregrasp_gaze import bearing
    from harness.visual_arm import PULSE_PER_DEGREE
    r=tr.robots[rid]; pose=r.goal.explorer.local_pose
    target=math.degrees(wrap(bearing(pose,grip)-pose[2]))
    commanded=(r.servo[6]-1500)/PULSE_PER_DEGREE
    return abs(wrap(math.radians(target-commanded))) > math.radians(PARAMS['gaze_deadband_deg'])


def search_memory(tr, rid, a, pose, last, now):
    """Keep search direction/covered sectors across repeated scan/explore cycles."""
    if not enabled(tr): return
    age = math.inf if last is None else now-last['rgb']['t_sim']
    point = np.asarray(last['pose_own_m'][:2]) if 0<=age<=PARAMS['search_memory_s'] else None
    yaw = math.atan2(*(point-pose[:2])[::-1]) if point is not None else float(pose[2])
    direction = 1 if wrap(yaw-pose[2]) >= 0 else -1
    a['sector_search'] = dict(origin_yaw=yaw, direction=direction, index=0,
        tried=[], source='last_own_rgb' if point is not None else 'own_heading', pose=np.asarray(pose[:2]).tolist())
    a['yaw'] = yaw


def next_yaw(tr, rid, a, pose):
    if not enabled(tr): return float(pose[2]+math.pi/3)
    s=a['sector_search']
    # Retain one direction for a complete sweep. Record completed/attempted
    # sectors so a 25 s exploration detour cannot reset the same scan order.
    s['tried'].append(s['index']%6); s['index']+=1
    return float(s['origin_yaw']+s['direction']*s['index']*PARAMS['sector_rad'])


def views(tr, rid, a, pose, default):
    if not enabled(tr): return default
    s=a['sector_search']; error=wrap(a['yaw']-pose[2])
    side=1750 if (error if abs(error)>.2 else s['direction'])>=0 else 1250
    # First inspect the last observed side; preserve all calibrated postures.
    sequence=(('search',side),('search',1500),('p45',1500),('inspect',1500),('search',3000-side))
    tr.robots[rid].carrier_approach['search_memory'] = copy.deepcopy(s)
    return sequence
