"""Low-contrast ORB extraction, opt-in; no change to the pinned SLAM core.

Projection/mask/descriptor handling follows natural_floor_slam.extract.
Only FAST=7 differs from OpenCV's default20. ORB-SLAM2's TUM1.yaml uses
iniThFAST20/minThFAST7 for low-contrast cells. This is a global OpenCV ORB
comparison, not the ORB-SLAM octree/grid extractor or complete SLAM system.
Match/inlier/SE(2)/covariance/admission thresholds remain unchanged.
"""
import cv2
import numpy as np
from harness.natural_floor_slam import Observation, Options


def extract(rgb, servo, *, frame_id, t, sha256=''):
    from harness.e2e_rgb_vo import HEIGHT, WIDTH, ground, image_mask
    image=np.asarray(rgb)
    if image.shape != (HEIGHT, WIDTH, 3) or image.dtype != np.uint8:
        raise ValueError('NATURAL_FLOOR_REQUIRES_640X480_UINT8_RGB')
    keypoints,desc=cv2.ORB_create(nfeatures=Options().features,fastThreshold=7).detectAndCompute(
        cv2.cvtColor(image,cv2.COLOR_RGB2GRAY),image_mask(image,servo))
    if desc is None or not keypoints:
        return Observation(int(frame_id),float(t),np.empty((0,2)),np.empty((0,32),np.uint8),sha256)
    points,depth=ground(servo,np.asarray([p.pt for p in keypoints],np.float64))
    valid=np.isfinite(points).all(1)&np.isfinite(depth)&(depth>0)
    return Observation(int(frame_id),float(t),points[valid],desc[valid],sha256)
