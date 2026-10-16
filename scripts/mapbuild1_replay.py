"""Own-RGB-only sparse SLAM and LK replay. Evaluation labels are separate.

No static map/ground-truth parameter exists in replay(). Existing Options and
LK PARAMS remain unchanged; raw counts/errors are reported without fitting a
success threshold to these cases. cap_end denotes the finite input ending.
"""
from __future__ import annotations
import argparse
from collections import Counter
import hashlib
import json
from pathlib import Path
import sys
import cv2
import numpy as np
from harness.natural_floor_slam import NaturalFloorSLAM, extract
from harness.e2e_rgb_vo import ground_pair, compose, PARAMS


def dump(path,value):
    path.write_text(json.dumps(value,indent=2,allow_nan=False)+'\n')


def percentiles(values):
    x=np.asarray(values,float)
    return dict(n=len(x),p50=float(np.median(x)),p95=float(np.percentile(x,95)),max=float(x.max())) if len(x) else dict(n=0,p50=None,p95=None,max=None)


def read_frame(root,row):
    allowed={'sequence','robot_id','frame_id','t','rgb','sha256','servo','command_delta','command_covariance'}
    if set(row)!=allowed: raise ValueError('STRICT_OWN_RECORD_FIELDS_REQUIRED')
    path=(root/row['rgb']).resolve()
    if not path.is_relative_to(root.resolve()): raise ValueError('RGB_PATH_ESCAPE')
    raw=path.read_bytes()
    if hashlib.sha256(raw).hexdigest()!=row['sha256']:raise ValueError('RGB_HASH_MISMATCH')
    bgr=cv2.imdecode(np.frombuffer(raw,np.uint8),cv2.IMREAD_COLOR)
    if bgr is None or bgr.shape!=(480,640,3):raise ValueError('VGA_RGB_REQUIRED')
    return cv2.cvtColor(bgr,cv2.COLOR_BGR2RGB)


def replay(root,manifest):
    """Only the restricted manifest is consumed here; labels are not opened."""
    if manifest['schema']!='ugrp.mapbuild1.own.v1' or manifest['backend']!='mjwarp_render':
        raise ValueError('MJWARP_OWN_MANIFEST_REQUIRED')
    grouped={}
    for row in manifest['frames']:grouped.setdefault(row['sequence'],[]).append(row)
    output=[]
    for name,frames in sorted(grouped.items()):
        slam=NaturalFloorSLAM(frames[0]['robot_id'])
        before=None; previous_t=None; lkpose=np.zeros(3); previous_servo=None
        for row in frames:
            rgb=read_frame(root,row); servo={int(k):int(v) for k,v in row['servo'].items()}
            if previous_t is not None and row['t']<=previous_t:raise ValueError('CAUSAL_FRAMES_REQUIRED')
            observation=extract(rgb,servo,frame_id=row['frame_id'],t=row['t'],sha256=row['sha256'])
            event=slam.step(observation,command_delta=row['command_delta'],command_covariance=row['command_covariance'])
            if before is None:lk=dict(status='bootstrap',tracks=0,inliers=0,cells=0)
            elif servo!=previous_servo:lk=dict(status='unknown_servo_change',tracks=0,inliers=0,cells=0)
            elif row['t']-previous_t>PARAMS['max_pair_gap_s']:lk=dict(status='unknown_stale',tracks=0,inliers=0,cells=0)
            else:lk=ground_pair(before,rgb,servo)  # default off map mask; no surveyed walls
            lkpose=compose(lkpose,lk['delta'] if lk['status']=='measured' else row['command_delta'])
            output.append(dict(sequence=name,frame_id=row['frame_id'],t=row['t'],rgb=row['rgb'],
                slam=event,lk=lk,lk_pose=lkpose.tolist(),
                rejection=dict(category='visual_tracking',reason=event['reason'],blocked_object='not_observed',
                    minimum_gap_m=None,gap_status='not_measured')))
            before=rgb;previous_t=row['t'];previous_servo=servo
    return output


