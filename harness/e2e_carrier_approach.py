"""Own-map pregrasp navigation, commanded camera postures, then visual servo."""
import math
import numpy as np
from harness.e2e_carrier_axes import station
from harness.self_odom_grid import transform
from harness.active_wall_mapping import compose,inverse,wrap
from harness.public_navigation_unknown import from_observed_grid
from harness.public_navigation.follower import projected_clear
from harness.public_navigation_recovery import issued_twist
from harness.e2e_rpp_path import command as rpp_command
from harness.owncam_pair_beam_v2 import look_posture,pose_of

OPTION='standoff_v1'


def advance(transport,rid,now):
    r=transport.robots[rid];g=r.goal;b=r.beam
    state=transport.approach.setdefault(rid,{})
    frame=r.last_obs['frame_id'] if r.last_obs else None
    if state.get('frame')==frame:return state.get('fine',False),[]
    state['frame']=frame;state['fine']=False
    fresh=b is not None and now-b['rgb']['t_sim']<=.45
    target=g.entities.get('B')
    if fresh and target:
        end,grip,basis=station(b,target['center_m'],rid)
        state.update(station=end,grip=grip,basis=basis,last_seen=now)
    if 'station' not in state:
        r.carrier_approach=dict(t=now,status='search_own_beam')
        # Preserve the existing own-map exploration until this robot sees its beam.
        return False,[{k:v for k,v in r.nav_command.items() if k!='t'}]
    pose=np.asarray(g.explorer.local_pose);end=state['station'];grip=state['grip']
    distance=float(np.linalg.norm(end[:2]-pose[:2]));heading_error=wrap(end[2]-pose[2])
    grip_distance=float(np.linalg.norm(grip-pose[:2]))
    tag,pwm=look_posture(grip_distance)
    diag=dict(t=now,status='approach',station_own_m=end.tolist(),grip_own_m=grip.tolist(),
        distance_m=distance,heading_error_rad=heading_error,own_beam_age_s=now-state['last_seen'],camera=tag,
        basis_yaw_rad=state['basis']['yaw_rad'])
    r.carrier_approach=diag
    if any(r.servo.get(sid)!=pwm[sid] for sid in (3,4,5)):
        transport._poses(rid,now,[(pwm,.4,.5)])
        transport.align[rid].gate.until=now+.9
        diag['status']='camera_settle'
        return False,[dict(kind='hold')]
    if fresh:
        measured=transform([b['grip_base_m']],pose)[0]
        correct_end=float(np.linalg.norm(measured-grip))<.09
        diag['correct_end']=correct_end
        if correct_end and abs(b['axis_heading_rad'])<.20 and .10<b['grip_base_m'][0]<.40 and abs(b['grip_base_m'][1])<.10:
            if now-state.get('motion_until',-math.inf)<.45:
                diag['status']='base_settle';return False,[dict(kind='hold')]
            state['fine']=True;diag['status']='visual_servo'
            return True,[]
    tf=g.explorer.map_to_odom;mp=compose(tf,pose);mt=compose(tf,end)
    costmap=from_observed_grid(g.explorer.grid,mp,g.explorer.latest,set())
    path=g.explorer.navigator.plan_to(costmap,mp,mt[:2])
    diag['path_points']=len(path)
    if not path:
        diag['status']='approach_path_unavailable'
        transport.event(now,'own_pregrasp_path_wait',robot_id=rid,distance_m=distance)
        return False,[dict(kind='hold')]
    command,rpp=rpp_command(dict(coordinate_frame=rid+'/own_odom',path_m=transform(path,inverse(tf)).tolist(),
        status='goal_approach',heading_rad=float(end[2])),pose,transport.profiles,robot_id=rid)
    diag['rpp']=rpp
    twist=issued_twist(command) if command['kind']=='mecanum' else np.zeros(3)
    clear=projected_clear(costmap,mp,twist)
    if not clear:
        transport.event(now,'would_stop_pregrasp_collision_guard',robot_id=rid,dev_light=transport.dev_light)
        if not transport.dev_light:command=dict(kind='hold');twist=np.zeros(3)
    diag.update(projected_clear=bool(clear),status='navigate_pregrasp')
    if np.linalg.norm(twist)>1e-10:state['motion_until']=now+command['duration_s']
    return False,[command]
