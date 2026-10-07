"""S2 start-only Active Markov Localization; default off delegates unchanged.

Fox/Burgard/Thrun 1998 section 4.1: H(b)-E_z H(b'|z), finite motion
actions, zero cost weight as explicitly requested. S2 adapters: 512 systematic
belief representatives, six-point Gaussian motion cubature, existing central
camera-column categorical sensor (8px bins + unknown). No GT inputs.
"""
import copy
import math
import numpy as np

from harness import zone_solo_cyan_kld_start as kld
from harness import zone_solo_cyan_augmented_start as aug
from harness import zone_solo_cyan_v106 as legacy
from harness.zone_solo_cyan_pulse_cal import action_of
from harness.zone_solo_cyan_flow_fusion import compose
from harness.zone_solo_cyan_slip_detect import compose_cov
from harness import zone_pair_highpose_frame_gate as frame_gate

OPTION='active_markov_v1'
PARAMS=dict(sim_cap_s=30.,sigma_xy_m=.10,sigma_yaw_rad=math.pi/36,
    arm_settle_s=2.,motion_settle_s=.4,observation_wait_s=1.5,
    planning_particles=512,belief_bins=[.5,.5,math.pi/18],cost_weight=0.,
    turn_degrees=[45,-45,90,-90,180,-180],side_fine_pulses=10)


def bins(px):
    p=np.array(px,copy=True);p[:,2]=(p[:,2]+math.pi)%(2*math.pi)-math.pi
    return np.unique(np.floor(p/PARAMS['belief_bins']).astype(int),axis=0,return_inverse=True)[1]


def entropy(weights):
    w=np.asarray(weights);return float(-np.sum(w[w>0]*np.log(w[w>0])))


def expected_posterior_entropy(px,weights,sensor):
    """Exact categorical E_z H(L|z) after grouping predicted state bins."""
    ids=bins(px);joint=np.zeros((ids.max()+1,sensor.shape[1]))
    np.add.at(joint,ids,np.asarray(weights)[:,None]*sensor)
    marginal=joint.sum(0)
    return float(-np.sum(joint*np.log(np.maximum(joint,1e-300)/np.maximum(marginal,1e-300))))


def candidates(profiles):
    specs=[]
    for angle in PARAMS['turn_degrees']:
        key=f"0:turn:{.35 if angle>0 else -.35:.2f}:0.10"
        count=max(1,round(abs(math.radians(angle)/profiles[key]['mean_delta'][2])))
        specs.append((f'turn{angle:+d}',key,count))
    for sign in (1,-1):specs.append((f'side{sign:+d}',f'0:left:{sign*.35:.2f}:0.06',PARAMS['side_fine_pulses']))
    result=[]
    for name,key,count in specs:
        p=profiles[key];d=np.array(p['mean_delta']);q=np.diag(p['prediction_variance'])
        mean=np.zeros(3);cov=np.zeros((3,3))
        for _ in range(count):cov,mean=compose_cov(mean,d,cov,q),compose(mean,d)
        result.append(dict(name=name,key=key,pulses=count,delta=mean.tolist(),covariance=cov.tolist(),
            horizon_s=count*p['times'][-1],command=action_of(p),pulse_horizon_s=p['times'][-1]))
    return result


def predicted_samples(px,delta,covariance):
    eig,vec=np.linalg.eigh(covariance);root=vec@np.diag(np.sqrt(np.maximum(eig,0)*3.))
    noise=np.vstack([root.T,-root.T]);d=np.asarray(delta)+noise
    out=np.repeat(px,6,axis=0);body=np.tile(d,(len(px),1));c,s=np.cos(out[:,2]),np.sin(out[:,2])
    out[:,0]+=c*body[:,0]-s*body[:,1];out[:,1]+=s*body[:,0]+c*body[:,1]
    out[:,2]=(out[:,2]+body[:,2]+math.pi)%(2*math.pi)-math.pi
    return out


def rank_actions(pf,servo,actions):
    from harness import vision_loc_protocol as vp
    n=PARAMS['planning_particles'];cdf=np.cumsum(pf._weights());cdf[-1]=1.
    idx=np.searchsorted(cdf,(np.arange(n)+.5)/n,side='right');sample=pf.px[idx]
    prior_entropy=entropy(np.bincount(bins(sample))/n)
    cm=pf.column_model_for(servo,columns=np.array([320.]));vl=vp.load_vis3()[0];ranked=[]
    for action in actions:
        predicted=predicted_samples(sample,action['delta'],action['covariance'])
        bottom,_=vl.expected_rows(pf.geometry,predicted,cm)
        prob=aug.sensor_probabilities(bottom[:,0],float(pf.measurement['sigma_px']))
        after=expected_posterior_entropy(predicted,np.full(len(predicted),1/len(predicted)),prob)
        ranked.append(dict(**copy.deepcopy(action),prior_entropy_nats=prior_entropy,
            expected_posterior_entropy_nats=after,expected_reduction_nats=prior_entropy-after,
            predicted_collision_mass=float(np.mean(pf._map_logprior(predicted)<0)),hypothetical=True))
    return sorted(ranked,key=lambda r:-r['expected_reduction_nats'])


