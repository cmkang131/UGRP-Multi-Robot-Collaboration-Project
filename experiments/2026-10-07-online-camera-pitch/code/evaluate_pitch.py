"""Own-only online prediction seal, then the unchanged manual projection gate."""
import argparse
from collections import Counter
from pathlib import Path
import subprocess
import sys
import numpy as np
import cv2

EXP=Path(__file__).resolve().parents[1]
ROOT=EXP.parents[1]
OUT=Path('/Users/changmin/projects/ugrp/outputs/online-camera-pitch-v1')
sys.path[:0]=[str(ROOT),str(ROOT/'experiments/2026-10-07-camera-pose-projection/code')]
import audit as a
from evaluate_fk import gate,CRITERIA
from harness.online_camera_pitch import PARAMETERS


def hashes():
    files=[EXP/'README.md',EXP/'SOURCES.json',Path(__file__),
        ROOT/'harness/online_camera_pitch.py',*sorted((ROOT/'harness/vendor/lu_vp').glob('*.py')),
        ROOT/'harness/vendor/lu_vp/UPSTREAM.json',
        ROOT/'experiments/2026-10-07-camera-pose-projection/code/audit.py',
        ROOT/'experiments/2026-10-07-camera-pose-projection/code/evaluate_fk.py',
        ROOT/'experiments/2026-10-05-ego-wall-map-probe/code/v3_confidence_replay.py',
        ROOT/'experiments/2026-10-07-wall-floor-boundary/annotation-sample.json']
    return {str(p.relative_to(ROOT)):a.digest(p) for p in files}


