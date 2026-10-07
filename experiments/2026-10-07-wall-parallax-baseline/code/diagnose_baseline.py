"""Evaluation-only baseline interventions; NEVER import this into a controller.

Stage capture uses own RGB/commands only and reproduces old prediction bytes.
Stage diagnose reads GT translation only after capture receipts have been sealed.
The frozen detector/tracker/calibration and all selection thresholds are unchanged.
"""
from pathlib import Path
import argparse,copy,json,math,subprocess,sys
from collections import Counter
import numpy as np
ROOT=Path(__file__).resolve().parents[3]
EXP=Path(__file__).resolve().parents[1]
TEXTURE=ROOT/'experiments/2026-10-07-wall-parallax-texture'
RAW=Path('/Users/changmin/projects/ugrp/outputs/wall-parallax-baseline-v1')
sys.path[:0]=[str(ROOT),str(ROOT/'experiments/2026-10-07-wall-parallax-texture/code')]
import replay_texture as source
frozen,c=source.frozen,source.c
from harness import wall_parallax as geometry
BASE=Path('/Users/changmin/projects/ugrp/outputs/wall-parallax-texture-v1/replay/parallax_v1')
CASES=('tape-north','tape-south')
MODES=('eval_gt_translation_only','eval_gt_length_only')


def provenance():
    paths=[Path(__file__),EXP/'README.md',EXP/'results/model-source-comparison.json']
    return dict(source_sha=subprocess.check_output(['git','rev-parse','HEAD'],cwd=ROOT,text=True).strip(),
        source_hashes={str(p.relative_to(ROOT)):c.sha(p) for p in paths},
        frozen_hashes=frozen.hashes(),settings=frozen.settings(),
        environment=dict(python=sys.version,numpy=np.__version__,opencv=source.cv2.__version__))


def plain(value):
    if isinstance(value,np.ndarray):return value.tolist()
    if isinstance(value,np.generic):return value.item()
    if isinstance(value,dict):return {k:plain(v) for k,v in value.items()}
    if isinstance(value,(tuple,list)):return [plain(v) for v in value]
    return value


def history_array(rows):
    return [dict(r,pose=np.array(r['pose']),cov=np.array(r['cov']),uv=np.array(r['uv'])) for r in rows]


def baseline_history(history,gt_xy,origin,rotation,mode):
    """Intervene on translation only, leaving yaw/UV/covariance bit-identical.

    gt_xy is evaluation-only body translation expressed in a common start frame.
    Scalar diagnostic scales camera-centre offsets so depth scale is isolated
    from trajectory direction/shape. Current camera centre stays at its DR value.
    """
    if mode not in MODES:raise ValueError('EXPLICIT_EVALUATION_ONLY_MODE_REQUIRED')
    modified=copy.deepcopy(history)
    xy=np.array([gt_xy[h['frame_id']] for h in history],float)
    if xy.shape!=(len(history),2) or not np.isfinite(xy).all():raise ValueError('FINITE_EVAL_XY_REQUIRED')
    if mode=='eval_gt_translation_only':
        for row,pos in zip(modified,xy):row['pose'][:2]=pos
    else:
        body=np.array([h['pose'][:2] for h in history])
        distance=np.linalg.norm(body[-1]-body[0])
        if distance<1e-8:return modified
        scale=np.linalg.norm(xy[-1]-xy[0])/distance
        centres=[geometry.camera(h['pose'],origin,rotation)[0] for h in history]
        for row,centre in zip(modified,centres):
            # Camera lever arm preserved. z offsets are zero for the frozen SE2 model.
            target=centres[-1]+scale*(centre-centres[-1])
            row['pose'][:2]=(target-geometry.rz(row['pose'][2])@origin)[:2]
    for a,b in zip(history,modified):
        assert a['pose'][2]==b['pose'][2] and np.array_equal(a['cov'],b['cov']) and np.array_equal(a['uv'],b['uv'])
    return modified