class Runtime(kld.Runtime):
    def __init__(self,*args,start_localization='off',**kwargs):
        if start_localization not in ('off',OPTION):raise ValueError('unknown active start option')
        if start_localization==OPTION and (kwargs.get('particle_sampling')!=kld.OPTION or
                kwargs.get('global_localization')!=aug.OPTION or kwargs.get('pulse_motion_model')!='v7_pulse_cal_v1'):
            raise ValueError('active Markov start requires KLD, augmented MCL and calibrated pulses')
        self.active_markov_option=start_localization
        super().__init__(*args,start_localization='off',**kwargs)
        if start_localization=='off':return
        self.active_audit=dict(option=OPTION,parameters=copy.deepcopy(PARAMS),decisions=[],
            observations=[],reason=None,gt_inputs=False,known_own_dock=False,start_only=True)
        self.active_phase='setup';self.active_queue=[];self.active_next=0.;self.observe_after=None
        self.active_actions=candidates(self.pulse_profiles)
        inner=self.pose.provider;inner.runtime_contract['s2_active_markov']=copy.deepcopy(self.active_audit)
        inner.identity_sha256=legacy.hp.base.digest(inner.runtime_contract)
        inner.source='owncam_pf_s2_active_markov:'+inner.identity_sha256[:8];self.pose.source=inner.source

    def on_command(self,rid,now,action):
        if self.active_markov_option=='off':return super().on_command(rid,now,action)
        # Keep the global KLD belief active during these localization motions;
        # the old first-base-motion handoff belongs to normal S2 navigation.
        return legacy.Runtime.on_command(self,rid,now,action)

    def on_frames(self,now,frames):
        if self.active_markov_option=='off':return super().on_frames(now,frames)
        obs,rgb=frames[self.robot_id];verdict,_=frame_gate.gate().assess(obs,self.robot_id,now,ob=False)
        ready=self.active_phase=='observe' and now>=self.observe_after
        before=self.amcl_audit['updates']
        rep=self.last_report=self.pose.on_frame(now,rgb if ready and verdict==frame_gate.VALID else None)
        self.pose_log.append(dict(t=now,t_est=rep.t_est,x=rep.x_m,y=rep.y_m,yaw=rep.yaw_rad,
            std_xy_m=rep.std_xy_m,std_yaw_rad=rep.std_yaw_rad,last_fix_t=rep.last_fix_t))
        if self.amcl_audit['updates']>before:
            self.active_audit['observations'].append(dict(t=now,measurement_t=self.amcl_audit['rows'][-1]['t']))

    def step(self,now):
        if self.active_markov_option=='off':return super().step(now)
        rid=self.robot_id;pf=self.pose.provider.loc._pf
        if self.terminal:return [(rid,dict(kind='hold'))]
        if now-self.started_at>=PARAMS['sim_cap_s']-1e-8:
            self.active_audit['reason']='TIME_CAP';self.set_state('done',now)
            return [(rid,dict(kind='hold'))]
        if self.active_phase=='setup':
            self.active_phase='observe';self.observe_after=now+PARAMS['arm_settle_s']
            self.global_policy.seen.clear();self.set_state('active_start',now)
            return [(rid,dict(kind='arm',servo_id=k,pulse=v)) if k!=6 else
                    (rid,dict(kind='look',pan_pulse=v)) for k,v in {**legacy.LOOK_P20,6:1500}.items()]
        if self.active_phase=='moving':
            if now<self.active_next-1e-8:return []
            if self.active_queue:
                p=self.active_queue.pop(0);self.active_next=now+p['pulse_horizon_s']
                self.active_audit['decisions'][-1]['issued_pulses']+=1
                return [(rid,copy.deepcopy(p['command']))]
            self.active_audit['decisions'][-1].update(completed=True,completed_t=now)
            self.active_phase='observe';self.observe_after=now+PARAMS['motion_settle_s']
            self.global_policy.seen.clear()  # one forced new settled view at this action endpoint
            return [(rid,dict(kind='hold'))]
        if now<self.observe_after-1e-8:return []
        fresh=pf.last_scan_t is not None and pf.last_scan_t>=self.observe_after-1e-8
        if not fresh and now<self.observe_after+PARAMS['observation_wait_s']:return []
        if not fresh:self.soft('ACTIVE_OBSERVATION_UNKNOWN',now)
        estimate=pf.estimate()
        if fresh and estimate['std_xy_m']<=PARAMS['sigma_xy_m'] and estimate['std_yaw_rad']<=PARAMS['sigma_yaw_rad']:
            self.active_audit['reason']='SIGMA_REACHED';self.set_state('done',now)
            return [(rid,dict(kind='hold'))]
        remaining=PARAMS['sim_cap_s']-(now-self.started_at)
        available=[a for a in self.active_actions if a['horizon_s']+PARAMS['motion_settle_s']+.25<=remaining]
        if not available:return []
        ranking=rank_actions(pf,self.servo,available);selected=ranking[0]
        self.active_audit['decisions'].append(dict(t=now,ranking=ranking,selected=selected['name'],issued_pulses=0,completed=False))
        if selected['predicted_collision_mass']>0:self.soft('ACTIVE_PREDICTED_COLLISION',now)
        self.active_queue=[selected]*selected['pulses'];self.active_phase='moving';self.active_next=now
        return self.step(now)

    def record(self):
        out=super().record()
        if self.active_markov_option!='off':out['active_markov']=copy.deepcopy(self.active_audit)
        return out
