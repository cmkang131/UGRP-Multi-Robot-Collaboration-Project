"""Default-off S2 calibrated ground-plane visual odometry.

Seegmiller/Wettergreen IROS2011 II-C--F: LK, calibrated inverse perspective
(plane homography), robust metric SE2. Command response is prediction ONLY;
complete visual displacement replaces it once, without fusing the command as
another measurement. This is a delayed PF adapter, not robot_localization EKF.
No simulator state, encoder or live measured arm pose is an input.
"""
import copy
import math
import cv2
import numpy as np
from harness import zone_solo_cyan_slip_detect as slip
from harness.zone_solo_cyan_slip_recovery import Runtime as Previous
from harness.zone_solo_cyan_flow_fusion import PulseBuffer, compose
from harness.zone_solo_cyan_progress_noise import pair
from harness.zone_solo_cyan_floor_contact import floor_pixels
from harness.zone_solo_cyan_scene_change import cyan
from harness.zone_solo_cyan_visibility import K
from harness.zone_solo_cyan_pulse_cal import profile_key
from harness.vision_pose_source_final import camera_key

OPTION = 'ground_vo_v1'
PARAMS = dict(max_track_gap_s=.15, finite_difference_rad=.0001,
              minimum_complete_coverage=1., identical_rgb_fallback=True)


def camera_supported(inner, pose):
    state='loaded' if inner.loc._pf.load.loaded else 'unloaded'
    return all(k in pose for k in (3,4,5,6)) and camera_key(pose) in inner.calibration['camera_models'][state]


def plane_homography(cm, delta):
    """Undistorted image_after -> image_before, fixed floor z=0 and camera.

    G maps metric body-floor coordinates to pixels. The fitted SE2 motion T
    induces H=G T G^-1. Fixed height supplies scale, never a truth trajectory.
    """
    origin=np.asarray(cm.origin);basis=np.column_stack((np.eye(3)[:,:2],-origin))
    g=K @ cm._rot.T @ basis
    c,s=math.cos(delta[2]),math.sin(delta[2])
    t=np.array([[c,-s,delta[0]],[s,c,delta[1]],[0.,0.,1.]])
    h=g@t@np.linalg.inv(g)
    return h/h[2,2]


def ground_pair(before,after,cm,pose,table):
    from harness import vision_loc_protocol as vp
    vl=vp.load_vis3()[0]
    fractions=[]
    for im in (before,after):
        bgr=vl.mp.undistort(cv2.cvtColor(im,cv2.COLOR_RGB2BGR))
        floor=floor_pixels(bgr,table);cargo=cyan(bgr)
        fractions.append(dict(floor_image_fraction=float(floor.mean()),
            cyan_image_fraction=float(cargo.mean()),
            usable_floor_image_fraction=float((floor&~cargo).mean())))
    if np.array_equal(before,after):
        return dict(status='unknown_identical_rgb',image_fractions=fractions)
    obs=pair(before,after,cm,pose,table,metric_observation=True)
    obs['image_fractions']=fractions
    if obs['status']=='measured':obs['homography_after_to_before']=plane_homography(cm,obs['delta']).tolist()
    return obs


def observed_pulse(item,frames,table,pitch_bound_deg):
    p=item['profile'];start=item['t'];end=start+p['times'][-1]
    last_t,last_rgb=item['before'];curve=[np.zeros(3)];times=[0.]
    covariance=np.zeros((3,3));plus=np.zeros(3);minus=np.zeros(3);rows=[];chain=True
    eps=PARAMS['finite_difference_rad']
    for now,rgb in frames:
        if now>end+1e-7:break
        gap=now-last_t;obs=dict(status='unknown_frame')
        if gap>PARAMS['max_track_gap_s']+1e-8:chain=False
        if chain and last_rgb is not None and rgb is not None and gap>1e-8:
            obs=ground_pair(last_rgb,rgb,item['cm'],item['pose'],table)
        if obs['status']=='measured':
            d=np.array(obs['delta']);q=np.array(obs['covariance'])
            covariance=slip.compose_cov(curve[-1],d,covariance,q)
            plus=compose(plus,slip.scale_delta(obs,item['cm'],eps))
            minus=compose(minus,slip.scale_delta(obs,item['cm'],-eps))
            curve.append(compose(curve[-1],d));times.append(now-start)
            old_t=last_t;last_t,last_rgb=now,rgb
            rows.append(dict(t=float(now),from_t=float(old_t),**obs))
        else:
            rows.append(dict(t=float(now),from_t=float(last_t),**obs))
            # Identical pixels do not establish a usable VO measurement. Do
            # not turn absent/stale visual information into zero displacement.
            if obs['status']=='unknown_identical_rgb':chain=False
    complete=bool(chain and abs(last_t-end)<1e-7 and len(curve)>1)
    d=curve[-1];size=float(np.linalg.norm(d[:2]));expected=np.array(p['mean_delta'])
    den=float(np.linalg.norm(expected[:2]));ratio=None if not complete or den<1e-12 else float(d[:2]@expected[:2]/den**2)
    radial_sigma=0.;pitch_cov=np.zeros((3,3))
    if complete and size>1e-12:
        derivative=(np.linalg.norm(plus[:2])-np.linalg.norm(minus[:2]))/(2*eps)
        radial_sigma=abs(derivative)*np.radians(pitch_bound_deg)/np.sqrt(3)
        radial=np.r_[d[:2]/size,0.];pitch_cov=np.outer(radial,radial)*radial_sigma**2
    covariance=(covariance+covariance.T)/2+pitch_cov
    out=copy.deepcopy(p)
    if complete:
        out.update(times=times,mean_curve=np.array(curve).tolist(),mean_delta=d.tolist(),
            prediction_variance=np.diag(covariance).tolist(),prediction_covariance=covariance.tolist())
    is_slip=bool(complete and den>=slip.PARAMS['minimum_expected_m'] and ratio<slip.PARAMS['progress_ratio_threshold'])
    row=dict(t=start,key=item['key'],end=end,loaded=p['loaded'],
        status='slip_replaced' if is_slip else ('normal_measured' if complete else 'unknown_preserved'),
        complete_visual=complete,coverage=1. if complete else 0.,prediction_replaced=complete,
        source='ground_vo' if complete else 'command_prediction_fallback',command_double_counted=False,
        expected_delta=p['mean_delta'],visual_delta=d.tolist() if complete else None,
        applied_delta=out['mean_delta'],delta=out['mean_delta'],
        progress_ratio=ratio,variance=out['prediction_variance'],
        covariance=covariance.tolist() if complete else None,
        pitch_radial_sigma_m=radial_sigma,pitch_scale_relative_sigma=radial_sigma/size if size>1e-12 else None,
        pitch_radial_covariance=pitch_cov.tolist(),intervals=rows,
        direction=[float(item['command'].get(k,0)) for k in ('forward','left')])
    return out,row


