"""Own-camera floor support and static-wall occlusion; no simulator inputs.

Map and estimated pose MUST share a registered frame. A local odometry origin
is not a map pose. Missing registration is an explicit unknown, never identity.
The inverse projection (ray/box slabs) handles fisheye curvature and walls
crossing the near plane without projecting invalid polygon vertices.
"""
from functools import lru_cache
import math

import cv2
import numpy as np

from harness.active_camera import transform
from sim.masterpi_camera_profile import CAMERA_FISHEYE_D, scaled_camera_matrix

OPTIONS = ('off', 'homography_v1', 'geom_v1')
PARAMS = dict(homography_px=3., confidence=.995, max_iters=2000,
              wall_margin_px=3, horizon_margin_px=3)
K = scaled_camera_matrix(640, 480)
D = np.asarray(CAMERA_FISHEYE_D, np.float64).reshape(4, 1)


def validate(option):
    if option not in OPTIONS:
        raise ValueError('UNKNOWN_VO_FLOOR_MASK')


@lru_cache(maxsize=16)
def rays(servo_items):
    origin, rotation = map(np.asarray, transform(dict(servo_items)))
    y, x = np.indices((480, 640))
    uv = np.stack((x, y), -1).astype(np.float64).reshape(-1, 1, 2)
    normal = cv2.fisheye.undistortPoints(uv, K, D).reshape(-1, 2)
    directions = np.column_stack((normal, np.ones(len(normal)))) @ rotation.T
    origin.setflags(write=False); directions.setflags(write=False)
    return origin, directions


def wall_boxes(static_map):
    """Whitelist only authored fixed wall geometry, never spawn/evaluation data."""
    boxes = []
    for wall in static_map['obstacles']:
        if wall.get('kind') != 'wall':
            continue
        values = np.array([*wall['center_m'], *wall['half_extents_m'],
                           wall['height_m'], wall.get('yaw_rad', 0.)], float)
        if values.shape != (6,) or not np.isfinite(values).all() or np.any(values[2:5] <= 0):
            raise ValueError('INVALID_STATIC_WALL')
        boxes.append(tuple(values))
    if not boxes:
        raise ValueError('STATIC_WALLS_REQUIRED')
    return tuple(boxes)


def geometric_mask(servo, boxes, estimated_pose):
    """Horizon below + exclude fixed walls projected at an estimated MAP pose.

    Returns None when map registration is unavailable. Caller must not silently
    substitute an own-start or evaluation pose.
    """
    if boxes is None or estimated_pose is None:
        return None
    pose = np.asarray(estimated_pose, float)
    if pose.shape != (3,) or not np.isfinite(pose).all():
        raise ValueError('FINITE_REGISTERED_MAP_POSE_REQUIRED')
    origin, direction = rays(tuple(sorted((int(k), int(v)) for k, v in servo.items())))
    down = direction[:, 2] < -1e-9
    floor_t = np.full(len(direction), np.inf)
    floor_t[down] = -origin[2] / direction[down, 2]
    c, s = math.cos(pose[2]), math.sin(pose[2])
    rot = np.array([[c, -s, 0.], [s, c, 0.], [0., 0., 1.]])
    eye = origin @ rot.T + [pose[0], pose[1], 0.]
    world = direction @ rot.T
    blocked = np.zeros(len(direction), bool)
    for cx, cy, hx, hy, height, yaw in boxes:
        c, s = math.cos(yaw), math.sin(yaw)
        inv = np.array([[c, s, 0.], [-s, c, 0.], [0., 0., 1.]])
        o = (eye - [cx, cy, height / 2]) @ inv.T
        d = world @ inv.T
        near = np.full(len(d), -np.inf); far = np.full(len(d), np.inf)
        possible = np.ones(len(d), bool)
        for axis, half in enumerate((hx, hy, height / 2)):
            parallel = np.abs(d[:, axis]) < 1e-12
            possible &= ~(parallel & (abs(o[axis]) > half))
            a = np.full(len(d), -np.inf); b = np.full(len(d), np.inf)
            np.divide(-half-o[axis], d[:, axis], out=a, where=~parallel)
            np.divide(half-o[axis], d[:, axis], out=b, where=~parallel)
            near = np.maximum(near, np.minimum(a, b)); far = np.minimum(far, np.maximum(a, b))
        blocked |= possible & (far >= np.maximum(near, 0.)) & (np.maximum(near, 0.) < floor_t)
    n = 2*PARAMS['wall_margin_px']+1
    blocked = cv2.dilate(blocked.reshape(480, 640).astype(np.uint8), np.ones((n, n), np.uint8)) > 0
    n = 2*PARAMS['horizon_margin_px']+1
    below = cv2.erode(down.reshape(480, 640).astype(np.uint8), np.ones((n, n), np.uint8)) > 0
    return ((below & ~blocked)*255).astype(np.uint8)


def homography_inliers(p, q):
    """RANSAC in ideal pixel coordinates, NOT distorted fisheye pixels.

    A wall is also a plane: consensus alone cannot identify the ground.
    Geometry excludes walls first; downstream metric SE(2) still constrains
    the accepted plane to the calibrated ground height and normal.
    """
    if len(p) < 4:
        return np.zeros(len(p), bool)
    ideal = [cv2.fisheye.undistortPoints(np.asarray(x, np.float64).reshape(-1, 1, 2),
                                       K, D, P=K).reshape(-1, 2) for x in (p, q)]
    if not all(np.isfinite(x).all() for x in ideal):
        return np.zeros(len(p), bool)
    H, mask = cv2.findHomography(*ideal, cv2.RANSAC, PARAMS['homography_px'],
                                maxIters=PARAMS['max_iters'], confidence=PARAMS['confidence'])
    if H is None or mask is None or not np.isfinite(H).all() or np.linalg.matrix_rank(H) != 3:
        return np.zeros(len(p), bool)
    return mask.ravel().astype(bool)
