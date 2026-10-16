"""Unmodified S2 constants/moments; PR406 2fa4bf9a, see provenance.json."""
import math
import numpy as np

TEMPER = 'pr_likelihood_half_v1'


ALPHA = .5


def moments(px,w):
    """Overall covariance reported by Nav2 best-cluster adapter, pre delay."""
    center=w@px[:,:2];delta=px[:,:2]-center
    yaw=math.atan2(w@np.sin(px[:,2]),w@np.cos(px[:,2]))
    cov=np.zeros((3,3));cov[:2,:2]=(delta*w[:,None]).T@delta
    cov[2,2]=max(0.,-2*math.log(max(math.hypot(w@np.sin(px[:,2]),w@np.cos(px[:,2])),1e-300)))
    return dict(mean=[*center.tolist(),yaw],cov=cov.tolist(),ess=float(1/(w@w)),
        xy_trace=float(np.trace(cov[:2,:2])),unique_poses=len(np.unique(px[:,:3],axis=0)))
