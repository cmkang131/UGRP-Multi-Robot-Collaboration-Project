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
    from harness import e2e_approach_efficiency as efficient
    if state.get('frame')==frame:
        continued=efficient.continuation(transport,rid,now,state)
        return continued if continued is not None else (state.get('fine',False),[])
    if efficient.enabled(transport):state.pop('efficient_cruise',None)
    state['frame']=frame;state['fine']=False
    from harness.e2e_stage_cadence import settling,admit_gaze
    if settling(transport,rid,now):
        r.carrier_approach=dict(t=now,status='gaze_settle')
        return False,[dict(kind='hold')]
    fresh=b is not None and now-b['rgb']['t_sim']<=.45
    target=g.entities.get('B')
    from harness.e2e_approach_recovery import seek_goal
    seeking=seek_goal(transport,rid,now,target)
    if seeking is not None:return seeking
    if fresh and target:
        end,grip,basis=station(b,target['center_m'],rid)
        state.update(station=end,grip=grip,basis=basis,last_seen=now)
        state.pop('search_started',None);state.pop('search_step',None)
    from harness.e2e_mapping_cadence import expire
    from harness import e2e_approach_commit as committed
    from harness import e2e_grasp_once as once
    once.seed_station(transport,rid,now,state,target)
    tracked=once.retained(transport,rid,now,state)
    if not tracked and not committed.retained(transport,now,state):expire(transport,rid,now,state,fresh)
    if 'station' not in state and getattr(transport,'pregrasp_acquire','off')!='off':
        from harness.e2e_pregrasp_acquire import acquire
        result=acquire(transport,rid,now,state,target)
        if result is not None:return result
    if 'station' not in state:
        r.carrier_approach=dict(t=now,status='search_own_beam')
        # Preserve the existing own-map exploration until this robot sees its beam.
        return False,[{k:v for k,v in r.nav_command.items() if k!='t'}]
    pose=np.asarray(g.explorer.local_pose);end=state['station'];grip=state['grip']
    distance=float(np.linalg.norm(end[:2]-pose[:2]));heading_error=wrap(end[2]-pose[2])
    grip_distance=float(np.linalg.norm(grip-pose[:2]))
    tag,pwm=committed.view(transport,rid,state,fresh,grip_distance)
    diag=dict(t=now,status='approach',station_own_m=end.tolist(),grip_own_m=grip.tolist(),
        distance_m=distance,heading_error_rad=heading_error,own_beam_age_s=now-state['last_seen'],camera=tag,
        basis_yaw_rad=state['basis']['yaw_rad'])
    r.carrier_approach=diag
    from harness.e2e_clip_recovery import step as clip_step
    clipped=clip_step(transport,rid,now,state,diag)
    if clipped is not None:return clipped
    from harness.e2e_station_heading import control as station_control
    station_control_mode=station_control(transport,rid,now,state,diag)
    if station_control_mode=='settle':
        diag['status']='station_heading_settle'
        return False,[dict(kind='hold')]
    rotate_station=station_control_mode=='rotate'
    observe_station=station_control_mode=='observe'
    recovery=getattr(transport,'pregrasp_recovery','off')=='bounded_search_v1'
    from harness.e2e_pregrasp_progress import step as progress_step
    progressed=None if rotate_station or observe_station else progress_step(transport,rid,now,state,distance)
    if progressed is not None:return progressed
    cached_navigation=getattr(transport,'pregrasp_progress','off')=='backup_replan_v1' and now<=state.get('lost_nav_until',-math.inf)
    cached_navigation=cached_navigation or committed.navigating(transport,rid,now,state,distance)
    cached_navigation=cached_navigation or (tracked and distance>committed.PARAMS['staging_radius_m'])
    if recovery and not fresh and now-state['last_seen']>2. and not cached_navigation and not rotate_station and not observe_station:
        from harness.e2e_align_progress import lost_search
        return lost_search(transport,rid,now,state)
    if any(r.servo.get(sid)!=pwm[sid] for sid in (3,4,5)):
        transport._poses(rid,now,[(pwm,.4,.5)])
        transport.align[rid].gate.until=now+.9
        diag['status']='camera_settle'
        return False,[dict(kind='hold')]
    if fresh:
        measured=transform([b['grip_base_m']],pose)[0]
        correct_end=float(np.linalg.norm(measured-grip))<.09
        diag['correct_end']=correct_end
        from harness.e2e_fine_entry import heading_limit
        from harness.e2e_capture_pose import admit as capture_admit
        if correct_end and capture_admit(transport,distance) and abs(b['axis_heading_rad'])<heading_limit(transport) and .10<b['grip_base_m'][0]<.40 and abs(b['grip_base_m'][1])<.10:
            from harness.e2e_clip_hysteresis import blocked as clip_blocked
            if clip_blocked(transport,rid,now,state):
                diag['status']='clip_hysteresis_hold';return False,[dict(kind='hold')]
            if now-state.get('motion_until',-math.inf)<.45:
                diag['status']='base_settle';return False,[dict(kind='hold')]
            state['fine']=True;diag['status']='visual_servo'
            return True,[]
    if observe_station:
        from harness.e2e_station_handoff import observe
        return observe(transport,rid,now,state,diag)
    tf=g.explorer.map_to_odom;mp=compose(tf,pose);mt=compose(tf,end)
    costmap=from_observed_grid(g.explorer.grid,mp,g.explorer.latest,set())
    avoidance=getattr(transport,'beam_avoidance','off')=='own_obstacle_v1'
    if avoidance:
        from harness.e2e_beam_avoidance import add
        beam_center=transform([state['basis']['center_m']],tf)[0]
        beam_yaw=state['basis']['yaw_rad']+tf[2]
        costmap=add(costmap,beam_center,beam_yaw)
        diag['beam_obstacle_source']='own_rgb_center_axis_known_size'
    from harness.e2e_grasp_fov import step as fov_step
    fov=fov_step(transport,rid,now,state,costmap,mp)
    if fov is not None:return fov
    path=[mp[:2]] if rotate_station else efficient.navigation_path(transport,rid,now,state,costmap,mp,mt)
    diag['path_points']=len(path)
    if not path and recovery and (fresh or cached_navigation) and transport.dev_light:
        if avoidance:
            from harness.e2e_beam_avoidance import fallback
            path=fallback(g.explorer.navigator,mp,mt[:2],beam_center,beam_yaw)
        else:path=[mp[:2],mt[:2]]
        diag['would_stop_path_unavailable']=True
        transport.event(now,'would_stop_pregrasp_no_path',robot_id=rid,dev_light=True,source='fresh_own_rgb_station' if fresh else 'last_own_rgb_station',last_seen_age_s=now-state['last_seen'])
    if not path:
        from harness.e2e_approach_recovery import no_path
        recovered=no_path(transport,rid,now,state,distance)
        if recovered is not None:return recovered
        diag['status']='approach_path_unavailable'
        transport.event(now,'own_pregrasp_path_wait',robot_id=rid,distance_m=distance)
        return False,[dict(kind='hold')]
    state['no_path_frames']=0
    from harness.e2e_approach_heading import kwargs as heading_kwargs
    command,rpp=rpp_command(dict(coordinate_frame=rid+'/own_odom',path_m=transform(path,inverse(tf)).tolist(),
        status='goal_approach',heading_rad=float(end[2])),pose,transport.profiles,robot_id=rid,**heading_kwargs(transport))
    diag['rpp']=rpp
    from harness.e2e_approach_floor import apply as floor_apply
    command=floor_apply(transport,rid,now,state,command,diag)
    twist=issued_twist(command) if command['kind']=='mecanum' else np.zeros(3)
    clear=projected_clear(costmap,mp,twist)
    if not clear:
        transport.event(now,'would_stop_pregrasp_collision_guard',robot_id=rid,dev_light=transport.dev_light)
        if not transport.dev_light:command=dict(kind='hold');twist=np.zeros(3)
    diag.update(projected_clear=bool(clear),status='rotate_station_heading' if rotate_station else 'navigate_pregrasp')
    if np.linalg.norm(twist)>1e-10:state['motion_until']=now+command['duration_s']
    from harness.e2e_pregrasp_gaze import fresh_gaze
    target=committed.gaze_target(transport,rid,fresh,grip)
    gazes=[] if target is None else fresh_gaze(transport,rid,target)
    actions=admit_gaze(transport,rid,now,gazes,command)
    if actions==[command]:efficient.prepare_cruise(transport,rid,now,state,command,diag,costmap,mp,path)
    return False,actions
