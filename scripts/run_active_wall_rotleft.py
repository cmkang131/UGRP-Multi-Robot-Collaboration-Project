"""egomap34 supervisor-authorized rotL DEV; egomap33 gate remains 5/7."""
from pathlib import Path
import argparse
import json
import math
import os
from time import monotonic
from scripts import run_wall_parallax_strafe as old
from scripts.run_wall_servo_stiffness import arm

ROOT=old.ROOT
EXP=ROOT/'experiments/2026-10-08-wall-segment-dev'
RAW=Path('/Users/changmin/projects/ugrp/outputs/wall-segment-dev-v1')


def dump(path,value):
    import numpy as np
    path=Path(path)
    path.parent.mkdir(parents=True,exist_ok=True)
    def default(x):
        if isinstance(x,np.ndarray):return x.tolist()
        if isinstance(x,np.generic):return x.item()
        raise TypeError(type(x).__name__)
    path.write_text(json.dumps(value,default=default,allow_nan=False,indent=2)+'\n')


def install_profile(grid, *, profile='off'):
    if profile == 'off':return grid
    if profile != 'egomap27_wide':raise ValueError('FROZEN_PROFILE_REQUIRED')
    from harness.rbpf_motion_gate import install as motion, OPTION as MOTION
    from harness.rbpf_rejection import install as selective, OPTION as SELECTIVE
    from harness.rbpf_composition import install as compose, OPTION as COMPOSE, SEARCH
    from harness.rbpf_manhattan import install as manhattan, OPTION as MANHATTAN
    motion(grid,rbpf_update=MOTION)
    selective(grid,rbpf_rejection=SELECTIVE)
    compose(grid,rbpf_composition=COMPOSE,rbpf_search=SEARCH)
    return manhattan(grid,yaw_prior=MANHATTAN)


def frozen_bundle(case, source):
    from harness.active_camera import SEARCH
    from harness.rbpf_motion_gate import OPTION
    seed=32002
    cap=180.
    bundle=dict(source_sha=source,execution_bundle_id='egomap34-rotleft-dev-v1',check='active-rotleft-dev',case='active-'+case,
        map_id='zone_wide_two_doors_final_v3',contact_profile='cargo_noslip_v1',
        task=dict(robot_id='r3',seed=seed,destination='B',pickup_slot='P1-2'),
        spawn=[3.25,.75,math.pi],initial_servo=SEARCH,case_cap_s=cap,capture_s=.2,
        options=dict(servo_stiffness='real_v1',wall_texture='tape_v1',
            camera_pose='SEARCH',navigation_map='public_ros_v8',active_recovery='nav2_frontier_v1',rbpf_update=OPTION,rbpf_rejection='gmapping_selective_v1',
            rbpf_composition='insert_selective_v1',rbpf_search='correlative_20deg_v1',yaw_prior='manhattan_v1',active_mapping='frontier_rbpf_v1',active_loop='information_gain_v1',
            motion_model='s2_pulse_v122_rotL_v1',drive_profile='masterpi_drive_friction_v7',camera_profile='camera_v3',
            roller_collision='mesh',idle_robot_contacts='off',min_wheel_cmd='real_v1'))
    from harness.active_wall_mapping import OPTIONS
    bundle['estimator_options']={**OPTIONS, 'motion_model':'s2_pulse_v122_rotL_v1'}
    bundle['admission']='supervisor_authorized_DEV; egomap33_gate_5_of_7_UNMET'
    bundle['profile']='egomap27_wide'
    return bundle


