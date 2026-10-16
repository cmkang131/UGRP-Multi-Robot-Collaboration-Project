"""Explicit gcp2 MJWarp relocation batch; queue/funnel and clean SHA required."""
from __future__ import annotations
import argparse,datetime,hashlib,json,os,platform,subprocess,sys,time,traceback
from pathlib import Path
import numpy as np
from scripts.warp5_batch import Batch
from scripts.warp5_episode import make_carry,make_selfmap

ROOT=Path(__file__).resolve().parents[1]


def write(p,value):p.write_text(json.dumps(value,indent=2,allow_nan=False)+'\n')


def admit_render_gate(gate,diagnostic):
    if gate.get('admission_scope')=='static DEV motion diagnosis only' and not diagnostic:
        raise ValueError('static RGB audit admits explicit motion diagnosis only')
    measured=gate.get('checks',{})
    diagnostic_admitted=diagnostic and all(measured.get(k) is True for k in ('semantic_labels_present','hashes_match','no_false_components'))
    if not gate.get('admitted',False) and not diagnostic_admitted:
        raise ValueError('MJWarp visual admission missing; control batch withheld')


def identity(*,gcp3_exclusive=False):
    from scripts.grasp_act_host import metadata
    base='http://169.254.169.254/computeMetadata/v1/'
    get=lambda key:metadata(base+key,{'Metadata-Flavor':'Google'})
    host=dict(provider='gcp',project_id=get('project/project-id'),instance=get('instance/name'),
              machine_type=get('instance/machine-type').rsplit('/',1)[-1],zone=get('instance/zone').rsplit('/',1)[-1],
              cpu_count=len(os.sched_getaffinity(0)),schema='ugrp.grasp_act.host.v1')
    expected=('ugrp-sim-c-1016','ugrp-act-l4-gcp3') if gcp3_exclusive else ('ugrp-sim-b-1014','ugrp-act-l4-gcp2')
    if (host['project_id'],host['instance'])!=expected:raise ValueError('registered L4 host required')
    return host


