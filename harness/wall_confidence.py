"""Tempered inverse range sensor model; own detection/command covariance only.

Thrun Ch9 Table9.2 and Elfes 1989 justify hit/free log-odds accumulation.
The fixed factors here are our sensor model, NOT a fitted correctness probability.
See experiment README §23.2 for derivation, limitations and calibration curves.
"""
import math
import numpy as np
from harness.self_odom_grid import ray_cells

VALUES = ('off', 'inverse_sensor_v1')


def confidence(segment, camera, features, covariance, yaw=0., resolution=.1):
    ends, camera = np.asarray(segment, float), np.asarray(camera, float)
    cov = np.asarray(covariance, float)
    values = [features[k] for k in ('height_m','fy','contrast','band_std','sharpness','body_settling')]
    if (ends.shape != (2,2) or camera.shape != (2,) or cov.shape != (3,3) or
            not np.isfinite(np.r_[ends.ravel(),camera,cov.ravel(),values]).all() or
            min(values[:2]) <= 0 or min(values[2:]) < 0 or values[-1] > 1 or
            not np.allclose(cov,cov.T,atol=1e-10) or np.linalg.eigvalsh(cov).min() < -1e-10):
        raise ValueError('INVALID_WALL_CONFIDENCE_INPUT')
    h,fy,contrast,std,gradient,settling = values
    mid = ends.mean(0)
    direction, view = ends[1]-ends[0],mid-camera
    length, r = np.linalg.norm(direction),np.linalg.norm(view)
    cross = direction[0]*view[1]-direction[1]*view[0]
    incidence = float(cross**2/(length*r)**2) if length*r > 1e-12 else 0.
    sigma_r = (r*r+h*h)/(h*fy)  # 1 px contact uncertainty propagated to ground
    c,s = math.cos(yaw),math.sin(yaw)
    rotated = mid@np.array([[c,s],[-s,c]])
    J = np.array([[1.,0.,-rotated[1]],[0.,1.,rotated[0]]])
    pose_variance = max(0.,float(np.trace(J@cov@J.T)/2))
    factors = {'range':resolution**2/(resolution**2+sigma_r**2),
               'incidence':min(1.,incidence),
               'contrast':contrast**2/(contrast**2+std**2+36.),
               'sharpness':gradient**2/(gradient**2+std**2+36.),
               'pose':resolution**2/(resolution**2+pose_variance),
               'settling':settling}
    return {'weight':float(math.prod(factors.values())), 'factors':factors,
            'range_m':float(r),'sigma_range_m':float(sigma_r),'pose_variance_m2':pose_variance}


def weighted_insert(grid, camera, segments, weights):
    """One strongest hit/miss per cell/frame; hit wins; both signs tempered."""
    if len(segments) != len(weights) or any(not math.isfinite(w) or not 0 <= w <= 1 for w in weights):
        raise ValueError('INVALID_WALL_CONFIDENCE_WEIGHTS')
    occupied,free = {},{}
    for (a,b),weight in zip(segments,weights):
        if weight == 0:
            continue
        a,b = np.asarray(a),np.asarray(b)
        n = max(2,int(math.ceil(np.linalg.norm(b-a)/(grid.resolution_m/2)))+1)
        for point in np.linspace(a,b,n):
            cells = ray_cells(camera,point,grid.resolution_m)
            occupied[cells[-1]] = max(occupied.get(cells[-1],0.),weight)
            for cell in cells[:-1]:
                free[cell] = max(free.get(cell,0.),weight)
    for evidence,increment in (({k:v for k,v in free.items() if k not in occupied},grid.miss),(occupied,grid.hit)):
        for cell,weight in evidence.items():
            grid.cells[cell] = min(grid.hi,max(grid.lo,grid.cells.get(cell,0.)+weight*increment))
    grid.frames += 1
