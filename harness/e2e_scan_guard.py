"""Own-map or command-space pre-scan retreat for front-sonar blind sectors."""
import math
import numpy as np
from harness.active_wall_mapping import compose as tf_compose
OPTIONS=('map_v1','retreat_v1','retreat_slots_v1')
VERSIONS=dict(zip(OPTIONS,(254,255,256)))
PARAMS=dict(map_wall_radius_m=.45,retreat_valid_s=12.,retreat_translation_m=.10,retreat_yaw_rad=.26)


def mapped_wall_distance(robot):
    e=robot.goal.explorer;grid=e.grid
    if grid.robot_id!=robot.robot_id:raise ValueError('SCAN_GUARD_OWN_MAP_REQUIRED')
    pose=tf_compose(e.map_to_odom,np.asarray(e.local_pose));cx,cy=grid.cell(pose[:2])
    n=math.ceil(PARAMS['map_wall_radius_m']/grid.resolution)+1;distance=None
    for x in range(cx-n,cx+n+1):
        for y in range(cy-n,cy+n+1):
            cell=(x,y)
            if not e.latest.get(cell,grid.state(cell)>0):continue
            d=float(np.linalg.norm(grid.point(cell)-pose[:2]))-grid.resolution*math.sqrt(2)/2
            distance=d if distance is None else min(distance,d)
    return distance


def forced(guard,rid,now,pose):
    if guard.scan_guard not in ('retreat_v1','retreat_slots_v1'):return False
    granted=guard.retreat_grants.get(rid)
    if granted is None:return True
    at,old=granted;delta=pose-old
    return (not 0<=now-at<=PARAMS['retreat_valid_s'] or np.linalg.norm(delta[:2])>PARAMS['retreat_translation_m']
            or abs(math.atan2(math.sin(delta[2]),math.cos(delta[2])))>PARAMS['retreat_yaw_rad'])


def compose(bundle,option):
    if option=='off':return ()
    if option not in OPTIONS or bundle['execution_bundle_id']!='e2e18-v253':
        raise ValueError('SCAN_GUARD_REQUIRES_V253')
    v=VERSIONS[option];bundle['e2e_options']['scan_guard']=option
    bundle['scan_guard_parameters']=dict(PARAMS)
    bundle.update(schema=f'ugrp.e2e_ownmap_live.v{v}',execution_bundle_id=f'e2e18-v{v}',workflow_version=f'7.{v-107}.0')
    return (f'configs/simulation_workflows.d/e2e18_v{v}.json',)
