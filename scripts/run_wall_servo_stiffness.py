"""Registered egomap19 command schedules; evaluation is write-only."""
from pathlib import Path
import argparse
import json
import os
from time import monotonic
from scripts import run_wall_parallax_strafe as old

ROOT=old.ROOT
EXP=ROOT/'experiments/2026-10-07-servo-stiffness'
RAW=Path('/Users/changmin/projects/ugrp/outputs/servo-stiffness-v1')
write,sha=old.write,old.sha
CASES=('static-off','static-on','stiff-north','stiff-south')


def arm(pose):
    return [dict(kind='look',pan_pulse=v) if k==6 else dict(kind='arm',servo_id=k,pulse=v)
            for k,v in pose.items()]


def static_actions(tick):
    from harness.zone_pair_highpose import HIGH,raise_path
    from harness.zone_final_pair_vision import grasp_postures
    hover,descent=grasp_postures()
    poses={0:old.PULSES,60:{1:2000,**HIGH},120:{1:2000,**hover},
           **{180+10*i:{1:2000,**p} for i,p in enumerate(descent)},
           250:{1:1500},270:{1:1500,**hover},
           310:{1:1500,**raise_path()[0][0]},350:{1:1500,**raise_path()[1][0]},
           390:{1:1500,**HIGH}}
    if tick in poses:return arm(poses[tick])
    if tick in (480,510):
        return [dict(kind='mecanum',forward=0.,left=.65 if tick==480 else -.65,
                     turn=0.,duration_s=.65)]
    return []


def acquire_case(case,out,source,backend_factory,*,servo_stiffness='off'):
    static=case.startswith('static-')
    direction='strafe-north' if static else case.replace('stiff-','strafe-')
    spec=old.CASES[direction]
    cap=55. if static else 18.
    bundle=dict(source_sha=source,execution_bundle_id='egomap19-servo-stiffness-v1',
        check='servo-stiffness',case=case,map_id='zone_wide_two_doors_final_v3',
        contact_profile='cargo_noslip_v1',task=dict(robot_id='r3',seed=19101 if static else spec['seed'],
        destination='B',pickup_slot='P1-2'),spawn=spec['spawn'],initial_servo=old.PULSES,
        options=dict(servo_stiffness=servo_stiffness,wall_texture='off' if static else 'tape_v1',
            drive_profile='masterpi_drive_friction_v7',camera_profile='camera_v3',
            roller_collision='mesh',idle_robot_contacts='off',min_wheel_cmd='real_v1'),
        case_cap_s=cap,capture_s=.1)
    out.mkdir(parents=True,exist_ok=False)
    write(out/'bundle.json',bundle)
    result=dict(status='HOST_ERROR',source_sha=source,case=case,loadavg_start=list(os.getloadavg()),
        model_calls=0,freeze=False,qualification='authored mechanical diagnostic, no student success claim')
    backend=None
    started=monotonic()
    try:
        backend=backend_factory(bundle,out,seed=bundle['task']['seed'])
        backend.reset(5.)
        start=backend.now
        result['start_sim_s']=start
        backend.set_deadline(start+cap)
        for i in range(round(cap*10)+1):
            for action in (static_actions(i) if static else old.actions(direction,i)):
                backend.issue('r3',action)
            backend.capture()
            backend.eval_sample()
            if i%20==0:
                write(out/'progress.json',dict(sim_s=i/10,frames=i+1))
                print(case,'SIM',i/10,flush=True)
            if i<round(cap*10):backend.advance_to(round(start+(i+1)/10,9))
        result.update(status='RECORDED',frames=round(cap*10)+1,total_sim_s=backend.now)
    except Exception as e:
        result.update(status='PHYSICAL_FAILURE' if type(e).__name__=='PhysicalStop' else 'HOST_ERROR',
            failure=dict(type=type(e).__name__,message=str(e)),enospc=getattr(e,'errno',None)==28)
    finally:
        if backend is not None:backend.close()
        result['wall_s']=monotonic()-started
        result['loadavg_end']=list(os.getloadavg())
        write(out/'result.json',result)
        write(out/'artifacts.sha256.json',{str(p.relative_to(out)):sha(p) for p in sorted(out.rglob('*'))
              if p.is_file() and p.name!='artifacts.sha256.json'})
    return result


def main():
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('--case',choices=CASES,required=True)
    p.add_argument('--servo-stiffness',choices=['off','real_v1'],default='off')
    p.add_argument('--expected-source-sha',required=True)
    p.add_argument('--output',type=Path,required=True)
    p.add_argument('--execute',action='store_true')
    a=p.parse_args()
    admission=old.verify_source(a.expected_source_sha)
    assert a.output.resolve()==RAW/a.case and not a.output.exists()
    assert a.servo_stiffness==('off' if a.case=='static-off' else 'real_v1')
    if a.case.startswith('stiff-'):
        assert json.loads((EXP/'results/static-summary.json').read_text())['static_gate_passed']
    if not a.execute:
        print(json.dumps(dict(admitted=True,physics_started=False)))
        return 0
    from scripts.agent_lock import DEFAULT_ROOT,status,acquire,release
    assert status(DEFAULT_ROOT) is None,'physics lock occupied'
    lock=acquire(DEFAULT_ROOT,owner='codex',branch='claude/ego-wall-map',
        purpose='egomap19 servo stiffness '+a.case,pid=os.getpid(),expected_minutes=10)
    try:
        from sim.wall_servo_stiffness import PhysicsBackend
        result=acquire_case(a.case,a.output,a.expected_source_sha,PhysicsBackend,
            servo_stiffness=a.servo_stiffness)
        write(a.output/'source-admission.json',admission)
        write(a.output/'lock.json',lock)
    finally:
        release(DEFAULT_ROOT,owner='codex')
    print(json.dumps(result,ensure_ascii=False),flush=True)
    return 0 if result['status']=='RECORDED' else 1


if __name__=='__main__':raise SystemExit(main())
