"""Default-off, S2-only own-RGB pulse innovation / nominal-Q scaling.

Ground-plane LK / rigid RANSAC follows Seegmiller et al., IROS 2011 II-C--F.
Innovation scaling follows Popescu et al. 2026 eqs 13--15, adapted to one
completed command pulse, not an IMU InEKF. It changes uncertainty only: missing
texture is unknown, never zero odometry. No contact/pose truth input exists.
"""
import copy
import math
import cv2
import numpy as np
from harness.zone_solo_cyan_load_height import Runtime as Previous
from harness.zone_solo_cyan_floor_contact import floor_pixels,validate
from harness.zone_solo_cyan_pulse_cal import profile_key
from harness.zone_solo_cyan_visibility import pixel_rays,robot_boxes,shadow_depths

OPTION='ground_flow_noise_v1'
PARAMS=dict(max_corners=240,quality=.01,min_distance_px=5,lk_window_px=21,
    lk_pyramid_levels=3,fb_max_px=1.,min_tracks=6,min_inliers=6,min_cells=2,
    cell_size_px=[160,120],ransac_samples=3,ransac_iterations=200,
    ransac_threshold_m=.005,min_inlier_fraction=.6,feature_pixel_sigma=1.,
    pose_translation_span_m=.03,ground_range_m=[.05,2.],before_max_age_s=.06,
    after_max_lateness_s=.06,minimum_expected_m=.05)


def ground(cm,uv):
    rays=pixel_rays(cm,uv[:,0],uv[:,1])
    depth=np.divide(-cm.origin[2],rays[:,2],out=np.full(len(uv),np.nan),where=abs(rays[:,2])>1e-10)
    return (cm.origin+rays*depth[:,None])[:,:2],depth,rays


def rigid(before,after):
    """Static landmarks: p_before = R(robot_delta_yaw) p_after + robot_delta_xy."""
    a,b=before.mean(0),after.mean(0)
    u,_,vt=np.linalg.svd((before-a).T@(after-b))
    rot=u@np.diag([1.,np.linalg.det(u@vt)])@vt
    return rot,a-rot@b


def rigid_ransac(before,after):
    if len(before)<PARAMS['min_tracks']:return None
    rng=np.random.default_rng(0);best=np.zeros(len(before),bool);best_err=float('inf')
    for _ in range(PARAMS['ransac_iterations']):
        idx=rng.choice(len(before),PARAMS['ransac_samples'],replace=False)
        rot,delta=rigid(before[idx],after[idx])
        e=np.linalg.norm(before-(after@rot.T+delta),axis=1)
        inside=e<PARAMS['ransac_threshold_m'];cost=float(e[inside].sum())
        if inside.sum()>best.sum() or (inside.sum()==best.sum() and cost<best_err):
            best,best_err=inside,cost
    if best.sum()<PARAMS['min_inliers'] or best.mean()<PARAMS['min_inlier_fraction']:return None
    rot,delta=rigid(before[best],after[best])
    # A refit must not silently admit pairs outside the registered residual.
    inside=np.linalg.norm(before-(after@rot.T+delta),axis=1)<PARAMS['ransac_threshold_m']
    if inside.sum()<PARAMS['min_inliers'] or inside.mean()<PARAMS['min_inlier_fraction']:return None
    rot,delta=rigid(before[inside],after[inside])
    return rot,delta,inside


