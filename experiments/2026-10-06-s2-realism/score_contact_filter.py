"""Score frozen contact-filter replays after their predictors are closed."""
import hashlib,json,sys
from pathlib import Path
import numpy as np
HERE=Path(__file__).resolve().parent

def metrics(path,criteria):
    d=json.loads(path.read_text());raw=Path(criteria['source_raw'])
    assert d['frames']==5117 and not d['gt_inputs'] and not d['physics_runs']
    gt=[json.loads(s) for s in (raw/'eval_only/trajectory.jsonl').read_text().splitlines()]
    tt=np.array([g['t'] for g in gt]);xy=np.array([g['robot_xyz_m'][:2] for g in gt])
    lo,hi=criteria['carry_window_sim_s'];errors=[];stationary=[];phase={name:[] for name in ('early_floor','visible_walls','late')}
    for r in d['poses']:
        actual=np.array([np.interp(r['t_est'],tt,xy[:,i]) for i in (0,1)])
        error=float(np.linalg.norm([r['x']-actual[0],r['y']-actual[1]]))
        if lo<=r['t']<hi:
            errors.append(error);phase['early_floor' if r['t']<110 else ('visible_walls' if r['t']<158 else 'late')].append(error)
        if r['t_est']<12:stationary.append(error)
    times=sorted({r['t'] for r in d['amcl']['rows'] if lo<=r['t']<hi and r['visual_weight_update']})
    return dict(option=d['option'],source=str(path),sha256=hashlib.sha256(path.read_bytes()).hexdigest(),
        source_sha=d['source_sha'],candidate_sha256=d['candidate_sha256'],criteria_sha256=d['criteria_sha256'],
        carry_rmse_m=float(np.sqrt(np.mean(np.square(errors)))),carry_end_error_m=errors[-1],
        carry_p90_error_m=float(np.quantile(errors,.9)),carry_updates=len(times),update_times=times,
        max_update_gap_sim_s=float(max(np.diff([lo,*times,hi]))),initial_stationary_max_error_m=max(stationary),
        phase_rmse_m={k:float(np.sqrt(np.mean(np.square(v)))) for k,v in phase.items()},
        contact_attempts=len((d.get('contact_filter') or {}).get('rows',[])),
        removed_contacts=sum(r['removed'] for r in (d.get('contact_filter') or {}).get('rows',[])))

def main(folder,out):
    assert not out.exists();criteria=json.loads((HERE/'contact-filter-criteria.json').read_text())
    a=metrics(folder/'replay-off-final.json',criteria);b=metrics(folder/'replay-floor_appearance_v1.json',criteria)
    off=json.loads((folder/'replay-off-final.json').read_text())
    previous=json.loads(Path('/Users/changmin/projects/ugrp/outputs/s2-observed-amcl-20261007/replay-nav2_observed_v1.json').read_text())
    exact=all(off[k]==previous[k] for k in ('poses','amcl','visibility'))
    assert exact and abs(a['carry_rmse_m']-criteria['admission']['observed_baseline_rmse_m'])<1e-12
    expected=hashlib.sha256((HERE/'contact-filter-criteria.json').read_bytes()).hexdigest()
    assert a['criteria_sha256']==b['criteria_sha256']==expected
    gates=dict(off_exact=exact,rmse=b['carry_rmse_m']<criteria['admission']['carry_rmse_strictly_less_than_m'],
        updates=b['carry_updates']>=criteria['admission']['carry_updates_min'],
        stationary=b['initial_stationary_max_error_m']<=criteria['admission']['initial_stationary_max_error_at_most_m'])
    result=dict(schema='ugrp.s2.contact_filter.summary.v1',admission_pass=all(gates.values()),gates=gates,
        results=[a,b],criteria=criteria,criteria_sha256=expected,physics_runs=0,model_calls=0,
        gt_usage='completed prediction scoring only',new_physical_metrics=None)
    out.write_text(json.dumps(result,indent=2)+'\n');print(json.dumps(dict(gates=gates,results=[a,b])))
if __name__=='__main__':main(*map(Path,sys.argv[1:]))
