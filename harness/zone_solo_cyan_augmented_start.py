"""Default-off S2 unknown-start localization; no dock labels or truth inputs.

Augmented MCL: Nav2 235fc5ce pf.c / Probabilistic Robotics Table 8.3.
Selective resampling: ROS navigation f44bb1fc pf.c (LGPL-2.1+).
Active sensor pointing: Fox, Burgard, Thrun 1998, section 4.3, equation 13.
Adapters: fixed-N own-RGB endpoint likelihood, finite calibrated wrist pans,
one central-ray observation for planning, command-settled view identity.
The active score predicts information, not an observed localization success.
"""
import copy
import math

import numpy as np
from scipy.special import ndtr

from harness.zone_solo_cyan_global_start import Runtime as Previous
from collections import Counter
from harness.zone_solo_cyan_amcl_update import (converged, moved, resample, probability_loglik, BEAM)
from harness.zone_solo_cyan_likelihood_field import Field, PARAMS, endpoints, likelihood
from harness.zone_solo_cyan_v106 import LOOK_P20, hp

OPTION = 'augmented_active_v1'
ALPHA_SLOW, ALPHA_FAST = .001, .1
PANS = (1500, 1230, 970, 1770, 2030)


# Isolated port of the frozen AMCL update; never edit its hash-pinned source.
def install_global_update(pf,static,*,preset,visibility=None,pose_supported=None):
    field=Field(static);predict=pf.predict_to
    state=dict(odom=np.zeros(3),anchor=None,converged=False)
    audit=dict(option=preset,scope='S2 initial global scan, then unchanged AMCL tracking',
        parameters={**copy.deepcopy(PARAMS),'do_beamskip':preset=='ros_motion_prob_v1',
                    'resample_interval':1,'recovery_alpha_slow':ALPHA_SLOW,
                    'recovery_alpha_fast':ALPHA_FAST,'selective_resampling_ess_fraction':.5},
        beam=copy.deepcopy(BEAM),global_localization=OPTION,absolute_fix=False,candidates=0,updates=0,resamples=0,rows=[],skips=Counter(),
        adaptations='RGB endpoints; own pulse odometry; fixed N with latent-state ancestry; no KLD size change',
        force_update_on_posture_change='new settled pose once per motion epoch during initial global scan only',
        tracking_after_global=dict(recovery_alpha_slow=0.,recovery_alpha_fast=0.,selective_resampling=False),gt_inputs=False)
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
        policy=getattr(pf,'s2_global_policy',None)
        new_view=policy is not None and policy.new_view(pose)
        if delta is not None and not moved(delta) and not new_view:return skip(t,'below_motion_threshold')
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
        if policy is None:
            resample(pf);audit['resamples']+=1
        else:
            details=policy.measure(pf,w0,ll,pose,delta is None or moved(delta))
            audit['resamples']+=int(details['resampled']);q['global_localization']=details
        state['converged']=converged(pf.px)
        q['converged_after']=state['converged'];audit['rows'].append(q)
        return estimate(t,used)
    pf.predict_to=predict_to;pf.update_obs=update
    return audit


def pose_key(pose):
    return tuple(int(pose[k]) for k in (3, 4, 5, 6))


def belief_report(px, weights):
    """Full posterior moments and disjoint bins, never a connected-cluster claim."""
    w = np.asarray(weights); p = np.asarray(px)
    xy = w @ p[:, :2]
    cs, sn = w @ np.cos(p[:, 2]), w @ np.sin(p[:, 2])
    yaw = math.atan2(sn, cs)
    d = p[:, :2] - xy
    cov = np.zeros((3, 3)); cov[:2, :2] = (w[:, None]*d).T @ d
    cov[2, 2] = max(0., -2*math.log(max(math.hypot(cs, sn), 1e-300)))
    bins, ids = np.unique(np.floor(p/[.5, .5, math.pi/18]).astype(int), axis=0, return_inverse=True)
    masses = np.bincount(ids, weights=w)
    best = np.argsort(-masses, kind='stable')[:10]
    modes = [dict(bin=bins[i].tolist(), weight=float(masses[i])) for i in best]
    ready = converged(p) and cov[2, 2] <= math.radians(5)**2
    return np.r_[xy, yaw], cov, dict(resolved=bool(ready), bin_count=len(bins),
        leading_bins=modes, global_std_xy_m=float(np.sqrt(np.trace(cov[:2, :2]))),
        circular_yaw_std_rad=float(np.sqrt(cov[2, 2])), known_own_dock=False)


