"""Bounded own-odom staging navigation before fresh-image fine alignment.

Nav2 Docking separates navigation to staging from the final perception loop.
Here the staging hypothesis comes only from the robot's previous own RGB.
"""
import math
import numpy as np
from harness.owncam_pair_beam_v2 import look_posture,pose_of
from harness.self_odom_grid import transform

OPTIONS=('memory20_v1','memory60_v1','memory60_view_v1')
VERSIONS=dict(zip(OPTIONS,(251,252,253)))
AGE={'memory20_v1':20.,'memory60_v1':60.,'memory60_view_v1':60.}
PARAMS=dict(fresh_alignment_required=True,staging_radius_m=.08,view_hysteresis_m=.025)


def retained(tr,now,state):
    mode=getattr(tr,'approach_commit','off')
    if mode=='off':return False
    if mode not in OPTIONS:raise ValueError('UNKNOWN_APPROACH_COMMIT')
    return 'station' in state and 0<=now-state.get('last_seen',-math.inf)<=AGE[mode]


def navigating(tr,rid,now,state,distance):
    yes=retained(tr,now,state) and distance>PARAMS['staging_radius_m']
    if yes and now-state['last_seen']>2.:
        key=state['last_seen']
        if state.get('committed_logged')!=key:
            state['committed_logged']=key
            tr.event(now,'would_reacquire_during_staging',robot_id=rid,source='own_rgb_station_hypothesis',
                     last_seen_age_s=now-state['last_seen'],max_age_s=AGE[tr.approach_commit],distance_m=distance)
    return yes


def view(tr,rid,state,fresh,grip_distance):
    from harness.e2e_fine_view import view as fine_view
    final=fine_view(tr,rid,state,grip_distance)
    if final is not None:return final
    if getattr(tr,'approach_commit','off')!='memory60_view_v1':return look_posture(grip_distance)
    r=tr.robots[rid];previous=state.get('committed_camera')
    # The visible band guides viewing even when the assigned grasp is the far
    # end. This does not change the carrier's assigned end or grasp condition.
    if fresh:distance=float(np.linalg.norm(r.beam['grip_base_m']))
    else:
        from harness.e2e_grasp_once import gaze_target as remembered_gaze
        point=remembered_gaze(tr,rid,(r.last_obs or {}).get('sim_time',-math.inf))
        if point is not None:distance=float(np.linalg.norm(point-r.goal.explorer.local_pose[:2]))
        elif previous:return previous,pose_of(previous)
        else:distance=grip_distance
    tag,_=look_posture(distance)
    boundaries={frozenset(('search','p45')):.34,frozenset(('p45','inspect')):.255}
    boundary=boundaries.get(frozenset((previous,tag)))
    if boundary is not None and abs(distance-boundary)<PARAMS['view_hysteresis_m']:tag=previous
    state['committed_camera']=tag
    return tag,pose_of(tag)


def gaze_target(tr,rid,fresh,assigned):
    from harness.e2e_fine_view import active
    if active(tr,rid,tr.approach.get(rid,{})):return assigned
    if getattr(tr,'approach_commit','off')!='memory60_view_v1':return assigned
    if not fresh:
        from harness.e2e_grasp_once import gaze_target as remembered_gaze
        return remembered_gaze(tr,rid,(tr.robots[rid].last_obs or {}).get('sim_time', -math.inf))
    r=tr.robots[rid]
    return transform([r.beam['grip_base_m']],r.goal.explorer.local_pose)[0]


def compose(bundle,option):
    if option=='off':return ()
    if option not in OPTIONS or bundle['execution_bundle_id']!='e2e18-v249':
        raise ValueError('APPROACH_COMMIT_REQUIRES_V249')
    v=VERSIONS[option];bundle['e2e_options']['approach_commit']=option
    bundle['approach_commit_parameters']={**PARAMS,'max_age_s':AGE[option]}
    bundle.update(schema=f'ugrp.e2e_ownmap_live.v{v}',execution_bundle_id=f'e2e18-v{v}',workflow_version=f'7.{v-107}.0')
    return (f'configs/simulation_workflows.d/e2e18_v{v}.json',)
