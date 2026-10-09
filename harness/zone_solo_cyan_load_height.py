"""Default-off S2 load-conditioned motion and independent wall-height support.

Motion variance follows Nav2 OmniMotionModel (alpha1..5), with an explicit
command-response time interpolation instead of measured odometry. Geometry is
calibrated single-view metrology. Canny correspondence is an RGB adaptation,
not semantic proof. No simulator truth or online fitting is available here.
"""
import copy
import cv2
import numpy as np
from harness.zone_solo_cyan_floor_contact import Runtime as Previous
from harness.zone_solo_cyan_visibility import K

LOAD='load_conditioned_v1'
HEIGHT='wall_height_v1'
HEIGHT_PARAMS=dict(wall_height_m=.4,gaussian_kernel=5,canny_thresholds=[100,200],support_radius_px=3)


def omni_noise(profile,alpha,z,fraction):
    """Nav2 longitudinal/orthogonal/yaw variances, in initial pulse body axes.

    Per-pulse covariance distributed in time as independent increments, retaining
    the existing S2 continuous prediction cadence. This is not encoder odometry.
    """
    a1,a2,a3,a4,a5=alpha
    d=np.asarray(profile['mean_delta']);t2=d[:2]@d[:2];r2=d[2]**2
    var=np.maximum([a3*t2+a4*r2,a4*r2+a5*t2,a1*r2+a2*t2],
        [.0005**2,.0005**2,.001**2])*fraction
    parallel,strafe,yaw=(np.asarray(z)*np.sqrt(var)).T
    bearing=np.arctan2(d[1],d[0]);c,s=np.cos(bearing),np.sin(bearing)
    return np.c_[parallel*c+strafe*s,parallel*s-strafe*c,yaw]


def validate_motion(table):
    if (table.get('load_motion_option')!=LOAD or table.get('noise_model')!='nav2_omni_v1'
            or table.get('fit_seed')!=1050 or table.get('runtime_gt') is not False):
        raise ValueError('preregistered offline load calibration required')
    for key in ('0','1'):
        a=np.asarray(table['noise_alpha_1_to_5'][key],float)
        if a.shape!=(5,) or not np.isfinite(a).all() or np.any(a<0):raise ValueError('invalid fixed Omni alpha')


def wall_height_support(cm,obs,edges):
    """Lift each measured floor contact by known height; require observed top.

    Does not consume the detector's t_lo, its predicted wall band, particle
    positions, weights, or map association. Clipped/missing supports are unknown.
    """
    n=len(obs.columns);keep=np.zeros(n,bool);top=np.full((n,2),np.nan)
    valid=(obs.b_kind==1)&np.isfinite(obs.b_lo)
    point=cm.floor_point(cm.t_of_row(obs.b_lo))
    opt=(np.c_[point,np.full(n,HEIGHT_PARAMS['wall_height_m'])]-cm.origin)@cm._rot
    good=valid&np.isfinite(opt).all(1)&(opt[:,2]>0)
    project=opt[good]@K.T;top[good]=project[:,:2]/project[:,2,None]
    visible=np.zeros(n,bool)
    if edges is None:return keep,top,visible
    height,width=edges.shape;r=HEIGHT_PARAMS['support_radius_px']
    for j in np.flatnonzero(good):
        u,v=np.rint(top[j]).astype(int)
        if not (r<=u<width-r and r<=v<height-r):continue
        visible[j]=True
        keep[j]=bool(edges[v-r:v+r+1,u-r:u+r+1].any())
    return keep,top,visible


def install_height(visibility):
    rgb=visibility.on_rgb;apply=visibility.apply;state={'edges':None}
    audit=dict(option=HEIGHT,parameters=copy.deepcopy(HEIGHT_PARAMS),rows=[],gt_inputs=False,
        replaces='floor_appearance_v1',unknown_policy='no measurement, never zero range')
    def on_rgb(image):
        rgb(image);state['edges']=None
        if image is not None:
            from harness import vision_loc_protocol as vp
            und=vp.load_vis3()[0].mp.undistort(cv2.cvtColor(image,cv2.COLOR_RGB2BGR))
            gray=cv2.cvtColor(und,cv2.COLOR_BGR2GRAY)
            state['edges']=cv2.Canny(cv2.GaussianBlur(gray,(5,5),0),100,200)
    def filtered(pf,obs,pose,t):
        masked=apply(pf,obs,pose,t)
        if masked is None:return None
        keep,top,visible=wall_height_support(pf.column_model_for(pose),masked,state['edges'])
        detected=masked.b_kind==1;masked.b_kind[~keep]=0
        audit['rows'].append(dict(t=float(t),before=int(detected.sum()),kept=int(keep.sum()),
            top_in_view=int((visible&detected).sum()),removed=int((detected&~keep).sum()),
            kept_columns=masked.columns[keep].tolist()))
        return masked if keep.any() else None
    visibility.on_rgb=on_rgb;visibility.apply=filtered
    return audit


class Runtime(Previous):
    def __init__(self,*args,load_motion='off',load_motion_calibration=None,contact_geometry='off',**kwargs):
        if load_motion not in ('off',LOAD) or contact_geometry not in ('off',HEIGHT):raise ValueError('unknown S2 load/height option')
        if load_motion!='off':
            validate_motion(load_motion_calibration or {})
            if kwargs.get('pulse_motion_model')!='v7_pulse_cal_v1':raise ValueError('explicit pulse model required')
            kwargs['pulse_calibration']=copy.deepcopy(load_motion_calibration)
        if contact_geometry!='off':
            if kwargs.get('contact_filter','off')!='off':raise ValueError('height replaces appearance; filters cannot be stacked')
            if kwargs.get('visibility_policy')!='nav2_observed_v1':raise ValueError('observed AMCL required')
            static=args[0] if args else kwargs['static']
            # The configured environment has a uniform 0.4m wall profile; no
            # current robot pose or runtime scene state is used for this check.
            if float(static['wall_profile']['height_m'])!=HEIGHT_PARAMS['wall_height_m']:
                raise ValueError('wall height profile mismatch')
        self.load_motion,self.contact_geometry=load_motion,contact_geometry
        super().__init__(*args,**kwargs)
        if load_motion!='off' or contact_geometry!='off':
            from harness.zone_solo_cyan_v106 import hp
            inner=self.pose.provider
            if contact_geometry!='off':self.height_audit=install_height(self.visibility)
            inner.runtime_contract['s2_load_height']=dict(load_motion=load_motion,contact_geometry=contact_geometry,
                calibration_sha256=hp.base.digest(load_motion_calibration) if load_motion!='off' else None,
                height_parameters=HEIGHT_PARAMS if contact_geometry!='off' else None,runtime_gt=False)
            inner.identity_sha256=hp.base.digest(inner.runtime_contract)
            inner.source='owncam_pf_s2_load_height:'+inner.identity_sha256[:8];self.pose.source=inner.source
    def record(self):
        out=super().record()
        if self.load_motion!='off':out['load_motion']=dict(option=self.load_motion,fit_seed=1050,runtime_gt=False)
        if self.contact_geometry!='off':out['contact_geometry']=copy.deepcopy(self.height_audit)
        return out
