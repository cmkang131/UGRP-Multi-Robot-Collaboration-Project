"""Fixed PR #406 unloaded camera product. No live pose/joint/GT inputs.

Partial table is deliberately NOT admitted as a loaded/runtime calibration.
Own RGB wall replay opts into exact commanded poses, otherwise fails closed.
"""
from functools import lru_cache
import hashlib
import json
from pathlib import Path

import numpy as np
from harness.zone_final_pair_camera import floor_camera

VALUES = ('off', 'v3_unloaded_extrinsic_v1')
SOURCE_REF = 'dc1ed79bb561ec83d26085256ee6a3e1642adc41'
SHA256 = 'dc3157dbf77d5df5ab7ee63145e5c2cf7f5e8c0fbfc2231dd60712e26bc77b8c'
TABLE = Path(__file__).resolve().parents[1]/'experiments/2026-10-05-ego-wall-map-probe/calibration/s2_camera_v3_extrinsic_v1.json'


@lru_cache(maxsize=1)
def calibration():
    raw = TABLE.read_bytes()
    if hashlib.sha256(raw).hexdigest() != SHA256:
        raise ValueError('WALL_CAMERA_CALIBRATION_HASH_CHANGED')
    return json.loads(raw)


def camera_transform(servo, *, wall_camera_calibration='off'):
    if wall_camera_calibration not in VALUES:
        raise ValueError('UNKNOWN_WALL_CAMERA_CALIBRATION')
    if wall_camera_calibration == 'off':
        return None, 'off'
    servo = {int(k): int(v) for k, v in servo.items()}
    if 1 not in servo or servo[1] <= 1600:
        return None, 'loaded_or_unknown_load_not_calibrated'
    if any(k not in servo for k in (3, 4, 5, 6)):
        return None, 'unregistered_command_pose'
    key = ','.join(str(servo[k]) for k in (3, 4, 5, 6))
    entry = calibration()['camera_models']['unloaded'].get(key)
    if entry is None:
        return None, 'unregistered_command_pose'
    result = floor_camera(entry)
    return (np.array(result['origin_m']), np.array(result['rotation'])), 'calibrated_unloaded'
