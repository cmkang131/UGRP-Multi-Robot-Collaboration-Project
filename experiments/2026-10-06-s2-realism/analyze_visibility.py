"""Posthoc geometric evaluation ONLY. No controller imports this file.

Logged camera/cargo truth is used solely for diagnostic ray intersections.
Robot joints and signed chassis tilt were not logged: self-body attribution is
a conservative command-geometry bound, not measured contact/occluder truth.
"""
import json, math, sys
from collections import Counter
from pathlib import Path
from types import SimpleNamespace as NS
import cv2
import numpy as np
sys.path.insert(0,str(Path(__file__).resolve().parent))
import replay_unloaded_sag as old
from harness.zone_solo_cyan_visibility import (robot_boxes, shadow_depths, box_depth,
    pixel_rays, K, K_INV, LOCAL_OPTICAL, POSITION_M)
from harness.visual_arm_v3 import tool_pose
from harness import zone_pair_highpose as high, vision_loc_protocol as vp
from harness.vision_pose_source_final import measured_column_model
from harness.opencv_wall_observation import observations
from harness.zone_solo_cyan_scene_change import cyan


def lines(p): return [json.loads(l) for l in p.read_text().splitlines()]


def rz(yaw):
    c,s=np.cos(yaw),np.sin(yaw)
    return np.array([[c,-s,0],[s,c,0],[0,0,1]])


def nominal_camera(pose, columns):
    p=tool_pose(pose,tool_length_cm=0.)
    yaw,pitch=np.radians([p.yaw_left_deg,p.pitch_deg])
    c,s=np.cos(pitch),np.sin(pitch)
    r=rz(yaw)@np.array([[c,0,-s],[0,1,0],[s,0,c]])
    o=np.array([p.x_m,p.y_m,p.z_m])+r@POSITION_M
    return NS(origin=o,_rot=r@LOCAL_OPTICAL,columns=columns)


def wall_segments(static):
    result=[]
    for o in static['obstacles']:
        if o.get('kind')!='wall':continue
        assert not o.get('yaw_rad',0)
        x,y=o['center_m'];dx,dy=o['half_extents_m']
        p=np.array([[x-dx,y-dy,0],[x+dx,y-dy,0],[x+dx,y+dy,0],[x-dx,y+dy,0]])
        result.extend(zip(p,np.roll(p,-1,axis=0)))
    return np.array(result)


def bottom_projection(cm, pose, segments):
    """Nearest positive-depth floor/wall crossing in each image-column plane.

    Unlike expected_rows' +/-infinity sentinels, finite projection is retained
    beyond image borders to distinguish above/below. No GT required by math.
    """
    xy=np.r_[pose[:2],0.];rotation=rz(pose[2])
    seg=(segments-xy)@rotation
    a,b=seg[:,0],seg[:,1];delta=b-a
    r0=pixel_rays(cm,cm.columns,0);r1=pixel_rays(cm,cm.columns,1)
    normals=np.cross(r0,r1);den=normals@delta.T
    with np.errstate(divide='ignore',invalid='ignore'):
        s=(normals@(cm.origin-a).T)/den
    with np.errstate(invalid='ignore'):
        p=a[None,:,:]+s[:,:,None]*delta
    opt=(p-cm.origin)@cm._rot
    valid=np.isfinite(s)&(s>=0)&(s<=1)&(opt[:,:,2]>1e-8)
    depth=np.where(valid,opt[:,:,2],np.inf);idx=np.argmin(depth,axis=1);c=np.arange(len(idx))
    best=opt[c,idx];selected=p[c,idx]
    with np.errstate(divide='ignore',invalid='ignore'):
        row=K[1,2]+K[1,1]*best[:,1]/best[:,2]
    row[~np.isfinite(depth[c,idx])]=np.nan
    return row,selected,best[:,2]


def wall_depths(cm, pose, rays, static):
    rotation=rz(pose[2]);origin=np.r_[pose[:2],0.];depth=np.full(rays.shape[:-1],np.inf)
    for o in static['obstacles']:
        if o.get('kind')!='wall':continue
        h=o['height_m'];center=(np.r_[o['center_m'],h/2]-origin)@rotation
        half=np.r_[o['half_extents_m'],h/2]
        np.minimum(depth,box_depth(cm.origin,rays,center,rotation.T,half),out=depth)
    return depth


def counts(labels, selected):
    return dict(Counter(labels[selected].tolist()))


