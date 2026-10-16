"""Ulrich & Nourbakhsh AAAI 2000, section 4 (single-frame basic variant).

Appearance-based obstacle contacts, NOT a semantic wall classifier. Own undistorted
RGB and fixed command-indexed calibration only. The wall-only evaluation gate must
pass before enabling this input in mapping. No training, GT, peer map or simulator.
Algorithm/provenance and all engineering constants:
experiments/2026-10-07-wall-floor-boundary/REFERENCES.md
"""
from __future__ import annotations
from functools import lru_cache

import cv2
import numpy as np

CONFIG = dict(gaussian_kernel=5, histogram_bins=256, histogram_window=5,
              hue_count_threshold=60, intensity_count_threshold=80,
              min_intensity=10/255, min_saturation=.1,
              reference_forward_m=(.30, 1.00), reference_half_width_m=.30,
              minimum_reference_pixels=1024, max_range_m=4.)


def hsi(bgr):
    """HSI hue in [0,1), saturation in [0,1], I=(R+G+B)/3 (not HSV V)."""
    b, g, r = np.moveaxis(np.asarray(bgr, float)/255., -1, 0)
    intensity = (r+g+b)/3
    saturation = 1-np.minimum(np.minimum(r,g),b)/np.maximum(intensity,1e-12)
    hue = np.mod(np.arctan2(np.sqrt(3.)*(g-b),2*r-g-b),2*np.pi)/(2*np.pi)
    valid_hue = (intensity > CONFIG['min_intensity']) & (saturation > CONFIG['min_saturation'])
    return hue, saturation, intensity, valid_hue


