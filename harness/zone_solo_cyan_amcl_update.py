"""Default-off S2 port of Nav2 AMCL's motion-triggered sensor update.

Reference: navigation2 235fc5ce55bdf94d9be360fdbca39d89dc0e4f74,
amcl_node.cpp, likelihood_field_model{,_prob}.cpp, pf.c (LGPL-2.1+).
Preserves first scan, strict odometry thresholds, hit/random models, optional
converged-only beam skipping, and multinomial resampling at sensor updates.
Necessary adapters: RGB floor endpoints, own commanded pulse odometry, fixed
particle count (min=max existing N) and coupled latent states. No live truth.
"""
import copy
import math
from collections import Counter
import numpy as np
from harness.zone_solo_cyan_real_carry_dev import Runtime as Previous
from harness.zone_solo_cyan_likelihood_field import Field,PARAMS,endpoints,likelihood
from harness import zone_solo_cyan_v106 as legacy

PRESETS=('ros_motion_v1','ros_motion_prob_v1')
BEAM=dict(distance=.5,threshold=.3,error_threshold=.9,converged_distance=.5)
SEARCH_UNCERTAINTY={'CYAN_NOT_UNIQUELY_VISIBLE','CYAN_REGRASP_NOT_UNIQUELY_VISIBLE','CYAN_ALIGN_VIEW_LOST'}


def moved(delta):
    return (np.any(abs(delta[:2])>PARAMS['update_min_d_m']) or
            abs(math.atan2(math.sin(delta[2]),math.cos(delta[2])))>PARAMS['update_min_a_rad'])


def converged(px):
    return bool(np.all(abs(px[:,:2]-px[:,:2].mean(0))<=BEAM['converged_distance']))


def probability_loglik(field,px,points,*,is_converged):
    """Nav2 likelihood_field_prob; missing RGB beams never become fake ranges."""
    c,s=np.cos(px[:,2,None]),np.sin(px[:,2,None])
    x=px[:,0,None]+c*points[None,:,0]-s*points[None,:,1]
    y=px[:,1,None]+s*points[None,:,0]+c*points[None,:,1]
    d=field.distances(np.stack((x,y),axis=-1))
    p=PARAMS['z_hit']*np.exp(-d*d/(2*PARAMS['sigma_hit_m']**2))+PARAMS['z_rand']/PARAMS['range_max_m']
    keep=np.ones(len(points),bool);fallback=False
    if is_converged:
        keep=np.mean(d<BEAM['distance'],axis=0)>BEAM['threshold']
        if np.count_nonzero(~keep)>=len(keep)*BEAM['error_threshold']:
            keep[:]=True;fallback=True
    return np.log(p[:,keep]).sum(1),dict(beam_skip_enabled=is_converged,
        skipped=int(np.count_nonzero(~keep)),fallback_all=fallback)


def resample(pf):
    """pf.c CDF sampler with min=max N, recovery alphas=0, no roughening."""
    # Nav2 consumes one recovery draw then one CDF draw per retained sample.
    u=pf.rng.random((pf.n,2))[:,1]
    idx=np.minimum(np.searchsorted(np.cumsum(pf._weights()),u,side='right'),pf.n-1)
    for key in ('px','scale','stuck','yaw_bias','yaw_extra','drift'):
        value=getattr(pf,key,None)
        if value is not None:setattr(pf,key,value[idx].copy())
    pf.logw=np.zeros(pf.n);pf._inject=0.
    pf.stats['resamples']+=1


