"""Default-off colour-supported Manhattan compass with a retained null mode.

Only own RGB, issued PWM rotation and own predicted yaw enter. Image line l has
plane normal K.T@l; a world-horizontal line has body direction z cross R@n.
No camera origin/loaded metric FK, simulator pose, held-object pose or top RGB.
GlobustVP §3 geometry; spatial checks and delayed confirmation are our adapter.
"""
import hashlib,math
import cv2
import numpy as np
from harness.natural_floor_slam import wrap
from harness.reloc15_heading import commanded_rotation
from harness.scene_colour_boundary import surface_masks

OPTION='reloc16_wall_compass_v1'
TASK_YAW_RAD=math.radians(5)  # existing task heading precision, never relaxed
AXIS_PERIOD=math.pi/2        # Manhattan axis ambiguity, geometric not fitted


def axis_wrap(a):
    return (a+AXIS_PERIOD/2)%AXIS_PERIOD-AXIS_PERIOD/2


def contacts(und,calibration,columns,p):
    masks,score=surface_masks(und,calibration,expanded_wall_value=True);points=[]
    half,window=int(p['strip_half_px']),int(p['window_px']);band=int(p['band_px'])
    gray=cv2.cvtColor(und,cv2.COLOR_BGR2GRAY).astype(float)
    for u in columns:
        sl=slice(max(0,u-half),min(und.shape[1],u+half+1))
        f=np.median(masks['floor'][:,sl],axis=1).astype(bool)
        w=np.median(masks['wall'][:,sl],axis=1).astype(bool)
        s=np.median(score[:,sl],axis=1)-calibration['split']
        for v in np.flatnonzero((s[:-1]>0)&(s[1:]<=0))[::-1]:
            wa=w[max(0,v-band):v+1];fb=f[v+1:min(len(f),v+1+band)]
            support=lambda a:len(a)>=window and np.any(np.convolve(a.astype(int),np.ones(window,int),'valid')>window/2)
            if not support(wa) or not support(fb):continue
            lum=np.median(gray[:,sl],axis=1)
            edges=np.arange(max(0,v-window),min(len(lum)-1,v+window+1))
            row=float(edges[np.argmax(abs(lum[edges+1]-lum[edges]))])
            points.append([float(u),row]);break
    return np.asarray(points,float).reshape(-1,2)


def fit_line(points):
    # Intercepts at infinity are valid; normalized SVD retains that case.
    a=np.column_stack([points,np.ones(len(points))])
    if np.linalg.matrix_rank(a[:,:2]-a[:,:2].mean(0))<1:return None
    _,_,v=np.linalg.svd(a,full_matrices=False);l=v[-1]
    n=np.linalg.norm(l[:2])
    return l/n if n>np.finfo(float).eps else None


def line_axis(line,K,R):
    n=R@K.T@line
    if np.linalg.norm(n[:2])<=np.finfo(float).eps:return None
    return axis_wrap(-math.atan2(n[0],-n[1]))


