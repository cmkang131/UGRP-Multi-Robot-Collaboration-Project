"""Scene-only wall LK channel, separate from unchanged metric floor VO.

The old S>100 test remains exactly in floor image_mask. Wall points have a
separate RGB class mask and are NEVER projected to z=0 for translation.
"""
import cv2
import numpy as np
from harness.e2e_rgb_vo import PARAMS
from harness.scene_colour_boundary import surface_masks

OPTION='scene_wall_tracking_v1'


def track(before,after,calibration):
    from harness.active_wall_vision import modules
    mp,_,_=modules()
    images=[mp.undistort(cv2.cvtColor(x,cv2.COLOR_RGB2BGR)) for x in (before,after)]
    valid=(mp.undistort(np.full_like(images[0],255))==255).all(-1)
    masks=[]
    for im in images:
        mask=surface_masks(im,calibration,expanded_wall_value=True)[0]['wall'] & valid
        # Inherited floor LK erosion/block size7; window21, pyramid3, FB1px.
        masks.append(cv2.erode(mask.astype(np.uint8)*255,np.ones((7,7),np.uint8)))
    gray=[cv2.cvtColor(im,cv2.COLOR_BGR2GRAY) for im in images]
    unknown=dict(option=OPTION,status='unknown_wall_texture',wall_tracks=0,wall_inliers=0,
                 floor_mask_changed=False,metric_ground_fusion=False,truth_inputs=0)
    p=cv2.goodFeaturesToTrack(gray[0],maxCorners=PARAMS['max_corners'],qualityLevel=PARAMS['quality'],
        minDistance=PARAMS['min_distance_px'],mask=masks[0],blockSize=7)
    if p is None:return unknown
    cfg=dict(winSize=(PARAMS['lk_window_px'],)*2,maxLevel=PARAMS['lk_pyramid_levels'],
             criteria=(cv2.TERM_CRITERIA_EPS|cv2.TERM_CRITERIA_COUNT,30,.01))
    q,ok,_=cv2.calcOpticalFlowPyrLK(gray[0],gray[1],p,None,**cfg)
    if q is None:return unknown
    back,ok2,_=cv2.calcOpticalFlowPyrLK(gray[1],gray[0],q,None,**cfg)
    if back is None:return unknown
    a,b=p[:,0],q[:,0];ij=np.rint(b).astype(int)
    inside=(ij[:,0]>=0)&(ij[:,0]<640)&(ij[:,1]>=0)&(ij[:,1]<480)
    good=inside & ok.ravel().astype(bool)&ok2.ravel().astype(bool)&(abs(a-back[:,0]).max(1)<PARAMS['fb_max_px'])
    good[inside]&=masks[1][ij[inside,1],ij[inside,0]]>0
    a,b=a[good],b[good]
    if len(a)<PARAMS['min_tracks']:return {**unknown,'wall_tracks':len(a)}
    from harness.e2e_vo_floor_mask import PARAMS as H
    # Coordinates are already undistorted here; do not undistort a second time.
    _,mask=cv2.findHomography(a,b,cv2.RANSAC,H['homography_px'],maxIters=H['max_iters'],confidence=H['confidence'])
    keep=mask.ravel().astype(bool) if mask is not None else np.zeros(len(a),bool)
    return {**unknown,'status':'tracked_wall_plane','wall_tracks':len(a),'wall_inliers':int(keep.sum()),
            'before_uv':a[keep].tolist(),'after_uv':b[keep].tolist()}