def install(pf,static,*,preset,visibility=None,pose_supported=None):
    field=Field(static);predict=pf.predict_to
    state=dict(odom=np.zeros(3),anchor=None,converged=False)
    audit=dict(option=preset,scope='S2 all calibrated stationary arm poses, unloaded and loaded',
        parameters={**copy.deepcopy(PARAMS),'do_beamskip':preset=='ros_motion_prob_v1',
                    'resample_interval':1,'recovery_alpha_slow':0.,'recovery_alpha_fast':0.},
        beam=copy.deepcopy(BEAM),absolute_fix=False,candidates=0,updates=0,resamples=0,rows=[],skips=Counter(),
        adaptations='RGB endpoints; own pulse odometry; fixed N with latent-state ancestry; no KLD size change',
        force_update_on_posture_change=False,gt_inputs=False)
    def predict_to(t):
        while pf.t<t-1e-9:
            before=float(pf.t);predict(min(t,before+.05));dt=float(pf.t)-before
            if dt<=0:raise ValueError('pulse prediction clock did not advance')
            vx,vy,w=pf.vel;co,si=np.cos(state['odom'][2]),np.sin(state['odom'][2])
            state['odom']+=np.array([co*vx-si*vy,si*vx+co*vy,w])*dt
    def estimate(t,used=False):
        out=pf.estimate();out['measured']=used
        out['since_scan_s']=None if pf.last_scan_t is None else round(t-pf.last_scan_t,3)
        return out
    def skip(t,reason):
        audit['skips'][reason]+=1
        # Crucially do not delegate update(None): legacy normalizes/resamples
        # even without a sensor update. Predicting own motion remains permitted.
        return estimate(t)
    def update(t,obs,pose):
        predict_to(t)
        if not pf.initialized or obs is None or not pf.settled(t):return skip(t,'no_settled_observation')
        delta=None if state['anchor'] is None else state['odom']-state['anchor']
        if delta is not None and not moved(delta):return skip(t,'below_motion_threshold')
        if pf.load.loaded and visibility is not None:
            if pose_supported is not None and not pose_supported(pose):return skip(t,'loaded_transit')
            obs=visibility.apply(pf,obs,pose,t)
            if obs is None:return skip(t,'visibility_unknown')
        cm=pf.column_model_for(pose)
        if preset=='ros_motion_prob_v1':
            # Nav2 probability model uses ceil(range_count/max_beams), while
            # the default field model uses floor((count-1)/(max_beams-1)).
            idx=np.arange(0,len(obs.columns),max(1,math.ceil(len(obs.columns)/PARAMS['max_beams'])))
            thin=copy.copy(obs)
            thin.b_kind=obs.b_kind.copy();thin.b_kind[np.setdiff1d(np.arange(len(obs.columns)),idx)]=0
            points=endpoints(cm,thin)
        else:points=endpoints(cm,obs)
        if not len(points):return skip(t,'no_rgb_floor_endpoint')
        w0=pf._weights();extra={}
        if preset=='ros_motion_prob_v1':ll,extra=probability_loglik(field,pf.px,points,is_converged=state['converged'])
        else:ll=np.log(likelihood(field,pf.px,points))
        posterior=w0*np.exp(ll-ll.max());posterior/=posterior.sum()
        kl=float(np.sum(posterior*np.log(np.maximum(posterior,1e-300)/np.maximum(w0,1e-300))))
        used=bool(kl>1e-12);state['anchor']=state['odom'].copy()
        audit['candidates']+=1
        q=dict(t=float(t),accepted=True,informative=used,settled=True,visual_weight_update=used,
               absolute_fix=False,reason='soft_weight_update' if used else 'constant_likelihood',
               model=preset,columns=len(points),kl=kl,odom=state['odom'].tolist(),
               delta=None if delta is None else delta.tolist(),**extra)
        if used:
            pf.last_scan_t=float(t);pf.v3_last_fix_quality=copy.deepcopy(q)
            pf.stats['scan_updates']+=1;pf.stats['scan_columns']+=len(points);audit['updates']+=1
            for key,gain in pf._gains(w0,posterior).items():
                if gain>=pf.robust['info_gain_min']:pf.last_info_t[key]=float(t)
        pf.logw=np.log(np.maximum(posterior,1e-300));pf._inject=0.
        pf.diag=dict(amcl_update=copy.deepcopy(q));pf.partial_fix_last=copy.deepcopy(q)
        resample(pf);audit['resamples']+=1;state['converged']=converged(pf.px)
        q['converged_after']=state['converged'];audit['rows'].append(q)
        return estimate(t,used)
    pf.predict_to=predict_to;pf.update_obs=update
    return audit


class Runtime(Previous):
    def __init__(self,*args,amcl_update='off',dev_search='off',**kwargs):
        if amcl_update not in ('off',*PRESETS):raise ValueError('unknown amcl_update')
        if dev_search not in ('off','repeat_views_v1'):raise ValueError('unknown dev_search')
        if amcl_update!='off' and kwargs.get('pulse_motion_model')!='v7_pulse_cal_v1':
            raise ValueError('AMCL own odometry requires the fixed pulse model')
        self.amcl_update,self.dev_search=amcl_update,dev_search
        super().__init__(*args,**kwargs)
        if amcl_update!='off':
            static=args[0] if args else kwargs['static'];inner=self.pose.provider
            self.amcl_audit=install(inner.loc._pf,static,preset=amcl_update,
                visibility=self.visibility,pose_supported=self.visual_pose_supported)
            inner.runtime_contract['s2_amcl_update']=dict(option=amcl_update,
                parameters=copy.deepcopy(self.amcl_audit['parameters']),gt_inputs=False)
            inner.identity_sha256=legacy.hp.base.digest(inner.runtime_contract)
            inner.source='owncam_pf_s2_amcl_update:'+inner.identity_sha256[:8];self.pose.source=inner.source

    def fail(self,code,now):
        if self.dev_search!='off' and code in SEARCH_UNCERTAINTY:
            self.soft(code,now);self.search_i=0;self.target=None;self.target_t=None
            self.path=[];self.path_goal=None
            self.queue(legacy.pose_of('search'),now)
            self.set_state('search_move',now)
            return [{'kind':'hold'}]
        return super().fail(code,now)

    def record(self):
        out=super().record()
        if self.amcl_update!='off':
            out['legacy_soft_measurement']=out.get('soft_measurement')
            out['amcl_update']=copy.deepcopy(self.amcl_audit)
            out['soft_measurement']=copy.deepcopy(self.amcl_audit)
        if self.dev_search!='off':out['dev_search']=dict(option=self.dev_search,
            scope='S2 DEV search exhaustion log-only; repeat existing two views; finite global cap unchanged')
        return out
