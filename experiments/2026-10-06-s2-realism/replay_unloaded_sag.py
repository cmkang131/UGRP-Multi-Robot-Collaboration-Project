"""Offline fixed-command PF replay. No simulator, GT input, or runtime admission.

The saved camera poses/trajectory are deliberately read by a separate evaluator.
PR405's coefficients are copied verbatim with provenance, never refitted here.
"""
import argparse
import base64
import copy
import fcntl
import hashlib
import importlib.util
import json
import math
from pathlib import Path
import sys

import cv2
import numpy as np

ROOT = Path(__file__).resolve().parents[2]
HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(ROOT))
from harness import zone_solo_cyan_camera_v3 as camera
from harness import zone_solo_cyan_contract_v106 as contract
from harness import zone_pair_highpose_frame_gate as frame_gate
from harness.zone_solo_cyan_visual_fix import Runtime
from harness.zone_pair_highpose_exact_speedups import install

CRITERIA = json.loads((HERE/'unloaded-sag-criteria.json').read_text())
TABLE_PATH = ROOT/'configs/calibration/s2_camera_v3_extrinsic_v1.json'
TABLE = json.loads(TABLE_PATH.read_text())
RUNS = {1045:'f0bb26e7', 1046:'e619ee57', 1047:'1a2dbf5e'}
RAW = Path('/Users/changmin/projects/ugrp/outputs')


