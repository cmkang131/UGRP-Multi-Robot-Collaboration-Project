"""Evaluation-only camera-pose decomposition; never import from an actor.

No dynamics, rendering, fitting or model requests. Stored actual camera pose is
read ONLY here. Own transforms are fixed before truth/annotations are loaded.
"""
from collections import defaultdict
import hashlib
import json
from pathlib import Path
import subprocess
import sys

import numpy as np
from scipy.spatial.transform import Rotation

ROOT=Path(__file__).resolve().parents[3]
EXP=Path(__file__).resolve().parents[1]
OUT=Path('/Users/changmin/projects/ugrp/outputs/camera-pose-projection-v1')
sys.path[:0]=[str(ROOT),str(ROOT/'experiments/2026-10-05-ego-wall-map-probe/code')]
import v3_confidence_replay as old
sys.path.insert(0,str(ROOT/'experiments/2026-10-07-wall-floor-boundary/code'))
from evaluate import annotation_rows, COLS
from harness.zone_final_pair_camera import floor_camera

AXES=np.array([[0.,0.,1.],[-1.,0.,0.],[0.,-1.,0.]])
COMPONENTS=('x','y','height','yaw','pitch','roll')


def load(p):
    return json.loads(Path(p).read_text())


def digest(p):
    return hashlib.sha256(Path(p).read_bytes()).hexdigest()


def write(p,value):
    p.parent.mkdir(parents=True,exist_ok=True)
    p.write_text(json.dumps(value,indent=2,allow_nan=False)+'\n')


def angles(matrix):
    a=Rotation.from_matrix(np.asarray(matrix)@AXES.T).as_euler('ZYX')
    a[1]*=-1
    return a


def rotation(a):
    return Rotation.from_euler('ZYX',np.asarray(a)*[1,-1,1]).as_matrix()@AXES


def rz(yaw):
    return Rotation.from_euler('z',yaw).as_matrix()


def actual_camera(row,body,field='cached'):
    prefix='camera_cached' if field=='cached' else 'camera_from_body'
    yaw=body['robot_yaw_rad']
    origin=rz(yaw).T@(np.asarray(row[prefix+'_xyz_m'])-np.r_[body['robot_xyz_m'][:2],0.])
    return origin,rz(yaw).T@np.asarray(row[prefix+'_optical_rotation'])


def project(uv,origin,rot):
    rays=np.c_[np.asarray(uv),np.ones(len(uv))]@old.mp.K_INV.T@np.asarray(rot).T
    with np.errstate(divide='ignore',invalid='ignore'):
        t=-origin[2]/rays[:,2]
        xyz=origin+t[:,None]*rays
    depth=((xyz-origin)@rot)[:,2]
    positive=np.isfinite(xyz).all(axis=1)&(t>0)&(depth>0)
    distance=np.linalg.norm(xyz[:,:2]-origin[:2],axis=1)
    return xyz[:,:2],positive,distance


def stats(values):
    a=np.asarray(values,float)
    return dict(n=len(a),median=float(np.median(a)) if len(a) else None,
        p05=float(np.quantile(a,.05)) if len(a) else None,p90=float(np.quantile(a,.90)) if len(a) else None,
        p95=float(np.quantile(a,.95)) if len(a) else None)


def nominal(servo):
    key=','.join(str(int(servo[str(k)] if str(k) in servo else servo[k])) for k in (3,4,5,6))
    entry=old.calibration()['camera_models']['unloaded'].get(key)
    if entry is None:
        return None
    value=floor_camera(entry)
    return np.array(value['origin_m']),np.array(value['rotation'])


def swap(one,two,index):
    o,r=np.array(one[0],copy=True),np.array(one[1],copy=True)
    if index<3:
        o[index]=two[0][index]
    else:
        a=angles(r)
        a[index-3]=angles(two[1])[index-3]
        r=rotation(a)
    return o,r


