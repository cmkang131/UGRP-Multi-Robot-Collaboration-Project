"""Post-run s1050 evidence; saved records only, no simulator or controller."""
import hashlib
import json
from pathlib import Path
import sys
import numpy as np


def analyze(raw):
    read=lambda name:json.loads((raw/name).read_text())
    lines=lambda name:[json.loads(x) for x in (raw/name).read_text().splitlines()]
    result=read('result.json');record=read('student_record.json')
    assert result['source_sha'].startswith('97fcb5d2')
    assert result['posthoc_evaluation']['seed']==1050
    managed=json.loads(Path(str(raw)+'-managed/manifest.json').read_text())
    assert managed['status']=='process_completed' and managed['exit_code']==0
    assert not managed['source_changed_during_run'] and not managed['inputs_changed_during_run']
    truth=lines('eval_only/trajectory.jsonl');frames=lines('robots/r3/frames.jsonl')
    for f in frames:
        assert hashlib.sha256((raw/f['path']).read_bytes()).hexdigest()==f['sha256']
    tt=np.array([r['t'] for r in truth]);xy=np.array([r['robot_xyz_m'][:2] for r in truth])
    yaw=np.unwrap([r['robot_yaw_rad'] for r in truth]);poses=[]
    for r in record['poses']:
        actual=np.array([np.interp(r['t_est'],tt,xy[:,j]) for j in (0,1)])
        dy=r['yaw']-np.interp(r['t_est'],tt,yaw)
        poses.append(dict(t=r['t'],t_est=r['t_est'],estimated_xy_m=[r['x'],r['y']],
            actual_xy_m=actual.tolist(),error_m=float(np.linalg.norm(np.array([r['x'],r['y']])-actual)),
            yaw_error_deg=float(np.degrees(np.arctan2(np.sin(dy),np.cos(dy)))),std_xy_m=r['std_xy_m']))
    first=min(c['t'] for c in record['commands'] if c['kind']=='mecanum' and
              any(c.get(k,0) for k in ('forward','left','turn')))
    stationary=[r for r in poses if r['t_est']<first]
    actual=np.array([r['actual_xy_m'] for r in stationary])
    post=result['posthoc_evaluation'];lo,hi=post['carry_window']
    masks=[r for r in record['visibility_mask']['rows'] if lo<=r['t']<hi]
    carry=[r for r in poses if lo<=r['t']<hi]
    rmse=float(np.sqrt(np.mean([r['error_m']**2 for r in carry])))
    assert abs(rmse-post['carry_xy_rmse_m'])<1e-12
    assert sum(r['kept'] for r in masks)==post['visibility_measurement']['kept_columns']==0
    # Every detected frame has zero columns passing the .95 prior-view gate.
    positive=[r for r in masks if r['detected']>0]
    assert positive and all(r['prior_view_columns']==0 for r in positive)
    assert all(r['detected_self_shadow']==r['detected_cargo_shadow']==0 for r in masks)
    vis={k:v for k,v in post['actual_visibility'].items() if k!='rows'}
    compact_post={k:v for k,v in post.items() if k not in ('actual_visibility','update_times')}
    compact_post['actual_visibility']=vis
    original=['result.json','student_record.json','bundle.json','robots/r3/frames.jsonl',
              'eval_only/trajectory.jsonl','eval_only/camera-pose.jsonl','eval_only/metrics.json']
    return dict(schema='ugrp.s2.amcl_full.posthoc.v1',seed=1050,raw=str(raw),
        source_sha=result['source_sha'],execution_bundle_id=result['execution_bundle_id'],
        physics_runs=1,additional_physics_runs=0,model_calls=result['model_calls'],gt_usage='post-run evaluation only',
        source_changed_during_run=False,options=result['options'],status=result['status'],failure=result['failure'],
        evaluation=result['evaluation'],posthoc_evaluation=compact_post,
        wall_s=result['wall_s'],sim_s=result['total_sim_s'],wall_per_sim=result['wall_per_sim'],
        commands=result['commands_issued'],would_stop=result['dev_light_would_stop'],
        hold_status=result['hold_status'],pickup_site_status=result['pickup_site_status'],regrasp_count=result['regrasp_count'],
        first_wheel_t=first,stationary=dict(max_error_m=max(r['error_m'] for r in stationary),
            end_error_m=stationary[-1]['error_m'],actual_max_displacement_m=float(np.max(np.linalg.norm(actual-actual[0],axis=1))),
            updates=sum(r['t']<first for r in record['amcl_update']['rows'])),
        state_samples=[dict(state=e['state'],**min(poses,key=lambda p:abs(p['t']-e['t'])))
                       for e in record['events'] if e['event']=='state'],last_pose=poses[-1],
        amcl={k:v for k,v in record['amcl_update'].items() if k!='rows'},amcl_updates=record['amcl_update']['rows'],
        mask_failure=dict(attempts=len(masks),positive_detection_frames=len(positive),
            positive_detection_frames_with_any_prior_visible_column=sum(r['prior_view_columns']>0 for r in positive),
            total_detected_columns=sum(r['detected'] for r in masks),kept_columns=sum(r['kept'] for r in masks),
            self_shadow=0,cargo_shadow=0,prior_probability_threshold=.95),
        largest_remaining_cause='Visibility prior gate starves every loaded update: all 1900 detected frames have zero columns with >=.95 prior in-view probability; detected self/cargo shadow counts are zero. Evaluation sees clear true bottoms in 71.87% of detected columns. No further fix or run in this turn.',
        interpretation_limit='Particle-prior visibility is not RGB visibility. Actual visibility uses saved camera/cargo geometry and conservative command-body bounds at 1 Hz. Visual weight updates are not guaranteed full-rank pose fixes.',
        frames_verified=len(frames),frame_range_sim_s=[frames[0]['sim_time'],frames[-1]['sim_time']],
        source_hashes={str(raw/p):hashlib.sha256((raw/p).read_bytes()).hexdigest() for p in original})


if __name__=='__main__':
    raw,out=map(Path,sys.argv[1:]);assert not out.exists()
    out.write_text(json.dumps(analyze(raw),indent=2)+'\n')
