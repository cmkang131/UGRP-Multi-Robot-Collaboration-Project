"""Read-only artifact/judge/error audit; writes a new derived summary only."""
import bisect
from collections import Counter
import hashlib
import json
import math
from pathlib import Path
import sys
import numpy as np
from sim.solo_cyan_v106 import evaluate

ROOT = Path('/Users/changmin/projects/ugrp/outputs')
SHA = 'dfec1f19e1580534242d3b1b436eb45c07a979ea'
def digest(p):
    return hashlib.sha256(p.read_bytes()).hexdigest()
def audit(seed, slot):
    p = ROOT/f'solo-cyan-v106-{SHA[:8]}-s{seed}-{slot}-place'
    read = lambda n: json.loads((p/n).read_text())
    result, student, bundle, manifest = [read(n) for n in ('result.json', 'student_record.json', 'bundle.json', 'artifacts.sha256.json')]
    bad = [n for n,h in manifest.items() if digest(p/n) != h]
    truth = [json.loads(l) for l in (p/'eval_only/trajectory.jsonl').read_text().splitlines()]
    truth_t = [r['t'] for r in truth]
    poses = student['poses']; pose_t = [r['t'] for r in poses]
    def near(rows, times, t):
        i = bisect.bisect_left(times, t)
        return min(rows[max(0,i-1):min(len(rows),i+1)], key=lambda r:abs(r['t']-t))
    checkpoints = []
    for e in student['events']:
        if e['event'] != 'carry_checkpoint': continue
        est = near(poses, pose_t, e['t']); actual = near(truth, truth_t, est['t_est'])
        yaw = math.atan2(math.sin(est['yaw']-actual['robot_yaw_rad']),math.cos(est['yaw']-actual['robot_yaw_rad']))
        checkpoints.append({'index':e['index'], 't':e['t'], 't_est':est['t_est'], 'truth_t':actual['t'],
            'xy_error_m':math.dist((est['x'],est['y']),actual['robot_xyz_m'][:2]), 'yaw_error_deg':math.degrees(yaw)})
    relooks = [{k:e[k] for k in ('index','t','fresh_fix','last_fix_t','observation_quality')} for e in student['events'] if e['event']=='cyan_relook_result']
    static = read('inputs/static_map.json')
    evaluated = evaluate(truth, static, bundle['task']['destination'])
    managed_path = Path(str(p)+'-managed')/'manifest.json'; managed=json.loads(managed_path.read_text())
    region=static['regions']['zone_B']; last=truth[-1]
    ext=abs(np.array(last['cyan_rotation']).reshape(3,3))@np.array(last['box_half_m'])
    clearance=min(np.array(region['half_extents_m'])-abs(np.array(last['cyan_xyz_m'][:2])-np.array(region['center_m']))-ext[:2])
    proxy_errors=[]
    for r in truth:
        if r['cyan_xyz_m'][2] < .12: continue
        x,y=[r['cyan_xyz_m'][i]-r['robot_xyz_m'][i] for i in (0,1)]
        d=math.atan2(y,x)-r['robot_yaw_rad']
        proxy_errors.append(math.degrees(math.atan2(math.sin(d),math.cos(d))))
    assert not bad and result['source_sha']==SHA and result['evaluation']==evaluated
    assert managed['source_changed_during_run'] is False and managed['exit_code']==0
    return {'seed':seed,'slot':slot,'source':str(p),'source_sha':SHA,'artifact_files_checked':len(manifest),
        'artifact_mismatches':bad,'judge_recomputed_equal':evaluated==result['evaluation'],
        'hashes':{n:digest(p/n) for n in ('result.json','bundle.json','artifacts.sha256.json','student_record.json','eval_only/trajectory.jsonl')},
        'managed_path':str(managed_path),'managed_sha256':digest(managed_path),
        'managed':{k:managed[k] for k in ('status','runtime_s','exit_code','source_changed_during_run','started_utc','ended_utc','finalization_errors')},
        'result':result,'relooks':relooks,'checkpoints':checkpoints,'final_cyan_xyz_m':last['cyan_xyz_m'],
        'final_cuboid_boundary_margin_m':float(clearance),'carry_proxy_minus_actual_yaw_deg_minmax':[min(proxy_errors),max(proxy_errors)],
        'would_stop_codes':student['dev_light_would_stop'],
        'would_stop_logged_event_counts':dict(Counter(e['code'] for e in student['events'] if e['event']=='dev_light_would_stop'))}
if __name__=='__main__':
    target=Path(sys.argv[1]); assert not target.exists()
    seeds=[(912,'P1-1'),(913,'P1-3'),(914,'P2-2')]
    runs=[audit(seed,slot) for seed,slot in seeds]
    target.write_text(json.dumps({'scope':'Frozen three-case DEV, provisional geometry only; no study/physical claim','source_sha':SHA,'runs':runs},indent=2)+'\n')
    for r in runs:
        print({k:r[k] for k in ('seed','slot','artifact_files_checked','final_cuboid_boundary_margin_m','carry_proxy_minus_actual_yaw_deg_minmax','would_stop_codes')})
        print('outcome',r['result']['evaluation'],'SIM',r['result']['check_sim_s'],'wall',r['managed']['runtime_s'],'checkpoints',r['checkpoints'])
