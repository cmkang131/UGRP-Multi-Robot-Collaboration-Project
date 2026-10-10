"""Default-off S2 fixed own-RGB MLE motion covariance, no live fitting/GT.

Nav2 OmniMotionModel alpha1..5, LGPL-2.1+ equations. This adapter replaces
only covariance for measured loaded coarse lateral profiles. All means,
unmeasured profiles, observations and conservative thresholds stay unchanged.
"""
import copy
import hashlib
import json
from pathlib import Path

import numpy as np

OPTION='nav2_omni_mle_v1'
BASE=Path(__file__).resolve().parents[1]/'configs/s2_motion_v7_pulse_cal_v1.json'


def covariance_basis(delta):
    """Q=sum(alpha_i B_i), Nav2 omni_motion_model.cpp:59-85."""
    x,y,yaw=np.asarray(delta,float);t2=x*x+y*y;r2=yaw*yaw
    bearing=np.arctan2(y,x);c,s=np.cos(bearing),np.sin(bearing)
    rotation=np.array([[c,-s,0],[s,c,0],[0,0,1]])
    diag=np.array([[0,0,r2],[0,0,t2],[t2,0,0],[r2,r2,0],[0,t2,0]])
    return np.array([rotation@np.diag(d)@rotation.T for d in diag])


def attach(runtime, *, motion_noise='off', calibration=None):
    if motion_noise=='off':return runtime
    if motion_noise!=OPTION:raise ValueError('unknown motion_noise')
    table=copy.deepcopy(calibration or {})
    if (table.get('option')!=OPTION or table.get('fit_gt_inputs') is not False or
            table.get('fit_admitted') is not True or len(table.get('fit_seeds',[]))!=2 or
            table.get('base_sha256')!=hashlib.sha256(BASE.read_bytes()).hexdigest()):
        raise ValueError('identified two-run own-RGB calibration required')
    alpha=np.array(table['alpha'],float)
    if alpha.shape!=(5,) or not np.isfinite(alpha).all() or (alpha<0).any():raise ValueError('invalid alpha')
    live=runtime.flow.profiles
    for key in table['profiles']:
        p=live[key]
        if not p['loaded'] or p['axis']!='left' or abs(p['u'])!=.65 or p['duration_s']!=.65:
            raise ValueError('unmeasured motion profile')
    replacements={}
    for key in table['profiles']:
        p=copy.deepcopy(live[key]);cov=np.einsum('i,ijk->jk',alpha,covariance_basis(p['mean_delta']))
        p.update(prediction_covariance=cov.tolist(),prediction_variance=np.diag(cov).tolist())
        replacements[key]=p
    live.update(replacements)
    previous=runtime.record
    receipt=dict(option=OPTION,calibration=table,scope='loaded coarse lateral only; all means and all other profiles unchanged',gt_inputs=False)
    runtime.record=lambda:{**previous(),'motion_noise':copy.deepcopy(receipt)}
    inner=runtime.pose.provider
    from harness.zone_solo_cyan_v106 import hp
    inner.runtime_contract['s2_motion_noise']=receipt
    inner.identity_sha256=hp.base.digest(inner.runtime_contract)
    inner.source='owncam_pf_s2_noise:'+inner.identity_sha256[:8];runtime.pose.source=inner.source
    return runtime
