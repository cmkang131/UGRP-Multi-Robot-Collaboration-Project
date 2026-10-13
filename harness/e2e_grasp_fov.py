"""Default-off own-track bearing constraint before pregrasp translation.

Reuse calibrated rotate-to-heading pulses and the existing clearance/dispatch
pipeline. A remembered target only selects where to look; it never grants a
fresh alignment or a grasp. No evaluator/simulator input.
"""
import math
import numpy as np
from harness.active_wall_mapping import wrap
from harness.e2e_grasp_once import valid
from harness.e2e_pregrasp_gaze import bearing
from harness.e2e_rpp_path import command
from harness.public_navigation.follower import projected_clear
from harness.public_navigation_recovery import issued_twist

OPTIONS = {'turn60_v1': 60., 'turn45_v1': 45., 'near_once60_v1':60., 'near_once45_v1':45.}


def step(tr, rid, now, state, costmap=None, map_pose=None, distance_m=math.inf):
    option=getattr(tr,'grasp_fov','off')
    if option=='off':return None
    if option not in OPTIONS:raise ValueError('UNKNOWN_GRASP_FOV')
    once=option.startswith('near_once')
    if once and (state.get('fov_completed') or distance_m>.35):
        return None
    if once and now-state.get('fov_started',now)>=3.:
        state['fov_completed']=True;state.pop('fov_turning',None)
        return None
    r=tr.robots[rid]
    if not valid(r,now):return None
    pose=np.asarray(r.goal.explorer.local_pose,float)
    target=np.asarray(r.grasp_track['band'],float)
    error=wrap(bearing(pose,target)-pose[2])
    limit=math.radians(OPTIONS[option])
    active=state.get('fov_turning',False)
    release=limit-math.radians(15.)
    if abs(error)<=(release if active else limit):
        if once and active:state['fov_completed']=True
        state.pop('fov_turning',None)
        return None
    state['fov_turning']=True
    if once:state.setdefault('fov_started',now)
    yaw=wrap(bearing(pose,target)-math.copysign(max(0.,release-.07),error))
    action,diag=command(dict(coordinate_frame=rid+'/own_odom',path_m=[pose[:2].tolist()],
        status='goal_reobserve',heading_rad=yaw),pose,tr.profiles,robot_id=rid)
    if action['kind']=='mecanum' and (action.get('forward',0) or action.get('left',0)):
        raise ValueError('FOV_RECOVERY_ROTATION_ONLY')
    twist=issued_twist(action) if action['kind']=='mecanum' else np.zeros(3)
    clear=projected_clear(costmap,map_pose,twist)
    if not clear:
        tr.event(now,'would_stop_pregrasp_collision_guard',robot_id=rid,dev_light=tr.dev_light)
        if not tr.dev_light:action=dict(kind='hold')
    diag['projected_clear']=bool(clear)
    state.pop('efficient_cruise',None)
    if action['kind']=='mecanum':state['motion_until']=now+action['duration_s']
    r.carrier_approach.update(status='turn_for_own_beam_view',bearing_error_rad=error,
        bearing_limit_rad=limit,hypothesis_age_s=now-r.grasp_track['seen'],
        hypothesis_rgb=r.grasp_track['rgb'],fov_rpp=diag)
    return False,[action]
