"""Offline prediction first, immutable receipt, then separate wall truth scoring."""
import argparse
from collections import Counter
import math
import subprocess
import sys
import cv2
import numpy as np
import common as c
from harness.wall_parallax import ParallaxWallDetector,detect,PARAMETERS,LK,FEATURE
from harness.self_odom_grid import transform

COLS=c.old.mp.column_positions(96,2)
sys.path.insert(0,str(c.ROOT/'experiments/2026-10-07-wall-floor-boundary/code'))
import evaluate as metric
FILES=['harness/wall_parallax.py','harness/self_map_prob.py','harness/self_odom_grid.py',
       'harness/wall_camera_calibration.py','harness/owncam_localizer.py',
       'experiments/2026-09-26-zone-m1-owncam/calibration_m1_dev.json',
       'experiments/2026-10-05-ego-wall-map-probe/calibration/s2_camera_v3_extrinsic_v1.json',
       'experiments/2026-10-05-ego-wall-map-probe/code/height_free_wall.py',
       'experiments/2026-10-05-ego-wall-map-probe/code/markerless_probe.py',
       'experiments/2026-10-05-ego-wall-map-probe/code/v3_confidence_replay.py',
       'experiments/2026-10-07-wall-floor-boundary/annotation-sample.json',
       'experiments/2026-10-07-wall-floor-boundary/code/evaluate.py',
       *['experiments/2026-10-07-wall-parallax/'+p for p in
         ['README.md','cohort.json','new-annotations.json','code/common.py','code/replay.py']]]
CRITERIA=dict(precision=.9,annotated_precision=.9,recall=.7,median_m=.1,p90_m=.25,
              positive_labels=50,annotated_tp=30,baseline_nondecrease=True)


def hashes():return {p:c.sha(c.ROOT/p) for p in FILES}
def settings():return dict(parameters=PARAMETERS,lk=LK,feature=FEATURE,criteria=CRITERIA)
def write_line(stream,row):stream.write(__import__('json').dumps(row,allow_nan=False)+'\n')


def predict(case,option):
    ep=c.EPISODES[case]
    cohort=c.read(c.EXP/'cohort.json')['cases'][case]
    for path,digest in cohort['sources'].items():assert c.sha(path)==digest
    out=c.OUT/option/case
    out.mkdir(parents=True,exist_ok=False)
    state=ParallaxWallDetector('r3',intrinsic=c.old.mp.K,wall_detector=option) if option!='off' else None
    accepted=[]
    totals=Counter()
    cv2.setNumThreads(1)
    with (out/'predictions.jsonl').open('w') as stream,(out/'eligibility.jsonl').open('w') as ledger:
        for f,cm,reason,pose,cov in c.stream(case):
            write_line(ledger,dict(frame_id=f['frame_id'],t=f['sim_time'],reason=reason))
            totals[reason]+=1
            if cm is None:
                if state is not None:state.reset()
                continue
            path=ep/f['path']
            assert c.sha(path)==f['sha256']
            image=c.old.mp.undistort(cv2.imread(str(path)))
            servo={int(k):v for k,v in f['commanded_servo'].items()}
            scan=c.old.hfw.detect(image,cm,params=c.old.PARAMS,loaded=c.old.wp.is_loaded(servo))
            rows=scan['vb'][:,0]
            uv=np.c_[COLS,rows]
            xy,ranges,ok=metric.project(uv,cm.origin,cm._rot,c.old.mp.K)
            baseline=[dict(uv=uv[i].tolist(),xy=xy[i].tolist(),range_m=float(ranges[i])) for i in np.flatnonzero(ok)]
            result=detect(baseline,wall_detector=option,state=state,und_bgr=image,
                robot_id='r3',frame_id=f['frame_id'],t=f['sim_time'],pose=pose,covariance=cov,
                camera_origin=cm.origin,camera_rotation=cm._rot,columns=COLS,boundary_rows=rows,
                servo_key=tuple(servo[k] for k in (3,4,5,6)))
            points=result['points'] if option!='off' else result
            counts=result['counts'] if option!='off' else {}
            write_line(stream,dict(frame_id=f['frame_id'],t=f['sim_time'],pose=pose,
                covariance=cov.tolist(),origin=cm.origin.tolist(),rotation=cm._rot.tolist(),
                baseline=baseline,candidate=points,counts=counts))
            totals.update(counts)
            accepted.append(f['frame_id'])
            if len(accepted)%100==0:print(case,option,'frames',len(accepted),'accepted points',totals['accepted'],flush=True)
    assert accepted==cohort['eligible_frames']
    receipt=dict(case=case,option=option,source_sha=subprocess.check_output(['git','rev-parse','HEAD'],text=True).strip(),
        source_hashes=hashes(),settings=settings(),cohort_sha256=c.sha(c.EXP/'cohort.json'),
        predictions_sha256=c.sha(out/'predictions.jsonl'),eligibility_sha256=c.sha(out/'eligibility.jsonl'),
        counts=dict(totals),frames=len(accepted),physics=0,model_calls=0,
        environment=dict(python=sys.version,opencv=cv2.__version__,numpy=np.__version__))
    c.dump(out/'receipt.json',receipt)
    assert 'mujoco' not in sys.modules
    print(case,'prediction sealed',len(accepted),dict(totals),flush=True)


