"""Bounded S2 Active Markov sensing. Default off is an identity attachment.

Burgard/Fox/Thrun IJCAI97 §3: maximize H(b)-E_z H(b|z,a).
Only own belief/issued PWM and authored map enter the planner. Predicted
features are hypothetical and NEVER passed to the localization filter.
"""
import copy
import math

import numpy as np

from harness.zone_solo_cyan_active_markov import bins, entropy, expected_posterior_entropy
from harness.zone_solo_cyan_landmarks import MapFeatures, PARAMS as SENSOR, wrap
from harness.zone_solo_cyan_pulse_cal import action_of
from harness.zone_solo_cyan_flow_fusion import compose
from harness.zone_solo_cyan_bias_tempering import closure, replace_cell
from harness.zone_final_pair_binding import bind
from harness.zone_own_guards_v3 import body_spheres
from harness.owncam_sweep_collision import BASE_MARGIN_M, BODY_COVERAGE_RESIDUAL_M, K_SIGMA
from harness.zone_solo_cyan_v106 import ENVELOPE

OPTION = 'discriminating_views_v1'
LIMITS = dict(min_interval_s=20., max_events=5, max_added_fraction=.10,
              angles_deg=[45,-45,90,-90], translations=False, settle_s=.4,
              observation_wait_s=1.5, planning_particles=512)


def representatives(px, weights):
    n=LIMITS['planning_particles'];cdf=np.cumsum(weights);cdf[-1]=1.
    return np.asarray(px)[np.searchsorted(cdf,(np.arange(n)+.5)/n,side='right')].copy()


def actions(profiles, loaded):
    out=[]
    for angle in LIMITS['angles_deg']:
        sign=1 if angle>0 else -1
        key=f'{int(loaded)}:turn:{sign*.35:.2f}:0.10'
        back=f'{int(loaded)}:turn:{-sign*.35:.2f}:0.10'
        p,q=profiles[key],profiles[back]
        # Floor, not round: never exceed the supervisor's angular bound.
        n=max(1,int(abs(math.radians(angle)/p['mean_delta'][2])))
        m=max(1,round(abs(n*p['mean_delta'][2]/q['mean_delta'][2])))
        delta=np.zeros(3);path=[delta.copy()]
        for profile,count in ((p,n),(q,m)):
            for _ in range(count):
                delta=compose(delta,np.array(profile['mean_delta']));path.append(delta.copy())
        cost=n*p['times'][-1]+m*q['times'][-1]+2*(LIMITS['settle_s']+LIMITS['observation_wait_s'])
        out.append(dict(name=f'turn{angle:+d}',key=key,return_key=back,pulses=n,return_pulses=m,
            delta=path[n].tolist(),path=np.array(path).tolist(),added_s=cost,
            command=action_of(p),return_command=action_of(q),horizon_s=p['times'][-1],
            return_horizon_s=q['times'][-1]))
    return out


def map_features(static):
    mapped=MapFeatures(static);result=[]
    # Both incident floor edges exist in the permitted static map. Same hue
    # has the SAME sensor signature across regions (no landmark-ID oracle).
    for e in mapped.edges:
        result.append(dict(kind='floor_crossing',signature=('floor',e['hue']),xy=e['a'].tolist()))
    for d in mapped.doors:
        result.append(dict(kind='door',signature=('door',d['width']),xy=d['center'].tolist()))
    return result


def ray_clear(start,end,static):
    """Vectorized segment/axis-aligned map-wall intersection; endpoints excluded."""
    clear=np.ones(len(start),bool);delta=end-start
    for box in static['obstacles']:
        lo=np.array(box['center_m'])-box['half_extents_m'];hi=np.array(box['center_m'])+box['half_extents_m']
        parallel=abs(delta)<1e-12
        with np.errstate(divide='ignore',invalid='ignore'):
            a=(lo-start)/delta;b=(hi-start)/delta
        low=np.where(parallel,-np.inf,np.minimum(a,b));high=np.where(parallel,np.inf,np.maximum(a,b))
        impossible=np.any(parallel & ((start<lo)|(start>hi)),axis=1)
        entry=np.maximum(low.max(1),1e-6);leave=np.minimum(high.min(1),1.-1e-6)
        clear &= impossible | (entry>leave)
    return clear