class Policy:
    def __init__(self):
        self.slow = self.fast = 0.
        self.seen = set()
        self.rows = []
        self.active = True

    def new_view(self, pose):
        return self.active and pose_key(pose) not in self.seen

    def measure(self, pf, prior, ll, pose, moved):
        # Nav2 uses the unnormalised sensor total/N, NOT normalised weights
        # or the max-shifted likelihood (both destroy the recovery signal).
        avg = float(prior @ np.exp(ll)/pf.n)
        self.slow = avg if self.slow == 0 else self.slow+ALPHA_SLOW*(avg-self.slow)
        self.fast = avg if self.fast == 0 else self.fast+ALPHA_FAST*(avg-self.fast)
        diff = max(0., 1-self.fast/self.slow) if self.slow > 0 else 0.
        ess = float(1/np.sum(pf._weights()**2))
        row = dict(w_avg=avg, w_slow=self.slow, w_fast=self.fast, injection_probability=diff,
            ess=ess, resampled=False, injected=0, pose=list(pose_key(pose)))
        if moved:
            self.seen.clear()
        self.seen.add(pose_key(pose))
        # ROS AMCL selective resampling returns BEFORE the recovery draw when
        # ESS>N/2. All hypotheses and weights survive, no arbitrary row quota.
        if ess <= .5*pf.n:
            cdf = np.cumsum(pf._weights()); indices=[]; injected=[]
            for i in range(pf.n):
                random = pf.rng.random() < diff
                injected.append(random)
                indices.append(0 if random else min(int(np.searchsorted(cdf, pf.rng.random(), side='right')), pf.n-1))
            indices=np.array(indices); injected=np.array(injected)
            # Latent motion variables keep ordinary weighted ancestry; an
            # injected pose gets an independent prior latent sample ancestry.
            indices[injected]=pf.rng.integers(pf.n, size=int(injected.sum()))
            for name in ('px','scale','stuck','yaw_bias','yaw_extra','drift'):
                value=getattr(pf,name,None)
                if value is not None:setattr(pf,name,value[indices].copy())
            if injected.any():pf.px[injected]=pf._uniform_free(int(injected.sum()))
            pf.logw=np.zeros(pf.n);pf._inject=0.;pf.stats['resamples']+=1
            row.update(resampled=True,injected=int(injected.sum()))
            if diff>0:self.slow=self.fast=0.
        self.rows.append(row)
        return copy.deepcopy(row)


def sensor_probabilities(rows, sigma_px):
    """Normalised finite camera sensor model for active planning only.

    60 eight-pixel bins plus unknown. Gaussian hit mass outside the image goes
    to unknown; no pretend max-range reading. Existing hit/random .5/.5 and
    existing fixed pixel sigma, not tuned against the replay or truth.
    """
    rows=np.asarray(rows,float);edges=np.arange(0,481,8)
    finite=np.isfinite(rows)
    cdf=ndtr((edges[None,:]-np.where(finite,rows,0.)[:,None])/sigma_px)
    hit=np.maximum(0.,np.diff(cdf,axis=1));hit[~finite]=0.
    hit=np.c_[hit,np.maximum(0.,1-hit.sum(1))]
    return .5*hit+.5/hit.shape[1]


def information_gain(weights, observation_probabilities):
    """I(L;Z)=H(Z)-E_L H(Z|L), equal to Fox equation 13's H(L)-E_Z H(L|Z)."""
    p=np.asarray(observation_probabilities);w=np.asarray(weights)
    marginal=w@p
    return float(np.sum(w[:,None]*p*np.log(np.maximum(p,1e-300)/np.maximum(marginal,1e-300))))


def rank_views(pf, pans=PANS):
    from harness import vision_loc_protocol as vp
    vl=vp.load_vis3()[0];out=[]
    for pan in pans:
        pose={**LOOK_P20,6:pan}
        cm=pf.column_model_for(pose,columns=np.array([320.]))
        bottom,_=vl.expected_rows(pf.geometry,pf.px,cm)
        p=sensor_probabilities(bottom[:,0],float(pf.measurement['sigma_px']))
        out.append(dict(pan=pan,expected_information_nats=information_gain(pf._weights(),p),
            hypothetical=True,actual_observation=False))
    return sorted(out,key=lambda r:(-r['expected_information_nats'],PANS.index(r['pan'])))


