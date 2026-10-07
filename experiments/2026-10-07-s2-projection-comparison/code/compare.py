"""Same-frame projection comparison. All GT opens follow own prediction seal."""
import argparse
from collections import defaultdict
import json
from pathlib import Path
import subprocess
import sys
import numpy as np

EXP=Path(__file__).resolve().parents[1]
ROOT=EXP.parents[1]
OUT=Path('/Users/changmin/projects/ugrp/outputs/s2-projection-comparison-v1')
sys.path[:0]=[str(ROOT),str(ROOT/'experiments/2026-10-07-camera-pose-projection/code'),str(Path(__file__).parent)]
import audit as a
from evaluate_fk import gate, CRITERIA
import s2_path


def hashes():
    paths=[EXP/'README.md',EXP/'sources.json',*sorted((EXP/'sources').glob('*')),
           EXP/'code/s2_path.py',EXP/'code/compare.py',
           ROOT/'experiments/2026-10-07-wall-floor-boundary/annotation-sample.json',
           ROOT/'experiments/2026-10-07-camera-pose-projection/code/audit.py',
           ROOT/'experiments/2026-10-07-camera-pose-projection/code/evaluate_fk.py',
           ROOT/'experiments/2026-10-05-ego-wall-map-probe/code/v3_confidence_replay.py']
    return {str(p.relative_to(ROOT)):a.digest(p) for p in paths}


def stats(values):
    out=a.stats(values)
    out['rmse']=float(np.sqrt(np.mean(np.square(values)))) if len(values) else None
    return out


