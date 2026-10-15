"""Masked dense ECC homography. Default-off carry heading comparison only.

OpenCV findTransformECC default count=50, used as a finite computation budget;
no wall deadline, correlation cutoff or new motion acceptance constant.
https://docs.opencv.org/5.0/main_modules/video_track.html
"""
import math
import cv2
import numpy as np


def measure(before,after,cm):
    from harness.zone_solo_cyan_rotation_envelope import FLOW,PARAMS,PITCH,pitch_camera
    from harness import vision_loc_protocol as vp
    from harness.zone_solo_cyan_scene_change import cyan
    vl=vp.load_vis3()[0];K=np.linalg.inv(vl.mp.K_INV)
    images=[vl.mp.undistort(cv2.cvtColor(x,cv2.COLOR_RGB2BGR)) for x in (before,after)]
    gray=[cv2.cvtColor(x,cv2.COLOR_BGR2GRAY) for x in images]
    # A full pyramidal LK support must lie inside real image pixels. The R1
    # failure had 35/39 inliers on the fixed image border, H ~= identity.
    # Radius derives from the existing 21px window and 3 pyramid levels:80px.
    radius=(FLOW['lk_window_px']-1)//2*2**FLOW['lk_pyramid_levels']
    masks=[((g>10)&~cyan(im)).astype(np.uint8)*255 for im,g in zip(images,gray)]
    for m in masks:
        m[:radius]=0;m[-radius:]=0;m[:,:radius]=0;m[:,-radius:]=0
    # Dense image gradients supply the homography's eight constraints. Reject
    # algebraic rank loss using machine precision, not a fitted eigen cutoff.
    gx=cv2.Sobel(gray[0],cv2.CV_64F,1,0);gy=cv2.Sobel(gray[0],cv2.CV_64F,0,1)
    ys,xs=np.nonzero((masks[0]>0)&((gx!=0)|(gy!=0)))
    if len(xs)<8:return dict(status='unknown_dense_gradient_rank',category='weak_observation')
    ix=np.linspace(0,len(xs)-1,min(FLOW['max_corners'],len(xs)),dtype=int)
    x,y=xs[ix].astype(float),ys[ix].astype(float);u,v=gx[ys[ix],xs[ix]],gy[ys[ix],xs[ix]]
    J=np.column_stack([u*x,v*x,u*y,v*y,u,v,-u*x*x-v*x*y,-u*x*y-v*y*y])
    if np.linalg.matrix_rank(J)<8:return dict(status='unknown_dense_gradient_rank',category='weak_observation')
    try:
        cc,H=cv2.findTransformECC(gray[0],gray[1],np.eye(3,dtype=np.float32),cv2.MOTION_HOMOGRAPHY,
            (cv2.TERM_CRITERIA_COUNT,50,0),masks[1])
        back_cc,B=cv2.findTransformECC(gray[1],gray[0],np.eye(3,dtype=np.float32),cv2.MOTION_HOMOGRAPHY,
            (cv2.TERM_CRITERIA_COUNT,50,0),masks[0])
    except cv2.error:
        return dict(status='unknown_dense_alignment',category='weak_observation')
    p=np.column_stack([x,y]).astype(np.float32)
    q=cv2.perspectiveTransform(p[:,None],H)[:,0]
    back=cv2.perspectiveTransform(q[:,None],B)[:,0]
    residual=float(np.sqrt(np.mean(np.sum((back-p)**2,axis=1))))
    _,Rs,ts,ns=cv2.decomposeHomographyMat(H,K)
    possible=cv2.filterHomographyDecompByVisibleRefpoints(Rs,ns,
        cv2.undistortPoints(p[:,None],K,None),cv2.undistortPoints(q[:,None],K,None))
    ids=[i for i,n in enumerate(ns) if np.linalg.norm(n)<1e-8]
    if possible is not None:ids+=list(np.asarray(possible).ravel())
    ids=sorted(set(ids))
    if not ids:return dict(status='unknown_dense_cheirality',category='weak_observation')
    angles=[]
    for i in ids:
        for pitch in (-PITCH['pitch_common_bound_deg'],0.,PITCH['pitch_common_bound_deg']):
            R=pitch_camera(cm,math.radians(pitch))._rot
            body=R@Rs[i].T@R.T;angles.append(math.atan2(body[1,0],body[0,0]))
    angles=np.unwrap(angles);lo,hi=float(min(angles)),float(max(angles))
    pixel=max(FLOW['feature_pixel_sigma'],residual)/min(K[0,0],K[1,1])
    sigma=math.hypot(pixel,math.radians(PITCH['pitch_independent_bound_deg'])*math.sqrt(2/3))+(hi-lo)/(2*PARAMS['confidence_sigma'])
    return dict(status='measured',delta_yaw=(hi+lo)/2,sigma_yaw=sigma,method='masked_dense_ecc_homography',
        support_radius_px=radius,gradient_samples=len(p),gradient_rank=8,
        solutions=len(ids),solution_yaws_deg=np.degrees(angles).tolist(),
        forward_backward_rms_px=residual,ecc=cc,back_ecc=back_cc,
        iteration_budget_each=50,correlation_is_accuracy_certificate=False)
