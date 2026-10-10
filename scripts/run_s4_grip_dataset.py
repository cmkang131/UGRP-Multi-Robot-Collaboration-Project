"""Frozen 24-case labeled-data diagnostic; x86 execution only, no model calls."""
import argparse
import hashlib
import json
import os
from pathlib import Path
import platform
import time
import traceback

ROOT = Path(__file__).resolve().parents[1]
RECORD = 'experiments/2026-10-06-s4-llm/s4grip2'
PLAN = ROOT/RECORD/'batch-plan.json'
BUNDLE_ID = 'zone-s4-grip-dataset-v163'
WORKFLOW = 'configs/simulation_workflows.d/s4_grip_dataset_v163.json'


def cases(job):
    p = json.loads(PLAN.read_text())
    row = next(r for r in p['runs'] if r['name'] == job)
    return row, row['cases']


def bundle(sha, rid, seed):
    from scripts.run_s3_capture_diagnostic import bundle as parent
    from harness.python_source_closure import source_closure
    b = parent(sha, 'capture', 0)
    b.update(execution_bundle_id=BUNDLE_ID, workflow_version='7.56.0', schema='ugrp.s4_grip_dataset.v163',
        seed=seed, case='cyan' if rid == 'r3' else 'pair', research_result=False, student_control=False,
        physical_supervisor='diagnostic_weld_finite_tilt_only_intentional_drop', model_calls=0,
        camera_scope='target robot own RGB only; no camera changes', concurrent_probe_limit=6,
        cap_sim_s_per_trial=16.35, cap_per_trial_s=14., stage_scope='fixed O grasp tape then stationary hold/loss labels',
        dataset_plan_sha256=hashlib.sha256(PLAN.read_bytes()).hexdigest())
    paths = set(b['source_sha256']) | set(source_closure(ROOT, ['scripts/run_s4_grip_dataset.py','sim/s4_grip_dataset.py']))
    paths.update((WORKFLOW,RECORD+'/README.md',RECORD+'/batch-plan.json'))
    b['source_sha256'] = {p:hashlib.sha256((ROOT/p).read_bytes()).hexdigest() for p in sorted(paths)}
    return b


def trial(b, rid, case, out):
    import mujoco
    import numpy as np
    from scripts import run_s3_capture_diagnostic as capture
    from sim.s4_grip_dataset import PhysicsBackend, Perturbation
    from scripts.run_final_environment_checks import write
    from scripts.run_s3_host import artifact_manifest
    out.mkdir(parents=True)
    write(out/'bundle.json', b); write(out/'case.json', case)
    host = None; started = time.monotonic()
    result = dict(status='COLLECTED', robot_id=rid, case=case, research_result=False, model_calls=0)
    try:
        host = PhysicsBackend(b,out,seed=case['seed']); host.reset(b['reset_cap_s'])
        capture.stage.previous.restore_scene(host,capture.capture_setup(dict(robot=rid,dx=0.,dy=0.,dyaw=0.)))
        start = host.now; host.set_deadline(start+14.)
        owners = ('r3',) if rid == 'r3' else ('r1','r2')
        tape,timing = capture.arm_tape(host.commands[owners[0]])
        write(out/'fixed-tape.json',dict(events=tape,timing=timing,owners=owners,post_settle_s=8.,feedback=False))
        cursor=0
        for i in range(161):
            elapsed=i*.05; host.advance_to(start+elapsed)
            while cursor<len(tape) and tape[cursor][0]<=elapsed+1e-8:
                _,sid,pulse=tape[cursor];cursor+=1
                action=dict(kind='look',pan_pulse=pulse) if sid==6 else dict(kind='arm',servo_id=sid,pulse=pulse)
                for owner in owners: host.issue(owner,action)
            host.eval_sample()
        spec=mujoco.mjtState.mjSTATE_INTEGRATION
        state=np.empty(mujoco.mj_stateSize(host.world.model,spec));mujoco.mj_getState(host.world.model,host.world.data,state,spec)
        np.savez(out/'eval_only/held-start-integration-state.npz',state=state,spec=int(spec))
        perturb=Perturbation(host,rid,case)
        # No condition, contact, detector result, or success can alter this tape.
        for i in range(61):
            relative=round(i*.1,8);host.advance_to(start+8.+relative)
            host.eval_sample();host.capture_one(rid,relative);host.label(rid,relative)
            perturb.apply(relative)  # force acts on NEXT physics interval
        result['sim_s']=host.now
        result['recorded_frames']=host.frame
    except Exception as exc:
        result.update(status='PHYSICAL_STOP' if type(exc).__name__=='PhysicalStop' else 'HOST_ERROR',failure=traceback.format_exc())
    finally:
        if host is not None: host.close()
    result['wall_s']=time.monotonic()-started
    write(out/'result.json',result);artifact_manifest(out)
    return result


def main(argv=None):
    p=argparse.ArgumentParser();p.add_argument('--expected-source-sha',required=True)
    p.add_argument('--output',type=Path,required=True);p.add_argument('--job',required=True)
    p.add_argument('--execute',action='store_true');a=p.parse_args(argv)
    row, trials=cases(a.job)
    if not a.execute:
        print(json.dumps(dict(execution_started=False,job=row,bundle_id=BUNDLE_ID)));return 0
    from scripts.run_s3_x86_probe import archive_guard
    archive_guard(a.expected_source_sha,a.output)
    if os.environ.get('LP_NUM_THREADS')!='4':raise ValueError('LP_NUM_THREADS=4 required')
    from harness.zone_pair_highpose_exact_speedups import install
    from scripts.run_final_environment_checks import write
    _,undo=install('v98-exact-v6');a.output.mkdir(parents=True)
    write(a.output/'environment.json',dict(host='oracle-x86',machine=platform.machine(),loadavg=os.getloadavg(),
        LP_NUM_THREADS=os.environ['LP_NUM_THREADS'],OMP_NUM_THREADS=os.environ.get('OMP_NUM_THREADS'),model_calls=0))
    results=[]
    try:
        for case in trials:
            results.append(trial(bundle(a.expected_source_sha,row['robot_id'],case['seed']),row['robot_id'],case,a.output/case['id']))
        write(a.output/'result.json',dict(source_sha=a.expected_source_sha,research_result=False,runs=results))
    finally:undo()
    return int(any(x['status']!='COLLECTED' for x in results))


if __name__=='__main__':raise SystemExit(main())
