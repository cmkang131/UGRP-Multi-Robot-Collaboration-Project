"""Post-replay layer decomposition only; never used by the controller."""
import json,sys
from pathlib import Path
import numpy as np
from harness.zone_solo_cyan_flow_fusion import compose


def analyze(out):
    r=json.loads((out/'replay-candidate.json').read_text())
    s=json.loads((out/'scoring-v2/summary.json').read_text())
    pe=json.loads((out/'scoring-v2/pitch-scale-eval.json').read_text())
    geom={round(x['t'],6):x for x in pe['intervals']};decomp=[]
    for row in r['visual_odometry']['rows']:
        if round(row['t'],2) not in [x['t'] for x in s['six']]:continue
        a=np.zeros(3);b=np.zeros(3);ekf=np.zeros(3);nuisance=[]
        for i in row['intervals']:
            measured=i['status']=='measured'
            delta=i['delta'] if measured else i['estimate_delta']
            truth_geometry=geom[round(i['t'],6)]['eval_camera_delta'] if measured else i['estimate_delta']
            a=compose(a,np.array(delta));b=compose(b,np.array(truth_geometry));ekf=compose(ekf,np.array(i['estimate_delta']))
            if measured:nuisance.append(dict(t=i['t'],raw=i['delta'],filtered=i['estimate_delta'],
                sigma_m=float(np.sqrt(np.trace(np.array(i['covariance'])[:2,:2])))))
        truth=np.array(next(x['actual_delta'] for x in s['six'] if x['t']==row['t']))
        decomp.append(dict(t=row['t'],raw_integrated=a.tolist(),actual_geometry_integrated=b.tolist(),
            ekf_integrated=ekf.tolist(),truth=truth.tolist(),raw_error_cm=float(np.linalg.norm(a[:2]-truth[:2])*100),
            actual_geometry_error_cm=float(np.linalg.norm(b[:2]-truth[:2])*100),ekf_error_cm=float(np.linalg.norm(ekf[:2]-truth[:2])*100),intervals=nuisance))
    return dict(scope='evaluation only; no new candidate or tuning; same accepted pairs and fallback intervals',six=decomp)

if __name__=='__main__':
    out=Path(sys.argv[1]);result=analyze(out)
    assert result==json.loads((out/'estimator-layer-eval.json').read_text())
    print('Saved layer decomposition reproduced exactly; six pulses; no control/physics')
