"""Default-off own-goal acquisition and planner-failure recovery."""
import numpy as np
from harness.active_camera import SEARCH
from harness.e2e_pregrasp_progress import step as progress_step
GOAL='seek_own_B_v1'
PATH='backup_v1'
WORKFLOW='configs/simulation_workflows.d/e2e18_v238.json'


def seek_goal(tr,rid,now,target):
    if getattr(tr,'carrier_goal','off')=='off' or target is not None:return None
    if tr.carrier_goal!=GOAL:raise ValueError('UNKNOWN_CARRIER_GOAL')
    r=tr.robots[rid]
    r.carrier_approach=dict(t=now,status='seek_own_B',source='own_frontier_navigation')
    if any(r.servo.get(k)!=v for k,v in SEARCH.items()):
        tr._poses(rid,now,[(SEARCH,.3,.6)])
        return False,[dict(kind='hold')]
    return False,[dict(r.nav_command)]


def no_path(tr,rid,now,state,distance):
    if getattr(tr,'blocked_path_recovery','off')=='off':return None
    if tr.blocked_path_recovery!=PATH or not tr.dev_light:raise ValueError('DEV_BLOCKED_PATH_REQUIRED')
    r=tr.robots[rid];state['no_path_frames']=state.get('no_path_frames',0)+1
    r.carrier_approach['no_path_frames']=state['no_path_frames']
    if state['no_path_frames']<3:return None
    pose=np.asarray(r.goal.explorer.local_pose)
    watch=state.setdefault('progress_watch',{})
    cycle=watch.get('cycle',0)+1
    watch.update(pose=pose.copy(),since=now,count=r.translation_commands,issued=0,last_issue=now,
                 cycle=cycle,phase='backup',phase_t=now,phase_pose=pose.copy())
    state['no_path_frames']=0
    tr.event(now,'own_pregrasp_blocked_plan_recovery',robot_id=rid,distance_m=distance,
             recovery='calibrated_backup_then_turn',cycle=cycle,source='own_rgb_grid_plan_failure')
    return progress_step(tr,rid,now,state,distance)


def compose(bundle,goal,path):
    if goal=='off' and path=='off':return ()
    if goal!=GOAL or path!=PATH or bundle['execution_bundle_id']!='e2e18-v237' or not bundle['e2e_options']['dev_light']:
        raise ValueError('APPROACH_RECOVERY_REQUIRES_DEV_V237')
    bundle['e2e_options'].update(carrier_goal=goal,blocked_path_recovery=path)
    bundle.update(schema='ugrp.e2e_ownmap_live.v238',execution_bundle_id='e2e18-v238',workflow_version='7.131.0')
    return (WORKFLOW,)
