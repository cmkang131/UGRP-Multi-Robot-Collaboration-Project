# Player - One Hell of a Robot Server
# Copyright (C) 2000 Brian Gerkey & Kasper Stoy
# Copyright (c) 2000-2003, Andrew Howard
# LGPL-2.1-or-later. This modified Python translation is provided without
# warranty. Original C/C++ and the license are shipped in upstream/ and COPYING.LIB.
"""Line-order NumPy ports. Formula references and differences: NOTICE.md."""
import math
import numpy as np


def wrap(x):
    return np.arctan2(np.sin(x), np.cos(x))


def motion(particles, delta, alphas, rng):
    """Nav2 DifferentialMotionModel::odometryUpdate, local old_pose=(0,0,0).

    Implements sample_motion_odometry (Prob Rob p136). The upstream .01m
    bearing singularity guard is retained, including its small-motion behavior.
    """
    a1, a2, a3, a4 = alphas
    trans = float(np.hypot(delta[0], delta[1]))
    rot1 = 0. if trans < .01 else math.atan2(delta[1], delta[0])
    rot2 = float(wrap(delta[2] - rot1))
    n1 = min(abs(float(wrap(rot1))), abs(float(wrap(rot1-math.pi))))
    n2 = min(abs(float(wrap(rot2))), abs(float(wrap(rot2-math.pi))))
    # Draw triples in particle order, matching the C++ loop's three draws.
    draws = rng.normal(size=(len(particles), 3))
    r1 = wrap(rot1 - draws[:, 0]*math.sqrt(a1*n1*n1+a2*trans*trans))
    tr = trans - draws[:, 1]*math.sqrt(a3*trans*trans+a4*(n1*n1+n2*n2))
    r2 = wrap(rot2 - draws[:, 2]*math.sqrt(a1*n2*n2+a2*trans*trans))
    yaw = particles[:, 2]+r1
    particles[:, 0] += tr*np.cos(yaw)
    particles[:, 1] += tr*np.sin(yaw)
    particles[:, 2] = wrap(particles[:, 2]+r1+r2)


def likelihood(field, poses, points, sigma_hit, max_beams=60, range_max=100.):
    """likelihood_field_model.cpp sensorFunction: p=1; p+=pz^3.

    points are ALREADY projected endpoints in chassis axes; no extra laser
    transform. max_beams=60, z_hit=z_rand=.5. Historical callers retain100m;
    Nav2 AmclNode lines725-730 actually uses min(sensor.range_max,100m).
    The explicit RGB adapter supplies its existing4m sensor guard, not a fit.
    Missing RGB returns do not appear in points and cannot become max-range.
    """
    points = np.asarray(points, float).reshape(-1, 2)
    if not len(points):
        return np.ones(len(poses))
    step = max(1, (len(points)-1)//(max_beams-1))
    points = points[::step]
    points = points[np.isfinite(points).all(axis=1)]  # upstream skips NaN AFTER stride
    result = np.empty(len(poses))
    # Chunk is a memory bound only, never a candidate/work truncation.
    for begin in range(0, len(poses), 2048):
        p = poses[begin:begin+2048]
        c, s = np.cos(p[:, 2, None]), np.sin(p[:, 2, None])
        x = p[:, 0, None]+c*points[None, :, 0]-s*points[None, :, 1]
        y = p[:, 1, None]+s*points[None, :, 0]+c*points[None, :, 1]
        z = field.distances(np.stack((x, y), axis=-1))
        pz = .5*np.exp(-z*z/(2*sigma_hit*sigma_hit))+.5/range_max
        result[begin:begin+len(p)] = 1.+np.sum(pz*pz*pz, axis=1)
    return result


def sample_limit(k, minimum=2000, maximum=100000, error=.05, z=.99):
    """pf.c pf_resample_limit, including pop_z interpreted AS supplied.

    Nav2 default pf_z=.99 is passed directly, not invPhi(.99). Thus this is
    upstream numerical parity, NOT a claim of a calibrated 99% posterior.
    """
    if k <= 1:
        return maximum
    x = 1.-2./(9*(k-1))+math.sqrt(2./(9*(k-1)))*z
    return min(maximum, max(minimum, math.ceil((k-1)/(2*error)*x*x*x)))


def resample(poses, weights, rng, uniform_free, injection, minimum=2000, maximum=100000):
    """pf.c multinomial + occupied bins + strict sample_count>limit exit.

    pf_kdtree.c bin widths .5m/.5m/10deg retained; these bins control compute
    only and are NOT convergence or single-mode acceptance thresholds.
    """
    cdf = np.cumsum(weights); cdf[-1] = 1.
    bins = np.array([.5, .5, math.pi/18])
    # Batch draws preserve particle order and bound work by maximum samples.
    draws = rng.random((maximum, 2))
    ids = np.searchsorted(cdf, draws[:, 1], side='right')
    selected = poses[ids].copy()
    injected = draws[:, 0] < injection
    if injected.any():
        selected[injected] = uniform_free(int(injected.sum()))
    occupied = set(); limit = maximum; count = 0
    keys = np.floor(selected/bins).astype(int)
    for key in keys:
        count += 1
        key = tuple(key)
        if key not in occupied:
            occupied.add(key); limit = sample_limit(len(occupied), minimum, maximum)
        if count > limit:
            break
    return selected[:count], dict(samples=count, occupied_bins=len(occupied),
        kld_limit=limit, capped=count==maximum, injected=int(injected[:count].sum()))


def likelihood_product(field, poses, points, sigma_hit, max_beams=60):
    """Nav2 LikelihoodFieldModelProb::sensorFunction, do_beamskip=false.

    Textbook likelihood-field beam product; upstream ceil(range_count/max_beams)
    stride, log_p+=log(pz), weight*=exp(log_p) are retained. Unlike the default
    cubic sum, this model assumes independent beams; RGB correlation remains
    an explicit qualification risk, not a fitted confidence claim.
    """
    points=np.asarray(points,float).reshape(-1,2)
    if not len(points):return np.ones(len(poses))
    points=points[::max(1,math.ceil(len(points)/max_beams))]
    points=points[np.isfinite(points).all(axis=1)]  # keep original beam slots until stride
    out=np.empty(len(poses))
    for begin in range(0,len(poses),2048):
        p=poses[begin:begin+2048];c,s=np.cos(p[:,2,None]),np.sin(p[:,2,None])
        x=p[:,0,None]+c*points[None,:,0]-s*points[None,:,1]
        y=p[:,1,None]+s*points[None,:,0]+c*points[None,:,1]
        z=field.distances(np.stack((x,y),axis=-1))
        pz=.5*np.exp(-z*z/(2*sigma_hit*sigma_hit))+.5/100.
        out[begin:begin+len(p)]=np.exp(np.sum(np.log(pz),axis=1))
    return out
