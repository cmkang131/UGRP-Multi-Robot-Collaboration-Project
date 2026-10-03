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
# valid_frame_ob (policy flag own_image_ob): the dark level is taken from the frame's own optical-black
# reference, the fisheye exterior >= OB_EDGE_PX outside the calibrated valid circle, plus OB_MARGIN_LSB.
# It is never above valid_frame's fixed level (V <= 7), so the dark rule is never stricter than v1.
OB_EDGE_PX = 10
OB_MARGIN_LSB = 2
LEGACY_DARK_MAX = 7


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


_OB = None


def _optical_black():
    """Pixels at least OB_EDGE_PX outside the fisheye valid circle: the renderer's unexposed area."""
    global _OB
    if _OB is None:
        k = np.ones((2 * OB_EDGE_PX + 1, 2 * OB_EDGE_PX + 1), np.uint8)
        _OB = cv2.erode((~_valid()).astype(np.uint8), k).astype(bool)
    return _OB


def dark_level(v_channel):
    """Highest V value that still counts as 'no signal': the optical-black median + OB_MARGIN_LSB, capped at
    valid_frame's fixed level so that this gate never rejects a frame the fixed-level gate accepts."""
    black = float(np.median(v_channel[_optical_black()]))
    return min(black + OB_MARGIN_LSB, LEGACY_DARK_MAX)


def valid_frame_ob(obs, rid, now):
    """``valid_frame`` with the dark fraction measured against the optical-black reference.

    Every other rule (freshness, JPEG, shape, 1-99 percentile contrast >= 15, std >= 3, dark fraction < 25 %)
    is the same. A wholly black or covered view has its interior at the optical-black level and still fails;
    a floor in shadow (V 5-9, well above the reference) is a low-light view, not a blocked one.
    """
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
        v_channel = cv2.cvtColor(frame, cv2.COLOR_BGR2HSV)[..., 2]
        value = v_channel[_valid()]
        low, high = np.percentile(value, [1, 99])
        return bool((value <= dark_level(v_channel)).mean() < .25 and high - low >= 15 and value.std() >= 3)
    except (ValueError, TypeError, KeyError, AttributeError, RuntimeError, cv2.error):
        return False


def frame_gate(policy):
    """The per-step own-image gate of a pair policy (the module attribute at call time, so probe patches apply)."""
    return valid_frame_ob if getattr(policy, 'own_image_ob', False) else valid_frame
