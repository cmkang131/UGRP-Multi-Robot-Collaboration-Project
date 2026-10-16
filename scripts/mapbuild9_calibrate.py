"""Fit odometry noise from own RGB LK covariances, never ground truth."""
import argparse
import hashlib
import json
from pathlib import Path
import platform


def main(a):
    if not platform.node().startswith('ugrp-act-l4-gcp5'):
        raise ValueError('GCP5_ONLY')
    import numpy as np
    from scipy.optimize import nnls
    sources={}; X=[]; yaw=[]; translation=[]; counts={}
    for root in a.inputs:
        p=root/'online-trajectory.json'; rows=json.loads(p.read_text())
        sources[str(p)]=hashlib.sha256(p.read_bytes()).hexdigest()
        selected=[r for r in rows if r['lk']['status']=='measured']
        counts[str(root)]=len(selected)
        for r in selected:
            d=np.asarray(r['lk']['delta']); P=np.asarray(r['lk']['covariance'])
            tr=float(np.hypot(d[0],d[1])); r1=0. if tr<.01 else float(np.arctan2(d[1],d[0]))
            r2=float(np.arctan2(np.sin(d[2]-r1),np.cos(d[2]-r1)))
            n1=min(abs(r1),abs(float(np.arctan2(np.sin(r1-np.pi),np.cos(r1-np.pi)))))
            n2=min(abs(r2),abs(float(np.arctan2(np.sin(r2-np.pi),np.cos(r2-np.pi)))))
            X.append([n1*n1+n2*n2,2*tr*tr]);yaw.append(P[2,2]);translation.append(np.trace(P[:2,:2]))
    X=np.asarray(X); y=np.asarray(yaw); q=np.asarray(translation)
    if len(X)<4 or np.linalg.matrix_rank(X)!=2:
        raise ValueError('OWN_MOTION_DESIGN_RANK_DEFICIENT')
    # Rotation response dispersion comes from the frozen R2 own-RGB repeated
    # command distribution, not only the optimistic within-frame LK fit noise.
    command=json.loads(a.command_calibration.read_text())
    if command['schema']!='ugrp.mapbuild8.own_command_motion.v1':raise ValueError('OWN_REPEAT_CALIBRATION_REQUIRED')
    mean=np.asarray(command['mean_delta']); P=np.asarray(command['predictive_covariance'])
    turn=float(mean[2]**2)
    if turn<=0:raise ValueError('REPEAT_TURN_REQUIRED')
    a1=float(P[2,2]/turn)
    a4=float(np.trace(P[:2,:2])/turn)
    # Translation channels: nonnegative fit to remaining own reported LK
    # variance. These short rotation recordings do not qualify loaded travel.
    a2=float(nnls(X[:,1,None],np.maximum(0,y-X[:,0]*a1))[0][0])
    # Var(trans_hat)=alpha3*trans^2+alpha4*(rot1_noise^2+rot2_noise^2).
    a3=float(nnls((X[:,1]/2)[:,None],np.maximum(0,q-X[:,0]*a4))[0][0])
    sources[str(a.command_calibration)]=hashlib.sha256(a.command_calibration.read_bytes()).hexdigest()
    out=dict(schema='ugrp.mapbuild9.own_amcl_noise.v1',alphas=[a1,a2,a3,a4],truth_inputs=0,
        sources=sources,counts=counts,rows=len(X),design_rank=int(np.linalg.matrix_rank(X)),
        covariance_scope='alpha1/4 from R2 raw own-LK repeated-command predictive dispersion divided by mean yaw squared; alpha2/3 nonnegative fit to remaining R1/R2 LK reported variance; no ground-truth residuals or load calibration',
        residual_rms=dict(yaw_variance=float(np.sqrt(np.mean((X@[a1,a2]-y)**2))),
            translation_variance=float(np.sqrt(np.mean((np.column_stack((X[:,1]/2,X[:,0]))@[a3,a4]-q)**2)))),
        scope='R1/R2 calibration; R3 held out; no claim that regression residuals are real motion error',reproduction=__import__('sys').argv)
    if a.output.exists():raise ValueError('NO_OVERWRITE')
    a.output.write_text(json.dumps(out,indent=2)+'\n');print(json.dumps(out))


if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('--inputs',nargs='+',type=Path,required=True);p.add_argument('--command-calibration',type=Path,required=True);p.add_argument('--output',type=Path,required=True);main(p.parse_args())
