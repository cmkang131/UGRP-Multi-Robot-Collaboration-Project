"""Command-only review-v3 mount FK and native fisheye floor projection.

Adapted from ground_geometry_v4.py without rectangle fitting or half-depth.
Assumes settled commanded joints, a level base and a flat floor. No sim inputs.
"""
import math

import cv2
import numpy as np


K = np.array([[619.5194540517232, 0., 287.68910608896766],
              [0., 622.1654884818748, 218.69686648455726], [0., 0., 1.]])
D = np.array([-.0199819517209417, -.1707593617153504,
              -.2568318201202376, .9650933421665181])
TOOL_OFFSET = np.array([(407.5-283)*343/806/1000, 0.,
                        (831.5-765)*185/437/1000])


def camera_extrinsics(posture):
    """Return origin and ROW axes right/down/forward in the base floor frame."""
    try:
        p = np.array([posture[i] for i in (6, 5, 4, 3)], dtype=float)
    except (KeyError, TypeError, ValueError) as exc:
        raise ValueError('posture requires PWM keys 3,4,5,6') from exc
    if p.shape != (4,) or not np.isfinite(p).all():
        raise ValueError('posture commands must be finite scalars')
    p = np.clip(p, 500, 2500)
    yaw, shoulder, elbow, wrist = np.clip(
        [(p[0]-1500)*math.pi/2000, math.pi/2-(p[1]-1589)*math.pi/2000,
         -(p[2]-1553)*math.pi/2000, (p[3]-1554)*math.pi/2000],
        [-1.75, -.15, -1.80, -1.80], [1.75, 2.80, 1.80, 1.80])
    c, s = math.cos(yaw), math.sin(yaw)
    beta = shoulder + elbow + wrist
    cb, sb = math.cos(beta), math.sin(beta)
    ex, ey, ez = np.array([c*cb, s*cb, sb]), np.array([-s, c, 0.]), np.array([-c*sb, -s*sb, cb])
    r = .065*math.cos(shoulder) + .062*math.cos(shoulder+elbow)
    origin = np.array([.0482+c*r, s*r,
                       .1277+.065*math.sin(shoulder)+.062*math.sin(shoulder+elbow)])
    origin = origin + TOOL_OFFSET[0]*ex + TOOL_OFFSET[2]*ez
    a = math.radians(10)
    return origin, np.array([-ey, math.sin(a)*ex-math.cos(a)*ez,
                              math.cos(a)*ex+math.sin(a)*ez])


def pixel_rays(pixels, posture):
    """Invalid pixels/inversions return NaN rays, never plausible defaults."""
    uv = np.asarray(pixels, dtype=float).reshape(-1, 2)
    origin, axes = camera_extrinsics(posture)
    rays = np.full((len(uv), 3), np.nan)
    inside = (np.isfinite(uv).all(axis=1) & (uv[:, 0] >= 0) & (uv[:, 0] <= 639)
              & (uv[:, 1] >= 0) & (uv[:, 1] <= 479))
    ids = np.flatnonzero(inside)
    if len(ids):
        try:
            xy = cv2.fisheye.undistortPoints(uv[ids, None, :], K, D).reshape(-1, 2)
            back = cv2.fisheye.distortPoints(xy[:, None, :], K, D).reshape(-1, 2)
        except cv2.error:
            return origin, rays
        valid = np.isfinite(xy).all(axis=1) & (np.linalg.norm(back-uv[ids], axis=1) < 1e-5)
        good = np.column_stack((xy[valid], np.ones(int(valid.sum())))) @ axes
        rays[ids[valid]] = good / np.linalg.norm(good, axis=1)[:, None]
    return origin, rays


def project_pixels(pixels, posture):
    origin, rays = pixel_rays(pixels, posture)
    hits = np.full((len(rays), 2), np.nan)
    valid = np.isfinite(rays).all(axis=1) & (rays[:, 2] < -1e-6) & (origin[2] > 0)
    hits[valid] = origin[:2] - origin[2]*rays[valid, :2]/rays[valid, 2, None]
    return hits


def blob_body_bearing(blob, posture):
    """Camera-origin centroid ray azimuth expressed in body-oriented axes.

    Rotation is accounted for, but camera translation is NOT: without depth,
    this is not an exact base-origin point bearing. Bearing-only updates use
    that approximation at the retained predicted range; contact projection
    separately includes the full camera origin and supplies metric position.
    """
    _origin, rays = pixel_rays([[blob['cx'], blob['cy']]], posture)
    ray = rays[0]
    if not np.isfinite(ray).all() or math.hypot(*ray[:2]) <= 1e-6:
        return None
    return math.atan2(ray[1], ray[0])


def measure_contact(blob, posture):
    """Midpoint of endpoint medians of the projected lower envelope.

    Endpoint groups are exactly the first and last three occupied columns.
    Reject the entire measurement if any contour ray is invalid. This is a
    visible ground contact proxy, NOT a reconstructed box center.
    """
    uv = np.asarray(blob.get('bottom_pixels', []), dtype=float)
    if uv.ndim != 2 or uv.shape[1] != 2 or len(uv) < 6 or blob.get('clipped', False):
        return None
    if np.any((uv[:, 0] <= 1) | (uv[:, 0] >= 638) | (uv[:, 1] <= 1) | (uv[:, 1] >= 478)):
        return None
    hits = project_pixels(uv, posture)
    if not np.isfinite(hits).all():
        return None
    hits = hits[np.argsort(uv[:, 0], kind='stable')]
    n = 3
    contact = (np.median(hits[:n], axis=0) + np.median(hits[-n:], axis=0)) / 2.
    return float(contact[0]), float(contact[1])
