"""Source-VM Monte Carlo replay of Nav2 AMCL, no new physics or renderer.

Stages isolate own-input preparation, EVALUATION-ONLY coarse-prior generation,
sealed prediction, and scoring. The coordinator's 2026-10-17 ops directive
authorizes conditional synthetic .5m boxes / +/-30deg priors for old recordings.
These are NOT recorded operator priors or evidence of physical success.
"""
import argparse
from collections import Counter
from concurrent.futures import ProcessPoolExecutor
import hashlib
import json
import math
from pathlib import Path
import platform
import subprocess
import sys

ROOT=Path(__file__).resolve().parents[1]
BASE=Path('/home/ugrp/ugrp-sim')


def raw(p):
    return p.read_bytes() if p.exists() else subprocess.check_output(['zstd','-qdc',str(p)+'.zst'])


def read(p):return json.loads(raw(p))
def sha(p):return hashlib.sha256(raw(p)).hexdigest()
def dump(p,v):
    with p.open('x') as f:json.dump(v,f,indent=2,allow_nan=False);f.write('\n')


def make_prior(evaluation_pose, static, rng, zone_id):
    """EVALUATOR ONLY: truth's relative box position is uniform, never centered.

    .5m and pi/6 come directly from coordinator ops; not tuned against errors.
    No offsets, truth pose or generator seed are returned to the predictor.
    """
    from harness.mapbuild_start_zone import SCHEMA
    import numpy as np
    x,y,yaw=evaluation_pose
    u=rng.uniform(size=3)
    xmin,ymin=x-.5*u[0],y-.5*u[1]
    heading=yaw-(2*u[2]-1)*math.pi/6
    heading=float(np.arctan2(np.sin(heading),np.cos(heading)))
    return dict(schema=SCHEMA,zone_id=zone_id,map_id=static['map_id'],
        bounds_m=[float(xmin),float(xmin+.5),float(ymin),float(ymin+.5)],
        heading_center_rad=heading,heading_half_width_rad=math.pi/6,
        source_kind='operator_coarse',source_evidence='coordinator ops 2026-10-17; EVALUATION-DERIVED conditional MC prior, not an original operator region')


def prepare_own(a):
    import numpy as np
    from harness.e2e_rgb_vo import between,compose
    a.work.mkdir(parents=True,exist_ok=False);streams=[];sources={};rgb_n=0;max_recompose=0.
    def load(p):sources[str(p)]=sha(p);return read(p)
    if a.host=='gcp5':
        inputs=[]
        for r in (1,2,3):
            inp=BASE/f'runs/mapbuild8/recording-r{r}';pred=BASE/f'runs/mapbuild9/r{r}-likelihood_product_v1-slots'
            own=load(inp/'own.json')['frames'];scans=load(BASE/'runs/mapbuild8/replay-r1-v2/scans.json' if r==1 else inp/'scans.json')
            inputs.append((f'r{r}',inp,load(inp/'static-map.json'),own,load(pred/'trajectory.json'),scans,None,None))
    else:
        inp=BASE/'runs/warp8/selfmap-open-r1';spec=load(inp/'own-inputs.json');inputs=[]
        for w in spec['worlds']:
            for rid,own in w['robots'].items():
                pred=BASE/f"runs/warp8/mapbuild9-amcl-v1/world-{w['world']:03d}-{rid}"
                inputs.append((f"w{w['world']:03d}-{rid}",inp,load(inp/w['static']),own,load(pred/'trajectory.json'),load(pred/'scans.json'),w['world'],rid))
    for name,inp,static,own,pred,scans,world,rid in inputs:
        if not len(own)==len(pred)==len(scans):raise ValueError('FRAME_JOIN_REQUIRED')
        frames=[];last=np.zeros(3)
        for k,(f,r,s) in enumerate(zip(own,pred,scans)):
            if f['t']!=r['t']:raise ValueError('TIME_JOIN_REQUIRED')
            rgb=inp/f['rgb'];expected=f.get('sha256',f.get('rgb_sha256'))
            if sha(rgb)!=expected:raise ValueError('RGB_CHANGED')
            rgb_n+=1
            pose=np.asarray(r['off_pose']);delta=between(last,pose)
            max_recompose=max(max_recompose,float(np.max(abs(compose(last,delta)-pose))))
            frames.append(dict(t=f['t'],frame_id=f.get('frame_id',k),servo=f['servo'],scan=s,
                own_delta=delta.tolist(),off_pose=pose.tolist()))
            last=pose
        streams.append(dict(id=name,static=static,frames=frames,evaluation_source=str(inp/'eval-only.json'),world=world,rid=rid))
    value=dict(host=a.host,streams=streams,source_sha256=sources,rgb_sha_checked=rgb_n,
        source='sealed mapbuild9 own OFF trajectory + original own scan/servo; no evaluation state opened',
        motion_recomposition_max_abs=max_recompose,truth_inputs=0,physics_steps=0,reproduction=sys.argv)
    dump(a.work/'own-streams.json',value)
    dump(a.work/'own-seal.json',dict(own_streams_sha256=sha(a.work/'own-streams.json'),sources=sources,rgb_sha_checked=rgb_n,truth_inputs=0))
    print(json.dumps(dict(host=a.host,streams=len(streams),frames=sum(len(s['frames']) for s in streams),rgb_sha_checked=rgb_n,motion_recomposition_max_abs=max_recompose)),flush=True)