def main():
    dest=OUT/'decomposition'
    dest.mkdir(parents=True,exist_ok=False)
    # Own-command/fixed-product side sealed first; no GT or annotation needed here.
    own={}
    inputs={}
    for case,ep in old.EPISODES.items():
        fs,_=old.own_inputs(ep,'r3')
        eligfile=old.OUT/case/'v3_unloaded_extrinsic_v1/extraction.jsonl'
        eligible={r['frame_id'] for r in old.base.read_rows(eligfile) if r['reason']=='calibrated_unloaded'}
        own[case]=[dict(frame_id=f['frame_id'],t=f['sim_time'],servo=f['commanded_servo'],
            eligible=f['frame_id'] in eligible,nominal=None if nominal(f['commanded_servo']) is None else
            [v.tolist() for v in nominal(f['commanded_servo'])]) for f in fs]
        for p in (ep/'robots/r3/frames.jsonl',eligfile):inputs[str(p)]=digest(p)
    write(dest/'own-nominal.json',own)
    seal=digest(dest/'own-nominal.json')
    # Evaluation starts only after own predictions are saved and hashed.
    annotations=load(ROOT/'experiments/2026-10-07-wall-floor-boundary/annotation-sample.json')['rows']
    summaries={}
    for case,ep in old.EPISODES.items():
        bodyfile=ep/'eval_only/trajectory.jsonl'
        actualfile=ep/'eval_only/camera-pose.jsonl'
        body={round(r['t'],6):r for r in old.base.read_rows(bodyfile)}
        camera={round(r['t'],6):r for r in old.base.read_rows(actualfile)} if actualfile.exists() else {}
        for p in (bodyfile,actualfile,ep/'inputs/static_map.json'):
            if p.exists():inputs[str(p)]=digest(p)
        rects=np.array([w['center_m']+w['half_extents_m'] for w in load(ep/'inputs/static_map.json')['obstacles'] if w.get('kind')=='wall'])
        groups=defaultdict(list)
        comparisons=[]
        cache_delta=[]
        for f in own[case]:
            key=round(f['t'],6)
            if key not in camera or key not in body:continue
            actual=actual_camera(camera[key],body[key])
            other=actual_camera(camera[key],body[key],'from_body')
            cache_delta.append([float(np.linalg.norm(actual[0]-other[0])),
                                float(Rotation.from_matrix(actual[1].T@other[1]).magnitude())])
            if f['nominal'] is None:continue
            n=[np.array(v) for v in f['nominal']]
            diff=np.r_[actual[0]-n[0],(angles(actual[1])-angles(n[1])+np.pi)%(2*np.pi)-np.pi]
            cmdkey=','.join(str(f['servo'][str(k)]) for k in (3,4,5,6))
            group='eligible' if f['eligible'] else 'ineligible'
            groups[group].append(diff)
            groups['pose:'+cmdkey].append(diff)
            comparisons.append(dict(frame_id=f['frame_id'],t=f['t'],eligible=f['eligible'],command_pose=cmdkey,
                nominal_origin=n[0].tolist(),actual_origin=actual[0].tolist(),
                nominal_angles_deg=np.degrees(angles(n[1])).tolist(),actual_angles_deg=np.degrees(angles(actual[1])).tolist(),
                difference_xyz_m_angles_rad=diff.tolist()))
        old.rows(dest/(case+'-frames.jsonl'),comparisons)
        groupstats={}
        for group,values in groups.items():
            a=np.asarray(values)
            groupstats[group]={k:stats(a[:,i]*(1000 if i<3 else 180/np.pi)) for i,k in enumerate(COMPONENTS)}
        measures=defaultdict(list)
        displacement=defaultdict(list)
        validcounts=defaultdict(int)
        labels=[]
        lookup={f['frame_id']:f for f in own[case]}
        fixed_count=0
        for annotation in (a for a in annotations if a['case']==case):
            f=lookup[annotation['frame_id']]
            n=[np.array(v) for v in f['nominal']]
            v,ignore=annotation_rows(annotation)
            uv=np.c_[COLS,v]
            nxy,nvalid,nrange=project(uv,*n)
            positive=np.isfinite(v)&~ignore&nvalid&(nrange<=4.)
            fixed_count+=int(positive.sum())
            key=round(f['t'],6)
            pose=[*body[key]['robot_xyz_m'][:2],body[key]['robot_yaw_rad']]
            conditions={'nominal':n}
            truth=None
            if key in camera:
                truth=actual_camera(camera[key],body[key])
                conditions['actual_all']=truth
                for i,k in enumerate(COMPONENTS):
                    conditions['nominal_replace_'+k]=swap(n,truth,i)
                    conditions['actual_revert_'+k]=swap(truth,n,i)
            txy=project(uv,*truth)[0] if truth is not None else None
            for tag,rigid in conditions.items():
                xy,valid,distance=project(uv,*rigid)
                selected=positive&valid
                errors=old.base.boundary_dist(old.transform(xy[selected],pose),rects)
                measures[tag].extend(errors.tolist())
                validcounts[tag]+=int((positive&valid&(distance<=4.)).sum())
                if truth is not None:
                    displacement[tag].extend(np.linalg.norm(xy[selected]-txy[selected],axis=1).tolist())
                labels.append(dict(frame_id=f['frame_id'],t=f['t'],condition=tag,fixed_points=int(positive.sum()),
                    positive_points=int(selected.sum()),valid_within_4m=int((positive&valid&(distance<=4.)).sum()),
                    error=stats(errors)))
        old.rows(dest/(case+'-annotations.jsonl'),labels)
        summary=dict(case=case,actual_logged_frames=len(camera),matched_nominal_frames=len(comparisons),
            fixed_annotation_points=fixed_count,groups=groupstats,
            boundary_error={k:stats(v) for k,v in measures.items()},
            displacement_from_actual={k:stats(v) for k,v in displacement.items()},valid_within_4m=dict(validcounts),
            cache_vs_body_max=None if not cache_delta else dict(position_m=float(np.max(cache_delta,axis=0)[0]),
                rotation_rad=float(np.max(cache_delta,axis=0)[1])))
        summaries[case]=summary
        write(dest/(case+'-summary.json'),summary)
        print(case,'actual frames',len(camera),'nominal',summary['boundary_error']['nominal'],
              'actual',summary['boundary_error'].get('actual_all'),flush=True)
    assert digest(dest/'own-nominal.json')==seal
    write(dest/'summary.json',summaries)
    write(dest/'provenance.json',dict(source_sha=subprocess.check_output(['git','rev-parse','HEAD'],text=True).strip(),
        sources=inputs,own_prediction_sha256=seal,gt_to_actor=False,physics=0,render=0,model_calls=0,
        annotation_sha256=digest(ROOT/'experiments/2026-10-07-wall-floor-boundary/annotation-sample.json')))


if __name__=='__main__':main()
