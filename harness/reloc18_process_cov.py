"""Default-off body-frame process noise from native transition residuals.

R2 used accumulated world error as a per-time Q, then applied the motion
Jacobian again. Here the initial pose error stays in P0 and Q describes only
actual body transition minus issued-command-model transition. Percentile and
positive-sequence correlation inflation are recorded in the immutable config.
"""
from functools import lru_cache
import json,math
from pathlib import Path
import numpy as np

@lru_cache(maxsize=1)
def calibration():
    return json.loads((Path(__file__).resolve().parents[1]/'configs/calibration/reloc18_process_cov_v1.json').read_text())

def covariance(corpus,delta,dt):
    delta=np.asarray(delta,float)
    if corpus not in ('carry','selfmap') or delta.shape!=(3,) or not np.isfinite(delta).all() or not math.isfinite(dt) or dt<0:
        raise ValueError('FINITE_BODY_TRANSITION_AND_SIM_INTERVAL_REQUIRED')
    mode='moving' if np.any(delta!=0) else 'idle'
    return np.asarray(calibration()['fits'][corpus][mode]['covariance_per_sim_s'])*dt
