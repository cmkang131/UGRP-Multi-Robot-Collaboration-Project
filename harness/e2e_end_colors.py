"""Default-off own-RGB colored end identity; static order, no world/peer state.

OpenCV HSV inRange + the existing calibrated beam-top ray intersection.
Only an observed assigned-color band can seed a grasp station.
"""
import copy
import hashlib
import json
import math
import cv2
import numpy as np
from harness import owncam_pair_beam as v1

PROFILE='teal_blue_v1'
OPTIONS=('scan_v1','remember_v1','short_side_v1','anchor_v2','anchor_short_v2','sweep_v2')
COLORS={'teal':dict(rgba=[.02,.95,.60,1.],hsv_lo=[74,185,45],hsv_hi=[83,255,255]),
        'blue':dict(rgba=[.02,.02,.95,1.],hsv_lo=[116,185,45],hsv_hi=[124,255,255])}
ORDER={'r1':'teal','r2':'blue'}


def record():
    value=dict(schema='ugrp.beam_end_colors.v1',profile=PROFILE,colors=COLORS,order=ORDER,
        scene_version='e2e_one_beam_ownmap_end_colors_v1',
        map_version='zone_wide_door_e2e_b80_end_colors_v1',
        exception='사용자 명시 예외(물체 외관 변경)',changes_physics=False)
    value['sha256']=hashlib.sha256(json.dumps(value,sort_keys=True).encode()).hexdigest()
    return value


def mask(frame,color):
    c=COLORS[color]
    return cv2.inRange(cv2.cvtColor(frame,cv2.COLOR_BGR2HSV),np.array(c['hsv_lo']),np.array(c['hsv_hi']))>0


def observe(image,servo,color,rays,option='scan_v1'):
    from harness.zone_final_pair_binding import bind
    if option not in OPTIONS:raise ValueError('UNKNOWN_END_COLOR_POLICY')
    frame=v1.decode(image)
    base=bind(v1.observe_beam,base_rays=rays)(frame,servo)
    out=dict(base,perception=PROFILE,target_color=color,end_visible=False,
        provenance='own_RGB_HSV+issued_camera_PWM+beam_top_plane+static_color_order')
    if not base.get('visible'):return out
    origin,directions,xs,ys,valid=rays(servo,v1.RAY_STEP)
    down=directions[:,2]<-1e-6
    scales=np.where(down,(v1.BEAM_TOP_Z_M-origin[2])/np.where(down,directions[:,2],-1.),np.nan)
    pts=origin[:2]+scales[:,None]*directions[:,:2]
    valid=valid&down&(scales>0)&(np.linalg.norm(pts,axis=1)<2.5)
    xi,yi=xs.astype(int),ys.astype(int)
    heading=base['axis_heading_rad'];u=np.array([math.cos(heading),math.sin(heading)])
    n=np.array([-u[1],u[0]]);anchor=np.array(base['grip_base_m'])
    across=(pts-anchor)@n
    corridor=valid&(abs(across)<.028)
    selected=corridor&mask(frame,color)[yi,xi]
    if selected.sum()<8:return dict(out,reason='OWN_COLOR_NOT_VISIBLE',color_points=int(selected.sum()))
    # Connected color patches are measured separately, never averaged across distractors.
    from harness.owncam_pair_beam_v2 import _runs
    indices=np.flatnonzero(selected);along=(pts-anchor)@u
    lime=corridor&v1.lime_mask(frame)[yi,xi]
    if v1._INNER is None:v1._INNER=v1._inner_valid()
    candidates=[]
    for run in _runs(along[indices],.025):
        ids=indices[run]
        if len(ids)<8:continue
        lo,hi=np.quantile(along[ids],[.02,.98]);length=float(hi-lo)
        if not .015<=length<=.065:continue
        center=anchor+(lo+hi)/2*u+np.median(across[ids])*n
        offsets=(pts[lime]-center)@u
        if len(offsets)<25:continue
        low,high=np.quantile(offsets,[.02,.98])
        required=.06 if option in ('short_side_v1','anchor_short_v2') else .12
        neg=low < -required and high < .10
        pos=high > required and low > -.10
        if neg==pos:continue
        inward=-u if neg else u
        clipped=bool(np.any(~v1._INNER[yi[ids],xi[ids]]))
        candidates.append(dict(out,reason='BAND_CLIPPED' if clipped else 'BAND_VISIBLE',
            end_visible=not clipped,grip_source='band_centre',color_points=len(ids),
            grip_base_m=center.tolist(),near_end_base_m=(center-.03*inward).tolist(),
            axis_heading_rad=math.atan2(inward[1],inward[0]),endpoint_model=PROFILE,
            observed_band_side='far' if neg else 'near',
            band=dict(length_m=length,points=len(ids),touches_invalid_border=clipped),
            endpoint_side_evidence=dict(q02_m=float(low),q98_m=float(high),threshold_m=required)))
    if len(candidates)!=1:return dict(out,reason='OWN_COLOR_GEOMETRY_UNRESOLVED',candidates=len(candidates))
    return candidates[0]


