"""Own-map search lifecycle recovery; remembered beam is a search hypothesis only.

Uses explore_lite resume/reselection and bounded navigation with position-only
progress (Nav2 SimpleProgressChecker). Never promotes memory to a current beam.
"""
import math
import numpy as np
from harness.active_wall_mapping import compose as tf_compose, inverse
from harness.self_odom_grid import transform
from harness.public_navigation_unknown import from_observed_grid
from harness.e2e_rpp_path import command as rpp_command
from harness.owncam_pair_beam_v2 import pose_of

OPTIONS=('resume_v1','remembered_view_v1')
VERSIONS=dict(zip(OPTIONS,(249,250)))
PARAMS=dict(explore_s=25.,progress_s=10.,progress_m=.05,view_radius_m=1.)


def resume(robot,now):
    e=robot.goal.explorer;n=e.navigator
    # Expire action suppression, preserving all observed map cells and odometry.
    n.blacklist.clear();n.visited.clear();n.reset_action()
    n.target=n.frontier=n.requested_goal=None;n.path=[]
    n.locked=n.finished=n.static_mode=False
    n.goal_started=n.progress_time=n.progress_xy=None;n.best_distance=math.inf
    n.next_frontier_ns=0;n.initial_scan_used=False
    e.plan=None;e.last_plan_t=-math.inf
    n.event(now,'acquisition_frontier_resumed')


def remembered_command(tr,rid,now,a):
    r=tr.robots[rid];e=r.goal.explorer;last=getattr(r,'last_beam',None)
    if not last or last['rgb']['t_sim']>now:return None
    pose=np.asarray(e.local_pose,float);center=np.asarray(last['pose_own_m'][:2],float)
    if not np.isfinite(center).all():return None
    delta=pose[:2]-center;distance=float(np.linalg.norm(delta))
    if distance<=PARAMS['view_radius_m']+.08:return None
    target=center+PARAMS['view_radius_m']*delta/distance
    tf=e.map_to_odom;mp=tf_compose(tf,pose);mt=transform([target],tf)[0]
    costmap=from_observed_grid(e.grid,mp,e.latest,set())
    from harness.e2e_beam_avoidance import add
    costmap=add(costmap,transform([center],tf)[0],float(last['pose_own_m'][2]+tf[2]))
    path=e.navigator.plan_to(costmap,mp,mt)
    if not path:return None
    action,diag=rpp_command(dict(coordinate_frame=rid+'/own_odom',path_m=transform(path,inverse(tf)).tolist(),
        status='goal_reobserve',heading_rad=math.atan2(*(center-pose[:2])[::-1])),pose,tr.profiles,robot_id=rid)
    r.carrier_approach.update(status='acquire_remembered_view',hypothesis_age_s=now-last['rgb']['t_sim'],
        hypothesis_rgb=last['rgb'],view_target_own_m=target.tolist(),path_points=len(path),rpp=diag)
    return action


def explore(tr,rid,now,a):
    option=getattr(tr,'acquisition_mobility','off')
    if option=='off':return None
    if option not in OPTIONS:raise ValueError('UNKNOWN_ACQUISITION_MOBILITY')
    r=tr.robots[rid];pose=np.asarray(r.goal.explorer.local_pose,float)
    key=a['cycles']
    if a.get('mobile_cycle')!=key:
        a.update(mobile_cycle=key,mobile_started=now,progress_t=now,progress_xy=pose[:2].copy())
        resume(r,now)
        tr.event(now,'own_acquisition_navigation_resumed',robot_id=rid,cycle=key,option=option)
        tr._poses(rid,now,[(pose_of('search'),.3,.6)])
        return False,[dict(kind='hold')]
    if np.linalg.norm(pose[:2]-a['progress_xy'])>=PARAMS['progress_m']:
        a.update(progress_t=now,progress_xy=pose[:2].copy())
    from harness import e2e_approach_efficiency as efficient
    duration=efficient.PARAMS['search_explore_s'] if efficient.enabled(tr) else PARAMS['explore_s']
    progress=efficient.PARAMS['search_no_progress_s'] if efficient.enabled(tr) else PARAMS['progress_s']
    if now-a['mobile_started']>=duration or now-a['progress_t']>=progress:
        tr.event(now,'own_acquisition_navigation_window_end',robot_id=rid,cycle=key,
            elapsed_s=now-a['mobile_started'],no_translation_s=now-a['progress_t'])
        a.update(phase='turn',started=now,yaw=efficient.next_yaw(tr,rid,a,pose))
        return False,[dict(kind='hold')]
    action=remembered_command(tr,rid,now,a) if option=='remembered_view_v1' else None
    return False,[action if action is not None else {k:v for k,v in r.nav_command.items() if k!='t'}]


def compose(bundle,option):
    if option=='off':return ()
    if option not in OPTIONS or bundle['execution_bundle_id']!='e2e18-v246':
        raise ValueError('ACQUISITION_MOBILITY_REQUIRES_V246')
    v=VERSIONS[option];bundle['e2e_options']['acquisition_mobility']=option
    bundle['acquisition_mobility_parameters']=dict(PARAMS)
    bundle.update(schema=f'ugrp.e2e_ownmap_live.v{v}',execution_bundle_id=f'e2e18-v{v}',workflow_version=f'7.{v-107}.0')
    return (f'configs/simulation_workflows.d/e2e18_v{v}.json',)
