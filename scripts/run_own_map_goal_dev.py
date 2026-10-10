"""egomap43 exactly one preregistered unknown-start own-B closed-loop DEV."""
from pathlib import Path
import argparse
import json
import os
import signal
from time import monotonic
from scripts import run_active_wall_rotleft as base
from scripts.run_wall_servo_stiffness import arm
from harness.self_map_closed_loop import attach,OPTION
ROOT=base.ROOT
RAW=Path('/Users/changmin/projects/ugrp/outputs/own-map-closed-loop-v1')
dump=base.dump


def bundle(source):
    b=base.frozen_bundle('new-seed',source)
    b.update(execution_bundle_id='egomap43-own-B-dev-v1',check='own-map-goal',case='new-seed',case_cap_s=360.,
        admission='user_authorized_DEV_1; offline utility gate not required',preregistration='91e4fd50')
    b['task']['seed']=43001
    b['options'].update(map_utility=OPTION,likelihood_tempering='pr_likelihood_half_v1',sensor_landmarks='floor_zones_doors_v1')
    return b


def acquire(out,source,backend_factory,*,bundle_override=None,mapper_factory=None,controller_factory=None,progress_label='egomap43'):
    from harness.active_camera import SEARCH
    from harness.active_wall_recovery import make_mapper
    from harness.active_wall_vision import observe
    b=bundle(source) if bundle_override is None else bundle_override
    cap=b['case_cap_s'];seed=b['task']['seed']
    out.mkdir(parents=True,exist_ok=False);dump(out/'bundle.json',b)
    result=dict(status='HOST_ERROR',source_sha=source,model_calls=0,freeze=False,
        qualification='one MuJoCo DEV attempt, not real hardware or confirmation cohort',loadavg_start=list(os.getloadavg()))
    started=monotonic();backend=controller=explorer=None;last_snapshot=None;loss_saved=False
    try:
        backend=backend_factory(b,out,seed=seed)
        backend.reset(5.)
        start=backend.now;result['start_sim_s']=start;backend.set_deadline(start+cap)
        for action in arm(SEARCH):backend.issue('r3',action)
        factory=make_mapper if mapper_factory is None else mapper_factory
        explorer=factory('r3',start,SEARCH,active_mapping='frontier_rbpf_v1',active_loop='information_gain_v1',
            seed=seed,active_recovery='nav2_frontier_v1',navigation_map='public_ros_v8',motion_model='s2_pulse_v122_rotL_v1')
        base.install_profile(explorer.memory.self_map,profile='egomap27_wide')
        controller=attach(explorer,map_utility=OPTION,seed=seed) if controller_factory is None else controller_factory(explorer,seed=seed)
        for tick in range(round(cap*5)+1):
            t=backend.now;obs,rgb=backend.capture()['r3']
            if tick>=10:
                detection=observe(rgb,SEARCH,body_settling=.7)
                frame_hash=base.old.sha(out/f'robots/r3/rgb/{tick:05d}.jpg')
                command,trace=controller.receive(robot_id='r3',t=t,frame_id=obs['frame_id'],rgb=rgb,servo=SEARCH,
                    observation=detection,frame_sha256=frame_hash)
                backend._append('own-controller.jsonl',trace)
                backend._append('own-contacts.jsonl',dict(t=t,frame_id=obs['frame_id'],**detection))
                if controller.stage=='explore':
                    g=explorer.memory.self_map
                    backend._append('frontend-covariances.jsonl',dict(t=t,frame_id=obs['frame_id'],
                        pose=list(g.odom.pose),covariance=g.odom.covariance.tolist()))
                    revision=(g.revision,g.best,g.resamples)
                    if revision!=last_snapshot:
                        backend._append('online-maps.jsonl',dict(t=t,frame_id=obs['frame_id'],view='online_frontend',grid=g.export(),ledger=g.ledger))
                        last_snapshot=revision
                elif not loss_saved:
                    dump(out/'snapshot.json',controller.snapshot)
                    dump(out/'prefix-measurements.json',controller.measurements)
                    dump(out/'prefix-poses.json',controller.poses)
                    loss_saved=True
                if tick<round(cap*5) or controller.declared:
                    backend.issue('r3',{k:v for k,v in command.items() if k!='t'})
                    controller.command(command)
            backend.eval_sample()
            if tick%25==0:
                print(progress_label,'SIM',round(t-start,2),'stage',controller.stage,'frames',tick+1,flush=True)
                dump(out/'progress.json',dict(sim_s=t-start,frames=tick+1,stage=controller.stage))
            if controller.declared:break
            if monotonic()-started>3600:raise TimeoutError('HOST_BUDGET_60_MINUTES')
            if tick<round(cap*5):backend.advance_to(round(start+(tick+1)*.2,9))
        result.update(status='RECORDED',frames=tick+1,total_sim_s=backend.now,stage=controller.stage,
            declared_goal=controller.declared,loss_t=controller.loss_t)
    except Exception as e:
        result.update(status='PHYSICAL_FAILURE' if type(e).__name__=='PhysicalStop' else 'HOST_ERROR',
            frames=backend.frame if backend else 0,total_sim_s=backend.now if backend else None,
            failure=dict(type=type(e).__name__,message=str(e)),enospc=getattr(e,'errno',None)==28)
        import traceback
        traceback.print_exc()
    finally:
        signal.setitimer(signal.ITIMER_REAL,0)
        if backend is not None:backend.close()
        if controller is not None:
            dump(out/'own-inputs.json',controller.inputs)
            dump(out/'utility-events.json',controller.events)
            dump(out/'remembered-goal.json',controller.goal)
            dump(out/'tempering-audit.json',controller.pf.tempering_audit if controller.pf else [])
            dump(out/'return-navigation.json',controller.navigator.events if controller.navigator else [])
        if explorer is not None:
            dump(out/'frontend-grid.json',explorer.memory.self_map.export())
            dump(out/'frontend-ledger.json',explorer.memory.self_map.ledger)
            dump(out/'frontend-poses.json',explorer.poses)
            dump(out/'decisions.json',explorer.memory.self_map.decisions)
            dump(out/'navigation.json',explorer.navigator.events)
            dump(out/'active-events.json',explorer.events)
            dump(out/'graphs.json',explorer.graphs)
        result.update(wall_s=monotonic()-started,loadavg_end=list(os.getloadavg()))
        dump(out/'result.json',result)
        dump(out/'artifacts.sha256.json',{str(p.relative_to(out)):base.old.sha(p) for p in sorted(out.rglob('*')) if p.is_file() and p.name!='artifacts.sha256.json'})
    return result


