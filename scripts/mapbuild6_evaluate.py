"""Sealed predictions -> chassis SE(2) task scores; never called by control."""
import argparse
from collections import Counter
import hashlib
import json
import math
from pathlib import Path
import platform
import sys


def sha(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def dump(path,value):
    path.write_text(json.dumps(value,indent=2,ensure_ascii=False,allow_nan=False)+'\n')


def relative_trajectory(world):
    """One SE(2) alignment only; distances are never rescaled."""
    import numpy as np
    p=np.asarray(world,float);dx=p[:,:2]-p[0,:2];c,s=np.cos(p[0,2]),np.sin(p[0,2])
    xy=dx@np.array([[c,-s],[s,c]])
    yaw=np.arctan2(np.sin(p[:,2]-p[0,2]),np.cos(p[:,2]-p[0,2]))
    return np.column_stack((xy,yaw))


def errors(prediction,truth):
    import numpy as np
    error=np.asarray(prediction)-np.asarray(truth)
    error[:,2]=np.arctan2(np.sin(error[:,2]),np.cos(error[:,2]))
    return np.linalg.norm(error[:,:2],axis=1),np.abs(error[:,2])


def run(a):
    if not platform.node().startswith('ugrp-act-l4-gcp5'):raise ValueError('GCP5_ONLY')
    import numpy as np
    seal=json.loads((a.prediction/'prediction-seal.json').read_text())
    for path,h in seal['input_sha256'].items():
        if sha(path)!=h:raise ValueError('SEALED_INPUT_CHANGED')
    for name,h in seal['prediction_sha256'].items():
        if sha(a.prediction/name)!=h:raise ValueError('SEALED_PREDICTION_CHANGED')
    a.output.mkdir(parents=True,exist_ok=False)
    rows=json.loads((a.prediction/'trajectory.json').read_text());evals=json.loads((a.input/'eval-only.json').read_text())['frames']
    if [r['frame_id'] for r in rows]!=[r['frame_id'] for r in evals]:raise ValueError('EXACT_FRAME_COVERAGE_REQUIRED')
    req=json.loads(a.requirements.read_text());world=np.array([r['pose'] for r in evals]);gt=relative_trajectory(world)
    distance=np.r_[0,np.cumsum(np.linalg.norm(np.diff(gt[:,:2],axis=0),axis=1))]
    per_method={};error_arrays={}
    for method in ('lk','rbpf'):
        p=np.array([r[method+'_pose'] for r in rows]);xy,yaw=errors(p,gt);error_arrays[method]=(xy,yaw)
        # Camera values are reference-only nominal FK. They never replace the
        # chassis SE2 metric, and no scale fit is performed in either column.
        per_method[method]=dict(ate_xy_rmse_m=float(np.sqrt(np.mean(xy**2))),xy_p95_m=float(np.percentile(xy,95)),
            maximum_xy_m=float(xy.max()),maximum_xy_t=float(rows[int(xy.argmax())]['t']),
            final_xy_m=float(xy[-1]),yaw_rmse_deg=float(np.degrees(np.sqrt(np.mean(yaw**2)))),
            maximum_yaw_deg=float(np.degrees(yaw.max())),final_yaw_deg=float(np.degrees(yaw[-1])),
            final_drift_percent=float(100*xy[-1]/distance[-1]) if distance[-1]>0 else None,
            maximum_xy_over_total_distance_percent=float(100*xy.max()/distance[-1]) if distance[-1]>0 else None)
    events=json.loads((a.input/'events.json').read_text());checkpoints=[]
    for event in events:
        index=min(range(len(rows)),key=lambda k:abs(rows[k]['t']-event['t']))
        methods={}
        for method,(xy,yaw) in error_arrays.items():
            facing=float(yaw[index]+math.atan2(xy[index],req['handoff']['nominal_target_range_m']-xy[index]))
            methods[method]=dict(xy_m=float(xy[index]),yaw_deg=float(np.degrees(yaw[index])),
                cumulative_distance_m=float(distance[index]),
                drift_percent=float(100*xy[index]/distance[index]) if distance[index]>0 else None,
                handoff_budget_pass=bool(xy[index]<=req['handoff']['position_error_m'] and facing<=req['handoff']['yaw_error_rad']),
                slot_center_budget_pass=bool(xy[index]<=req['arrival']['slot_center_error_m']))
        checkpoints.append(dict(**event,index=index,methods=methods))
    static=json.loads((a.input/'static-map.json').read_text());crossings=[]
    for passage in static['passages']:
        if passage.get('kind') not in ('door','corridor'):continue
        axis=0 if passage.get('axis')=='x' else 1;normal=1-axis;center=np.asarray(passage['center_m'])
        cross=np.flatnonzero((world[:-1,axis]-center[axis])*(world[1:,axis]-center[axis])<=0)+1
        for k in cross:
            if world[k-1,axis]==world[k,axis] or abs(world[k,normal]-center[normal])>passage['width_m']/2:continue
            methods={}
            for method,(xy,yaw) in error_arrays.items():
                support=req['passage']['robot_half_length_m']*abs(math.sin(yaw[k]))+req['passage']['robot_half_width_m']*abs(math.cos(yaw[k]))
                methods[method]=dict(xy_m=float(xy[k]),yaw_deg=float(np.degrees(yaw[k])),
                    chassis_error_plus_halfwidth_m=float(xy[k]+support),
                    chassis_budget_pass=bool(xy[k]+support<=passage['width_m']/2),
                    arm_and_held_pass=None,arm_and_held_status='requires separate physical footprint assessment; never inferred from centre')
            crossings.append(dict(passage=passage['id'],t=rows[k]['t'],width_m=passage['width_m'],methods=methods))
    motion=Counter(r['lk']['status'] for r in rows);largest=Counter()
    for k,row in enumerate(rows):
        if row['lk']['status'] not in ('bootstrap','measured'):largest[row['lk']['status']]+=1
    missing=[]
    if not any(e['event']=='estimated_zone_arrival' for e in events):missing.append('zone_arrival')
    if not crossings:missing.append('door_or_corridor_crossing')
    if not any(e['event']=='post_setdown_lookaround_end' for e in events):missing.append('post_setdown_lookaround')
    if not any(e['event']=='estimated_return_arrival' for e in events):missing.append('return')
    # A command prefix starts near cargo; it has no upstream map->ACT transfer.
    missing.append('map_to_ACT_handoff_after_navigation')
    missing.append('independent_full_cargo_transport_recount')
    result=dict(status='NOT_READY',decision='no default adoption; required actual-route gates missing' if missing else 'requires_physical_recount',
        missing_required_evidence=missing,reference='chassis centre SE2; start-only alignment; scale=1',
        measured_path_m=float(distance[-1]),frames=len(rows),sim_s=rows[-1]['t'],methods=per_method,
        checkpoints=checkpoints,passage_crossings=crossings,motion_status_counts=dict(motion),
        rejection_distribution=[dict(category='motion_observation',reason=k,count=v,blocked_object='own_camera_support',
            minimum_gap_m=None,gap_status='not_measured') for k,v in largest.most_common()],
        cause_status='counts are symptoms; inspect >=6 own frames and playback before assigning cause',
        requirements_sha256=sha(a.requirements),prediction_seal_sha256=sha(a.prediction/'prediction-seal.json'),
        raw=dict(recording=str(a.input),prediction=str(a.prediction)),reproduction=sys.argv,
        truth_inputs_to_control=0,scale_fitting=0,parameter_tuning=0)
    dump(a.output/'summary.json',result)
    dump(a.output/'frame-errors.json',[dict(t=r['t'],path_m=float(distance[k]),
        methods={m:dict(xy_m=float(v[0][k]),yaw_rad=float(v[1][k])) for m,v in error_arrays.items()}) for k,r in enumerate(rows)])
    print(json.dumps({k:result[k] for k in ('status','decision','missing_required_evidence','measured_path_m','frames','methods','motion_status_counts')}))


if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__)
    for name in ('input','prediction','requirements','output'):p.add_argument('--'+name,type=Path,required=True)
    run(p.parse_args())
