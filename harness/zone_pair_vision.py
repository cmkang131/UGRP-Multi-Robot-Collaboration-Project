"""Fail-closed own-frame gate before the frozen M2 visual hold/readiness checks.

A dev guard against corrupt, blank and substantially black-covered frames, not
proof that every possible occluder is detectable. No simulation state is read.
"""
import base64

import cv2
import numpy as np

from harness.m1_owncam_contract import validate_observation
from harness.owncam_pair_beam_v2 import _valid

PROFILE = 'zone_pair_frame_gate_v1_dev'


def valid_frame(obs, rid, now):
    try:
        validate_observation(obs, robot_id=rid, previous_frame_id=None, now=now)
        if (type(obs['frame_id']) is not int or obs['frame_id'] < 0
                or not 0 <= now - obs['sim_time'] <= .25):
            return False
        jpeg = base64.b64decode(obs['image'], validate=True)
        if not jpeg.startswith(b'\xff\xd8') or not jpeg.endswith(b'\xff\xd9'):
            return False
        frame = cv2.imdecode(np.frombuffer(jpeg, np.uint8), cv2.IMREAD_COLOR)
        if frame is None or frame.shape != (480, 640, 3):
            return False
        # Ignore the calibrated fisheye rim; the dark grip band is valid when
        # the remaining view retains contrast (including the dark-floor v3 fixtures).
        value = cv2.cvtColor(frame, cv2.COLOR_BGR2HSV)[..., 2][_valid()]
        low, high = np.percentile(value, [1, 99])
        return bool((value < 8).mean() < .25 and high - low >= 15 and value.std() >= 3)
    except (ValueError, TypeError, KeyError, AttributeError, RuntimeError, cv2.error):
        return False
