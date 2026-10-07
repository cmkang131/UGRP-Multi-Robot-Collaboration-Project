"""Default-off S2 slip-check substitution, not command/vision EKF fusion.

MER slip check (Maimone et al. 2007 pp1,17), signed progress ratio convention
(Kilic et al. 2022 Eq1). 0.5 is a preregistered configuration, not universal.
Own RGB/command/fixed geometry only. Command response is a no-slip surrogate,
not an encoder reading; this cannot distinguish slip from a blocked drive.
"""
import copy
import math
import numpy as np
from harness import zone_solo_cyan_flow_fusion as flow
from harness.zone_solo_cyan_progress_noise import pair,ground,rigid
from harness.zone_solo_cyan_pulse_cal import install as install_pulses
from harness.zone_solo_cyan_amcl_update import install as install_amcl

OPTION='slip_detect_v1'
PARAMS=dict(progress_ratio_threshold=.5,minimum_expected_m=.05,max_track_gap_s=.15,
    pitch_scale_bound_deg=2.8,finite_difference_rad=.0001,pitch_distribution='uniform +/- bound',
    minimum_complete_coverage=1.)


def compose_cov(a,b,pa,pb):
    """First-order SE2 measurement covariance, independent feature-fit term."""
    c,s=math.cos(a[2]),math.sin(a[2]);ja=np.eye(3);jb=np.eye(3)
    ja[:2,2]=[-s*b[0]-c*b[1],c*b[0]-s*b[1]];jb[:2,:2]=flow.rot(a[2])
    return ja@pa@ja.T+jb@pb@jb.T


def scale_delta(obs,cm,angle):
    """Geometry sensitivity affects magnitude only, never measured heading."""
    changed=flow.pitch_camera(cm,angle)
    a=ground(changed,np.array(obs['before_uv']))[0];b=ground(changed,np.array(obs['after_uv']))[0]
    _,d=rigid(a,b);nom=np.array(obs['delta'],float);length=np.linalg.norm(nom[:2])
    if length>1e-12:nom[:2]*=np.linalg.norm(d)/length
    return nom


def observed_pulse(item,frames,table):
    profile=item['profile'];start=item['t'];end=start+profile['times'][-1]
    last_t,last_rgb=item['before'];curve=[np.zeros(3)];times=[0.];cov=np.zeros((3,3))
    plus=np.zeros(3);minus=np.zeros(3);rows=[];eps=PARAMS['finite_difference_rad'];chain=True
    for now,rgb in frames:
        if now>end+1e-7:break
        gap=now-last_t;obs=dict(status='unknown_frame')
        if gap>PARAMS['max_track_gap_s']+1e-8:chain=False
        if chain and last_rgb is not None and rgb is not None and gap>1e-8:
            obs=pair(last_rgb,rgb,item['cm'],item['pose'],table,metric_observation=True)
        if obs['status']=='measured':
            d=np.array(obs['delta']);q=np.array(obs['covariance'])
            cov=compose_cov(curve[-1],d,cov,q)
            plus=flow.compose(plus,scale_delta(obs,item['cm'],eps))
            minus=flow.compose(minus,scale_delta(obs,item['cm'],-eps))
            curve.append(flow.compose(curve[-1],d));times.append(now-start)
            rows.append(dict(t=float(now),from_t=float(last_t),**obs))
            last_t,last_rgb=now,rgb
        else:rows.append(dict(t=float(now),from_t=float(last_t),**obs))
    complete=bool(chain and abs(last_t-end)<1e-7 and len(curve)>1)
    d=curve[-1];size=np.linalg.norm(d[:2]);expected=np.array(profile['mean_delta']);den=np.linalg.norm(expected[:2])
    ratio=None if not complete or den<1e-12 else float(d[:2]@expected[:2]/den**2)
    pitch_cov=np.zeros((3,3));radial_sigma=0.
    if complete and size>1e-12:
        derivative=(np.linalg.norm(plus[:2])-np.linalg.norm(minus[:2]))/(2*eps)
        radial_sigma=abs(derivative)*np.radians(PARAMS['pitch_scale_bound_deg'])/np.sqrt(3)
        direction=np.r_[d[:2]/size,0.];pitch_cov=np.outer(direction,direction)*radial_sigma**2
    measured_cov=(cov+cov.T)/2+pitch_cov
    slip=bool(complete and den>=PARAMS['minimum_expected_m'] and ratio<PARAMS['progress_ratio_threshold'])
    result=copy.deepcopy(profile)
    if slip:
        result.update(times=times,mean_curve=np.array(curve).tolist(),mean_delta=d.tolist(),
            prediction_variance=np.diag(measured_cov).tolist(),prediction_covariance=measured_cov.tolist())
    row=dict(t=start,key=item['key'],end=end,status='slip_replaced' if slip else ('normal_preserved' if complete else 'unknown_preserved'),
        complete_visual=complete,coverage=1. if complete else 0.,tracked_fraction=(last_t-start)/profile['times'][-1],
        progress_ratio=ratio,slip_ratio=None if ratio is None else 1-ratio,expected_delta=profile['mean_delta'],
        visual_delta=d.tolist() if complete else None,applied_delta=result['mean_delta'],
        delta=d.tolist() if complete else profile['mean_delta'],
        variance=np.diag(measured_cov).tolist() if complete else profile['prediction_variance'],
        covariance=measured_cov.tolist() if complete else None,pitch_radial_covariance=pitch_cov.tolist(),
        pitch_radial_sigma_m=float(radial_sigma),intervals=rows,
        direction=[float(item['command'].get(k,0)) for k in ('forward','left')])
    return result,row


