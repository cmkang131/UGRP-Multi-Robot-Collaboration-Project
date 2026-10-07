"""Posthoc replay scoring; reads closed prediction files, never controls."""
import hashlib,json,sys
from pathlib import Path
import numpy as np

HERE=Path(__file__).resolve().parent


def main(folder,out):
    assert not out.exists()
    criteria=json.loads((HERE/'observed-amcl-criteria.json').read_text())
    raw=Path(criteria['source_raw']);gt=[json.loads(l) for l in (raw/'eval_only/trajectory.jsonl').read_text().splitlines()]
    tt=np.array([r['t'] for r in gt]);xy=np.array([r['robot_xyz_m'][:2] for r in gt])
    lo,hi=criteria['carry_window_sim_s'];results=[]
    for option in ('off',criteria['candidate']):
        p=folder/f'replay-{option}.json';d=json.loads(p.read_text())
        assert d['frames']==5117 and d['gt_inputs'] is False and d['physics_runs']==0
        assert d['criteria_sha256']==hashlib.sha256((HERE/'observed-amcl-criteria.json').read_bytes()).hexdigest()
        errors=[];stationary=[]
        for r in d['poses']:
            actual=[np.interp(r['t_est'],tt,xy[:,i]) for i in (0,1)]
            error=float(np.linalg.norm(np.array([r['x'],r['y']])-actual))
            if lo<=r['t']<hi:errors.append(error)
            if r['t_est']<12.:stationary.append(error)
        updates=sorted({r['t'] for r in d['amcl']['rows'] if lo<=r['t']<hi and r['visual_weight_update']})
        rmse=float(np.sqrt(np.mean(np.square(errors))))
        results.append(dict(option=option,source=str(p),sha256=hashlib.sha256(p.read_bytes()).hexdigest(),
            candidate_sha256=d['candidate_sha256'],frames=d['frames'],baseline_max_delta=d['baseline_max_delta'],
            initial_stationary_max_error_m=max(stationary),carry_updates=len(updates),
            max_update_gap_sim_s=float(max(np.diff([lo,*updates,hi]))),update_times=updates,
            carry_rmse_m=rmse,carry_end_error_m=errors[-1],carry_p90_error_m=float(np.quantile(errors,.9)),
            mask_attempts=len(d['visibility']['rows']),kept_columns=sum(r['kept'] for r in d['visibility']['rows'])))
    a,b=results;assert abs(a['carry_rmse_m']-criteria['admission']['carry_rmse_strictly_less_than_saved_m'])<1e-12
    passed=(a['baseline_max_delta']<=criteria['baseline_replay_max_pose_delta'] and
        b['carry_updates']>criteria['admission']['carry_updates_strictly_greater_than'] and
        b['carry_rmse_m']<criteria['admission']['carry_rmse_strictly_less_than_saved_m'] and
        b['initial_stationary_max_error_m']<=criteria['admission']['initial_stationary_max_error_at_most_m'])
    result=dict(schema='ugrp.s2.observed_amcl.summary.v1',admission_pass=passed,selected_policy=criteria['candidate'],
        criteria_sha256=hashlib.sha256((HERE/'observed-amcl-criteria.json').read_bytes()).hexdigest(),
        candidate_sha256=b['candidate_sha256'],results=results,physics_runs=0,model_calls=0,
        gt_usage='scoring only, completed predictors closed before this separate process',
        trajectory_sha256=hashlib.sha256((raw/'eval_only/trajectory.jsonl').read_bytes()).hexdigest())
    out.write_text(json.dumps(result,indent=2)+'\n');print(json.dumps(result),flush=True)


if __name__=='__main__':main(*map(Path,sys.argv[1:]))