def run(case):
    ep=a.old.EPISODES[case]
    dest=OUT/case
    dest.mkdir(parents=True,exist_ok=False)
    frames,_=a.old.own_inputs(ep,'r3')
    eligibility=a.old.OUT/case/'v3_unloaded_extrinsic_v1/extraction.jsonl'
    eligible={r['frame_id'] for r in a.old.base.read_rows(eligibility) if r['reason']=='calibrated_unloaded'}
    table,models=s2_path.models()
    oldtable=a.old.calibration()
    assert all(models['unloaded'][k]==v for k,v in oldtable['camera_models']['unloaded'].items())
    factories={s:s2_path.column_model_factory(a.old.mp,a.COLS,loaded=s=='loaded') for s in ('unloaded','loaded')}
    cache={}
    own=[]
    for f in frames:
        servo={int(k):int(v) for k,v in f['commanded_servo'].items()}
        key=','.join(str(servo[k]) for k in (3,4,5,6))
        high=key=='896,2035,1894,1500'
        if f['frame_id'] not in eligible and not high:continue
        # HIGH loaded is a command-group counterfactual, not GT load selection.
        states=['unloaded','loaded'] if high else ['unloaded']
        if key not in cache:
            value={}
            for state in states:
                cm=factories[state](servo)
                value[state]=[cm.origin.tolist(),cm._rot.tolist()]
            nominal=a.nominal(servo)
            cache[key]=dict(servo=servo,nominal=[x.tolist() for x in nominal],s2=value)
        own.append(dict(frame_id=f['frame_id'],t=f['sim_time'],key=key,
                        eligible=f['frame_id'] in eligible,high=high,path=f['path'],sha256=f['sha256']))
    prediction=dict(case=case,geometries=cache,frames=own)
    a.write(dest/'own-predictions.json',prediction)
    sealed=a.digest(dest/'own-predictions.json')
    sources={str(p):a.digest(p) for p in (ep/'robots/r3/frames.jsonl',eligibility)}
    a.write(dest/'prediction-source.json',dict(source_sha=subprocess.check_output(['git','rev-parse','HEAD'],text=True).strip(),
        s2_source=s2_path.MANIFEST['ref'],hashes=hashes(),sources=sources,prediction_sha256=sealed))
    # Evaluation-only truth begins here. Never passed to a factory above.
    truth={round(r['t'],6):r for r in a.old.base.read_rows(ep/'eval_only/trajectory.jsonl')}
    actualfile=ep/'eval_only/camera-pose.jsonl'
    actual={round(r['t'],6):r for r in a.old.base.read_rows(actualfile)} if actualfile.exists() else {}
    rects=np.array([w['center_m']+w['half_extents_m'] for w in a.load(ep/'inputs/static_map.json')['obstacles'] if w.get('kind')=='wall'])
    anns=[r for r in a.load(ROOT/'experiments/2026-10-07-wall-floor-boundary/annotation-sample.json')['rows'] if r['case']==case]
    index={r['frame_id']:r for r in own}
    groups=defaultdict(list)
    camera_rows=[]
    rigid_delta=[]
    for f in own:
        g=cache[f['key']]
        nominal=[np.asarray(v) for v in g['nominal']]
        candidate=[np.asarray(v) for v in g['s2']['unloaded']]
        if f['eligible']:
            rigid_delta.append([float(np.max(abs(candidate[i]-nominal[i]))) for i in range(2)])
        t=round(f['t'],6)
        if t not in actual:continue
        ac=a.actual_camera(actual[t],truth[t])
        for state,rigid in g['s2'].items():
            r=[np.asarray(v) for v in rigid]
            diff=np.r_[r[0]-ac[0],(a.angles(r[1])-a.angles(ac[1])+np.pi)%(2*np.pi)-np.pi]
            labels=[]
            if f['eligible'] and state=='unloaded':labels.append('eligible_unloaded')
            if f['high']:labels.append('HIGH_'+state+'_counterfactual')
            for label in labels:
                groups[label].append(diff)
                camera_rows.append(dict(frame_id=f['frame_id'],t=f['t'],group=label,
                    s2_origin=r[0].tolist(),actual_origin=ac[0].tolist(),
                    s2_angles_deg=np.degrees(a.angles(r[1])).tolist(),actual_angles_deg=np.degrees(a.angles(ac[1])).tolist(),
                    difference_xyz_m_angles_rad=diff.tolist()))
    metrics=defaultdict(list)
    distances=defaultdict(list)
    frame_scores=[]
    columns=[]
    count=positive=within=0
    equivalence=[]
    for ann in anns:
        f=index[ann['frame_id']]
        g=cache[f['key']]
        assert f['eligible']
        assert a.digest(ep/f['path'])==f['sha256']
        n=[np.asarray(v) for v in g['nominal']]
        r=[np.asarray(v) for v in g['s2']['unloaded']]
        cm=factories['unloaded'](g['servo'])
        v,ignore=a.annotation_rows(ann)
        uv=np.c_[a.COLS,v]
        xy0,ok0,range0=a.project(uv,*n)
        fixed=np.isfinite(v)&~ignore&ok0&(range0<=4.)
        xy,ok,dist=a.project(uv,*r)
        trace=cm.floor_point(cm.t_of_row(v))
        np.testing.assert_allclose(xy[fixed],trace[fixed],atol=1e-10,rtol=0)
        equivalence.extend(np.linalg.norm(xy[fixed]-trace[fixed],axis=1).tolist())
        t=round(f['t'],6)
        body=truth[t]
        pose=[*body['robot_xyz_m'][:2],body['robot_yaw_rad']]
        count+=int(fixed.sum())
        positive+=int((fixed&ok).sum())
        within+=int((fixed&ok&(dist<=4.)).sum())
        choices={'pr405':(xy0,ok0,range0),'pr406':(xy,ok,dist)}
        if t in actual:choices['actual_oracle']=a.project(uv,*a.actual_camera(actual[t],body))
        fs=dict(frame_id=f['frame_id'],t=f['t'],fixed_points=int(fixed.sum()),metrics={})
        for label,(points,valid,ranges) in choices.items():
            use=fixed&valid
            err=a.old.base.boundary_dist(a.old.transform(points[use],pose),rects)
            metrics[label].extend(err.tolist())
            distances[label].extend(ranges[use].tolist())
            fs['metrics'][label]=stats(err)
            for j,e in zip(np.flatnonzero(use),err):
                columns.append(dict(frame_id=f['frame_id'],column=int(a.COLS[j]),row=float(v[j]),condition=label,
                    range_m=float(ranges[j]),error_m=float(e),xy=points[j].tolist()))
        fs['s2_delta_from_pr405_max_m']=float(np.max(np.linalg.norm(xy[fixed]-xy0[fixed],axis=1)))
        frame_scores.append(fs)
    oldprior=a.load(ROOT/f'experiments/2026-10-07-wall-floor-boundary/results/off/{case}.json')['annotation_projection_error_m']
    assert oldprior['count']==count and abs(oldprior['median']-stats(metrics['pr405'])['median'])<1e-10
    results=dict(case=case,split='development' if case in ('s1042','s1043') else 'confirmation_replay',
        annotation_frames=len(anns),fixed_points=count,positive=positive,within4m=within,
        metrics={k:stats(v) for k,v in metrics.items()},ranges={k:stats(v) for k,v in distances.items()},
        gate=gate(stats(metrics['pr405']),stats(metrics['pr406']),count,positive,within),
        camera_differences={k:{n:stats(np.asarray(v)[:,i]*(1000 if i<3 else 180/np.pi))
            for i,n in enumerate(a.COMPONENTS)} for k,v in groups.items()},
        eligible_rigid_delta_max=np.max(rigid_delta,axis=0).tolist(),
        ray_vs_s2_column_max_m=max(equivalence),
        same_21_unloaded_records=True,new_pose_keys=sorted(set(models['unloaded'])-set(oldtable['camera_models']['unloaded'])),
        frame_scores=frame_scores,prediction_sha256=sealed,physics=0,render=0,models_called=0,runtime_changed=False)
    a.old.rows(dest/'camera-differences.jsonl',camera_rows)
    a.old.rows(dest/'columns.jsonl',columns)
    for p in (ep/'eval_only/trajectory.jsonl',actualfile,ep/'inputs/static_map.json'):
        if p.exists():sources[str(p)]=a.digest(p)
    a.write(dest/'evaluation-sources.json',sources)
    assert a.digest(dest/'own-predictions.json')==sealed
    a.write(dest/'result.json',results)
    a.write(EXP/'results'/f'{case}.json',results)
    print(case,'405/406/oracle',[(k,v['median']) for k,v in results['metrics'].items()],
          'gate',results['gate']['passed'],'rigid_delta',results['eligible_rigid_delta_max'],flush=True)


def main():
    p=argparse.ArgumentParser()
    p.add_argument('--split',choices=['development','confirmation'],required=True)
    p.add_argument('--freeze',type=Path)
    args=p.parse_args()
    if args.split=='confirmation':
        f=a.load(args.freeze) if args.freeze else {}
        assert f.get('hashes')==hashes() and f.get('criteria')==CRITERIA, 'FROZEN_SOURCE_REQUIRED'
    for case in (['s1042','s1043'] if args.split=='development' else ['s1044','s1045','s1046','s1047']):run(case)


if __name__=='__main__':main()
