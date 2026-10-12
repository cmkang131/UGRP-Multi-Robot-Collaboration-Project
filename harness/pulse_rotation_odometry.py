"""Shared, data-only finite-pulse calibration transform; default off identity.

Consumers (PF or analytic command odometry) use the same returned profiles.
Only fixed calibration assets and an existing profile table are inputs.
"""
import copy
import hashlib
import json
from pathlib import Path
import numpy as np

OPTION = 'rotation_xy_alpha_v1'
ASSET = Path(__file__).with_name('calibrations')/'pulse_rotation_xy_alpha_v1.json'


def selected_model(model, *, pulse_odometry='off'):
    if pulse_odometry == 'off':
        return model  # No copy, import-time asset read, RNG or metadata mutation.
    if pulse_odometry != OPTION:
        raise ValueError('unknown pulse_odometry')
    raw=ASSET.read_bytes();cal=json.loads(raw)
    alpha=np.asarray(cal['alpha_1_to_4'],float)
    if cal['option']!=OPTION or cal['runtime_gt'] is not False or alpha.shape!=(4,) or not np.isfinite(alpha).all() or np.any(alpha<0):
        raise ValueError('invalid fixed odometry calibration')
    result=copy.deepcopy(model)
    for key,fit in cal['profiles'].items():
        p=result['profiles'][key]
        if p['loaded'] or p['axis']!='turn' or p['duration_s']!=.10 or abs(p['u'])!=.35:
            raise ValueError('rotation calibration profile mismatch')
        curve=np.asarray(p['mean_curve'],float).copy()
        xy=np.asarray(fit['xy_curve'],float)
        curve[:,:2]=np.array([np.interp(p['times'],fit['times'],xy[:,i]) for i in range(2)]).T
        p['mean_curve']=curve.tolist();p['mean_delta']=curve[-1].tolist()
        trans2=float(curve[-1,:2]@curve[-1,:2]);rot2=float(curve[-1,2]**2)
        a1,a2,a3,a4=alpha
        # PR 5.4 squared-motion scaling; holonomic rotation slip is isotropic
        # in XY. Retain old floors and never reduce any original variance.
        variance=np.maximum(p['prediction_variance'],[(a3*trans2+a4*rot2)/2]*2+[a1*rot2+a2*trans2])
        p['prediction_variance']=variance.tolist()
        p['prediction_covariance']=np.diag(variance).tolist()
        p['rotation_xy_calibration']=copy.deepcopy(fit)
    result['pulse_odometry']=dict(option=OPTION,asset_sha256=hashlib.sha256(raw).hexdigest(),
        alpha_1_to_4=alpha.tolist(),runtime_gt=False,scope=cal['scope'])
    return result
