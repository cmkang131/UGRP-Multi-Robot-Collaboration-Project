"""GT evaluation only AFTER immutable own-RGB replay. Never imported by runtime."""
import hashlib,json
from collections import Counter
from pathlib import Path
import numpy as np
HERE=Path(__file__).resolve().parent
OUT=Path('/Users/changmin/projects/ugrp/outputs/s2-ground-vo-20261007')
SIX={107.35,108.30,109.25,110.20,111.15,113.70}
def sha(p):return hashlib.sha256(p.read_bytes()).hexdigest()
def main():
    criteria=json.loads((HERE/'ground-vo-criteria.json').read_text());raw=Path(criteria['legacy_raw'])
    paths=dict(baseline=OUT/'replay-baseline.json',candidate=OUT/'replay-candidate-allposes.json')
    replays={k:json.loads(p.read_text()) for k,p in paths.items()}
    assert all(r['frames']==5202 and not r['gt_inputs'] for r in replays.values())
    truth=[json.loads(l) for l in (raw/'eval_only/trajectory.jsonl').read_text().splitlines()]
    tt=np.array([t['t'] for t in truth]);xy=np.array([t['robot_xyz_m'][:2] for t in truth]);yaw=np.unwrap([t['robot_yaw_rad'] for t in truth])
    lo,hi=criteria['carry_window'];results=[]
    for name,r in replays.items():
        errors=[]
        for p in r['poses']:
            if lo<=p['t']<hi:
                actual=[np.interp(p['t_est'],tt,xy[:,i]) for i in range(2)]
                errors.append(float(np.linalg.norm(np.array([p['x'],p['y']])-actual)))
        fixes=[x['t'] for x in r['amcl']['rows'] if lo<=x['t']<hi and x['visual_weight_update']]
        results.append(dict(option=name,carry_rmse_m=float(np.sqrt(np.mean(np.square(errors)))),
            carry_updates=len(fixes),max_gap_s=float(max(np.diff([lo,*fixes,hi])))))
    vo=replays['candidate']['ground_vo'];by_t={round(r['t'],6):r for r in vo['rows']}
    original=Path('/Users/changmin/projects/ugrp/outputs/s2-load-height-20261007/drift-decomposition.json')
    pulse_rows=json.loads(original.read_text())['rows'];motion=[]
    for p in pulse_rows:
        r=by_t.get(round(p['t'],6),{});actual=np.array(p['actual_delta']);old=np.array(p['predicted_delta'])
        new=np.array(r['applied_delta']) if r.get('prediction_replaced') else old
        motion.append(dict(t=p['t'],key=p['key'],six=round(p['t'],2) in SIX,
            old_error_m=float(np.linalg.norm(old[:2]-actual[:2])),new_error_m=float(np.linalg.norm(new[:2]-actual[:2])),
            old_prediction=old.tolist(),new_prediction=new.tolist(),actual_delta=actual.tolist(),
            measured=r.get('prediction_replaced',False),status=r.get('status')))
    assert len(motion)==277 and sum(r['six'] for r in motion)==6
    rms=lambda rows,key:float(np.sqrt(np.mean([r[key]**2 for r in rows])))
    normal=[r for r in motion if not r['six']];six=[r for r in motion if r['six']]
    ms=dict(loaded_pulses=len(motion),normal_pulses=len(normal),normal_old_rms_m=rms(normal,'old_error_m'),
        normal_new_rms_m=rms(normal,'new_error_m'),all_old_rms_m=rms(motion,'old_error_m'),all_new_rms_m=rms(motion,'new_error_m'),
        six_pass_035m=sum(r['new_error_m']<=.035 for r in six),six_measured=sum(r['measured'] for r in six))
    # Additional unloaded cohort, scored with the same recorded command horizon;
    # not folded into the existing 271 normal loaded pulses.
    bundle=json.loads((raw/'bundle.json').read_text());unloaded=[]
    for r in vo['rows']:
        if not r.get('key','').startswith('0:'):continue
        p=bundle['pulse_calibration']['profiles'].get(r['key'])
        if p is None:continue
        t=r['t'];end=t+p['times'][-1];angle=np.interp(t,tt,yaw);c,s=np.cos(angle),np.sin(angle)
        d=np.array([np.interp(end,tt,xy[:,i])-np.interp(t,tt,xy[:,i]) for i in range(2)])
        actual=np.array([[c,s],[-s,c]])@d
        old=np.array(p['mean_delta'][:2]);new=np.array(r['applied_delta'][:2]) if r.get('prediction_replaced') else old
        unloaded.append(dict(t=t,key=r['key'],measured=r.get('prediction_replaced',False),
            old_error_m=float(np.linalg.norm(old-actual)),new_error_m=float(np.linalg.norm(new-actual))))
    us=dict(pulses=len(unloaded),measured=sum(r['measured'] for r in unloaded),
        old_rms_m=rms(unloaded,'old_error_m'),new_rms_m=rms(unloaded,'new_error_m')) if unloaded else None
    intervals=[i for r in vo['rows'] for i in r.get('intervals',[])]
    fractions=[f for i in intervals for f in i.get('image_fractions',[])]
    rad=[r['pitch_radial_sigma_m'] for r in vo['rows'] if r.get('complete_visual')]
    scale=[r['pitch_scale_relative_sigma'] for r in vo['rows'] if r.get('complete_visual') and r.get('pitch_scale_relative_sigma') is not None]
    obs=dict(status_counts=dict(Counter(r['status'] for r in vo['rows'])),
        interval_status_counts=dict(Counter(i['status'] for i in intervals)),
        measurement_count=sum(r.get('prediction_replaced',False) for r in vo['rows']),
        command_fallback_count=sum(not r.get('prediction_replaced',False) for r in vo['rows']),
        wall_frames_dropped=vo['wall_frames_dropped'],all_frame_hashes_equal=replays['baseline']['source_hashes']==replays['candidate']['source_hashes'],
        image_fraction_quantiles={k:np.quantile([f[k] for f in fractions],[0,.5,.95,1]).tolist() for k in fractions[0]} if fractions else {},
        pitch_radial_sigma_m_quantiles=np.quantile(rad,[0,.5,.95,1]).tolist() if rad else None,
        pitch_relative_sigma_quantiles=np.quantile(scale,[0,.5,.95,1]).tolist() if scale else None)
    recovery=json.loads((OUT/'recovery-clear.json').read_text())
    gates=dict(default_off_exact=replays['baseline']['baseline_max_delta']==0.,recovery_clear=recovery['pass_'],
        normal_loaded_rms=ms['normal_new_rms_m']<=ms['normal_old_rms_m']+1e-10,
        normal_unloaded_rms=us is not None and us['new_rms_m']<=us['old_rms_m']+1e-10,
        carry_rmse=results[1]['carry_rmse_m']<results[0]['carry_rmse_m'],
        all_own_rgb_preserved=obs['all_frame_hashes_equal'] and obs['wall_frames_dropped']==0)
    result=dict(schema='ugrp.s2.ground_vo.result.v1',complete=True,source_sha=replays['candidate']['source_sha'],
        criteria_commit='a4db20e6',options={**bundle['options'],'odom_source':'ground_vo_v1',
            'slip_detection':'slip_detect_v1','slip_recovery':'slip_recovery_v1','servo_stiffness':'off'},
        legacy_replay_gates=gates,legacy_replay_pass=all(gates.values()),metrics=results,motion=ms,unloaded=us,
        observations=obs,recovery=recovery,ground_vo_calibration=vo['calibration'],
        required_plant_assessment='NOT_EVALUABLE: stiffness ON S2 pose/load/motion calibration and S1051-condition RGB missing',
        admission_pass=False,new_physics_runs=0,model_calls=0,new_seed=None,new_bundle=None,
        full_dev='NOT_RUN',lifted=None,inside=None,carry_visibility=None,distance_to_B_m=None,would_stop_points=None,wall_sim_ratio=None,
        previous_success_not_inherited=True,source_raw=str(raw),outputs=str(OUT),
        sources={str(p):sha(p) for p in [*paths.values(),original,raw/'eval_only/trajectory.jsonl',HERE/'ground-vo-criteria.json']},
        scope='Legacy stiffness-OFF open-loop exploration only. Recovery replay is independent saved states, not closed-loop escape. GT evaluation only after frozen own-RGB replay.')
    for name,value in [('motion-score.json',dict(loaded=motion,unloaded=unloaded)),('result.json',result)]:
        with (OUT/name).open('x') as f:json.dump(value,f,indent=2)
    print(json.dumps({k:result[k] for k in ('legacy_replay_gates','metrics','motion','unloaded','observations','admission_pass')},indent=2))
if __name__=='__main__':main()
