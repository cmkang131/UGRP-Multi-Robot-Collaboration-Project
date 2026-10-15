"""Frozen offline pure-turn calibration. Runtime accepts issued commands only."""
from functools import lru_cache
import hashlib
import json
import math
from pathlib import Path

OPTION = 'reloc9_rotation_calibration_v1'
ROOT = Path(__file__).resolve().parents[1]
CALIBRATION = ROOT/'configs/calibration/reloc9_carry_rotation_v1.json'


def validate(enabled):
    if type(enabled) is not bool:
        raise ValueError(OPTION+' must be bool')


@lru_cache(maxsize=1)
def calibration():
    value = json.loads(CALIBRATION.read_bytes())
    if (value['schema'] != 'ugrp.reloc9_rotation.v1'
            or not math.isfinite(value['yaw_scale']) or not .1 < value['yaw_scale'] < 1.5
            or not math.isfinite(value['residual_rotation_fraction']) or value['residual_rotation_fraction'] < .25
            or not value['calibration_ids'] or not value['validation_ids']
            or set(value['calibration_ids']) & set(value['validation_ids'])
            or value['drive_model_sha256'] != hashlib.sha256((ROOT/'harness/drive_model.py').read_bytes()).hexdigest()):
        raise ValueError('RELOC9_ROTATION_PROVENANCE_MISMATCH')
    return value


def pure_turn(issued):
    a, b, c, d = issued['wheels']
    durations = issued['duration_s']
    return (abs(a) > 1e-9 and abs(a+b)+abs(a-c)+abs(b-d) < 1e-9
            and max(durations)-min(durations) < 1e-9)


def corrected_delta(issued, delta, value):
    # Mixed trim/translation and XY are deliberately outside the fitted scope.
    return (*delta[:2], delta[2]*value['yaw_scale']) if pure_turn(issued) else delta


def selfmap_model(motion_model, enabled=False):
    """Reuse the already calibrated pulse model, NEVER apply carry's .61 gain twice.

    Selfmap's default already selects rotL. The explicit reloc9 toggle pins the
    same model for either supported pulse starting model; v7 steady-state carry
    and finite-pulse selfmap are separate calibration strata.
    """
    validate(enabled)
    if not enabled:
        return motion_model
    from harness.self_pulse_rotation import OPTION as ROTATION
    from harness.self_pulse_odom import OPTION as BASE
    if motion_model not in (BASE, ROTATION):
        raise ValueError('RELOC9_REQUIRES_CALIBRATED_PULSE_MODEL')
    return ROTATION
