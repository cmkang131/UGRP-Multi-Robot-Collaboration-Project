"""Default-off scene-v5 virtual scans and the existing own-map RBPF.

No map, truth, simulator, peer-pose or measured-joint input. The adapter reuses
Grisetti proposal/importance weights, per-particle OdomGrid and selective
resampling. Frozen constants and departures are recorded in mapbuild5 README.
"""
from types import MethodType
import math
import cv2
import numpy as np

OPTION = 'mapbuild_rbpf_v1'


def virtual_scan(rgb, servo, state, *, camera_pose='off'):
    """Only measured wall/floor contacts; missing bearings remain None.

    Inherited 96 columns and colour calibration, servo FK, fixed K/D. Mask
    orange peer columns and own projected silhouette in UNDISTORTED pixels.
    Neighbour segments require consecutive returned columns; no gap is joined.
    """
    from harness.active_wall_vision import modules
    from harness.active_camera import transform
    from harness.scene_colour_boundary import detect
    from harness.opencv_wall_observation_robot_mask import robot_occluded_columns
    from harness.floor_goal_self_mask import self_body_mask
    from harness.e2e_rgb_vo import K, D
    mp, hfw, _ = modules()
    if camera_pose=='off':
        origin, rotation = transform(servo)
    else:
        from harness.servo_camera_fk import CARRY_OPTION,transform_from_commands
        if camera_pose!=CARRY_OPTION:raise ValueError('UNKNOWN_MAPBUILD_CAMERA')
        value,reason=transform_from_commands(servo,camera_pose=camera_pose)
        if value is None:raise ValueError(reason)
        origin,rotation=value
    columns = mp.column_positions(96,2)
    cm = mp.ColumnModel(tuple(sorted(servo.items())),0.,columns,camera_transform=(origin,rotation))
    und = mp.undistort(cv2.cvtColor(rgb,cv2.COLOR_RGB2BGR))
    scan = detect(hfw,und,cm,params={'floor_patch_max_m':.81,'run_step_window':3,'top_edge_px':4},
                  loaded=False,state=state)
    robot = robot_occluded_columns(und)
    if camera_pose=='off':
        raw_body = self_body_mask(servo,'camera_v3',640,480).astype(np.uint8)
    else:
        from harness.floor_goal_self_mask import body_envelopes,project_envelopes
        raw_body=project_envelopes(body_envelopes(servo,'camera_v3'),origin,rotation.T,640,480).astype(np.uint8)
    # Nearest-neighbour remap preserves the binary own-body exclusion.
    mx,my = cv2.fisheye.initUndistortRectifyMap(K,D,np.eye(3),K,(640,480),cv2.CV_32FC1)
    body = cv2.remap(raw_body,mx,my,cv2.INTER_NEAREST,borderMode=cv2.BORDER_CONSTANT,borderValue=0)>0
    rows=[]; points={}; reasons=[]
    grey=cv2.cvtColor(und,cv2.COLOR_BGR2GRAY).astype(float)
    for j,u in enumerate(columns.astype(int)):
        v=scan['vb'][j,0]; reason=state.last_result['column_reasons'][j]
        # Entire peer/body columns are excluded, rather than trusting a wall
        # colour behind a foreground robot. No silhouette truth is consulted.
        peer=bool(robot[max(0,u-2):min(640,u+3)].any())
        own=bool(body[:,u].any())
        point=None; distance=None; bearing=None
        if peer: reason='peer_rgb_column'
        elif own: reason='self_body_column'
        elif np.isfinite(v):
            ray=rotation @ (np.linalg.inv(K) @ [u,v,1.])
            depth=-origin[2]/ray[2] if ray[2]<0 else -1.
            p=origin+depth*ray
            r=float(np.linalg.norm(p[:2]-origin[:2]))
            # Existing own-map projection guard: positive depth and 4m range.
            if depth>0 and np.isfinite(p).all() and r<4.:
                point=p[:2];points[j]=point
                distance=r; bearing=float(math.atan2(point[1]-origin[1],point[0]-origin[0]))
                reason='returned_wall_floor_contact'
            else: reason='nonpositive_depth_or_4m_range'
        reasons.append(reason)
        rows.append(dict(column=int(u),row=float(v) if np.isfinite(v) else None,
                         range_m=distance,bearing_rad=bearing,status='hit' if point is not None else 'unknown',
                         reason=reason,blocked_object='peer_robot_rgb' if peer else 'self_body_rgb' if own else 'not_observed',
                         minimum_gap_m=None,gap_status='not_measured'))
    segments=[];features=[]
    # Segments are ONLY between adjacent observed bearings. Isolated hits are
    # retained as zero-length rays, with no fabricated wall direction.
    for j,p in points.items():
        q=points.get(j+1,p)
        if j-1 in points and j+1 not in points: continue
        segments.append([p.tolist(),q.tolist()])
        v=int(np.clip(round(scan['vb'][j,0]),1,478));u=int(columns[j])
        features.append(dict(height_m=float(origin[2]),fy=float(K[1,1]),contrast=float(scan['c'][j,0]),
             band_std=float(scan['s'][j,0]),sharpness=float(abs(grey[v+1,u]-grey[v-1,u])),body_settling=1.))
    return dict(columns=rows,segments=segments,features=features,camera=np.asarray(origin[:2]).tolist(),
                work=state.last_result['work_budget'],truth_inputs=0,unknown_as_max_range=0)


