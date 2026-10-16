"""Opt-in pinhole cheirality at the own-wall map input, no pose/map truth.

Input points are floor (z=0) contacts in the current chassis frame. Camera
geometry must come from the caller's own command calibration in that SAME frame.
References and fixed replay criteria: ego-wall-map-probe README section 21.
"""
from __future__ import annotations

import numpy as np

VALUES = ("off", "positive_depth_v1")


def validate_option(value):
    if value not in VALUES:
        raise ValueError("UNKNOWN_WALL_PROJECTION_GUARD")


def floor_depths(points, camera_origin, camera_rotation):
    """Return optical Z and forward-ray floor parameter (NOT floor-trace t).

    R maps optical coordinates (right/down/forward) into the chassis frame.
    A pinhole ray has optical direction (x/z, y/z, 1), hence positive optical Z
    and positive ray t are equivalent for exact, finite plane intersections.
    Both are checked explicitly, including zero, horizon and nonfinite inputs.
    """
    origin = np.asarray(camera_origin, dtype=float)
    rotation = np.asarray(camera_rotation, dtype=float)
    if (origin.shape != (3,) or rotation.shape != (3, 3)
            or not np.isfinite(origin).all() or not np.isfinite(rotation).all()
            or not np.allclose(rotation.T @ rotation, np.eye(3), atol=1e-8, rtol=0)
            or not np.isclose(np.linalg.det(rotation), 1., atol=1e-8, rtol=0)):
        raise ValueError("WALL_PROJECTION_NEEDS_VALID_OWN_CAMERA_GEOMETRY")
    points = np.asarray(points, dtype=float)
    if points.ndim < 2 or points.shape[-1] != 2:
        raise ValueError("INVALID_WALL_PROJECTION_POINTS")
    floor = np.concatenate((points, np.zeros((*points.shape[:-1], 1))), axis=-1)
    with np.errstate(divide="ignore", invalid="ignore", over="ignore"):
        optical = (floor-origin) @ rotation
        depth = optical[..., 2]
        ray = (optical/depth[..., None]) @ rotation.T
        ray_t = -origin[2]/ray[..., 2]
    valid = (np.isfinite(floor).all(axis=-1) & np.isfinite(depth) & (depth > 0)
             & np.isfinite(ray_t) & (ray_t > 0))
    return depth, ray_t, valid


def filter_segments(segments, *, wall_projection_guard="off", camera_origin=None,
                    camera_rotation=None):
    """Keep a complete face only when BOTH endpoints have z>0 and ray t>0.

    Positive depth is affine along a straight segment, so this also covers its
    interior. No clipping, endpoint repair, free-space ray or hit for a rejected
    face. Off returns the exact input and never inspects geometry.
    """
    validate_option(wall_projection_guard)
    if wall_projection_guard == "off":
        return segments, None
    points = np.asarray(segments, dtype=float)
    if points.ndim != 3 or points.shape[1:] != (2, 2):
        raise ValueError("INVALID_WALL_PROJECTION_SEGMENTS")
    depth, ray_t, valid = floor_depths(points, camera_origin, camera_rotation)
    keep = valid.all(axis=1)
    rows = []
    for i in range(len(points)):
        reason = "accepted"
        if not keep[i]:
            reason = ("nonfinite_projection" if not (np.isfinite(points[i]).all()
                      and np.isfinite(depth[i]).all() and np.isfinite(ray_t[i]).all())
                      else "nonpositive_depth_or_ray_t")
        rows.append({"segment": i, "accepted": bool(keep[i]), "reason": reason,
                     "optical_z_m": [float(v) if np.isfinite(v) else None for v in depth[i]],
                     "ray_t": [float(v) if np.isfinite(v) else None for v in ray_t[i]]})
    return [segments[i] for i in np.flatnonzero(keep)], {
        "wall_projection_guard": wall_projection_guard, "input_segments": len(points),
        "accepted_segments": int(keep.sum()), "rejected_segments": int((~keep).sum()),
        "segments": rows,
    }
