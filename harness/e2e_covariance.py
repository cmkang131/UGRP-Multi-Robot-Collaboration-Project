"""Apply a frozen offline NEES scale, never fit on live truth or innovations."""
import numpy as np
from harness.zone_study_contract import ContractViolation

OPTION = 'nees_frozen_v1'


def inflate(covariance, *, option='off', profile=None):
    if option == 'off':
        return covariance
    if option != OPTION or not isinstance(profile, dict) or set(profile) != {
            'schema', 'xy_scale', 'calibration_sha256', 'scope'}:
        raise ContractViolation('FROZEN_NEES_PROFILE_REQUIRED')
    if profile['schema'] != 'ugrp.e2e_covariance_scale.v1':
        raise ContractViolation('INVALID_NEES_PROFILE')
    scale = profile['xy_scale']
    if type(scale) not in (float, int) or not np.isfinite(scale) or scale < 1:
        raise ContractViolation('INFLATION_SCALE_AT_LEAST_ONE')
    h = profile['calibration_sha256']
    if not isinstance(h, str) or len(h) != 64 or any(c not in '0123456789abcdef' for c in h):
        raise ContractViolation('NEES_CALIBRATION_HASH_REQUIRED')
    p = np.asarray(covariance, float)
    if p.shape != (3, 3) or not np.isfinite(p).all() or not np.allclose(p, p.T) or np.linalg.eigvalsh(p).min() < 0:
        raise ContractViolation('PSD_POSE_COVARIANCE_REQUIRED')
    # Scale cross-covariances consistently; yaw is not calibrated by XY NEES.
    d = np.diag([np.sqrt(scale), np.sqrt(scale), 1.])
    return (d @ p @ d).tolist()
