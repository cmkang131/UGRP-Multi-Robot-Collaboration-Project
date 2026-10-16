"""Issued-motion covariance, shared with own-map CSM; no measured state."""
import math
import numpy as np


def propagate(covariance, before_yaw, delta_world, velocity, dt, profile, *, loaded_floor=0.):
    # Same 50 ms velocity/1 s correlated scale model as UncertainCommandOdometry.
    dx,dy=delta_world
    F=np.eye(3);F[:2,2]=[-dy,dx]
    c,s=math.cos(before_yaw),math.sin(before_yaw)
    R=np.array([[c,-s,0.],[s,c,0.],[0.,0.,1.]])
    velocity=np.abs(velocity)
    std=np.asarray(profile.get('noise_rel',[0.,0.,0.]))*velocity+profile.get('noise_abs',[0.,0.,0.])
    variance=(std*dt)**2+(profile.get('scale_std',0.)*velocity)**2*dt
    variance[:2]+=loaded_floor**2*dt
    return F@np.asarray(covariance)@F.T+R@np.diag(variance)@R.T