def truth_for(s):
    j=read(Path(s['evaluation_source']))
    if s['world'] is None:
        gt=j['frames'];poses=[r['pose'] for r in gt]
    else:
        gt=[r for r in j['rows'] if r['world']==s['world'] and r['rid']==s['rid']];poses=[r['truth_pose'] for r in gt]
    if len(gt)!=len(s['frames']) or [r['t'] for r in gt]!=[r['t'] for r in s['frames']]:raise ValueError('EVALUATION_JOIN_REQUIRED')
    return poses


def prepare_priors(a):
    import numpy as np
    own=read(a.work/'own-streams.json');rng=np.random.default_rng(a.prior_seed);priors={};offsets=[]
    for s in own['streams']:
        initial=truth_for(s)[0];entries=[]
        for trial in range(a.trials):
            p=make_prior(initial,s['static'],rng,f"synthetic-{s['id']}-{trial:03d}")
            entries.append(p)
            # Never put exact within-box offsets in the predictor's prior file.
            offsets.append(dict(stream=s['id'],trial=trial,
                relative_x=(initial[0]-p['bounds_m'][0])/.5,relative_y=(initial[1]-p['bounds_m'][2])/.5,
                relative_yaw=float(np.arctan2(np.sin(initial[2]-p['heading_center_rad']),np.cos(initial[2]-p['heading_center_rad'])))/(math.pi/6)))
        priors[s['id']]=entries
    dump(a.work/'priors.json',dict(streams=priors,trials=a.trials,
        scope='evaluation-derived conditional uncertainty boxes; not original operator regions; no exact pose or within-box offsets'))
    dump(a.work/'prior-generation-eval-only.json',dict(prior_seed=a.prior_seed,trials=a.trials,relative_positions=offsets,
        truth_sources={s['evaluation_source']:sha(Path(s['evaluation_source'])) for s in own['streams']},
        priors_sha256=sha(a.work/'priors.json'),reproduction=sys.argv,
        boundary='This process uses truth ONLY to generate coarse boxes. Predictor never opens this file/evaluation sources.'))
    print(json.dumps(dict(priors=len(offsets),trials=a.trials,scope='SYNTHETIC_CONDITIONAL_PRIORS')),flush=True)


_data=None
def worker_init(work,calibration,requirements):
    global _data
    own=read(Path(work)/'own-streams.json')
    _data=({s['id']:s for s in own['streams']},read(Path(work)/'priors.json'),read(Path(calibration)),read(Path(requirements)),Path(work))


