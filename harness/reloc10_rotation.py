"""Direction-specific offline odometry calibration; issued commands only.

Fit source: reloc9 90L / 180R diagnostic, GCP n4-highcpu-64.
The four fresh directions are holdout, never used by this runtime to fit.
This is UMBmark-style gain identification, not the UMBmark square experiment.
"""
from functools import lru_cache
import hashlib
import json
from pathlib import Path
from harness.reloc9_rotation import pure_turn

ROOT = Path(__file__).resolve().parents[1]
OPTION = 'reloc10_rotation_calibration_v1'


@lru_cache(maxsize=1)
def calibration():
    value = json.loads((ROOT/'configs/calibration/reloc10_carry_rotation_v1.json').read_bytes())
    if value['drive_model_sha256'] != hashlib.sha256((ROOT/'harness/drive_model.py').read_bytes()).hexdigest():
        raise ValueError('RELOC10_DRIVE_MODEL_CHANGED')
    if not all(.1 < value[k] < 1.5 for k in ('left_scale', 'right_scale')):
        raise ValueError('INVALID_RELOC10_ROTATION_GAIN')
    return value


def corrected_delta(issued, delta, value):
    if not pure_turn(issued):
        return delta
    scale = value['left_scale'] if delta[2] >= 0 else value['right_scale']
    return (*delta[:2], delta[2]*scale)