def predicted_feature(px,cm,K,static):
    """Nearest visible crossing/door range-bearing-signature, or unknown.

    Optimistic static visibility: own dynamic cargo/other robots can occlude
    it. This ranking proxy cannot certify a detector return in a future RGB.
    """
    features=map_features(static);signatures=sorted(set(q['signature'] for q in features))
    result=np.zeros((len(px),3));result[:,0]=-1;distance=np.full(len(px),np.inf)
    c,s=np.cos(px[:,2]),np.sin(px[:,2])
    for f in features:
        dx,dy=(np.array(f['xy'])-px[:,:2]).T
        xyz=np.c_[c*dx+s*dy,-s*dx+c*dy,np.zeros(len(px))]
        cam=(xyz-cm.origin)@cm._rot;uv=cam@K.T
        with np.errstate(divide='ignore',invalid='ignore'):uv=uv[:,:2]/uv[:,2,None]
        r=np.linalg.norm(xyz[:,:2],axis=1)
        valid=(cam[:,2]>0)&(uv[:,0]>=0)&(uv[:,0]<640)&(uv[:,1]>=0)&(uv[:,1]<480)&(r<SENSOR['max_range_m'])
        valid &= ray_clear(px[:,:2],np.broadcast_to(f['xy'],(len(px),2)),static)
        use=valid&(r<distance);distance[use]=r[use]
        result[use]=np.c_[np.full(len(px),signatures.index(f['signature'])),r,np.arctan2(xyz[:,1],xyz[:,0])][use]
    return result


def observation_probabilities(features):
    """Finite normalized Gaussian hit/random observation experiment.

    Observation support is the equally weighted belief-predicted outcomes;
    repeated hypotheses remain repeated support, not distinct map identities.
    Unknown is one identical outcome. Gaussian noise uses existing constants.
    """
    f=np.asarray(features);same=f[:,0,None]==f[None,:,0]
    dr=(f[:,1,None]-f[None,:,1])/SENSOR['sigma_range_m']
    db=wrap(f[:,2,None]-f[None,:,2])/SENSOR['sigma_bearing_rad']
    hit=same*np.exp(-.5*(dr*dr+db*db))
    unknown=f[:,0]<0;hit[unknown]=same[unknown]
    p=(1-SENSOR['random_fraction'])*hit+SENSOR['random_fraction']/len(f)
    return p/p.sum(1,keepdims=True)


def clearance(static,servo,loaded,report,action):
    """Whole swept-circle enclosure (includes return); existing 2sigma margin.

    This deliberately excludes near-wall rotations instead of overriding a
    veto under dev_light. Unobserved dynamic robots remain a documented limit.
    """
    arm=max(math.hypot(x,y)+r for x,y,z,r in body_spheres(servo,loaded=loaded))
    body=max(math.hypot(x,y) for x in ENVELOPE['x_m'] for y in ENVELOPE['y_m'])
    drift=max(np.linalg.norm(np.array(action['path'])[:,:2],axis=1))
    radius=max(arm,body)+drift+BASE_MARGIN_M+BODY_COVERAGE_RESIDUAL_M+K_SIGMA*report['std_xy_m']
    point=np.array([report['x'],report['y']]);best=math.inf
    for box in [*static['obstacles'],*static.get('terrain',[])]:
        d=np.maximum(abs(point-box['center_m'])-box['half_extents_m'],0.)
        best=min(best,float(np.linalg.norm(d))-radius)
    return best


def rank(px,weights,cm,K,static,servo,loaded,report,profiles):
    sample=representatives(px,weights);n=len(sample);prior=entropy(np.bincount(bins(sample))/n)
    ranked=[]
    for action in [dict(name='stay',delta=[0.,0.,0.],path=[[0.,0.,0.]],added_s=0.),*actions(profiles,loaded)]:
        d=action['delta'];p=sample.copy();c,s=np.cos(p[:,2]),np.sin(p[:,2])
        p[:,0]+=c*d[0]-s*d[1];p[:,1]+=s*d[0]+c*d[1];p[:,2]=wrap(p[:,2]+d[2])
        features=predicted_feature(p,cm,K,static);sensor=observation_probabilities(features)
        # State labels before deterministic action: mutual information cannot
        # be manufactured by moving samples across arbitrary entropy-bin edges.
        after=expected_posterior_entropy(sample,np.full(n,1/n),sensor)
        ranked.append(dict(**action,prior_entropy_nats=prior,expected_posterior_entropy_nats=after,
            expected_reduction_nats=prior-after,visible_fraction=float(np.mean(features[:,0]>=0)),
            clearance_m=clearance(static,servo,loaded,report,action),hypothetical=True))
    return sorted(ranked,key=lambda q:-q['expected_reduction_nats'])


