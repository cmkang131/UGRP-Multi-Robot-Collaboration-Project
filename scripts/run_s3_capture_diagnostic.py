"""Frozen evaluation-only capture grid and low pulses; Oracle x86 only.

Scene setup may use saved truth, but acquisition is a fixed command tape.
No pose/contact/outcome is returned to any controller (there is no student).
"""
import argparse
import copy
import hashlib
import itertools
import json
import math
import os
from pathlib import Path
import platform
import time
import traceback
import numpy as np
from scripts import run_s3_x86_probe as stage
from scripts.run_s3_x86_pulse_measure import measurement_setup, pose
from scripts.run_final_environment_checks import write
from scripts.run_s3_host import artifact_manifest
from sim.s3_capture_diagnostic import PhysicsBackend, OPTION, LEVELS

BUNDLE_ID='zone-s3-capture-diagnostic-v160'
WORKFLOW='configs/simulation_workflows.d/s3_capture_diagnostic_v160.json'
RECORD='experiments/2026-10-10-s3-capture-region'
XY=(-.024,-.012,0.,.012,.024)
YAW=(-.14,0.,.14)
CAP=12.


def capture_grid(robot, yaw_index):
    if robot not in ('r1','r2','r3') or yaw_index not in range(3):raise ValueError('unregistered grid')
    return [dict(robot=robot,dx=x,dy=y,dyaw=YAW[yaw_index]) for x,y in itertools.product(XY,XY)]


def low_sequence():
    return [dict(kind='mecanum',forward=0.,left=0.,turn=0.,duration_s=.10)|{axis:sign*level}
        for repeat in range(2) for level in LEVELS for axis in ('forward','left','turn') for sign in (1,-1)]


def capture_setup(row):
    from harness.owncam_pair_beam_v2 import pose_of
    from sim.zone_model_conventions import station_offset
    from harness.zone_final_pair_vision import GRASP_RADIUS_M
    setup=stage.setup_record(None,'cyan' if row['robot']=='r3' else 'pair')
    beam=setup['truth']['items']['beam_1'];cyan=setup['truth']['items']['cyan_1']
    for rid,role in (('r1','end_neg'),('r2','end_pos'),('r3','west')):
        item=cyan if rid=='r3' else beam
        ox,oy,a=(-GRASP_RADIUS_M,0.,0.) if rid=='r3' else station_offset({'robot_model':'masterpi_v3'},'long_beam',role)
        c,s=math.cos(item['yaw']),math.sin(item['yaw'])
        yaw=item['yaw']+a
        xyz=[item['x']+c*ox-s*oy,item['y']+s*ox+c*oy,.032]
        if rid==row['robot']:
            # Grid coordinates are the same grip-centre base-frame errors as
            # RGB alignment, not chassis deltas mixed with a 203mm yaw lever.
            gx=xyz[0]+GRASP_RADIUS_M*math.cos(yaw)
            gy=xyz[1]+GRASP_RADIUS_M*math.sin(yaw)
            yaw+=row['dyaw'];c1,s1=math.cos(yaw),math.sin(yaw)
            xyz[0]=gx-c1*(GRASP_RADIUS_M+row['dx'])+s1*row['dy']
            xyz[1]=gy-s1*(GRASP_RADIUS_M+row['dx'])-c1*row['dy']
        setup['robots'][rid]['pose'].update(robot_xyz_m=xyz,robot_yaw_rad=yaw)
        setup['robots'][rid]['frame']['commanded_servo']={1:2000,**pose_of('inspect')}
    setup.update(classification='evaluation-only fixed grip-centre alignment-error grid; partner nominal',
                 grid=copy.deepcopy(row),runtime_gt=False)
    return setup


def arm_tape(initial):
    """Same ArmSequence hover/descent/close/low-lift as the existing cyan path."""
    from scripts.zone_teacher import ArmSequence
    from harness.zone_final_pair_vision import grasp_postures
    from harness.zone_pair_highpose_blind_close import HOVER_SETTLE_S, DESCENT_STEP_S
    hover,path=grasp_postures();arm=ArmSequence(None,initial)
    arm.queue({**hover,1:2000},0.,duration=1.,settle=HOVER_SETTLE_S)
    for p in path:arm.queue(p,0.,duration=DESCENT_STEP_S,settle=0.)
    arm.until+=HOVER_SETTLE_S
    close_start=arm.until
    arm.queue({1:1500},0.,duration=.5,settle=.4)
    lift_start=arm.until
    arm.queue({**hover,1:1500},0.,duration=1.2,settle=2.8)
    assert arm.until<CAP
    return list(arm.events),dict(close_start=close_start,lift_start=lift_start,settled_at=arm.until)


