"""egomap20 sealed command tours; no RGB/GT feedback to the scheduler."""
from pathlib import Path
import argparse
import json
import os
from time import monotonic
from scripts import run_wall_parallax_strafe as old
from scripts.run_wall_servo_stiffness import arm
ROOT=old.ROOT
EXP=ROOT/'experiments/2026-10-07-arena-wall-map'
RAW=Path('/Users/changmin/projects/ugrp/outputs/arena-wall-map-v1')


def acquire_case(case,out,source,backend_factory):
    plan=json.loads((EXP/(case+'-plan.json')).read_text())
    bundle=dict(source_sha=source,execution_bundle_id='egomap20-arena-tour-v1',check='arena-wall-map',
        case=case,map_id='zone_wide_two_doors_final_v3',contact_profile='cargo_noslip_v1',
        task=dict(robot_id='r3',seed=plan['seed'],destination='B',pickup_slot='P1-2'),
        spawn=plan['spawn_setup_only'],initial_servo=old.PULSES,case_cap_s=plan['cap_s'],capture_s=.1,
        options=dict(servo_stiffness='real_v1',wall_texture='tape_v1',motion_model='s2_pulse_v122',
            drive_profile='masterpi_drive_friction_v7',camera_profile='camera_v3',
            roller_collision='mesh',idle_robot_contacts='off',min_wheel_cmd='real_v1'),
        authored_plan_sha256=old.sha(EXP/(case+'-plan.json')))
    out.mkdir(parents=True,exist_ok=False)
    old.write(out/'bundle.json',bundle)
    old.write(out/'authored-plan.json',plan)
    actions={}
    for row in plan['commands']:
        tick=round(row['t']*10)
        assert abs(tick/10-row['t'])<1e-8 and tick not in actions
        actions[tick]={k:v for k,v in row.items() if k not in ('leg','t')}
    result=dict(status='HOST_ERROR',source_sha=source,case=case,model_calls=0,freeze=False,
        loadavg_start=list(os.getloadavg()),qualification='authored command tour; not autonomous exploration')
    started=monotonic()
    backend=None
    try:
        backend=backend_factory(bundle,out,seed=plan['seed'])
        backend.reset(5.)
        start=backend.now
        result['start_sim_s']=start
        backend.set_deadline(start+plan['cap_s'])
        for tick in range(round(plan['cap_s']*10)+1):
            if tick==0:
                for action in arm(old.PULSES):backend.issue('r3',action)
            if tick in actions:backend.issue('r3',actions[tick])
            backend.capture() # saved own RGB, never interpreted as simulator state
            backend.eval_sample() # write-only with physical abort; no navigation feedback
            if tick%100==0:
                old.write(out/'progress.json',dict(sim_s=tick/10,frames=tick+1))
                print(case,'SIM',tick/10,flush=True)
            if tick<round(plan['cap_s']*10):backend.advance_to(round(start+(tick+1)/10,9))
        result.update(status='RECORDED',frames=tick+1,total_sim_s=backend.now)
    except Exception as e:
        result.update(status='PHYSICAL_FAILURE' if type(e).__name__=='PhysicalStop' else 'HOST_ERROR',
            frames=backend.frame if backend is not None else 0,total_sim_s=backend.now if backend is not None else None,
            failure=dict(type=type(e).__name__,message=str(e)),enospc=getattr(e,'errno',None)==28)
    finally:
        if backend is not None:backend.close()
        result['wall_s']=monotonic()-started
        result['loadavg_end']=list(os.getloadavg())
        old.write(out/'result.json',result)
        old.write(out/'artifacts.sha256.json',{str(p.relative_to(out)):old.sha(p) for p in sorted(out.rglob('*'))
            if p.is_file() and p.name!='artifacts.sha256.json'})
    return result


def main():
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('--case',choices=['forward','reverse'],required=True)
    p.add_argument('--output',type=Path,required=True)
    p.add_argument('--expected-source-sha',required=True)
    p.add_argument('--execute',action='store_true')
    a=p.parse_args()
    receipts=old.verify_source(a.expected_source_sha)
    frozen=json.loads((EXP/'freeze.json').read_text())
    assert all(old.sha(ROOT/k)==h for k,h in frozen['files'].items())
    assert a.output.resolve()==RAW/a.case and not a.output.exists()
    if not a.execute:return 0
    from scripts.agent_lock import DEFAULT_ROOT,status,acquire,release
    assert status(DEFAULT_ROOT) is None,'physics lock occupied'
    lock=acquire(DEFAULT_ROOT,owner='codex',branch='claude/ego-wall-map',purpose='egomap20 arena '+a.case,
                 pid=os.getpid(),expected_minutes=10)
    try:
        from sim.wall_servo_stiffness import PhysicsBackend
        result=acquire_case(a.case,a.output,a.expected_source_sha,PhysicsBackend)
        old.write(a.output/'source-admission.json',receipts)
        old.write(a.output/'lock.json',lock)
    finally:release(DEFAULT_ROOT,owner='codex')
    print(json.dumps(result,ensure_ascii=False),flush=True)
    return 0 if result['status']=='RECORDED' else 1


if __name__=='__main__':raise SystemExit(main())