def predict_job(job):
    import numpy as np
    from harness.mapbuild_amcl import StaticAMCL,OPTION
    from harness.e2e_rgb_vo import between,compose
    streams,priors,cal,req,work=_data
    name,trial,mode=job;s=streams[name]
    kwargs=dict(profile='nav2_defaults_v1',option=OPTION,seed=2026101700+trial)
    if mode=='coarse':kwargs.update(initial_prior_option='start_zone_prior_v1',initial_prior=priors['streams'][name][trial])
    amcl=StaticAMCL(s['static'],cal,req,**kwargs);rows=[]
    for f in s['frames']:
        e=amcl.step(f['t'],f['frame_id'],f['own_delta'],f['scan'],servo=f['servo'])
        p=compose(amcl.current['candidate_pose'],between(amcl.sensor_odom,amcl.odom)).tolist() if amcl.current else None
        rows.append(dict(t=f['t'],frame_id=f['frame_id'],candidate=p,ready=e['converged'],attempted=e['attempted'],
            reason=e['reason'],xy95=e.get('xy_p95_m'),yaw95=e.get('yaw_p95_rad'),ess=e.get('ess')))
    folder=work/'predictions';file=folder/f'{name}-{mode}-{trial:03d}.json'
    dump(file,dict(stream=name,trial=trial,mode=mode,particle_seed=2026101700+trial,rows=rows,
        own_map_frames=len(amcl.local_map),runtime_qualified=False,ready_for_handoff=False,adopted_pose=None))
    if trial==0 and mode=='coarse':dump(folder/f'{name}-own-map.json',amcl.local_map)
    return dict(stream=name,trial=trial,mode=mode,file=file.name,sha256=sha(file),
        frames=len(rows),updates=sum(r['attempted'] for r in rows),ready_updates=sum(r['ready'] for r in rows),
        own_map_frames=len(amcl.local_map),reasons=dict(Counter(r['reason'] for r in rows)))


def predict(a):
    own=read(a.work/'own-streams.json');seal=read(a.work/'own-seal.json')
    if sha(a.work/'own-streams.json')!=seal['own_streams_sha256']:raise ValueError('OWN_INPUT_CHANGED')
    if not Path(read(a.queue)['rejection_table']).is_file():raise ValueError('FUNNEL_REQUIRED')
    if not read(a.stack_check).get('ok'):raise ValueError('HISTORICAL_STACK_CHECK_REQUIRED')
    (a.work/'predictions').mkdir(exist_ok=False)
    jobs=[(s['id'],t,mode) for mode in ('coarse','global') for s in own['streams'] for t in range(a.trials)]
    with ProcessPoolExecutor(max_workers=a.workers,initializer=worker_init,initargs=(a.work,a.calibration,a.requirements)) as pool:
        result=list(pool.map(predict_job,jobs))
    dump(a.work/'predictions/index.json',result)
    files={p.name:sha(p) for p in sorted((a.work/'predictions').glob('*.json'))}
    inputs=[a.work/'own-streams.json',a.work/'own-seal.json',a.work/'priors.json',a.calibration,a.requirements,a.queue,a.stack_check,
        ROOT/'harness/mapbuild_amcl.py',ROOT/'harness/mapbuild_start_zone.py',ROOT/'harness/mapbuild_amcl_vendor/algorithms.py',Path(__file__)]
    dump(a.work/'prediction-seal.json',dict(input_sha256={str(p):sha(p) for p in inputs},prediction_sha256=files,
        exact_truth_inputs=0,prior_scope='coarse boxes generated by separate evaluation-only process',physics_steps=0,
        cases=len(result),reproduction=sys.argv))
    print(json.dumps(dict(cases=len(result),host=a.host,predictions_sealed=True)),flush=True)


