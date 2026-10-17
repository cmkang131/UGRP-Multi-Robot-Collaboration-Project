"""Default-off empirical OWN-RGB repeat-command prior; no simulator inputs.

Exact issued wheel/duration/servo signature only. No interpolation, gain fit,
load extrapolation or confidence-of-the-mean shrinkage. The predictive covariance
is the observed per-interval spread, not an independent-trial uncertainty.
"""
import numpy as np

OPTION='own_command_motion_v1'


class CommandPrior:
    def __init__(self,calibration=None,*,option='off'):
        if option not in ('off',OPTION):raise ValueError('UNKNOWN_OWN_COMMAND_PRIOR')
        self.option=option;self.calibration=calibration
        if option==OPTION:
            c=calibration
            if not isinstance(c,dict) or c.get('schema')!='ugrp.mapbuild8.own_command_motion.v1':raise ValueError('OWN_RGB_COMMAND_CALIBRATION_REQUIRED')
            mean=np.asarray(c['mean_delta']);P=np.asarray(c['predictive_covariance'])
            if mean.shape!=(3,) or P.shape!=(3,3) or not np.isfinite(np.r_[mean,P.ravel()]).all() or not np.allclose(P,P.T) or np.linalg.eigvalsh(P).min()<=0:raise ValueError('FULL_RANK_PREDICTIVE_COVARIANCE_REQUIRED')

    def predict(self,nominal_delta,nominal_covariance,command,servo,previous_servo,interval_s):
        out=dict(delta=np.asarray(nominal_delta).tolist(),covariance=np.asarray(nominal_covariance).tolist(),source='nominal_6f_unqualified_native')
        if self.option=='off':return out
        c=self.calibration;qualified={int(k):v for k,v in c['qualified_servo'].items()}
        if servo!=qualified or previous_servo!=qualified or command is None or interval_s!=c['interval_s']:
            out['reason']='uncalibrated_pose_or_interval';return out
        if list(command['wheels'])!=c['wheels'] or list(command['duration_s'])!=c['duration_s']:
            out['reason']='uncalibrated_issued_signature';return out
        return dict(delta=c['mean_delta'],covariance=c['predictive_covariance'],source=OPTION,reason='exact_own_RGB_repeat_signature',calibration_sha256=c['source_sha256'])
