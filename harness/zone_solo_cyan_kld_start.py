"""Default-off S2 global KLD particle budget; no truth or dock prior.

Fox, NIPS 2001 eq.7; Nav2 235fc5ce pf_init_model/pf_resample_limit/
pf_update_resample (LGPL-2.1+ algorithm port). Existing RGB likelihood and
selective-resampling trigger remain unchanged. Global init uses max_samples;
subsequent multinomial draws stop using occupied 0.5m/0.5m/10deg bins.
"""
import copy
import math
from statistics import NormalDist

import numpy as np

from harness import zone_solo_cyan_augmented_start as previous

OPTION = 'kld_global_v1'
PARAMS = dict(min_samples=2000,max_samples=100000,epsilon=.05,confidence=.99,
              bins=[.5,.5,math.pi/18])
LATENTS = ('scale','stuck','yaw_bias','yaw_extra','drift')


def sample_limit(k, parameters=PARAMS):
    if k <= 1:
        return parameters['max_samples']
    z=NormalDist().inv_cdf(parameters['confidence'])
    x=1.-2./(9*(k-1))+math.sqrt(2./(9*(k-1)))*z
    n=math.ceil((k-1)/(2*parameters['epsilon'])*x**3)
    return min(parameters['max_samples'],max(parameters['min_samples'],n))


def assign(pf, indices, poses=None):
    old_n=pf.n
    for key in ('px',)+LATENTS:
        value=getattr(pf,key,None)
        if value is not None:
            if not isinstance(value,np.ndarray) or value.shape[0]!=old_n:
                raise ValueError('unexpected per-particle state: '+key)
            setattr(pf,key,value[indices].copy())
    if poses is not None:pf.px=np.array(poses,copy=True)
    pf.n=len(indices);pf.logw=np.zeros(pf.n);pf._inject=0.


def resample(pf, injection=0., parameters=PARAMS):
    """Nav2's multinomial draw, occupied-bin count and strict > stop rule."""
    cdf=np.cumsum(pf._weights());cdf[-1]=1.
    occupied=set();indices=[];poses=[];injected=0;limit=parameters['max_samples']
    for _ in range(parameters['max_samples']):
        random=pf.rng.random()<injection
        i=(int(pf.rng.integers(pf.n)) if random else
           min(int(np.searchsorted(cdf,pf.rng.random(),side='right')),pf.n-1))
        p=pf._uniform_free(1)[0] if random else pf.px[i]
        indices.append(i);poses.append(p);injected+=int(random)
        key=tuple(np.floor(p/parameters['bins']).astype(int))
        if key not in occupied:
            occupied.add(key);limit=sample_limit(len(occupied),parameters)
        if len(indices)>limit:break
    assign(pf,np.asarray(indices),poses);pf.stats['resamples']+=1
    return dict(samples=pf.n,occupied_bins=len(occupied),limit=limit,
                capped=pf.n==parameters['max_samples'],injected=injected)


class Policy(previous.Policy):
    def measure(self,pf,prior,ll,pose,moved):
        # Same augmented recovery EMA and ESS trigger as the existing policy.
        avg=float(prior@np.exp(ll)/pf.n)
        self.slow=avg if self.slow==0 else self.slow+previous.ALPHA_SLOW*(avg-self.slow)
        self.fast=avg if self.fast==0 else self.fast+previous.ALPHA_FAST*(avg-self.fast)
        diff=max(0.,1-self.fast/self.slow) if self.slow>0 else 0.
        ess=float(1/np.sum(pf._weights()**2))
        row=dict(w_avg=avg,w_slow=self.slow,w_fast=self.fast,injection_probability=diff,
                 ess=ess,resampled=False,injected=0,pose=list(previous.pose_key(pose)),
                 samples_before=pf.n)
        if moved:self.seen.clear()
        self.seen.add(previous.pose_key(pose))
        if ess<=.5*pf.n:
            row.update(resample(pf,diff),resampled=True)
            if diff>0:self.slow=self.fast=0.
        row['samples_after']=pf.n;self.rows.append(row)
        return copy.deepcopy(row)


class Runtime(previous.Runtime):
    def __init__(self,*args,particle_sampling='off',**kwargs):
        if particle_sampling not in ('off',OPTION):raise ValueError('unknown particle_sampling')
        if particle_sampling!='off' and kwargs.get('global_localization')!=previous.OPTION:
            raise ValueError('KLD requires augmented global S2 localization')
        self.particle_sampling=particle_sampling
        super().__init__(*args,**kwargs)
        if particle_sampling=='off':return
        pf=self.pose.provider.loc._pf
        # Nav2 pf_init_model uses max_samples even before the first sensor read.
        # Fresh poses are map-uniform, never drawn around the stored estimate.
        poses=pf._uniform_free(PARAMS['max_samples'])
        indices=pf.rng.integers(pf.n,size=len(poses))
        assign(pf,indices,poses)
        self.global_policy=pf.s2_global_policy=Policy()
        self.kld_audit=dict(option=OPTION,parameters=copy.deepcopy(PARAMS),initial_samples=pf.n,
            initial_source='uniform static free space and yaw',gt_inputs=False,known_own_dock=False,
            latent_initialization='independent resampling of existing prior latent states',
            sampling_scope='global only; weighted 2000-particle handoff on first base motion',handoff=None)
        inner=self.pose.provider
        inner.runtime_contract['s2_particle_sampling']=copy.deepcopy(self.kld_audit)
        inner.identity_sha256=previous.hp.base.digest(inner.runtime_contract)
        inner.source='owncam_pf_s2_kld_start:'+inner.identity_sha256[:8];self.pose.source=inner.source

    def on_command(self,rid,now,action):
        if (self.particle_sampling!='off' and self.global_policy.active and
                action['kind'] in ('mecanum','drive') and
                any(action.get(k,0) for k in ('forward','left','turn'))):
            pf=self.pose.provider.loc._pf;old_n=pf.n
            indices=pf.rng.choice(pf.n,size=PARAMS['min_samples'],p=pf._weights())
            assign(pf,indices)
            self.kld_audit['handoff']=dict(t=now,before=old_n,after=pf.n)
        return super().on_command(rid,now,action)

    def record(self):
        out=super().record()
        if self.particle_sampling!='off':
            out['particle_sampling']={**copy.deepcopy(self.kld_audit),
                                      'updates':copy.deepcopy(self.global_policy.rows)}
        return out
