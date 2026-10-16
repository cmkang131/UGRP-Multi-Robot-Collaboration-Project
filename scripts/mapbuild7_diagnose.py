"""gcp5 evaluation only: separate R3 interval residuals before any retuning."""
import argparse
from collections import defaultdict, Counter
import hashlib
import json
import math
import os
from pathlib import Path
import platform
import sys


def run(a):
    if not platform.node().startswith('ugrp-act-l4-gcp5'):raise ValueError('GCP5_ONLY')
    sys.path[:0]=[str(Path(__file__).resolve().parents[1]),str(a.vision)]
    import numpy as np
    import mujoco
    from harness.servo_camera_fk import transform_from_commands
    from harness.e2e_rgb_vo import between
    def read(p):return json.loads(p.read_text())
    def write(p,x):p.write_text(json.dumps(x,indent=2,allow_nan=False)+'\n')
    a.output.mkdir(parents=True,exist_ok=False)
    frames=read(a.input/'own.json')['frames'];pred=read(a.prediction/'trajectory.json')
    seal=read(a.prediction/'prediction-seal.json')
    for n,h in seal['prediction_sha256'].items():
        if hashlib.sha256((a.prediction/n).read_bytes()).hexdigest()!=h:raise ValueError('SEAL_CHANGED')
    gt=np.array([r['pose'] for r in read(a.input/'eval-only.json')['frames']]);commands=read(a.input/'commands.json')
    events=read(a.prediction/'events.json')
    os.chdir(a.renderer);m=mujoco.MjModel.from_xml_string((a.input/'scene.xml').read_text());d=mujoco.MjData(m)
    qs=np.load(a.input/'eval-state.npz')['qpos'];cid=m.camera('r1__robot_cam').id;bid=m.body('r1__robot').id
    camera=[];origins=[];rots=[]
    for i,q in enumerate(qs):
        d.qpos[:]=q;mujoco.mj_forward(m,d) # evaluation FK only; zero CPU integration
        servo={int(k):v for k,v in frames[i]['servo'].items()}
        # Diagnostic nominal chain has no gripper joint. Opening ONLY the
        # copied diagnostic PWM evaluates that same chain; never sent to control.
        nominal,_=transform_from_commands({**servo,1:2000},camera_pose='servo_fk_v1')
        no,nr=nominal;heading=gt[i,2];c,s=np.cos(heading),np.sin(heading)
        R=np.array([[c,-s,0],[s,c,0],[0,0,1]])
        actual_o=R.T@(d.cam_xpos[cid]-np.r_[gt[i,:2],0.])
        actual_r=R.T@d.cam_xmat[cid].reshape(3,3)@np.diag([1,-1,-1])
        angle=np.arccos(np.clip((np.trace(nr.T@actual_r)-1)/2,-1,1))
        origins.append(actual_o);rots.append(actual_r)
        camera.append(dict(t=frames[i]['t'],grip=servo[1],nominal_origin=no.tolist(),actual_origin=actual_o.tolist(),
            position_error_m=float(np.linalg.norm(no-actual_o)),rotation_error_deg=float(np.degrees(angle)),
            actual_height_m=float(actual_o[2]),nominal_height_m=float(no[2])))
    rows=[];groups=defaultdict(list)
    for i in range(1,len(frames)):
        truth=between(gt[i-1],gt[i]);delta=np.array(pred[i]['motion_delta']);res=delta-truth
        res[2]=math.atan2(math.sin(res[2]),math.cos(res[2]));status=pred[i]['lk']['status']
        servo_change=frames[i]['servo']!=frames[i-1]['servo']
        cmd_rotation=bool(abs(frames[i]['command_delta'][2])>0)
        # These are exact issued-command labels, not newly fitted thresholds.
        cause=('servo_change' if servo_change else 'loaded_FK_unqualified' if 'loaded' in status else
               'feature_rigid_consensus_failure' if status!='measured' else 'LK_measured_rotation' if cmd_rotation else 'LK_measured_translation_or_rest')
        row=dict(t=frames[i]['t'],status=status,category=cause,command_rotation=cmd_rotation,servo_change=servo_change,
            xy_residual_m=float(np.linalg.norm(res[:2])),signed_body_residual=res.tolist(),truth_delta=truth.tolist(),used_delta=delta.tolist(),
            camera_position_error_m=camera[i]['position_error_m'],camera_rotation_error_deg=camera[i]['rotation_error_deg'],
            camera_interval_origin_change_m=float(np.linalg.norm(origins[i]-origins[i-1])),
            camera_interval_rotation_deg=float(np.degrees(np.arccos(np.clip((np.trace(rots[i-1].T@rots[i])-1)/2,-1,1)))),
            tracks=pred[i]['lk'].get('tracks'),inliers=pred[i]['lk'].get('inliers'),cells=pred[i]['lk'].get('cells'),
            wall_update_reason=events[i]['reason'],blocked_object='own_camera_projection_or_command_model',minimum_gap_m=None,gap_status='not_measured')
        rows.append(row);groups[cause].append(row)
    def agg(label,rs):
        return dict(category=label,n=len(rs),xy_residual_sum_m=sum(r['xy_residual_m'] for r in rs),
            xy_residual_p95_m=float(np.percentile([r['xy_residual_m'] for r in rs],95)),
            camera_rotation_error_p50_p95_deg=np.percentile([r['camera_rotation_error_deg'] for r in rs],[50,95]).tolist(),
            camera_origin_error_p50_p95_m=np.percentile([r['camera_position_error_m'] for r in rs],[50,95]).tolist(),
            signed_body_residual_sum=np.sum([r['signed_body_residual'] for r in rs],axis=0).tolist(),
            blocked_object='own_camera_projection_or_command_model',minimum_gap_m=None,gap_status='not_measured')
    distribution=sorted([agg(k,v) for k,v in groups.items()],key=lambda x:-x['xy_residual_sum_m'])
    # Fixed one-second reporting bins: descriptive time axis, no acceptance gate.
    bins=defaultdict(list)
    for r in rows:bins[int(r['t'])].append(r)
    summary=dict(raw=str(a.input),prediction=str(a.prediction),reproduction=sys.argv,frames=len(frames),intervals=len(rows),
        distribution=distribution,time_bins=[agg(str(k),v) for k,v in sorted(bins.items())],
        largest_intervals=sorted(rows,key=lambda r:-r['xy_residual_m'])[:12],
        wall_reasons=dict(Counter(e['reason'] for e in events)),
        camera_error=dict(position_p50_p95_max_m=np.percentile([r['position_error_m'] for r in camera],[50,95,100]).tolist(),
            rotation_p50_p95_max_deg=np.percentile([r['rotation_error_deg'] for r in camera],[50,95,100]).tolist()),
        interpretation='Interval residual sums are not additive final SE2 error attribution. Evaluation camera is never estimator input.',
        parameter_tuning=0,cpu_physics_steps=0,truth_feedback=0,
        source_sha256={str(p):hashlib.sha256(p.read_bytes()).hexdigest() for p in [a.input/'own.json',a.input/'eval-state.npz',a.input/'scene.xml',a.prediction/'prediction-seal.json']})
    write(a.output/'intervals.json',rows);write(a.output/'camera-evaluation.json',camera);write(a.output/'summary.json',summary)
    write(a.output/'rejection_table.json',dict(stages=[dict(stage='recorded',cumulative_pass_n=len(frames),rejected_n=0),
        dict(stage='adjacent_intervals',cumulative_pass_n=len(rows),rejected_n=1),dict(stage='LK_measurement',cumulative_pass_n=sum(r['status']=='measured' for r in rows),rejected_n=sum(r['status']!='measured' for r in rows))],
        distribution=distribution,raw=str(a.input),reproduction=sys.argv))
    print(json.dumps({k:v for k,v in summary.items() if k not in ('time_bins','largest_intervals')}))

if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__)
    for n in ('input','prediction','vision','renderer','output'):p.add_argument('--'+n,type=Path,required=True)
    run(p.parse_args())
