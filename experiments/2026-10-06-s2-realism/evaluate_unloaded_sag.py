"""Separate offline evaluation, NEVER imported by the replay/controller."""
import copy
import json
import math
import sys
from pathlib import Path
import cv2
import numpy as np

sys.path.insert(0,str(Path(__file__).resolve().parent))
import replay_unloaded_sag as replay
from harness import vision_loc_protocol as vp
from harness.opencv_wall_observation import observations
from harness.vision_pose_source_final import measured_column_model


def lines(path):
    return [json.loads(l) for l in path.read_text().splitlines()]


def evaluate(out):
    dest=out/'geometry-evaluation.json'
    if dest.exists():raise FileExistsError(dest)
    c=replay.contract
    source=replay.camera.build_provider(c.hp.resolve(c.MAP_ID)[0],c.ROOT/c.CALIBRATION,c.CALIBRATION_SHA,0)
    inner=source.provider;pf=inner.loc._pf;vl=vp.load_vis3()[0]
    original=copy.deepcopy(inner.calibration)
    variants={'legacy':original,**{v:replay.approximation(v) for v in replay.CRITERIA['variants'][1:]}}
    allrows=[]
    try:
        for seed,sha in replay.RUNS.items():
            raw=replay.RAW/f's2-realism-{sha}-s{seed}-P1-2-place'
            frames=lines(raw/'robots/r3/frames.jsonl');truth=lines(raw/'eval_only/trajectory.jsonl')
            cams=lines(raw/'eval_only/camera-pose.jsonl')
            window=replay.carry_window(json.loads((raw/'student_record.json').read_text()))
            # Fixed uniform one-SIM-second grid, selected before looking at RGB/GT.
            for t in np.arange(math.ceil(window[0]),window[1],1.):
                f=min(frames,key=lambda r:abs(r['sim_time']-t));t=f['sim_time']
                g=min(truth,key=lambda r:abs(r['t']-t));ca=min(cams,key=lambda r:abs(r['t']-t))
                servo={int(k):v for k,v in f['commanded_servo'].items()}
                if tuple(servo.get(k) for k in (3,4,5,6))!=(896,2035,1894,1500):continue
                pf.load.loaded=True;inner.servo=servo
                yaw=g['robot_yaw_rad'];co,si=math.cos(yaw),math.sin(yaw)
                rz=np.array([[co,si,0],[-si,co,0],[0,0,1]])
                gt_rec=dict(origin_m=rz@(np.array(ca['camera_cached_xyz_m'])-np.r_[g['robot_xyz_m'][:2],0]),
                            rotation=rz@np.array(ca['camera_cached_optical_rotation']))
                actual=measured_column_model(vl.mp,gt_rec,pf.columns)
                xy=np.r_[g['robot_xyz_m'][:2],yaw][None,:]
                actual_rows=vl.expected_rows(pf.geometry,xy,actual)[0][0]
                image=cv2.imread(str(raw/f['path']))
                row=dict(seed=seed,t=t,path=f['path'],actual_pitch_deg=ca['cached_pitch_deg'],
                    actual_height_m=float(gt_rec['origin_m'][2]),variants={})
                for name,table in variants.items():
                    for key in ('camera_models','pan_base_yaw'):
                        inner.calibration[key].clear();inner.calibration[key].update(copy.deepcopy(table[key]))
                    cm=pf.column_model_for(servo);obs=observations(vl,image,cm,inner.gates['values'])
                    expected=vl.expected_rows(pf.geometry,xy,cm)[0][0]
                    detected=obs.b_kind==vl.EDGE
                    visible=detected & (actual_rows>=4) & (actual_rows<=470)
                    diff=abs(expected-obs.b_lo)
                    row['variants'][name]=dict(columns=int(detected.sum()),visible_wall_columns=int(visible.sum()),
                        all_abs_residual_median_px=float(np.median(diff[detected])) if detected.any() else None,
                        visible_abs_residual_median_px=float(np.median(diff[visible])) if visible.any() else None,
                        actual_eval_abs_residual_median_px=float(np.median(abs(actual_rows[visible]-obs.b_lo[visible]))) if visible.any() else None,
                        pitch_deg=float(np.degrees(np.arcsin(cm._rot[2,2]))),height_m=float(cm.origin[2]))
                allrows.append(row)
            print('geometry',seed,'complete',flush=True)
        dest.write_text(json.dumps(dict(gt_use='evaluation only; not replay or admission',
            sample_grid_sim_s=1.,visible_definition='GT projected wall bottom row in [4,470]; detector not changed',rows=allrows))+'\n')
    finally:source.close()


if __name__=='__main__':evaluate(Path(sys.argv[1]))
