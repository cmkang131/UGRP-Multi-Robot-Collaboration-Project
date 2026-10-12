"""One r3 mode/split DEV job, four fixed trials, no model or Mac execution."""
import argparse
import base64
import hashlib
import json
import os
from pathlib import Path
import random
import time
import traceback
import numpy as np

ROOT=Path(__file__).resolve().parents[1]
RECORD='experiments/2026-10-06-s4-llm/s4grip3'
PLAN=ROOT/RECORD/'plan.json'
BUNDLE_ID='zone-s4-grip-r3-v165'
WORKFLOW='configs/simulation_workflows.d/s4_grip_r3_v165.json'


def sha(path):return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def cases(job):
    p=json.loads(PLAN.read_text());row=next(r for r in p['runs'] if r['name']==job)
    rows=[]
    for seed in p['seeds'][row['split']]:
        rng=random.Random(seed);angle=rng.uniform(-np.pi,np.pi);force=rng.uniform(.4,.8)
        onset=round(2.+rng.randrange(4)*.1,1)
        for variant in ('hold','loss'):
            rows.append(dict(id=f'{row["split"]}-s{seed}-{variant}',split=row['split'],seed=seed,
                variant=variant,onset_s=onset,force_xy_n=[round(force*np.cos(angle),6),round(force*np.sin(angle),6)]))
    return row,rows


def bundle(sha_value,mode,seed):
    from scripts.run_s4_grip_dataset import bundle as parent
    from harness.python_source_closure import source_closure
    b=parent(sha_value,'r3',seed)
    b.update(execution_bundle_id=BUNDLE_ID,workflow_version='7.58.0',schema='ugrp.s4grip3.v165',
        mode=mode,concurrent_probe_limit=10,model_calls=0,research_result=False,
        setup='unchanged S3 O r3 fixed tape; camera mount/FOV unchanged',
        camera_scope='r3 own RGB; warmup0/4s plus 0.1s monitor',
        control_scope='fixed r3 tape plus one own-RGB-triggered bounded arm reobserve only',
        dataset_plan_sha256=sha(PLAN))
    paths=set(b['source_sha256'])|set(source_closure(ROOT,['scripts/run_s4_grip_r3.py','sim/s4_grip_r3.py','harness/s4_grip_r3.py']))
    paths.update((WORKFLOW,RECORD+'/plan.json',RECORD+'/README.md'))
    b['source_sha256']={p:sha(ROOT/p) for p in sorted(paths)}
    return b


def write(path,value):
    path=Path(path);path.parent.mkdir(parents=True,exist_ok=True)
    path.write_text(json.dumps(value,allow_nan=False)+'\n')


