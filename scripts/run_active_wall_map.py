"""egomap22 own-RGB feedback exploration / static look-ahead qualification."""
from pathlib import Path
import argparse
import json
import math
import os
from time import monotonic
from scripts import run_wall_parallax_strafe as old
from scripts.run_wall_servo_stiffness import arm

ROOT=old.ROOT
EXP=ROOT/'experiments/2026-10-07-active-wall-map'
RAW=Path('/Users/changmin/projects/ugrp/outputs/active-wall-map-v1')


def dump(path,value):
    import numpy as np
    path=Path(path)
    path.parent.mkdir(parents=True,exist_ok=True)
    def default(x):
        if isinstance(x,np.ndarray):return x.tolist()
        if isinstance(x,np.generic):return x.item()
        raise TypeError(type(x).__name__)
    path.write_text(json.dumps(value,default=default,allow_nan=False,indent=2)+'\n')


def acquire(case,out,source,backend_factory):
    from harness.active_camera import SEARCH,LOOK_AHEAD
    from harness.active_wall_mapping import ActiveMapper
    from harness.active_wall_vision import observe
    seed={'static':22000,'photo':22001,'speckle':22002}[case]
    cap=8. if case=='static' else 180.
    bundle=dict(source_sha=source,execution_bundle_id='egomap22-active-wall-map-v1',check='active-wall-map',case='active-'+case,
        map_id='zone_wide_two_doors_final_v3',contact_profile='cargo_noslip_v1',
        task=dict(robot_id='r3',seed=seed,destination='B',pickup_slot='P1-2'),
        spawn=[3.25,.75,math.pi],initial_servo=SEARCH,case_cap_s=cap,capture_s=.2,
        options=dict(servo_stiffness='real_v1',wall_texture=('off' if case=='static' else case+'_v1'),
            camera_pose='look_ahead_v1',active_mapping='frontier_rbpf_v1',active_loop='information_gain_v1',
            motion_model='s2_pulse_v122',drive_profile='masterpi_drive_friction_v7',camera_profile='camera_v3',
            roller_collision='mesh',idle_robot_contacts='off',min_wheel_cmd='real_v1'))
    out.mkdir(parents=True,exist_ok=False)
    dump(out/'bundle.json',bundle)
    result=dict(status='HOST_ERROR',source_sha=source,case=case,model_calls=0,freeze=False,loadavg_start=list(os.getloadavg()))
    started=monotonic()
    backend=controller=None
    try:
        backend=backend_factory(bundle,out,seed=seed)
        backend.reset(5.)
        start=backend.now
        result['start_sim_s']=start
        backend.set_deadline(start+cap)
        servo=SEARCH if case=='static' else LOOK_AHEAD
        for action in arm(servo):backend.issue('r3',action)
        if case!='static':controller=ActiveMapper('r3',start,servo,active_mapping='frontier_rbpf_v1',active_loop='information_gain_v1',seed=seed)
        for tick in range(round(cap*5)+1):
            t=backend.now
            if case=='static' and tick==20:
                servo=LOOK_AHEAD
                for action in arm(servo):backend.issue('r3',action)
            own=backend.capture()['r3']
            # Strict allowlist, never send actuator_state/other observation fields.
            obs,rgb=own
            if controller is not None and tick>=10:
                detection=observe(rgb,servo,body_settling=.7)
                command,trace=controller.receive(robot_id='r3',t=t,frame_id=obs['frame_id'],rgb=rgb,servo=servo,observation=detection)
                backend._append('own-controller.jsonl',trace)
                backend._append('own-contacts.jsonl',dict(t=t,frame_id=obs['frame_id'],**detection))
                if tick<round(cap*5):
                    backend.issue('r3',{k:v for k,v in command.items() if k!='t'})
                    controller.command(command)
            backend.eval_sample()
            if tick%25==0:
                print(case,'SIM',round(t-start,2),'frames',tick+1,flush=True)
                dump(out/'progress.json',dict(sim_s=t-start,frames=tick+1))
            if monotonic()-started>1800:raise TimeoutError('HOST_BUDGET_30_MINUTES')
            if tick<round(cap*5):backend.advance_to(round(start+(tick+1)*.2,9))
        result.update(status='RECORDED',frames=tick+1,total_sim_s=backend.now)
    except Exception as e:
        result.update(status='PHYSICAL_FAILURE' if type(e).__name__=='PhysicalStop' else 'HOST_ERROR',
            frames=backend.frame if backend else 0,total_sim_s=backend.now if backend else None,
            failure=dict(type=type(e).__name__,message=str(e)),enospc=getattr(e,'errno',None)==28)
        import traceback
        traceback.print_exc()
    finally:
        if backend is not None:backend.close()
        if controller is not None:
            # Seal controller outputs before a separate scoring process reads eval_only.
            dump(out/'frontend-grid.json',controller.memory.self_map.export())
            dump(out/'frontend-ledger.json',controller.memory.self_map.ledger)
            dump(out/'frontend-poses.json',controller.poses)
            dump(out/'decisions.json',controller.memory.self_map.decisions)
            dump(out/'navigation.json',controller.navigator.events)
            dump(out/'active-events.json',controller.events)
            dump(out/'graphs.json',controller.graphs)
            graph=controller.memory.finalize_pose_graph(controller.poses) if controller.poses else None
            if graph:
                dump(out/'graph.json',graph)
                dump(out/'grid.json',controller.memory._graph_view.export())
        result.update(wall_s=monotonic()-started,loadavg_end=list(os.getloadavg()))
        dump(out/'result.json',result)
        dump(out/'artifacts.sha256.json',{str(p.relative_to(out)):old.sha(p) for p in sorted(out.rglob('*')) if p.is_file() and p.name!='artifacts.sha256.json'})
    return result


def main():
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('--case',choices=['static','photo','speckle'],required=True)
    p.add_argument('--output',type=Path,required=True)
    p.add_argument('--expected-source-sha',required=True)
    p.add_argument('--execute',action='store_true')
    args=p.parse_args()
    receipts=old.verify_source(args.expected_source_sha)
    assert args.output.resolve()==RAW/args.case and not args.output.exists()
    manifest=json.loads((EXP/'navigation-source.json').read_text())
    assert all(old.sha(ROOT/k)==h for k,h in manifest['files'].items())
    if args.case!='static':assert json.loads((RAW/'static-gate.json').read_text())['passed']
    if not args.execute:return 0
    from scripts.agent_lock import DEFAULT_ROOT,status,acquire as take,release
    assert status(DEFAULT_ROOT) is None,'physics lock occupied'
    lock=take(DEFAULT_ROOT,owner='codex',branch='claude/ego-wall-map',purpose='egomap22 closed-loop '+args.case,pid=os.getpid(),expected_minutes=30)
    try:
        from sim.active_wall_map import PhysicsBackend
        result=acquire(args.case,args.output,args.expected_source_sha,PhysicsBackend)
        dump(args.output/'source-admission.json',receipts)
        dump(args.output/'lock.json',lock)
    finally:release(DEFAULT_ROOT,owner='codex')
    print(json.dumps(result,ensure_ascii=False),flush=True)
    return 0 if result['status']=='RECORDED' else 1


if __name__=='__main__':raise SystemExit(main())
