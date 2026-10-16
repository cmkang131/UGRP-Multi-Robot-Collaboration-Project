"""Evaluation-only paired prefix, because physical failures shorten exposure."""
import json
import math
from pathlib import Path
import sys
import numpy as np
from scripts.evaluate_egomap_covariance import lines
from scripts.evaluate_ego_pose_continuity import jump_metrics


def score(group):
    table=[]
    for folder in sorted((Path(group)/'data').iterdir()):
        if not (folder/'RUN_META.json').exists():continue
        own,own_receipt=lines(folder/'data/own-controller.jsonl')
        truth,truth_receipt=lines(folder/'data/eval_only/trajectory.jsonl')
        if not own or not truth:raise ValueError('PAIRED_TRAJECTORIES_REQUIRED')
        table.append((folder,own,truth,[own_receipt,truth_receipt]))
    if len(table)!=3:raise ValueError('ALL_THREE_CONDITIONS_REQUIRED')
    horizon=min(own[-1]['t']-own[0]['t'] for _,own,_,_ in table)
    reports=[]
    for folder,own,truth,receipts in table:
        selected=[r for r in own if r['t']-own[0]['t']<=horizon+1e-8]
        by_t={round(t['t'],6):t for t in truth}
        origin=np.asarray(truth[0]['robot_xyz_m'][:2]);angle=truth[0]['robot_yaw_rad']
        R=np.array([[math.cos(angle),-math.sin(angle)],[math.sin(angle),math.cos(angle)]])
        target=np.asarray([R.T@(np.asarray(by_t[round(r['t'],6)]['robot_xyz_m'][:2])-origin) for r in selected])
        poses=np.asarray([r['local_pose'] for r in selected])
        control=[r.get('pose_continuity',{}).get('control_pose',r['local_pose']) for r in selected]
        errors=np.sum((poses[:,:2]-target)**2,axis=1)
        reports.append(dict(condition=folder.name.split('-',1)[1],frames=len(selected),
            squared_error_sum_m2=float(errors.sum()),rmse_m=float(np.sqrt(errors.mean())),
            final_error_m=float(np.sqrt(errors[-1])),map_jumps=jump_metrics(poses),
            control_jumps=jump_metrics(control),sources=receipts))
    return dict(scope='same elapsed own-camera prefix; distinct policy trajectories, not identical commands',
        horizon_s=horizon,evaluation_truth_control_input=False,runs=reports)


if __name__=='__main__':print(json.dumps(score(sys.argv[1]),allow_nan=False))