def stats(values):
    v=np.asarray(values)
    return dict(n=len(v),median=float(np.median(v)) if len(v) else None,
                p90=float(np.quantile(v,.9)) if len(v) else None,
                rmse=float(np.sqrt(np.mean(v*v))) if len(v) else None)


def point_errors(points,pose,rects):
    if not points:return np.empty(0)
    return c.old.base.boundary_dist(transform([p['xy'] for p in points],pose),rects)


def annotate(points,errors,annotation,origin,rotation):
    label,ignore=metric.annotation_rows(annotation)
    _,label_ranges,valid=metric.project(np.c_[COLS,label],origin,rotation,c.old.mp.K)
    positive=np.isfinite(label)&~ignore&valid
    bins={}
    assigned=[]
    for p,e in zip(points,errors):
        j=int(np.argmin(abs(COLS-p['uv'][0])))
        if abs(COLS[j]-p['uv'][0])>float(np.diff(COLS).min())/2:continue
        if ignore[j]:continue
        pixel=bool(positive[j] and abs(p['uv'][1]-label[j])<=3.)
        assigned.append((j,p['range_m'],pixel,pixel and e<=.15))
    for name,lo,hi in [('all',0.,4.000001),('0-2m',0.,2.),('2-3m',2.,3.),('3-4m',3.,4.000001)]:
        pred=[p for p in assigned if lo<=p[1]<hi]
        labels=positive&(label_ranges>=lo)&(label_ranges<hi)
        covered={p[0] for p in assigned if p[3] and labels[p[0]]}
        bins[name]=dict(predicted=len(pred),tp=sum(p[3] for p in pred),
                       positive=int(labels.sum()),covered=len(covered))
    return bins


def finalize_annotation(counts):
    return {key:dict(v,precision=v['tp']/v['predicted'] if v['predicted'] else None,
        recall=v['covered']/v['positive'] if v['positive'] else None) for key,v in counts.items()}


