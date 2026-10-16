"""egomap19 own-input adapter around the byte-frozen parallax detector/scorer."""
from pathlib import Path
import sys
import json
from collections import Counter
import cv2
import numpy as np
ROOT=Path(__file__).resolve().parents[3]
EXP=Path(__file__).resolve().parents[1]
RAW=Path('/Users/changmin/projects/ugrp/outputs/servo-stiffness-v1')
sys.path.insert(0,str(ROOT/'experiments/2026-10-07-wall-parallax/code'))
# This file is also named replay.py; load the frozen module under another name.
import importlib.util
spec=importlib.util.spec_from_file_location('egomap14_replay',ROOT/'experiments/2026-10-07-wall-parallax/code/replay.py')
frozen=importlib.util.module_from_spec(spec)
spec.loader.exec_module(frozen)
c=frozen.c
from harness.self_pulse_odom import command_odometry
c.EXP=EXP
c.EPISODES={case:RAW/case for case in ('stiff-north','stiff-south')}
ORIGINAL_STREAM=c.stream
ORIGINAL_HASHES=frozen.hashes
MODES={'off':('off','off'),'fk':('servo_fk_v1','off'),
       'pulse':('off','s2_pulse_v122'),'fk_pulse':('servo_fk_v1','s2_pulse_v122')}
MODE='off'
EXTRA=['harness/self_pulse_odom.py','harness/data/s2_motion_v7_pulse_cal_v122.json',
       'harness/servo_camera_fk.py','harness/data/servo_camera_v3_chain.json',
       'experiments/2026-10-07-servo-stiffness/cohort.json',
       'experiments/2026-10-07-servo-stiffness/new-annotations.json',
       str(Path(__file__).relative_to(ROOT))]


def hashes():return {**ORIGINAL_HASHES(),**{p:c.sha(ROOT/p) for p in EXTRA}}
frozen.hashes=hashes


def stream(case):
    camera,motion=MODES[MODE]
    fs,cs=c.old.own_inputs(c.EPISODES[case],'r3')
    odom=command_odometry(fs[0]['sim_time'],motion_model=motion)
    odom.command(dict(t=fs[0]['sim_time'],kind='initial_servo_command',pulses=fs[0]['commanded_servo']))
    cursor=0
    for i,f in enumerate(fs):
        t=f['sim_time']
        while cursor<len(cs) and cs[cursor]['t']<t-1e-8:
            odom.command(cs[cursor])
            cursor+=1
        odom.advance(t)
        if i%2:continue
        cm=None
        if t-odom.servo_since+1e-8<(.25,2.25)[int(odom.loaded)]:reason='unsettled'
        else:
            servo={int(k):int(v) for k,v in f['commanded_servo'].items()}
            cm,_,reason=c.old.geometry(servo,'v3_unloaded_extrinsic_v1' if camera=='off' else 'off',camera_pose=camera)
        yield f,cm,reason,odom.pose,odom.covariance.copy()
c.stream=stream


def verify():
    freeze=c.read(ROOT/'experiments/2026-10-07-wall-parallax/freeze.json')
    assert freeze['hashes']==ORIGINAL_HASHES()
    assert freeze['settings']==json.loads(json.dumps(frozen.settings()))


def off_golden():
    assert MODE=='off'
    count=0
    for case in c.EPISODES:
        for a,b in zip(ORIGINAL_STREAM(case),stream(case),strict=True):
            assert json.dumps([a[0],a[2],a[3]])==json.dumps([b[0],b[2],b[3]])
            assert a[4].tobytes()==b[4].tobytes()
            assert (a[1] is None)==(b[1] is None)
            if a[1] is not None:
                assert a[1].origin.tobytes()==b[1].origin.tobytes()
                assert a[1]._rot.tobytes()==b[1]._rot.tobytes()
            count+=1
    return count


