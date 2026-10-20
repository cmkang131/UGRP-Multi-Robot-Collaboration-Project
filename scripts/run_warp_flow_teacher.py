"""Beam pair / release teacher; MJWarp default, approved Linux GCP hosts only.

Existing CPU entrypoints are retained as explicit historical comparisons.
Training and LLM execution are outside this adapter's admission.
"""
from __future__ import annotations
import argparse
from collections import Counter, deque
import hashlib
import json
import os
from pathlib import Path
import platform
import subprocess
import sys
import time
import traceback

ROOT=Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0,str(ROOT))
if str(ROOT/'scripts') not in sys.path:
    sys.path.insert(0,str(ROOT/'scripts'))


def write(path,value):
    path.parent.mkdir(parents=True,exist_ok=True)
    path.write_text(json.dumps(value,indent=2,allow_nan=False,default=str)+'\n')


def require_source(path, expected):
    if subprocess.check_output(['git','-C',str(path),'rev-parse','HEAD'],text=True).strip()!=expected:
        raise ValueError('exact frozen source required: '+expected)
    if subprocess.check_output(['git','-C',str(path),'status','--porcelain','--untracked-files=no']):
        raise ValueError('clean frozen source required')


def require_case_profiles(flow,cases):
    for case in cases:
        if case['plan'].get('scene_profile')!='walls_floor_contrast_v5_indigo110_s80':
            raise ValueError('selected scene-v5 required for every flow case')
        if flow=='release':
            required=dict(held_object='hidden_v1',pose_anchor='command_relative_v1',
                lookaround='setdown_global_v1',placement='global_localized_release_v1',
                review_top='off',release_sweep_wall_aware='release_sweep_wall_aware_v1')
            if any(case.get('profile',{}).get(k)!=v for k,v in required.items()):
                raise ValueError('release25 hidden/command-relative own-RGB profile required')


def world_sim_clocks(contexts, results):
    # The perception mirror advances every lane's timestamp, including lanes
    # whose teacher already returned. Use that terminal task duration instead
    # of crediting padding physics as completed task work.
    return [max(0.,float(results[i]['sim_s']) if i in results else
                float(c['world'].data.time)-float(c['origin']))
            for i,c in enumerate(contexts)]


def parser():
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('--physics-backend',choices=['mjwarp_batch_v1','c_pilot_v1'],default='mjwarp_batch_v1')
    p.add_argument('--flow',choices=['beampair','release'],required=True)
    p.add_argument('--adapter-source',type=Path,required=True)
    p.add_argument('--teacher-source',type=Path)
    p.add_argument('--cases',type=Path,required=True,help='[{plan, profile, candidate}] exact immutable inputs')
    p.add_argument('--indices',help='world case indices; repeated indices are throughput only')
    p.add_argument('--canonical-xml',type=Path)
    p.add_argument('--cap-s',type=float,required=True)
    p.add_argument('--out',type=Path,required=True)
    p.add_argument('--initialize-only',action='store_true')
    p.add_argument('--export-compiled-only',action='store_true')
    p.add_argument('--compiled-reference-v1',type=Path)
    p.add_argument('--compiled-geometry-312-v1',type=Path)
    p.add_argument('--per-world-model-references-v1',type=Path)
    p.add_argument('--world-model-parameters-v1',action='store_true',help='retain exact heterogeneous parameters on one topology, never normalize masses')
    p.add_argument('--native-sleep-policy-compat-v1',action='store_true')
    p.add_argument('--placement-graspable-filter-v1',action='store_true')
    p.add_argument('--gcp3-isolated-v1',action='store_true',help='explicit warp6 L4 host admission; default OFF')
    p.add_argument('--batch-per-world-speed-v1',action='store_true',help='warp8 admission recording: batch wall / (batch SIM * world count); task throughput separate; default OFF')
    p.add_argument('--full-active-dof-workspace-v1',action='store_true',help='exact full-model nvmax workspace for legal wakeups; default OFF; no physics settings changed')
    p.add_argument('--warp-native-contact-v1',action='store_true',help='user-approved warpfit contact profile; separate cohort, legacy default unchanged')
    p.add_argument('--rejection-table',type=Path,help='absolute existing prior funnel for the warp8 gate')
    p.add_argument('--warp-debug-v1',action='store_true',help='Warp bounds checks and CUDA line information; default OFF')
    p.add_argument('--warp-workspace-trace-v1',action='store_true',help='synchronize and persist allocations after each existing graph chunk; default OFF')
    p.add_argument('--warp-verify-cuda-v1',action='store_true',help='uncaptured identical physics schedule with launch verification; default OFF')
    p.add_argument('--diagnostic-ticks',type=int,help='optional finite control-tick budget; never a teacher trial or SIM cap_end')
    p.add_argument('--sap-segmented-v1',action='store_true',help='existing upstream segmented sweep-and-prune candidate; default OFF')
    p.add_argument('--physics-profile-v1',action='store_true',help='record one discarded warmup step kernel timings; default OFF')
    p.add_argument('--mps-shared-v1',action='store_true',help='explicit private warp4 MPS runtime cohort; default OFF')
    p.add_argument('--vm-hourly-usd',type=float,required=True)
    p.add_argument('--student-eval',type=Path,help='pairact P5: student ACT issues every command (teacher DESIGN §9); default OFF')
    return p