class Runtime(Previous):
    def __init__(self,*args,global_localization='off',**kwargs):
        if global_localization not in ('off',OPTION):raise ValueError('unknown global_localization')
        if global_localization!='off' and (kwargs.get('start_localization','off')!='off'
                or kwargs.get('amcl_update')!='ros_motion_v1'):
            raise ValueError('augmented global start requires S2 AMCL and no competing start prior')
        self.global_localization=global_localization
        super().__init__(*args,**kwargs)
        if global_localization=='off':return
        inner=self.pose.provider;pf=inner.loc._pf
        if pf.t!=0 or pf.n!=2000:raise ValueError('untouched 2000-particle provider required')
        pf.px=pf._uniform_free(pf.n);pf.logw=np.zeros(pf.n);pf.initialized=True;pf.last_scan_t=None
        pf.stats['resets']=pf.stats.get('resets',0)+1
        self.global_policy=pf.s2_global_policy=Policy()
        self.amcl_audit=install_global_update(pf,args[0] if args else kwargs['static'],
            preset='ros_motion_v1',visibility=self.visibility,pose_supported=self.visual_pose_supported)
        self.global_actions=[];self.global_scan_started=None;estimate=pf.estimate
        self.global_previous_estimate=estimate
        def report():
            out=estimate();mean,cov,modes=belief_report(pf.px,pf._weights())
            yaw=mean[2]+out.get('pan_yaw_offset',0.)
            out.update(x=float(mean[0]),y=float(mean[1]),yaw=math.atan2(math.sin(yaw),math.cos(yaw)),
                cov=cov.tolist(),std_xy_m=modes['global_std_xy_m'],
                std_yaw_rad=modes['circular_yaw_std_rad'],global_modes=modes)
            return out
        pf.estimate=report
        inner.prior=dict(source='uniform static free space and yaw',known_own_dock=False,option=OPTION)
        inner.runtime_contract['s2_global_localization']=copy.deepcopy(inner.prior)
        inner.identity_sha256=hp.base.digest(inner.runtime_contract)
        inner.source='owncam_pf_s2_augmented_start:'+inner.identity_sha256[:8];self.pose.source=inner.source

    def scan(self, now, after):
        super().scan(now,after)
        if self.global_localization!='off' and self.global_policy.active:
            if self.global_scan_started is None:self.global_scan_started=now
            # One independent view per pan. Do not append the repeated center.
            self.scan_queue=[{**LOOK_P20,6:p} for p in PANS]

    def on_command(self,rid,now,action):
        super().on_command(rid,now,action)
        if (self.global_localization!='off' and self.global_policy.active
                and action['kind'] in ('mecanum','drive')
                and any(action.get(k,0) for k in ('forward','left','turn'))):
            # The recorded initial window includes the settled search posture
            # after the pan sweep. End the global policy at first base motion,
            # not while the camera is still acquiring that final static view.
            self.global_policy.active=False
            pf=self.pose.provider.loc._pf
            del pf.s2_global_policy
            pf.estimate=self.global_previous_estimate

    def _control(self,now,idle):
        if self.global_localization!='off' and self.global_policy.active and idle and self.state=='scan':
            if self.global_scan_started is not None and now-self.global_scan_started>=120:
                self.scan_queue=[]
            if self.scan_queue:
                rank=rank_views(self.pose.provider.loc._pf,[p[6] for p in self.scan_queue])
                selected=rank[0]['pan'];self.scan_queue.sort(key=lambda p:p[6]!=selected)
                self.global_actions.append(dict(t=now,ranking=rank,selected_pan=selected))
            else:
                # DEV uncertainty is log-only. No false resolved/dock claim.
                if not self.pose.provider.loc._pf.estimate()['global_modes']['resolved']:
                    self.soft('GLOBAL_START_UNRESOLVED',now)
        return super()._control(now,idle)

    def record(self):
        out=super().record()
        if self.global_localization!='off':
            out['global_localization']=dict(option=OPTION,known_own_dock=False,gt_inputs=False,
                parameters=dict(alpha_slow=ALPHA_SLOW,alpha_fast=ALPHA_FAST,ess_fraction=.5),
                updates=copy.deepcopy(self.global_policy.rows),actions=copy.deepcopy(self.global_actions),
                admission='offline candidate until registered replay gates pass')
        return out
