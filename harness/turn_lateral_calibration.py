"""Default-off, independently measured turn-Y curve. No online truth input.

UMBmark's bidirectional measurement/split validation, adapted to command-driven
mecanum pulses; not the differential-drive wheelbase formula. X/yaw/noise stay.
"""
import copy
import hashlib
import json
from pathlib import Path
import numpy as np
from harness.self_pulse_rotation import calibrated_model

OPTION = 'motion_model_turn_lateral_v2'
ARTIFACT = Path(__file__).with_name('data')/'turn_lateral_v2.json'


def apply_model(calibration, base=None):
    result = copy.deepcopy(calibrated_model() if base is None else base)
    if calibration['option'] != OPTION or set(calibration['fit_seeds']) & set(range(63001,63007)):
        raise ValueError('INDEPENDENT_TURN_CALIBRATION_REQUIRED')
    for key, values in calibration['profiles'].items():
        p = result['profiles'][key]
        if p['axis'] != 'turn' or p['loaded'] or p['duration_s'] != .1:
            raise ValueError('UNMEASURED_PROFILE')
        curve = np.asarray(p['mean_curve']).copy()
        y = np.asarray(values['lateral_curve_m'])
        if y.shape != (len(curve),) or not np.isfinite(y).all() or y[0] != 0:
            raise ValueError('INVALID_LATERAL_CURVE')
        curve[:,1] = y
        p['mean_curve'] = curve.tolist()
        p['mean_delta'][1] = float(y[-1])
    return result


def load():
    raw = ARTIFACT.read_bytes()
    data=json.loads(raw)
    if not data.get('qualification',{}).get('gate'):
        raise ValueError('INDEPENDENT_CALIBRATION_NOT_QUALIFIED')
    return apply_model(data), hashlib.sha256(raw).hexdigest()


def install(controller, *, motion_model_turn_lateral_v2='off', calibration=None):
    if motion_model_turn_lateral_v2 == 'off':
        return controller
    if motion_model_turn_lateral_v2 != OPTION:
        raise ValueError('UNKNOWN_TURN_LATERAL_OPTION')
    model, digest = load() if calibration is None else (apply_model(calibration), 'test_fixture')
    driver = controller.explorer.memory.self_map.odom.driver
    driver.profiles = model['profiles']
    # Finish a prefix command with its original curve; only new issued commands
    # select the new profile. No checkpoint pose/map rewrite or retroactive GT.
    controller.heading_host.profiles = model['profiles']
    from harness import active_wall_mapping
    previous = active_wall_mapping.selected_model
    active_wall_mapping.selected_model = lambda option='off': model if option == 's2_pulse_v122_rotL_v1' else previous(option)
    controller._turn_lateral_record = dict(option=OPTION, sha256=digest, prefix_recomputed=False,
        changed_axes=['turn_lateral'], yaw_noise_forward_unchanged=True)
    return controller
