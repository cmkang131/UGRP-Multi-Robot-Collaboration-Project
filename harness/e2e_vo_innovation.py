"""Default-off measurement rejection for the existing own-RGB increment estimator.

robot_localization rejects a measurement outside its Mahalanobis gate; a large
innovation is not evidence that the visual measurement is correct. The original
VO instead replaces the command prior unconditionally on that branch. Keep that
original path for OFF. The stationary variant accepts a zero-translation update
only when the existing causal RGB stationarity detector corroborates it.
Inputs are issued-command predictions and own RGB diagnostics, never evaluation.
"""
import math
import numpy as np

OPTIONS = ('off', 'nis_reject_v1', 'nis_stationary_v1')
CHI2_99_SE2 = 11.345  # existing registered VO threshold, 3 degrees of freedom


def select_increment(row, *, option='off'):
    if option not in OPTIONS:
        raise ValueError('UNKNOWN_VO_INNOVATION_OPTION')
    current = np.asarray(row['fused_delta'], dtype=float)
    command = np.asarray(row['command_delta'], dtype=float)
    if current.shape != (3,) or command.shape != (3,) or not np.isfinite(current).all() or not np.isfinite(command).all():
        raise ValueError('FINITE_SE2_INCREMENT_REQUIRED')
    if option == 'off' or row.get('status') != 'measured':
        return current.copy(), 'unchanged'
    nis = float(row['nis'])
    if not math.isfinite(nis) or nis < 0:
        raise ValueError('FINITE_NONNEGATIVE_NIS_REQUIRED')
    if nis <= CHI2_99_SE2:
        return current.copy(), 'accepted_innovation'
    if option == 'nis_stationary_v1' and (row.get('gate') or {}).get('stationary') is True:
        # Same existing stall gate convention: no claim that RGB validates yaw.
        return np.array([0., 0., command[2]]), 'rgb_stationary_translation'
    return command.copy(), 'rejected_visual_innovation'