def trial(b,case,out,job_out):
    from scripts import run_s3_capture_diagnostic as capture
    from scripts.run_s3_host import artifact_manifest
    from sim.s4_grip_r3 import PhysicsBackend
    from sim.s4_grip_dataset import Perturbation
    from harness.s4_grip_r3 import R3Grip
    from harness.owncam_pair_beam import decode
    out.mkdir(parents=True,exist_ok=False);write(out/'bundle.json',b);write(out/'case.json',case)
    host=None;started=time.monotonic();sensor=R3Grip(b['mode']);issued=0;sids=set();span=0.;initial=None
    result=dict(status='COLLECTED',case=case,mode=b['mode'],research_result=False,model_calls=0)
    def health(phase,status='RUNNING',error=None):
        nonlocal span,initial
        if host is not None and host.world is not None:
            tip=host.world.data.body('r3__gripper').xpos.copy()
            if initial is None:initial=tip.copy()
            span=max(span,float(np.linalg.norm(tip-initial)))
            row=dict(case=case['id'],mode=b['mode'],status=status,phase=phase,sim_time=host.now,
                frames=host.frame,issued_commands=issued,servo_ids=sorted(sids),arm_displacement_m=span,
                gripper_body_xyz_m=tip.tolist(),wall_elapsed_s=time.monotonic()-started,error=error,
                qualification='evaluation-only early liveness; base intentionally stationary')
        else:row=dict(case=case['id'],status=status,phase=phase,error=error)
        write(job_out/'health.json',row)
        with (job_out/'health-history.jsonl').open('a') as f:f.write(json.dumps(row)+'\n')
    def issue(sid,pulse):
        nonlocal issued
        action=dict(kind='look',pan_pulse=pulse) if sid==6 else dict(kind='arm',servo_id=sid,pulse=pulse)
        host.issue('r3',action);issued+=1;sids.add(sid)
    try:
        host=PhysicsBackend(b,out,seed=case['seed']);host.reset(b['reset_cap_s'])
        capture.stage.previous.restore_scene(host,capture.capture_setup(dict(robot='r3',dx=0.,dy=0.,dyaw=0.)))
        start=host.now;host.set_deadline(start+14.)
        tape,timing=capture.arm_tape(host.commands['r3']);cursor=0
        write(out/'fixed-tape.json',dict(events=tape,timing=timing,owners=['r3'],post_settle_s=8.))
        health('GRASP_LIFT')
        for i in range(161):
            elapsed=round(i*.05,8);host.advance_to(round(start+elapsed,9))
            while cursor<len(tape) and tape[cursor][0]<=elapsed+1e-8:
                _,sid,pulse=tape[cursor];cursor+=1;issue(sid,pulse)
            host.eval_sample()
            if i in (0,80):host.capture_r3(elapsed-8.,'warmup')
            if i%20==0:health('GRASP_LIFT')
        perturb=Perturbation(host,'r3',case);pending=[];cursor=0
        for i in range(61):
            relative=round(i*.1,8);host.advance_to(round(start+8.+relative,9))
            while cursor<len(pending) and pending[cursor][0]<=host.now+1e-8:
                _,sid,pulse=pending[cursor];cursor+=1;issue(sid,pulse)
            image=host.capture_r3(relative,'monitor')
            prediction=sensor.observe(decode(image),host.now)
            host._append('robots/r3/predictions.jsonl',dict(sim_time=host.now,relative_s=relative,**prediction))
            reobserve=sensor.request_reobserve(relative,host.now,dict(host.commands['r3']))
            if reobserve:
                pending=reobserve['events'];cursor=0
                host._append('robots/r3/reobserve.jsonl',dict(sim_time=host.now,relative_s=relative,**reobserve))
            # Contact dump and labels now share the AFTER-capture forward state.
            # They are never passed to sensor or command policy.
            host.eval_sample();host.label('r3',relative);perturb.apply(relative)
            if i%5==0:
                if hasattr(host,'flush'):host.flush()
                health('REOBSERVE' if sensor.moving_until is not None else 'POST_GRASP_MONITOR')
        result.update(sim_s=host.now,frames=host.frame,monitor_frames=61,reobserve_attempts=int(sensor.reobserved),
            commands=issued,arm_displacement_m=span)
        health('COMPLETE','COLLECTED')
    except Exception as exc:
        result.update(status='PHYSICAL_STOP' if type(exc).__name__=='PhysicalStop' else 'HOST_ERROR',failure=traceback.format_exc())
        health('FAILED','ERROR',result['failure'].splitlines()[-1])
    finally:
        if host is not None:host.close()
    result['wall_s']=time.monotonic()-started;write(out/'result.json',result);artifact_manifest(out)
    return result


def main(argv=None):
    p=argparse.ArgumentParser();p.add_argument('--expected-source-sha',required=True);p.add_argument('--output',type=Path,required=True)
    p.add_argument('--job',required=True);p.add_argument('--execute',action='store_true');a=p.parse_args(argv)
    row,seq=cases(a.job)
    if not a.execute:print(json.dumps(dict(execution_started=False,job=row,cases=seq)));return 0
    from scripts.run_s3_x86_probe import archive_guard
    archive_guard(a.expected_source_sha,a.output)
    if os.environ.get('LP_NUM_THREADS')!='4':raise ValueError('LP_NUM_THREADS=4 required')
    for path,digest in json.loads(PLAN.read_text())['frozen_paths_sha256'].items():
        if sha(ROOT/path)!=digest:raise ValueError('frozen beam/legacy source changed')
    job_out=a.output.parent;write(job_out/'driver.json',dict(pid=os.getpid(),pgid=os.getpgid(0),job=a.job,source_sha=a.expected_source_sha))
    a.output.mkdir(parents=True,exist_ok=False)
    write(a.output/'environment.json',dict(loadavg=os.getloadavg(),LP_NUM_THREADS=os.environ['LP_NUM_THREADS'],model_calls=0))
    from harness.zone_pair_highpose_exact_speedups import install
    _,undo=install('v98-exact-v6');results=[]
    try:
        for case in seq:
            results.append(trial(bundle(a.expected_source_sha,row['mode'],case['seed']),case,a.output/case['id'],job_out))
            if results[-1]['status']!='COLLECTED':break
        write(a.output/'result.json',dict(source_sha=a.expected_source_sha,mode=row['mode'],split=row['split'],runs=results,research_result=False))
    finally:undo()
    return int(len(results)!=4 or any(r['status']!='COLLECTED' for r in results))


if __name__=='__main__':raise SystemExit(main())