def run(case,option):
    dest=OUT/option/case
    dest.mkdir(parents=True,exist_ok=False)
    ep=a.old.EPISODES[case]
    frames,_=a.old.own_inputs(ep,'r3')
    # Frame IDs alone are a pre-registered scheduling list, no pixel labels used.
    sample=a.load(ROOT/'experiments/2026-10-07-wall-floor-boundary/annotation-sample.json')['rows']
    scheduled={r['frame_id'] for r in sample if r['case']==case}
    inputs={str(ep/'robots/r3/frames.jsonl'):a.digest(ep/'robots/r3/frames.jsonl')}
    predictions=[]
    for f in frames:
        if f['frame_id'] not in scheduled:continue
        path=ep/f['path']
        assert a.digest(path)==f['sha256']
        servo={int(k):v for k,v in f['commanded_servo'].items()}
        cm,offset,meta=a.old.geometry(servo,'v3_unloaded_extrinsic_v1',camera_pitch=option,
                                    own_bgr=cv2.imread(str(path)) if option!='off' else None)
        assert cm is not None and np.array_equal(offset,np.zeros(3))
        predictions.append(dict(frame_id=f['frame_id'],t=f['sim_time'],servo=servo,
             origin=cm.origin.tolist(),rotation=cm._rot.tolist(),meta=meta,image_sha256=f['sha256']))
        inputs[str(path)]=f['sha256']
    assert len(predictions)==len(scheduled)
    a.old.rows(dest/'own-predictions.jsonl',predictions)
    seal=a.digest(dest/'own-predictions.jsonl')
    a.write(dest/'prediction-source.json',dict(source_sha=subprocess.check_output(['git','rev-parse','HEAD'],text=True).strip(),
        hashes=hashes(),inputs=inputs,parameters=PARAMETERS,criteria=CRITERIA,prediction_sha256=seal))
    # Evaluation boundary: GT body/walls/actual camera and human pixels only below.
    truth={round(r['t'],6):r for r in a.old.base.read_rows(ep/'eval_only/trajectory.jsonl')}
    actualfile=ep/'eval_only/camera-pose.jsonl'
    actual={round(r['t'],6):r for r in a.old.base.read_rows(actualfile)} if actualfile.exists() else {}
    rects=np.array([w['center_m']+w['half_extents_m'] for w in a.load(ep/'inputs/static_map.json')['obstacles'] if w.get('kind')=='wall'])
    annotations={r['frame_id']:r for r in sample if r['case']==case}
    metrics={k:[] for k in ('baseline','candidate','oracle')}
    columns,perframe=[],[]
    count=positive=within=0
    pitch_diffs=[]
    for r in predictions:
        uvrows,ignore=a.annotation_rows(annotations[r['frame_id']])
        uv=np.c_[a.COLS,uvrows]
        nominal=a.nominal(r['servo'])
        xy0,ok0,range0=a.project(uv,*nominal)
        fixed=np.isfinite(uvrows)&~ignore&ok0&(range0<=4.)
        t=round(r['t'],6)
        body=truth[t]
        pose=[*body['robot_xyz_m'][:2],body['robot_yaw_rad']]
        rigid=np.array(r['origin']),np.array(r['rotation'])
        xy,ok,ranges=a.project(uv,*rigid)
        count+=int(fixed.sum())
        positive+=int((fixed&ok).sum())
        within+=int((fixed&ok&(ranges<=4.)).sum())
        choices=dict(baseline=(xy0,ok0,range0),candidate=(xy,ok,ranges))
        f=dict(frame_id=r['frame_id'],fixed_points=int(fixed.sum()),meta=r['meta'],metrics={},
               candidate_pitch_deg=float(np.degrees(a.angles(rigid[1])[1])))
        if t in actual:
            ac=a.actual_camera(actual[t],body)
            choices['oracle']=a.project(uv,*ac)
            f['actual_pitch_deg']=float(np.degrees(a.angles(ac[1])[1]))
            pitch_diffs.append(f['candidate_pitch_deg']-f['actual_pitch_deg'])
        for label,(points,valid,distance) in choices.items():
            use=fixed&valid
            err=a.old.base.boundary_dist(a.old.transform(points[use],pose),rects)
            metrics[label].extend(err.tolist())
            f['metrics'][label]=a.stats(err)
            for j,e in zip(np.flatnonzero(use),err):
                columns.append(dict(frame_id=r['frame_id'],condition=label,column=int(a.COLS[j]),
                                    error_m=float(e),range_m=float(distance[j])))
        perframe.append(f)
    stats={k:{**a.stats(v),'rmse':float(np.sqrt(np.mean(np.square(v)))) if v else None} for k,v in metrics.items()}
    prior=a.load(ROOT/f'experiments/2026-10-07-wall-floor-boundary/results/off/{case}.json')['annotation_projection_error_m']
    assert prior['count']==count and abs(prior['median']-stats['baseline']['median'])<1e-10
    result=dict(case=case,camera_pitch=option,split='development' if case in ('s1042','s1043') else 'confirmation_replay',
        frames=len(predictions),points=count,positive=positive,within4m=within,metrics=stats,
        counts=dict(Counter(r['meta']['reason'] if isinstance(r['meta'],dict) else 'off' for r in predictions)),
        pitch_delta_deg=a.stats(pitch_diffs),gate=gate(stats['baseline'],stats['candidate'],count,positive,within),
        frame_scores=perframe,prediction_sha256=seal,hashes=hashes(),physics=0,models=0)
    a.old.rows(dest/'columns.jsonl',columns)
    a.write(dest/'result.json',result)
    a.write(EXP/'results'/option/(case+'.json'),result)
    paths=[ep/'eval_only/trajectory.jsonl',actualfile,ep/'inputs/static_map.json']
    a.write(dest/'evaluation-sources.json',{str(p):a.digest(p) for p in paths if p.exists()})
    assert seal==a.digest(dest/'own-predictions.jsonl')
    print(case,option,'median/P90',stats['candidate']['median'],stats['candidate']['p90'],
          'counts',result['counts'],'gate',result['gate']['passed'],flush=True)


def main():
    p=argparse.ArgumentParser()
    p.add_argument('--split',choices=['development','confirmation'],required=True)
    p.add_argument('--camera-pitch',choices=['off','online_vp_v1'],default='off')
    p.add_argument('--freeze',type=Path)
    args=p.parse_args()
    if args.split=='confirmation':
        frozen=a.load(args.freeze) if args.freeze else {}
        assert frozen.get('hashes')==hashes() and frozen.get('criteria')==CRITERIA
        assert frozen.get('parameters')==PARAMETERS
    for case in (['s1042','s1043'] if args.split=='development' else ['s1044','s1045','s1046','s1047']):
        run(case,args.camera_pitch)


if __name__=='__main__':
    main()
