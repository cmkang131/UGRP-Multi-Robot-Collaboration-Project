"""Opt-in gcp2 lockstep ACT solo teacher pilot; never launches on macOS.

Use a clean frozen teacher checkout as --teacher-source. Existing C entrypoints
are untouched. This first transport deliberately rejects training recording.
"""
import argparse
from collections import Counter
import hashlib
import json
from pathlib import Path
import platform
import subprocess
import sys
import time
import traceback

ROOT=Path(__file__).resolve().parents[1]
# Support the standard manager's `python -m scripts...` entry as well as direct CLI.
if str(ROOT/'scripts') not in sys.path:
    sys.path.insert(0,str(ROOT/'scripts'))
TEACHER_SHA='6f057f7e97c1a3aec9e8c398b8d9068e27b25df8'


def write(path,value):
    path.parent.mkdir(parents=True,exist_ok=True)
    path.write_text(json.dumps(value,indent=2,allow_nan=False)+'\n')


def parser():
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('--physics-backend',choices=['off','mjwarp_batch_v1','c_pilot_v1'],default='off')
    p.add_argument('--teacher-source',type=Path,required=True)
    p.add_argument('--plan',type=Path,required=True)
    p.add_argument('--episode',type=int,default=0)
    p.add_argument('--world-episodes',help='comma-separated per-world indices; default repeats --episode for throughput')
    p.add_argument('--nworld',type=int,choices=[1,16,64,256],default=1)
    p.add_argument('--cap-s',type=float,default=90.)
    p.add_argument('--out',type=Path,required=True)
    p.add_argument('--compiled-reference-v1',type=Path)
    p.add_argument('--compiled-geometry-312-v1',type=Path)
    p.add_argument('--per-world-model-references-v1',type=Path,help='default OFF: XMLsha→exact C312 assets; preserve batchable per-world model fields')
    p.add_argument('--native-sleep-policy-compat-v1',action='store_true',help='default OFF: explicit native sleep scene plus exact runtime policy adapter; separate cohort')
    p.add_argument('--float32-solver-default-v1',action='store_true',help='default OFF: retain upstream float32 tolerance clamp; unchanged task success criteria')
    p.add_argument('--reset-check-v1',action='store_true',help='diagnostic only: reset selected initial state; no teacher rollout or gate')
    p.add_argument('--export-compiled-only',action='store_true')
    p.add_argument('--vm-hourly-usd',type=float,required=True)
    return p



def interruption_outcome(out):
    marker=out/'SUPERVISOR_STOP.json'
    if not marker.exists():
        return dict(status='interrupted',resource_cap_end=False,
            reason='unmarked external interrupt; task success not inferred')
    stop=json.loads(marker.read_text())
    cap=stop.get('category')=='cap_end' or stop.get('reason')=='resource_cap4h'
    return dict(status='cap_end' if cap else 'supervisor_stop',resource_cap_end=cap,
        reason=stop.get('reason') or 'explicit supervisor marker without detail')


