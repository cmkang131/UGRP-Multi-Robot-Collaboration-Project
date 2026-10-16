"""Scale freezing and post-save trajectory scoring, separate from SLAM.

`scale` never reads truth. `score` accepts saved camera-centre XYZ for every
input frame. No interpolation, no zero-motion replacement, no quality cutoff.
Rigid/Sim(3) least squares follows Umeyama (IEEE PAMI 1991).
"""
from __future__ import annotations
import argparse
import hashlib
import json
from pathlib import Path

import cv2
import numpy as np


def digest(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def align(x,y,fit_scale):
    x,y=np.asarray(x,float),np.asarray(y,float)
    if x.shape != y.shape or x.ndim!=2 or len(x)<3:
        raise ValueError('alignment_requires_3_corresponding_points')
    xc,yc=x-x.mean(0),y-y.mean(0)
    var=np.sum(xc*xc)
    if var==0:
        raise ValueError('zero_estimated_translation_variance')
    u,s,vt=np.linalg.svd(yc.T@xc)
    signs=np.ones(x.shape[1]); signs[-1]=np.linalg.det(u@vt)
    r=(u*signs)@vt
    scale=float(np.sum(s*signs)/var) if fit_scale else 1.
    t=y.mean(0)-scale*(r@x.mean(0))
    errors=np.linalg.norm(scale*x@r.T+t-y,axis=1)
    return dict(rmse_m=float(np.sqrt(np.mean(errors**2))),median_m=float(np.median(errors)),
        p95_m=float(np.percentile(errors,95)),max_m=float(errors.max()),
        alignment_scale=scale,rotation=r.tolist(),translation=t.tolist(),
        estimated_translation_rank=int(np.linalg.matrix_rank(xc)),
        truth_translation_rank=int(np.linalg.matrix_rank(yc)),matched_frames=len(x))


def freeze_scale(pointmap,reference,output):
    """Known fixed camera height / predicted signed floor distance (median).

    Floor mask must be selected from own RGB alone and frozen before truth is
    opened. No RANSAC acceptance constant or ground-truth metric fit is used.
    """
    ref=json.loads(Path(reference).read_text())
    mask_path=Path(reference).parent/ref['mask_path']
    if digest(mask_path)!=ref['mask_sha256']:
        raise ValueError('floor_mask_sha256_mismatch')
    mask=cv2.imread(str(mask_path),cv2.IMREAD_GRAYSCALE)
    p=np.load(pointmap)
    xyz=p['xyz'].reshape(*p['rgb'].shape[:2],3)
    if mask is None or mask.shape!=xyz.shape[:2]:
        raise ValueError('floor_mask_shape_mismatch')
    normal=np.asarray(ref['floor_normal_camera'],float)
    normal/=np.linalg.norm(normal)
    distances=-(xyz@normal)[mask>0]
    distances=distances[np.isfinite(distances)&(distances>0)]
    if not len(distances) or ref['camera_height_m']<=0:
        raise ValueError('floor_scale_unobservable')
    scale=float(ref['camera_height_m']/np.median(distances))
    result=dict(scale=scale,truth_reads=0,method='fixed_height_over_median_signed_predicted_floor_distance',
        selected_positive_finite_points=len(distances),distance_percentiles=np.percentile(distances,[0,25,50,75,100]).tolist(),
        reference_sha256=digest(reference),pointmap_sha256=digest(pointmap),reference=ref)
    with Path(output).open('x') as f:f.write(json.dumps(result,indent=2)+'\n')
    return result


def score(trajectory,truth,metric_scale,output):
    # Saved estimation and frozen allowed-input scale are loaded before truth.
    est=json.loads(Path(trajectory).read_text())['frames']
    frozen=json.loads(Path(metric_scale).read_text()) if metric_scale else None
    gt=json.loads(Path(truth).read_text())['frames']
    if len(est)!=len(gt) or any(a['index']!=b['index'] or a['t_sim_s']!=b['t_sim_s'] for a,b in zip(est,gt)):
        raise ValueError('frame_index_or_timestamp_denominator_mismatch')
    selected=[(a,b) for a,b in zip(est,gt) if a['success'] and b.get('camera_xyz_m') is not None]
    x=np.asarray([a['pose_sim3_final'][:3] for a,b in selected])
    y=np.asarray([b['camera_xyz_m'] for a,b in selected])
    result=dict(total_frames=len(est),tracking_success=sum(a['success'] for a in est),
        tracking_failure=sum(not a['success'] for a in est),scored_frames=len(selected),
        unscored_frames=len(est)-len(selected),trajectory_sha256=digest(trajectory),truth_sha256=digest(truth),
        scale_sha256=digest(metric_scale) if metric_scale else None,
        truth_used_only_for_post_save_alignment=True)
    for name,scale,fit_scale in [('sim3_truth_scale_reference',1.,True),('se3_allowed_scale',frozen['scale'] if frozen else None,False)]:
        if scale is None:
            result[name]=dict(status='unknown_no_allowed_scale')
            continue
        try: result[name]=align(x*scale,y,fit_scale)
        except ValueError as e: result[name]=dict(status='unobservable',reason=str(e))
    with Path(output).open('x') as f:f.write(json.dumps(result,indent=2)+'\n')
    return result


if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__)
    sub=p.add_subparsers(dest='mode',required=True)
    s=sub.add_parser('scale');s.add_argument('--pointmap',required=True);s.add_argument('--reference',required=True);s.add_argument('--output',required=True)
    s=sub.add_parser('score');s.add_argument('--trajectory',required=True);s.add_argument('--truth',required=True);s.add_argument('--metric-scale');s.add_argument('--output',required=True)
    a=p.parse_args()
    result=freeze_scale(a.pointmap,a.reference,a.output) if a.mode=='scale' else score(a.trajectory,a.truth,a.metric_scale,a.output)
    print(json.dumps(result,indent=2))