def acquire(case,out,source,backend_factory):
    from harness.active_camera import SEARCH
    from harness.active_wall_recovery import make_mapper
    from harness.active_wall_vision import observe
    bundle=frozen_bundle(case,source)
    seed=bundle['task']['seed']
    cap=bundle['case_cap_s']
    last_snapshot=None
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
        servo=SEARCH
        for action in arm(servo):backend.issue('r3',action)
        controller=make_mapper('r3',start,servo,active_mapping='frontier_rbpf_v1',active_loop='information_gain_v1',seed=seed,active_recovery='nav2_frontier_v1',navigation_map='public_ros_v8',motion_model='s2_pulse_v122_rotL_v1')
        install_profile(controller.memory.self_map,profile='egomap27_wide')
        for tick in range(round(cap*5)+1):
            t=backend.now
            own=backend.capture()['r3']
            # Strict allowlist, never send actuator_state/other observation fields.
            obs,rgb=own
            if controller is not None and tick>=10:
                detection=observe(rgb,servo,body_settling=.7)
                command,trace=controller.receive(robot_id='r3',t=t,frame_id=obs['frame_id'],rgb=rgb,servo=servo,observation=detection)
                backend._append('own-controller.jsonl',trace)
                g=controller.memory.self_map
                backend._append('frontend-covariances.jsonl',dict(t=t,frame_id=obs['frame_id'],
                    pose=list(g.odom.pose),covariance=g.odom.covariance.tolist()))
                revision=(g.revision,g.best,g.resamples)
                if revision!=last_snapshot:
                    # Capture now, never reconstruct history from the final particle/map.
                    backend._append('online-maps.jsonl',dict(t=t,frame_id=obs['frame_id'],
                        view='online_frontend',grid=g.export(),ledger=g.ledger))
                    last_snapshot=revision
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
        import signal
        signal.setitimer(signal.ITIMER_REAL,0)
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
            graph=getattr(controller.memory,'pose_graph_result',None)
            complete=bool(graph and graph['poses'] and graph['poses'][-1]['t']==controller.poses[-1]['t'])
            result['prediction_view']='completed_graph' if complete else 'partial_frontend_unfinished_graph'
            if not complete:
                from harness.self_wall_evidence import build_evidence
                ledger=[dict(r,robot_id='r3') for r in controller.memory.self_map.ledger]
                graph=dict(ledger=ledger,poses=controller.poses,diagnostics=dict(loop_counts=None,switch_counts=None),
                    wall_evidence=build_evidence(ledger,robot_id='r3',wall_evidence='tsdf_weight_v1'))
            if graph:
                dump(out/'graph.json',graph)
                dump(out/'grid.json',controller.memory._graph_view.export() if complete else controller.memory.self_map.export())
        result.update(wall_s=monotonic()-started,loadavg_end=list(os.getloadavg()))
        dump(out/'result.json',result)
        dump(out/'artifacts.sha256.json',{str(p.relative_to(out)):old.sha(p) for p in sorted(out.rglob('*')) if p.is_file() and p.name!='artifacts.sha256.json'})
    return result



def verify_source(expected):
    import subprocess
    git=lambda *a:subprocess.check_output(['git',*a],cwd=ROOT,text=True).strip()
    assert git('branch','--show-current')=='claude/ego-wall-map'
    assert git('rev-parse','HEAD')==expected
    assert not git('diff','HEAD','--name-only')
    assert set(git('ls-files','--others','--exclude-standard').splitlines())==set(old.USER_FILES)
    assert all(old.sha(ROOT/p)==h for p,h in old.USER_FILES.items())
    remote=git('rev-parse','origin/claude/ego-wall-map')
    subprocess.run(['git','merge-base','--is-ancestor',remote,expected],cwd=ROOT,check=True)
    return dict(source_sha=expected,remote_sha=remote,push_pending=remote!=expected,
                admission='committed local source; explicit user server-500 exception if unpushed',
                preserved_untracked=old.USER_FILES)

def main():
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('--case',choices=['new-seed'],required=True)
    p.add_argument('--output',type=Path,required=True)
    p.add_argument('--expected-source-sha',required=True)
    p.add_argument('--execute',action='store_true')
    args=p.parse_args()
    receipts=verify_source(args.expected_source_sha)
    frozen=json.loads((EXP/'freeze.json').read_text())
    assert all(old.sha(ROOT/p)==digest for p,digest in frozen['hashes'].items())
    receipts['egomap27_wide_hashes']=frozen['hashes']
    assert args.output.resolve()==RAW/args.case and not args.output.exists()
    manifest=json.loads((ROOT/'experiments/2026-10-07-active-wall-map/navigation-source.json').read_text())
    assert all(old.sha(ROOT/k)==h for k,h in manifest['files'].items())
    if not args.execute:return 0
    from scripts.agent_lock import DEFAULT_ROOT,status,acquire as take,release
    assert status(DEFAULT_ROOT) is None,'physics lock occupied'
    lock=take(DEFAULT_ROOT,owner='codex',branch='claude/ego-wall-map',purpose='egomap34 supervisor DEV rotL seed 32002',pid=os.getpid(),expected_minutes=30)
    try:
        import signal
        def budget_stop(*_):raise TimeoutError('HOST_BUDGET_30_MINUTES')
        signal.signal(signal.SIGALRM,budget_stop)
        signal.setitimer(signal.ITIMER_REAL,1800)
        from sim.active_wall_map import PhysicsBackend
        result=acquire(args.case,args.output,args.expected_source_sha,PhysicsBackend)
        dump(args.output/'source-admission.json',receipts)
        dump(args.output/'lock.json',lock)
    finally:release(DEFAULT_ROOT,owner='codex')
    print(json.dumps(result,ensure_ascii=False),flush=True)
    return 0 if result['status']=='RECORDED' else 1


if __name__=='__main__':raise SystemExit(main())
