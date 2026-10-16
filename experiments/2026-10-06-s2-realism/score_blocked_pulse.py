"""Evaluation-only scoring AFTER frozen own-observation replay has completed."""
import hashlib,json,sys
from pathlib import Path
import numpy as np

HERE=Path(__file__).resolve().parent

def main(out):
    criteria=json.loads((HERE/'blocked-pulse-criteria.json').read_text());raw=Path(criteria['evaluation']['raw'])
    replay={k:json.loads((out/f'replay-{k}.json').read_text()) for k in ('baseline','candidate')}
    assert all(r['frames']==5202 and not r['gt_inputs'] for r in replay.values())
    truth=[json.loads(l) for l in (raw/'eval_only/trajectory.jsonl').read_text().splitlines()]
    tt=[r['t'] for r in truth];xy=np.array([r['robot_xyz_m'][:2] for r in truth]);lo,hi=criteria['evaluation']['carry_window_sim_s']
    results=[]
    for name,r in replay.items():
        error=[];initial=[]
        for p in r['poses']:
            true=np.array([np.interp(p['t_est'],tt,xy[:,i]) for i in range(2)])
            e=float(np.linalg.norm(np.array([p['x'],p['y']])-true))
            if lo<=p['t']<hi:error.append(e)
            if p['t_est']<12:initial.append(e)
        fixes=[x['t'] for x in r['amcl']['rows'] if lo<=x['t']<hi and x['visual_weight_update']]
        results.append(dict(option=name,carry_rmse_m=float(np.sqrt(np.mean(np.square(error)))),
            carry_updates=len(fixes),max_gap_s=float(max(np.diff([lo,*fixes,hi]))),stationary_max_m=max(initial),
            off_max_difference=r['baseline_max_delta']))
    bundle=json.loads((raw/'bundle.json').read_text());profiles=bundle['pulse_calibration']['profiles']
    pulses=json.loads(Path('/Users/changmin/projects/ugrp/outputs/s2-load-height-20261007/drift-decomposition.json').read_text())['rows']
    progress={round(r['t'],6):r for r in replay['candidate']['visual_progress']['rows']}
    six={107.35,108.30,109.25,110.20,111.15,113.70};motion=[]
    for p in pulses:
        r=progress.get(round(p['t'],6),{});q=np.array(profiles[p['key']]['prediction_variance'])
        effective=np.array(r.get('effective_variance',q));error=np.array(p['actual_delta'])-p['predicted_delta']
        error[2]=(error[2]+np.pi)%(2*np.pi)-np.pi
        nll=lambda v:float(.5*np.sum(np.log(2*np.pi*v)+error*error/v))
        d2=lambda v:float(np.sum(error[:2]**2/v[:2]))
        motion.append(dict(t=p['t'],key=p['key'],blocked_six=round(p['t'],2) in six,
            status=r.get('status','below_registered_motion_size'),alpha=r.get('alpha',1.),
            actual_delta=p['actual_delta'],predicted_delta=p['predicted_delta'],error=error.tolist(),
            old_variance=q.tolist(),effective_variance=effective.tolist(),old_nll=nll(q),new_nll=nll(effective),
            old_xy_d2=d2(q),new_xy_d2=d2(effective),vo=r))
    blocked=[r for r in motion if r['blocked_six']];other=[r for r in motion if not r['blocked_six']]
    assert len(blocked)==6 and len(motion)==277
    motion_score=dict(loaded_pulses=len(motion),old_xy_rmse_m=float(np.sqrt(np.mean([np.dot(r['error'][:2],r['error'][:2]) for r in motion]))),
        old_yaw_rmse_deg=float(np.degrees(np.sqrt(np.mean([r['error'][2]**2 for r in motion])))),
        old_mean_nll=float(np.mean([r['old_nll'] for r in motion])),new_mean_nll=float(np.mean([r['new_nll'] for r in motion])),
        six_xy_3sigma_covered=sum(r['new_xy_d2']<=9 for r in blocked),six_coverage=sum(r['new_xy_d2']<=9 for r in blocked)/6,
        nonblocked_inflation_count=sum(r['alpha']>1 for r in other),nonblocked_count=len(other),
        nonblocked_inflation_fraction=sum(r['alpha']>1 for r in other)/len(other),
        mean_prediction_unchanged=True,vo_status_counts={s:sum(r['status']==s for r in motion) for s in sorted(set(r['status'] for r in motion))})
    motion_score['new_xy_rmse_m']=motion_score['old_xy_rmse_m'];motion_score['new_yaw_rmse_deg']=motion_score['old_yaw_rmse_deg']
    # Unchanged own-command odometry means equal AMCL trigger/candidate times.
    bm=replay['baseline']['measurements'];cm=replay['candidate']['measurements']
    same_points=[(a['t'],a['points_local_m']) for a in bm]==[(a['t'],a['points_local_m']) for a in cm]
    same_filter=replay['baseline']['contact_filter']==replay['candidate']['contact_filter']
    same_visibility=replay['baseline']['visibility']==replay['candidate']['visibility']
    b,c=results;adm=criteria['admission']
    gates=dict(default_off_exact=b['off_max_difference']==0,
        motion_mean_xy_not_worse=motion_score['new_xy_rmse_m']<=motion_score['old_xy_rmse_m'],
        motion_mean_yaw_not_worse=motion_score['new_yaw_rmse_deg']<=motion_score['old_yaw_rmse_deg'],
        motion_nll_better=motion_score['new_mean_nll']<motion_score['old_mean_nll'],
        six_coverage=motion_score['six_coverage']>=adm['six_blocked_xy_3sigma_coverage_min'],
        nonblocked_preservation=motion_score['nonblocked_inflation_fraction']<=adm['nonblocked_inflation_fraction_max'],
        carry_rmse=c['carry_rmse_m']<b['carry_rmse_m'],updates=c['carry_updates']>=adm['carry_updates_min'],
        max_gap=c['max_gap_s']<=adm['max_gap_s']+1e-7,stationary=c['stationary_max_m']<=adm['initial_stationary_max_m'],
        rgb_exact=replay['baseline']['source_hashes']==replay['candidate']['source_hashes'],
        wall_filter_unchanged=same_filter and same_visibility,wall_observation_retention=same_points)
    result=dict(schema='ugrp.s2.blocked_pulse.summary.v1',admission_pass=all(gates.values()),gates=gates,
        results=results,motion=motion_score,six=blocked,observation=dict(points_exact=same_points,filter_exact=same_filter,
            visibility_exact=same_visibility,baseline_candidates=len(bm),candidate_candidates=len(cm)),
        source_sha=replay['candidate']['source_sha'],criteria_sha256=hashlib.sha256((HERE/'blocked-pulse-criteria.json').read_bytes()).hexdigest(),
        physics_runs=0,model_calls=0,new_seed=None,new_bundle=None,
        full_dev='ADMITTED_NOT_YET_RUN' if all(gates.values()) else 'NOT_RUN_CRITERIA_FAILED',
        limits='Fixed-command exploratory replay; covariance only, mean bias not corrected; endpoint NLL is post-pulse conditional calibration, not prospective prediction accuracy. No new lifted/inside/wall-SIM/visibility/B-distance outcomes.')
    with (out/'motion-score.json').open('x') as f:f.write(json.dumps(motion,indent=2)+'\n')
    with (out/'summary.json').open('x') as f:f.write(json.dumps(result,indent=2)+'\n')
    print(json.dumps({k:v for k,v in result.items() if k!='six'},indent=2))

if __name__=='__main__':main(Path(sys.argv[1]))
