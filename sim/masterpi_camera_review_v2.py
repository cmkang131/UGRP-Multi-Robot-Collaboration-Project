"""Official SDK *sample* output camera, offline only; not device calibration.

Camera.py at SDK_SHA rectifies the Brown-5 image with alpha=0. Rendering its
ideal output rays directly avoids incorrectly applying the old fisheye D4.
The published 170-degree lens spec has no named axis/projection: it cannot
define MuJoCo fovy. Neither that spec nor this sample NPZ measures our device.
"""
from __future__ import annotations

import numpy as np

from sim import masterpi_camera_review_v1 as mount

PROFILE_ID = 'masterpi-camera-official-sdk-sample-review-v2'
SDK_SHA = '11b0cb04ada14be7c391e6c865ac705f903a95e7'
NPZ_SHA256 = 'e2329e57b70887f30e032702b3acd48e34e083bf6387b867129f7a10480115d6'
K = ((1266.9258200661907, 0., 324.82760876528357),
     (0., 1285.5144320144632, 116.0909553740869), (0., 0., 1.))
BROWN_D = (-.46330440526985905, -1.3069063152512517,
           -.0035339629326752984, -.005185913664714308, 19.159043885972334)
# Pure official SDK IK of (0,6,18) cm, requested pitch 0; then Deviation.yaml.
# This is the sorting example's lift pose, not a documented universal carry pose.
OFFICIAL_LIFT_NOMINAL = {3: 695, 4: 2413, 5: 782, 6: 1500}
OFFICIAL_LIFT_PWM = {3: 749, 4: 2466, 5: 871, 6: 1564}


def rectified_matrix():
    import cv2
    return cv2.getOptimalNewCameraMatrix(np.array(K), np.array(BROWN_D),
                                         (640, 480), 0, (640, 480))[0]


def valid_mask():
    import cv2
    x, y = cv2.initUndistortRectifyMap(np.array(K), np.array(BROWN_D), None,
                                      rectified_matrix(), (640, 480), cv2.CV_32FC1)
    return (x >= 0) & (x <= 639) & (y >= 0) & (y <= 479)


def pixel_intrinsic():
    k = rectified_matrix()
    return np.array([k[0, 0], k[1, 1], 320-k[0, 2], 240-k[1, 2]])


def transform_xml(xml: str, *, profile_id: str) -> str:
    if profile_id != PROFILE_ID:
        raise ValueError('explicit offline v2 profile required')
    return mount.transform_xml(xml, profile_id=mount.PROFILE_ID)


def record():
    import cv2
    k = rectified_matrix()
    return {'id': PROFILE_ID, 'runtime_admitted': False, 'default_changed': False,
            'status': 'OFFICIAL_SAMPLE_OUTPUT_NOT_DEVICE_CALIBRATED',
            'mount': mount.record(), 'sdk_sha': SDK_SHA, 'npz_sha256': NPZ_SHA256,
            'K': K, 'brown_D5': BROWN_D, 'rectified_K': k.tolist(),
            'processing': 'Camera.py: resize 640x480, Brown5 rectify, alpha=0; no ROI slice',
            'rendering': 'ideal rectified output rays; invalid remap pixels masked; no D4 remap',
            'opencv': cv2.__version__, 'official_lens_fov_deg': 170,
            'official_lens_fov_axis': 'UNSPECIFIED; not used as vertical fovy',
            'official_lift_pwm': OFFICIAL_LIFT_PWM,
            'unknowns': ['our device K/D and processed stream', 'lens optical centre',
                         'actual mount angles', 'real loaded joint angles and grasp depth',
                         'user object dimensions', 'SDK nominal vs real servo calibration'],
            'user_evidence': '2026-10-06: stock MasterPi camera; held object barely visible',
            'setdown_relook_candidate': {'value': 'off_candidate', 'implemented': False,
                'requires': ['new calibrated bundle', 'loaded localization',
                             'grasp/loss checks without visible cargo', 'loaded motion validation']}}