def digest(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def sag_delta(pose_key):
    spec = importlib.util.spec_from_file_location('pinned_sag', HERE/'pr405-sag-source/sag_comp.py')
    sag = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(sag)
    coeffs = sag.load_coeffs(HERE/'pr405-sag-source/sag_coeffs.json')
    servo = dict(zip((3,4,5,6), map(int, pose_key.split(','))))
    return sag.bias_rad(servo, True, coeffs) - sag.bias_rad(servo, False, coeffs)


def approximation(variant):
    if variant not in CRITERIA['variants'][1:]:
        raise ValueError('offline approximation variant required')
    models = {s:copy.deepcopy(TABLE['camera_models']['unloaded']) for s in ('loaded','unloaded')}
    deltas = {}
    for key, rec in models['loaded'].items():
        delta = (CRITERIA['constant_delta_rad'] if variant == 'unloaded_constant_delta'
                 else sag_delta(key) if variant == 'unloaded_pr405_sag_delta' else 0.)
        c,s = math.cos(delta), math.sin(delta)
        # Optical right axis, positive rotation raises the forward ray.
        rec['rotation'] = (np.asarray(rec['rotation']) @ np.array([[1,0,0],[0,c,-s],[0,s,c]])).tolist()
        deltas[key] = delta
    return dict(camera_models=models, pan_base_yaw=copy.deepcopy(TABLE['pan_base_yaw']),
                load_delta_rad=deltas, variant=variant, runtime_admitted=False,
                measured_loaded=False, table_sha256=digest(TABLE_PATH))


def factory_for(variant):
    table = approximation(variant)
    def factory(*args, **kwargs):
        source = camera.build_provider(*args, **kwargs)
        cal = source.provider.calibration
        for key in ('camera_models','pan_base_yaw'):
            cal[key].clear()
            cal[key].update(copy.deepcopy(table[key]))
        return source
    factory.controller_geometry_id = camera.build_provider.controller_geometry_id
    factory.uses_landmark_tags = False
    return factory


def carry_window(record):
    states = [e for e in record['events'] if e['event']=='state']
    i = next(i for i,e in enumerate(states) if e['state']=='carry')
    return states[i]['t'], states[i+1]['t']


def fix_metrics(rows, window):
    start,end = window
    fixes = sorted({r['last_fix_t'] for r in rows if r['last_fix_t'] is not None
                    and start <= r['last_fix_t'] < end})
    independent = []
    for t in fixes:
        if not independent or t-independent[-1] >= CRITERIA['independent_spacing_sim_s']-1e-9:
            independent.append(t)
    gaps = np.diff([start,*fixes,end])
    maximum = float(max(gaps))
    passed = len(independent)>=CRITERIA['min_independent_fixes'] and maximum<=CRITERIA['max_fix_gap_sim_s']
    return dict(carry_window=list(window),accepted_fixes=len(fixes),independent_fixes=len(independent),
                max_fix_gap_sim_s=maximum,fix_times=fixes,admission_pass=passed)


def replay(seed, variant, output):
    run = RAW/f's2-realism-{RUNS[seed]}-s{seed}-P1-2-place'
    output.mkdir(parents=True,exist_ok=True)
    dest = output/f's{seed}-{variant}.json'
    if dest.exists():raise FileExistsError(dest)
    record = json.loads((run/'student_record.json').read_text())
    bundle = json.loads((run/'bundle.json').read_text())
    frames = [json.loads(l) for l in (run/'robots/r3/frames.jsonl').read_text().splitlines()]
    _,undo = install('v98-exact-v6')
    excluded = ('drive_profile','stagnation_watch','idle_robot_contacts','dev_grasp_policy','eval_camera_trace')
    kwargs = {k:v for k,v in bundle['options'].items() if k not in excluded}
    kwargs['motion_model'] = bundle['motion_model']
    if 'pulse_calibration' in bundle:kwargs['pulse_calibration']=bundle['pulse_calibration']
    if variant!='legacy':kwargs['provider_factory']=factory_for(variant)
    runtime = Runtime(contract.hp.resolve(contract.MAP_ID)[0],ROOT/contract.CALIBRATION,
                      contract.CALIBRATION_SHA,seed=seed,**kwargs)
    provider=runtime.pose
    commands={}
    for cmd in record['commands']:commands.setdefault(round(cmd['t'],6),[]).append(cmd)
    provider.on_command(commands[round(frames[0]['sim_time'],6)].pop(0))
    rows=[];maximum=0.;mismatches=0
    try:
        for i,(f,p) in enumerate(zip(frames,record['poses'])):
            now=f['sim_time'];data=(run/f['path']).read_bytes()
            assert hashlib.sha256(data).hexdigest()==f['sha256']
            rgb=cv2.cvtColor(cv2.imdecode(np.frombuffer(data,np.uint8),1),cv2.COLOR_BGR2RGB)
            verdict,_=frame_gate.gate().assess({**f,'image':base64.b64encode(data).decode()},'r3',now,ob=False)
            report=provider.on_frame(now,rgb if verdict==frame_gate.VALID else None)
            delta=max(abs(report.x_m-p['x']),abs(report.y_m-p['y']),abs(report.yaw_rad-p['yaw']))
            maximum=max(maximum,delta);mismatches+=delta>CRITERIA['baseline_max_pose_delta']
            rows.append(dict(t=now,x=report.x_m,y=report.y_m,yaw=report.yaw_rad,
                last_fix_t=report.last_fix_t,gate=copy.deepcopy(getattr(provider.provider.loc._pf,'partial_fix_last',None))))
            for cmd in commands.get(round(now,6),[]):provider.on_command(cmd)
            if i%1000==0:print(seed,variant,i,now,flush=True)
        result=dict(seed=seed,variant=variant,physics_runs=0,model_calls=0,gt_inputs=False,
            commands_fixed=True,frames=len(rows),saved_poses=len(record['poses']),
            trailing_pose_without_rgb=len(record['poses'])-len(rows),baseline_max_pose_delta=maximum,
            baseline_mismatches=mismatches,source_raw=str(run),criteria_sha256=digest(HERE/'unloaded-sag-criteria.json'),
            source_hashes={p:digest(run/p) for p in ('bundle.json','student_record.json','robots/r3/frames.jsonl')},
            metrics=fix_metrics(rows,carry_window(record)),rows=rows)
        if variant!='legacy':result['approximation']=approximation(variant)
        dest.write_text(json.dumps(result)+'\n')
        print(seed,variant,'complete',result['metrics'], 'baseline_delta',maximum,flush=True)
        if variant=='legacy' and mismatches:raise AssertionError('legacy source replay mismatch')
    finally:
        runtime.close();undo()


if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('--seed',type=int,required=True,choices=RUNS)
    p.add_argument('--variant',required=True,choices=CRITERIA['variants']);p.add_argument('--output',type=Path,required=True)
    a=p.parse_args()
    a.output.mkdir(parents=True,exist_ok=True)
    # Independent offline seeds can run concurrently; duplicate requests share
    # an advisory writer lock and preserve the completed artifact verbatim.
    with (a.output/f's{a.seed}-{a.variant}.writer-lock').open('a') as lock:
        fcntl.flock(lock,fcntl.LOCK_EX)
        dest=a.output/f's{a.seed}-{a.variant}.json'
        if dest.exists():
            saved=json.loads(dest.read_text())
            assert saved['seed']==a.seed and saved['variant']==a.variant
            assert saved['criteria_sha256']==digest(HERE/'unloaded-sag-criteria.json')
            if a.variant=='legacy':assert saved['baseline_mismatches']==0
            print('preserved completed replay',dest.name,flush=True)
        else:replay(a.seed,a.variant,a.output)
