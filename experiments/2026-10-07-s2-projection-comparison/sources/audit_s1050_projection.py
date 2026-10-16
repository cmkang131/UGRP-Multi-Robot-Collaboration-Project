"""Evaluation ONLY: fixed S2 projection vs saved actual camera on same pixels.

No simulator construction/step; no estimator action or calibration mutation.
"""
import hashlib,json,math,sys
from pathlib import Path
from types import SimpleNamespace as NS
import cv2
import numpy as np
sys.path.insert(0,str(Path(__file__).resolve().parent))
import analyze_visibility as geo
from harness import zone_solo_cyan_contract_v106 as c,vision_loc_protocol as vp
from harness.zone_solo_cyan_real_carry_dev import approximate
from harness.zone_solo_cyan_real_carry import at_carry
from harness.zone_final_pair_camera import floor_camera
from harness.vision_pose_source_final import measured_column_model
from harness.opencv_wall_observation import observations
from harness.zone_pair_highpose_contract import own_image_gates

RAW=Path('/Users/changmin/projects/ugrp/outputs/s2-realism-97fcb5d2-s1050-P1-2-place')


def summary(v):
    v=np.asarray(v,float);v=v[np.isfinite(v)]
    return dict(n=len(v),median=float(np.median(v)) if len(v) else None,
        p10=float(np.quantile(v,.1)) if len(v) else None,p90=float(np.quantile(v,.9)) if len(v) else None,
        rmse=float(np.sqrt(np.mean(v*v))) if len(v) else None)


def project(cm,rows):
    points=cm.floor_point(cm.t_of_row(rows))
    opt=(np.c_[points,np.zeros(len(points))]-cm.origin)@cm._rot
    valid=np.isfinite(points).all(1)&(opt[:,2]>0)
    return points,valid


