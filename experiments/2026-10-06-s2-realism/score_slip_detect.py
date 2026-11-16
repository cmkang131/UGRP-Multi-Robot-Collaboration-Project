"""Evaluation-only scorer, invoked only after frozen own-RGB replay is closed."""
import hashlib,json,sys
from pathlib import Path
import numpy as np

HERE=Path(__file__).resolve().parent
SIX={107.35,108.30,109.25,110.20,111.15,113.70}

def main(out,destination=None):
    destination=out if destination is None else destination
    destination.mkdir(parents=True,exist_ok=True)
    criteria=json.loads((HERE/'slip-detect-criteria.json').read_text());raw=Path(criteria['evaluation']['raw'])
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
    pulses=json.loads(Path('/Users/changmin/projects/ugrp/outputs/s2-load-height-20261007/drift-decomposition.json').read_text())['rows']
    vo={round(r['t'],6):r for r in replay['candidate']['slip_detection']['rows']};motion=[]
    for p in pulses:
        row=vo.get(round(p['t'],6),{});new=row.get('applied_delta',p['predicted_delta']) if row.get('prediction_replaced') else p['predicted_delta']
        errors=[np.array(delta)-p['actual_delta'] for delta in (p['predicted_delta'],new)]
        for e in errors:e[2]=(e[2]+np.pi)%(2*np.pi)-np.pi
        motion.append(dict(t=p['t'],key=p['key'],blocked_six=round(p['t'],2) in SIX,
            actual_delta=p['actual_delta'],old_prediction=p['predicted_delta'],new_prediction=new,
            old_error=errors[0].tolist(),new_error=errors[1].tolist(),coverage=row.get('coverage',0.),
            status=row.get('status','outside_coarse_scope'),variance=row.get('variance'),
            replaced=row.get('prediction_replaced',False),progress_ratio=row.get('progress_ratio'),
            pitch_radial_sigma_m=row.get('pitch_radial_sigma_m'),
            unchanged_profile_exact=row.get('unchanged_profile_exact',True),
            intervals=[{k:v for k,v in i.items() if k not in ('before_uv','after_uv')} for i in row.get('intervals',[])]))
    blocked=[r for r in motion if r['blocked_six']];other=[r for r in motion if not r['blocked_six']]
    assert len(blocked)==6 and len(motion)==277
    def rmse(rows,key,axis):return float(np.sqrt(np.mean([np.dot(np.array(r[key])[axis],np.array(r[key])[axis]) for r in rows])))
    ms=dict(loaded_pulses=len(motion),nonblocked_pulses=len(other),
        old_xy_rmse_m=rmse(motion,'old_error',slice(0,2)),new_xy_rmse_m=rmse(motion,'new_error',slice(0,2)),
        nonblocked_old_xy_rmse_m=rmse(other,'old_error',slice(0,2)),nonblocked_new_xy_rmse_m=rmse(other,'new_error',slice(0,2)),
        six_old_yaw_rmse_deg=float(np.degrees(rmse(blocked,'old_error',slice(2,3)))),six_new_yaw_rmse_deg=float(np.degrees(rmse(blocked,'new_error',slice(2,3)))),
        six_replacement_count=sum(r['replaced'] for r in blocked),six_error_pass_count=sum(np.linalg.norm(r['new_error'][:2])<=.035 for r in blocked),
        six_error_median_m=float(np.median([np.linalg.norm(r['new_error'][:2]) for r in blocked])),
        measured_intervals=sum(i['status']=='measured' for r in vo.values() for i in r.get('intervals',[])),
        interval_status_counts={status:sum(i['status']==status for r in vo.values() for i in r.get('intervals',[]))
            for status in sorted({i['status'] for r in vo.values() for i in r.get('intervals',[])})})
    bm={r['t']:r for r in replay['baseline']['measurements']};cm={r['t']:r for r in replay['candidate']['measurements']}
    common=sorted(bm.keys()&cm.keys())
    same_points=bool(common) and all(bm[t]['points_local_m']==cm[t]['points_local_m'] for t in common)
    shadow=replay['candidate']['shadow_recovery'];inhibited=[r['t'] for r in shadow['attempts'] if r['would_inhibit']]
    # First/second blocked attempts may trigger only after their end images.
    before_fourth=any(t<=110.20+1e-7 for t in inhibited)
    b,c=results;adm=criteria['admission']
    gates=dict(default_off_exact=b['off_max_difference']==0.,six_replacements=ms['six_replacement_count']>=adm['six_replacements_min'],
        normal_profiles_exact=all(r['unchanged_profile_exact'] for r in motion if not r['replaced']),
        six_endpoint_error=ms['six_error_pass_count']>=adm['six_endpoint_error_at_most_035_min_count'],six_median_error=ms['six_error_median_m']<=adm['six_endpoint_error_median_max_m'],
        six_yaw_not_worse=ms['six_new_yaw_rmse_deg']<=ms['six_old_yaw_rmse_deg'],
        loaded_xy_better=ms['new_xy_rmse_m']<ms['old_xy_rmse_m'],nonblocked_not_worse=ms['nonblocked_new_xy_rmse_m']<=ms['nonblocked_old_xy_rmse_m']+1e-10,
        carry_rmse=c['carry_rmse_m']<b['carry_rmse_m'],updates=c['carry_updates']>=adm['carry_updates_min'],
        max_gap=c['max_gap_s']<=adm['max_gap_s']+1e-7,stationary=c['stationary_max_m']<=adm['initial_stationary_max_m'],
        rgb_exact=replay['baseline']['source_hashes']==replay['candidate']['source_hashes'],wall_observation_retention=same_points,
        shadow_before_fourth=before_fourth)
    result=dict(schema='ugrp.s2.slip_detect.summary.v1',admission_pass=all(gates.values()),gates=gates,results=results,motion=ms,
        six=[{k:v for k,v in r.items() if k!='intervals'} for r in blocked],shadow=dict(events=shadow['rows'],inhibited_attempt_count=len(inhibited),first_inhibited_t=min(inhibited) if inhibited else None),
        observation=dict(common_candidates=len(common),common_points_exact=same_points,baseline_candidates=len(bm),candidate_candidates=len(cm),buffered_frames=replay['candidate']['slip_detection']['buffered_frames'],dropped_wall_frames=0),
        replacements=sum(r['replaced'] for r in motion),
        pitch_scale_bound_deg=criteria['parameters']['pitch_scale_bound_deg'],
        source_sha=replay['candidate']['source_sha'],criteria_sha256=hashlib.sha256((HERE/'slip-detect-criteria.json').read_bytes()).hexdigest(),physics_runs=0,model_calls=0,new_seed=None,new_bundle=None,
        full_dev='ADMITTED_NOT_YET_RUN' if all(gates.values()) else 'NOT_RUN_CRITERIA_FAILED',
        limits='Fixed-command exploratory replay. Recovery is shadow only; actual escape not proven. No new lifted/inside/wall-SIM/visibility/B-distance outcomes. Incomplete visual pulses keep the entire fixed command profile unchanged; no command-filled visual displacement.')
    for filename,obj in [('motion-score.json',motion),('summary.json',result)]:
        data=json.dumps(obj,indent=2,default=lambda value:value.item())+'\n'
        with (destination/filename).open('x') as f:f.write(data)
    print(json.dumps({k:v for k,v in result.items() if k not in ('six','pitch')},indent=2,default=lambda value:value.item()))

if __name__=='__main__':main(Path(sys.argv[1]),Path(sys.argv[2]) if len(sys.argv)>2 else None)