def main():
    p=parser();a=p.parse_args()
    if a.physics_backend=='off' or platform.system()!='Linux':
        p.error('explicit Linux gcp2 backend opt-in required; Mac physics/render forbidden')
    if not 0<a.cap_s<=90 or a.vm_hourly_usd<=0:
        p.error('finite <=90 SIM seconds and positive explicit price required')
    if a.physics_backend=='mjwarp_batch_v1' and (not a.compiled_reference_v1 or not a.compiled_geometry_312_v1):
        p.error('warp1 profile requires explicit same-XML compiled312 damping and geometry assets')
    if a.reset_check_v1 and (a.physics_backend!='mjwarp_batch_v1' or a.nworld<2):
        p.error('reset diagnostic requires a multi-world Warp batch')
    # Check real metadata before importing any simulator or executing source code.
    from simalt_host import gcp2_identity
    host=gcp2_identity()
    if a.physics_backend=='mjwarp_batch_v1' and host['instance']!='ugrp-act-l4-gcp2':
        p.error('existing gcp2 L4 required')
    if a.physics_backend=='c_pilot_v1' and a.nworld!=1:
        p.error('C pilot uses independent N1 processes for CPU concurrency')
    source=a.teacher_source.resolve()
    if subprocess.check_output(['git','-C',str(source),'rev-parse','HEAD'],text=True).strip()!=TEACHER_SHA:
        p.error('exact frozen ACT11 teacher checkout required')
    if subprocess.check_output(['git','-C',str(source),'status','--porcelain','--untracked-files=no']):
        p.error('clean frozen teacher source required')
    source_sha=subprocess.check_output(['git','-C',str(ROOT),'rev-parse','HEAD'],text=True).strip()
    if subprocess.check_output(['git','-C',str(ROOT),'status','--porcelain','--untracked-files=no']):
        p.error('committed backend source required')
    sys.path.insert(0,str(source))
    import numpy as np
    import mujoco
    from warp_act_episode import episode
    from warp_act_backend import CTransport,WarpTransport
    plans=json.loads(a.plan.read_text())
    indices=[int(x) for x in a.world_episodes.split(',')] if a.world_episodes else [a.episode]*a.nworld
    if len(indices)!=a.nworld or any(i<0 or i>=len(plans['episodes']) for i in indices):
        p.error('one valid episode index per world required')
    world_plans=[plans['episodes'][i] for i in indices]
    plan=world_plans[0]
    if any(p['kind'] not in ('cyan','red','green','yellow') or p['robot_id']!='r1' for p in world_plans):
        p.error('warp1 supports r1 solo boxes only')
    a.out.mkdir(parents=True,exist_ok=False)
    report=dict(status='running',physics_backend=a.physics_backend,source_sha=source_sha,
        teacher_sha=TEACHER_SHA,host=host,nworld=a.nworld,seed=plan['seed'],
        world_seeds=[p['seed'] for p in world_plans],unique_seeds=len({p['seed'] for p in world_plans}),cap_s=a.cap_s,
        training_rgb=False,training_recording_supported=False,student_evaluation_supported=False,
        native_sleep_policy_compat_v1=a.native_sleep_policy_compat_v1,
        float32_solver_default_v1=a.float32_solver_default_v1,
        teacher_vectorized=False,scope='transitional scalar frozen teacher on batched physics/commands/RGB',
        gate_eligible=False,scene_status='HOLD_SCENE',reproduce=sys.argv,
        plan_sha256=hashlib.sha256(a.plan.read_bytes()).hexdigest(),mujoco=mujoco.__version__,
        hourly_usd=a.vm_hourly_usd,price_basis='user/inherited VM estimate; actual billing not measured')
    write(a.out/'summary.json',report)
    hooks=(WarpTransport if a.physics_backend=='mjwarp_batch_v1' else CTransport)(host,source_sha,a.physics_backend,a.out,native_sleep_policy_compat_v1=a.native_sleep_policy_compat_v1)
    generators=[];contexts=[];active=np.ones(a.nworld,bool);reports={};ticks=np.zeros(a.nworld,int)
    start=time.perf_counter();loop_start=None
    try:
        for i in range(a.nworld):
            gen=episode(world_plans[i],a.out/f'world-{i:03d}',hooks=hooks,world_index=i,execution_host='gcp2',
                profile='solo_visible_only_v1',hidden=True,look=True,cap_s=a.cap_s,
                teacher_stability='align_relook_v1',reach_mode='pad_window_v2',
                rgb_lift_mode='solo_lift_lookback_v1',solo_lift_lookback_margin_v1=True,
                solo_truth_free_lookaround_v1=True)
            generators.append(gen)
            setup=next(gen)
            if setup['kind']!='setup':raise RuntimeError('missing initial setup barrier')
            contexts.append(setup)
        report['model_counts']={k:int(getattr(contexts[0]['world'].model,k)) for k in ('nq','nv','nu','nbody','ngeom')}
        if a.export_compiled_only:
            from simalt_compiled_compat import export_reference,export_geometry
            if mujoco.__version__!='3.12.0':raise ValueError('reference export needs C3.12')
            xml=a.out/'runtime-scene.xml';xml.write_text(contexts[0]['world'].scene_xml)
            export_reference(contexts[0]['world'].model,xml,mujoco.__version__,a.out/'compiled-312.json')
            export_geometry(contexts[0]['world'].model,xml,mujoco.__version__,a.out/'compiled-geometry312.npz')
            report.update(status='compiled_export_only',physics_steps=0)
            return
        if a.physics_backend=='mjwarp_batch_v1':
            hooks.initialize(contexts,compiled_reference=a.compiled_reference_v1,
                compiled_geometry=a.compiled_geometry_312_v1,
                per_world_model_references=json.loads(a.per_world_model_references_v1.read_text()) if a.per_world_model_references_v1 else None,
                float32_solver_default_v1=a.float32_solver_default_v1)
            report.update(camera=hooks.camera,compatibility=hooks.compat,capacities=hooks.capacities,model_batch=hooks.model_batch_audit,solver_numerics=hooks.solver_numerics,sleep_compact=hooks.sleep_audit)
            initial=hooks.initial_state_proof(contexts)
            write(a.out/'initial-world-state.json',initial)
            report['initial_world_state']=initial
            if a.reset_check_v1:
                if initial['expected_unique_qpos']<2:
                    raise ValueError('distinct starts required for the reset diagnostic')
                qpos=hooks.wd.qpos.numpy();qpos[0]=qpos[1]
                hooks.wp.copy(hooks.wd.qpos,hooks.wp.array(qpos,dtype=hooks.wd.qpos.dtype))
                mask=np.zeros(a.nworld,dtype=bool);mask[0]=True
                reset=hooks.reset_physics_worlds(mask)
                hooks.sync_render(contexts)
                after=hooks.initial_state_proof(contexts)
                write(a.out/'reset-proof.json',dict(reset=reset,initial=initial,after=after))
                report.update(status='reset_diagnostic_complete',reset_proof=reset,physics_rollout_steps=0)
                return
        report['setup_compile_s']=time.perf_counter()-start
        loop_start=time.perf_counter()
        while active.any():
            decision_start=time.perf_counter()
            for i in np.flatnonzero(active):
                try:
                    row=next(generators[i])
                    if row['kind']!='step':raise RuntimeError('missing physics barrier')
                    ticks[i]+=1
                except StopIteration as done:
                    reports[int(i)]=done.value
                    active[i]=False
            hooks.seconds['teacher_visibility_rgb_eval_logging']+=time.perf_counter()-decision_start
            if active.any():hooks.step(contexts,active)
            write(a.out/'progress.json',dict(ticks=ticks.tolist(),active=int(active.sum()),
                loop_wall_s=time.perf_counter()-loop_start,timing=dict(hooks.seconds)))
        report.update(status='complete',worlds=[dict(world=i,physical_success=r['physical_success'],
            lift_success=r['lift_success'],release_success=r['release_success'],cap_end=r['cap_end'],
            result=r['teacher']['command_result'],sim_s=r['sim_s'],input_audit=r['input_audit'])
            for i,r in sorted(reports.items())])
    except KeyboardInterrupt:
        report.update(interruption_outcome(a.out),interrupted=True,interrupted_worlds=int(active.sum()))
    except BaseException as error:
        report.update(status='HOST_ERROR',error_type=type(error).__name__,error=str(error),
            traceback=traceback.format_exc())
        raise
    finally:
        for gen in generators:gen.close()
        hooks.save_states()
        if hasattr(hooks,'solver_samples'):
            write(a.out/'solver-iterations.json',hooks.solver_samples)
        report['prototype_reset']={'unique_plans':len(hooks.prototypes),'cache_hits':hooks.prototype_hits,
            'scope':'exact-plan initial MjData copy; per-world native buffers/command arrays are independent'}
        hooks.close()
        wall=time.perf_counter()-start
        sim=sum(r.get('sim_s',0.) for r in reports.values())
        loop_wall=time.perf_counter()-loop_start if loop_start else None
        report.update(wall_s=wall,loop_wall_s=loop_wall,aggregate_completed_sim_s=sim,
            completed=len(reports),attempted=a.nworld,
            physical_success=sum(r.get('physical_success',False) for r in reports.values()),
            cap_end=sum(r.get('cap_end',False) for r in reports.values())+(int(active.sum()) if report.get('resource_cap_end') else 0),
            timing=dict(hooks.seconds),
            physical_batch_sim_s=getattr(hooks,'tick',0)*.1*a.nworld if a.physics_backend=='mjwarp_batch_v1' else sum(ticks)*.1,
            attempted_control_sim_s=float(sum(ticks))*.1,
            vm_cost_estimate_usd=wall*a.vm_hourly_usd/3600,
            sim_s_per_wall_s=sim/loop_wall if loop_wall else None,
            sim_s_per_usd=sim/(wall*a.vm_hourly_usd/3600),
            useful_completed_sim_s_per_usd=sum(r.get('sim_s',0.) for r in reports.values() if r.get('physical_success'))/(wall*a.vm_hourly_usd/3600))
        rejection=Counter(r.get('teacher',{}).get('command_result') or 'cap_end' for r in reports.values() if not r.get('physical_success'))
        if report['status']=='HOST_ERROR':rejection[report.get('error_type','HOST_ERROR')]+=1
        if report.get('interrupted'):rejection[report['status']]+=int(active.sum())
        write(a.out/'rejection_table.json',dict(funnel=[dict(gate='requested',passed=a.nworld,rejected=0),
            dict(gate='returned',passed=len(reports),rejected=a.nworld-len(reports)),
            dict(gate='physical_success',passed=report['physical_success'],rejected=len(reports)-report['physical_success'])],
            rejections=[dict(category=k,count=v,reason=k,blocking_object='not_attributed',minimum_gap_m=None,
                minimum_gap_status='no geometric cause attribution in transport pilot') for k,v in rejection.items()],
            raw=str(a.out),reproduce=sys.argv))
        report['rejection_table']=str(a.out/'rejection_table.json')
        report['sha256']={str(f.relative_to(a.out)):hashlib.sha256(f.read_bytes()).hexdigest()
            for f in a.out.rglob('*') if f.is_file() and f.name!='summary.json'}
        write(a.out/'summary.json',report)
    print(json.dumps(report,indent=2))


if __name__=='__main__':main()
