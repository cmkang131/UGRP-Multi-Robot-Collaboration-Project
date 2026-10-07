"""Frozen command-FK projection gate, own prediction before truth scoring."""
import argparse
import hashlib
import json
from pathlib import Path
import subprocess
import sys
import numpy as np

sys.path.insert(0,str(Path(__file__).parent))
import audit as a
from harness.servo_camera_fk import transform_from_commands

FILES=['harness/servo_camera_fk.py','harness/data/servo_camera_v3_chain.json',
       'harness/visual_arm.py','experiments/2026-10-05-ego-wall-map-probe/code/v3_confidence_replay.py',
       'experiments/2026-10-07-camera-pose-projection/code/evaluate_fk.py',
       'experiments/2026-10-07-camera-pose-projection/code/audit.py',
       'experiments/2026-10-07-wall-floor-boundary/annotation-sample.json',
       'experiments/2026-10-05-ego-wall-map-probe/calibration/s2_camera_v3_extrinsic_v1.json']
CRITERIA=dict(median_m=.10,p90_m=.25,min_points=50,valid_fraction=.95,baseline_nonincrease=True)


def source_hashes():
    return {n:a.digest(a.ROOT/n) for n in FILES}


def gate(base,error,fixed,positive,within):
    checks=dict(points=fixed>=50,positive=positive==fixed,
        valid_fraction=within/max(1,fixed)>=.95,
        median=error['median'] is not None and error['median']<=.10,
        p90=error['p90'] is not None and error['p90']<=.25,
        nonincrease=error['median'] is not None and error['median']<=base['median'])
    return dict(checks=checks,passed=all(checks.values()))


def run(case):
    ep=a.old.EPISODES[case]
    dest=a.OUT/'servo_fk_v1'/case
    dest.mkdir(parents=True,exist_ok=False)
    frames,_=a.old.own_inputs(ep,'r3')
    eligible={r['frame_id'] for r in a.old.base.read_rows(a.old.OUT/case/'v3_unloaded_extrinsic_v1/extraction.jsonl')
              if r['reason']=='calibrated_unloaded'}
    predictions=[]
    for f in frames:
        if f['frame_id'] not in eligible:continue
        servo={int(k):int(v) for k,v in f['commanded_servo'].items()}
        rigid,reason=transform_from_commands(servo,camera_pose='servo_fk_v1')
        predictions.append(dict(frame_id=f['frame_id'],t=f['sim_time'],servo=servo,
            transform=None if rigid is None else [x.tolist() for x in rigid],reason=reason))
    a.old.rows(dest/'own-predictions.jsonl',predictions)
    sealed=a.digest(dest/'own-predictions.jsonl')
    a.write(dest/'prediction-source.json',dict(source_sha=subprocess.check_output(['git','rev-parse','HEAD'],text=True).strip(),
        hashes=source_hashes(),prediction_sha256=sealed,criteria=CRITERIA,
        frames_sha256=a.digest(ep/'robots/r3/frames.jsonl')))
    # Truth is first read below this boundary; no calibration/parameter changes.
    truth={round(r['t'],6):r for r in a.old.base.read_rows(ep/'eval_only/trajectory.jsonl')}
    rects=np.array([w['center_m']+w['half_extents_m'] for w in a.load(ep/'inputs/static_map.json')['obstacles'] if w.get('kind')=='wall'])
    annotations=[r for r in a.load(a.ROOT/'experiments/2026-10-07-wall-floor-boundary/annotation-sample.json')['rows'] if r['case']==case]
    index={r['frame_id']:r for r in predictions}
    errors,base_errors,perframe=[],[],[]
    count=positive=within=0
    for annotation in annotations:
        r=index[annotation['frame_id']]
        nominal=a.nominal(r['servo'])
        v,ignore=a.annotation_rows(annotation)
        uv=np.c_[a.COLS,v]
        xy0,ok0,range0=a.project(uv,*nominal)
        fixed=np.isfinite(v)&~ignore&ok0&(range0<=4.)
        body=truth[round(r['t'],6)]
        pose=[*body['robot_xyz_m'][:2],body['robot_yaw_rad']]
        baseline=a.old.base.boundary_dist(a.old.transform(xy0[fixed],pose),rects)
        base_errors.extend(baseline.tolist())
        count+=int(fixed.sum())
        errs=[]
        current_positive=current_within=0
        if r['transform'] is not None:
            rigid=[np.array(x) for x in r['transform']]
            xy,ok,dist=a.project(uv,*rigid)
            use=fixed&ok
            current_positive=int(use.sum())
            current_within=int((use&(dist<=4.)).sum())
            errs=a.old.base.boundary_dist(a.old.transform(xy[use],pose),rects).tolist()
        positive+=current_positive
        within+=current_within
        errors.extend(errs)
        perframe.append(dict(frame_id=r['frame_id'],t=r['t'],fixed_points=int(fixed.sum()),
            positive_points=current_positive,within4m=current_within,baseline=a.stats(baseline),candidate=a.stats(errs)))
    result=dict(case=case,split='development' if case in ('s1042','s1043') else 'confirmation_replay',
        camera_pose='servo_fk_v1',frames=len(predictions),fixed_annotation_points=count,positive_points=positive,
        within4m_points=within,baseline=a.stats(base_errors),candidate=a.stats(errors),
        gate=gate(a.stats(base_errors),a.stats(errors),count,positive,within),
        hashes=source_hashes(),prediction_sha256=sealed,frame_scores=perframe)
    assert sealed==a.digest(dest/'own-predictions.jsonl')
    # Exact old baseline reproduction checks annotation/coordinate/denominator parity.
    prior=a.load(a.ROOT/f'experiments/2026-10-07-wall-floor-boundary/results/off/{case}.json')['annotation_projection_error_m']
    assert prior['count']==count and abs(prior['median']-result['baseline']['median'])<1e-10
    a.write(dest/'result.json',result)
    a.write(a.EXP/'results'/'servo_fk_v1'/f'{case}.json',result)
    print(case,'old/new median',result['baseline']['median'],result['candidate']['median'],
          'P90',result['candidate']['p90'],'valid',within,count,'PASS',result['gate']['passed'],flush=True)
    return result


def main():
    p=argparse.ArgumentParser()
    p.add_argument('--split',choices=['development','confirmation'],required=True)
    p.add_argument('--freeze',type=Path)
    args=p.parse_args()
    if args.split=='confirmation':
        frozen=a.load(args.freeze) if args.freeze else {}
        if frozen.get('hashes')!=source_hashes() or frozen.get('criteria')!=CRITERIA:
            raise ValueError('EXACT_FROZEN_SOURCE_REQUIRED')
    for case in (['s1042','s1043'] if args.split=='development' else ['s1044','s1045','s1046','s1047']):
        run(case)


if __name__=='__main__':main()