def pair(before,after,cm,pose,table):
    """Metric displacement and covariance from own RGB; no particle/map position."""
    from harness import vision_loc_protocol as vp
    from harness.zone_solo_cyan_scene_change import cyan
    vl=vp.load_vis3()[0]
    images=[vl.mp.undistort(cv2.cvtColor(im,cv2.COLOR_RGB2BGR)) for im in (before,after)]
    gray=[cv2.cvtColor(im,cv2.COLOR_BGR2GRAY) for im in images]
    masks=[]
    for im in images:
        mask=floor_pixels(im,table)&~cv2.dilate(cyan(im).astype(np.uint8),np.ones((5,5),np.uint8)).astype(bool)
        mask=cv2.erode(mask.astype(np.uint8),np.ones((7,7),np.uint8))*255
        mask[:4]=0;mask[-10:]=0;mask[:,:4]=0;mask[:,-4:]=0
        masks.append(mask)
    unknown=dict(status='unknown_texture',tracks=0,inliers=0,cells=0)
    pts=cv2.goodFeaturesToTrack(gray[0],maxCorners=PARAMS['max_corners'],qualityLevel=PARAMS['quality'],
        minDistance=PARAMS['min_distance_px'],mask=masks[0],blockSize=7)
    if pts is None:return unknown
    cfg=dict(winSize=(PARAMS['lk_window_px'],)*2,maxLevel=PARAMS['lk_pyramid_levels'],
        criteria=(cv2.TERM_CRITERIA_EPS|cv2.TERM_CRITERIA_COUNT,30,.01))
    nxt,ok,_=cv2.calcOpticalFlowPyrLK(gray[0],gray[1],pts,None,**cfg)
    if nxt is None:return unknown
    back,ok2,_=cv2.calcOpticalFlowPyrLK(gray[1],gray[0],nxt,None,**cfg)
    if back is None:return unknown
    p,q=pts[:,0],nxt[:,0];xy=np.rint(q).astype(int)
    inside=(xy[:,0]>=0)&(xy[:,0]<640)&(xy[:,1]>=0)&(xy[:,1]<480)
    good=inside&ok.ravel().astype(bool)&ok2.ravel().astype(bool)&(abs(p-back[:,0]).max(1)<PARAMS['fb_max_px'])
    good[inside]&=masks[1][xy[inside,1],xy[inside,0]]>0
    p,q=p[good],q[good]
    a,da,ra=ground(cm,p);b,db,rb=ground(cm,q)
    boxes=robot_boxes(pose,cm)
    lo,hi=PARAMS['ground_range_m']
    valid=np.isfinite(a).all(1)&np.isfinite(b).all(1)&(da>0)&(db>0)
    for points,depth,rays in ((a,da,ra),(b,db,rb)):
        ranges=np.linalg.norm(points,axis=1);valid&=(ranges>=lo)&(ranges<=hi)
        valid&=np.minimum.reduce(list(shadow_depths(cm.origin,rays,boxes).values()))>depth
    p,q,a,b=p[valid],q[valid],a[valid],b[valid]
    cw,ch=PARAMS['cell_size_px'];cells=len(set((int(x)//cw,int(y)//ch) for x,y in p))
    unknown.update(tracks=len(p),cells=cells)
    if len(p)<PARAMS['min_tracks'] or cells<PARAMS['min_cells']:return unknown
    fit=rigid_ransac(a,b)
    if fit is None:return {**unknown,'status':'unknown_rigid_consensus'}
    rot,delta,inside=fit;a,b,p,q=a[inside],b[inside],p[inside],q[inside]
    cells=len(set((int(x)//cw,int(y)//ch) for x,y in p))
    if cells<PARAMS['min_cells'] or np.linalg.svd(b-b.mean(0),compute_uv=False)[-1]<PARAMS['pose_translation_span_m']:
        return {**unknown,'status':'unknown_spatial_support','inliers':len(a),'cells':cells}
    rotated=b@rot.T;residual=a-(rotated+delta)
    jac=np.zeros((2*len(a),3));jac[::2,0]=1;jac[1::2,1]=1
    jac[::2,2]=-rotated[:,1];jac[1::2,2]=rotated[:,0]
    # One-pixel localisation uncertainty propagated through fixed ground rays.
    pixel_var=[]
    for uv in (p,q):
        dx=(ground(cm,uv+[.5,0])[0]-ground(cm,uv-[.5,0])[0])
        dy=(ground(cm,uv+[0,.5])[0]-ground(cm,uv-[0,.5])[0])
        pixel_var.append(float(np.mean(dx*dx+dy*dy))*PARAMS['feature_pixel_sigma']**2)
    sigma2=max(float(np.sum(residual**2)/(2*len(a)-3)),sum(pixel_var))
    cov=sigma2*np.linalg.inv(jac.T@jac)
    return dict(status='measured',tracks=unknown['tracks'],inliers=len(a),cells=cells,
        delta=[float(delta[0]),float(delta[1]),float(math.atan2(rot[1,0],rot[0,0]))],
        covariance=cov.tolist(),fit_rms_m=float(np.sqrt(np.mean(residual**2))))


def scaled_variance(predicted,variance,observed,covariance):
    innovation=np.asarray(observed)-predicted
    innovation[2]=(innovation[2]+np.pi)%(2*np.pi)-np.pi
    q=np.asarray(variance,float)
    alpha=max(1.,float((innovation@innovation-np.trace(covariance))/q.sum()))
    # Nominal, not recursively scaled Q; registered one-pulse M=1 estimator.
    return q*np.sqrt(alpha),alpha


def install(inner,profiles,pose_supported,table):
    old_command,old_frame=inner.on_command,inner.on_frame
    pf=inner.loc._pf;pending=None;last=None
    audit=dict(option=OPTION,parameters=copy.deepcopy(PARAMS),rows=[],gt_inputs=False,
        mean_correction=False,wall_observations_filtered=False,clock='existing delayed capture clock')
    def command(row):
        nonlocal pending
        old_command(row)
        if row['kind'] in ('arm','look','initial_servo_command'):
            pending=None
        if row['kind'] in ('mecanum','drive') and any(row.get(k,0) for k in ('forward','left','turn')):
            pending=None
            if not pf.load.loaded or not pose_supported(inner.servo):return
            p=profiles[profile_key(row,True)]
            if np.linalg.norm(p['mean_delta'][:2])<PARAMS['minimum_expected_m']:return
            base=dict(t=float(row['t']),key=profile_key(row,True),profile=copy.deepcopy(p))
            if last is None or not 0<=row['t']-last[0]<=PARAMS['before_max_age_s']+1e-8:
                audit['rows'].append({**base,'status':'unknown_before_frame'});return
            pending={**base,'before_t':last[0],'before':last[1],
                'pose':dict(inner.servo),'cm':pf.column_model_for(inner.servo),
                'end':float(row['t'])+p['times'][-1]}
    def frame(now,rgb):
        nonlocal pending,last
        if pending is not None and now>=pending['end']-1e-8:
            item=pending;pending=None
            result=dict(status='unknown_after_frame')
            if (rgb is not None and now-item['end']<=PARAMS['after_max_lateness_s']+1e-8
                    and dict(inner.servo)==item['pose']):
                result=pair(item['before'],rgb,item['cm'],item['pose'],table)
            row={k:v for k,v in item.items() if k not in ('before','pose','cm')}
            row.update(after_t=float(now),**result)
            q=np.asarray(item['profile']['prediction_variance']);effective=q.copy()
            if result['status']=='measured':
                effective,alpha=scaled_variance(item['profile']['mean_delta'],q,result['delta'],result['covariance'])
                row['alpha']=alpha
                if alpha>1.:
                    pf.predict_to(now)
                    noise=pf.rng.normal(size=(pf.n,3))*np.sqrt(effective-q)
                    # Calibration variance is in the initial pulse body frame.
                    yaw=pf.px[:,2]-item['profile']['mean_delta'][2]
                    c,s=np.cos(yaw),np.sin(yaw)
                    pf.px[:,0]+=c*noise[:,0]-s*noise[:,1]
                    pf.px[:,1]+=s*noise[:,0]+c*noise[:,1]
                    pf.px[:,2]=(pf.px[:,2]+noise[:,2]+np.pi)%(2*np.pi)-np.pi
                    pf.logw+=pf._map_logprior(pf.px)
            row['effective_variance']=effective.tolist();audit['rows'].append(row)
        last=(float(now),rgb.copy()) if rgb is not None and pf.load.loaded and pose_supported(inner.servo) else None
        return old_frame(now,rgb) # same RGB / wall detector / AMCL path, after covariance only
    inner.on_command=command;inner.on_frame=frame
    return audit


class Runtime(Previous):
    def __init__(self,*args,visual_progress='off',**kwargs):
        if visual_progress not in ('off',OPTION):raise ValueError('unknown visual_progress')
        if visual_progress!='off':
            if kwargs.get('pulse_motion_model')!='v7_pulse_cal_v1':raise ValueError('fixed pulse calibration required')
            validate(kwargs.get('floor_appearance') or {})
        self.visual_progress=visual_progress
        super().__init__(*args,**kwargs)
        if visual_progress!='off':
            inner=self.pose.provider
            self.progress_audit=install(inner,self.pulse_profiles,self.visual_pose_supported,copy.deepcopy(kwargs['floor_appearance']))
            from harness.zone_solo_cyan_v106 import hp
            inner.runtime_contract['s2_visual_progress']=dict(option=OPTION,parameters=PARAMS,gt_inputs=False)
            inner.identity_sha256=hp.base.digest(inner.runtime_contract)
            inner.source='owncam_pf_s2_progress_noise:'+inner.identity_sha256[:8];self.pose.source=inner.source
    def record(self):
        out=super().record()
        if self.visual_progress!='off':out['visual_progress']=copy.deepcopy(self.progress_audit)
        return out