class GroundBuffer(PulseBuffer):
    def __init__(self,*args,calibration,**kwargs):
        super().__init__(*args,**kwargs)
        self.calibration=copy.deepcopy(calibration)
        self.audit.update(option=OPTION,parameters=copy.deepcopy(PARAMS),calibration=self.calibration,
            scope='all supported loaded/unloaded translation/rotation/fine command pulses; fixed calibrated poses only',
            covariance='pixel SE2 fit plus common radial pitch-scale uncertainty; no command measurement fusion')
    def command(self,row):
        moving=row['kind'] in ('mecanum','drive') and any(row.get(k,0) for k in ('forward','left','turn'))
        if self.pending is not None:
            if moving or row['kind'] in ('arm','look','initial_servo_command'):self.flush(False)
            else:
                self.pending['events'].append(('command',(copy.deepcopy(row),)));return
        if moving:
            pf=self.inner.loc._pf;key=profile_key(row,pf.load.loaded);p=self.profiles.get(key)
            supported=self.supported(self.inner.servo) and pf.settled(row['t'])
            reason='unsupported_profile' if p is None else ('unsupported_camera_pose' if not supported else 'missing_before_frame')
            if p is not None and supported and self.last is not None and abs(row['t']-self.last[0])<1e-7:
                self.pending=dict(t=float(row['t']),key=key,profile=copy.deepcopy(p),command=copy.deepcopy(row),
                    pose=dict(self.inner.servo),cm=pf.column_model_for(self.inner.servo),before=self.last,
                    frames=[],events=[('command',(copy.deepcopy(row),))])
                return
            self.audit['rows'].append(dict(t=float(row['t']),key=key,status=reason,
                source='command_prediction_fallback',prediction_replaced=False,complete_visual=False,coverage=0.))
        return self.command0(row)
    def flush(self,completed=True):
        item=self.pending
        if item is None:return
        self.pending=None;key=item['key'];old=self.profiles[key]
        if completed:
            p,row=observed_pulse(item,item['frames'],self.table,self.calibration['pitch_scale_bound_deg'])
            if row['prediction_replaced']:self.profiles[key]=p
            self.audit['rows'].append(row)
        else:self.audit['rows'].append(dict(t=item['t'],key=key,status='interrupted',
            source='command_prediction_fallback',coverage=0.,complete_visual=False,prediction_replaced=False))
        try:
            for kind,args in item['events']:(self.command0 if kind=='command' else self.frame0)(*args)
        finally:self.profiles[key]=old


class Runtime(Previous):
    def __init__(self,*args,odom_source='off',ground_vo_calibration=None,**kwargs):
        if odom_source not in ('off',OPTION):raise ValueError('unknown odom_source')
        if odom_source!='off':
            if kwargs.get('slip_detection')!=slip.OPTION:raise ValueError('ground VO requires existing slip detector for recovery evidence')
            if not ground_vo_calibration or not 0<float(ground_vo_calibration.get('pitch_scale_bound_deg',0))<=10:
                raise ValueError('explicit fixed ground VO calibration required')
        super().__init__(*args,**kwargs);self.odom_source=odom_source
        if odom_source!='off':
            old=self.flow;inner=self.pose.provider
            # Replace the old buffer, never nest two buffers/measurements.
            inner.on_command,inner.on_frame,inner.report=old.command0,old.frame0,old.report0
            self.flow=GroundBuffer(inner,old.profiles,lambda pose:camera_supported(inner,pose),
                                   old.table,calibration=ground_vo_calibration)
            from harness.zone_solo_cyan_v106 import hp
            inner.runtime_contract['s2_ground_vo']=dict(option=OPTION,calibration=copy.deepcopy(ground_vo_calibration),
                parameters=copy.deepcopy(PARAMS),gt_inputs=False,command_is_measurement=False)
            inner.identity_sha256=hp.base.digest(inner.runtime_contract)
            inner.source='owncam_pf_s2_ground_vo:'+inner.identity_sha256[:8];self.pose.source=inner.source
    def record(self):
        out=super().record()
        if self.odom_source!='off':out['ground_vo']=copy.deepcopy(self.flow.audit)
        return out