def evaluate_case(rows,poses,off_poses,req):
    import numpy as np
    from harness.e2e_rgb_vo import compose
    world=np.asarray(poses);off=np.array([compose(world[0],p) for p in off_poses])
    pred=np.array([r['candidate'] if r['candidate'] is not None else [np.nan]*3 for r in rows]);has=np.isfinite(pred).all(1)
    def errors(p):
        d=p-world;xy=np.linalg.norm(d[:,:2],axis=1);yaw=abs(np.arctan2(np.sin(d[:,2]),np.cos(d[:,2])))
        return xy,yaw,yaw+np.arctan2(xy,req['nominal_target_range_m']-xy)
    oe=errors(off);pe=errors(pred);ready=np.array([r['ready'] for r in rows]);first=np.flatnonzero(ready)
    within=(pe[0]<=req['position_error_m'])&(pe[2]<=req['yaw_error_rad']);wrong=ready&~within
    since=np.arange(len(rows))>=first[0] if len(first) else np.zeros(len(rows),bool)
    off_after=float(np.sqrt(np.mean(oe[0][since]**2))) if since.any() else None
    amcl_after=float(np.sqrt(np.mean(pe[0][since&has]**2))) if (since&has).any() else None
    passed=bool(len(first) and not wrong.any() and np.all(within[since&has]) and amcl_after<off_after)
    ownpath=np.r_[0,np.cumsum(np.linalg.norm(np.diff(np.asarray(off_poses)[:,:2],axis=0),axis=1))]
    segments=[]
    for start in range(0,int(rows[-1]['t'])+1,10):
        mask=np.array([start<=r['t']<start+10 for r in rows])&has
        if mask.any():segments.append(dict(start_sim_s=start,xy_rmse_m=float(np.sqrt(np.mean(pe[0][mask]**2))),off_xy_rmse_m=float(np.sqrt(np.mean(oe[0][mask]**2)))))
    return dict(ready_updates=int(ready.sum()),wrong_ready_updates=int(wrong.sum()),
        first_converged_sim_s=rows[int(first[0])]['t'] if len(first) else None,
        first_converged_own_path_m=float(ownpath[int(first[0])]) if len(first) else None,
        final_xy_m=float(pe[0][-1]) if has[-1] else None,final_yaw_deg=float(np.degrees(pe[1][-1])) if has[-1] else None,
        final_handoff_pass=bool(within[-1]) if has[-1] else False,xy_rmse_m=float(np.sqrt(np.mean(pe[0][has]**2))) if has.any() else None,
        off_final_xy_m=float(oe[0][-1]),off_final_yaw_deg=float(np.degrees(oe[1][-1])),off_xy_rmse_m=float(np.sqrt(np.mean(oe[0]**2))),
        since_convergence_off_rmse_m=off_after,since_convergence_amcl_rmse_m=amcl_after,offline_pass=passed,segments=segments)


