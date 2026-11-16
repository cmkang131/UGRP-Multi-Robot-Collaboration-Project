"""Reproduce a stored pulse's EKF algebra; no physics and no GT inputs."""
import hashlib,json,sys
from pathlib import Path
import numpy as np
from harness.zone_solo_cyan_flow_fusion import VelocityEKF,PARAMS,compose,rot
from harness.zone_solo_cyan_pulse_cal import response


def audit():
    path=Path('/Users/changmin/projects/ugrp/outputs/s2-flow-fusion-20261007/replay-candidate.json')
    r=json.loads(path.read_text());pulse=next(p for p in r['visual_odometry']['rows'] if p['t']==107.35)
    bundle=json.loads((Path(r['source_raw'])/'bundle.json').read_text());profile=bundle['pulse_calibration']['profiles'][pulse['key']]
    f=VelocityEKF();rows=[];total=np.zeros(3);raw=np.zeros(3)
    for p in pulse['intervals']:
        dt=p['dt'];b=p['t']-pulse['t'];a=b-dt
        va,vb=response(profile,a),response(profile,b);cmd=vb-va;cmd[:2]=rot(-va[2])@cmd[:2]
        row=dict(t=p['t'],dt=dt,status=p['status'],command_delta=cmd.tolist(),
            command_variance=(np.array(profile['prediction_variance'])*dt/profile['times'][-1]).tolist(),command_is_ekf_input=False)
        if p['status']=='measured':
            z=np.array(p['delta'])/dt;R=np.array(p['covariance'])/dt**2
            prior=None if f.x is None else f.x.copy()
            P=None if f.p is None else f.p+np.diag(PARAMS['velocity_process_diagonal'])*dt
            d,cov,K=f.update(p['delta'],p['covariance'],dt)
            row.update(visual_delta=p['delta'],visual_velocity=z.tolist(),visual_velocity_R=R.tolist(),visual_delta_R=p['covariance'],
                prior_velocity=None if prior is None else prior.tolist(),prior_velocity_P=None if P is None else P.tolist(),
                kalman_gain=K.tolist(),posterior_velocity=f.x.tolist(),posterior_velocity_P=f.p.tolist(),filtered_delta=d.tolist(),
                covariance_units='velocity: (m/s,m/s,rad/s); delta: (m,m,rad)',
                correction_terms=None if prior is None else (K*(z-prior)[None,:]).tolist())
            raw=compose(raw,np.array(p['delta']))
        else:
            f=VelocityEKF();d=np.array(p['estimate_delta']);raw=compose(raw,d)
        assert np.allclose(d,p['estimate_delta'],atol=1e-14,rtol=0)
        total=compose(total,d);rows.append(row)
    assert np.allclose(total,pulse['delta'],atol=1e-14,rtol=0)
    return dict(schema='ugrp.s2.flow_ekf.input_audit.v1',source=str(path),source_sha256=hashlib.sha256(path.read_bytes()).hexdigest(),
        pulse_t=pulse['t'],axes=['forward_m','left_m','yaw_rad'],command_mean=profile['mean_delta'],command_covariance=np.diag(profile['prediction_variance']).tolist(),
        command_weight_in_valid_ekf_updates=0,raw_vo_plus_one_fallback=raw.tolist(),filtered_pulse=total.tolist(),
        command_fallback_intervals=[p['t'] for p in rows if p['status']!='measured'],rows=rows,
        conclusions='16.01 cm was evaluation error, not command-axis displacement. EKF has no command prior: valid updates fuse previous visual velocity, Q and current visual velocity/R; one unknown interval uses command outside EKF. Off-diagonal gains mix yaw innovation into x.',gt_inputs=False)

if __name__=='__main__':
    result=audit();dest=Path(sys.argv[1]);data=json.dumps(result,indent=2)+'\n'
    with dest.open('x') as f:f.write(data)
    print(json.dumps({k:v for k,v in result.items() if k!='rows'},indent=2))
    for t in (107.55,107.70):print(json.dumps(next(r for r in result['rows'] if abs(r['t']-t)<1e-7),indent=2))
