"""Post-save paired camera-centre ATE for MASt3R, LK and RBPF.

All inference and allowed-input scale must already be sealed. Truth is used
only here. Baseline frame_id/t/lk_pose/rbpf_pose are mapbuild5 saved outputs.
Truth contract: frames with frame_id,t,camera_xyz_m. No interpolation or fill.
"""
import argparse
import json
from pathlib import Path

import numpy as np

from mast3rcmp_evaluate import align, digest


def body_to_camera(poses,origin):
    poses=np.asarray(poses,float);origin=np.asarray(origin,float)
    c,s=np.cos(poses[:,2]),np.sin(poses[:,2])
    return np.column_stack((poses[:,0]+c*origin[0]-s*origin[1],
                            poses[:,1]+s*origin[0]+c*origin[1],
                            np.full(len(poses),origin[2])))


def compare(trajectory,scale,baseline,truth,calibration,output):
    # Never used by the estimator. Frozen scale is opened before truth.
    ml=json.loads(Path(trajectory).read_text())['frames']
    frozen=json.loads(Path(scale).read_text())
    if frozen.get('truth_reads')!=0:
        raise ValueError('allowed_scale_provenance_required')
    base=json.loads(Path(baseline).read_text())
    cal=json.loads(Path(calibration).read_text())
    gt=json.loads(Path(truth).read_text())['frames']
    n=len(ml)
    if len(base)!=n or len(gt)!=n:
        raise ValueError('full_denominator_mismatch')
    for i,(a,b,c) in enumerate(zip(ml,base,gt)):
        if a['index']!=i or b['frame_id']!=i or c['frame_id']!=i or a['t_sim_s']!=b['t'] or a['t_sim_s']!=c['t']:
            raise ValueError('exact_frame_time_association_required')
    common=np.asarray([i for i,a in enumerate(ml) if a['success']],int)
    actual=np.asarray([g['camera_xyz_m'] for g in gt],float)
    camera_origin=cal['camera_origin_body_m']
    rows=[]
    for method in ('mast3r','lk','rbpf'):
        if method=='mast3r':
            x=np.asarray([ml[i]['pose_sim3_final'][:3] for i in common])
            metric_scale=frozen['scale']
            measured=sum(a['status']=='tracked' for a in ml)
            failure=sum(not a['success'] for a in ml)
            row=dict(method=method,all_frames=n,pose_available=len(common),tracking_failed=failure,
                initialized=sum(a['status']=='initialized' for a in ml),tracked=measured,
                allowed_inputs='own RGB + fixed K/D; metric scale from fixed camera/floor + own RGB',
                inference_host='gcp4')
        else:
            all_camera=body_to_camera([r[method+'_pose'] for r in base],camera_origin)
            x=all_camera[common];metric_scale=1.
            row=dict(method=method,all_frames=n,pose_available=n,
                lk_measured=sum(r['lk']['status']=='measured' for r in base),
                command_prediction=sum(r['motion_source']=='command_prediction' for r in base),
                allowed_inputs='own RGB + issued commands + fixed calibration',inference_host='gcp5',
                camera_lift='nominal fixed body-to-camera; baseline roll/pitch/height are not estimated')
            try:row['all_available_metric_se3']=align(all_camera,actual,False)
            except ValueError as e:row['all_available_metric_se3']=dict(status='unobservable',reason=str(e))
        for name,factor,fit_scale in [('sim3_truth_scale_reference',1.,True),('se3_allowed_scale',metric_scale,False)]:
            try:row[name]=align(x*factor,actual[common],fit_scale)
            except ValueError as e:row[name]=dict(status='unobservable',reason=str(e))
        row.update(paired_ate_frames=len(common),not_in_paired_ate=n-len(common))
        rows.append(row)
    result=dict(full_denominator=n,paired_indices=common.tolist(),methods=rows,
        evaluation_location='camera centre; same saved frame indices for both paired ATE columns',
        truth_reference='actual saved camera centres, not nominal camera centres inferred from body GT',
        truth_opened_after_saved_estimation=True,pooled_results=False,
        hashes={name:digest(path) for name,path in dict(trajectory=trajectory,scale=scale,baseline=baseline,truth=truth,calibration=calibration).items()})
    with Path(output).open('x') as f:f.write(json.dumps(result,indent=2)+'\n')
    return result


if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__)
    for name in ('trajectory','scale','baseline','truth','calibration','output'):p.add_argument('--'+name,required=True)
    a=p.parse_args();print(json.dumps(compare(a.trajectory,a.scale,a.baseline,a.truth,a.calibration,a.output),indent=2))