STUDENT_EVAL_KEYS={'mode','python','source','model','config','device'}
STUDENT_EVAL_MODE='pairact_r1_student_eval_v1'
STUDENT_SHA='3c9337d5f5c9deefd49139b26ae7117022e3d5cc'   # dsh/pairact-p5-student worker tree


def load_student_eval(path):
    """Exact P5 config: the isolated worker's python/source/model/config. No GT key exists."""
    if path is None:return None
    cfg=json.loads(Path(path).read_text())
    if set(cfg)!=STUDENT_EVAL_KEYS or cfg['mode']!=STUDENT_EVAL_MODE:
        raise ValueError('student eval config must be exactly '+str(sorted(STUDENT_EVAL_KEYS)))
    for key in ('python','source','model','config'):
        if not Path(cfg[key]).is_absolute():raise ValueError(f'absolute {key} path required')
    head=source_head(cfg['source'])
    if head!=STUDENT_SHA:raise ValueError(f'student worker source {head} != pinned {STUDENT_SHA}')
    return cfg


def source_head(path):
    return subprocess.check_output(['git','-C',str(path),'rev-parse','HEAD'],text=True).strip()


def main():
    p=parser();a=p.parse_args()
    if platform.system()!='Linux':
        p.error('Mac physics/render forbidden; approved Linux GCP host required')
    if not 0<a.cap_s<=180 or not 0<a.vm_hourly_usd<float('inf'):
        p.error('finite existing SIM cap and explicit positive hourly price required')
    if a.diagnostic_ticks is not None and a.diagnostic_ticks<=0:
        p.error('positive diagnostic control-tick budget required')
    student_eval=load_student_eval(a.student_eval)
    if student_eval is not None and a.flow!='beampair':
        p.error('student eval is a beampair pair-carry flow option')
    if a.batch_per_world_speed_v1 and (not a.gcp3_isolated_v1 or a.rejection_table is None
            or not a.rejection_table.is_absolute() or not a.rejection_table.is_file()):
        p.error('warp8 speed recording requires isolated gcp3 and an absolute existing rejection table')
    if a.full_active_dof_workspace_v1 and not (a.gcp3_isolated_v1 and a.native_sleep_policy_compat_v1 and a.world_model_parameters_v1):
        p.error('full DOF workspace requires isolated gcp3 and the existing native sleep/world-model profiles')
    if a.mps_shared_v1 and os.environ.get('CUDA_MPS_PIPE_DIRECTORY')!='/home/ugrp/ugrp-sim/runs/warp4/mps/pipe':
        p.error('private task-owned MPS pipe required; no global GPU configuration changes')
    from simalt_host import gcp2_identity
    if a.gcp3_isolated_v1 and (a.mps_shared_v1 or not a.placement_graspable_filter_v1):
        p.error('isolated gcp3 requires placement filter ON and MPS OFF')
    host=gcp2_identity(gcp3_v1=a.gcp3_isolated_v1)
    if a.physics_backend=='mjwarp_batch_v1' and not (a.initialize_only or a.export_compiled_only) and host['instance'] not in ('ugrp-act-l4-gcp2','ugrp-act-l4-gcp3'):
        p.error('approved L4 required for rollout')
    if a.gcp3_isolated_v1:
        # Fail closed before creating a CUDA context. No MPS daemon is managed here.
        if any(k.startswith('CUDA_MPS_') for k in os.environ):
            p.error('isolated gcp3 forbids CUDA_MPS environment')
        gpu=subprocess.check_output(['nvidia-smi','--query-compute-apps=pid','--format=csv,noheader'],text=True).strip()
        mps=subprocess.run(['pgrep','-f','[n]vidia-cuda-mps'],capture_output=True,text=True)
        if gpu or mps.returncode!=1:
            p.error('isolated gcp3 requires no existing GPU clients or MPS daemon')
    if a.warp_debug_v1:
        import warp as wp
        wp.config.mode='debug'
    from warp_flow_episode import ADAPTER_SHA,TEACHER_SHA,RELEASE_SHA,make_lane
    require_source(a.adapter_source,ADAPTER_SHA if a.flow=='beampair' else RELEASE_SHA)
    if a.flow=='beampair':
        if not a.teacher_source:p.error('beampair needs pinned teacher source')
        require_source(a.teacher_source,TEACHER_SHA)
    else:
        require_source(a.adapter_source.parent/TEACHER_SHA,TEACHER_SHA)
    source=subprocess.check_output(['git','-C',str(ROOT),'rev-parse','HEAD'],text=True).strip()
    require_source(ROOT,source)
    cases=json.loads(a.cases.read_text())
    indices=[int(i) for i in a.indices.split(',')] if a.indices else list(range(len(cases)))
    if not indices or len(indices)>256 or any(i<0 or i>=len(cases) for i in indices):
        p.error('one to256 valid world indices required')
    selected=[cases[i] for i in indices]
    require_case_profiles(a.flow,selected)
    a.out.mkdir(parents=True,exist_ok=False)
    import numpy as np
    import mujoco
    from warp_act_backend import WarpTransport,CFlowTransport
    from warp_flow_model import model_arrays_equal
    from warp_flow_recording import DiskRing
    if a.physics_backend=='c_pilot_v1' and (len(indices)!=1 or host['instance']!='ugrp-sim-gcp2'):
        p.error('CPU comparison is one process/world on existing gcp2 CPU host')
    transport=WarpTransport if a.physics_backend=='mjwarp_batch_v1' else CFlowTransport
    hooks=transport(host,source,a.physics_backend,a.out,native_sleep_policy_compat_v1=a.native_sleep_policy_compat_v1)
    hooks.scene_v5_v1=True
    hooks.world_model_parameters_v1=a.world_model_parameters_v1
    hooks.batch_sleep_v1=a.world_model_parameters_v1
    hooks.placement_graspable_filter_v1=a.placement_graspable_filter_v1
    hooks.workspace_trace_v1=a.warp_workspace_trace_v1
    hooks.verify_cuda_v1=a.warp_verify_cuda_v1
    hooks.physics_profile_v1=a.physics_profile_v1
    hooks.warp_native_contact_v1=a.warp_native_contact_v1
    contact_profile=None
    if a.warp_native_contact_v1:
        # User 2026-10-16: use warpfit's byte-exact module; no other physics
        # compatibility profile changes until warpfit supplies its inventory.
        from sim.warp_native_contact import apply,record
        hooks.contact_xml_transform=lambda xml:apply(xml,'warp_native_contact_v1')
        contact_profile=record('warp_native_contact_v1')
        contact_profile.update(module_sha256=hashlib.sha256((ROOT/'sim/warp_native_contact.py').read_bytes()).hexdigest(),
            origin_commit='df5a1f86aad420f2fab2c10e3ee77cdb5ec11807',origin_PR=562)
    canonical_xml=a.canonical_xml.read_text() if a.canonical_xml else None
    if canonical_xml and a.warp_native_contact_v1:canonical_xml=hooks.contact_xml_transform(canonical_xml)
    canonical={'xml':canonical_xml}
    report=dict(schema='ugrp.warp4.batch.v1',status='running',source_sha=source,
        host=host,flow=a.flow,physics_backend=a.physics_backend,mujoco=mujoco.__version__,
        cases_sha256=hashlib.sha256(a.cases.read_bytes()).hexdigest(),world_indices=indices,
        planned_N=len(indices),started_N=0,completed_N=0,success_n=0,cap_end=0,HOST_ERROR=0,
        training_rgb=False,model_calls=0,weld='off',cpu_results_pooled=False,
        gcp3_isolated_v1=a.gcp3_isolated_v1,warp_debug_v1=a.warp_debug_v1,
        workspace_trace_v1=a.warp_workspace_trace_v1,
        warp_verify_cuda_v1=a.warp_verify_cuda_v1,
        diagnostic_ticks=a.diagnostic_ticks,
        sap_segmented_v1=a.sap_segmented_v1,physics_profile_v1=a.physics_profile_v1,
        gate_eligible=False,shared_load=not a.gcp3_isolated_v1,vm_hourly_usd=a.vm_hourly_usd,
        placement_graspable_filter_v1=a.placement_graspable_filter_v1,
        batch_per_world_speed_v1=a.batch_per_world_speed_v1,
        full_active_dof_workspace_v1=a.full_active_dof_workspace_v1,
        contact_profile=contact_profile,
        prior_rejection_table=str(a.rejection_table) if a.rejection_table else None,
        cuda_runtime_profile=('gcp3_isolated_no_mps_v1' if a.gcp3_isolated_v1 else
            'warp4_private_mps_v1' if a.mps_shared_v1 else 'shared_contexts_baseline'),
        price_basis='inherited regional VM estimate; billing unverified',reproduce=sys.argv)
    if student_eval is not None:
        # P5: success below is the student's (joint hold reached AND the unchanged GT evaluator).
        report.update(model_calls=None,student_eval=dict(student_eval,
            config_sha256=hashlib.sha256(Path(student_eval['config']).read_bytes()).hexdigest()))
    write(a.out/'summary.json',report)
    lanes=[];bridges=[];contexts=[];results={};recent=[deque(maxlen=100) for _ in indices]
    disk_rings=[DiskRing(a.out/f'world-{i:03d}'/'tail-ring-10hz') for i in range(len(indices))]
    active=np.ones(len(indices),bool);ticks=0;start=time.perf_counter();loop=None
    try:
        for i,case in enumerate(selected):
            lane,bridge=make_lane(a.adapter_source,a.teacher_source,case['plan'],a.out/f'world-{i:03d}',hooks,i,a.cap_s,
                flow=a.flow,profile=case.get('profile'),canonical=canonical,
                candidate=case.get('candidate','baseline'),student_eval=student_eval)
            lanes.append(lane);bridges.append(bridge)
            contexts.append(next(lane));report['started_N']+=1
        write(a.out/'single-model-audit.json',model_arrays_equal([c['world'].model for c in contexts]))
        native=[]
        for c in contexts:
            m,d=c['world'].model,c['world'].data
            trees=m.body_treeid[m.dof_bodyid]
            native.append(dict(nv=int(m.nv),tree_asleep=d.tree_asleep.tolist(),
                active_dofs=int(np.sum(d.tree_asleep[trees]<0)),
                robot_dofs={r:int(np.count_nonzero(trees==m.body_treeid[m.body(r+'__robot').id])) for r in c['ports']}))
        write(a.out/'native-setup-audit.json',native)
        if a.warp_native_contact_v1:
            contact_options=[]
            for c in contexts:
                opt=c['world'].model.opt
                values=dict(noslip_iterations=int(opt.noslip_iterations),cone=int(opt.cone),
                    integrator=int(opt.integrator),impratio=float(opt.impratio),
                    iterations=int(opt.iterations),ls_iterations=int(opt.ls_iterations))
                if values!=dict(noslip_iterations=0,cone=int(mujoco.mjtCone.mjCONE_ELLIPTIC),
                        integrator=int(mujoco.mjtIntegrator.mjINT_IMPLICITFAST),impratio=5.,iterations=80,ls_iterations=50):
                    raise ValueError('warpfit native-v1 options or retained Newton/LS80/50 differ: '+str(values))
                contact_options.append(values)
            write(a.out/'native-contact-options.json',dict(profile=contact_profile,worlds=contact_options))
        if not model_arrays_equal([c['world'].model for c in contexts])['exact'] and not a.world_model_parameters_v1:
            raise ValueError('single-model post-setup arrays differ; no SLEEP exception admitted')
        (a.out/'canonical-scene.xml').write_text(canonical['xml'])
        write(a.out/'canonical-poses.json',[b.model_audit for b in bridges])
        report['native_initialization_only_sim_s']=[float(c['origin']) for c in contexts]
        if a.export_compiled_only:
            if mujoco.__version__!='3.12.0':raise ValueError('C312 reference export requires3.12')
            from simalt_compiled_compat import export_reference,export_geometry
            references={}
            for c in contexts:
                xml=Path(c['scene_xml_path']);m=c['world'].model
                sha=hashlib.sha256(xml.read_bytes()).hexdigest()
                if sha in references:continue
                folder=a.out/'references'/sha;folder.mkdir(parents=True)
                export_reference(m,xml,mujoco.__version__,folder/'compiled-312.json')
                export_geometry(m,xml,mujoco.__version__,folder/'compiled-geometry312.npz')
                references[sha]=dict(actuator=str(folder/'compiled-312.json'),geometry=str(folder/'compiled-geometry312.npz'))
            write(a.out/'per-world-references.json',references)
        if a.initialize_only or a.export_compiled_only:
            report['status']='initialization_only';return
        references=json.loads(a.per_world_model_references_v1.read_text()) if a.per_world_model_references_v1 else None
        first=references[hashlib.sha256(Path(contexts[0]['scene_xml_path']).read_bytes()).hexdigest()] if references else {}
        if a.physics_backend=='mjwarp_batch_v1':
            hooks.initialize(contexts,compiled_reference=Path(first['actuator']) if first else a.compiled_reference_v1,
                compiled_geometry=Path(first['geometry']) if first else a.compiled_geometry_312_v1,
                per_world_model_references=references,sap_segmented_v1=a.sap_segmented_v1,
                full_active_dof_workspace_v1=a.full_active_dof_workspace_v1)
            report.update(camera=hooks.camera,capacities=hooks.capacities,compatibility=hooks.compat,
                initial_state_proof=hooks.initial_state_proof(contexts),model_batch_audit=hooks.model_batch_audit,
                sleep_audit=hooks.sleep_audit,solver_numerics=hooks.solver_numerics)
        report.update(started_N=len(contexts),setup_compile_s=time.perf_counter()-start)
        write(a.out/'summary.json',report)
        loop=time.perf_counter()
        while active.any():
            for i in np.flatnonzero(active):
                sample=dict(world_t=float(contexts[i]['world'].data.time),
                    images={r:hooks.capture(i,contexts[i]['world'],r) for r in contexts[i]['ports']})
                recent[i].append(sample)
                disk_rings[i].add(sample['world_t'],sample['images'])
                if ticks%5==0:
                    for rid,jpg in sample['images'].items():
                        path=a.out/f'world-{i:03d}'/'review-2hz'/rid/f'{ticks:06d}.jpg'
                        path.parent.mkdir(parents=True,exist_ok=True);path.write_bytes(jpg)
                try:next(lanes[i])
                except StopIteration as done:
                    active[i]=False;results[int(i)]=done.value
            if active.any():hooks.step(contexts,active)
            ticks+=1
            elapsed=time.perf_counter()-loop
            progress=dict(ticks=ticks,active_N=int(active.sum()),completed_N=len(results),
                sim_s=ticks*.1,loop_wall_s=elapsed,timing=dict(hooks.seconds))
            if a.batch_per_world_speed_v1:
                # User-supplied coordinator decision 2026-10-16, user
                # unconfirmed: admission uses wall / (batch SIM * world count).
                # Task throughput excludes padding and is a separate metric.
                clocks=world_sim_clocks(contexts,results)
                aggregate=sum(clocks)
                batch_sim=getattr(hooks,'tick',ticks)*.1
                progress.update(world_sim_s=clocks,aggregate_world_sim_s=aggregate,
                    batch_sim_s=batch_sim,
                    per_world_wall_SIM=elapsed/(batch_sim*len(indices)) if batch_sim else None,
                    task_wall_per_SIM=elapsed/aggregate if aggregate else None,
                    batch_wall_SIM=elapsed/batch_sim if batch_sim else None)
                if batch_sim>=30.-1e-8 and not (a.out/'first30-speed.json').exists():
                    write(a.out/'first30-speed.json',dict(progress,
                        scope='first batch clock >=30 SIM; setup/compile excluded; admission denominator=batch SIM*world count',
                        basis='coordinator decision 2026-10-16, user unconfirmed',
                        block_threshold=6.,warning_threshold=3.5,
                        speed_gate_fail=progress['per_world_wall_SIM']>6.))
            write(a.out/'progress.json',progress)
            if a.diagnostic_ticks is not None and ticks>=a.diagnostic_ticks:break
        report['status']='diagnostic_prefix_complete' if active.any() else 'complete'
    except BaseException as error:
        rejected=type(error).__name__=='PlacementRejected'
        report.update(status='admission_rejected' if rejected else 'HOST_ERROR',HOST_ERROR=0 if rejected else 1,
            error_type=type(error).__name__,error=str(error),traceback=traceback.format_exc())
        raise
    finally:
        loop_wall=time.perf_counter()-loop if loop is not None else None
        for lane in lanes:
            try:lane.close()
            except BaseException as error:report.setdefault('close_errors',[]).append(str(error))
        hooks.save_states()
        worlds=[]
        for i,raw in sorted(results.items()):
            success=bool(raw.get('physical_success') if a.flow=='beampair' else raw.get('release_success'))
            sim=float(raw.get('sim_s',0.))
            worlds.append(dict(world=i,seed=selected[i]['plan']['seed'],candidate=selected[i].get('candidate'),
                success=success,sim_s=sim,cap_end=not success and sim>=a.cap_s-1e-8,
                # pairact P2 (default off): separate eval-only carry judgement,
                # never merged into the grasp gate ``success`` above.
                carry_success=(raw.get('carry_eval') or {}).get('success'),
                carry_failure=(raw.get('carry_eval') or {}).get('failure'),
                **({'student_funnel':(raw.get('student_eval') or {}).get('funnel'),
                    'teacher_steps':(raw.get('student_eval') or {}).get('teacher_steps'),
                    'student_worker_requests':(raw.get('student_eval') or {}).get('worker_requests')}
                   if student_eval is not None else {}),
                input_audit=raw.get('input_audit'),raw=str(a.out/f'world-{i:03d}'/'raw')))
        # Recording-only native JPEG ring, including bootstrap exceptions and
        # supervisor interrupts. No extra render/capture calls enter control.
        for i,ring in enumerate(recent):
            rows=[]
            for j,sample in enumerate(ring):
                files={}
                for rid,jpg in sample['images'].items():
                    path=a.out/f'world-{i:03d}'/'tail-10hz'/rid/f'{j:04d}.jpg'
                    path.parent.mkdir(parents=True,exist_ok=True);path.write_bytes(jpg);files[rid]=str(path)
                rows.append(dict(world_t=sample['world_t'],files=files))
            write(a.out/f'world-{i:03d}'/'tail-10hz.json',rows)
        report.update(worlds=worlds,completed_N=len(worlds),success_n=sum(r['success'] for r in worlds),
            cap_end=sum(r['cap_end'] for r in worlds),wall_s=time.perf_counter()-start,timing=dict(hooks.seconds),
            source_contract=dict(adapter_sha=ADAPTER_SHA if a.flow=='beampair' else RELEASE_SHA,
                certification_sha=TEACHER_SHA,teacher_sha=TEACHER_SHA if a.flow=='beampair' else RELEASE_SHA,
                ast_transforms=[b.transforms for b in bridges]),
            native_initialization_only_sim_s=[float(c['origin']) for c in contexts])
        report['solver_samples']=getattr(hooks,'solver_samples',[])
        sim=sum(r['sim_s'] for r in worlds)
        report.update(aggregate_completed_task_sim_s=sim,loop_wall_s=loop_wall,
            warm_loop_sim_s_per_wall_s=sim/loop_wall if loop_wall and report['status']=='complete' else None,
            warm_loop_sim_s_per_usd=3600*sim/loop_wall/a.vm_hourly_usd if loop_wall and report['status']=='complete' else None,
            warm_scope='full fixed-scenario task after model/graph warmup; includes teacher/RGB/recording; incomplete runs have no throughput',
            vm_cost_estimate_usd=report['wall_s']*a.vm_hourly_usd/3600,
            cost_scope='whole VM estimate over this interval; overlapping shared jobs must not be summed; not billing')
        categories=Counter('cap_end' if r['cap_end'] else 'teacher_failure' for r in worlds if not r['success'])
        if report['HOST_ERROR']:categories[report['error_type']]+=1
        table=dict(raw=str(a.out),reproduce=sys.argv,funnel=[
            dict(stage='requested',passed_cumulative_N=len(indices),rejected_N=0),
            dict(stage='setup',passed_cumulative_N=len(contexts),rejected_N=len(indices)-len(contexts)),
            dict(stage='completed',passed_cumulative_N=len(worlds),rejected_N=len(contexts)-len(worlds)),
            dict(stage='success',passed_cumulative_N=report['success_n'],rejected_N=len(worlds)-report['success_n'])],
            rejections=[dict(reason_category=k,blocked_object='software:'+k if report['HOST_ERROR'] else 'none:unattributed',min_gap_m=None,count=v) for k,v in categories.items()])
        write(a.out/'rejection_table.json',table);report['rejection_table']=str(a.out/'rejection_table.json')
        artifacts={str(f.relative_to(a.out)):dict(bytes=f.stat().st_size,sha256=hashlib.sha256(f.read_bytes()).hexdigest())
            for f in sorted(a.out.rglob('*')) if f.is_file() and f.name not in ('summary.json','artifact-sha256.json')}
        write(a.out/'artifact-sha256.json',artifacts)
        report['artifact_sha256_manifest']=dict(path=str(a.out/'artifact-sha256.json'),
            sha256=hashlib.sha256((a.out/'artifact-sha256.json').read_bytes()).hexdigest(),files=len(artifacts))
        write(a.out/'summary.json',report)
        hooks.close()


if __name__=='__main__':main()