def certify_points(points,K,R,*,residual_px,min_columns,cell_size=(160,120)):
    """Finite all-pair consensus, then disjoint spatial fits and nuisance bounds.

    min_columns is inherited HFW run support; grid160x120 is inherited S2.
    Pixel bound1.5 is original v1 boundary p95, not tuned to carry failures.
    Common pitch±2.8 and independent±.9 are inherited S2, not loaded-certified.
    """
    from harness.zone_solo_cyan_flow_fusion import PARAMS as PITCH
    from harness.zone_solo_cyan_rotation_envelope import PARAMS as YAW
    unknown=dict(status='unknown_static_support',method=OPTION,contact_columns=len(points),
                 truth_inputs=0,null_hypothesis_retained=True,metric_fix_refreshed=False)
    if len(points)<min_columns:return unknown
    best=np.zeros(len(points),bool);checks=0
    for i in range(len(points)-1):
        for j in range(i+1,len(points)):
            l=np.cross([*points[i],1.],[*points[j],1.]);norm=np.linalg.norm(l[:2])
            if norm==0:continue
            keep=abs(np.column_stack([points,np.ones(len(points))])@l/norm)<=residual_px
            checks+=1
            if keep.sum()>best.sum():best=keep
    support=points[best];blocks=[]
    if len(support)<min_columns:return unknown
    cells=np.floor_divide(support,cell_size).astype(int)
    for cell in sorted(set(map(tuple,cells))):
        subset=support[(cells==cell).all(1)]
        if len(subset)<min_columns:continue
        line=fit_line(subset)
        if line is not None:blocks.append((cell,subset,line))
    # At least two disjoint image regions: the existing S2 minimum cells. Each
    # must independently fit the same mode; one tiny foreground cannot pass.
    from harness.zone_solo_cyan_progress_noise import PARAMS as FLOW
    unknown.update(static_columns=len(support),spatial_blocks=len(blocks),line_pair_checks=checks)
    if len(blocks)<FLOW['min_cells']:return unknown
    centre=line_axis(fit_line(support),K,R)
    if centre is None:return {**unknown,'status':'unknown_yaw_observability'}
    intervals=[]
    pitch_bound=math.radians(PITCH['pitch_common_bound_deg']+PITCH['pitch_independent_bound_deg'])
    # Propagate the whole line's observed endpoints; refitting a short cell's
    # endpoints as if they were the full line inflated the yaw bound (R2:
    # measurable2/88). Spatial verification is held-out prediction, not an
    # unjustified iid point-count covariance reduction.
    ends=support[[support[:,0].argmin(),support[:,0].argmax()]]
    angles=[]
    for e0 in (-residual_px,residual_px):
        for e1 in (-residual_px,residual_px):
            edge=ends.copy();edge[:,1]+=[e0,e1]
            l=np.cross([*edge[0],1.],[*edge[1],1.])
            for pitch in (-pitch_bound,0.,pitch_bound):
                c,s=math.cos(pitch),math.sin(pitch)
                Rp=R@np.array([[1,0,0],[0,c,-s],[0,s,c]])
                angle=line_axis(l,K,Rp)
                if angle is None:return {**unknown,'status':'unknown_yaw_observability'}
                angles.append(centre+axis_wrap(angle-centre))
    spatial_errors=[];nominal=[]
    for cell,held,line in blocks:
        other=support[~(cells==cell).all(1)]
        fit=fit_line(other)
        if fit is None:return {**unknown,'status':'unknown_spatial_revalidation'}
        residual=abs(np.column_stack([held,np.ones(len(held))])@fit)
        # The source calibration names p95=1.5px. Test the same percentile on
        # the excluded region; no uncalibrated agreement angle is introduced.
        spatial_errors.append(float(np.percentile(residual,95)))
        a=line_axis(fit,K,R)
        if a is None:return {**unknown,'status':'unknown_yaw_observability'}
        nominal.append(centre+axis_wrap(a-centre))
    spatial_ok=all(e<=residual_px for e in spatial_errors)
    lo=min([*angles,*nominal]);hi=max([*angles,*nominal])
    radius=max(abs(centre-lo),abs(hi-centre))
    detail=dict(**unknown,axis_yaw_rad=centre,spatial_yaws_rad=nominal,
                heldout_residual_p95_px=spatial_errors,uncertainty_interval_rad=[lo,hi],
                uncertainty_bound_rad=radius,sigma_yaw=radius/YAW['confidence_sigma'],
                spatial_consistent=spatial_ok,command_extrinsics_only=True)
    if not spatial_ok:return {**detail,'status':'unknown_spatial_revalidation'}
    if not math.isfinite(radius) or radius>TASK_YAW_RAD:return {**detail,'status':'unknown_yaw_observability'}
    return {**detail,'status':'measured'}


