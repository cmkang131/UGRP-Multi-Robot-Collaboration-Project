"""Default-off calibrated innovation validation and Joseph-form pose fusion.

Bar-Shalom et al. / Piche (2016): S=H P H' + R, NIS=nu' S^-1 nu.
H=I for an SE(2) pose measurement in the SAME local frame. Three measured
coordinates give DOF=3, alpha=.01 -> chi2(3,.99)=11.344866730144373.
The nominal probability assumes independent Gaussian errors. Successive PF
posteriors are correlated; this adapter does not claim statistical coverage.
Calibration uses every fresh candidate in the two original DEV runs, including
rejections and bad poses. Sources, percentiles and limitations are in config.
"""
import json, math
from pathlib import Path
import numpy as np
from harness.natural_floor_slam import wrap

OPTION='reloc18_innovation_v1'

def calibration():
    return json.loads((Path(__file__).resolve().parents[1]/'configs/calibration/reloc18_innovation_v1.json').read_text())

def carry_calibration():
    return json.loads((Path(__file__).resolve().parents[1]/'configs/calibration/reloc18_carry_innovation_v1.json').read_text())

def fuse_heading(prior,observed,P,variance):
    """One observed yaw -> DOF=1, chi2(.99,1), preserving yaw null branches upstream."""
    x=np.asarray(prior,float).copy();P=np.asarray(P,float)
    nu=wrap(observed-x[2]);S=float(P[2,2]+variance)
    if not np.isfinite(P).all() or not np.isfinite([nu,S,variance]).all() or variance<=0 or S<=0:
        raise ValueError('FINITE_POSITIVE_HEADING_VARIANCE_REQUIRED')
    threshold=6.6348966010212145  # scipy chi2.ppf(.99,1), same nominal alpha=.01
    nis=nu*nu/S;accepted=nis<=threshold;K=P[:,2]/S if accepted else np.zeros(3)
    x+=K*nu;x[2]=wrap(x[2]);H=np.array([[0.,0.,1.]]);I=np.eye(3)-K[:,None]@H
    posterior=I@P@I.T+np.outer(K,K)*variance
    return dict(accepted=accepted,reason='within_chi2_gate' if accepted else 'chi2_rejected',nis=nis,dof=1,alpha=.01,
        chi2_threshold=threshold,kalman_gain=K.tolist(),innovation_rad=nu,posterior_pose=x.tolist(),posterior_covariance=posterior.tolist(),
        category='heading_innovation',blocked_object='own_rgb_wall_axis',minimum_gap_m=None,gap_scope='not_applicable_localization_gate')

def fuse(prior,candidate,P,R,*,threshold):
    prior,candidate=np.asarray(prior,float),np.asarray(candidate,float)
    P,R=np.asarray(P,float),np.asarray(R,float)
    if prior.shape!=(3,) or candidate.shape!=(3,) or P.shape!=(3,3) or R.shape!=(3,3):
        raise ValueError('SE2_POSE_AND_COVARIANCE_REQUIRED')
    if not all(np.isfinite(v).all() for v in (prior,candidate,P,R)) or not math.isfinite(threshold) or threshold<=0:
        raise ValueError('FINITE_FILTER_INPUTS_REQUIRED')
    if not np.allclose(P,P.T) or not np.allclose(R,R.T) or min(np.linalg.eigvalsh(P).min(),np.linalg.eigvalsh(R).min())<0:
        raise ValueError('PSD_SYMMETRIC_FILTER_COVARIANCE_REQUIRED')
    nu=candidate-prior;nu[2]=wrap(nu[2]);S=P+R
    # Singular observed directions cannot silently disappear via pseudoinverse.
    if np.linalg.eigvalsh(S).min()<=0:
        return dict(accepted=False,reason='singular_innovation',nis=None,posterior_pose=prior.tolist(),posterior_covariance=P.tolist())
    nis=float(nu@np.linalg.solve(S,nu));accepted=nis<=threshold
    K=np.linalg.solve(S.T,P.T).T if accepted else np.zeros((3,3))
    x=prior+K@nu;x[2]=wrap(x[2]);I=np.eye(3)-K
    posterior=I@P@I.T+K@R@K.T
    return dict(accepted=accepted,reason='within_chi2_gate' if accepted else 'chi2_rejected',
        nis=nis,innovation=nu.tolist(),predicted_covariance=P.tolist(),measurement_covariance=R.tolist(),
        innovation_covariance=S.tolist(),kalman_gain=K.tolist(),posterior_pose=x.tolist(),
        posterior_covariance=((posterior+posterior.T)/2).tolist(),chi2_threshold=threshold,dof=3,alpha=.01,
        category='accepted_visual_pose' if accepted else 'innovation_outlier',blocked_object='own_rgb_static_pose',
        minimum_gap_m=None,gap_scope='not_applicable_localization_gate',confirmed_outlier=False)

class InnovationGate:
    def __init__(self,fit=None):
        self.fit=fit or calibration();self.hypotheses=[];self.last=None
        self.rotation=np.eye(3);self.last_fused_t=-math.inf

    def consider(self,prior,candidate,predicted,measured,**meta):
        t=float(meta['t'])
        if t-self.last_fused_t<self.fit['measurement_correlation_sim_s']:
            self.last=dict(accepted=False,reason='correlated_measurement_thinned',confirmed_outlier=False,
                option=OPTION,nis=None,category='correlated_measurement',blocked_object='reused_PF_posterior',
                minimum_gap_m=None,gap_scope='not_applicable_localization_gate',
                correlation_sim_s=self.fit['measurement_correlation_sim_s'])
            return self.last
        # PF formal covariance is added to an empirically measured residual
        # floor. A concentrated wrong PF mode cannot declare itself precise.
        floor=self.rotation@np.asarray(self.fit['measurement_covariance_world'])@self.rotation.T
        R=np.asarray(measured)+floor
        self.last=fuse(prior,candidate,predicted,R,threshold=self.fit['chi2_threshold'])
        if self.last['accepted']:self.last_fused_t=t
        self.last.update(option=OPTION,source=meta.get('source'),confirmations=0,
                         measured_frame='same_robot_local_origin',covariance_calibration_scope=self.fit['fit_scope'])
        return self.last
