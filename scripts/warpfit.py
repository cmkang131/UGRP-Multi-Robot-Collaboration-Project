"""Finite, opt-in gcp6 fixed-command contact benchmark (no policy feedback).

Evaluation state is recorded at 10Hz for every world for deferred own-camera
reconstruction on gcp2. No rendered image or evaluator output changes a tape.
"""
import argparse
from contextlib import nullcontext
import hashlib
import json
import os
from pathlib import Path
import platform
import subprocess
import sys
import time
import traceback

PIN = '57b4692f4d3cdf4d27d916b4b8c4759ba36e9148'
OPTIONS = ('timestep', 'solver', 'cone', 'integrator', 'iterations', 'ls_iterations',
           'noslip_iterations', 'impratio', 'tolerance')


def dump(path, value):
    Path(path).write_text(json.dumps(value, indent=2, allow_nan=False) + '\n')


def digest(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def host():
    if platform.system() != 'Linux' or not platform.node().startswith('ugrp-act-l4-gcp6'):
        raise ValueError('explicit gcp6 diagnostic only; Mac physics forbidden')
    lease = Path('/home/ugrp/ugrp-sim/leases/warpfit.json')
    if not lease.is_file() or json.loads(lease.read_text()).get('task') != 'warpfit':
        raise ValueError('own warpfit lease required')


def load(a):
    import mujoco
    import numpy as np
    from sim.warp_native_contact import apply, record
    meta = json.loads((a.fixture/'fixture.json').read_text())
    os.chdir(meta['asset_cwd'])
    xml = apply((a.fixture/'scene.xml').read_text(), a.profile)
    m = mujoco.MjModel.from_xml_string(xml)
    if a.engine=='warp':
        # Keep the existing C3.12 compiled mesh/actuator compatibility constant
        # across ALL contact profiles. Drivecheck owns collider cause analysis;
        # this experiment changes contact/solver settings, not wheel geometry.
        from scripts.simalt_compiled_compat import apply_geometry, apply_reference
        apply_geometry(m,a.fixture/'scene.xml',a.fixture/'geometry312.npz')
        apply_reference(m,a.fixture/'scene.xml',a.fixture/'actuator312.json')
    f = np.load(a.fixture/'fixture.npz')
    for k in ('tree_sleep_policy', 'cam_pos', 'cam_quat', 'cam_resolution', 'cam_sensorsize', 'cam_intrinsic'):
        if k in f:
            getattr(m, k)[:] = f[k]
    if np.any(m.eq_active0):
        raise ValueError('active equality assistance forbidden')
    d = mujoco.MjData(m)
    for k in ('qpos', 'qvel', 'ctrl', 'qacc_warmstart'):
        if k in f:
            getattr(d, k)[:] = f[k]
    mujoco.mj_forward(m, d)
    return m, d, f, meta, xml, record(a.profile)


def run(a):
    host()
    import numpy as np
    import mujoco
    q = json.loads(a.queue.read_text())
    if not q.get('enabled') or not Path(q.get('rejection_table', '')).is_file():
        raise ValueError('enabled queue with existing rejection_table required')
    if a.round not in (1, 2, 3):
        raise ValueError('three-round limit')
    m, d, f, meta, xml, profile = load(a)
    a.output.mkdir(parents=True, exist_ok=False)
    (a.output/'scene.xml').write_text(xml)
    source = subprocess.check_output(['git', '-C', str(Path(__file__).resolve().parents[1]),
                                      'rev-parse', 'HEAD'], text=True).strip()
    report = dict(status='initializing', engine=a.engine, source_sha=source, profile=profile,
        round=a.round, nworld=a.nworld, fixture=str(a.fixture), fixture_sha256=digest(a.fixture/'fixture.npz'),
        xml_sha256=hashlib.sha256(xml.encode()).hexdigest(), mujoco=mujoco.__version__,
        model={k:int(getattr(m, k)) for k in ('nq','nv','nu','ngeom','nbody')},
        options={k:float(getattr(m.opt,k)) for k in OPTIONS},
        evaluation_only=True, feedback=dict(truth=0, contacts=0, measured_joints=0, models=0),
        recording=dict(hz=10, terminal_sim_s=10, full_history=True, recording_only=True),
        completed=0, HOST_ERROR=0, cap_end=False, rejection_table=str(a.output/'rejection_table.json'),
        reproduce=sys.argv, physical_gpu_s=0., physics_wall_s=0., sim_s=0., steps=0)
    dump(a.output/'RUN_META.json', dict(schema='ugrp.run_meta.v1', **{'class':'dev'},
         branch='codex/warpfit', sha=source, pr=None, batch='warpfit'))
    dump(a.output/'result.json', report)
    tape = f[a.case]
    if tape.ndim==3 and a.engine=='cpu':tape=tape[:,a.lane]
    dt = float(m.opt.timestep)
    stride = round(.1/dt)  # User's fixed 10Hz evaluator ring, independent of control.
    ticks = len(tape) if a.max_sim_s is None else min(len(tape), round(a.max_sim_s/dt))
    if ticks % stride:
        raise ValueError('fixed work must end on the recorded 10Hz boundary')
    samples=[]; all_contacts=[]; setup=time.perf_counter()
    max_nc=int(d.ncon); max_nf=int(d.nefc)
    target_ids={m.geom(n).id for n in meta.get('target_geoms',[])}
    fingers={m.geom(n).id:k for k,n in enumerate(meta.get('finger_geoms',[]))}
    try:
        if a.engine == 'warp':
            import warp as wp
            import mujoco_warp as mjw
            wp.init()
            import importlib.metadata
            url = json.loads(importlib.metadata.distribution('mujoco-warp').read_text('direct_url.json'))['url']
            if PIN not in url:
                raise ValueError('pinned MJWarp required: '+url)
            report.update(mjwarp_source=url, warp=wp.__version__)
            wm=mjw.put_model(m)
            from scripts.simalt_collision_compat import install_legacy_plane
            report['collision_adapter']=install_legacy_plane(m)
            report['compatibility_held_constant']='C312 mesh/actuator compilation and legacy plane; every profile'
            # Baseline preserves the earlier path's explicit 1e-8 tolerance.
            # Native profiles accept the pinned float32 conversion floor.
            if a.profile == 'baseline_noslip10':
                wm.opt.tolerance.fill_(float(m.opt.tolerance))
            report['effective_tolerance'] = float(wm.opt.tolerance.numpy().item())
            ref=json.loads(a.capacity_reference.read_text()) if a.capacity_reference else {}
            def pow2(x): return 1 << (max(1,int(x))-1).bit_length()
            nc=pow2(max(int(d.ncon),int(ref.get('max_ncon',0)),a.nconmax or 0))
            nf=pow2(max(int(d.nefc),int(ref.get('max_nefc',0)),a.njmax or 0))
            report['capacity']=dict(nconmax=nc,njmax=nf,basis='power-of-two observed C/import maxima; overflow rejects')
            from scripts.simalt_physics_compare import unused_efm
            with unused_efm(m,d): wd=mjw.put_data(m,d,nworld=a.nworld,nconmax=nc,njmax=nf)
            mjw.step(wm,wd);wp.synchronize()
            if np.any(wd.overflow.numpy()):
                raise RuntimeError('warmup CAPACITY_OVERFLOW')
            with unused_efm(m,d): wd=mjw.put_data(m,d,nworld=a.nworld,nconmax=nc,njmax=nf)
            if tape.ndim==2:tape=tape[:,None,:]
            wt=wp.array(np.asarray(tape,dtype=np.float32),dtype=wp.float32)
            tick=wp.zeros(1,dtype=wp.int32)
            @wp.kernel
            def control(values:wp.array3d[float],at:wp.array[int],ctrl:wp.array2d[float]):
                w,j=wp.tid()
                ctrl[w,j]=values[at[0],w%values.shape[1],j]
            @wp.kernel
            def advance(at:wp.array[int]): at[0]+=1
            # Same graph length in every profile. The unchanged native dt is
            # preserved; 10 ticks divide both 0.1s and drivecheck's .06s pulse.
            graph_steps=10
            with wp.ScopedCapture() as capture:
                for _ in range(graph_steps):
                    wp.launch(control,dim=(a.nworld,m.nu),inputs=[wt,tick,wd.ctrl])
                    mjw.step(wm,wd)
                    wp.launch(advance,dim=1,inputs=[tick])
            report['graph_steps']=graph_steps
            first,last=wp.Event(enable_timing=True),wp.Event(enable_timing=True)
        report.update(status='running',setup_jit_s=time.perf_counter()-setup)
        dump(a.output/'result.json',report)
        start=time.perf_counter()
        for begin in range(0,ticks+1,stride):
            if a.engine == 'warp':
                wp.synchronize()
                if np.any(wd.overflow.numpy()):
                    raise RuntimeError('CAPACITY_OVERFLOW '+str(wd.overflow.numpy().tolist()))
                qp,qv=wd.qpos.numpy(),wd.qvel.numpy()
                nacon=int(wd.nacon.numpy()[0]); ids=wd.contact.worldid.numpy()[:nacon]
                gs=wd.contact.geom.numpy()[:nacon]; dist=wd.contact.dist.numpy()[:nacon]
                nc_world=np.bincount(ids,minlength=a.nworld)
                nefc=wd.nefc.numpy()
                force=wd.efc.force.numpy(); adr=wd.contact.efc_address.numpy()[:nacon]
                normal=np.array([force[int(w),int(v[0])] if v[0]>=0 else 0. for w,v in zip(ids,adr)])
            else:
                qp,qv=d.qpos[None].copy(),d.qvel[None].copy()
                gs=np.array([c.geom for c in d.contact],int).reshape(-1,2)
                ids=np.zeros(d.ncon,int);dist=d.contact.dist.copy()
                normal=np.array([d.efc_force[c.efc_address] if c.efc_address>=0 else 0. for c in d.contact])
                nc_world=np.array([d.ncon]);nefc=np.array([d.nefc])
            if not np.isfinite(qp).all() or not np.isfinite(qv).all():
                raise RuntimeError('NONFINITE_STATE')
            max_nc=max(max_nc,int(max(nc_world)));max_nf=max(max_nf,int(max(nefc)))
            finger_force=np.zeros((a.nworld,len(fingers)))
            for j,(g0,g1) in enumerate(gs):
                fid=int(g1) if int(g0) in target_ids else int(g0) if int(g1) in target_ids else -1
                if fid in fingers and dist[j]<=0:
                    finger_force[int(ids[j]),fingers[fid]]+=max(0.,float(normal[j]))
            samples.append((begin*dt,qp.copy(),qv.copy(),nc_world.copy(),nefc.copy(),finger_force))
            # Contacts are evaluator output only. World0 retains all pairs for
            # inspecting blocked objects/minimum gaps without hidden control.
            sel=np.flatnonzero(ids==0)
            all_contacts.extend([[begin*dt,int(gs[j,0]),int(gs[j,1]),float(dist[j]),float(normal[j])] for j in sel])
            if begin == ticks:break
            ps=time.perf_counter()
            if a.engine == 'warp':
                wp.record_event(first)
                for _ in range(stride//graph_steps):wp.capture_launch(capture.graph)
                wp.record_event(last);wp.synchronize()
                report['physical_gpu_s']+=wp.get_event_elapsed_time(first,last)/1000.
            else:
                for j in range(begin,begin+stride):
                    d.ctrl[:]=tape[j];mujoco.mj_step(m,d)
            report['physics_wall_s']+=time.perf_counter()-ps
            report.update(sim_s=(begin+stride)*dt,steps=begin+stride,
                          runtime_wall_s=time.perf_counter()-start,max_ncon=max_nc,max_nefc=max_nf)
            if begin % (10*stride)==0:
                dump(a.output/'result.json',report)
                print(a.profile,a.nworld,a.case,report['sim_s'],flush=True)
        report.update(status='complete',completed=1,runtime_wall_s=time.perf_counter()-start)
        report['wall_per_sim_s']=report['runtime_wall_s']/report['sim_s']
        report['amortized_wall_per_world_sim_s']=report['wall_per_sim_s']/a.nworld
        report['physical_gpu_ms_per_step']=1000*report['physical_gpu_s']/ticks if a.engine=='warp' else None
        report['cap_end']=ticks<len(tape)
    except BaseException as error:
        report.update(status='HOST_ERROR',HOST_ERROR=1,error=repr(error),traceback=traceback.format_exc())
    finally:
        if samples:
            np.savez_compressed(a.output/'states.npz',t=[s[0] for s in samples],qpos=[s[1] for s in samples],
                qvel=[s[2] for s in samples],ncon=[s[3] for s in samples],nefc=[s[4] for s in samples],
                finger_force=[s[5] for s in samples])
            np.savez_compressed(a.output/'contacts-world0.npz',contacts=np.array(all_contacts).reshape(-1,5))
        report['max_ncon']=max_nc;report['max_nefc']=max_nf
        passed=report['completed']
        dump(a.output/'rejection_table.json',dict(stages=[
            dict(gate='fixed_tape_admitted',cumulative_pass=1,rejected=0),
            dict(gate='finite_no_overflow_fixed_work',cumulative_pass=passed,rejected=1-passed)],
            reasons=[] if passed else [dict(category='HOST_ERROR',reason=report.get('error','incomplete'),
                blocked_object='physics_engine',minimum_gap_m=None,gap_status='not_geometric')],
            raw=str(a.output),reproduce=sys.argv))
        dump(a.output/'result.json',report)
        dump(a.output/'SHA256.json',{p.name:digest(p) for p in a.output.iterdir() if p.is_file() and p.name!='SHA256.json'})
    if not report['completed']:raise SystemExit(1)


def main():
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('--enabled',action='store_true')
    p.add_argument('--fixture',type=Path,required=True)
    p.add_argument('--output',type=Path,required=True)
    p.add_argument('--queue',type=Path,required=True)
    p.add_argument('--case',default='tape')
    p.add_argument('--lane',type=int,default=0,help='C reference lane in a batched drive tape')
    p.add_argument('--engine',choices=['cpu','warp'],default='warp')
    p.add_argument('--profile',default='baseline_noslip10')
    p.add_argument('--nworld',type=int,choices=[1,16,64],default=1)
    p.add_argument('--round',type=int,required=True)
    p.add_argument('--capacity-reference',type=Path)
    p.add_argument('--nconmax',type=int)
    p.add_argument('--njmax',type=int)
    p.add_argument('--max-sim-s',type=float)
    a=p.parse_args()
    if not a.enabled:p.error('explicit --enabled required')
    if a.engine=='cpu' and a.nworld!=1:p.error('C distribution is a separate N1 reference')
    run(a)


if __name__=='__main__':main()