def evaluate_capture(host, rid, elapsed):
    item='cyan_1' if rid=='r3' else 'beam_1';d=host.world.data
    owners=('r3',) if rid=='r3' else ('r1','r2')
    fingers={r:[False,False] for r in owners}
    for c in d.contact[:d.ncon]:
        pair={int(c.geom1),int(c.geom2)}
        if pair & host._box_geom[item]:
            for r in owners:
                for i,f in enumerate(host._fingers[r]):fingers[r][i] |= bool(pair & f)
    return dict(t=elapsed,com_z_m=float(d.body(host.objects[item]['body_name']).xipos[2]),
                fingers=fingers,evaluation_only=True)


def bundle(sha,kind,condition):
    b=stage.bundle(sha,'pair',condition=condition)
    b.update(execution_bundle_id=BUNDLE_ID,workflow_version='7.53.0',schema='ugrp.s3_capture_diagnostic.v160',
        student_control=False,research_result=False,diagnostic_low_pulse=OPTION if kind=='pulse' else 'off',
        diagnostic=kind,concurrent_probe_limit=10,servo_option='off',
        physical_supervisor='S3_drop_tilt_nonfinite_v1',cap_per_trial_s=CAP if kind=='capture' else 48.,
        setup_truth_scope='evaluation-only perturbation; no live feedback or success-driven action',
        camera_scope='nominal capture trial only; diagnostic trajectories do not require images')
    from harness.python_source_closure import source_closure
    paths=set(source_closure(stage.ROOT,['scripts/run_s3_capture_diagnostic.py']))|{WORKFLOW,RECORD+'/README.md',RECORD+'/diagnostic-plan.json'}
    b['source_sha256'].update({p:hashlib.sha256((stage.ROOT/p).read_bytes()).hexdigest() for p in paths})
    return b


def capture_trial(b,row,out,*,cap=CAP):
    out.mkdir(parents=True,exist_ok=False);write(out/'bundle.json',b)
    result=dict(status='HOST_ERROR',grid=row,host='oracle-x86',student_control=False,research_result=False)
    host=None;started=time.monotonic();samples=[]
    try:
        host=PhysicsBackend(b,out,seed=b['seed']);host.reset(b['reset_cap_s'])
        setup=capture_setup(row);stage.previous.restore_scene(host,setup)
        start=host.now;host.set_deadline(start+cap)
        owners=('r3',) if row['robot']=='r3' else ('r1','r2')
        tape,timing=arm_tape(host.commands[owners[0]])
        write(out/'fixed-tape.json',dict(events=tape,timing=timing,owners=owners))
        index=0
        for i in range(round(cap/.05)+1):
            elapsed=round(i*.05,8);host.advance_to(round(start+elapsed,9))
            while index<len(tape) and tape[index][0]<=elapsed+1e-9:
                _,sid,pulse=tape[index]
                action=dict(kind='look',pan_pulse=pulse) if sid==6 else dict(kind='arm',servo_id=sid,pulse=pulse)
                for rid in owners:host.issue(rid,action)
                index+=1
            host.eval_sample();samples.append(evaluate_capture(host,row['robot'],elapsed))
            if row['dx']==row['dy']==row['dyaw']==0 and i%4==0:host.capture()
        own=lambda s:all(s['fingers'][row['robot']])
        grasp=[s for s in samples if timing['close_start']+.5<=s['t']<timing['lift_start'] and own(s)]
        window=[s for s in samples if s['t']>=cap-1.-1e-8]
        lifted=lambda s: s['com_z_m']>.06 and all(all(f) for f in s['fingers'].values())
        result.update(status='COLLECTED',sim_s=cap,timing=timing,grasp=len(grasp)>=4,
            lift=len(window)>=20 and all(lifted(s) for s in window),
            bilateral_grasp_samples=len(grasp),contact_lift_samples=sum(lifted(s) for s in samples),
            max_z_m=max(s['com_z_m'] for s in samples),end_z_m=samples[-1]['com_z_m'])
    except Exception as exc:
        from sim.zone_s3_no_prior import PhysicalStop
        result['failure']=traceback.format_exc()
        result['status']='PHYSICAL_STOP' if isinstance(exc,PhysicalStop) else 'HOST_ERROR'
        result['sim_s']=host.now-start if host and 'start' in locals() else 0.
        result.update(grasp=False,lift=False)
    finally:
        if host:host.close()
        result['wall_s']=time.monotonic()-started;write(out/'result.json',result)
        (out/'capture-samples.jsonl').write_text(''.join(json.dumps(s)+'\n' for s in samples))
        artifact_manifest(out)
    return result


