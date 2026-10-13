"""Default-off own-command gaze and own-last-seen bearing reacquisition."""
import math
import numpy as np
from harness.active_wall_mapping import wrap
from harness.owncam_pair_beam_v2 import pose_of
from harness.visual_arm import PULSE_PER_DEGREE
from harness.e2e_rpp_path import command as rpp_command

GAZE='own_bearing_v1'
BEARING='last_seen_v1'
WORKFLOW='configs/simulation_workflows.d/e2e18_v230.json'


def bearing(pose,grip):
    delta=np.asarray(grip)-np.asarray(pose[:2])
    return math.atan2(delta[1],delta[0])


def pan(pose,grip,current):
    error=wrap(bearing(pose,grip)-pose[2])
    target=round(1500+math.degrees(max(-math.pi/3,min(math.pi/3,error)))*PULSE_PER_DEGREE)
    return int(max(current-80,min(current+80,target)))


def fresh_gaze(transport,rid,grip):
    if getattr(transport,'pregrasp_gaze','off')!=GAZE:return []
    from harness.e2e_approach_efficiency import gaze_needed
    if not gaze_needed(transport,rid,grip):return []
    r=transport.robots[rid];current=r.servo[6]
    from harness.e2e_grasp_once import pan_target
    target=pan_target(transport,rid,grip)
    if target is None:target=pan(r.goal.explorer.local_pose,grip,current)
    return [dict(kind='look',pan_pulse=target)] if abs(target-current)>=10 else []


def recover(transport,rid,now,state):
    if getattr(transport,'search_bearing','off')!=BEARING or now-state.get('search_started',now)<6.:return None
    r=transport.robots[rid];pose=r.goal.explorer.local_pose
    target=pose_of('search')
    if any(r.servo.get(k)!=v for k,v in target.items()):
        transport._poses(rid,now,[(target,.3,.4)])
        return False,[dict(kind='hold')]
    yaw=bearing(pose,state['grip'])
    action,diag=rpp_command(dict(coordinate_frame=rid+'/own_odom',path_m=[list(pose[:2])],status='goal_approach',heading_rad=yaw),pose,transport.profiles,robot_id=rid)
    r.carrier_approach.update(status='turn_to_last_seen_beam',bearing_error_rad=wrap(yaw-pose[2]),rpp=diag,
        source='own_rgb_last_seen_and_own_command_odometry')
    if action['kind']=='hold':
        state['search_started']=now;state.pop('search_step',None)
        if getattr(transport,'pregrasp_progress','off')=='backup_replan_v1':state['lost_nav_until']=now+5.
    else:
        state['motion_until']=now+action['duration_s']
    return False,[action]


def compose(bundle,gaze,search,pulse):
    if gaze=='off' and search=='off' and pulse=='off':return ()
    if gaze!=GAZE or search!=BEARING or pulse!='finish_active_v1' or bundle['execution_bundle_id']!='e2e18-v229':
        raise ValueError('PREGRASP_GAZE_REQUIRES_V229')
    bundle['e2e_options'].update(pregrasp_gaze=gaze,search_bearing=search,pulse_admission=pulse)
    bundle.update(schema='ugrp.e2e_ownmap_live.v230',execution_bundle_id='e2e18-v230',workflow_version='7.123.0')
    return (WORKFLOW,)