def main(out):
    assert not out.exists()
    lines=lambda p:[json.loads(x) for x in (RAW/p).read_text().splitlines()]
    frames=lines('robots/r3/frames.jsonl');truth={round(r['t'],6):r for r in lines('eval_only/trajectory.jsonl')}
    cameras={round(r['t'],6):r for r in lines('eval_only/camera-pose.jsonl')}
    result=json.loads((RAW/'result.json').read_text());lo,hi=result['posthoc_evaluation']['carry_window']
    table=json.loads((c.ROOT/'configs/calibration/s2_camera_v3_unloaded_sag_v1.json').read_text())
    models=approximate(table);static=c.hp.resolve(c.MAP_ID)[0];segments=geo.wall_segments(static)
    vl=vp.load_vis3()[0];gates=own_image_gates()['values'];columns=np.linspace(8,631,96).astype(int)
    ft=np.array([f['sim_time'] for f in frames]);ids=sorted(set(int(np.argmin(abs(ft-t))) for t in np.arange(math.ceil(lo),hi,1.)))
    rows=[];allcols=[];pitches=[];heights=[];origin_delta=[]
    for i in ids:
        f=frames[i];t=f['sim_time'];servo={int(k):v for k,v in f['commanded_servo'].items()}
        if not at_carry(servo):continue
        g=truth[round(t,6)];a=cameras[round(t,6)];r=geo.rz(g['robot_yaw_rad']);base=np.r_[g['robot_xyz_m'][:2],0.]
        actual=NS(origin=r.T@(np.array(a['camera_cached_xyz_m'])-base),
            _rot=r.T@np.array(a['camera_cached_optical_rotation']),columns=columns)
        actual_cm=measured_column_model(vl.mp,dict(origin_m=actual.origin,rotation=actual._rot),columns)
        key=','.join(str(servo[k]) for k in (3,4,5,6))
        fixed_cm=measured_column_model(vl.mp,floor_camera(models['loaded'][key]),columns)
        pose=np.r_[g['robot_xyz_m'][:2],g['robot_yaw_rad']]
        true_rows,true_points,depth=geo.bottom_projection(actual,pose,segments)
        inside=np.isfinite(true_rows)&(true_rows>=4)&(true_rows<=470)
        rays=geo.pixel_rays(actual,columns,np.nan_to_num(true_rows))
        body=geo.shadow_depths(actual.origin,rays,geo.robot_boxes(servo,actual))
        cargo=geo.box_depth(actual.origin,rays,r.T@(np.array(g['cyan_xyz_m'])-base),
            r.T@np.array(g['cyan_rotation']).reshape(3,3),np.array(g['box_half_m']))
        layers=np.stack([cargo,*body.values(),geo.wall_depths(actual,pose,rays,static)])
        clear=inside&(layers.min(0)>=depth-1e-6)
        data=(RAW/f['path']).read_bytes();assert hashlib.sha256(data).hexdigest()==f['sha256']
        # The actual runtime detector sees the fixed calibration, never GT.
        obs=observations(vl,cv2.imdecode(np.frombuffer(data,np.uint8),1),fixed_cm,gates)
        det=obs.b_kind==vl.EDGE
        pred,valid=project(fixed_cm,obs.b_lo);oracle,oracle_valid=project(actual_cm,obs.b_lo)
        true_fixed,tfvalid=project(fixed_cm,true_rows);true_actual,tavalid=project(actual_cm,true_rows)
        world=pred@r[:2,:2].T+base[:2]
        # Nearest static floor-wall segment metric, independent of association.
        x=segments[:,:,:2];seg=x[:,1]-x[:,0]
        u=((world[:,None,:]-x[None,:,0,:])*seg[None]).sum(2)/(seg*seg).sum(1)
        nearest=x[None,:,0,:]+np.clip(u,0,1)[:,:,None]*seg[None]
        nearest_error=np.linalg.norm(world[:,None,:]-nearest,axis=2).min(1)
        pitch_delta=float(np.degrees(np.arcsin(fixed_cm._rot[2,2])-np.arcsin(actual._rot[2,2])))
        pitches.append(pitch_delta);heights.append(float(fixed_cm.origin[2]-actual.origin[2]))
        origin_delta.append(float(np.linalg.norm(fixed_cm.origin-actual.origin)))
        good=det&clear&valid&oracle_valid&tfvalid&tavalid
        total=np.linalg.norm(pred-true_points[:,:2],axis=1)
        pixel=np.linalg.norm(oracle-true_points[:,:2],axis=1)
        calibration=np.linalg.norm(true_fixed-true_points[:,:2],axis=1)
        consistency=np.linalg.norm(true_actual-true_points[:,:2],axis=1)
        signed_range=np.linalg.norm(pred,axis=1)-np.linalg.norm(true_points[:,:2],axis=1)
        frame=[]
        for j in np.where(det)[0]:
            q=dict(t=t,column=int(columns[j]),true_clear=bool(clear[j]),valid=bool(valid[j]),
                compared=bool(good[j]),pixel_residual_px=float(obs.b_lo[j]-true_rows[j]) if clear[j] else None,
                nearest_wall_error_m=float(nearest_error[j]) if valid[j] else None)
            if good[j]:q.update(total_endpoint_error_m=float(total[j]),pixel_only_error_m=float(pixel[j]),
                calibration_only_error_m=float(calibration[j]),true_pixel_actual_camera_error_m=float(consistency[j]),
                signed_radial_error_m=float(signed_range[j]))
            frame.append(q)
        allcols.extend(frame)
        rows.append(dict(t=t,path=f['path'],detected=int(det.sum()),true_clear_detected=int((det&clear).sum()),
            compared=int(good.sum()),pitch_fixed_minus_actual_deg=pitch_delta,
            fixed_height_m=float(fixed_cm.origin[2]),actual_height_m=float(actual.origin[2]),
            total_endpoint_error_m=summary(total[good]),calibration_only_error_m=summary(calibration[good])))
    good=[q for q in allcols if q['compared']];vis=[q for q in allcols if q['true_clear']]
    keys=['total_endpoint_error_m','pixel_only_error_m','calibration_only_error_m','true_pixel_actual_camera_error_m','signed_radial_error_m','pixel_residual_px']
    out.mkdir(parents=True)
    detail=out/'columns.json';detail.write_text(json.dumps(allcols)+'\n')
    report=dict(schema='ugrp.s2.projection_audit.v1',physics_runs=0,model_calls=0,gt_usage='evaluation only; no controller instance',
        sample_hz=1.,frames=len(rows),carry_window=[lo,hi],detected_columns=len(allcols),visible_detected_columns=len(vis),
        finite_compared_columns=len(good),within_3px_visible_fraction=sum(abs(q['pixel_residual_px'])<=3 for q in vis)/len(vis),
        all_valid_detected_nearest_wall_error_m=summary([q['nearest_wall_error_m'] for q in allcols if q['valid']]),
        visible_metrics={k:summary([q[k] for q in good]) for k in keys},
        frame_median_total_error_m=summary([x['total_endpoint_error_m']['median'] for x in rows if x['compared']]),
        frame_median_calibration_only_error_m=summary([x['calibration_only_error_m']['median'] for x in rows if x['compared']]),
        pitch_fixed_minus_actual_deg=summary(pitches),height_fixed_minus_actual_m=summary(heights),origin_delta_m=summary(origin_delta),
        rows=rows,limitations='Fixed model on the true visible bottom isolates calibration error; actual camera on detected pixels isolates pixel error. Vector magnitudes are not additive. Command-body bounds are conservative; no manual annotations or correction fit. Different cohort from PR405; no pooling.',
        source_hashes={str(RAW/p):hashlib.sha256((RAW/p).read_bytes()).hexdigest() for p in ['result.json','bundle.json','robots/r3/frames.jsonl','eval_only/trajectory.jsonl','eval_only/camera-pose.jsonl']},
        columns=dict(path=str(detail),sha256=hashlib.sha256(detail.read_bytes()).hexdigest()))
    (out/'summary.json').write_text(json.dumps(report,indent=2)+'\n')
    print(json.dumps({k:v for k,v in report.items() if k not in ['rows','source_hashes']}),flush=True)


if __name__=='__main__':main(Path(sys.argv[1]))