def pulse_run(b,out):
    host=None;started=time.monotonic();rows=[]
    result=dict(status='HOST_ERROR',host='oracle-x86',student_control=False,research_result=False)
    try:
        host=PhysicsBackend(b,out,seed=b['seed']);host.reset(b['reset_cap_s'])
        stage.previous.restore_scene(host,measurement_setup(b['initial_condition']))
        start=host.now;host.set_deadline(start+48.)
        for index,action in enumerate(low_sequence()):
            t=host.now;origins={r:pose(host,r) for r in stage.previous.ROBOTS};curves={r:[] for r in origins}
            times=np.round(np.arange(0,1.001,.01),8)
            for rid in origins:host.issue(rid,action)
            for dt in times:
                host.advance_to(round(t+float(dt),9))
                for rid,q0 in origins.items():
                    d=pose(host,rid)-q0;c,s=math.cos(q0[2]),math.sin(q0[2])
                    curves[rid].append([c*d[0]+s*d[1],-s*d[0]+c*d[1],math.atan2(math.sin(d[2]),math.cos(d[2]))])
            host.eval_sample()
            rows.extend(dict(index=index,robot=rid,action=action,times=times.tolist(),curve=curve,
                evaluation_only=True) for rid,curve in curves.items())
        result.update(status='COLLECTED',sim_s=host.now-start,rows=len(rows))
    except Exception:result['failure']=traceback.format_exc()
    finally:
        if host:host.close()
        result['wall_s']=time.monotonic()-started;write(out/'result.json',result)
        (out/'pulse-responses.jsonl').write_text(''.join(json.dumps(r)+'\n' for r in rows));artifact_manifest(out)
    return result


def main():
    p=argparse.ArgumentParser();p.add_argument('--expected-source-sha',required=True);p.add_argument('--output',type=Path,required=True)
    p.add_argument('--kind',choices=('capture','pulse'),required=True);p.add_argument('--condition',type=int,choices=range(6),default=0)
    p.add_argument('--robot',choices=('r1','r2','r3'),default='r1');p.add_argument('--yaw-index',type=int,choices=range(3),default=0)
    p.add_argument('--path-check',action='store_true');p.add_argument('--execute',action='store_true');a=p.parse_args()
    if not a.execute:print(json.dumps(dict(execution_started=False,bundle_id=BUNDLE_ID)));return 0
    stage.archive_guard(a.expected_source_sha,a.output)
    b=bundle(a.expected_source_sha,a.kind,a.condition)
    a.output.mkdir(parents=True,exist_ok=False);write(a.output/'bundle.json',b)
    write(a.output/'environment.json',dict(host='oracle-x86',machine=platform.machine(),MUJOCO_GL=os.getenv('MUJOCO_GL'),
        LP_NUM_THREADS=os.getenv('LP_NUM_THREADS'),OMP_NUM_THREADS=os.getenv('OMP_NUM_THREADS'),loadavg=os.getloadavg()))
    from harness.zone_pair_highpose_exact_speedups import install
    _,undo=install('v98-exact-v6')
    try:
        if a.kind=='pulse':r=pulse_run(b,a.output)
        else:
            grid=[dict(robot=a.robot,dx=0.,dy=0.,dyaw=0.)] if a.path_check else capture_grid(a.robot,a.yaw_index)
            results=[capture_trial(b,row,a.output/f'trial-{i:02}',cap=8. if a.path_check else CAP) for i,row in enumerate(grid)]
            r=dict(status='COLLECTED' if all(x['status']=='COLLECTED' for x in results) else 'COLLECTED_WITH_FAILURES',
                host='oracle-x86',results=results,student_control=False,research_result=False,
                sim_s=sum(x.get('sim_s',0) for x in results),wall_s=sum(x['wall_s'] for x in results))
            write(a.output/'result.json',r);artifact_manifest(a.output)
    finally:undo()
    print(json.dumps(r));return int(r['status'] not in ('COLLECTED','COLLECTED_WITH_FAILURES'))


if __name__=='__main__':raise SystemExit(main())
