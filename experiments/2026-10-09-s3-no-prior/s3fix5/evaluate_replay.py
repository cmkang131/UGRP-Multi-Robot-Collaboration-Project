"""Score sealed predictions against GT after controller replay exits."""
import argparse
import hashlib
import json
from pathlib import Path
import numpy as np


def read(p):return json.loads(p.read_text())


def evaluate(raw,off,on):
    original=read(raw/'student_record.json')['localizers']['r2']['poses']
    truth=[json.loads(s) for s in (raw/'eval_only/r2/trajectory.jsonl').read_text().splitlines()]
    ts=[r['t'] for r in truth];xy=np.array([r['robot_xyz_m'][:2] for r in truth]);yaw=np.unwrap([r['robot_yaw_rad'] for r in truth])
    result={}
    for label,path in [('off',off),('on',on)]:
        receipt=read(path/'result.json');poses=read(path/'state.json')['r2']['poses']
        if receipt['error'] is not None or len(poses)!=len(original):
            raise ValueError('incomplete replay '+label)
        prediction_sha=hashlib.sha256((path/'state.json').read_bytes()).hexdigest()
        if label=='off':
            # Record extensions are compared too: no tolerance or dropped keys.
            assert poses==original,'baseline does not reproduce original pose records'
        active=[p for p in poses if p['t_est']>=13.34-1e-8]
        at=np.array([p['t_est'] for p in active]);actual=np.array([np.interp(at,ts,xy[:,j]) for j in range(2)]).T
        est=np.array([[p['x'],p['y']] for p in active]);error=np.linalg.norm(est-actual,axis=1)
        sigma=np.array([p['std_xy_m'] for p in active]);ye=np.array([p['yaw'] for p in active])-np.interp(at,ts,yaw)
        ye=abs((ye+np.pi)%(2*np.pi)-np.pi)
        result[label]=dict(source=str(path),prediction_sha256=prediction_sha,frames=len(poses),evaluated_frames=len(active),
            final_error_m=float(error[-1]),final_sigma_m=float(sigma[-1]),final_error_over_sigma=float(error[-1]/sigma[-1]),
            xy_rmse_m=float(np.sqrt((error**2).mean())),over_3sigma=int(sum(error>3*sigma)),
            over_3sigma_fraction=float(np.mean(error>3*sigma)),final_yaw_error_deg=float(np.rad2deg(ye[-1])),
            correct_certificates=int(sum(e<=.25 and y<=np.deg2rad(15) and p['convergence_certificate']['qualified'] for p,e,y in zip(active,error,ye))),
            false_certificates=int(sum((e>.25 or y>np.deg2rad(15)) and p['convergence_certificate']['qualified'] for p,e,y in zip(active,error,ye))))
    cal=read(Path(__file__).with_name('calibration-check.json'))
    gate=all(r['xy_rmse_after']<r['xy_rmse_before'] for r in cal.values()) and result['on']['final_error_m']<=result['off']['final_error_m'] and result['on']['over_3sigma_fraction']<=result['off']['over_3sigma_fraction']
    return dict(gt_evaluation_only=True,baseline_pose_records_exact=True,table=result,smoke_option='rotation_xy_alpha_v1' if gate else 'off',
        selection_rule='preregistered calibration XY RMSE lower; final r2 error and >3sigma fraction not worse; no posthoc tuning')


if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('--raw',type=Path,required=True);p.add_argument('--off',type=Path,required=True)
    p.add_argument('--on',type=Path,required=True);p.add_argument('--output',type=Path,required=True);a=p.parse_args()
    result=evaluate(a.raw,a.off,a.on)
    with a.output.open('x') as f:f.write(json.dumps(result,indent=2,allow_nan=False)+'\n')
    print(json.dumps(result,indent=2))