def main():
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('--output',type=Path,required=True);p.add_argument('--expected-source-sha',required=True)
    p.add_argument('--execute',action='store_true');args=p.parse_args()
    receipts=base.verify_source(args.expected_source_sha)
    assert args.output.resolve()==RAW/'new-seed' and not args.output.exists()
    frozen=json.loads((base.EXP/'freeze.json').read_text())
    admission=json.loads((ROOT/'experiments/2026-10-08-own-map-closed-loop/detector-off-admission.json').read_text())
    for p,h in frozen['hashes'].items():
        if p in admission['files']:
            a=admission['files'][p]
            assert a['original_sha256']==h==base.old.sha(ROOT/a['original_fixture'])
            assert base.old.sha(ROOT/p)==a['current_sha256']
        else:assert base.old.sha(ROOT/p)==h,p
    receipts['default_off_detector_admission']=admission
    receipts['egomap34_estimator_hashes']=frozen['hashes']
    nav=json.loads((ROOT/'experiments/2026-10-07-active-wall-map/navigation-source.json').read_text())
    assert all(base.old.sha(ROOT/p)==h for p,h in nav['files'].items())
    if not args.execute:return 0
    from scripts.agent_lock import DEFAULT_ROOT,status,acquire as take,release
    assert status(DEFAULT_ROOT) is None,'physics lock occupied'
    lock=take(DEFAULT_ROOT,owner='codex',branch='claude/ego-wall-map',purpose='egomap43 own B closed-loop DEV seed43001',pid=os.getpid(),expected_minutes=60)
    try:
        def timeout(*_):raise TimeoutError('HOST_BUDGET_60_MINUTES')
        signal.signal(signal.SIGALRM,timeout);signal.setitimer(signal.ITIMER_REAL,3600)
        from sim.own_map_closed_loop import PhysicsBackend
        result=acquire(args.output,args.expected_source_sha,PhysicsBackend)
        dump(args.output/'source-admission.json',receipts);dump(args.output/'lock.json',lock)
    finally:release(DEFAULT_ROOT,owner='codex')
    print(json.dumps(result,ensure_ascii=False),flush=True)
    return 0 if result['status']=='RECORDED' else 1


if __name__=='__main__':raise SystemExit(main())