def score(a):
    import numpy as np
    seal=read(a.work/'prediction-seal.json')
    for p,h in seal['input_sha256'].items():
        if sha(Path(p))!=h:raise ValueError('INPUT_CHANGED')
    for p,h in seal['prediction_sha256'].items():
        if sha(a.work/'predictions'/p)!=h:raise ValueError('PREDICTION_CHANGED')
    own=read(a.work/'own-streams.json');streams={s['id']:s for s in own['streams']};gt={k:truth_for(v) for k,v in streams.items()}
    req=read(a.requirements)['handoff'];results=[]
    for ix in read(a.work/'predictions/index.json'):
        p=read(a.work/'predictions'/ix['file']);s=streams[p['stream']]
        result=evaluate_case(p['rows'],gt[s['id']],[f['off_pose'] for f in s['frames']],req)
        results.append(dict(stream=s['id'],trial=p['trial'],mode=p['mode'],**result))
    aggregates=[]
    for name in streams:
        for mode in ('coarse','global'):
            rs=[r for r in results if r['stream']==name and r['mode']==mode]
            def percentiles(key):
                v=[r[key] for r in rs if r[key] is not None]
                return dict(n=len(v),median=float(np.median(v)),p90=float(np.percentile(v,90))) if v else dict(n=0,median=None,p90=None)
            aggregates.append(dict(stream=name,mode=mode,trials=len(rs),converged_trials=sum(r['ready_updates']>0 for r in rs),
                wrong_converged_trials=sum(r['wrong_ready_updates']>0 for r in rs),wrong_ready_updates=sum(r['wrong_ready_updates'] for r in rs),
                offline_pass_trials=sum(r['offline_pass'] for r in rs),final_handoff_pass_trials=sum(r['final_handoff_pass'] for r in rs),
                final_xy_m=percentiles('final_xy_m'),final_yaw_deg=percentiles('final_yaw_deg'),xy_rmse_m=percentiles('xy_rmse_m'),
                convergence_sim_s=percentiles('first_converged_sim_s'),convergence_own_path_m=percentiles('first_converged_own_path_m'),
                off_final_xy_m=rs[0]['off_final_xy_m'],off_final_yaw_deg=rs[0]['off_final_yaw_deg'],off_xy_rmse_m=rs[0]['off_xy_rmse_m']))
    dump(a.work/'evaluation.json',dict(host=a.host,scope='conditional synthetic coarse priors; no actual operator prior, no physical success',
        trials=a.trials,results=results,aggregates=aggregates,physics_steps=0,new_physical_runs=0,
        prediction_seal_sha256=sha(a.work/'prediction-seal.json'),requirements_sha256=sha(a.requirements),reproduction=sys.argv))
    table=dict(source=str(a.work),reproduction=sys.argv,cohorts=[],distribution=[])
    for mode in ('coarse','global'):
        rs=[r for r in results if r['mode']==mode];con=sum(r['ready_updates']>0 for r in rs);correct=sum(r['ready_updates']>0 and not r['wrong_ready_updates'] for r in rs);passed=sum(r['offline_pass'] for r in rs)
        table['cohorts'].append(dict(mode=mode,stages=[dict(stage='case_replays',cumulative_pass_n=len(rs),rejected_n=0),dict(stage='convergence',cumulative_pass_n=con,rejected_n=len(rs)-con),dict(stage='no_wrong_convergence',cumulative_pass_n=correct,rejected_n=con-correct),dict(stage='existing_OFF_improvement_and_requirement_gate',cumulative_pass_n=passed,rejected_n=correct-passed)]))
        for reason,count in [('unresolved',len(rs)-con),('wrong_convergence',con-correct),('OFF_improvement_or_requirement_failure',correct-passed)]:
            table['distribution'].append(dict(mode=mode,reason_category=reason,reason=reason,n=count,blocked_object='static_wall_likelihood_and_motion_uncertainty',minimum_gap_m=None,gap_status='not_measured'))
    dump(a.work/'rejection_table.json',table)
    dump(a.work/'summary.json',dict(host=a.host,trials=a.trials,streams=len(streams),cases=len(results),aggregates=aggregates,
        status='OFFLINE_PASS' if all(r['offline_pass'] for r in results if r['mode']=='coarse') else 'NOT_READY',
        scope='synthetic conditional prior only; no physical success; direct exact truth to estimator=0; evaluation truth used for coarse box placement',
        new_physical_runs=0,rejection_table=str(a.work/'rejection_table.json')))
    print(json.dumps(aggregates),flush=True)


if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('--stage',choices=['prepare-own','prepare-priors','predict','score'],required=True)
    p.add_argument('--host',choices=['gcp5','gcp3'],required=True);p.add_argument('--work',type=Path,required=True)
    p.add_argument('--trials',type=int,default=20);p.add_argument('--prior-seed',type=int,default=46820261017)
    p.add_argument('--workers',type=int,default=4)
    for name in ('calibration','requirements','queue','stack-check'):p.add_argument('--'+name,type=Path)
    a=p.parse_args()
    if a.trials<20:raise ValueError('COORDINATOR_MINIMUM_20_MC_TRIALS')
    if not platform.node().startswith('ugrp-act-l4-'+a.host):raise ValueError('SOURCE_VM_ONLY')
    sys.path.insert(0,str(ROOT))
    {'prepare-own':prepare_own,'prepare-priors':prepare_priors,'predict':predict,'score':score}[a.stage](a)
