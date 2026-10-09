"""Saved s1049 evidence only; never used by a controller or live stop."""
import hashlib
import json
from pathlib import Path
import sys
import cv2
import numpy as np
from harness.zone_solo_cyan_scene_change import cyan


def analyze(raw):
    read=lambda name:json.loads((raw/name).read_text())
    lines=lambda name:[json.loads(x) for x in (raw/name).read_text().splitlines()]
    result=read('result.json');record=read('student_record.json')
    gt=lines('eval_only/trajectory.jsonl');frames=lines('robots/r3/frames.jsonl')
    times=np.array([x['t'] for x in gt]);xy=np.array([x['robot_xyz_m'][:2] for x in gt])
    yaw=np.unwrap([x['robot_yaw_rad'] for x in gt])
    poses=[]
    for p in record['poses']:
        actual=np.array([np.interp(p['t_est'],times,xy[:,j]) for j in (0,1)])
        dy=(p['yaw']-np.interp(p['t_est'],times,yaw)+np.pi)%(2*np.pi)-np.pi
        poses.append(dict(t=p['t'],t_est=p['t_est'],estimated_xy_m=[p['x'],p['y']],
            actual_xy_m=actual.tolist(),xy_error_m=float(np.linalg.norm(np.array([p['x'],p['y']])-actual)),
            yaw_error_deg=float(np.degrees(dy)),std_xy_m=p['std_xy_m'],last_fix_t=p['last_fix_t']))
    state_rows=[e for e in record['events'] if e['event']=='state']
    state_samples=[dict(state=e['state'],**min(poses,key=lambda p:abs(p['t']-e['t']))) for e in state_rows]
    first_wheel=min(c['t'] for c in record['commands'] if c['kind']=='mecanum' and any(c.get(k,0) for k in ('forward','left','turn')))
    stationary=[p for p in poses if p['t_est']<first_wheel]
    actual=np.array([p['actual_xy_m'] for p in stationary])
    max_row=max(stationary,key=lambda p:p['xy_error_m'])
    image_rows=[]
    for f in frames:
        # Every saved controller input, no image selection by outcome.
        data=(raw/f['path']).read_bytes();assert hashlib.sha256(data).hexdigest()==f['sha256']
        mask=cyan(cv2.imdecode(np.frombuffer(data,np.uint8),1))
        state=max((e for e in state_rows if e['t']<=f['sim_time']),key=lambda e:e['t'])['state']
        image_rows.append(dict(t=f['sim_time'],state=state,pixels=int(mask.sum()),path=f['path']))
    search=[r for r in image_rows if r['state']=='search']
    peaks=sorted(image_rows,key=lambda r:r['pixels'],reverse=True)[:3]
    original=['result.json','student_record.json','bundle.json','robots/r3/frames.jsonl',
              'eval_only/trajectory.jsonl','eval_only/camera-pose.jsonl','eval_only/metrics.json']
    return dict(schema='ugrp.s2.real_carry_full.posthoc.v1',seed=1049,raw=str(raw),
        source_sha=result['source_sha'],execution_bundle_id=result['execution_bundle_id'],
        simulation_runs=1,additional_simulation_runs=0,model_calls=result['model_calls'],
        evaluation_only=True,options=result['options'],result_status=result['status'],
        failure=result['failure'],evaluation=result['evaluation'],posthoc_evaluation=result['posthoc_evaluation'],
        wall_s=result['wall_s'],sim_s=result['total_sim_s'],wall_per_sim=result['wall_per_sim'],
        commands=result['commands_issued'],would_stop=result['dev_light_would_stop'],
        actual_nonphysical_terminal='CYAN_NOT_UNIQUELY_VISIBLE in frozen v106 search exhaustion; dev_light gap',
        grasp_confirmations='not reached; no prior cyan alignment observation, no invented blind target',
        first_wheel_t=first_wheel,stationary_scan=dict(
            actual_max_displacement_m=float(np.max(np.linalg.norm(actual-actual[0],axis=1))),
            maximum_pose_error=max_row),state_samples=state_samples,
        last_pose=poses[-1],fix_times=sorted({p['last_fix_t'] for p in poses if p['last_fix_t'] is not None}),
        cyan_rgb=dict(frames=len(image_rows),search_frames=len(search),
            search_max_pixels=max(r['pixels'] for r in search),
            search_frames_ge90=sum(r['pixels']>=90 for r in search),largest_areas=peaks),
        largest_observed_cause='Unloaded initial scan converged to a wrong pose while the chassis was stationary; search drove to wrong physical locations. New carry behavior was never reached.',
        unproven_causal_detail='Attribution between calibration residual and wall-feature ambiguity needs next-step offline analysis; no controller fix in this run.',
        source_hashes={str(raw/p):hashlib.sha256((raw/p).read_bytes()).hexdigest() for p in original})


if __name__=='__main__':
    raw,out=map(Path,sys.argv[1:]);assert not out.exists()
    out.write_text(json.dumps(analyze(raw),indent=2)+'\n')