def install(tr,option='off'):
    if option=='off':return
    if option not in OPTIONS:raise ValueError('UNKNOWN_END_COLOR_POLICY')
    from harness.e2e_live_mapping import camera_transform
    from harness.owncam_view import _pixel_rays
    def rays(servo,step=8):
        origin,rotation=camera_transform(servo);xs,ys,normal,valid=_pixel_rays(step)
        d=np.column_stack((normal,np.ones(len(normal))))@rotation.T
        d/=np.linalg.norm(d,axis=1,keepdims=True)
        return origin,d,xs,ys,valid
    tr.end_colors=option
    for rid in ('r1','r2'):
        r=tr.robots[rid]
        r.observe_beam=lambda image,servo,color=ORDER[rid]:observe(image,servo,color,rays,option)
        previous=r.beam or getattr(r,'last_beam',None) or (getattr(r,'grasp_track',None) or {}).get('beam')
        r.color_search_anchor=(dict(pose_own_m=[*previous['pose_own_m'][:2],0.],rgb=copy.deepcopy(previous['rgb']))
            if previous and option in ('anchor_v2','anchor_short_v2') else None)
        # Only the old center may guide search, never a grip/axis/end assignment.
        # The restored black-band history cannot establish a colored end identity.
        r.beam=None;r.last_beam=None;r.beam_observation=None;r.grasp_track=None
        tr.approach.pop(rid,None)
    tr.event(0.,'static_end_color_order',order=ORDER,profile_sha256=record()['sha256'],
        restored_black_band_identity_cleared=True,communication_independent=True)


def step(tr,rid,now,state):
    """Seed own-color geometry or scan; no B-dependent/local-axis sign assignment."""
    mode=getattr(tr,'end_colors','off')
    if mode=='off':return False,None
    from harness.self_odom_grid import transform
    from harness.zone_s3_coarse_fine import arm,PARAMS
    r=tr.robots[rid];b=r.beam
    fresh=b is not None and 0<=now-b['rgb']['t_sim']<=.45
    if fresh:
        pose=np.asarray(r.goal.explorer.local_pose)
        grip=transform([b['grip_base_m']],pose)[0]
        yaw=pose[2]+b['axis_heading_rad'];yaw=math.atan2(math.sin(yaw),math.cos(yaw))
        inward=np.array([math.cos(yaw),math.sin(yaw)])
        reach=arm.MOUNT_X_M+PARAMS['pair_radius_m']
        state.update(station=np.r_[grip-reach*inward,yaw],grip=grip,last_seen=now,
            basis=dict(yaw_rad=yaw,center_m=b['pose_own_m'][:2],rgb=copy.deepcopy(b['rgb']),rule='static_own_color_'+ORDER[rid]))
        state.pop('color_scan',None);state.pop('acquisition',None)
        return True,None
    age=now-state.get('last_seen',-math.inf)
    retention=2. if mode=='scan_v1' else 30.
    if 'station' in state and age<=retention:return True,None
    state.pop('station',None);state.pop('grip',None)
    if mode in ('anchor_v2','anchor_short_v2','sweep_v2'):
        # Reuse the settled-image/goal-angle bounded search already used by the baseline.
        # Explicit target=None prevents its legacy remembered-end station shortcut.
        from harness.e2e_pregrasp_acquire import acquire
        previous=r.last_beam
        if previous is None:r.last_beam=getattr(r,'color_search_anchor',None)
        try:action=acquire(tr,rid,now,state,None)
        finally:r.last_beam=previous
        if action is None:raise ValueError('COLOR_SEARCH_REQUIRES_EXISTING_ACQUISITION_SKILL')
        return True,action
    scan=state.setdefault('color_scan',dict(started=now,index=-1))
    from harness.owncam_pair_beam_v2 import pose_of
    index=int((now-scan['started'])/2.)%8
    r.carrier_approach=dict(t=now,status='search_own_color',target_color=ORDER[rid],scan_index=index)
    if index<6:
        views=[('search',1500),('p45',1500),('inspect',1500),('search',1200),('search',1800),('search',1500)]
        if scan['index']!=index:
            tag,pan=views[index];pwm=pose_of(tag);pwm[6]=pan
            tr._poses(rid,now,[(pwm,.3,.6)]);scan['index']=index
            tr.event(now,'own_color_search_view',robot_id=rid,color=ORDER[rid],camera=tag,pan=pan)
        return True,(False,[dict(kind='hold')])
    from harness.e2e_rpp_path import command as rpp_command
    pose=np.asarray(r.goal.explorer.local_pose)
    if index==6:
        from harness.zone_solo_cyan_pulse_cal import action_of
        from harness.active_wall_mapping import compose
        from harness.public_navigation_unknown import from_observed_grid
        from harness.public_navigation.follower import projected_clear
        from harness.public_navigation_recovery import issued_twist
        profiles=[p for p in tr.profiles.values() if not p['loaded'] and p['axis']=='forward' and -.35<=p['u']<0 and p['duration_s']==.1]
        action=action_of(min(profiles,key=lambda p:abs(p['u'])))
        ex=r.goal.explorer;mp=compose(ex.map_to_odom,pose)
        costmap=from_observed_grid(ex.grid,mp,ex.latest,set())
        if not projected_clear(costmap,mp,issued_twist(action),action['duration_s']):action=dict(kind='hold')
    else:
        if scan['index']!=index:scan['yaw']=float(pose[2]+math.pi/3)
        action,_=rpp_command(dict(coordinate_frame=rid+'/own_odom',path_m=[pose[:2].tolist()],status='goal_approach',heading_rad=scan['yaw']),pose,tr.profiles,robot_id=rid)
    scan['index']=index
    return True,(False,[action])
