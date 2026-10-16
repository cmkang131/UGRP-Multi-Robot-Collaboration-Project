"""Own-RGB feedback envelope for optional S2 active rotations, default off.

Nav2 Spin (jazzy spin.cpp 110--139) accumulates measured relative yaw and
reserves stopping distance. Feedback is calibrated RGB homography rotation,
not TF, PF yaw or issued yaw. See the recorded rejected ground-LK candidate.
Finite PWM pulses cannot decelerate continuously: reserve a complete pulse
including its coast, and cancel this optional action if it will not fit.
The confidence envelope is an empirical safeguard, not a formal plant bound.
"""
import copy
import math
import numpy as np
import cv2

from harness.zone_solo_cyan_bias_tempering import closure
from harness.zone_solo_cyan_progress_noise import PARAMS as FLOW
from harness.zone_solo_cyan_flow_fusion import pitch_camera, PARAMS as PITCH
from harness.zone_solo_cyan_pulse_cal import profile_key

OPTION = 'rgb_homography_bound_v1'
PARAMS = dict(max_abs_deg=90., confidence_sigma=3.,
              homography_ransac_px=3., homography_confidence=.995,
              homography_max_iterations=2000,
              frame_max_age_s=FLOW['before_max_age_s'],
              uncertainty_accumulation='sum of interval sigma, no independence assumption',
              unknown_action='cancel optional rotation; hold, then mission replan',
              pulse_reserve='max fixed full pulse curve plus 3sigma, observed pulse plus uncertainty',
              gt_inputs=False)


