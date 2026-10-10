"""Explicit, offline-only mount candidates; never a new production default.

The Hiwonder drawing gives a lens *front*, not a measured optical centre.
Keep the ugrp1 K/distortion fixed to isolate mounting; this is not calibration
of the stock 170-degree lens or of our physical robot. See the experiment README.
"""
from __future__ import annotations

import math
import xml.etree.ElementTree as ET

import numpy as np

from sim.masterpi_camera_profile import CAMERA_LOCAL_POS_M, CAMERA_LOCAL_QUAT_WXYZ

PROFILE_ID = 'masterpi-camera-drawing-mount-review-v1'
DRAWING_URL = ('https://cdn.shopify.com/s/files/1/0084/2799/5187/files/'
               'masterpi_01173667-020d-4baa-8ec8-6ff4a45b6220.jpg?v=1716200111')
# Published pixel anchors, independently recorded before this review (2026-09-28).
# Drawing side view: wrist y=407.5, lens front y=283, tool x=765, lens x=831.5.
POSITION_M = ((407.5 - 283.) * 343. / 806. / 1000., 0.,
              (831.5 - 765.) * 185. / 437. / 1000.)
# MuJoCo camera right=-Y, up=+Z, view=-camera.Z=+X of the tool.
QUAT_WXYZ = (.5, .5, -.5, -.5)


def record():
    return {'id': PROFILE_ID, 'status': 'DRAWING_NOMINAL_NOT_REAL_CALIBRATED',
            'runtime_admitted': False, 'parent_body': 'gripper',
            'position_m': list(POSITION_M), 'quat_wxyz': list(QUAT_WXYZ),
            'source': DRAWING_URL, 'source_class': 'official_drawing_scaled',
            'translation_reading_uncertainty_m': .002,
            'uncertainty_scope': 'drawing reading only, not manufacturing tolerance',
            'unmeasured': ['optical centre vs lens front', 'lateral offset',
                           'mount angles', 'actual hardware camera revision'],
            'orientation_basis': 'parallel to tool in drawing; nominal, not measured',
            'intrinsics': 'existing ugrp1 K and fisheye D unchanged; stock lens unverified',
            'default_changed': False}


def quat_matrix(q):
    w, x, y, z = np.asarray(q, float) / np.linalg.norm(q)
    return np.array([[1-2*(y*y+z*z), 2*(x*y-z*w), 2*(x*z+y*w)],
                     [2*(x*y+z*w), 1-2*(x*x+z*z), 2*(y*z-x*w)],
                     [2*(x*z-y*w), 2*(y*z+x*w), 1-2*(x*x+y*y)]])


def _multiply(a, b):
    w, v = a[0], np.asarray(a[1:])
    s, u = b[0], np.asarray(b[1:])
    return np.r_[w*s-v@u, w*u+s*v+np.cross(v, u)]


def optical_tool_pitch_deg(quat):
    forward = -quat_matrix(quat)[:, 2]
    return math.degrees(math.atan2(forward[2], math.hypot(*forward[:2])))


def transform_xml(xml: str, *, profile_id: str) -> str:
    """Opt-in standalone diagnostic XML. Production renderers reset the old mount.

    Only the wrist cameras and massless, noncolliding camera visuals change.
    Contact geometry, dynamics, K/D, lights, objects and other cameras are fixed.
    No function installs this on the existing controller or simulation bundles.
    """
    if profile_id != PROFILE_ID:
        raise ValueError('unknown explicit camera review profile')
    root = ET.fromstring(xml)
    old = np.asarray(CAMERA_LOCAL_POS_M)
    qold = np.asarray(CAMERA_LOCAL_QUAT_WXYZ)
    delta = _multiply(QUAT_WXYZ, qold * [1, -1, -1, -1])
    rot = quat_matrix(delta)
    fmt = lambda v: ' '.join(f'{x:.15g}' for x in v)
    moved = 0
    for body in root.iter('body'):
        for cam in body.findall('camera'):
            if cam.get('name', '').split('__')[-1] != 'robot_cam':
                continue
            if body.get('name', '').split('__')[-1] != 'gripper':
                raise ValueError('review requires eye-in-hand gripper parent')
            if (not np.allclose(np.fromstring(cam.get('pos', ''), sep=' '), old)
                    or not np.allclose(np.fromstring(cam.get('quat', ''), sep=' '), qold)):
                raise ValueError('unexpected baseline camera mount')
            cam.set('pos', fmt(POSITION_M))
            cam.set('quat', fmt(QUAT_WXYZ))
            moved += 1
            for geom in body.findall('geom'):
                if '__v3_camera_' not in geom.get('name', '') and not geom.get('name', '').startswith('v3_camera_'):
                    continue
                if any(float(geom.get(k, '1')) != 0 for k in ('mass', 'contype', 'conaffinity')):
                    raise ValueError('camera hardware must be noncolliding and massless')
                if any(k in geom.attrib for k in ('euler', 'xyaxes', 'axisangle', 'zaxis')):
                    raise ValueError('unexpected camera hardware orientation encoding')
                if 'fromto' in geom.attrib:
                    points = np.fromstring(geom.get('fromto'), sep=' ').reshape(2, 3)
                    geom.set('fromto', fmt(((points-old) @ rot.T + POSITION_M).ravel()))
                else:
                    pos = np.fromstring(geom.get('pos', '0 0 0'), sep=' ')
                    geom.set('pos', fmt(rot @ (pos-old) + POSITION_M))
                    q = np.fromstring(geom.get('quat', '1 0 0 0'), sep=' ')
                    geom.set('quat', fmt(_multiply(delta, q)))
    if not moved:
        raise ValueError('no wrist cameras found')
    return ET.tostring(root, encoding='unicode')