def run(a):
    q=json.loads(a.queue.read_text());sha=subprocess.check_output(['git','rev-parse','HEAD'],cwd=ROOT,text=True).strip()
    if q['source_sha']!=sha or subprocess.check_output(['git','status','--porcelain','--untracked-files=no'],cwd=ROOT):raise ValueError('clean pinned source required')
    rejection=Path(q['rejection_table'])
    if not rejection.is_absolute() or not rejection.is_file():raise ValueError('existing absolute rejection_table required')
    if not a.setup_only:
        gate=json.loads(Path(q['render_gate']).read_text())
        diagnostic=q.get('diagnostic_only') is True
        # The user explicitly requests N16 motion diagnosis after measuring
        # native-image accuracy. Keep incomplete recall NOT_READY; an explicit
        # DEV queue may investigate it only with complete labels/hashes and
        # zero falsely accepted components. Never promote this to E2E-ready.
        admit_render_gate(gate,diagnostic)
        if len(q['runs'])<16 and not q.get('warp9_profile_v1'):raise ValueError('N16 minimum for run-first batch')
    exclusive=q.get('warp9_exclusive_gcp3_v1',False)
    host=identity(gcp3_exclusive=exclusive);a.output.mkdir(parents=True,exist_ok=False)
    for key,value in q.get('environment',{}).items():
        if not key.startswith(('UGRP_SCENE_','UGRP_RELOC','UGRP_WARP5_','UGRP_WARP7_')):raise ValueError('unapproved simulation environment field')
        os.environ[key]=str(value)
    base=Path('/home/ugrp/ugrp-sim');leases=[json.loads(p.read_text()) for p in (base/'leases').glob('*.json')]
    task=q.get('task','warp5')
    if task not in ('warp5','warp7','warp9') or not any(l.get('task')==task for l in leases):raise ValueError('matching task lease required before execution')
    foreign=[l for l in leases if l.get('task')!=task]
    if exclusive and foreign:raise ValueError('exclusive gcp3 has foreign leases')
    if exclusive:
        gpu_pids=subprocess.check_output(['nvidia-smi','--query-compute-apps=pid','--format=csv,noheader,nounits'],text=True).strip()
        if gpu_pids:raise ValueError('exclusive gcp3 has existing GPU processes: '+gpu_pids)
    # User's explicit N64 scaling diagnostic is not a 64-trial task gate.
    scaling=q.get('warp9_profile_v1') and exclusive and len(q['runs']) in (1,4,16,64)
    if not scaling and sum(l.get('concurrency',0) for l in foreign)+len(q['runs'])>40:raise ValueError('shared concurrency exceeds40')
    available=int(next(line for line in Path('/proc/meminfo').read_text().splitlines() if line.startswith('MemAvailable:')).split()[1])*1024
    free=os.statvfs(base).f_bavail*os.statvfs(base).f_frsize
    storage=None
    if q.get('measured_storage_budget_v1',False):
        from scripts.storage_budget import check
        budget=q['storage_budget']
        if budget['per_run_bytes']<=0 or budget['reserved_bytes']<0 or not budget['source']:raise ValueError('measured original storage distribution required')
        # Project AGENTS/storage_budget's8GiB x86 floor, original decoded peak
        # x1.25 from both300SIM-second CPU carry recordings, plus explicitly
        # reserved foreign-stage writes. Legacy unexplained15GiB stays default.
        storage=check('x86',free,len(q['runs']),budget['per_run_bytes'],budget['reserved_bytes'])
        if not storage['ok']:raise ValueError('measured persistent storage budget refused')
    elif free<15*1024**3:raise ValueError('existing host disk floor not met')
    if available<6*1024**3:raise ValueError('existing host memory floor not met')
    write(a.output/'resource-admission.json',dict(leases=leases,available_bytes=available,disk_free_bytes=free,storage=storage,
        gpu=subprocess.check_output(['nvidia-smi','--query-gpu=name,memory.used,memory.total,utilization.gpu','--format=csv,noheader'],text=True),shared_load=not exclusive))
    write(a.output/'queue.json',q)
    report=dict(status='RUNNING',source_sha=sha,host=host,shared_load=not exclusive,model_calls=0,
        physics_backend='mjwarp_batch_v1',pool_with_cpu=False,attempted=len(q['runs']),worlds=[],errors=[],
        diagnostic_only=q.get('diagnostic_only',False),visual_qualified=gate.get('visual_pipeline_qualified',False) if not a.setup_only else False)
    hooks=Batch(host,sha,'mjwarp_batch_v1',a.output)
    hooks.warp5_native_visual_v1=q.get('warp5_native_visual_v1',False)
    hooks.warp5_native_visual_v2=q.get('warp5_native_visual_v2',False)
    lanes=[];bridges=[];contexts=[];groups=[];active=np.ones(len(q['runs']),bool)
    started=time.perf_counter()
    try:
        for i,t in enumerate(q['runs']):
            out=a.output/f'world-{i:03d}'/'raw';out.parent.mkdir()
            if t['kind']=='carry':lane,bridge=make_carry(ROOT,t['plan'],out,host,t['kwargs'])
            elif t['kind']=='selfmap':lane,bridge=make_selfmap(ROOT,t['bundle'],out,host)
            else:raise ValueError('registered carry/selfmap lane required')
            lanes.append(lane);bridges.append(bridge)
            context=next(lane)
            if context['kind']!='setup':raise ValueError('missing isolated setup barrier')
            contexts.append(context)
        report['adapter_ast']=[b.ast_audit for b in bridges]
        write(a.output/'initial-state.json',dict(worlds=[dict(world=i,seed=t['seed'],
            qpos_sha256=hashlib.sha256(c['world'].data.qpos.tobytes()).hexdigest(),origin=c['origin']) for i,(t,c) in enumerate(zip(q['runs'],contexts))]))
        if a.setup_only:
            report.update(status='SETUP_ONLY',physics_steps=0);return
        from scripts.warp_act_core import model_key
        if q.get('warp7_native_model_batch_v1',False):
            from scripts.warp7_native_models import group_key
            world_keys=[group_key(c['world'].model) for c in contexts]
        else:world_keys=[model_key(c['world'].scene_xml) for c in contexts]
        keys=set(world_keys)
        for key in sorted(keys):
            indices=np.array([i for i,k in enumerate(world_keys) if k==key])
            folder=a.output/'groups'/key;folder.mkdir(parents=True)
            transport=Batch(host,sha,'mjwarp_batch_v1',folder,
                native_sleep_policy_compat_v1=q.get('native_sleep_policy_compat_v1',False))
            transport.warp5_native_visual_v1=hooks.warp5_native_visual_v1;transport.warp5_native_visual_v2=hooks.warp5_native_visual_v2
            transport.camera_demand_v1=q.get('warp7_camera_demand_v1',False)
            transport.native_model_batch_v1=q.get('warp7_native_model_batch_v1',False)
            transport.batch_sleep_v1=transport.native_model_batch_v1
            if q.get('warp9_profile_v1'):
                import warp as wp
                from scripts.warp9_profile import Profile
                transport.warp9_profile=Profile(wp)
            cc=[contexts[i] for i in indices];groups.append((indices,cc,transport));transport.initialize(cc,
                float32_solver_default_v1=q.get('float32_solver_default_v1',False),sap_segmented_v1=q.get('warp7_sap_segmented_v1',False))
        report.update(model_groups=[dict(worlds=ii.tolist(),camera=h.camera,compatibility=h.compat,capacities=h.capacities,
            model_batch=h.model_batch_audit,native_model_adapter=getattr(h,'native_model_adapter',None)) for ii,cc,h in groups])
        loop=time.perf_counter()
        for ii,cc,h in groups:
            if getattr(h,'warp9_profile',None):h.warp9_profile.rows.clear()
        targets=np.array([c['origin'] for c in contexts],float)
        while active.any():
            for i in np.flatnonzero(active):
                # A .2 s capture lane must not resume after only one .1 s GPU
                # step. Targets are absolute SIM times, rounded like export.
                if round(float(contexts[i]['world'].data.time),9)<round(float(targets[i]),9):continue
                try:
                    from scripts.warp9_profile import phase
                    with phase(groups[0][2],'controller_python'):
                        event=next(lanes[i])
                    if event['kind']!='step':raise ValueError('missing step barrier')
                    targets[i]=event['target']
                except StopIteration as done:
                    active[i]=False;result=done.value
                    report['worlds'].append(dict(world=int(i),seed=q['runs'][i]['seed'],result=result))
            if active.any():
                for indices,cc,transport in groups:
                    if active[indices].any():transport.step(cc,active[indices])
            elapsed=max(h.tick*.1 for ii,cc,h in groups)
            write(a.output/'progress.json',dict(sim_s=elapsed,active=int(active.sum()),completed=len(report['worlds']),wall_s=time.perf_counter()-loop,timing=[dict(h.seconds) for ii,cc,h in groups]))
            if q.get('warp9_profile_v1'):
                write(a.output/'profile.json',dict(groups=[dict(worlds=ii.tolist(),
                    export_audit=getattr(h,'export_profile_audit',None),**h.warp9_profile.summary()) for ii,cc,h in groups]))
                # Fixed SIM work from the submitted diagnostic, never a wall
                # deadline or a changed physics/policy acceptance threshold.
                if elapsed>=q['profile_sim_s']:
                    report.update(status='PROFILE_COMPLETE',batch_sim_s=elapsed,task_outcome='unmeasured')
                    break
            if elapsed>=30 and not (a.output/'first30.json').exists():
                ratio=(time.perf_counter()-loop)/elapsed
                write(a.output/'first30.json',dict(sim_s=elapsed,wall_per_sim=ratio,shared_load=not exclusive,status='SPEED_GATE_FAIL' if ratio>6 else 'PASS'))
        if report['status']=='RUNNING':report.update(status='COMPLETE',batch_sim_s=elapsed)
    except BaseException as exc:
        report.update(status='HOST_ERROR',errors=[dict(category='HOST_ERROR',reason=repr(exc),blocked_object='batch_adapter',minimum_gap_m=None,gap_status='not_measured',traceback=traceback.format_exc())])
        raise
    finally:
        for lane in lanes:
            try:lane.close()
            except BaseException as exc:report['errors'].append(dict(category='HOST_ERROR',reason=repr(exc),blocked_object='finalizer',minimum_gap_m=None))
        hooks.close()
        for ii,cc,h in groups:h.close()
        report['wall_s']=time.perf_counter()-started
        write(a.output/'summary.json',report)
        write(a.output/'rejection-table.json',dict(stages=[dict(stage='requested',cumulative_pass_n=len(q['runs']),rejected_n=0),dict(stage='setup',cumulative_pass_n=len(contexts),rejected_n=len(q['runs'])-len(contexts)),dict(stage='completed',cumulative_pass_n=len(report['worlds']),rejected_n=len(q['runs'])-len(report['worlds']))],errors=report['errors'],raw=str(a.output),reproduction=sys.argv))
        write(a.output/'SHA256SUMS.json',{str(p.relative_to(a.output)):hashlib.sha256(p.read_bytes()).hexdigest() for p in a.output.rglob('*') if p.is_file() and p.name!='SHA256SUMS.json'})


def main():
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('--queue',type=Path,required=True);p.add_argument('--output',type=Path,required=True)
    p.add_argument('--execute',action='store_true');p.add_argument('--setup-only',action='store_true')
    a=p.parse_args()
    if not a.execute or platform.system()!='Linux':p.error('explicit Linux gcp2 execution required; Mac physics/render forbidden')
    run(a)


if __name__=='__main__':main()