def main(out):
    dest=out/'geometry-shadow.json'
    if dest.exists():raise FileExistsError(dest)
    c=old.contract;static=c.hp.resolve(c.MAP_ID)[0];segments=wall_segments(static)
    source=old.factory_for('unloaded_constant_delta')(static,c.ROOT/c.CALIBRATION,c.CALIBRATION_SHA,0)
    inner=source.provider;pf=inner.loc._pf;vl=vp.load_vis3()[0];pf.load.loaded=True
    cm=pf.column_model_for(high.HIGH);columns=pf.columns
    poses=dict(HIGH=high.HIGH,VIA110=high.VIA_110,VIA130=high.VIA_130,
        REAL_DELIVERY_CARRY={3:600,4:2200,5:1400,6:1500},LEGACY_POSE_CARRY={3:960,4:2410,5:1215,6:1500})
    models={name:nominal_camera(pose,columns) for name,pose in poses.items()}
    pose_boxes={name:robot_boxes({1:1500,**poses[name]},model) for name,model in models.items()}
    posture={}
    for name,model in models.items():
        rays=pixel_rays(model,np.array([K[0,2],K[0,2]]),np.array([4.,470.]))
        points=model.origin+(-model.origin[2]/rays[:,2,None])*rays
        posture[name]=dict(servo=poses[name],height_m=float(model.origin[2]),
            pitch_deg=float(np.degrees(np.arcsin(model._rot[2,2]))),
            center_column_floor_forward_m=[float(x) if ray[2]<0 else None for x,ray in zip(points[:,0],rays)],
            samples=0,in_view=0,clear_of_command_robot=0)
    summaries=[];records=[];hashes={}
    try:
        for seed,sha in old.RUNS.items():
            raw=old.RAW/f's2-realism-{sha}-s{seed}-P1-2-place'
            cameras=lines(raw/'eval_only/camera-pose.jsonl');gt=lines(raw/'eval_only/trajectory.jsonl')
            frames=lines(raw/'robots/r3/frames.jsonl');window=old.carry_window(json.loads((raw/'student_record.json').read_text()))
            for rel in ('eval_only/camera-pose.jsonl','eval_only/trajectory.jsonl','robots/r3/frames.jsonl','student_record.json'):
                hashes[str(raw/rel)]=old.digest(raw/rel)
            by_t={round(g['t'],6):g for g in gt};ca_t={round(g['t'],6):g for g in cameras}
            aggregate_all=Counter();aggregate_det=Counter();expected=Counter();samples=0;visible_frames=0
            distances={k:[] for k in ('above','below','in_view')};res=[];masks=Counter()
            pose_counts={name:Counter() for name in models}
            for request in np.arange(math.ceil(window[0]),window[1],1.):
                f=min(frames,key=lambda f:abs(f['sim_time']-request));t=f['sim_time']
                servo={int(k):v for k,v in f['commanded_servo'].items()}
                if not high.at_high(servo):continue
                g=by_t[round(t,6)];ca=ca_t[round(t,6)];base=np.r_[g['robot_xyz_m'][:2],0.];r=rz(g['robot_yaw_rad'])
                actual=NS(origin=r.T@(np.array(ca['camera_cached_xyz_m'])-base),
                    _rot=r.T@np.array(ca['camera_cached_optical_rotation']),columns=columns)
                pose=np.r_[g['robot_xyz_m'][:2],g['robot_yaw_rad']]
                rows,points,depth=bottom_projection(actual,pose,segments)
                inside=np.isfinite(rows)&(rows>=4)&(rows<=470)
                rays=pixel_rays(actual,columns,np.nan_to_num(rows))
                body=shadow_depths(actual.origin,rays,robot_boxes(servo,actual))
                cargo=box_depth(actual.origin,rays,r.T@(np.array(g['cyan_xyz_m'])-base),
                    r.T@np.array(g['cyan_rotation']).reshape(3,3),np.array(g['box_half_m']))
                depths=np.stack([cargo,body['gripper'],body['arm'],body['chassis'],wall_depths(actual,pose,rays,static)])
                first=np.argmin(depths,axis=0);hit=np.min(depths,axis=0)<depth-1e-6
                labels=np.full(len(columns),'no_front_wall',dtype=object)
                labels[np.isfinite(rows)&(rows<4)]='above'
                labels[np.isfinite(rows)&(rows>470)]='below'
                labels[inside]='clear'
                categories=np.array(['cargo_gt','gripper_possible','arm_possible','chassis_possible','wall_occlusion'])
                labels[inside&hit]=categories[first[inside&hit]]
                data=(raw/f['path']).read_bytes();assert old.hashlib.sha256(data).hexdigest()==f['sha256']
                bgr=cv2.imdecode(np.frombuffer(data,np.uint8),1)
                obs=observations(vl,bgr,cm,inner.gates['values']);det=obs.b_kind==vl.EDGE
                actual_cm=measured_column_model(vl.mp,dict(origin_m=actual.origin,rotation=actual._rot),columns)
                erows=vl.expected_rows(pf.geometry,pose[None,:],actual_cm)[0][0]
                ei=(erows>=4)&(erows<=470)
                expected.update(dict(detected=int(det.sum()),visible_detected=int((det&ei).sum()),
                    outside_detected=int((det&~ei).sum()),direct_visible_disagreements=int((ei!=inside).sum())))
                comparable=inside&ei
                res.extend(abs(rows[comparable]-erows[comparable]).tolist())
                aggregate_all.update(counts(labels,np.ones(len(labels),bool)));aggregate_det.update(counts(labels,det))
                for name,sel in [('above',rows<4),('below',rows>470),('in_view',inside)]:
                    distances[name].extend(np.linalg.norm(points[sel,:2]-actual.origin[:2],axis=1).tolist())
                visible_frames+=int(np.any(labels=='clear'));samples+=1
                # Coverage of robot and observed cargo mask on the image lattice.
                # Same rigid HIGH view -> nominal mask fixed and cached externally in replay.
                for name,model in models.items():
                    pr,_,pd=bottom_projection(model,pose,segments)
                    ok=np.isfinite(pr)&(pr>=4)&(pr<=470)
                    d=shadow_depths(model.origin,pixel_rays(model,columns,np.nan_to_num(pr)),pose_boxes[name])
                    clean=ok&(np.minimum.reduce(list(d.values()))>pd)&(wall_depths(model,pose,pixel_rays(model,columns,np.nan_to_num(pr)),static)>=pd-1e-6)
                    posture[name]['samples']+=len(columns);posture[name]['in_view']+=int(ok.sum())
                    posture[name]['clear_of_command_robot']+=int(clean.sum())
                    pose_counts[name].update(samples=len(columns),in_view=int(ok.sum()),clear=int(clean.sum()))
                records.append(dict(seed=seed,t=t,frame=f['path'],all_columns=counts(labels,np.ones(len(labels),bool)),
                    detected_columns=counts(labels,det),actual_pitch_deg=ca['cached_pitch_deg'],height_m=float(actual.origin[2]),
                    row_min=float(np.nanmin(rows)),row_max=float(np.nanmax(rows))))
            summary=dict(seed=seed,frames=samples,clear_frames=visible_frames,all_columns=dict(aggregate_all),
                detected_columns=dict(aggregate_det),previous_sentinel_definition=dict(expected),
                expected_vs_direct_visible_abs_px=dict(n=len(res),median=float(np.median(res)) if res else None,max=float(max(res)) if res else None),
                camera_to_wall_ground_range_m={k:dict(n=len(v),median=float(np.median(v)) if v else None,
                    p05=float(np.quantile(v,.05)) if v else None,p95=float(np.quantile(v,.95)) if v else None) for k,v in distances.items()},
                posture_counts={k:dict(v) for k,v in pose_counts.items()})
            summaries.append(summary);print('geometry',seed,json.dumps(summary),flush=True)
        for p in posture.values():
            p['in_view_fraction']=p['in_view']/p['samples'];p['clear_of_command_robot_fraction']=p['clear_of_command_robot']/p['samples']
        result=dict(physics_runs=0,model_calls=0,gt_usage='posthoc geometry evaluation only',
            limitation='cargo box intersection exact from eval; robot proxy shadows possible only (command FK, jaw sweep, no signed body tilt). Above/below independent of self-mask; v2 adds map-wall occlusion of bottom segments. geometry.json retained as preliminary no-map-occlusion analysis.',
            schema='ugrp.s2.visibility.geometry.v2',summaries=summaries,posture_geometry_only=posture,rows=records,source_hashes=hashes)
        dest.write_text(json.dumps(result,indent=2)+'\n')
    finally:source.close()


if __name__=='__main__':main(Path(sys.argv[1]))
