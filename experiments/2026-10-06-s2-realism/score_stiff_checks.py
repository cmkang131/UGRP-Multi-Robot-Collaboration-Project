"""Post-prediction evaluation only; never imported by capture or runtime."""
import hashlib,json,math
from collections import Counter
from pathlib import Path
import numpy as np
O=Path('/Users/changmin/projects/ugrp/outputs/s2-stiff-cal-20261007')
E=Path(__file__).resolve().parent
read=lambda p:json.loads(p.read_text())
sha=lambda p:hashlib.sha256(p.read_bytes()).hexdigest()

def main():
    truth=[json.loads(l) for l in (O/'start/eval_only/trajectory.jsonl').read_text().splitlines()]
    starts=[]
    for option in ('off','on'):
        pred=read(O/f'replay-start-{option}.json');errors=[];clouds=[]
        for p in pred['poses']:
            gt=min(truth,key=lambda q:abs(q['t']-p['t']))
            errors.append(math.dist([p['x'],p['y']],gt['robot_xyz_m'][:2]))
        for q in pred['clouds']:
            gt=min(truth,key=lambda r:abs(r['t']-q['t']));px=np.array(q['px']);w=np.array(q['w'])
            near=(np.linalg.norm(px[:,:2]-gt['robot_xyz_m'][:2],axis=1)<=.25)&(abs(np.arctan2(np.sin(px[:,2]-gt['robot_yaw_rad']),np.cos(px[:,2]-gt['robot_yaw_rad'])))<=np.deg2rad(15))
            clouds.append(dict(t=q['t'],count=int(near.sum()),mass=float(w[near].sum())))
        starts.append(dict(camera_pitch=option,plant='real_v1',frames=len(errors),final_error_m=errors[-1],max_error_m=max(errors),
            rmse_m=float(np.sqrt(np.mean(np.square(errors)))),updates=pred['amcl']['updates'],
            detector_columns=[dict(t=v['t'],columns=sum(k==1 for k in v['b_kind'])) for v in pred['views']],
            near_truth_eval=clouds,final_modes=pred['poses'][-1]['modes']))
    vo=read(O/'replay-stiff-vo-final.json');scored=[]
    for p in vo['rows']:
        rows=[json.loads(l) for l in (Path(p['raw'])/'eval_only/trajectory.jsonl').read_text().splitlines()]
        t=np.array([q['t'] for q in rows]);xy=np.array([q['robot_xyz_m'][:2] for q in rows]);angles=np.unwrap([q['robot_yaw_rad'] for q in rows])
        yaw=np.interp(p['t'],t,angles);cs,sn=np.cos(yaw),np.sin(yaw)
        delta=np.array([np.interp(p['end'],t,xy[:,i])-np.interp(p['t'],t,xy[:,i]) for i in range(2)])
        actual=np.array([[cs,sn],[-sn,cs]])@delta
        scored.append(dict(case=p['case'],t=p['t'],baseline_error_m=float(np.linalg.norm(actual-p['expected_delta'][:2])),
            vo_error_m=float(np.linalg.norm(actual-p['applied_delta'][:2])),measured=p['prediction_replaced'],
            exact_end_available=p['sampled_end'],interval_status_counts=dict(Counter(x['status'] for x in p['intervals']))))
    motion=dict(pulses=len(scored),measured=sum(p['measured'] for p in scored),
        baseline_rms_m=float(np.sqrt(np.mean([p['baseline_error_m']**2 for p in scored]))),
        vo_rms_m=float(np.sqrt(np.mean([p['vo_error_m']**2 for p in scored]))),
        carry_rmse=None,carry_gate='NOT_EVALUABLE: no stiffness-on S2 carry replay',
        pulse_end_missing=sum(not p['exact_end_available'] for p in scored),rows=scored)
    diagnostic_files=[O/'capture/result.json',O/'capture/calibration.json',O/'capture/observations.json',
        O/'capture/eval_only.json',O/'calibration-evaluation.json',O/'start/result.json',
        O/'replay-start-off.json',O/'replay-start-on.json',O/'replay-stiff-vo-final.json',E/'stiff-camera-criteria.json']
    result=dict(schema='ugrp.s2.stiff_camera.result.v1',calibration_source='bcefa435',start_source='8386e299',
        calibration=read(O/'capture/result.json'),calibration_evaluation=read(O/'calibration-evaluation.json'),
        start_capture=read(O/'start/result.json'),start_replays=starts,ground_vo=motion,
        gates=dict(all_22_poses_calibrated=True,heldout_reprojection=True,start_detector_recovered=starts[-1]['detector_columns'][4]['columns']>=6,
            start_localization=starts[-1]['final_error_m']<=.25 and starts[-1]['max_error_m']<=.5,
            normal_vo_rms_nonincrease=motion['vo_rms_m']<=motion['baseline_rms_m']+1e-10,carry_vo_rmse_improvement=None),
        admission_pass=False,full_dev='NOT_RUN',new_full_seed=None,task_bundle=None,
        lifted=None,inside=None,carry_fixes=None,carry_max_gap_s=None,carry_rmse=None,carry_wall_visibility=None,distance_to_B=None,would_stop_points=None,full_wall_sim=None,
        physical_runs={'stationary_target_calibration':1,'stationary_prefix_diagnostic':1,'full_dev':0},
        model_calls=0,gt_use='post-prediction evaluation only; no fit/control',
        camera_mount_fov_changed=False,start_dock_prior=False,loaded_calibration='unloaded rigid approximation, NOT independently load-qualified',
        known_issue='startup hypotheses remain unresolved (true-neighborhood mass 7.19%); VO exact horizon absent in 10Hz external records',
        raw=str(O),hashes={str(p):sha(p) for p in diagnostic_files})
    (O/'result.json').write_text(json.dumps(result,indent=2)+'\n')
    (E/'stiff-camera-result.json').write_text(json.dumps(result,indent=2)+'\n')
    print(json.dumps(dict(start=starts[-1]['final_error_m'],motion={k:v for k,v in motion.items() if k!='rows'},gates=result['gates']),indent=2))
if __name__=='__main__':main()