def score(case,option):
    out=c.OUT/option/case
    receipt=c.read(out/'receipt.json')
    assert receipt['source_hashes']==hashes() and receipt['predictions_sha256']==c.sha(out/'predictions.jsonl')
    # Truth and labels are first opened here, after independent prediction seal.
    ep=c.EPISODES[case]
    truth=c.old.current_truth(ep)
    first=c.old.base.read_rows(ep/'eval_only/trajectory.jsonl')[0]
    start=[*first['robot_xyz_m'][:2],first['robot_yaw_rad']]
    rects=np.array([w['center_m']+w['half_extents_m'] for w in c.read(ep/'inputs/static_map.json')['obstacles'] if w.get('kind')=='wall'])
    annotations={a['frame_id']:a for a in [*c.read(c.ROOT/'experiments/2026-10-07-wall-floor-boundary/annotation-sample.json')['rows'],
        *c.read(c.EXP/'new-annotations.json')['rows']] if a['case']==case}
    data={mode:[] for mode in ('baseline','candidate')}
    annotation_counts={mode:{} for mode in data}
    paired,dr_errors=[],[]
    frames=c.old.base.read_rows(out/'predictions.jsonl')
    with (out/'evaluated-points.jsonl').open('w') as detail:
        for row in frames:
            pose=truth[round(row['t'],6)]
            for mode in data:
                points=row[mode]
                errors=point_errors(points,pose,rects)
                for p,e in zip(points,errors):
                    r=dict(mode=mode,frame_id=row['frame_id'],error_m=float(e),range_m=p['range_m'],
                           confidence=p.get('confidence'),depth_sigma_m=p.get('depth_sigma_m'))
                    data[mode].append(r)
                    write_line(detail,r)
                if row['frame_id'] in annotations:
                    counts=annotate(points,errors,annotations[row['frame_id']],np.array(row['origin']),np.array(row['rotation']))
                    for key,v in counts.items():annotation_counts[mode].setdefault(key,Counter()).update(v)
            # Same candidate pixels, same current GT body: isolate depth method.
            points=row['candidate']
            if points:
                uv=np.array([p['uv'] for p in points])
                xy,_,valid=metric.project(uv,np.array(row['origin']),np.array(row['rotation']),c.old.mp.K)
                floor=c.old.base.boundary_dist(transform(xy[valid],pose),rects)
                errors=point_errors(points,pose,rects)
                paired.extend(zip(errors[valid].tolist(),floor.tolist()))
                own=transform([p['xy'] for p in points],row['pose'])
                dr_errors.extend(c.old.base.boundary_dist(transform(own,start),rects).tolist())
    reports={}
    for mode,rows in data.items():
        bins={}
        for name,lo,hi in [('all',0.,4.000001),('0-2m',0.,2.),('2-3m',2.,3.),('3-4m',3.,4.000001)]:
            use=[r['error_m'] for r in rows if lo<=r['range_m']<hi]
            bins[name]=dict(**stats(use),precision=float(np.mean(np.array(use)<=.15)) if use else None)
        reports[mode]=dict(points=bins,annotated=finalize_annotation(annotation_counts[mode]))
    a,b=reports['candidate']['points']['all'],reports['candidate']['annotated']['all']
    previous=reports['baseline']['points']['all']
    def above(x,v):return x is not None and x>=v
    def below(x,v):return x is not None and x<=v
    checks=dict(precision=above(a['precision'],.9),annotated_precision=above(b['precision'],.9),
        recall=above(b['recall'],.7),median=below(a['median'],.1),p90=below(a['p90'],.25),
        baseline_nondecrease=previous['precision'] is not None and above(a['precision'],previous['precision']),
        labels=b['positive']>=50,annotated_tp=b['tp']>=30,off_golden=True,own_only=True,accepted_positive_depth=True)
    confidence=[]
    for lo,hi in [(0.,.01),(.01,.1),(.1,.5),(.5,1.000001)]:
        use=[r for r in data['candidate'] if r['confidence'] is not None and lo<=r['confidence']<hi]
        confidence.append(dict(lo=lo,hi=hi,n=len(use),precision=float(np.mean([r['error_m']<=.15 for r in use])) if use else None))
    result=dict(case=case,split='development' if case in ('s1042','s1043') else 'confirmation_replay',
        frames=len(frames),reports=reports,checks=checks,passed=all(checks.values()),
        counts=receipt['counts'],same_candidate_pixels=dict(n=len(paired),candidate=stats([a for a,b in paired]),
        floor=stats([b for a,b in paired]),floor_invalid=sum(len(r['candidate']) for r in frames)-len(paired)),
        dr_start_alignment_error=stats(dr_errors),confidence_bins=confidence,
        depth_sigma_m=stats([r['depth_sigma_m'] for r in data['candidate'] if r['depth_sigma_m'] is not None]),
        predictions_sha256=receipt['predictions_sha256'],source_sha=receipt['source_sha'],
        evaluation_sources={str(p):c.sha(p) for p in [ep/'eval_only/trajectory.jsonl',ep/'inputs/static_map.json']})
    c.dump(out/'result.json',result)
    c.dump(c.EXP/'results'/f'{case}.json',result)
    assert c.sha(out/'predictions.jsonl')==receipt['predictions_sha256']
    print(case,'P',a['precision'],'R',b['recall'],'median',a['median'],'PASS',result['passed'],flush=True)


def main():
    p=argparse.ArgumentParser()
    p.add_argument('--split',choices=['development','confirmation'],required=True)
    p.add_argument('--wall-detector',choices=['off','parallax_v1'],default='off')
    p.add_argument('--freeze',type=c.Path)
    args=p.parse_args()
    if args.split=='confirmation':
        f=c.read(args.freeze) if args.freeze else {}
        assert f.get('hashes')==hashes() and f.get('settings')==__import__('json').loads(__import__('json').dumps(settings()))
    cases=['s1042','s1043'] if args.split=='development' else ['s1044','s1045','s1046','s1047','s1050','s1051']
    # All own predictions in this split precede all truth scoring.
    for case in cases:predict(case,args.wall_detector)
    for case in cases:score(case,args.wall_detector)


if __name__=='__main__':main()