def prepare():
    assert not (EXP/'cohort.json').exists()
    golden=off_golden()
    cohort=dict(role='new_plant_development_no_tuning',off_golden_rows=golden,cases={})
    labels=[]
    for case,ep in c.EPISODES.items():
        rs=list(stream(case))
        eligible=[f for f,cm,reason,pose,cov in rs if cm is not None]
        cohort['cases'][case]=dict(episode=str(ep),sources={str(p):c.sha(p) for p in
            [ep/'robots/r3/frames.jsonl',ep/'robots/r3/commands.jsonl']},
            eligible_frames=[f['frame_id'] for f in eligible],counts=dict(Counter(r[2] for r in rs)))
        for k in range(6):
            f=eligible[(2*k+1)*len(eligible)//12]
            rgb=ep/f['path']
            assert c.sha(rgb)==f['sha256']
            image=RAW/'annotations'/f'{case}-{k}.png'
            image.parent.mkdir(parents=True,exist_ok=True)
            cv2.imwrite(str(image),c.old.mp.undistort(cv2.imread(str(rgb))))
            labels.append(dict(case=case,k=k,frame_id=f['frame_id'],t=f['sim_time'],raw_path=str(rgb),
                sha256=f['sha256'],image=str(image),undistorted_sha256=c.sha(image),
                polylines=[],ignore=[],status='pending_manual_rgb_annotation'))
    c.dump(EXP/'cohort.json',cohort)
    c.dump(EXP/'new-annotations.json',dict(rule='six_mid_quantiles_per_case',rows=labels))
    print('Prepared',golden,'off byte golden rows')


def floor_score(case,mode):
    """Same fixed label denominator for table/FK, GT read after prediction seal."""
    sys.path.insert(0,str(ROOT/'experiments/2026-10-07-camera-pose-projection/code'))
    import evaluate_fk as gate_module
    a=gate_module.a
    ep=c.EPISODES[case]
    truth=c.old.current_truth(ep)
    rects=np.array([w['center_m']+w['half_extents_m'] for w in c.read(ep/'inputs/static_map.json')['obstacles'] if w.get('kind')=='wall'])
    labels={r['frame_id']:r for r in c.read(EXP/'new-annotations.json')['rows'] if r['case']==case}
    pred=c.old.base.read_rows(c.OUT/'parallax_v1'/case/'predictions.jsonl')
    frames={r['frame_id']:r for r in c.old.own_inputs(ep,'r3')[0]}
    original,errors=[],[]
    fixed_count=positive=within=0
    for row in pred:
        if row['frame_id'] not in labels:continue
        label,ignore=frozen.metric.annotation_rows(labels[row['frame_id']])
        uv=np.c_[frozen.COLS,label]
        origin,rotation=a.nominal(frames[row['frame_id']]['commanded_servo'])
        xy0,ok0,range0=a.project(uv,origin,rotation)
        fixed=np.isfinite(label)&~ignore&ok0&(range0<=4.)
        fixed_count+=int(fixed.sum())
        pose=truth[round(row['t'],6)]
        original.extend(c.old.base.boundary_dist(frozen.transform(xy0[fixed],pose),rects))
        xy,ok,dist=a.project(uv,np.array(row['origin']),np.array(row['rotation']))
        positive+=int((fixed&ok).sum())
        within+=int((fixed&ok&(dist<=4.)).sum())
        errors.extend(c.old.base.boundary_dist(frozen.transform(xy[fixed&ok],pose),rects))
    base,current=a.stats(original),a.stats(errors)
    result=dict(case=case,mode=mode,fixed=fixed_count,positive=positive,within4m=within,
        baseline=base,candidate=current,gate=gate_module.gate(base,current,fixed_count,positive,within))
    c.dump(EXP/'results'/mode/(case+'-floor.json'),result)
    print(case,mode,'floor',current['median'],current['p90'],result['gate']['passed'])


def main():
    import argparse
    global MODE
    p=argparse.ArgumentParser()
    p.add_argument('stage',choices=['prepare','predict','score'])
    args=p.parse_args()
    verify()
    if args.stage=='prepare':return prepare()
    assert all(r['status']=='sealed_before_parallax_predictions' for r in c.read(EXP/'new-annotations.json')['rows'])
    if args.stage=='score':
        assert all((RAW/'replay'/mode/'parallax_v1'/case/'receipt.json').exists()
            for mode in MODES for case in c.EPISODES)
    for MODE in MODES:
        c.OUT=RAW/'replay'/MODE
        for case in c.EPISODES:
            if args.stage=='predict':frozen.predict(case,'parallax_v1')
            else:
                frozen.score(case,'parallax_v1')
                target=EXP/'results'/MODE/(case+'.json')
                target.parent.mkdir(parents=True,exist_ok=True)
                assert not target.exists()
                (EXP/'results'/(case+'.json')).rename(target)
                floor_score(case,MODE)


if __name__=='__main__':main()