def histograms(hue, intensity, valid_hue, reference):
    bins, win = CONFIG['histogram_bins'], CONFIG['histogram_window']
    h = np.minimum((hue*bins).astype(int),bins-1)
    i = np.minimum((intensity*bins).astype(int),bins-1)
    hh = np.bincount(h[reference & valid_hue],minlength=bins).astype(float)
    ih = np.bincount(i[reference],minlength=bins).astype(float)
    # Hue is circular; intensity is bounded. These edge conventions are explicit.
    kernel = np.ones(win)/win
    hh = np.convolve(np.pad(hh,(win//2,win//2),mode='wrap'),kernel,mode='valid')
    ih = np.convolve(np.pad(ih,(win//2,win//2),mode='constant'),kernel,mode='valid')
    return hh, ih, h, i


@lru_cache(maxsize=32)
def _plane(shape, origin_tuple, rotation_tuple, intrinsic_tuple):
    """Cached calibration-only floor-plane support, independent of RGB/scene."""
    origin = np.asarray(origin_tuple)
    rotation, intrinsic = np.array(rotation_tuple).reshape(3,3), np.array(intrinsic_tuple).reshape(3,3)
    v,u = np.indices(shape)
    rays = np.stack((u,v,np.ones(shape)),axis=-1) @ np.linalg.inv(intrinsic).T @ rotation.T
    with np.errstate(divide='ignore',invalid='ignore'):
        ray_t = -origin[2]/rays[...,2]
        xyz = origin+rays*ray_t[...,None]
    optical_z = ((xyz-origin)@rotation)[...,2]
    valid = np.isfinite(xyz).all(axis=-1) & (ray_t>0) & (optical_z>0)
    ranges = np.linalg.norm(xyz[...,:2]-origin[:2],axis=-1)
    lo,hi = CONFIG['reference_forward_m']
    reference = valid & (xyz[...,0]>=lo) & (xyz[...,0]<=hi) & (abs(xyz[...,1])<=CONFIG['reference_half_width_m'])
    for a in (xyz, ranges, valid, reference):
        a.setflags(write=False)
    return xyz, ranges, valid, reference


def detect(und_bgr, *, camera_origin, camera_rotation, intrinsic, columns, valid_image=None):
    """Run the selected basic algorithm, then lowest obstacle contact per column.

    valid_image can supply the fixed undistortion support (not a semantic GT mask).
    A 2 px Gaussian support erodes invalid borders; black objects remain valid.
    A lowest obstacle cut by the image/valid-mask border has no observed footpoint
    and abstains. We do not search above it for a more convenient candidate.
    """
    image = np.asarray(und_bgr)
    if image.ndim!=3 or image.shape[2]!=3 or image.dtype!=np.uint8:
        raise ValueError('expected undistorted uint8 BGR')
    origin, rotation, intrinsic = map(lambda a:np.asarray(a,float),(camera_origin,camera_rotation,intrinsic))
    if origin.shape!=(3,) or rotation.shape!=(3,3) or intrinsic.shape!=(3,3):
        raise ValueError('invalid fixed camera calibration shape')
    if not all(np.isfinite(a).all() for a in (origin,rotation,intrinsic)) or origin[2]<=0:
        raise ValueError('invalid fixed camera calibration')
    columns = np.asarray(columns,int)
    if columns.ndim!=1 or np.any(columns<0) or np.any(columns>=image.shape[1]):
        raise ValueError('invalid image columns')
    xyz,ranges,positive,reference = _plane(image.shape[:2],tuple(origin),tuple(rotation.ravel()),tuple(intrinsic.ravel()))
    support = np.ones(image.shape[:2],bool) if valid_image is None else np.asarray(valid_image,bool)
    if support.shape!=image.shape[:2]:
        raise ValueError('invalid image support shape')
    support = cv2.erode(support.astype(np.uint8),np.ones((5,5),np.uint8),
                        borderType=cv2.BORDER_CONSTANT,borderValue=0).astype(bool)
    reference = reference & support
    result = dict(uv=np.empty((0,2)),xy=np.empty((0,2)),ranges=np.empty(0),column_ids=np.empty(0,int),
                  obstacle=np.zeros(image.shape[:2],bool),reference=reference,
                  reference_pixels=int(reference.sum()),reason='insufficient_reference',
                  border_censored_columns=0, behind_camera_rejected=0, beyond_range_rejected=0)
    if reference.sum()<CONFIG['minimum_reference_pixels']:
        return result
    filtered = cv2.GaussianBlur(image,(5,5),0)
    hue,_,intensity,valid_hue = hsi(filtered)
    hh,ih,h,i = histograms(hue,intensity,valid_hue,reference)
    obstacle = ((valid_hue & (hh[h]<CONFIG['hue_count_threshold'])) |
                (ih[i]<CONFIG['intensity_count_threshold'])) & support
    result.update(obstacle=obstacle,reason='classified')
    ids,uv = [],[]
    for j,u in enumerate(columns):
        occupied = np.flatnonzero(obstacle[:,u])
        if not len(occupied):
            continue
        v = int(occupied[-1])
        # Footpoint visibility (no invented contact where an obstacle exits image).
        if v+1>=image.shape[0] or not support[v+1,u]:
            result['border_censored_columns']+=1
            continue
        if not positive[v,u]:
            result['behind_camera_rejected']+=1
            continue
        if ranges[v,u]>CONFIG['max_range_m']:
            result['beyond_range_rejected']+=1
            continue
        ids.append(j)
        uv.append((u,v))
    if ids:
        uv = np.array(uv,int)
        result.update(column_ids=np.array(ids,int),uv=uv.astype(float),xy=xyz[uv[:,1],uv[:,0],:2].copy(),
                      ranges=ranges[uv[:,1],uv[:,0]].copy())
    return result


def to_scan(result, und_bgr, cm, candidates=3):
    """Existing contact/segment ABI; appearance boundary does not infer wall height."""
    scan={key:np.full((len(cm.columns),candidates),np.nan) for key in ('vb','vt','h','h_lb','c','s','r','b')}
    grey=cv2.cvtColor(und_bgr,cv2.COLOR_BGR2GRAY).astype(float)
    for j,(u,v),xy,r in zip(result['column_ids'],result['uv'],result['xy'],result['ranges']):
        u,v=int(u),int(v)
        above=grey[max(0,v-3):v+1,u]
        below=grey[v+1:min(len(grey),v+5),u]
        scan['vb'][j,0]=v
        scan['c'][j,0]=abs(float(above.mean()-below.mean())) if len(below) else 0.
        scan['s'][j,0]=float(above.std())
        scan['r'][j,0]=r
        delta=xy-cm.origin[:2]
        scan['b'][j,0]=np.arctan2(delta[1],delta[0])
    return scan
