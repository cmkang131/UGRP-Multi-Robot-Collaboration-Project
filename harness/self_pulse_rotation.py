"""Opt-in left-turn response gain; egomap32 frozen command calibration only."""
import copy
from functools import lru_cache
import hashlib
import json
from pathlib import Path
import numpy as np
from harness import self_pulse_odom as base

OPTION='s2_pulse_v122_rotL_v1'
CALIBRATION=Path(__file__).with_name('data')/'s2_pulse_v122_rotL_v1.json'
CALIBRATION_SHA256='8e9cfeb068e6c7a3d0bbddeba8bcfa1039f1a7794f3d76cd446e1a8ae7bbb43d'


@lru_cache(maxsize=1)
def calibrated_model():
    raw=CALIBRATION.read_bytes()
    if hashlib.sha256(raw).hexdigest()!=CALIBRATION_SHA256:
        raise ValueError('ROTATION_CALIBRATION_CHANGED')
    cal=json.loads(raw)
    if cal['base_model_sha256']!=base.MODEL_SHA256 or cal['cw_gain']!=1.:
        raise ValueError('ROTATION_BASE_MODEL_CHANGED')
    result=copy.deepcopy(base.model())
    p=result['profiles'][cal['profile']]
    curve=np.asarray(p['mean_curve']).copy()
    curve[:,2]*=cal['gain']
    p['mean_curve']=curve.tolist()
    p['mean_delta'][2]*=cal['gain']
    return result


def selected_model(motion_model='off'):
    # For pulse consumers, off preserves their existing v122 profile.
    if motion_model in ('off',base.OPTION):return base.model()
    if motion_model!=OPTION:raise ValueError('UNKNOWN_MOTION_MODEL')
    return calibrated_model()


class RotationPulseOdometry(base.PulseOdometry):
    def __init__(self,start_time=0.):
        super().__init__(start_time)
        self.profiles=calibrated_model()['profiles']
