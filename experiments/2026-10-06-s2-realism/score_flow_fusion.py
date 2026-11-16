"""Evaluation-only scorer, invoked only after frozen own-RGB replay is closed."""
import hashlib,json,sys
from pathlib import Path
import numpy as np

HERE=Path(__file__).resolve().parent
SIX={107.35,108.30,109.25,110.20,111.15,113.70}

def main(out,destination=None):
    destination=out if destination is None else destination
    destination.mkdir(parents=True,exist_ok=True)
    criteria=json.loads((HERE/'flow-fusion-criteria.json').read_text());raw=Path(criteria['evaluation']['raw'])
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
    vo={round(r['t'],6):r for r in replay['candidate']['visual_odometry']['rows']};motion=[]
    for p in pulses:
        row=vo.get(round(p['t'],6),{});new=row.get('delta',p['predicted_delta']) if row.get('prediction_replaced') else p['predicted_delta']
        errors=[np.array(delta)-p['actual_delta'] for delta in (p['predicted_delta'],new)]
        for e in errors:e[2]=(e[2]+np.pi)%(2*np.pi)-np.pi
        motion.append(dict(t=p['t'],key=p['key'],blocked_six=round(p['t'],2) in SIX,
            actual_delta=p['actual_delta'],old_prediction=p['predicted_delta'],new_prediction=new,
            old_error=errors[0].tolist(),new_error=errors[1].tolist(),coverage=row.get('coverage',0.),
            status=row.get('status','outside_coarse_scope'),variance=row.get('variance'),
            intervals=[{k:v for k,v in i.items() if k not in ('before_uv','after_uv')} for i in row.get('intervals',[])]))
    blocked=[r for r in motion if r['blocked_six']];other=[r for r in motion if not r['blocked_six']]
    assert len(blocked)==6 and len(motion)==277
    def rmse(rows,key,axis):return float(np.sqrt(np.mean([np.dot(np.array(r[key])[axis],np.array(r[key])[axis]) for r in rows])))
    ms=dict(loaded_pulses=len(motion),nonblocked_pulses=len(other),
        old_xy_rmse_m=rmse(motion,'old_error',slice(0,2)),new_xy_rmse_m=rmse(motion,'new_error',slice(0,2)),
        nonblocked_old_xy_rmse_m=rmse(other,'old_error',slice(0,2)),nonblocked_new_xy_rmse_m=rmse(other,'new_error',slice(0,2)),
        six_old_yaw_rmse_deg=float(np.degrees(rmse(blocked,'old_error',slice(2,3)))),six_new_yaw_rmse_deg=float(np.degrees(rmse(blocked,'new_error',slice(2,3)))),
        six_coverage_count=sum(r['coverage']>=.8 for r in blocked),six_error_pass_count=sum(np.linalg.norm(r['new_error'][:2])<=.035 for r in blocked),
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
    gates=dict(default_off_exact=b['off_max_difference']==0.,six_observation_coverage=ms['six_coverage_count']>=adm['six_coverage_at_least_80percent_min_count'],
        six_endpoint_error=ms['six_error_pass_count']>=adm['six_endpoint_error_at_most_035_min_count'],six_median_error=ms['six_error_median_m']<=adm['six_endpoint_error_median_max_m'],
        six_yaw_not_worse=ms['six_new_yaw_rmse_deg']<=ms['six_old_yaw_rmse_deg'],
        loaded_xy_better=ms['new_xy_rmse_m']<ms['old_xy_rmse_m'],nonblocked_not_worse=ms['nonblocked_new_xy_rmse_m']<=ms['nonblocked_old_xy_rmse_m']+1e-10,
        carry_rmse=c['carry_rmse_m']<b['carry_rmse_m'],updates=c['carry_updates']>=adm['carry_updates_min'],
        max_gap=c['max_gap_s']<=adm['max_gap_s']+1e-7,stationary=c['stationary_max_m']<=adm['initial_stationary_max_m'],
        rgb_exact=replay['baseline']['source_hashes']==replay['candidate']['source_hashes'],wall_observation_retention=same_points,
        shadow_before_fourth=before_fourth)
    # Camera pitch and scale truth are read only here, after replay. No feedback.
    from harness.zone_solo_cyan_real_carry_dev import approximate
    from harness.zone_final_pair_camera import floor_camera
    from harness.zone_solo_cyan_flow_fusion import ground,rigid
    from types import SimpleNamespace as NS
    bundle=json.loads((raw/'bundle.json').read_text())
    camera=floor_camera(approximate(bundle['extrinsic_calibration'])['loaded']['600,2200,1400,1500'])
    nominal_pitch=float(np.degrees(np.arcsin(np.array(camera['rotation'])[2,2])))
    cameras={round(r['t'],6):r for r in (json.loads(l) for l in (raw/'eval_only/camera-pose.jsonl').read_text().splitlines())}
    by_t={round(r['t'],6):r for r in truth};pitch_rows=[];scale_rows=[]
    def actual_camera(t):
        cam=cameras[round(t,6)];tr=by_t[round(t,6)];yaw=tr['robot_yaw_rad'];c,s=np.cos(yaw),np.sin(yaw)
        rz=np.array([[c,-s,0],[s,c,0],[0,0,1.]])
        origin=rz.T@(np.array(cam['camera_cached_xyz_m'])-np.r_[tr['robot_xyz_m'][:2],0.])
        return NS(origin=origin,_rot=rz.T@np.array(cam['camera_cached_optical_rotation']))
    for pulse in vo.values():
        if not pulse.get('intervals'):continue
        pitch=[c['cached_pitch_deg']-nominal_pitch for t,c in cameras.items() if pulse['t']-1e-8<=t<=pulse['end']+1e-8]
        pitch_rows.append(dict(t=pulse['t'],blocked_six=round(pulse['t'],2) in SIX,
            pitch_error_deg_min=min(pitch),pitch_error_deg_max=max(pitch),pitch_error_deg_median=float(np.median(pitch))))
        for interval in pulse['intervals']:
            if interval['status']!='measured':continue
            t=interval['t'];dt=interval['dt'];ca,cb=actual_camera(t-dt),actual_camera(t)
            a=ground(ca,np.array(interval['before_uv']))[0];bb=ground(cb,np.array(interval['after_uv']))[0]
            r,d=rigid(a,bb);fixed=np.array(interval['delta'])
            scale_rows.append(dict(t=t,pulse_t=pulse['t'],fixed_delta=interval['delta'],eval_camera_delta=[*d,float(np.arctan2(r[1,0],r[0,0]))],
                fixed_vs_actual_geometry_xy_m=float(np.linalg.norm(fixed[:2]-d)),
                distance_scale_ratio=None if np.linalg.norm(d)<.001 else float(np.linalg.norm(fixed[:2])/np.linalg.norm(d)),
                fixed_sigma_xy_m=float(np.sqrt(np.trace(np.array(interval['covariance'])[:2,:2])))))
    pitch_result=dict(nominal_pitch_deg=nominal_pitch,pulses=pitch_rows,intervals=scale_rows,gt_use='evaluation only; no re-fitting',
        scale_ratio_quantiles=None if not any(x['distance_scale_ratio'] is not None for x in scale_rows) else
            np.quantile([x['distance_scale_ratio'] for x in scale_rows if x['distance_scale_ratio'] is not None],[0,.5,1]).tolist())
    result=dict(schema='ugrp.s2.flow_fusion.summary.v1',admission_pass=all(gates.values()),gates=gates,results=results,motion=ms,
        six=[{k:v for k,v in r.items() if k!='intervals'} for r in blocked],shadow=dict(events=shadow['rows'],inhibited_attempt_count=len(inhibited),first_inhibited_t=min(inhibited) if inhibited else None),
        observation=dict(common_candidates=len(common),common_points_exact=same_points,baseline_candidates=len(bm),candidate_candidates=len(cm),buffered_frames=replay['candidate']['visual_odometry']['buffered_frames'],dropped_wall_frames=0),
        pitch=dict(nominal_pitch_deg=nominal_pitch,six=[r for r in pitch_rows if r['blocked_six']],scale_ratio_quantiles=pitch_result['scale_ratio_quantiles']),
        source_sha=replay['candidate']['source_sha'],criteria_sha256=hashlib.sha256((HERE/'flow-fusion-criteria.json').read_bytes()).hexdigest(),physics_runs=0,model_calls=0,new_seed=None,new_bundle=None,
        full_dev='ADMITTED_NOT_YET_RUN' if all(gates.values()) else 'NOT_RUN_CRITERIA_FAILED',
        limits='Fixed-command exploratory replay. Recovery is shadow only; actual escape not proven. No new lifted/inside/wall-SIM/visibility/B-distance outcomes. Missing RGB motion intervals keep fixed command prediction.')
    for filename,obj in [('motion-score.json',motion),('pitch-scale-eval.json',pitch_result),('summary.json',result)]:
        data=json.dumps(obj,indent=2,default=lambda value:value.item())+'\n'
        with (destination/filename).open('x') as f:f.write(data)
    print(json.dumps({k:v for k,v in result.items() if k not in ('six','pitch')},indent=2,default=lambda value:value.item()))

if __name__=='__main__':main(Path(sys.argv[1]),Path(sys.argv[2]) if len(sys.argv)>2 else None)
