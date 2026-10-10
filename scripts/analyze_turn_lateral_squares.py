"""Heldout square closure audit only; truth never enters runtime calibration."""
import argparse
import hashlib
import json
import math
from pathlib import Path
import numpy as np
from harness.self_pulse_rotation import RotationPulseOdometry,calibrated_model
from harness.turn_lateral_calibration import apply_model
from scripts.run_turn_lateral_calibration import SEEDS,schedule
from scripts.run_own_route_references import rows


def model_displacement(commands,start_tick,end_tick,model):
    d=RotationPulseOdometry(start_tick/20);d.profiles=model['profiles']
    for tick,command in sorted(commands.items()):
        if start_tick<=tick<end_tick:d.command(dict(t=tick/20,**command))
    d.advance(end_tick/20)
    return np.asarray(d.pose)


def evaluate(folder):
    calibration=json.loads((folder/'calibration.json').read_text())
    models={'off':calibrated_model(),'on':apply_model(calibration)};result=[]
    for seed in SEEDS:
        root=folder/f'cal-{seed}';receipt=json.loads((root/'result.json').read_text())
        data={round(r['t'],6):r for r in rows(root/'eval_only/trajectory.jsonl')}
        blocks,commands,_=schedule(seed)
        for sign in (1,-1):
            ix=[i for i,b in enumerate(blocks) if b['kind']=='square' and b['axis']=='turn' and b['sign']==sign]
            lo=blocks[ix[0]-1]['start_tick'];hi=blocks[ix[-1]]['end_tick']
            a=data[round(receipt['start_sim_s']+lo/20,6)];b=data[round(receipt['start_sim_s']+hi/20,6)]
            yaw=a['robot_yaw_rad'];c,s=math.cos(yaw),math.sin(yaw)
            actual=np.array([[c,s],[-s,c]])@(np.asarray(b['robot_xyz_m'][:2])-a['robot_xyz_m'][:2])
            predictions={k:model_displacement(commands,lo,hi,v).tolist() for k,v in models.items()}
            result.append(dict(seed=seed,split='fit' if seed in SEEDS[:3] else 'check',direction=sign,
                pulses=sum(lo<=t<hi for t in commands),actual_closure_xy_m=actual.tolist(),predictions=predictions,
                endpoint_error_m={k:float(np.linalg.norm(np.asarray(v)[:2]-actual)) for k,v in predictions.items()}))
    return dict(gt_evaluation_only=True,fit_uses_squares=False,rows=result,
        calibration_sha256=hashlib.sha256((folder/'calibration.json').read_bytes()).hexdigest())


if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('folder',type=Path);a=p.parse_args()
    (a.folder/'square-closure.json').write_text(json.dumps(evaluate(a.folder),indent=2)+'\n')
