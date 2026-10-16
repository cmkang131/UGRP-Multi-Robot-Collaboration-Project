"""Explicit Linux-only drive diagnostic. Fixed tapes; all state is evaluator-only.

No production defaults, policies, camera/FOV or model credentials are changed.
The 10 Hz state/contact recording is independent of control and retained in full
(a superset of the requested last-10-SIM-second ring) for deferred RGB replay.
"""
import argparse
import hashlib
import json
import math
import os
import platform
from pathlib import Path
import subprocess
import sys
import time
import traceback

PATTERNS = {'forward': [1, 1, 1, 1], 'left': [-1, 1, 1, -1], 'turn': [-1, 1, -1, 1]}
RENDER_SHA = '5974a181a2cec9731339a6ce3aadc0464b8dddcf'
FIELDS = ('geom_friction', 'geom_solref', 'geom_solimp', 'body_mass', 'body_inertia',
          'dof_damping', 'dof_armature', 'actuator_gainprm', 'actuator_biasprm',
          'geom_pos', 'geom_quat', 'geom_size', 'mesh_vert')


def dump(path, value):
    Path(path).write_text(json.dumps(value, indent=2, allow_nan=False) + '\n')


def sha(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def host(engine=None):
    name = platform.node().split('.')[0]
    allowed = ('ugrp-sim-gcp2', 'ugrp-act-l4-gcp5')
    if platform.system() != 'Linux' or name not in allowed:
        raise ValueError('explicit gcp2 CPU / gcp5 diagnostic only')
    if engine == 'warp' and name != allowed[1]:
        raise ValueError('Warp requires gcp5')
    lease = Path('/home/ugrp/ugrp-sim/leases/drivecheck.json')
    if not lease.is_file():
        raise ValueError('drivecheck lease required')
    return name


def prepare(a):
    host()
    if subprocess.check_output(['git', '-C', str(a.renderer_source), 'rev-parse', 'HEAD'], text=True).strip() != RENDER_SHA:
        raise ValueError('pinned renderer source required')
    sys.path.insert(0, str(a.renderer_source))
    sys.path.insert(1, str(a.renderer_source / 'scripts'))
    import scripts
    scripts.__path__.insert(0, str(a.renderer_source / 'scripts'))
    os.chdir(a.renderer_source)
    import numpy as np
    import mujoco
    from scripts import probe_scene_tex2 as st
    from scripts.generate_scene_textures import MAPS
    from scripts.warp_act_core import runtime_sleep_policy
    from sim.masterpi_drive_friction_v7 import DriveParameters
    from harness.self_pulse_odom import model as pulse_model
    a.out.mkdir(parents=True, exist_ok=False)
    m, scene, hardware, xml, audit = st.build_model(MAPS[0], 'walls_floor_contrast_v5_indigo110_s80')
    from sim.camera_render_quality import configure_model
    configure_model(m, 'no_mip_v1')
    enum = mujoco.mjtSleepPolicy
    m.tree_sleep_policy[:] = runtime_sleep_policy(m.tree_sleep_policy.copy(), auto=int(enum.mjSLEEP_AUTO),
        auto_never=int(enum.mjSLEEP_AUTO_NEVER), auto_allowed=int(enum.mjSLEEP_AUTO_ALLOWED),
        never=int(enum.mjSLEEP_NEVER), allowed=int(enum.mjSLEEP_ALLOWED))
    d = mujoco.MjData(m)
    pwm, setup = st.fixture(m, d, scene, st.wall_views(scene.config['static_map'])[0], 'drive', hardware)
    d.ctrl[:] = 0
    for i in range(m.nu):
        if '__servo_' in m.actuator(i).name:
            d.ctrl[i] = d.qpos[int(m.jnt_qposadr[int(m.actuator_trnid[i, 0])])]
    (a.out / 'scene.xml').write_text(xml)
    cases = []
    # Pulse lengths requested by user. Original 60/100ms cases reproduce mapbuild2.
    for axis in PATTERNS:
        for duration in ([.25, .5, 1., 2., 4.] + ([.06] if axis == 'left' else [.1])):
            cases.append(dict(id=f'{axis}-{duration:g}', axis=axis, duration_s=duration,
                              settle_s=1., tail_s=1., value=.35))
    params = DriveParameters()
    arrays = dict(qpos=d.qpos, qvel=d.qvel, ctrl=d.ctrl, tree_sleep_policy=m.tree_sleep_policy)
    for field in ('cam_pos', 'cam_quat', 'cam_resolution', 'cam_sensorsize', 'cam_intrinsic'):
        arrays[field] = getattr(m, field)
    # Save tapes sampled at the unchanged native timestep; no measured input.
    wheels = [m.actuator('r1__wheel_' + n + '_drive').id for n in ('fl', 'fr', 'rl', 'rr')]
    dt = float(m.opt.timestep)
    for row in cases:
        ticks = round((row['settle_s'] + row['duration_s'] + row['tail_s']) / dt)
        tape = np.tile(d.ctrl, (ticks, 1))
        relay = np.zeros(4, int)
        for tick in range(ticks):
            active = round(row['settle_s']/dt) <= tick < round((row['settle_s']+row['duration_s'])/dt)
            u = .35*np.asarray(PATTERNS[row['axis']]) if active else np.zeros(4)
            effective, relay = params.command_step(u, relay)
            tape[tick, wheels] = params.torque_cap_nm * effective
        arrays[row['id']] = tape
        key = f"0:{row['axis']}:0.35:{row['duration_s']:.2f}"
        p = pulse_model()['profiles'].get(key)
        row['v122'] = None if p is None else dict(key=key, times=p['times'], mean_curve=p['mean_curve'])
    np.savez_compressed(a.out/'fixture.npz', **arrays)
    np.savez_compressed(a.out/'compiled312.npz', **{f: getattr(m, f) for f in FIELDS})
    dump(a.out/'fixture.json', dict(renderer_source=RENDER_SHA, fixture_sha256=sha(a.out/'fixture.npz'),
        xml_sha256=sha(a.out/'scene.xml'), map_sha256=sha(MAPS[0]), source_xml_sha256=hashlib.sha256(xml.encode()).hexdigest(),
        mujoco=mujoco.__version__, setup=setup, pwm=pwm, cases=cases, dt=dt, wheels=wheels,
        drive_parameters=params.record(), control_generation_physics_steps=0,
        prediction_note='v122 exact profiles only; uncalibrated durations are null, never extrapolated',
        physics_hashes={f: hashlib.sha256(getattr(m, f).tobytes()).hexdigest() for f in FIELDS}))
    dump(a.out/'rejection_table.json', dict(stages=[dict(stage='requested_pulses', cumulative_pass_n=18, rejected_n=0),
        dict(stage='generated_without_physics_feedback', cumulative_pass_n=18, rejected_n=0)], reasons=[], raw=str(a.out), reproduce=sys.argv))


def load_fixture(a):
    import numpy as np
    import mujoco
    os.chdir('/home/ugrp/ugrp-sim/src/drivecheck-renderer-5974a181')
    m = mujoco.MjModel.from_xml_string((a.fixture/'scene.xml').read_text())
    f = np.load(a.fixture/'fixture.npz')
    for field in ('tree_sleep_policy', 'cam_pos', 'cam_quat', 'cam_resolution', 'cam_sensorsize', 'cam_intrinsic'):
        getattr(m, field)[:] = f[field]
    if a.noslip_off_v1:
        m.opt.noslip_iterations = 0  # explicit diagnostic ablation; source value 10.
    meta = json.loads((a.fixture/'fixture.json').read_text())
    cases = [r for r in meta['cases'] if not a.only or r['id'] == a.only]
    return m, f, meta, cases


def run(a):
    hostname = host(a.engine)
    import numpy as np
    import mujoco
    m, f, meta, cases = load_fixture(a)
    a.out.mkdir(parents=True, exist_ok=False)
    q = json.loads(a.queue.read_text())
    if not q.get('enabled') or not Path(q['rejection_table']).is_file():
        raise ValueError('enabled queue with existing absolute rejection_table required')
    report = dict(status='running', engine=a.engine, host=hostname, mujoco=mujoco.__version__,
        source_sha=a.source_sha or subprocess.check_output(['git', 'rev-parse', 'HEAD'], text=True).strip(),
        fixture_sha256=sha(a.fixture/'fixture.npz'), xml_sha256=sha(a.fixture/'scene.xml'),
        toggles=dict(legacy_plane_v1=a.legacy_plane_v1, dense_capacity_v1=a.dense_capacity_v1,
                     noslip_off_v1=a.noslip_off_v1), cases=cases, dt=meta['dt'],
        options={k:float(getattr(m.opt,k)) for k in ('timestep','iterations','ls_iterations','noslip_iterations','tolerance','solver','cone','integrator')},
        physics_hashes={key:hashlib.sha256(getattr(m,key).tobytes()).hexdigest() for key in FIELDS},
        control_feedback=dict(truth=0, contacts=0, measured_joints=0, models=0),
        recording=dict(hz=10, scope='full evaluator state/contact history; deferred own-RGB reconstruction on gcp2',
                       terminal_ring_sim_s=10, control_path_unchanged=True), reproduce=sys.argv)
    dump(a.out/'RUN_META.json', dict(schema='ugrp.run_meta.v1', **{'class':'dev'}, pr=None,
         branch='codex/drivecheck', sha=report['source_sha'], batch='drivecheck'))
    np.savez_compressed(a.out/'compiled.npz', **{key:getattr(m,key) for key in FIELDS})
    dump(a.out/'result.json', report)
    dt = meta['dt']; stride = round(.1/dt)
    boundaries={round(r['settle_s']/dt) for r in cases}
    boundaries.update(round((r['settle_s']+r['duration_s'])/dt) for r in cases)
    boundaries.update(len(f[r['id']]) for r in cases)
    body = m.body('r1__robot').id
    report['base_qposadr'] = int(m.jnt_qposadr[m.body_jntadr[body]])
    geomwheel = np.full(m.ngeom, -1, int)
    for gid in range(m.ngeom):
        name = m.geom(gid).name or ''
        for wi, wn in enumerate(('fl','fr','rl','rr')):
            if name.startswith('r1__wheel_'+wn+'_roller_') and name.endswith('_contact'):
                geomwheel[gid] = wi
    planes = np.flatnonzero(m.geom_type == int(mujoco.mjtGeom.mjGEOM_PLANE))
    report['roller_contact_geoms'] = int(np.count_nonzero(geomwheel >= 0))
    report['floor_geoms'] = [m.geom(int(i)).name for i in planes]
    samples=[]; contacts=[]; started=time.perf_counter(); dense_ncon=0; dense_nefc=0
    try:
        if a.engine == 'cpu':
            for ci, case in enumerate(cases):
                d=mujoco.MjData(m);d.qpos[:]=f['qpos'];d.qvel[:]=f['qvel'];d.ctrl[:]=f['ctrl']
                mujoco.mj_forward(m,d)
                tape=f[case['id']]
                for tick in range(len(tape)+1):
                    if tick % stride == 0 or tick in boundaries:
                        samples.append((ci,tick*dt,d.qpos.copy(),d.qvel.copy(),int(d.ncon),int(d.nefc)))
                        for j,c in enumerate(d.contact):
                            g0,g1=map(int,c.geom)
                            if (geomwheel[g0]>=0 and g1 in planes) or (geomwheel[g1]>=0 and g0 in planes):
                                force=np.zeros(6);mujoco.mj_contactForce(m,d,j,force)
                                contacts.append([ci,tick*dt,g0,g1,float(c.dist),*c.pos,*np.asarray(c.frame).ravel(),*force])
                    if tick == len(tape):break
                    d.ctrl[:]=tape[tick];mujoco.mj_step(m,d)
                    dense_ncon=max(dense_ncon,int(d.ncon));dense_nefc=max(dense_nefc,int(d.nefc))
                report.update(completed_cases=ci+1, sim_s=sum(len(f[r['id']])*dt for r in cases[:ci+1]))
                dump(a.out/'result.json',report)
                print('completed',case['id'],flush=True)
        else:
            import warp as wp
            import mujoco_warp as mjw
            from scripts.simalt_physics_compare import unused_efm
            from mujoco_warp._src.support import contact_force_fn
            from mujoco_warp._src.types import vec5
            wp.init()
            report['warp']=wp.__version__
            report['warp_deterministic']=str(getattr(wp.config,'deterministic',None))
            wm=mjw.put_model(m);wm.opt.tolerance.fill_(float(m.opt.tolerance))
            if a.legacy_plane_v1:
                from scripts.simalt_collision_compat import install_legacy_plane
                report['collision_adapter']=install_legacy_plane(m)
            d=mujoco.MjData(m);d.qpos[:]=f['qpos'];d.qvel[:]=f['qvel'];d.ctrl[:]=f['ctrl'];mujoco.mj_forward(m,d)
            ncon=1 << (max(32,int(d.ncon))-1).bit_length()
            njmax=1 << (max(256,int(d.nefc))-1).bit_length()
            if a.dense_capacity_v1:
                ref=json.loads(a.capacity_reference.read_text())
                ncon=1 << (max(ncon,int(ref['max_ncon']))-1).bit_length()
                njmax=1 << (max(njmax,int(ref['max_nefc']))-1).bit_length()
            n=len(cases)
            report['capacities']=dict(nconmax=ncon,njmax=njmax,basis='import power of two; dense additionally uses observed reference maxima')
            def fresh():
                with unused_efm(m,d):data=mjw.put_data(m,d,nworld=n,nconmax=ncon,njmax=njmax)
                return data
            wd=fresh()
            mjw.step(wm,wd);wp.synchronize()
            wd=fresh()
            # Exactly 10 ms fixed physics graph, preserving original 60 ms pulse.
            substeps=round(.01/dt)
            with wp.ScopedCapture() as cap:
                for _ in range(substeps):mjw.step(wm,wd)
            max_ticks=max(len(f[r['id']]) for r in cases)
            force_out=wp.zeros((int(wd.naconmax),6),dtype=float)
            @wp.kernel
            def evaluate(cone:int,njmax:int,nacon:wp.array[int],frame:wp.array[wp.mat33],friction:wp.array[vec5],
                         condim:wp.array[int],adr:wp.array2d[int],adhesion:wp.array[float],
                         efc_force:wp.array2d[float],worldid:wp.array[int],out:wp.array2d[float]):
                i=wp.tid()
                if i < nacon[0]:
                    value=contact_force_fn(cone,frame,friction,condim,adr,adhesion,efc_force,njmax,nacon,worldid[i],i,False)
                    for k in range(6):out[i,k]=value[k]
            for tick in range(0,max_ticks+1,substeps):
                if tick % stride == 0 or tick in boundaries:
                    wp.synchronize()
                    if np.any(wd.overflow.numpy()):raise RuntimeError('CAPACITY_OVERFLOW '+str(wd.overflow.numpy().tolist()))
                    qp,qv=wd.qpos.numpy(),wd.qvel.numpy()
                    if not np.isfinite(qp).all() or not np.isfinite(qv).all():raise RuntimeError('NONFINITE_STATE')
                    nc=int(wd.nacon.numpy()[0]);ne=wd.nefc.numpy()
                    ids=wd.contact.worldid.numpy()
                    gs=wd.contact.geom.numpy();dist=wd.contact.dist.numpy();pos=wd.contact.pos.numpy();frame=wd.contact.frame.numpy()
                    wp.launch(evaluate,dim=int(wd.naconmax),inputs=[wm.opt.cone,wd.njmax,wd.nacon,wd.contact.frame,
                        wd.contact.friction,wd.contact.dim,wd.contact.efc_address,wd.contact.adhesion,wd.efc.force,
                        wd.contact.worldid,force_out])
                    forces=force_out.numpy()
                    for ci,case in enumerate(cases):
                        if tick<=len(f[case['id']]):
                            samples.append((ci,tick*dt,qp[ci].copy(),qv[ci].copy(),int(np.count_nonzero(ids[:nc]==ci)),int(ne[ci])))
                    for j in range(nc):
                        ci=int(ids[j]);g0,g1=map(int,gs[j])
                        if tick<=len(f[cases[ci]['id']]) and ((geomwheel[g0]>=0 and g1 in planes) or (geomwheel[g1]>=0 and g0 in planes)):
                            contacts.append([ci,tick*dt,g0,g1,float(dist[j]),*pos[j],*frame[j].ravel(),*forces[j]])
                    report.update(sim_s=tick*dt, max_ncon=int(max([s[4] for s in samples])),max_nefc=int(max([s[5] for s in samples])))
                    dump(a.out/'result.json',report)
                    print('recorded',tick*dt,flush=True)
                if tick==max_ticks:break
                controls=np.stack([f[r['id']][min(tick,len(f[r['id']])-1)] if tick<len(f[r['id']]) else f['ctrl'] for r in cases])
                wp.copy(wd.ctrl,wp.array(controls,dtype=wd.ctrl.dtype));wp.capture_launch(cap.graph)
            report['completed_cases']=len(cases)
        report.update(status='cap_end', cap_end=True, planned_tape_complete=True)
    except BaseException as exc:
        report.update(status='HOST_ERROR',error=dict(category='HOST_ERROR',reason=repr(exc),blocked_object='physics_engine_or_recorder',
            minimum_gap_m=None,gap_status='not_measured'),traceback=traceback.format_exc())
        raise
    finally:
        if samples:
            np.savez_compressed(a.out/'states.npz',case=np.asarray([s[0] for s in samples]),t=np.asarray([s[1] for s in samples]),
                qpos=np.asarray([s[2] for s in samples]),qvel=np.asarray([s[3] for s in samples]),
                ncon=np.asarray([s[4] for s in samples]),nefc=np.asarray([s[5] for s in samples]))
            report.update(max_ncon=max(s[4] for s in samples),max_nefc=max(s[5] for s in samples))
        np.savez_compressed(a.out/'contacts.npz',records=np.asarray(contacts).reshape(-1,23))
        if a.engine=='cpu':
            report.update(dense_max_ncon=dense_ncon,dense_max_nefc=dense_nefc)
        report.update(wall_s=time.perf_counter()-started,samples=len(samples),contact_rows=len(contacts),
                      recording_bytes=sum(p.stat().st_size for p in a.out.glob('*.npz')))
        dump(a.out/'result.json',report)
        done=report.get('completed_cases',0)
        dump(a.out/'rejection_table.json',dict(raw=str(a.out),reproduce=sys.argv,stages=[
            dict(stage='requested_pulses',cumulative_pass_n=len(cases),rejected_n=0),
            dict(stage='tape_complete',cumulative_pass_n=done,rejected_n=len(cases)-done)],
            reasons=[] if report['status']=='cap_end' else [report['error']]))
        dump(a.out/'SHA256SUMS.json',{p.name:sha(p) for p in a.out.iterdir() if p.is_file() and p.name!='SHA256SUMS.json'})


def main():
    p=argparse.ArgumentParser(description=__doc__)
    sub=p.add_subparsers(dest='action',required=True)
    b=sub.add_parser('prepare');b.add_argument('--renderer-source',type=Path,required=True);b.add_argument('--out',type=Path,required=True)
    b=sub.add_parser('run');b.add_argument('--enabled',action='store_true');b.add_argument('--fixture',type=Path,required=True)
    b.add_argument('--out',type=Path,required=True);b.add_argument('--engine',choices=('cpu','warp'),required=True)
    b.add_argument('--queue',type=Path,required=True);b.add_argument('--only')
    b.add_argument('--source-sha',help='original commit of a git archive on a host with shallow shared storage')
    b.add_argument('--legacy-plane-v1',action='store_true');b.add_argument('--dense-capacity-v1',action='store_true')
    b.add_argument('--noslip-off-v1',action='store_true');b.add_argument('--capacity-reference',type=Path)
    a=p.parse_args()
    if a.action=='prepare':prepare(a)
    elif a.enabled:run(a)
    else:p.error('explicit --enabled diagnostic required')


if __name__=='__main__':main()