class SlipBuffer(flow.PulseBuffer):
    def __init__(self,*a,**kw):
        super().__init__(*a,**kw)
        self.audit.update(option=OPTION,parameters=copy.deepcopy(PARAMS),
            scope='S2 loaded coarse translations; normal and unknown command profiles unchanged',
            covariance='pixel-fit SE2 covariance plus common rank-one radial pitch scale; no velocity EKF')
    def flush(self,completed=True):
        item=self.pending
        if item is None:return
        self.pending=None;key=item['key'];old=self.profiles[key]
        if completed:
            p,row=observed_pulse(item,item['frames'],self.table)
            replace=bool(item['replace'] and row['status']=='slip_replaced')
            row['prediction_replaced']=replace
            row['unchanged_profile_exact']=True if replace else p==old
            if replace:self.profiles[key]=p
            self.audit['rows'].append(row)
        else:self.audit['rows'].append(dict(t=item['t'],key=key,status='interrupted',coverage=0.,prediction_replaced=False))
        try:
            for kind,args in item['events']:
                (self.command0 if kind=='command' else self.frame0)(*args)
        finally:self.profiles[key]=old


class Runtime(flow.Runtime):
    def __init__(self,*args,slip_detection='off',stall_recovery='off',**kwargs):
        if slip_detection not in ('off',OPTION):raise ValueError('unknown slip_detection')
        if slip_detection=='off':
            self.slip_detection='off';super().__init__(*args,stall_recovery=stall_recovery,**kwargs);return
        if stall_recovery not in ('off',flow.RECOVERY):raise ValueError('unknown slip recovery')
        if any(kwargs.get(k,'off')!='off' for k in ('visual_odometry','visual_progress','load_motion')):
            raise ValueError('slip substitution cannot stack rejected odometry/noise options')
        if kwargs.get('pulse_motion_model')!='v7_pulse_cal_v1' or kwargs.get('amcl_update')!='ros_motion_v1':
            raise ValueError('slip requires S2 pulse model and motion-triggered AMCL')
        from harness.zone_solo_cyan_floor_contact import validate
        validate(kwargs.get('floor_appearance') or {})
        self.slip_detection=slip_detection
        super().__init__(*args,stall_recovery='off',**kwargs)
        self.stall_recovery=stall_recovery;inner=self.pose.provider;pf=inner.loc._pf
        live=install_pulses(pf,self.pulse_model)
        self.amcl_audit=install_amcl(pf,self.map,preset=self.amcl_update,
            visibility=self.visibility,pose_supported=self.visual_pose_supported)
        self.flow=SlipBuffer(inner,live,self.visual_pose_supported,copy.deepcopy(kwargs['floor_appearance']))
        self.recovery=flow.ProgressRecovery();self.flow_cursor=0;self.recovery_replanned=False
        from harness.zone_solo_cyan_v106 import hp
        inner.runtime_contract['s2_slip_detection']=dict(option=OPTION,parameters=copy.deepcopy(PARAMS),
            stall_recovery=stall_recovery,gt_inputs=False,uses_encoders=False,velocity_ekf=False)
        inner.identity_sha256=hp.base.digest(inner.runtime_contract)
        inner.source='owncam_pf_s2_slip_detect:'+inner.identity_sha256[:8];self.pose.source=inner.source
    def record(self):
        out=super().record()
        if self.slip_detection!='off':out['slip_detection']=copy.deepcopy(self.flow.audit)
        return out
