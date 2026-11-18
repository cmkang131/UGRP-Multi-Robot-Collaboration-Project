"""Planar camera motion from tracked points with an unchanged camera mount."""
import math

import cv2
import numpy as np


def ground_points(pixels, intrinsics, camera_axes):
    """Intersect rectified rays with the floor in nominal camera-height units."""
    rays = np.column_stack((pixels, np.ones(len(pixels)))) @ np.linalg.inv(intrinsics).T
    rays = rays @ camera_axes.T
    points = np.full((len(pixels), 2), np.nan)
    valid = rays[:, 2] < -.03
    points[valid] = rays[valid, :2] / -rays[valid, 2, None]
    return points


def fixed_floor_pose(anchor_pixels, current_pixels, intrinsics, camera_axes, camera_offset):
    """Fit current-to-anchor SE(2) and return it only with distributed support.

    Limits are development gates in camera-height units. The fit assumes a
    flat floor and an unchanged mount, including pitch and height.
    """
    anchor = ground_points(anchor_pixels, intrinsics, camera_axes)
    current = ground_points(current_pixels, intrinsics, camera_axes)
    valid = (np.linalg.norm(anchor, axis=1) < 8) & (np.linalg.norm(current, axis=1) < 8)
    anchor, current = anchor[valid], current[valid]
    min_support = max(24, math.ceil(.6 * len(anchor)))
    if len(anchor) < min_support:
        return None, dict(reason='few_ground_tracks')

    error_limit = .012
    similarity, inliers = cv2.estimateAffinePartial2D(
        current, anchor, method=cv2.RANSAC, ransacReprojThreshold=error_limit,
    )
    if similarity is None:
        return None, dict(reason='ground_fit_failed')
    scale = np.linalg.norm(similarity[:, 0])
    if abs(scale - 1) > .06:
        return None, dict(reason='ground_scale_changed', fitted_scale=float(scale))
    keep = inliers.ravel().astype(bool)
    if np.count_nonzero(keep) < min_support:
        return None, dict(reason='few_ground_inliers', inliers=int(keep.sum()))

    # Enforce unit scale in the final fit. Similarity was used for outlier
    # rejection and as evidence of a change in projection.
    source, target = current[keep], anchor[keep]
    source_centre, target_centre = source.mean(0), target.mean(0)
    u, _, vt = np.linalg.svd((target - target_centre).T @ (source - source_centre))
    rotation = u @ np.diag([1., np.linalg.det(u @ vt)]) @ vt
    shift = target_centre - rotation @ source_centre
    errors = np.linalg.norm(current @ rotation.T + shift - anchor, axis=1)
    keep = errors <= error_limit
    count = int(keep.sum())
    hull = cv2.contourArea(cv2.convexHull(current[keep].astype(np.float32))) if count else 0.
    if count < min_support or hull < .015:
        return None, dict(reason='weak_rigid_floor_fit', inliers=count, hull_height_sq=hull)

    yaw = math.degrees(math.atan2(rotation[1, 0], rotation[0, 0]))
    if abs(yaw) > 10 or np.linalg.norm(shift) > .5:
        return None, dict(reason='floor_motion_out_of_range')
    body_shift = shift + (np.eye(2) - rotation) @ camera_offset[:2]
    pose = dict(x=float(body_shift[0]), y=float(body_shift[1]), yaw_deg=yaw,
                camera_x=float(shift[0]), camera_y=float(shift[1]),
                unit='initial nominal camera height', metric_verified=False)
    return pose, dict(reason='ok', inliers=count, hull_height_sq=hull,
                      residual_median_height=float(np.median(errors[keep])))