def yaw_measurement(before, after, cm, pose, table):
    """Calibrated homography rotation, all cheirality-valid solutions bounded.

    OpenCV tutorial demos 3/4: R,t,n decomposition also accounts for the eye
    camera's lever-arm translation. Never assume an optical-centre rotation.
    A floor colour classifier is NOT used to suppress feature corners.
    Ambiguous rotation solutions widen the interval instead of picking the
    one nearest the command or a ground-truth heading.
    """
    from harness import vision_loc_protocol as vp
    from harness.zone_solo_cyan_scene_change import cyan
    vl=vp.load_vis3()[0];K=np.linalg.inv(vl.mp.K_INV)
    images=[vl.mp.undistort(cv2.cvtColor(x,cv2.COLOR_RGB2BGR)) for x in (before,after)]
    gray=[cv2.cvtColor(x,cv2.COLOR_BGR2GRAY) for x in images]
    masks=[cv2.erode(((g>10)&~cyan(im)).astype(np.uint8),np.ones((7,7),np.uint8))*255
           for im,g in zip(images,gray)]
    points=cv2.goodFeaturesToTrack(gray[0],maxCorners=FLOW['max_corners'],
        qualityLevel=FLOW['quality'],minDistance=FLOW['min_distance_px'],mask=masks[0],blockSize=7)
    unknown=dict(status='unknown_texture')
    if points is None:return unknown
    cfg=dict(winSize=(FLOW['lk_window_px'],)*2,maxLevel=FLOW['lk_pyramid_levels'],
        criteria=(cv2.TERM_CRITERIA_EPS|cv2.TERM_CRITERIA_COUNT,30,.01))
    nxt,ok,_=cv2.calcOpticalFlowPyrLK(gray[0],gray[1],points,None,**cfg)
    if nxt is None:return unknown
    back,ok2,_=cv2.calcOpticalFlowPyrLK(gray[1],gray[0],nxt,None,**cfg)
    if back is None:return unknown
    p,q=points[:,0],nxt[:,0];xy=np.rint(q).astype(int)
    inside=(xy[:,0]>=0)&(xy[:,0]<640)&(xy[:,1]>=0)&(xy[:,1]<480)
    good=inside&ok.ravel().astype(bool)&ok2.ravel().astype(bool)&(abs(p-back[:,0]).max(1)<FLOW['fb_max_px'])
    good[inside]&=masks[1][xy[inside,1],xy[inside,0]]>0
    p,q=p[good],q[good]
    if len(p)<FLOW['min_tracks']:return {**unknown,'tracks':len(p)}
    h,inliers=cv2.findHomography(p,q,cv2.RANSAC,PARAMS['homography_ransac_px'],
        maxIters=PARAMS['homography_max_iterations'],confidence=PARAMS['homography_confidence'])
    if h is None or inliers is None:return dict(status='unknown_homography')
    use=inliers.ravel().astype(bool);p,q=p[use],q[use]
    if len(p)<FLOW['min_inliers'] or use.mean()<FLOW['min_inlier_fraction']:
        return dict(status='unknown_homography_consensus',inliers=len(p))
    cw,ch=FLOW['cell_size_px'];cells=len(set((int(x)//cw,int(y)//ch) for x,y in p))
    if cells<FLOW['min_cells']:return dict(status='unknown_spatial_support')
    _,rotations,translations,normals=cv2.decomposeHomographyMat(h,K)
    a=cv2.undistortPoints(p[:,None,:],K,None);b=cv2.undistortPoints(q[:,None,:],K,None)
    possible=cv2.filterHomographyDecompByVisibleRefpoints(rotations,normals,a,b)
    # Pure rotations have a zero normal and no planar cheirality restriction.
    ids=[i for i,n in enumerate(normals) if np.linalg.norm(n)<1e-8]
    if possible is not None:ids+=list(np.asarray(possible).ravel())
    ids=sorted(set(ids))
    if not ids:return dict(status='unknown_homography_cheirality')
    angles=[]
    for i in ids:
        # Fixed mount common uncertainty; differential pitch conservatively
        # enters below as an additional interval, not a discarded direction.
        for pitch in (-PITCH['pitch_common_bound_deg'],0.,PITCH['pitch_common_bound_deg']):
            rotation=pitch_camera(cm,math.radians(pitch))._rot
            body=rotation@rotations[i].T@rotation.T
            angles.append(math.atan2(body[1,0],body[0,0]))
    angles=np.unwrap(angles);lo,hi=float(min(angles)),float(max(angles))
    reproj=cv2.perspectiveTransform(p[:,None,:],h)[:,0]
    residual=float(np.sqrt(np.mean(np.sum((reproj-q)**2,axis=1))))
    # 1px feature error, observed reprojection error and differential pitch.
    # Correlation is not divided by sqrt(feature count).
    pixel_sigma=max(FLOW['feature_pixel_sigma'],residual)/min(K[0,0],K[1,1])
    pitch_sigma=math.radians(PITCH['pitch_independent_bound_deg'])*math.sqrt(2/3)
    sigma=math.hypot(pixel_sigma,pitch_sigma)+(hi-lo)/(2*PARAMS['confidence_sigma'])
    return dict(status='measured',delta_yaw=(hi+lo)/2,sigma_yaw=sigma,
        inliers=len(p),cells=cells,solutions=len(ids),solution_yaws_deg=np.degrees(angles).tolist(),
        reprojection_rms_px=residual)


class RotationEnvelope:
    def __init__(self):
        self.yaw = 0.
        self.sigma_sum = 0.
        self.observed_pulse_bound = 0.
        self.rows = []

    def update(self, observation):
        if observation.get('status') != 'measured':
            return False
        d, s = observation['delta_yaw'], observation['sigma_yaw']
        if not np.isfinite([d, s]).all() or s < 0:
            return False
        self.yaw += d
        self.sigma_sum += s
        self.observed_pulse_bound = max(self.observed_pulse_bound,
            abs(d) + PARAMS['confidence_sigma'] * s)
        return True

    def permit(self, profile):
        curve = np.asarray(profile['mean_curve'])[:, 2]
        reserve = max(float(np.max(abs(curve))) + PARAMS['confidence_sigma'] *
            math.sqrt(profile['prediction_variance'][2]), self.observed_pulse_bound)
        sign = np.sign(profile['mean_delta'][2])
        # Full coast is in the stored pulse curve. Test both the current
        # extent and the next endpoint; the same rule covers the return leg.
        extent = max(abs(self.yaw), abs(self.yaw + sign * reserve))
        upper = extent + PARAMS['confidence_sigma'] * self.sigma_sum
        row = dict(yaw_deg=math.degrees(self.yaw),
            uncertainty_deg=math.degrees(PARAMS['confidence_sigma'] * self.sigma_sum),
            reserve_deg=math.degrees(reserve), upper_deg=math.degrees(upper),
            permitted=bool(upper <= math.radians(PARAMS['max_abs_deg'])))
        self.rows.append(row)
        return row


def attach(runtime, *, active_rotation_guard='off'):
    if active_rotation_guard == 'off':
        return runtime
    if active_rotation_guard != OPTION:
        raise ValueError('unknown active_rotation_guard')
    if not hasattr(runtime, 'active_observation'):
        raise ValueError('active observation attachment required')
    old_step, old_frames, old_record = runtime.step, runtime.on_frames, runtime.record
    active = closure(old_step)['state']
    state = dict(event=None, last=None, anchor=None, guard=None, pose=None, cm=None)
    audit = dict(option=OPTION, parameters=copy.deepcopy(PARAMS), events=[], gt_inputs=False)

    def frames(now, images):
        result = old_frames(now, images)
        obs, rgb = images[runtime.robot_id]
        state['last'] = (float(obs['sim_time']), rgb.copy())
        return result

    def cancel(e, now, reason):
        if not e.get('rotation_guard_stop'):
            e['rotation_guard_stop'] = dict(t=now, reason=reason)
            e['schedule'].clear()
            a = e['action']
            a['planned_added_s'] = a['added_s']
            from harness.zone_solo_cyan_active_observation import LIMITS
            a['added_s'] = min(a['added_s'], now-e['t'] +
                              LIMITS['settle_s'] + LIMITS['observation_wait_s'])
            audit['events'][-1]['stop'] = copy.deepcopy(e['rotation_guard_stop'])
        return [(runtime.robot_id, dict(kind='hold'))]

    def step(now):
        issued = old_step(now)
        e = active['event']
        if e is None:
            state['event'] = None
            return issued
        if state['event'] is not e:
            state.update(event=e, anchor=None, guard=RotationEnvelope(),
                         pose=dict(runtime.servo),
                         cm=runtime.pose.provider.loc._pf.column_model_for(runtime.servo))
            audit['events'].append(dict(t=now, checks=state['guard'].rows, observations=[]))
        moving = [(rid, a) for rid, a in issued if a.get('kind') == 'mecanum']
        if not moving:
            return issued
        if e.get('rotation_guard_stop'):
            return [(runtime.robot_id, dict(kind='hold'))]
        last = state['last']
        if last is None or not -1e-8 <= now-last[0] <= PARAMS['frame_max_age_s']+1e-8:
            return cancel(e, now, 'missing_fresh_own_rgb')
        if dict(runtime.servo) != state['pose']:
            return cancel(e, now, 'commanded_camera_changed')
        anchor = state['anchor'] or last
        try:
            measurement = yaw_measurement(anchor[1], last[1], state['cm'],
                                           state['pose'], runtime.flow.table)
        except (ValueError, np.linalg.LinAlgError, FloatingPointError, cv2.error):
            measurement = dict(status='unknown_numeric')
        audit['events'][-1]['observations'].append(dict(t=now, from_t=anchor[0], **measurement))
        if not state['guard'].update(measurement):
            return cancel(e, now, measurement['status'])
        state['anchor'] = last
        for _, command in moving:
            p = runtime.pulse_profiles[profile_key(command, runtime.pose.provider.loc._pf.load.loaded)]
            if not state['guard'].permit(p)['permitted']:
                return cancel(e, now, 'measured_yaw_plus_uncertainty_and_stop_reserve')
        return issued

    def record():
        out = old_record()
        out['active_rotation_guard'] = copy.deepcopy(audit)
        return out

    runtime.on_frames, runtime.step, runtime.record = frames, step, record
    runtime.rotation_guard_audit = audit
    return runtime
