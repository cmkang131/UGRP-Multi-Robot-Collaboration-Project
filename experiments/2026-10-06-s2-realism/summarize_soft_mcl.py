"""Separate posthoc GT evaluator; no importing this module into the PF replay."""
import json,sys
from pathlib import Path
import numpy as np
sys.path.insert(0,str(Path(__file__).resolve().parent))
import replay_soft_mcl as m
old=m.old
BASE=old.RAW/'s2-unloaded-sag-replay-20261007'


def update_metrics(times,window):
    start,end=window;times=sorted(set(t for t in times if start<=t<end))
    independent=[]
    for t in times:
        if not independent or t-independent[-1]>=m.CRITERIA['independent_spacing_sim_s']-1e-9:independent.append(t)
    gap=float(max(np.diff([start,*times,end])))
    return dict(updates=len(times),independent_updates=len(independent),max_update_gap_sim_s=gap,
                frequency_pass=len(independent)>=m.CRITERIA['min_independent_updates'] and gap<=m.CRITERIA['max_update_gap_sim_s'])


def accuracy(errors):
    a=np.array(errors,float)
    if not len(a) or not np.isfinite(a).all():raise ValueError('missing/nonfinite carry score')
    return dict(n=len(a),rmse_m=float(np.sqrt(np.mean(a*a))),p50_m=float(np.median(a)),p90_m=float(np.quantile(a,.9)),end_m=float(a[-1]))


def accuracy_pass(candidate,baselines):
    return all(candidate['rmse_m']<b['rmse_m'] and candidate['p90_m']<=b['p90_m'] for b in baselines)


def summarize(out):
    dest=out/'summary.json'
    if dest.exists():raise FileExistsError(dest)
    entries=[];hashes={};all_pass=True
    for seed,sha in old.RUNS.items():
        raw=old.RAW/f's2-realism-{sha}-s{seed}-P1-2-place'
        truth_path=raw/'eval_only/trajectory.jsonl';hashes[str(truth_path)]=old.digest(truth_path)
        truth=[json.loads(l) for l in truth_path.read_text().splitlines()]
        source_poses=json.loads((raw/'student_record.json').read_text())['poses'];estimate_times={p['t']:p['t_est'] for p in source_poses}
        ts=np.array([g['t'] for g in truth]);xy=np.array([g['robot_xyz_m'][:2] for g in truth]);comparisons=[]
        for variant in [*m.CRITERIA['comparison'],m.OPTION]:
            path=(out if variant==m.OPTION else BASE)/f's{seed}-{variant}.json'
            r=json.loads(path.read_text());hashes[str(path)]=old.digest(path)
            assert r['gt_inputs'] is False and r['commands_fixed'] is True
            for p,sha in r['source_hashes'].items():assert old.digest(raw/p)==sha
            if variant==m.OPTION:
                assert r['criteria_sha256']==old.digest(old.HERE/'soft-mcl-criteria.json')
                assert r['approximation']==old.approximation(m.CRITERIA['camera_variant'])
                assert r['soft_measurement']['parameters']==m.PARAMS
                window=r['carry_window']
                updates=update_metrics([a['t'] for a in r['soft_measurement']['rows'] if a['visual_weight_update']],window)
            else:
                assert r['criteria_sha256']==old.digest(old.HERE/'unloaded-sag-criteria.json')
                if variant=='legacy':assert r['baseline_mismatches']==0 and r['baseline_max_pose_delta']==0
                else:assert r['approximation']==old.approximation(m.CRITERIA['camera_variant'])
                window=r['metrics']['carry_window']
                updates=update_metrics([p['last_fix_t'] for p in r['rows'] if p['last_fix_t'] is not None],window)
            start,end=window;carry=[p for p in r['rows'] if start<=p['t']<end];errors=[]
            for p in carry:
                t=p.get('t_est',estimate_times[p['t']]);actual=np.array([np.interp(t,ts,xy[:,i]) for i in (0,1)])
                errors.append(float(np.linalg.norm(np.array([p['x'],p['y']])-actual)))
            entry=dict(seed=seed,variant=variant,carry_window=window,**updates,accuracy=accuracy(errors),
                measurement_receipt='soft weight update, not absolute fix' if variant==m.OPTION else 'legacy hard receipt')
            entries.append(entry);comparisons.append(entry)
        candidate=comparisons[-1]
        candidate['accuracy_pass']=accuracy_pass(candidate['accuracy'],[b['accuracy'] for b in comparisons[:-1]])
        candidate['admission_pass']=candidate['frequency_pass'] and candidate['accuracy_pass'];all_pass &= candidate['admission_pass']
    geometry=out/'residual-decomposition.json';hashes[str(geometry)]=old.digest(geometry)
    d=json.loads(geometry.read_text());decomp={k:v for k,v in d.items() if k!='rows'}
    for s in decomp['summaries']:
        rs=[r for r in d['rows'] if r['seed']==s['seed']]
        s['detected_columns']=sum(r['columns'] for r in rs)
        s['actual_wall_outside_columns']=sum(r['actual_wall_outside_columns'] for r in rs)
    result=dict(schema='ugrp.s2.soft_mcl.summary.v1',criteria_commit='9a38ae45',candidate_commit='dc1ed79b',
        criteria=m.CRITERIA,rows=entries,residual_decomposition=decomp,
        full_dev_permitted=bool(all_pass),physical_runs=0,model_calls=0,new_seed=None,
        baseline_reproduction='prior full legacy replay max delta 0; default-off byte tests passed',
        source_hashes=hashes,scope='fixed saved commands; GT only separate scoring, no closed-loop/mission claim')
    with dest.open('x') as f:json.dump(result,f,indent=2)
    print(json.dumps(dict(rows=entries,full_dev_permitted=bool(all_pass)),indent=2))


if __name__=='__main__':summarize(Path(sys.argv[1]))
