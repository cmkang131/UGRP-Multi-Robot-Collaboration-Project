"""egomap56 frozen P1 cohort; one locked own-RGB DEV slot per invocation."""
from pathlib import Path
import argparse,json,math,os,signal,subprocess
from time import monotonic
from scripts import run_active_wall_rotleft as base
from scripts.run_own_map_return_repeat import actor
from harness.goal_route_continuous import attach,OPTION
from harness.grid_acceleration import install

ROOT=base.ROOT
EXP=ROOT/'experiments/2026-10-09-goal-route-continuous'
RAW=Path('/Users/changmin/projects/ugrp/outputs/goal-route-continuous-v1')
SEEDS=tuple(range(55001,55010))


def bundle(seed,source):
    if seed not in SEEDS:raise ValueError('PREREGISTERED_SEED_REQUIRED')
    b=base.frozen_bundle('new-seed',source)
    b.update(execution_bundle_id=f'egomap56-goal-route-{seed}-v1',case=f'seed{seed}',
        map_id='zone_wide_door_geometry_v3',check='goal-route-continuous',case_cap_s=810.,
        preregistration='acf9cc7e',admission='user_authorized_P1_9_DEV; no forced loss; fixed gates')
    b['task']['seed']=seed
    b['condition']='T1' if seed<55004 else 'T2'
    if seed>=55004:b['spawn']=[-.898,[-2.25,-.85,.55][(seed-55004)//2],0.]
    b['options'].update(goal_route=OPTION,heading_mode='path_tangent_v1',pitch_calibration='off',
        route_hygiene='off',scan_accumulation='off',place_gate='off',
        navigation_start='navfn_recovery_v1',frontier_observation='yamauchi_cycle_v1',
        map_acceleration='scalar_rays_v1',graph_acceleration='match_cache_v1')
    b['sensors']={'ultrasonic_front':'off'}
    b['schedule']=dict(leg_cap_s=270.,maximum_legs=3,host_cap_s=3600.,forced_loss=False)
    return b


def controller(explorer):return install(attach(explorer,goal_route=OPTION),map_acceleration='scalar_rays_v1')


def run(out,source,seed,backend_factory):
    from harness.active_camera import SEARCH
    from harness.active_wall_vision import observe
    from scripts.run_wall_servo_stiffness import arm
    b=bundle(seed,source);out.mkdir(parents=True,exist_ok=False);base.dump(out/'bundle.json',b)
    result=dict(status='HOST_ERROR',source_sha=source,seed=seed,condition=b['condition'],
        model_calls=0,freeze=False,physical_hardware=False,loadavg_start=list(os.getloadavg()))
    backend=explorer=c=None;started=monotonic();last_snapshot=None
    try:
        backend=backend_factory(b,out,seed=seed);backend.reset(5.)
        start=backend.now;result['start_sim_s']=start;backend.set_deadline(start+b['case_cap_s'])
        for action in arm(SEARCH):backend.issue('r3',action)
        explorer=actor('r3',start,SEARCH,active_mapping='frontier_rbpf_v1',active_loop='information_gain_v1',
            seed=seed,active_recovery='nav2_frontier_v1',navigation_map='public_ros_v8',motion_model='s2_pulse_v122_rotL_v1')
        base.install_profile(explorer.memory.self_map,profile='egomap27_wide');c=controller(explorer)
        # Map identity only is written to output, never passed to policy.
        base.dump(out/'route-map-header.json',dict(robot_id='r3',coordinate_frame='r3/own_odom',
            map_id=b['map_id'],static_map_sha256=backend.scene.config['static_map_sha256'],
            source_sha=source,camera_pose='SEARCH/servo_fk_v1',pitch_calibration='off'))
        for tick in range(round(b['case_cap_s']*5)+1):
            t=backend.now;obs,rgb=backend.capture()['r3']
            if tick>=10:
                detection=observe(rgb,SEARCH,body_settling=.7)
                frame_hash=base.old.sha(out/f'robots/r3/rgb/{tick:05d}.jpg')
                cmd,trace=c.receive(robot_id='r3',t=t,frame_id=obs['frame_id'],rgb=rgb,servo=SEARCH,
                    observation=detection,frame_sha256=frame_hash)
                backend._append('own-controller.jsonl',trace)
                backend._append('own-contacts.jsonl',dict(t=t,frame_id=obs['frame_id'],**detection))
                g=explorer.memory.self_map
                backend._append('frontend-covariances.jsonl',dict(t=t,frame_id=obs['frame_id'],pose=list(g.odom.pose),covariance=g.odom.covariance.tolist()))
                revision=(g.revision,g.best,g.resamples)
                if revision!=last_snapshot:
                    backend._append('online-maps.jsonl',dict(t=t,frame_id=obs['frame_id'],view='online_frontend',grid=g.export(),ledger=g.ledger))
                    last_snapshot=revision
                backend.issue('r3',{k:v for k,v in cmd.items() if k!='t'});c.command(cmd)
            backend.eval_sample()
            if tick%25==0:
                progress=dict(sim_s=t-start,frames=tick+1,stage=c.stage,reached=list(c.reached),nodes=len(c.graph.nodes))
                print('egomap56',seed,json.dumps(progress),flush=True);base.dump(out/'progress.json',progress)
            if c.done:break
            if monotonic()-started>3600:raise TimeoutError('HOST_BUDGET_60_MINUTES')
            backend.advance_to(round(start+(tick+1)*.2,9))
        result.update(status='RECORDED',frames=tick+1,total_sim_s=backend.now,stage=c.stage,
            reached=list(c.reached),declared_B='B' in c.reached,declared_return=c.declared)
    except Exception as e:
        result.update(status='PHYSICAL_FAILURE' if type(e).__name__=='PhysicalStop' else 'HOST_ERROR',
            total_sim_s=backend.now if backend else None,frames=backend.frame if backend else 0,
            failure=dict(type=type(e).__name__,message=str(e)),enospc=getattr(e,'errno',None)==28)
        import traceback
        traceback.print_exc()
    finally:
        signal.setitimer(signal.ITIMER_REAL,0)
        if backend is not None:backend.close()
        if c is not None:
            base.dump(out/'route-map.json',c.snapshot());base.dump(out/'utility-events.json',c.events)
            base.dump(out/'own-inputs.json',c.inputs);base.dump(out/'return-navigation.json',c.navigator.events)
        if explorer is not None:
            g=explorer.memory.self_map
            for name,value in [('frontend-grid',g.export()),('frontend-ledger',g.ledger),('frontend-poses',explorer.poses),
                ('decisions',g.decisions),('navigation',explorer.navigator.events),('active-events',explorer.events),('graphs',explorer.graphs)]:
                base.dump(out/(name+'.json'),value)
        result.update(wall_s=monotonic()-started,loadavg_end=list(os.getloadavg()))
        base.dump(out/'result.json',result)
        base.dump(out/'artifacts.sha256.json',{str(p.relative_to(out)):base.old.sha(p) for p in sorted(out.rglob('*')) if p.is_file() and p.name!='artifacts.sha256.json'})
    return result


def preflight(source):
    receipts=base.verify_source(source)
    frozen=json.loads((EXP/'freeze.json').read_text())
    assert all(base.old.sha(ROOT/p)==h for p,h in frozen['files'].items()),'FROZEN_SOURCE_CHANGED'
    # Exact queue evidence is recorded once before the first physics slot.
    return dict(source=receipts,freeze=frozen)


def main():
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('--seed',type=int,choices=SEEDS,required=True);p.add_argument('--expected-source-sha',required=True)
    p.add_argument('--output',type=Path,required=True);p.add_argument('--execute',action='store_true')
    a=p.parse_args();receipt=preflight(a.expected_source_sha)
    assert a.output.resolve()==RAW/f'seed{a.seed}' and not a.output.exists()
    if not a.execute:return 0
    queue=json.loads((RAW/'queue-admission.json').read_text())
    assert queue['s3_retest_completed'] and queue['approved_ego_next']
    from scripts.agent_lock import DEFAULT_ROOT,status,acquire,release
    assert status(DEFAULT_ROOT) is None,'physics lock occupied'
    lock=acquire(DEFAULT_ROOT,owner='codex',branch='claude/ego-wall-map',purpose=f'egomap56 {a.seed} continuous goal route DEV',pid=os.getpid(),expected_minutes=60)
    try:
        def timeout(*_):raise TimeoutError('HOST_BUDGET_60_MINUTES')
        signal.signal(signal.SIGALRM,timeout);signal.setitimer(signal.ITIMER_REAL,3600)
        from sim.goal_route_continuous import PhysicsBackend
        result=run(a.output,a.expected_source_sha,a.seed,PhysicsBackend)
        base.dump(a.output/'source-admission.json',receipt);base.dump(a.output/'lock.json',lock)
        base.dump(a.output/'queue-admission.json',queue)
    finally:
        signal.setitimer(signal.ITIMER_REAL,0);release(DEFAULT_ROOT,owner='codex')
    print(json.dumps(result,ensure_ascii=False),flush=True)
    return 0 if result['status']=='RECORDED' else 1

if __name__=='__main__':raise SystemExit(main())
