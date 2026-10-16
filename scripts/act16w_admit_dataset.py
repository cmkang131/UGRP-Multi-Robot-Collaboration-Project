"""Explicit source/hash-bound training admission after fresh recording review."""
import argparse
from collections import defaultdict
import json
import math
from pathlib import Path
import sys
from act16w_runtime import ACT_SHA, PROJECT, frozen_source, require_gcp2, sha256, training_admission

ROOT=Path(__file__).resolve().parents[1]
B=Path('/home/ugrp/ugrp-sim')


def main():
    p=argparse.ArgumentParser();p.add_argument('--approve-reviewed-records',action='store_true')
    for k in ('dataset-root','record-plans','out'):p.add_argument('--'+k,type=Path,required=True)
    a=p.parse_args()
    if not a.approve_reviewed_records:p.error('explicit concrete reviewed-data approval required')
    require_gcp2(training=True);source=frozen_source(ROOT)
    sys.path.insert(0,str(B/'src/0362037280c6cbc4677f70366db43b9892b23690/scripts'))
    from warp_act_api import admit,QUALIFIED
    bootstrap_path=B/'runs/warp3/teacher-gate-qualification-r1.json'
    bootstrap=admit(bootstrap_path,B/'src'/QUALIFIED,B/'src/warp1-teacher-snapshot-6f057f7e')
    fresh_path=a.dataset_root/'fresh-recording-gate.json';fresh=json.loads(fresh_path.read_text())
    audit_path=a.dataset_root/'dataset-audit.json';audit=json.loads(audit_path.read_text())
    if not fresh['passed'] or not fresh['complete'] or not audit['passed'] or not audit['valid_future_action_targets_verified']:
        raise ValueError('actual fresh recording gate and complete dataset audits required')
    violations=sum(r['input_audit'][k] for r in fresh['rows'] for k in ('invisible_measurements','held_world_reads'))
    scene=ROOT/'experiments/2026-10-16-act16w/scene-decision.json';decision=json.loads(scene.read_text())
    if (decision['profile'],decision['floor'],decision['quality'])!=('walls_floor_contrast_v5_indigo110_s80','v1','no_mip_v1'):
        raise ValueError('exact approved scene required')
    proof=dict(approved=True,source_sha=source,act_source_sha=ACT_SHA,
        dataset_manifest_sha256=sha256(a.dataset_root/'dataset/manifest.json'),backend='mjwarp_batch_v1',project_id=PROJECT,
        training_rgb_during_gate=False,teacher_success_n=bootstrap['n'],teacher_attempts_N=bootstrap['N'],
        bootstrap_independent=False,input_audit_violations=violations,valid_future_action_targets_verified=True,
        fresh_record_confirmation=dict(n=fresh['n'],N=fresh['N'],seeds=sorted(r['seed'] for r in fresh['rows']),independent_of_warp1_debugging=True,training_rgb=True),
        scope='camera-off bootstrap plus separately confirmed fresh recording cohort; no student success claim')
    for key,path in [('gate_summary',bootstrap_path),('fresh_recording_gate',fresh_path),('rejection_table',a.dataset_root/'rejection_table.json'),('scene_decision',scene),('dataset_audit',audit_path)]:
        proof[key]=dict(path=str(path),sha256=sha256(path))
    a.out.mkdir(parents=True,exist_ok=False)
    def write(name,value):(a.out/name).write_text(json.dumps(value,indent=2)+'\n')
    write('training-admission.json',proof)
    training_admission(a.out/'training-admission.json',source=source,dataset=a.dataset_root/'dataset',act_source=ACT_SHA)
    plans={x['seed']:x for x in json.loads(a.record_plans.read_text())['episodes']}
    starts=[];groups=defaultdict(list)
    for seed in audit['train_seeds']:
        plan=plans[seed];sx,sy,_,yaw=plan['spawns']['r1'];cx,cy=plan['cargo_pose_m'][:2]
        error=math.atan2(cy-sy,cx-sx)-yaw
        starts.append(dict(seed=seed,object_kind=plan['kind'],start_distance_m=math.hypot(cx-sx,cy-sy),abs_start_yaw_rad=abs(math.atan2(math.sin(error),math.cos(error)))))
        groups[plan['kind']].append(seed)
    write('curriculum-starts.json',starts)
    selected=[]
    while len(selected)<min(20,len(starts)):
        for kind in sorted(groups):
            if groups[kind] and len(selected)<20:selected.append(groups[kind].pop(0))
    write('dagger-starts.json',dict(seeds=selected,selection='TRAIN-only deterministic round-robin kinds before any student training; same D0 starts, different policy-induced trajectories',normalization='D0 unchanged',scope='30SIM prefix coverage collection, cap_end separate; not task success evaluation'))
    print(json.dumps(dict(status='approved',source_sha=source,n=fresh['n'],N=fresh['N'],violations=violations,admission=str(a.out/'training-admission.json'))))


if __name__=='__main__':main()
