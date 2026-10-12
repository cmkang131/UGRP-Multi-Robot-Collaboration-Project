"""Robot-only calibrated envelope projection; no simulator or world-state input.

Equivalent to a conservative model shadow filter in the camera image. Articulated
links use issued servo commands; wheel envelopes cover unobserved wheel angles.
"""
from functools import lru_cache
import json
import math
from pathlib import Path

import cv2
import numpy as np

from harness.floor_goal import commanded_camera
from harness.visual_arm import PULSE_PER_DEGREE, SERVO_DEVIATION
from sim.masterpi_camera_profile import CAMERA_FISHEYE_D, scaled_camera_matrix


def rotation(node):
    if 'quat' in node:
        w, x, y, z = np.asarray(node['quat'], float)
        return np.array([[1-2*(y*y+z*z), 2*(x*y-z*w), 2*(x*z+y*w)],
                         [2*(x*y+z*w), 1-2*(x*x+z*z), 2*(y*z-x*w)],
                         [2*(x*z-y*w), 2*(y*z+x*w), 1-2*(x*x+y*y)]])
    result = np.eye(3)
    for axis, value in zip(np.eye(3), node.get('euler', [0., 0., 0.])):
        result = result @ cv2.Rodrigues(axis*value)[0]
    return result


def commanded_joints(servo):
    p = {int(k): float(v) for k, v in servo.items()}
    nominal = lambda i: p[i]-SERVO_DEVIATION.get(i, 0)
    close = max(0., min(1., (2000-p[1])/500))*.016
    return {'arm_yaw': math.radians((p[6]-1500)/PULSE_PER_DEGREE),
            'shoulder': math.radians(90-(nominal(5)-1500)/PULSE_PER_DEGREE),
            'elbow': math.radians(-(nominal(4)-1500)/PULSE_PER_DEGREE),
            'wrist_pitch': math.radians((nominal(3)-1500)/PULSE_PER_DEGREE),
            'left_gripper_close': close, 'right_gripper_close': close}


@lru_cache(maxsize=1)
def geometry():
    return json.loads((Path(__file__).parent/'data/floor_goal_self_geometry.json').read_text())['profiles']


def body_envelopes(servo, profile):
    angles = commanded_joints(servo)
    def visit(node, origin, axes):
        origin = origin + axes @ node['pos']
        axes = axes @ rotation(node)
        joint = node.get('joint')
        if joint:
            value = float(np.clip(angles[joint['name']], *joint['range']))
            axis = np.array(joint['axis'])
            if joint['type'] == 'slide':
                origin = origin + axes @ (axis*value)
            else:
                turn = cv2.Rodrigues(axis*value)[0]
                pivot = np.array(joint['pos'])
                origin = origin + axes @ (pivot-turn @ pivot)
                axes = axes @ turn
        for geom in node['envelopes']:
            yield geom['name'], np.asarray(geom['vertices']) @ axes.T + origin
        for child in node['children']:
            yield from visit(child, origin, axes)
    yield from visit(geometry()[profile], np.zeros(3), np.eye(3))


def project_envelopes(envelopes, origin, axes, width, height, padding_m=.002, dilate_px=2):
    """Conservative pinhole convex envelopes, then fisheye projection and dilation.

    Near-plane intersections are retained. A camera inside an envelope is masked
    fully rather than allowing rays through its own body. Holes can be overmasked.
    """
    mask = np.zeros((height, width), np.uint8)
    K, D = np.array(scaled_camera_matrix(width, height)), np.array(CAMERA_FISHEYE_D)
    for _, vertices in envelopes:
        center = vertices.mean(axis=0)
        directions = vertices[[4, 2, 1]]-vertices[0]
        lengths = np.linalg.norm(directions, axis=1)
        directions /= np.maximum(lengths[:, None], 1e-12)
        local = (vertices-center) @ directions.T
        vertices = center+(local+np.sign(local)*padding_m) @ directions
        camera_local = (origin-center) @ directions.T
        if np.all(lengths > 0) and np.all(np.abs(camera_local) <= lengths/2+padding_m):
            mask[:] = 1
            break
        optical = (vertices-origin) @ axes.T
        if np.max(optical[:, 2]) <= .001:
            continue
        # All pairs include every edge of each exported box, plus safe diagonals.
        samples = [optical[optical[:, 2] >= .001]]
        for i in range(len(optical)):
            for j in range(i):
                a, b = optical[i], optical[j]
                for fraction in (.25, .5, .75):
                    p = a*(1-fraction)+b*fraction
                    if p[2] >= .001:
                        samples.append(p[None])
                if (a[2]-.001)*(b[2]-.001) < 0:
                    samples.append((a+(.001-a[2])/(b[2]-a[2])*(b-a))[None])
        points = np.concatenate(samples)
        if len(points) < 3:
            continue
        uv = cv2.fisheye.projectPoints(points.reshape(-1, 1, 3), np.zeros(3), np.zeros(3), K, D)[0].reshape(-1, 2)
        if uv[:, 0].max() < 0 or uv[:, 1].max() < 0 or uv[:, 0].min() >= width or uv[:, 1].min() >= height:
            continue
        hull = cv2.convexHull(np.rint(uv).astype(np.int32))
        cv2.fillConvexPoly(mask, hull, 1)
    if dilate_px:
        mask = cv2.dilate(mask, np.ones((2*dilate_px+1, 2*dilate_px+1), np.uint8))
    return mask.astype(bool)


@lru_cache(maxsize=32)
def _cached_mask(servo_items, profile, width, height):
    servo = dict(servo_items)
    origin, axes = commanded_camera(servo, profile)
    mask = project_envelopes(body_envelopes(servo, profile), origin, axes, width, height)
    mask.setflags(write=False)
    return mask


def self_body_mask(servo, profile, width, height):
    return _cached_mask(tuple(sorted((int(k), float(v)) for k, v in servo.items())), profile, width, height)
