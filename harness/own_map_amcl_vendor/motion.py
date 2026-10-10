"""Unmodified PR406 definitions; only imports and Runtime omission differ."""
import math
import numpy as np
from .field import PARAMS


BEAM=dict(distance=.5,threshold=.3,error_threshold=.9,converged_distance=.5)


def moved(delta):
    return (np.any(abs(delta[:2])>PARAMS['update_min_d_m']) or
            abs(math.atan2(math.sin(delta[2]),math.cos(delta[2])))>PARAMS['update_min_a_rad'])


def converged(px):
    return bool(np.all(abs(px[:,:2]-px[:,:2].mean(0))<=BEAM['converged_distance']))


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