def capture_case(case):
    source.verify()
    events=[]
    class Recorder(geometry.ParallaxWallDetector):
        def observe(self,*args,**kwargs):
            calls=[];original=geometry.triangulate
            def record(history,origin,rotation,k):
                value,reason=original(history,origin,rotation,k)
                calls.append(dict(history=copy.deepcopy(history),reason=reason,value=copy.deepcopy(value)))
                return value,reason
            geometry.triangulate=record
            try:result=super().observe(*args,**kwargs)
            finally:geometry.triangulate=original
            identities={tuple(h[-1]['uv']):tid for tid,h in self.tracks}
            for row in calls:
                row.update(frame_id=kwargs['frame_id'],track_id=identities[tuple(row['history'][-1]['uv'])])
                events.append(plain(row))
            return result
    original=frozen.ParallaxWallDetector
    c.OUT=RAW/'capture' # c.EXP remains the immutable texture cohort, read-only.
    frozen.ParallaxWallDetector=Recorder
    try:frozen.predict(case,'parallax_v1')
    finally:frozen.ParallaxWallDetector=original
    out=c.OUT/'parallax_v1'/case
    for name in ('predictions.jsonl','eligibility.jsonl'):
        assert c.sha(out/name)==c.sha(BASE/case/name),f'FROZEN_BYTES_DIFFER:{case}/{name}'
    with (out/'track-history.jsonl').open('x') as f:
        for row in events:frozen.write_line(f,row)
    receipt=c.read(out/'receipt.json')
    assert Counter(e['reason'] for e in events)==Counter({k:v for k,v in receipt['counts'].items() if k in {
        'insufficient_views','zero_baseline','low_parallax','nonfinite','behind_camera','reprojection','beyond_4m','nonfinite_covariance','accepted'}})
    c.dump(out/'capture-receipt.json',dict(frozen_prediction_bytes_equal=True,events=len(events),
        track_history_sha256=c.sha(out/'track-history.jsonl'),prediction_receipt_sha256=c.sha(out/'receipt.json'),
        provenance=provenance(),gt_opened=False,own_only=True,physics=0,model_calls=0))
    print(case,'CAPTURE',len(events),'events, prediction/eligibility bytes identical',flush=True)


def summarize(predictions,truth,rects,annotations,oracle):
    modes=('baseline','candidate');errors={m:[] for m in modes};annotated={m:{} for m in modes}
    detail=[]
    for row in predictions:
        pose=truth[round(row['t'],6)]
        for mode in modes:
            ps=row[mode];es=frozen.point_errors(ps,pose,rects)
            errors[mode].extend(es.tolist())
            for p,e in zip(ps,es):
                detail.append(dict(mode=mode,frame_id=row['frame_id'],track_id=p.get('track_id'),
                    uv=p['uv'],xy=p['xy'],range_m=p['range_m'],error_m=float(e),confidence=p.get('confidence'),
                    baseline_m=p.get('baseline_m')))
            if row['frame_id'] in annotations:
                stats=frozen.annotate(ps,es,annotations[row['frame_id']],np.array(row['origin']),np.array(row['rotation']))
                for key,v in stats.items():annotated[mode].setdefault(key,Counter()).update(v)
    reports={mode:dict(points=dict(frozen.stats(errors[mode]),precision=float(np.mean(np.array(errors[mode])<=.15)) if errors[mode] else None),
        annotated=frozen.finalize_annotation(annotated[mode])) for mode in modes}
    p=reports['candidate']['points'];a=reports['candidate']['annotated']['all'];base=reports['baseline']['points']
    above=lambda x,v:x is not None and x>=v
    below=lambda x,v:x is not None and x<=v
    checks=dict(precision=above(p['precision'],.9),annotated_precision=above(a['precision'],.9),recall=above(a['recall'],.7),
        median=below(p['median'],.1),p90=below(p['p90'],.25),baseline_nondecrease=above(p['precision'],base['precision']),
        labels=a['positive']>=50,annotated_tp=a['tp']>=30)
    return dict(reports=reports,numerical_checks=checks,numerical_gate_passed=all(checks.values()),
        own_only=not oracle,adopted=False,operational_gate_passed=False,physics=0,model_calls=0),detail


