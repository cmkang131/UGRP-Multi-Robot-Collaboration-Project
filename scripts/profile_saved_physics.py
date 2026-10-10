"""Bounded native replay of saved issued commands; no controller/model calls."""
from __future__ import annotations
import argparse,cProfile,json,os,subprocess,time,pstats
from pathlib import Path
from scripts.profile_controller_replay import Timers,verify_inputs,rows,sha,write,ROOT,acquire_slot
from scripts import benchmark_v7_speed as benchmark

def selection(raw,kind,seconds):
    robots=('r1','r2','r3') if kind=='s3' else ('r3',)
    frames={r:rows(raw/f'robots/{r}/frames.jsonl') for r in robots}
    start=frames[robots[0]][0]['sim_time']
    selected=[x['sim_time'] for x in frames[robots[0]] if x['sim_time']<=start+seconds+1e-8]
    assert len(selected)>1
    for r in robots:assert [x['sim_time'] for x in frames[r][:len(selected)]]==selected
    schedule={}
    for r in robots:
        for row in rows(raw/f'robots/{r}/commands.jsonl'):
            if row['kind']!='initial_servo_command' and row['t']<=selected[-1]+1e-8:
                t=round(row['t'],9);assert t in selected
                schedule.setdefault(t,[]).append((r,{k:v for k,v in row.items() if k!='t'}))
    return robots,frames,selected,schedule

def worker(a):
    # Fresh interpreter, immutable original backend and committed common overlay.
    benchmark.OVERLAY=('harness.controller_exact_speedups',)+benchmark.OVERLAY
    benchmark.load_adapter(a.adapter)
    import numpy as np,mujoco
    robots,reference,times,schedule=selection(a.raw,a.kind,a.sim_seconds)
    input_receipt=verify_inputs(a.raw,robots)
    bundle=json.loads((a.raw/'bundle.json').read_text())
    os.environ['UGRP_CONTROLLER_EXACT_SPEEDUPS']='exact-v1'
    seed=bundle['seed'] if a.kind=='s3' else bundle['task']['seed']
    if a.kind=='s3':from sim.s3_motion_ports import PhysicsBackend
    else:from sim.goal_route_assets import PhysicsBackend
    a.output.mkdir(parents=True,exist_ok=False)
    timer=Timers();backend=None;profiler=cProfile.Profile() if a.profile else None
    load=os.getloadavg();started=time.perf_counter();failure=None;comparison=[]
    try:
        with timer.span('setup_proof'):
            backend=PhysicsBackend(bundle,a.output,seed=seed);backend.reset(5.)
            assert backend.now==times[0]
            scene=benchmark.scene_receipt(a.output/'scene.xml',a.raw/'scene.xml')
            backend.set_deadline(times[-1])
        backend.world._physics_step_for=timer.wrapper(backend.world._physics_step_for,'physics')
        backend.world.render_rgb=timer.wrapper(backend.world.render_rgb,'render')
        backend._append=timer.wrapper(backend._append,'record_io')
        if profiler:profiler.enable()
        loop_start=time.perf_counter()
        for i,t in enumerate(times):
            with timer.span('controller_other'):
                backend.advance_to(t)
                if a.kind=='egomap' and i==0:
                    for r,command in schedule.get(t,[]):backend.issue(r,command)
                if a.kind=='s3':backend.eval_sample()
            with timer.span('record_io'):batch=backend.capture()
            with timer.span('controller_other'):
                if a.kind=='s3' or i:
                    for r,command in schedule.get(t,[]):backend.issue(r,command)
                if a.kind=='egomap':backend.eval_sample()
            for r in robots:
                obs,_=batch[r]
                comparison.append(dict(robot=r,t=t,frame_id=obs['frame_id'],
                    sha256=obs['sha256'],reference_sha256=reference[r][i]['sha256'],
                    equal=obs['sha256']==reference[r][i]['sha256']))
        loop_wall=time.perf_counter()-loop_start
        if profiler:profiler.disable()
        spec=mujoco.mjtState.mjSTATE_INTEGRATION
        state=np.empty(mujoco.mj_stateSize(backend.world.model,spec))
        mujoco.mj_getState(backend.world.model,backend.world.data,state,spec)
        import hashlib
        write(a.output/'state.json',dict(state_spec=int(spec),sha256=hashlib.sha256(state.tobytes()).hexdigest(),
            time=backend.now,drive_inputs={r:hashlib.sha256(v.tobytes()).hexdigest()
                for r,v in backend.world.drive_input_state.items()}))
        write(a.output/'scene-proof.json',scene)
    except Exception as exc:
        failure=dict(type=type(exc).__name__,message=str(exc));loop_wall=None
        import traceback;traceback.print_exc()
    finally:
        if profiler:
            profiler.disable();profiler.dump_stats(a.output/'profile.pstats')
            with (a.output/'profile.txt').open('w') as stream:
                pstats.Stats(profiler,stream=stream).sort_stats('cumulative').print_stats(60)
        if backend:backend.close()
        write(a.output/'frame-proof.json',comparison)
        sim=times[-1]-times[0]
        write(a.output/'result.json',dict(kind=a.kind,scope='native saved-command cost sample; controller/model0',
            start=times[0],end=times[-1],sim_s=sim,frames=len(times),available_frames=len(reference[robots[0]]),
            wall_s=loop_wall,wall_per_sim=None if loop_wall is None else loop_wall/sim,
            total_including_setup_s=time.perf_counter()-started,timers=timer.snapshot(),failure=failure,
            rgb_identical=bool(comparison) and all(x['equal'] for x in comparison),
            compared_rgb=len(comparison),expected_rgb=len(times)*len(robots),model_calls=0,controller_calls=0,
            input_sha256=input_receipt,source_sha=bundle['source_sha'],profile=a.profile,
            loadavg_start=load,loadavg_end=os.getloadavg(),nice=os.getpriority(os.PRIO_PROCESS,0)))
    return failure is None and len(comparison)==len(times)*len(robots) and all(x['equal'] for x in comparison)

def main():
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('--kind',choices=('s3','egomap'),required=True)
    for key in ('raw','adapter','output'):p.add_argument('--'+key,type=Path,required=True)
    p.add_argument('--expected-source-sha',required=True);p.add_argument('--sim-seconds',type=float,default=30.)
    p.add_argument('--profile',action='store_true');p.add_argument('--execute',action='store_true')
    p.add_argument('--lock-owner-pid',type=int)
    a=p.parse_args();assert 0<a.sim_seconds<=30.
    if not a.execute:print(json.dumps(dict(execution_started=False,physics_runs=0)));return
    assert subprocess.check_output(['git','rev-parse','HEAD'],cwd=ROOT,text=True).strip()==a.expected_source_sha
    assert not subprocess.check_output(['git','status','--porcelain'],cwd=ROOT,text=True).strip()
    assert os.getpriority(os.PRIO_PROCESS,0)==0
    from scripts import agent_lock
    held,owned=acquire_slot(a.expected_source_sha,'speedctrl bounded saved-command native cost sample',
                           lock_owner_pid=a.lock_owner_pid)
    try:complete=worker(a)
    finally:
        released=agent_lock.release(agent_lock.DEFAULT_ROOT,owner='codex') if owned else None
        if a.output.exists():write(a.output/'lock.json',dict(acquired=held,released=released,borrowed=not owned))
    if not complete:raise RuntimeError('NATIVE_REPLAY_INCOMPLETE_OR_RGB_DIFF; evidence preserved')

if __name__=='__main__':main()
