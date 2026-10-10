"""Default-off checkpoint registration using own RGB static floor features.

Images, issued posture and fixed v3 calibration only. Registration maps the
current floor-heading frame to the first visual reference, not a simulator pose.
An unsupported fit produces no correction. Initial object origin is the public
task entrance, so its initial placement error remains unobservable here.
"""
import math
import cv2
import numpy as np
from harness.owncam_pair_beam import decode
from harness.owncam_view import _D, valid_pixel_mask
from sim.masterpi_camera_profile import scaled_camera_matrix
from harness.zone_s3_coarse_fine import yaw_calibration
from harness.zone_final_pair_contract import camera_record

PARAMS = dict(features=500, ratio=.75, min_inliers=10, min_fraction=.60,
    ransac_m=.006, max_rms_m=.004, scale_tolerance=.02,
    min_spread_m=.025, max_range_m=.8, max_correction_m=.08,
    cargo_mask='saturation >150 or value <90 excluded', runtime_gt=False)


def points(pixels, record):
    xy = np.asarray(pixels, float).reshape(-1, 1, 2)
    n = cv2.fisheye.undistortPoints(xy, scaled_camera_matrix(640, 480), _D).reshape(-1, 2)
    rays = np.c_[n, np.ones(len(n))] @ np.asarray(record['rotation']).T
    origin = np.asarray(record['origin_m'])
    with np.errstate(divide='ignore', invalid='ignore'):
        scale = -origin[2]/rays[:, 2]
        p = origin + scale[:, None]*rays
    good = (rays[:, 2] < -1e-6) & (scale > 0) & np.isfinite(p).all(1)
    good &= np.linalg.norm(p[:, :2], axis=1) < PARAMS['max_range_m']
    return p[:, :2], good


def snapshot(obs, servo, calibration, beam):
    image = decode(obs['image'])
    hsv = cv2.cvtColor(image, cv2.COLOR_BGR2HSV)
    mask = valid_pixel_mask(1) & (hsv[:, :, 1] <= 150) & (hsv[:, :, 2] >= 90)
    # Calibrated floor-plane intersection also excludes the sky/near chassis.
    ys, xs = np.mgrid[0:480:4, 0:640:4]
    record = camera_record(yaw_calibration(calibration, servo[6]), 'unloaded', servo)
    _, good = points(np.c_[xs.ravel(), ys.ravel()], record)
    floor = cv2.resize(good.reshape(120, 160).astype(np.uint8), (640, 480), interpolation=cv2.INTER_NEAREST)
    key, desc = cv2.ORB_create(nfeatures=PARAMS['features']).detectAndCompute(image, (mask & floor.astype(bool)).astype(np.uint8)*255)
    xy, valid = points([k.pt for k in key], record) if key else (np.empty((0, 2)), np.empty(0, bool))
    key = [k for k, ok in zip(key, valid) if ok]
    desc = desc[valid] if desc is not None else None
    h = float(beam['axis_heading_rad'])
    center = np.asarray(beam['grip_base_m'])+.27*np.array([math.cos(h), math.sin(h)])
    return dict(points=xy[valid], desc=desc, center=center, heading=h,
        frame_id=obs['frame_id'], sha256=obs['sha256'], sim_time=obs['sim_time'])


def register(reference, current):
    info = dict(reference_frame=reference['frame_id'], current_frame=current['frame_id'],
        reference_sha256=reference['sha256'], current_sha256=current['sha256'],
        accepted=False, features=[len(reference['points']), len(current['points'])])
    if any(s['desc'] is None or len(s['points']) < PARAMS['min_inliers'] for s in (reference, current)):
        return None, dict(info, reason='insufficient_static_floor_features')
    pairs = cv2.BFMatcher(cv2.NORM_HAMMING).knnMatch(current['desc'], reference['desc'], k=2)
    pairs = [a for pair in pairs if len(pair) == 2 for a, b in [pair] if a.distance < PARAMS['ratio']*b.distance]
    # Enforce one-to-one reference correspondences before robust estimation.
    unique = {}
    for m in sorted(pairs, key=lambda m:m.distance): unique.setdefault(m.trainIdx, m)
    matches = list(unique.values()); info['matches'] = len(matches)
    if len(matches) < PARAMS['min_inliers']: return None, dict(info, reason='insufficient_matches')
    src = np.array([current['points'][m.queryIdx] for m in matches])
    dst = np.array([reference['points'][m.trainIdx] for m in matches])
    matrix, inliers = cv2.estimateAffinePartial2D(src, dst, method=cv2.RANSAC,
        ransacReprojThreshold=PARAMS['ransac_m'], maxIters=2000, confidence=.99, refineIters=10)
    if matrix is None: return None, dict(info, reason='no_rigid_consensus')
    keep = inliers.ravel().astype(bool); n = int(keep.sum())
    scale = float(np.linalg.norm(matrix[:, 0])); rms = float(np.sqrt(np.mean(np.sum((src[keep] @ matrix[:, :2].T+matrix[:, 2]-dst[keep])**2, axis=1))))
    spread = float(np.linalg.svd(src[keep]-src[keep].mean(0), compute_uv=False)[-1]/math.sqrt(n))
    info.update(inliers=n, fraction=n/len(matches), scale=scale, rms_m=rms, spread_m=spread)
    if (n < PARAMS['min_inliers'] or n/len(matches) < PARAMS['min_fraction']
            or abs(scale-1) > PARAMS['scale_tolerance'] or rms > PARAMS['max_rms_m']
            or spread < PARAMS['min_spread_m']):
        return None, dict(info, reason='registration_quality')
    # Remove fitted scale; use rigid translation/rotation only.
    rot = matrix[:, :2]/scale
    displacement = rot @ current['center']+matrix[:, 2]-reference['center']
    h = -reference['heading']; c, s = math.cos(h), math.sin(h)
    displacement = np.array([[c, -s], [s, c]]) @ displacement
    return displacement, dict(info, accepted=True, displacement_m=displacement.tolist(), reason='static_floor_rigid_registration')