def diagnose_case(case):
    source.verify()
    cap=RAW/'capture/parallax_v1'/case
    rec=c.read(cap/'capture-receipt.json')
    assert rec['frozen_prediction_bytes_equal'] and rec['track_history_sha256']==c.sha(cap/'track-history.jsonl')
    assert rec['prediction_receipt_sha256']==c.sha(cap/'receipt.json')
    frames=c.old.base.read_rows(cap/'predictions.jsonl');events=c.old.base.read_rows(cap/'track-history.jsonl')
    # First evaluation data access; no GT fields are returned to the production harness.
    ep=c.EPISODES[case];truth=c.old.current_truth(ep)
    first=c.old.base.read_rows(ep/'eval_only/trajectory.jsonl')[0]
    start=np.r_[first['robot_xyz_m'][:2],first['robot_yaw_rad']]
    yaw=start[2];cs,sn=math.cos(yaw),math.sin(yaw)
    gt_xy={r['frame_id']:(truth[round(r['t'],6)][:2]-start[:2])@np.array([[cs,-sn],[sn,cs]]) for r in frames}
    byframe={r['frame_id']:r for r in frames}
    rects=np.array([w['center_m']+w['half_extents_m'] for w in c.read(ep/'inputs/static_map.json')['obstacles'] if w.get('kind')=='wall'])
    annotations={a['frame_id']:a for a in c.read(TEXTURE/'new-annotations.json')['rows'] if a['case']==case}
    out=RAW/'evaluation'/case;out.mkdir(parents=True,exist_ok=False)
    baseline,details=summarize(frames,truth,rects,annotations,False)
    # Cross-check the old score to protect denominators and precision definitions.
    old=c.read(TEXTURE/'results'/f'{case}.json')
    for key in ('n','precision','median','p90','rmse'):
        assert baseline['reports']['candidate']['points'][key]==old['reports']['candidate']['points']['all'][key]
    c.dump(out/'command_baseline.json',baseline)
    with (out/'command_points.jsonl').open('x') as f:
        for row in details:frozen.write_line(f,row)
    result={}
    for mode in MODES:
        predictions=copy.deepcopy(frames)
        for row in predictions:row['candidate']=[]
        modified_byframe={r['frame_id']:r for r in predictions}
        counters=Counter();paired=[];all_events=[]
        for event in events:
            history=history_array(event['history']);row=byframe[event['frame_id']]
            origin,rotation=np.array(row['origin']),np.array(row['rotation'])
            modified=baseline_history(history,gt_xy,origin,rotation,mode)
            value,reason=geometry.triangulate(modified,origin,rotation,c.old.mp.K)
            counters[reason]+=1
            info=dict(frame_id=event['frame_id'],track_id=event['track_id'],original_reason=event['reason'],reason=reason,
                original_body_baseline_m=float(np.linalg.norm(history[-1]['pose'][:2]-history[0]['pose'][:2])),
                gt_body_baseline_m=float(np.linalg.norm(gt_xy[history[-1]['frame_id']]-gt_xy[history[0]['frame_id']])) )
            if value is not None:modified_byframe[event['frame_id']]['candidate'].append(dict(track_id=event['track_id'],**value))
            if event['reason']=='accepted':
                errors=[] if value is None else frozen.point_errors([value],truth[round(row['t'],6)],rects).tolist()
                original_error=frozen.point_errors([event['value']],truth[round(row['t'],6)],rects)[0]
                paired.append(dict(**info,old_error_m=float(original_error),new_error_m=errors[0] if errors else None,
                    original_xyz=event['value']['xyz'],new_xyz=value['xyz'] if value else None))
            all_events.append(info)
        summary,points=summarize(predictions,truth,rects,annotations,True)
        summary.update(diagnostic=mode,case=case,counts=dict(counters),same_original_accepted=paired,
            thresholds_unchanged=True,provenance=dict(**provenance(),track_history_sha256=rec['track_history_sha256'],
                truth_sha256=c.sha(ep/'eval_only/trajectory.jsonl'),map_sha256=c.sha(ep/'inputs/static_map.json'),
                annotation_sha256=c.sha(TEXTURE/'new-annotations.json')))
        result[mode]=summary
        c.dump(out/(mode+'.json'),summary)
        for filename,rows in [('points',points),('events',all_events),('predictions',predictions)]:
            with (out/(mode+'-'+filename+'.jsonl')).open('x') as f:
                for row in rows:frozen.write_line(f,row)
        q=summary['reports']['candidate']['points'];a=summary['reports']['candidate']['annotated']['all']
        print(case,mode,'points',q['n'],'P',q['precision'],'R',a['recall'],'median',q['median'],'gate',summary['numerical_gate_passed'],flush=True)
    yaw_errors=[abs((start[2]+r['pose'][2]-truth[round(r['t'],6)][2]+math.pi)%(2*math.pi)-math.pi) for r in frames]
    c.dump(out/'unchanged_yaw_error.json',dict(scope='Evaluation only, yaw never replaced',rad=frozen.stats(yaw_errors),
        degrees=frozen.stats(np.degrees(yaw_errors))))
    return result


def main():
    p=argparse.ArgumentParser();p.add_argument('stage',choices=['capture','diagnose']);a=p.parse_args()
    source.verify()
    if a.stage=='capture':
        for case in CASES:capture_case(case)
    else:
        assert all((RAW/'capture/parallax_v1'/case/'capture-receipt.json').exists() for case in CASES)
        rows={case:diagnose_case(case) for case in CASES}
        recovered=[]
        for case in CASES:
            p=rows[case]['eval_gt_translation_only']['reports']['candidate']['points']
            recovered.append(p['precision'] is not None and p['precision']>=.9 and p['median'] is not None and p['median']<=.1)
        c.dump(RAW/'diagnosis-gate.json',dict(recovered_cases=sum(recovered),required=2,
            hypothesis='baseline_only_sufficient_for_precision_and_median',passed=all(recovered),
            next_step='READ_ONLY_V122_ADAPTER' if all(recovered) else 'STOP_BASELINE_ONLY_INSUFFICIENT',
            operational_admission=False,gt_is_evaluation_only=True))
    assert 'mujoco' not in sys.modules

if __name__=='__main__':main()
