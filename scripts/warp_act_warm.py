"""Finite qualified-teacher warm benchmark; replicas are load, never gate N.

SIM0..3 warms the exact controller/physics/native RGB path. SIM3..6 is timed.
3s is the existing Score lift-hold duration, used only as a bounded measurement
window (30 control quanta), not a new success or performance threshold.
"""
import argparse
import hashlib
import json
from pathlib import Path
import platform
import subprocess
import sys
import time
import traceback
import urllib.request

QUALIFIED = 'f0db6b1abb842ea65b71c433738210254f300a7c'
TEACHER = '6f057f7e97c1a3aec9e8c398b8d9068e27b25df8'


def identity():
    def get(key):
        req = urllib.request.Request('http://metadata.google.internal/computeMetadata/v1/'+key,
                                     headers={'Metadata-Flavor':'Google'})
        return urllib.request.urlopen(req, timeout=5).read().decode().split('/')[-1]
    host = dict(project_id=get('project/project-id'), instance=get('instance/name'),
                machine_type=get('instance/machine-type'), zone=get('instance/zone'))
    if host['project_id'] != 'ugrp-sim-b-1014': raise ValueError('gcp2 project only')
    return host


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('--enabled', action='store_true')
    p.add_argument('--backend', choices=['mjwarp_batch_v1','c_pilot_v1'], required=True)
    p.add_argument('--nworld', type=int, default=1)
    for key in ('qualified-source','teacher-source','plan','compiled-reference','compiled-geometry','out'):
        p.add_argument('--'+key, type=Path, required=True)
    p.add_argument('--episode', type=int, default=4)
    p.add_argument('--hourly-usd-estimate', type=float, required=True)
    p.add_argument('--barrier', type=Path, help='C16 supervisor READY/GO/DONE/FINALIZE directory')
    a = p.parse_args()
    if not a.enabled or platform.system() != 'Linux': p.error('default OFF; Linux gcp2 only, no Mac physics/render')
    host = identity()
    gpu = a.backend == 'mjwarp_batch_v1'
    if gpu and (host['instance'] not in ('ugrp-act-l4-gcp2','ugrp-act-l4-gcp2b') or host['machine_type'] != 'g2-standard-8'):
        p.error('explicit main/b L4 g2-standard-8 only')
    if not gpu and (host['instance'] != 'ugrp-sim-gcp2' or a.nworld != 1): p.error('C worker is N1 on gcp2 CPU VM')
    if not 1 <= a.nworld <= 256 or a.hourly_usd_estimate <= 0: p.error('finite batch and positive inherited price required')
    for source, sha in ((a.qualified_source,QUALIFIED),(a.teacher_source,TEACHER)):
        if subprocess.check_output(['git','-C',str(source),'rev-parse','HEAD'],text=True).strip() != sha:
            p.error('exact frozen source required')
        if subprocess.check_output(['git','-C',str(source),'status','--porcelain','--untracked-files=no']): p.error('clean source required')
    sys.path.insert(0,str(a.qualified_source/'scripts'));sys.path.insert(0,str(a.teacher_source))
    import sim
    sim.__path__.append(str(a.qualified_source/'sim'))
    import numpy as np
    import mujoco
    if not gpu and mujoco.__version__ != '3.12.0': p.error('C comparison requires exact3.12.0')
    from warp_act_episode import episode
    from warp_act_backend import WarpTransport,CTransport
    a.out.mkdir(parents=True,exist_ok=False)
    def write(name,value): (a.out/name).write_text(json.dumps(value,indent=2,allow_nan=False)+'\n')
    plan=json.loads(a.plan.read_text())['episodes'][a.episode]
    hooks=(WarpTransport if gpu else CTransport)(host,QUALIFIED,a.backend,a.out,native_sleep_policy_compat_v1=True)
    hooks.scene_v5_v1=True;hooks.numpy_teacher_v1=gpu;hooks.batch_sleep_v1=gpu
    generators=[];contexts=[];active=np.ones(a.nworld,bool);native={}
    report=dict(**{'class':'dev'},status='running',backend=a.backend,host=host,nworld=a.nworld,
        source_sha=subprocess.check_output(['git','-C',str(Path(__file__).resolve().parents[1]),'rev-parse','HEAD'],text=True).strip(),
        mujoco=mujoco.__version__,pr=534,branch='claude/warp-act',
        controller_source=QUALIFIED,teacher_source=TEACHER,seed=plan['seed'],replicas_are_load=True,
        independent_gate_episodes=0,scenario=plan['scenario_id'],warmup_sim_s=3.,timed_sim_range=[3.,6.],
        camera_native='640x480/10Hz original K,D/FOV/mount',training_rgb=False,weld='off',
        hourly_usd_estimate=a.hourly_usd_estimate,price_basis='inherited estimate; not a live price or actual bill',
        reproduce=sys.argv)
    setup_start=time.perf_counter()
    try:
        for i in range(a.nworld):
            gen=episode(plan,a.out/f'world-{i:03d}',hooks=hooks,world_index=i,execution_host='gcp2',
                profile='solo_visible_only_v1',hidden=True,look=True,cap_s=6.,
                teacher_stability='align_relook_v1',reach_mode='pad_window_v2',
                rgb_lift_mode='solo_lift_lookback_v1',solo_lift_lookback_margin_v1=True,
                solo_truth_free_lookaround_v1=True)
            generators.append(gen);contexts.append(next(gen))
        if gpu:
            hooks.initialize(contexts,compiled_reference=a.compiled_reference,compiled_geometry=a.compiled_geometry)
            report.update(camera=hooks.camera,solver_numerics=hooks.solver_numerics,capacities=hooks.capacities)
            def forbidden(*args,**kwargs): raise RuntimeError('C scalar ray/kinematics forbidden in warm Warp rollout')
            for name in ('mj_ray','mj_kinematics','mj_camlight'):
                native[name]=getattr(mujoco,name);setattr(mujoco,name,forbidden)
        def tick():
            for gen in generators:
                if next(gen)['kind'] != 'step': raise RuntimeError('unexpected teacher barrier')
            hooks.step(contexts,active)
        for _ in range(30): tick()
        report['setup_and_warmup_wall_s']=time.perf_counter()-setup_start
        if a.barrier:
            a.barrier.mkdir(exist_ok=True)
            (a.barrier/(a.out.name+'.READY.json')).write_text(json.dumps(dict(pid=__import__('os').getpid(),host=host))+'\n')
            while not (a.barrier/'GO.json').exists(): time.sleep(.05)  # administrative barrier, never a planning budget
        if gpu: hooks.wp.synchronize()
        print('WARM_MEASURE_BEGIN',flush=True)
        start=time.perf_counter();origin=time.monotonic();before=dict(hooks.seconds);intervals=[]
        for _ in range(30):
            t=time.perf_counter();tick();intervals.append(time.perf_counter()-t)
        if gpu: hooks.wp.synchronize()
        end=time.perf_counter();finish=time.monotonic()
        print('WARM_MEASURE_END',flush=True)
        report.update(timed_wall_s=end-start,timed_monotonic_start=origin,timed_monotonic_end=finish,
            aggregate_timed_sim_s=a.nworld*3.,sim_s_per_wall_s=a.nworld*3./(end-start),
            sim_s_per_usd=a.nworld*3./(end-start)*3600/a.hourly_usd_estimate,
            interval_wall_s=intervals,interval_median=float(np.median(intervals)),interval_p90=float(np.percentile(intervals,90)),
            first10_median=float(np.median(intervals[:10])),last10_median=float(np.median(intervals[-10:])),
            timed_components={k:v-before.get(k,0) for k,v in hooks.seconds.items()})
        if a.barrier:
            (a.barrier/(a.out.name+'.DONE.json')).write_text(json.dumps(report,indent=2)+'\n')
            while not (a.barrier/'FINALIZE.json').exists(): time.sleep(.05)
        rows=[]
        for gen in generators:
            try: next(gen)
            except StopIteration as done: rows.append(done.value)
            else: raise RuntimeError('benchmark did not stop at its fixed6SIM cap')
        report.update(status='complete',world_results=[{k:r[k] for k in ('status','cap_end','physical_success','input_audit')} for r in rows],
                      cap_end=sum(r['cap_end'] for r in rows),HOST_ERROR=0)
    except BaseException as error:
        report.update(status='HOST_ERROR',HOST_ERROR=1,error=repr(error),traceback=traceback.format_exc());raise
    finally:
        for name,value in native.items():setattr(mujoco,name,value)
        for gen in generators: gen.close()
        hooks.save_states();hooks.close()
        report['raw_sha256']={str(x.relative_to(a.out)):hashlib.sha256(x.read_bytes()).hexdigest() for x in a.out.rglob('*') if x.is_file()}
        write('summary.json',report)


if __name__=='__main__':main()
