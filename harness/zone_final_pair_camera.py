"""Offline rigid-frame contract for v88, never a live chassis correction.

Each posture/load calibration keeps optical->actual chassis AND the measured
chassis->floor-heading transform. The latter removes world xy/yaw, retains
height/roll/pitch, and must be fitted offline on valid settled samples. Both
beam and PF consumers use their composition. No nominal wheel-height fallback.
"""
from __future__ import annotations

import numpy as np

from harness.vision_pose_source_final import CalibrationError


def rigid(record):
    try:
        origin = np.asarray(record['origin_m'], float)
        rotation = np.asarray(record['rotation'], float)
    except (KeyError, TypeError, ValueError) as exc:
        raise CalibrationError('missing measured rigid camera frame') from exc
    if (origin.shape != (3,) or rotation.shape != (3, 3)
            or not np.isfinite(origin).all() or not np.isfinite(rotation).all()
            or not np.allclose(rotation.T @ rotation, np.eye(3), atol=1e-6)
            or not np.isclose(np.linalg.det(rotation), 1., atol=1e-6)):
        raise CalibrationError('invalid measured rigid camera frame')
    return origin, rotation


def floor_camera(record):
    """Compose a fixed calibration product; missing floor frame fails closed."""
    origin, rotation = rigid(record)
    if record.get('frame') != 'optical_to_actual_chassis':
        raise CalibrationError('optical_to_actual_chassis frame required')
    floor_origin, floor_rotation = rigid(record.get('chassis_to_floor'))
    if (floor_origin[2] <= 0 or not np.allclose(floor_origin[:2], 0., atol=1e-9)
            or abs(floor_rotation[1, 0]) > 1e-6 or floor_rotation[0, 0] <= 0):
        raise CalibrationError('floor-heading frame must remove world xy/yaw')
    result = {'origin_m': (floor_origin + floor_rotation @ origin).tolist(),
              'rotation': (floor_rotation @ rotation).tolist(),
              'frame': 'optical_to_floor_heading'}
    if result['origin_m'][2] <= 0:
        raise CalibrationError('camera must be above the floor')
    return result


def measurement_label(base_position, base_rotation, camera_position, camera_rotation):
    """Teacher-only label construction, called ONLY by the evaluation owner.

    MuJoCo camera coordinates are right/up/back; optical is right/down/front.
    This raw label is not an approved calibration product for student runtime.
    """
    p, rb, pc, rc = map(np.asarray, (base_position, base_rotation, camera_position, camera_rotation))
    yaw = np.arctan2(rb[1, 0], rb[0, 0])
    c, s = np.cos(yaw), np.sin(yaw)
    floor_from_world = np.array([[c, s, 0.], [-s, c, 0.], [0., 0., 1.]])
    return {'frame': 'optical_to_actual_chassis',
            'origin_m': (rb.T @ (pc-p)).tolist(),
            'rotation': (rb.T @ rc @ np.diag([1., -1., -1.])).tolist(),
            'chassis_to_floor': {'origin_m': [0., 0., float(p[2])],
                                 'rotation': (floor_from_world @ rb).tolist()}}