def choose(ranking,elapsed,charged,count):
    stay=next(q for q in ranking if q['name']=='stay')
    candidates=[q for q in ranking if q['name']!='stay' and q['clearance_m']>0 and
        q['expected_reduction_nats']>stay['expected_reduction_nats'] and
        charged+q['added_s'] <= (elapsed-charged)/9. and count<LIMITS['max_events']]
    return candidates[0] if candidates else None


def attach(runtime, *, active_localization='off'):
    if active_localization=='off':return runtime
    if active_localization!=OPTION:raise ValueError('unknown active_localization')
    if hasattr(runtime,'active_observation'):raise ValueError('already attached')
    inner=runtime.pose.provider;pf=inner.loc._pf;wrapper=pf.update_obs
    selected=closure(wrapper).get('selected')
    if selected is None:raise ValueError('landmark AMCL stack required')
    score=selected.__globals__['likelihood'];step=runtime.step;record=runtime.record
    audit=dict(option=OPTION,limits=copy.deepcopy(LIMITS),gt_inputs=False,triggers=[],decisions=[],events=[],added_s=0.)
    state=dict(pending=None,last_attempt=-math.inf,event=None)

    def likelihood(field,px,packet):
        value=score(field,px,packet);w=pf._weights()*value;w/=w.sum();ess=float(1/(w@w))
        row=dict(t=float(pf.t),ess=ess,n=len(w),trigger=ess<len(w)/2)
        audit['triggers'].append(row)
        state['pending']=row if row['trigger'] else None
        return value  # bit-identical filter scores/resampling/random stream
    pf.update_obs=replace_cell(wrapper,'selected',bind(selected,likelihood=likelihood))

    def active_step(now):
        e=state['event']
        if runtime.terminal:return step(now)
        if e is not None:
            dt=now-e['t'];a=e['action'];schedule=e['schedule']
            while schedule and dt>=schedule[0][0]-1e-8:
                _,cmd=schedule.pop(0)
                return [(runtime.robot_id,copy.deepcopy(cmd))]
            if dt < a['added_s']-1e-8:return []
            e['completed_t']=now;audit['added_s']+=dt;state['event']=None;state['pending']=None
            runtime.path=[];runtime.path_goal=None
            runtime.cal_settled_at=now;runtime.cal_until=None
            return [(runtime.robot_id,dict(kind='hold'))]
        if (state['pending'] is None or runtime.state not in ('search_move','carry') or
            now-state['last_attempt']<LIMITS['min_interval_s'] or now<runtime.next_control-1e-8 or
            runtime.arm.until>now or runtime.cal_until is not None or now<runtime.cal_settled_at or
            getattr(runtime,'slip_backup',None) is not None):return step(now)
        state['last_attempt']=now
        from harness import vision_loc_protocol as vp
        K=np.linalg.inv(vp.load_vis3()[0].mp.K_INV);r=runtime.last_report
        report=dict(x=r.x_m,y=r.y_m,std_xy_m=r.std_xy_m)
        ranking=rank(pf.px,pf._weights(),pf.column_model_for(runtime.servo),K,runtime.map,
            runtime.servo,pf.load.loaded,report,runtime.pulse_profiles)
        a=choose(ranking,now-runtime.started_at,audit['added_s'],len(audit['events']))
        audit['decisions'].append(dict(t=now,state=runtime.state,trigger=copy.deepcopy(state['pending']),
            ranking=ranking,selected=None if a is None else a['name']))
        if a is None:return step(now)
        schedule=[];t=0.
        for cmd,count,horizon in ((a['command'],a['pulses'],a['horizon_s']),
                (a['return_command'],a['return_pulses'],a['return_horizon_s'])):
            for _ in range(count):
                schedule.extend([(t,cmd),(t+cmd['duration_s'],dict(kind='hold'))]);t+=horizon
            t+=LIMITS['settle_s']+LIMITS['observation_wait_s']
        e=dict(t=now,action=copy.deepcopy(a),state=runtime.state,schedule=schedule)
        state['event']=e;audit['events'].append(e)
        return active_step(now)
    runtime.step=active_step;runtime.active_observation=audit
    def export():
        out=record();out['active_localization']=copy.deepcopy(audit)
        return out
    runtime.record=export
    return runtime
