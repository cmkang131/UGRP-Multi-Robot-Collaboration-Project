"""Scoped S2 port of PR405/762a952f left-turn calibration; default no-op.

Only own commanded SEARCH + inferred unloaded + explicitly stiff plant qualify.
Carry/CW/XY/noise remain v122. No simulator state or evaluation data is read.
"""
import copy
import hashlib
import json
from pathlib import Path

import numpy as np

OPTION = 's2_pulse_v122_rotL_v1'
SEARCH = {1: 2000, 3: 740, 4: 2320, 5: 1320, 6: 1500}
ROOT = Path(__file__).resolve().parents[1]
CALIBRATION = ROOT / 'configs/calibration/s2_pulse_v122_rotL_v1.json'
CALIBRATION_SHA = '8e9cfeb068e6c7a3d0bbddeba8bcfa1039f1a7794f3d76cd446e1a8ae7bbb43d'


def calibration():
    raw = CALIBRATION.read_bytes()
    if hashlib.sha256(raw).hexdigest() != CALIBRATION_SHA:
        raise ValueError('ROTATION_CALIBRATION_CHANGED')
    return json.loads(raw)


def corrected_profile(model):
    """Exact egomap33 arithmetic: scale yaw mean curve/endpoint only."""
    cal = calibration()
    base = ROOT / 'configs/s2_motion_v7_pulse_cal_v1.json'
    if hashlib.sha256(base.read_bytes()).hexdigest() != cal['base_model_sha256']:
        raise ValueError('ROTATION_BASE_MODEL_CHANGED')
    if model != json.loads(base.read_text()):
        raise ValueError('ROTATION_REQUIRES_UNCHANGED_V122')
    p = copy.deepcopy(model['profiles'][cal['profile']])
    curve = np.asarray(p['mean_curve']).copy()
    curve[:, 2] *= cal['gain']
    p['mean_curve'] = curve.tolist()
    p['mean_delta'][2] *= cal['gain']
    return p


def supported(servo, loaded, stiffness):
    return (stiffness == 'real_v1' and not loaded
            and all(servo.get(k) == v for k, v in SEARCH.items()))


def attach(runtime, *, rotation_calibration='off', servo_stiffness='off'):
    """Wrap the final S2 runtime after slip installs its PF pulse dictionary.

    Prediction picks its immutable profile at command time. Temporary dictionary
    selection does not change an already active pulse or a slip replacement.
    Planner and PF use the identical scope and profile. Off touches nothing.
    """
    if rotation_calibration == 'off':
        return runtime
    if rotation_calibration != OPTION:
        raise ValueError('UNKNOWN_ROTATION_CALIBRATION')
    if servo_stiffness != 'real_v1' or getattr(runtime, 'slip_detection', None) != 'slip_detect_v1':
        raise ValueError('ROTATION_REQUIRES_STIFF_V133_SLIP_STACK')
    if hasattr(runtime, 'rotation_left_audit'):
        raise ValueError('ROTATION_ALREADY_ATTACHED')
    cal = calibration(); key = cal['profile']
    profile = corrected_profile(runtime.pulse_model)
    inner = runtime.pose.provider; pf = inner.loc._pf
    live = runtime.flow.profiles
    audit = dict(option=OPTION, calibration_sha256=CALIBRATION_SHA,
                 source_commit='762a952f0786cb56e9ab88c8a2bf34ca2f346b87',
                 scope='stiff real_v1, own commanded SEARCH, inferred unloaded only',
                 loaded_motion='v122 unchanged', gt_inputs=False, rows=[])
    runtime.rotation_left_audit = audit
    old_command, old_drive, old_record = pf.command, runtime.drive, runtime.record

    def eligible():
        return supported(inner.servo, pf.load.loaded, servo_stiffness)

    def command(row):
        from harness.zone_solo_cyan_pulse_cal import profile_key
        moving = row['kind'] in ('drive', 'mecanum') and any(row.get(k, 0) for k in ('forward', 'left', 'turn'))
        change = bool(moving and eligible() and profile_key(row, False) == key)
        old = live[key]
        if change:
            live[key] = profile
            audit['rows'].append(dict(t=row['t'], profile=key, gain=cal['gain'],
                                     commanded_servo=dict(inner.servo)))
        try:
            return old_command(row)
        finally:
            live[key] = old

    def drive(*args, **kwargs):
        old = runtime.pulse_profiles[key]
        if eligible():
            runtime.pulse_profiles[key] = profile
        try:
            return old_drive(*args, **kwargs)
        finally:
            runtime.pulse_profiles[key] = old

    def record():
        return {**old_record(), 'rotation_calibration': copy.deepcopy(audit)}

    pf.command, runtime.drive, runtime.record = command, drive, record
    from harness.zone_solo_cyan_v106 import hp
    inner.runtime_contract['s2_rotation_calibration'] = {k: v for k, v in audit.items() if k != 'rows'}
    inner.identity_sha256 = hp.base.digest(inner.runtime_contract)
    inner.source = 'owncam_pf_s2_rotL:' + inner.identity_sha256[:8]
    runtime.pose.source = inner.source
    return runtime