class CompassHeading:
    def __init__(self,*,calibration=None,sample_s=.2,wall_tracking_v1=False):
        from harness.active_wall_vision import modules
        mp,hfw,_=modules()
        if calibration is None:
            state=getattr(hfw,'scene_colour_state',None)
            if state is None or state.option!='scene_colour_transition_v2':
                raise ValueError('reloc16 requires frozen scene colour v2 facade')
            calibration=state.calibration
        self.mp,self.calibration,self.p=mp,calibration,hfw.PARAMS
        self.sample_s=sample_s;self.servo=None;self.servo_since=None
        self.last_t=None;self.last_hash=None;self.pending=None;self.command_total=0.
        self.wall_tracking_v1=wall_tracking_v1;self.previous_rgb=None
        self.accepted=0;self.last_measurement_t=None
        self.last=dict(category='no_pair',option=OPTION)

    def issue(self,issued,delta):
        pwm={int(k):int(v) for k,v in issued['pwm'].items()}
        if pwm!=self.servo:self.servo_since=issued['t'];self.pending=None;self.previous_rgb=None
        self.servo=pwm;self.command_total+=delta[2]

    def observe(self,rgb,now,own):
        if self.last_t is not None and now-self.last_t<self.sample_s-1e-8:return
        self.last_t=now
        self.last=dict(option=OPTION,category='weak_observation',status='unknown_servo_settle',
            blocked_object='own_rgb_wall_floor_background',minimum_gap_m=None,
            gap_status='not_applicable_localization_gate',exposure_sim_t=now,
            last_measurement_t=self.last_measurement_t,null_hypothesis_retained=True,metric_fix_refreshed=False)
        from harness.e2e_rgb_vo import PARAMS
        held=self.servo is not None and self.servo[1]<=1600
        if self.servo is None or now-self.servo_since<PARAMS['settle_s'][int(held)]:return
        digest=hashlib.sha256(rgb.tobytes()).hexdigest()
        if digest==self.last_hash:self.last['status']='unknown_repeated_rgb';return
        self.last_hash=digest
        if self.wall_tracking_v1 and self.previous_rgb is not None:
            from harness.reloc16_wall_tracking import track
            wall=track(self.previous_rgb,rgb,self.calibration)
            wall.pop('before_uv',None);wall.pop('after_uv',None)
            self.last['wall_tracking']=wall
        self.previous_rgb=rgb.copy()
        und=self.mp.undistort(cv2.cvtColor(rgb,cv2.COLOR_RGB2BGR))
        points=contacts(und,self.calibration,self.mp.column_positions(96,2),self.p)
        observation=certify_points(points,np.linalg.inv(self.mp.K_INV),commanded_rotation(self.servo),
            residual_px=self.calibration['line_residual_px_p95'],min_columns=self.p['min_run_columns'])
        self.last.update(observation,requires_active_view=observation['status']!='measured')
        if observation['status']!='measured':self.pending=None;return
        axis=observation['axis_yaw_rad'];prior=float(own.x[2]);radius=observation['uncertainty_bound_rad']
        yaw=wrap(prior+axis_wrap(axis-prior))
        # A branch whose uncertainty meets a neighbouring90deg mode is unknown.
        if abs(wrap(yaw-prior))+radius>=AXIS_PERIOD/2:
            self.pending=None;self.last['status']='unknown_axis_ambiguity';return
        old=self.pending
        self.pending=dict(yaw=yaw,radius=radius,command_total=self.command_total,t=now)
        self.last.update(observed_yaw_rad=yaw,prior_yaw_rad=prior)
        if old is None:self.last['status']='pending_next_rgb';return
        from sim.solo_carry_pose import MOTION_ERROR
        delta=self.command_total-old['command_total']
        innovation=wrap(yaw-old['yaw']-delta)
        bound=radius+old['radius']+MOTION_ERROR['rotation_fraction']*abs(delta)
        self.last.update(temporal_innovation_rad=innovation,temporal_bound_rad=bound,
                         delayed_confirm_sim_s=now-old['t'],confirmation_exposure_t=old['t'])
        if abs(innovation)>bound:self.last['status']='unknown_temporal_revalidation';return
        # Absolute Manhattan mode, never a homography increment midpoint; do not
        # fuse the same RGB twice or reset xy/whole-pose fix age or slip budget.
        correction=wrap(yaw-prior);own.x[2]=yaw
        own.P[2,2]=max(float(own.P[2,2]),observation['sigma_yaw']**2)
        self.accepted+=1;self.last_measurement_t=now
        self.last.update(status='accepted',category='accepted_rgb_yaw',correction_rad=correction,
            accepted=self.accepted,last_measurement_t=now,null_hypothesis_retained=False)
