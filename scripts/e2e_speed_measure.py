"""External bounded measurement: never changes the authored execution bundle."""
import cProfile
import hashlib
import json
from pathlib import Path
import pstats
import time


def profile_rows(stats, sim_s):
    rows=[]
    for (filename,line,function),(primitive,calls,self_s,cumulative_s,_) in stats.stats.items():
        rows.append(dict(file=filename,line=line,function=function,calls=calls,
                         self_s=self_s,cumulative_s=cumulative_s,
                         cumulative_wall_per_sim=cumulative_s/sim_s))
    return sorted(rows,key=lambda x:x['cumulative_s'],reverse=True)[:20]


def rbpf_digest(robot):
    """Raw float bytes, RNG, all particle grids/history and revision after receive."""
    grid=robot.goal.explorer.memory.self_map
    h=hashlib.sha256()
    for name in ('poses','pending_cov','weights','log_weights'):
        a=getattr(grid,name)
        h.update(name.encode());h.update(a.dtype.str.encode());h.update(str(a.shape).encode());h.update(a.tobytes())
    value=dict(rng=grid.rng.bit_generator.state,best=grid.best,resamples=grid.resamples,
               revision=grid.revision,histories=grid.histories,
               maps=[sorted(g.cells.items()) for g in grid.maps])
    h.update(json.dumps(value,sort_keys=True,separators=(',',':')).encode())
    return h.hexdigest()


def measured_run(run,b,out,receipt,limit,profile):
    if not 60<=limit<=90:raise ValueError('MEASUREMENT_REQUIRES_60_TO_90_SIM_SECONDS')
    import mujoco
    from sim.e2e_ownmap_live import PhysicsBackend
    from harness.e2e_live_mapping import Robot
    from harness.e2e_result_writer import write
    root=out.parent
    profiler=cProfile.Profile() if profile else None
    timers=[];states=[];backend_ref=[];origin=[None]
    original_receive=Robot.receive
    hash_seconds=[0.]
    def receive(self,*args,**kwargs):
        result=original_receive(self,*args,**kwargs)
        start=time.perf_counter()
        states.append(dict(robot=self.robot_id,frame=self.frame.index,t=self.now,sha256=rbpf_digest(self)))
        hash_seconds[0]+=time.perf_counter()-start
        return result
    class MeasuredBackend(PhysicsBackend):
        def reset(self,cap):
            result=super().reset(cap);origin[0]=self.now;backend_ref.append(self)
            return result
        def advance_to(self,at):
            result=super().advance_to(at)
            if origin[0] is not None and self.now-origin[0]>=limit-1e-8:
                raise KeyboardInterrupt('MEASUREMENT_SIM_LIMIT')
            return result
        def close(self):
            if profile:
                for i,timer in enumerate(self.world.data.timer):
                    timers.append(dict(timer=mujoco.mjtTimer(i).name,duration_s=timer.duration,
                                       calls=timer.number,wall_per_sim=timer.duration/limit))
            return super().close()
    Robot.receive=receive
    previous=mujoco.get_mjcb_time()
    if profile:mujoco.set_mjcb_time(time.perf_counter)
    wall=time.perf_counter();cpu=time.process_time()
    try:
        if profiler:profiler.enable()
        result=run(b,out,receipt,backend_factory=MeasuredBackend)
    finally:
        if profiler:profiler.disable()
        wall=time.perf_counter()-wall;cpu=time.process_time()-cpu
        Robot.receive=original_receive
        if profile:mujoco.set_mjcb_time(previous)
    sim=result.get('sim_s',0.)
    record=dict(sim_s=sim,wall_s=wall,cpu_s=cpu,wall_per_sim=wall/sim if sim else None,
                cpu_per_sim=cpu/sim if sim else None,rbpf_hash_wall_s=hash_seconds[0],
                profiling=profile,includes_setup_and_finalization=True,mujoco_timers=timers,
                expected_stop=result.get('failure')=='MEASUREMENT_SIM_LIMIT',
                cprofile_top20=profile_rows(pstats.Stats(profiler),sim) if profiler and sim else [])
    if profiler:profiler.dump_stats(str(root/'cprofile.pstats'))
    write(root/'measurement.json',record)
    write(root/'rbpf-sha256.json',states)
    return result
