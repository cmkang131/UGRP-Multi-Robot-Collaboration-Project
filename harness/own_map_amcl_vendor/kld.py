"""Unmodified PR406 definitions; only imports and Runtime omission differ."""
import copy
import math
from statistics import NormalDist
import numpy as np
from . import augmented as previous


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