def propagate_covariance(grid, delta, covariance):
    """External measured/command interval, full body covariance exactly once."""
    delta=np.asarray(delta,float);cov=np.asarray(covariance,float)
    if delta.shape!=(3,) or cov.shape!=(3,3) or not np.isfinite(np.r_[delta,cov.ravel()]).all():
        raise ValueError('INVALID_INTERVAL_MOTION')
    if not np.allclose(cov,cov.T) or np.linalg.eigvalsh(cov).min() < -1e-12:
        raise ValueError('INVALID_INTERVAL_COVARIANCE')
    yaw=grid.poses[:,2].copy()
    grid.propagate(delta,np.zeros(3))
    c,s=np.cos(yaw),np.sin(yaw);r=np.zeros_like(grid.pending_cov)
    r[:,0,0]=c;r[:,0,1]=-s;r[:,1,0]=s;r[:,1,1]=c;r[:,2,2]=1.
    grid.pending_cov += r@cov@r.transpose(0,2,1)


class MapbuildRBPF:
    def __init__(self, servo, *, option='off'):
        if option!=OPTION: raise ValueError('EXPLICIT_MAPBUILD_RBPF_REQUIRED')
        from harness.self_wall_memory_motion import SelfWallMemory
        from harness.rbpf_motion_gate import install as gate
        from harness.rbpf_rejection import install as rejection
        from harness.rbpf_composition import install as composition
        from harness.rbpf_manhattan import install as manhattan
        # 30 is existing RBPFOptions/ROS default, not tuned to this recording.
        g=SelfWallMemory('r1',self_map='odom_grid_v1',pose_correction='own_map_rbpf_v1',
            pose_correction_options={'particles':30,'seed':20261006},motion_model='s2_pulse_v122',
            wall_confidence='inverse_sensor_v1',self_map_options={'settle_s':(.25,2.25)}).self_map
        g.odom.driver.command(dict(kind='initial_servo_command',t=0,pulses=servo))
        gate(g,rbpf_update='gmapping_motion_v1')
        rejection(g,rbpf_rejection='gmapping_selective_v1')
        composition(g,rbpf_composition='insert_selective_v1')
        manhattan(g,yaw_prior='manhattan_v1')
        # Fixed start coordinates define the gauge, not a measured world pose.
        # Do not draw the archived .1m initial-position floor as gauge error.
        g.pending_cov[:]=0.
        def advance(odom,t):
            if abs(t-odom.driver.t)>1e-8: raise ValueError('FEED_INTERVAL_BEFORE_SCAN')
            return odom.pose
        g.odom.advance=MethodType(advance,g.odom)
        self.grid=g;self.last_scan=-math.inf

    def step(self,t,frame_id,delta,covariance,scan):
        from harness.e2e_rgb_vo import compose
        g=self.grid
        if t<g.odom.driver.t: raise ValueError('NONCAUSAL_FRAME')
        propagate_covariance(g,delta,covariance)
        g.odom.driver._pose=compose(g.odom.driver._pose,delta);g.odom.driver.t=t
        prior=list(g.odom.pose)
        event=dict(t=t,frame_id=frame_id,reason='no_visible_scan',inserted=False,resampled=False)
        # Existing CSMOptions.keyframe_interval_s=1 SIMs. The ROS 1m/.5rad
        # gate is not used for this short round trip; no wall-time scheduler.
        if scan['segments'] and t-self.last_scan>=g.options.keyframe_interval_s-1e-8:
            g._wall_features=scan['features']
            try:
                g._admitted_scan_observer(g,dict(t_sim=t,view_index=frame_id),scan['segments'],
                                         camera_xy=scan['camera'],robot_id='r1')
            finally: g._wall_features=None
            event=g.decisions[-1]
            if event.get('inserted'): self.last_scan=t
        elif scan['segments']: event['reason']='sim_keyframe_interval'
        event={**event,'category':'scan_match','blocked_object':'own_observed_wall' if scan['segments'] else 'not_observed',
               'minimum_gap_m':None,'gap_status':'not_measured','prior_pose':prior}
        return np.asarray(g.odom.pose).tolist(),event
