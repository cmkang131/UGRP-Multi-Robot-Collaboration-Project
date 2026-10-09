"""Post-run S2 judge only. Reads saved evaluation files after controller close.

No value produced here is a robot observation, stop condition, or action.
Visibility uses actual saved camera/cargo geometry at 1 Hz and command-based
self geometry; robot-body occlusion is a bound, not measured joint ground truth.
"""
import hashlib
import importlib.util
import json
import math
from pathlib import Path
from types import SimpleNamespace as NS
from collections import Counter
import cv2
import numpy as np


def rows(path):return [json.loads(line) for line in path.read_text().splitlines()]


def metrics(raw,record,bundle):
    from harness.zone_solo_cyan_contract_v106 import hp,MAP_ID
    from harness import vision_loc_protocol as vp
    from harness.opencv_wall_observation import observations
    from harness.vision_pose_source_final import measured_column_model
    from harness.zone_solo_cyan_visibility import robot_boxes,shadow_depths,box_depth,pixel_rays
    root=Path(__file__).resolve().parents[1]
    path=root/'experiments/2026-10-06-s2-realism/analyze_visibility.py'
    spec=importlib.util.spec_from_file_location('s2_posthoc_geometry',path)
    geo=importlib.util.module_from_spec(spec);spec.loader.exec_module(geo)
    truth=rows(raw/'eval_only/trajectory.jsonl')
    if not truth:return dict(status='NO_EVALUATION_TRAJECTORY')
    static=hp.resolve(MAP_ID)[0];region=static['regions']['zone_B']
    center=np.array(region['center_m']);half=np.array(region['half_extents_m'])
    cargo=np.array(truth[-1]['cyan_xyz_m'][:2]);robot=np.array(truth[-1]['robot_xyz_m'][:2])
    boundary=lambda x:float(np.linalg.norm(np.maximum(abs(x-center)-half,0)))
    states=[e for e in record['events'] if e['event']=='state']
    indices=[i for i,e in enumerate(states) if e['state']=='carry']
    out=dict(scope='POSTHOC_EVAL_ONLY_NO_CONTROL_FEEDBACK',seed=bundle['task']['seed'],
        cargo_remaining_to_B_region_m=boundary(cargo),cargo_distance_to_B_center_m=float(np.linalg.norm(cargo-center)),
        robot_remaining_to_B_region_m=boundary(robot),final_cargo_xy_m=cargo.tolist(),
        final_robot_xy_m=robot.tolist(),carry_window=None,visual_updates=0,max_update_gap_sim_s=None,
        carry_xy_rmse_m=None,actual_visibility=None)
    if not indices:return {**out,'status':'NO_CARRY_PHASE'}
    i=indices[0];start=states[i]['t'];end=states[i+1]['t'] if i+1<len(states) else truth[-1]['t']
    out['carry_window']=[start,end]
    fix=sorted({float(x['t']) for x in record.get('soft_measurement',{}).get('rows',[])
                if x.get('visual_weight_update') and start<=x['t']<end})
    out.update(visual_updates=len(fix),max_update_gap_sim_s=float(max(np.diff([start,*fix,end]))),
               measurement_claim='nonconstant AMCL weight updates, not full-rank absolute pose fixes',update_times=fix)
    times=np.array([x['t'] for x in truth]);xy=np.array([x['robot_xyz_m'][:2] for x in truth])
    poses=[p for p in record['poses'] if start<=p['t']<end]
    errors=[float(np.linalg.norm(np.array([p['x'],p['y']])-
        [np.interp(p['t_est'],times,xy[:,j]) for j in (0,1)])) for p in poses]
    if errors:out.update(carry_xy_rmse_m=float(np.sqrt(np.mean(np.square(errors)))),
                         carry_xy_p90_m=float(np.quantile(errors,.9)),carry_end_error_m=errors[-1],carry_pose_samples=len(errors))
    frames=rows(raw/'robots/r3/frames.jsonl');cameras={round(r['t'],6):r for r in rows(raw/'eval_only/camera-pose.jsonl')}
    gt={round(r['t'],6):r for r in truth};ft=np.array([f['sim_time'] for f in frames])
    selected=sorted(set(int(np.argmin(abs(ft-t))) for t in np.arange(math.ceil(start),end,1.)))
    segments=geo.wall_segments(static);columns=np.linspace(8,631,96).astype(int);vl=vp.load_vis3()[0]
    from harness.zone_pair_highpose_contract import own_image_gates
    gates=own_image_gates()['values'];all_counts=Counter();det_counts=Counter();sample_rows=[]
    for idx in selected:
        f=frames[idx];t=f['sim_time'];g=gt[round(t,6)];a=cameras[round(t,6)]
        if not start<=t<end:continue
        rz=geo.rz(g['robot_yaw_rad']);base=np.r_[g['robot_xyz_m'][:2],0.]
        cm=NS(origin=rz.T@(np.array(a['camera_cached_xyz_m'])-base),
              _rot=rz.T@np.array(a['camera_cached_optical_rotation']),columns=columns)
        pose=np.r_[g['robot_xyz_m'][:2],g['robot_yaw_rad']]
        projected,_,depth=geo.bottom_projection(cm,pose,segments)
        inside=np.isfinite(projected)&(projected>=4)&(projected<=470)
        rays=pixel_rays(cm,columns,np.nan_to_num(projected))
        servo={int(k):v for k,v in f['commanded_servo'].items()}
        self_depth=shadow_depths(cm.origin,rays,robot_boxes(servo,cm))
        cargo_depth=box_depth(cm.origin,rays,rz.T@(np.array(g['cyan_xyz_m'])-base),
            rz.T@np.array(g['cyan_rotation']).reshape(3,3),np.array(g['box_half_m']))
        layers=np.stack([cargo_depth,*self_depth.values(),geo.wall_depths(cm,pose,rays,static)])
        labels=np.full(96,'no_front_wall',dtype=object)
        labels[np.isfinite(projected)&(projected<4)]='above'
        labels[np.isfinite(projected)&(projected>470)]='below'
        labels[inside]='clear'
        categories=np.array(['cargo_gt',*[k+'_possible' for k in self_depth], 'wall_occlusion'])
        hit=np.min(layers,axis=0)<depth-1e-6;first=np.argmin(layers,axis=0)
        labels[inside&hit]=categories[first[inside&hit]]
        data=(raw/f['path']).read_bytes();assert hashlib.sha256(data).hexdigest()==f['sha256']
        bgr=cv2.imdecode(np.frombuffer(data,np.uint8),1)
        m=measured_column_model(vl.mp,dict(origin_m=cm.origin,rotation=cm._rot),columns)
        obs=observations(vl,bgr,m,gates);det=obs.b_kind==vl.EDGE
        counts=dict(Counter(labels.tolist()));dc=dict(Counter(labels[det].tolist()))
        all_counts.update(counts);det_counts.update(dc)
        sample_rows.append(dict(t=t,path=f['path'],all_columns=counts,detected_columns=dc,pitch_deg=a['cached_pitch_deg']))
    out['actual_visibility']=dict(sample_hz=1.,sample_frames=len(sample_rows),all_columns=dict(all_counts),
        detected_columns=dict(det_counts),all_clear_fraction=all_counts['clear']/sum(all_counts.values()) if all_counts else None,
        detected_clear_fraction=det_counts['clear']/sum(det_counts.values()) if det_counts else None,
        method='saved actual camera/cargo + static walls, conservative command-body bounds, undistorted rows4..470; not live perception input',rows=sample_rows)
    masks=[m for m in record.get('visibility_mask',{}).get('rows',[]) if start<=m['t']<end]
    out['visibility_measurement']=dict(attempts=len(masks),less_than_six_columns=sum(m['kept']<6 for m in masks),
        detected_columns=sum(m['detected'] for m in masks),kept_columns=sum(m['kept'] for m in masks))
    out['status']='COMPLETE'
    return out