def score(rows,labels):
    """Evaluation-only first-origin SE(2), no optimized scale or pose correction."""
    truth={(r['sequence'],r['frame_id']):np.asarray(r['pose'],float) for r in labels['frames']}
    if len(truth)!=len(labels['frames']):raise ValueError('DUPLICATE_EVALUATION_LABEL')
    if {(r['sequence'],r['frame_id']) for r in rows}!=set(truth):raise ValueError('EXACT_EVALUATION_LABEL_COVERAGE_REQUIRED')
    by={}
    for r in rows:by.setdefault(r['sequence'],[]).append(r)
    results=[]
    for name,seq in sorted(by.items()):
        targets=np.array([truth[(name,r['frame_id'])] for r in seq])
        if not np.array_equal(targets[0],np.zeros(3)):raise ValueError('FIRST_ORIGIN_LABEL_REQUIRED')
        for method in ('slam','lk'):
            poses=np.array([r['slam']['pose'] if method=='slam' else r['lk_pose'] for r in seq])
            status=[r['slam']['status'] if method=='slam' else r['lk']['status'] for r in seq]
            good=np.array([s in ('visual_update','visual_relocalized') if method=='slam' else s=='measured' for s in status[1:]])
            # Pose and incremental error include unknown intervals. Visual-only
            # errors are also exposed so coverage cannot hide behind fallback.
            diff=poses-targets;diff[:,2]=np.arctan2(np.sin(diff[:,2]),np.cos(diff[:,2]))
            steps=np.diff(poses,axis=0);ts=np.diff(targets,axis=0)
            step_error=steps-ts;step_error[:,2]=np.arctan2(np.sin(step_error[:,2]),np.cos(step_error[:,2]))
            td=np.linalg.norm(ts[:,:2],axis=1); pd=np.linalg.norm(steps[:,:2],axis=1)
            runs=[];length=0
            for yes in good:
                length=length+1 if yes else 0;runs.append(length)
            results.append(dict(sequence=name,method=method,tracked_n=int(good.sum()),pairs=len(good),
                longest_tracked_pairs=max(runs,default=0),status_counts=dict(Counter(status)),
                ate_xy_m=percentiles(np.linalg.norm(diff[:,:2],axis=1)),
                ate_yaw_deg=percentiles(abs(np.degrees(diff[:,2]))),
                rpe_xy_m=percentiles(np.linalg.norm(step_error[:,:2],axis=1)),
                visual_rpe_xy_m=percentiles(np.linalg.norm(step_error[good,:2],axis=1)),
                translation_scale_ratio=percentiles(pd[td>0]/td[td>0]),
                loop_xy_m=float(np.linalg.norm(diff[-1,:2])),termination='cap_end'))
    return results


def main():
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('--input',type=Path,required=True);p.add_argument('--output',type=Path,required=True)
    p.add_argument('--evaluation-labels',type=Path,required=True)
    p.add_argument('--mapbuild1-v1',action='store_true');a=p.parse_args()
    if not a.mapbuild1_v1:p.error('default off; --mapbuild1-v1 required')
    cv2.setNumThreads(1);a.output.mkdir(parents=True,exist_ok=False)
    manifest=json.loads((a.input/'own.json').read_text())
    rows=replay(a.input,manifest)
    dump(a.output/'trajectory.json',rows)
    # Open labels only after the actor output is committed to disk.
    metrics=score(rows,json.loads(a.evaluation_labels.read_text()))
    dump(a.output/'summary.json',dict(scope=manifest['scope'],status='MEASURED_NOT_ADMITTED',
        results=metrics,runtime_inputs=['own_rgb','fixed_camera_calibration','fixture_pwm_specification','zero_wheel_prior'],
        command_scale_measured=False,physical_driving_measured=False,
        input_sha256=hashlib.sha256((a.input/'own.json').read_bytes()).hexdigest()))
    pairs=[r for r in rows if r['frame_id']!=0]
    features=[r for r in pairs if r['slam']['features']>=NaturalFloorSLAM('r1').options.min_matches]
    tracked=[r for r in features if r['slam']['status'] in ('visual_update','visual_relocalized')]
    stages=[('pairs',len(pairs)),('orb_feature_support',len(features)),('orb_rigid_tracking',len(tracked))]
    previous=len(pairs);funnel=[]
    for stage,n in stages:funnel.append(dict(stage=stage,cumulative_pass_n=n,rejected_n=previous-n));previous=n
    distribution=Counter(r['slam']['reason'] for r in pairs if r['slam']['status']=='command_only')
    dump(a.output/'rejection-table.json',dict(stages=funnel,reasons=dict(distribution),
        raw=str(a.input.resolve()),reproduction=sys.argv,
        rejection_fields='trajectory.json: category/reason/blocked_object/minimum_gap_m/gap_status'))
    dump(a.output/'SHA256SUMS.json',{p.name:hashlib.sha256(p.read_bytes()).hexdigest() for p in a.output.iterdir() if p.is_file()})
    print(json.dumps(dict(results=metrics,reasons=dict(distribution))))


if __name__=='__main__':main()
