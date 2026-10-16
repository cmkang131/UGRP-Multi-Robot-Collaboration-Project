"""Saved-output evaluation only. Never imported by a controller or replay."""
import copy
import json
import math
from pathlib import Path
import sys
import cv2
import numpy as np
from scipy.spatial.transform import Rotation
sys.path.insert(0,str(Path(__file__).resolve().parent))
import replay_unloaded_sag as old
from harness import vision_loc_protocol as vp
from harness.vision_pose_source_final import measured_column_model
from harness.opencv_wall_observation import observations
from sim.masterpi_camera_profile import scaled_camera_matrix, raw_fisheye_remap


def lines(path):return [json.loads(l) for l in path.read_text().splitlines()]


def stats(values):
    a=np.asarray(values,float);a=a[np.isfinite(a)]
    if not len(a):return dict(n=0)
    return dict(n=len(a),signed_median=float(np.median(a)),abs_median=float(np.median(abs(a))),
                p05=float(np.quantile(a,.05)),p95=float(np.quantile(a,.95)),std=float(np.std(a)))


def main(out):
    out.mkdir(parents=True,exist_ok=True);dest=out/'residual-decomposition.json'
    if dest.exists():raise FileExistsError(dest)
    c=old.contract;source=old.factory_for('unloaded_constant_delta')(c.hp.resolve(c.MAP_ID)[0],
        c.ROOT/c.CALIBRATION,c.CALIBRATION_SHA,0)
    inner=source.provider;pf=inner.loc._pf;vl=vp.load_vis3()[0];pf.load.loaded=True
    servo=dict(zip((3,4,5,6),(896,2035,1894,1500)));inner.servo=servo
    nominal=pf.column_model_for(servo)
    # Coordinate-field round trip of the exact renderer and detector remaps.
    rx,ry=raw_fisheye_remap(640,480);ux,uy=vl.mp._UNDISTORT
    backx=cv2.remap(rx,ux,uy,cv2.INTER_LINEAR,borderMode=cv2.BORDER_CONSTANT,borderValue=np.nan)
    backy=cv2.remap(ry,ux,uy,cv2.INTER_LINEAR,borderMode=cv2.BORDER_CONSTANT,borderValue=np.nan)
    yy,xx=np.indices((480,640));valid=(ux>2)&(ux<637)&(uy>2)&(uy<477)&np.isfinite(backy)
    lens=dict(K_max_difference=float(abs(vl.mp.K-scaled_camera_matrix(640,480)).max()),
        roundtrip_x_px=stats((backx-xx)[valid]),roundtrip_y_px=stats((backy-yy)[valid]),
        scope='numerical coordinate remaps only, not real hardware intrinsics validation')
    records=[];summaries=[];source_hashes={}
    try:
        for seed,sha in old.RUNS.items():
            raw=old.RAW/f's2-realism-{sha}-s{seed}-P1-2-place'
            cams=lines(raw/'eval_only/camera-pose.jsonl');trajectory=lines(raw/'eval_only/trajectory.jsonl')
            supervisors=lines(raw/'eval_only/supervisor.jsonl');frames=lines(raw/'robots/r3/frames.jsonl')
            window=old.carry_window(json.loads((raw/'student_record.json').read_text()))
            for rel in ('eval_only/camera-pose.jsonl','eval_only/trajectory.jsonl','eval_only/supervisor.jsonl','robots/r3/frames.jsonl'):
                source_hashes[str(raw/rel)]=old.digest(raw/rel)
            by_t={round(g['t'],6):g for g in trajectory}
            geo=[]
            for ca in cams:
                t=ca['t']
                if not window[0]<=t<window[1]:continue
                g=by_t[round(t,6)];yaw=g['robot_yaw_rad'];co,si=math.cos(yaw),math.sin(yaw)
                rz=np.array([[co,si,0],[-si,co,0],[0,0,1]])
                geo.append(dict(t=t,origin=rz@(np.array(ca['camera_cached_xyz_m'])-np.r_[g['robot_xyz_m'][:2],0]),
                    rotation=rz@np.array(ca['camera_cached_optical_rotation']),truth=g,pitch=ca['cached_pitch_deg']))
            mean_o=np.mean([g['origin'] for g in geo],axis=0)
            mean_r=Rotation.from_matrix(np.array([g['rotation'] for g in geo])).mean().as_matrix()
            mean_rec=dict(origin_m=mean_o,rotation=mean_r)
            collected=[]
            for requested in np.arange(math.ceil(window[0]),window[1],1.):
                f=min(frames,key=lambda f:abs(f['sim_time']-requested));t=f['sim_time']
                if tuple(f['commanded_servo'].get(str(k)) for k in (3,4,5,6))!=(896,2035,1894,1500):continue
                g=min(geo,key=lambda g:abs(g['t']-t));sup=min(supervisors,key=lambda s:abs(s['t']-t))
                actual=dict(origin_m=g['origin'],rotation=g['rotation'])
                variants=[dict(origin_m=nominal.origin,rotation=nominal._rot),
                    dict(origin_m=np.r_[nominal.origin[:2],mean_o[2]],rotation=nominal._rot),
                    dict(origin_m=mean_o,rotation=nominal._rot),mean_rec,actual]
                xy=np.r_[g['truth']['robot_xyz_m'][:2],g['truth']['robot_yaw_rad']][None,:]
                rows=[vl.expected_rows(pf.geometry,xy,measured_column_model(vl.mp,v,pf.columns))[0][0] for v in variants]
                data=(raw/f['path']).read_bytes();assert old.hashlib.sha256(data).hexdigest()==f['sha256']
                obs=observations(vl,cv2.imdecode(np.frombuffer(data,np.uint8),1),nominal,inner.gates['values'])
                det=obs.b_kind==vl.EDGE
                usable=det & (rows[-1]>=4)&(rows[-1]<=470)
                for r in rows:usable &= np.isfinite(r)&(abs(r)<9999)
                # First-order sensitivity envelope over UNKNOWN roll/pitch axis.
                # Tilt magnitude is logged, signed axes are not. This is not a
                # measured decomposition of joint droop and chassis attitude.
                deriv=[];h=np.array([0,0,g['truth']['robot_xyz_m'][2]])
                for axis in ([1,0,0],[0,1,0]):
                    eps=1e-5;rot=Rotation.from_rotvec(np.array(axis)*eps).as_matrix()
                    rec=dict(origin_m=h+rot@(g['origin']-h),rotation=rot@g['rotation'])
                    rp=vl.expected_rows(pf.geometry,xy,measured_column_model(vl.mp,rec,pf.columns))[0][0]
                    deriv.append((rp-rows[-1])/eps)
                tilt_rad=np.radians(sup['robot_tilt_deg'])
                envelope=np.hypot(*deriv)*tilt_rad
                contributions=[(rows[i]-rows[i+1])[usable] for i in range(4)]
                detector=(rows[-1]-obs.b_lo)[usable];total=(rows[0]-obs.b_lo)[usable]
                assert np.allclose(sum(contributions)+detector,total,atol=1e-9)
                row=dict(seed=seed,t=t,frame=f['path'],columns=int(det.sum()),visible_columns=int(usable.sum()),
                    tilt_deg=sup['robot_tilt_deg'],pitch_deg=g['pitch'],height_m=float(g['origin'][2]),
                    wheels_commanded=any(sup['wheel_command']),actual_wall_outside_columns=int((det&~((rows[-1]>=4)&(rows[-1]<=470))).sum()),
                    components={name:stats(v) for name,v in zip(['mean_height','mean_xy','mean_rotation','dynamic_total','detector_and_raster'],[*contributions,detector])},
                    total=stats(total),tilt_first_order_envelope_px=stats(envelope[usable]))
                records.append(row);collected.append((contributions,detector,total,envelope[usable]))
            merged={}
            for i,name in enumerate(['mean_height','mean_xy','mean_rotation','dynamic_total','detector_and_raster','total','tilt_first_order_envelope_px']):
                groups=[([*x[0],x[1],x[2],x[3]])[i] for x in collected]
                merged[name]=stats(np.concatenate(groups))
            sg=[r for r in records if r['seed']==seed]
            summaries.append(dict(seed=seed,carry_window=window,mean_origin_eval_only=mean_o.tolist(),
                mean_rotation_eval_only=mean_r.tolist(),pitch_deg=stats([g['pitch'] for g in geo]),
                height_m=stats([g['origin'][2] for g in geo]),tilt_deg=stats([s['robot_tilt_deg'] for s in supervisors if window[0]<=s['t']<window[1]]),
                sample_frames=len(sg),visible_sample_frames=sum(r['visible_columns']>0 for r in sg),
                signed_telescoping_contributions=merged,
                dynamic_by_command={str(on):stats([r['components']['dynamic_total']['abs_median'] for r in sg if r['wheels_commanded']==on and r['visible_columns']]) for on in (False,True)}))
            print('decomposition',seed,merged,flush=True)
        result=dict(physics_runs=0,gt_usage='evaluation only; all mean transforms confined to this file',
            ordering='nominal -> mean height -> mean xy -> mean R -> actual per frame -> detector',
            attribution_limit='nonlinear ordered decomposition; median magnitudes do not add; chassis roll/pitch and joints unlogged so separate sag/chassis contributions not identifiable',
            lens=lens,summaries=summaries,rows=records,source_hashes=source_hashes)
        dest.write_text(json.dumps(result,indent=2)+'\n')
    finally:source.close()


if __name__=='__main__':main(Path(sys.argv[1]))
