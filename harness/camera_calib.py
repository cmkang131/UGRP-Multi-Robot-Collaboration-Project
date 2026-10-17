"""camera_calib=measured_v1 (default off): fixed-posture camera extrinsics from an offline board calibration.

The commanded-servo FK (`servo_camera_fk`) is nominal: the real/rendered camera sits ~1 deg lower than the chain says
(pitch -19.05 vs -18.08 deg at SEARCH), which stretches ground-plane range by ~20 % at a 0.23 m camera height. A lab
fixes that once, offline, by viewing a known floor checkerboard from each fixed arm posture. The result is the versioned
file `data/camera_calib_measured_v1.json` (sha256 pinned below). At runtime this module is the ONLY input: it never reads
simulator/camera state. Postures are matched on the exact five commanded servo pulses; a posture that was not calibrated
falls back to the nominal FK and is counted in `status()` (never silent). Pan (servo 6) is part of the key because the
mount sag/offset may differ per arm configuration.
"""
import hashlib, json, sys
from pathlib import Path
import numpy as np

OPTION = 'measured_v1'
FILE = Path(__file__).with_name('data')/'camera_calib_measured_v1.json'
CALIB_SHA256_PIN = 'e52276b92bdd465a871591574bf6b2960078853f043dcd5fe65de80614f158d0'
_state = dict(mode='off', fallback=0, hits=0, missing=set())


def key(servo):
    return tuple(int(servo[k]) for k in (1, 3, 4, 5, 6))


def load(path=FILE, expected_sha256=None):
    raw = Path(path).read_bytes()
    digest = hashlib.sha256(raw).hexdigest()
    pin = expected_sha256 if expected_sha256 is not None else CALIB_SHA256_PIN
    if digest != pin:
        raise ValueError(f'CAMERA_CALIB_FILE_HASH_MISMATCH {digest}')
    return json.loads(raw)


_table = {}


def _build():
    if not _table:
        for entry in load()['postures']:
            _table[tuple(entry['servo_pulses_1_3_4_5_6'])] = (np.asarray(entry['origin_m'], float), np.asarray(entry['rotation_cam_in_robot'], float))
    return _table


def mode():
    return _state['mode']


def set_mode(value):
    """'off' | 'measured_v1'. Clears derived camera caches so cached floor masks/projections cannot leak between modes."""
    if value not in ('off', OPTION):
        raise ValueError('UNKNOWN_CAMERA_CALIB')
    if value == OPTION:
        _build()
    _state.update(mode=value, fallback=0, hits=0, missing=set())
    for name, module in list(sys.modules.items()):
        if name.startswith('harness.') and module is not None:
            for obj in list(vars(module).values()):
                if hasattr(obj, 'cache_clear') and callable(obj.cache_clear):
                    obj.cache_clear()


def apply(servo, nominal):
    """Calibrated (origin, rotation) for the exact posture, else the nominal FK pair (counted)."""
    if _state['mode'] != OPTION:
        return nominal
    hit = _build().get(key(servo))
    if hit is None:
        _state['fallback'] += 1; _state['missing'].add(key(servo))
        return nominal
    _state['hits'] += 1
    return hit[0].copy(), hit[1].copy()


def status():
    return dict(mode=_state['mode'], calibrated_hits=_state['hits'], nominal_fallbacks=_state['fallback'],
                uncalibrated_postures=sorted(_state['missing']))
