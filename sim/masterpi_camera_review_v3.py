"""User-observation target candidate, NOT a measured stock-camera calibration.

Keep the official drawing's nominal lens-front position and archived ugrp1
intrinsics. A +10 degree tool-relative optical pitch is a user-authorized
visibility-target choice (2026-10-06 16:40), not an official mounting angle.
Recovered real post-lift images support low visibility, but cannot identify
six mount parameters, lens distortion and grasp depth independently.
"""
from __future__ import annotations
import math
import xml.etree.ElementTree as ET
import numpy as np
from sim import masterpi_camera_review_v1 as drawing
from sim import masterpi_camera_profile as archived

PROFILE_ID = 'masterpi-camera-user-observation-target-review-v3'
POSITION_M = drawing.POSITION_M
OPTICAL_TOOL_PITCH_DEG = 10.
TARGET_MAX_FULL_FRACTION = .10
_ANGLE = math.radians(OPTICAL_TOOL_PITCH_DEG)
_DELTA = (math.cos(_ANGLE/2), 0., -math.sin(_ANGLE/2), 0.)
QUAT_WXYZ = tuple(drawing._multiply(_DELTA, drawing.QUAT_WXYZ))


def transform_xml(xml: str, *, profile_id: str) -> str:
    if profile_id != PROFILE_ID:
        raise ValueError('explicit offline user-observation v3 profile required')
    root = ET.fromstring(drawing.transform_xml(xml, profile_id=drawing.PROFILE_ID))
    rot = drawing.quat_matrix(_DELTA)
    fmt = lambda v: ' '.join(f'{x:.15g}' for x in v)
    for body in root.iter('body'):
        for camera in body.findall('camera'):
            if camera.get('name', '').split('__')[-1] != 'robot_cam':
                continue
            camera.set('quat', fmt(QUAT_WXYZ))
            for geom in body.findall('geom'):
                if not geom.get('name', '').split('__')[-1].startswith('v3_camera_'):
                    continue
                if 'fromto' in geom.attrib:
                    points = np.fromstring(geom.get('fromto'), sep=' ').reshape(2, 3)
                    geom.set('fromto', fmt(((points-POSITION_M) @ rot.T+POSITION_M).ravel()))
                else:
                    pos = np.fromstring(geom.get('pos', '0 0 0'), sep=' ')
                    geom.set('pos', fmt(rot@(pos-POSITION_M)+POSITION_M))
                    q = np.fromstring(geom.get('quat', '1 0 0 0'), sep=' ')
                    geom.set('quat', fmt(drawing._multiply(_DELTA, q)))
    return ET.tostring(root, encoding='unicode')


def record():
    return {'id': PROFILE_ID, 'runtime_admitted': False, 'default_changed': False,
        'status': 'USER_OBSERVATION_TARGET_NOT_REAL_CALIBRATED',
        'source_label': '사용자 실물 관찰 기반 목표', 'user_decision_kst': '2026-10-06T16:40:00+09:00',
        'target_max_full_image_fraction': TARGET_MAX_FULL_FRACTION,
        'position_m': list(POSITION_M), 'quat_wxyz': list(QUAT_WXYZ),
        'optical_tool_pitch_deg': OPTICAL_TOOL_PITCH_DEG,
        'position_source': drawing.DRAWING_URL,
        'angle_source': 'user visibility target; NOT official angle or measured fit',
        'angle_selection': 'single pre-run 10deg candidate; analytic projection on previous DEV HIGH gives ~5.62% full image',
        'intrinsics_source': archived.CAMERA_CALIBRATION_ID,
        'intrinsics_status': 'archived ugrp1 measured-K/D claim; original checkerboard and serial linkage unavailable',
        'processing': 'unchanged archived 640x480 fisheye K/D and raw remap; not SDK sample Brown5',
        'official_fov_deg': 170, 'official_fov_axis': 'UNSPECIFIED; cannot substitute for vertical fovy',
        'evidence': 'recovered real post-lift red 9 frames ~1.35%, blue 8 frames ~7.92%; PROBABLE_HELD only',
        'calibration_limit': 'no independent 3D/joint/held-state measurements; no unique mount or FOV fit',
        'setdown_relook_candidate': {'name': 'solo_cyan_setdown_relook', 'value': 'off_candidate',
            'implemented': False, 'requires_new_bundle': True,
            'requires': ['explicit runtime camera binding and ray calibration', 'loaded localization',
                         'grasp/loss verification without visible cargo', 'loaded drive/slip/placement tests']}}
