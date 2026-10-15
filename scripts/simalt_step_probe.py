"""Opt-in gcp2 evaluator: record every physics step of a frozen command tape.

No measured value feeds the tape. Raw step arrays stay on the execution host.
Resource wall caps are external; simulation work is bounded by tape length.
"""
import argparse
import hashlib
import json
from pathlib import Path
import platform
import sys
import time


COLUMNS = ['ncon', 'nefc', 'overflow', 'left_contacts', 'right_contacts',
           'left_min_dist', 'right_min_dist', 'left_normal_N', 'right_normal_N',
           'left_tangent_N', 'right_tangent_N', 'plane_mesh_contacts',
           'minimum_dist', 'left_joint', 'right_joint', 'left_condim', 'right_condim']


def digest(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('--enabled', action='store_true')
    p.add_argument('--fixture', type=Path, required=True)
    p.add_argument('--out', type=Path, required=True)
    p.add_argument('--engine', choices=['cpu', 'warp'], required=True)
    p.add_argument('--case', choices=['forward', 'side', 'turn', 'grip'], required=True)
    p.add_argument('--sha', required=True)
    p.add_argument('--capacity-reference', type=Path, required=True)
    p.add_argument('--backend-mode', choices=['baseline', 'box-sat-v1'], default='baseline')
    a = p.parse_args()
    if not a.enabled or platform.system() != 'Linux':
        p.error('explicit Linux gcp2 opt-in required; Mac physics/render forbidden')
    from simalt_host import gcp2_identity
    host = gcp2_identity()
    if a.engine == 'warp' and host['instance'] != 'ugrp-act-l4-gcp2':
        p.error('Warp requires the existing gcp2 L4')
    if a.engine != 'warp' and a.backend_mode != 'baseline':
        p.error('backend workaround is Warp only')
    import numpy as np
    import mujoco
    a.out.mkdir(parents=True, exist_ok=False)
    m = mujoco.MjModel.from_xml_path(str(a.fixture/'scene.xml'))
    f = np.load(a.fixture/'fixture.npz')
    tape = f[a.case]
    dt = float(m.opt.timestep)
    d = mujoco.MjData(m)
    d.qpos[:] = f['qpos']; d.qvel[:] = f['qvel']; d.ctrl[:] = tape[0]
    mujoco.mj_forward(m, d)
    if m.opt.noslip_iterations != 10 or np.any(m.eq_active0):
        raise RuntimeError('frozen noslip10 / weld OFF required')
    left, right, box = [m.geom(n).id for n in
                        ('r1__left_finger', 'r1__right_finger', 'cargo_cyan_2_geom')]
    joints = []
    for gid in (left, right):
        bid = int(m.geom_bodyid[gid])
        while m.body_jntnum[bid] == 0:
            bid = int(m.body_parentid[bid])
        joints.append(int(m.jnt_qposadr[m.body_jntadr[bid]]))
    ref = json.loads(a.capacity_reference.read_text())
    # Workspace allocation only: observed C trace + actual import maximum,
    # rounded to a power of two as in simalt3. Overflow checked each step.
    ncon = 1 << (max(int(d.ncon), max(c['max_ncon'] for c in ref['cases']))-1).bit_length()
    njmax = 1 << (max(int(d.nefc), max(c['max_nefc'] for c in ref['cases']))-1).bit_length()
    metadata = {'sha': a.sha, 'script_sha256': digest(__file__), 'engine': a.engine,
                'backend_mode': a.backend_mode, 'host': host, 'mujoco': mujoco.__version__,
                'fixture_sha256': digest(a.fixture/'fixture.npz'),
                'xml_sha256': digest(a.fixture/'scene.xml'), 'case': a.case,
                'dt': dt, 'steps_planned': len(tape), 'columns': COLUMNS,
                'nq': int(m.nq), 'nv': int(m.nv), 'pad_joint_qpos_indices': joints,
                'options': {k: float(getattr(m.opt, k)) for k in
                            ('timestep','solver','cone','integrator','iterations','ls_iterations',
                             'tolerance','noslip_iterations','noslip_tolerance','ccd_iterations','ccd_tolerance')},
                'physics_overrides': {}, 'status': 'running',
                'capacities': {'nconmax': ncon, 'njmax': njmax},
                'reproduce': sys.argv, 'initial_contacts': [
                    {'geoms': [m.geom(int(g)).name for g in c.geom], 'dist': float(c.dist),
                     'dim': int(c.dim), 'friction': c.friction.tolist()} for c in d.contact]}
    metadata['physics_hashes'] = {k: hashlib.sha256(getattr(m,k).tobytes()).hexdigest() for k in
        ('geom_friction','pair_friction','geom_solref','geom_solimp','body_mass','body_inertia',
         'actuator_gainprm','actuator_biasprm','geom_margin','geom_gap','geom_condim')}
    def save():
        (a.out/'result.json').write_text(json.dumps(metadata, indent=2, allow_nan=False)+'\n')
    save()
    total = len(tape)
    records = np.zeros((total, len(COLUMNS)+m.nq+m.nv), dtype=np.float64)
    started = time.perf_counter()
    done = 0
    try:
        if a.engine == 'cpu':
            for t in range(total):
                d.ctrl[:] = tape[t]; mujoco.mj_step(m, d)
                r = records[t]; r[0:2] = [d.ncon, d.nefc]
                r[13:15] = d.qpos[joints]
                for i, c in enumerate(d.contact):
                    g0,g1 = map(int,c.geom)
                    r[12] = min(r[12],c.dist)
                    r[11] += int({int(m.geom_type[g0]),int(m.geom_type[g1])} == {0,7})
                    if box in (g0,g1):
                        for k,gid in enumerate((left,right)):
                            if gid in (g0,g1):
                                force=np.zeros(6); mujoco.mj_contactForce(m,d,i,force)
                                r[3+k]+=1; r[5+k]=min(r[5+k],c.dist)
                                r[7+k]+=force[0]; r[9+k]+=np.linalg.norm(force[1:3])
                                r[15+k]=max(r[15+k],c.dim)
                r[len(COLUMNS):] = np.r_[d.qpos,d.qvel]
                done=t+1
                if done % 4000 == 0:
                    metadata.update(steps_done=done, sim_s=done*dt);save()
        else:
            import warp as wp
            import mujoco_warp as mjw
            from mujoco_warp._src.support import contact_force_fn
            from mujoco_warp._src.types import vec5
            from simalt_physics_compare import unused_efm
            wp.init()
            metadata['warp'] = wp.__version__
            metadata['warp_deterministic'] = str(getattr(wp.config,'deterministic',None))
            wm = mjw.put_model(m)
            # Pinned upstream io.py:433 adjusts to 1e-6 for float32. Match C's
            # original solver configuration; this does not change m.opt.
            wm.opt.tolerance.fill_(float(m.opt.tolerance))
            if a.backend_mode == 'box-sat-v1':
                # Pinned collision_driver.py routes BOX/BOX through CCD by default.
                # The upstream primitive SAT collider is an available alternate
                # collision pipeline, not a change to friction/contact parameters.
                from mujoco_warp._src import collision_driver as cd
                from mujoco_warp._src.types import GeomType, CollisionType
                cd.MJ_COLLISION_TABLE[(GeomType.BOX,GeomType.BOX)] = CollisionType.PRIMITIVE
            with unused_efm(m,d):
                wd=mjw.put_data(m,d,nworld=1,nconmax=ncon,njmax=njmax)
            metadata['capacities'].update(naconmax=int(wd.naconmax), njmax=int(wd.njmax))
            metadata['backend_options'] = {k: (float(getattr(wm.opt,k).numpy().item())
                 if hasattr(getattr(wm.opt,k),'numpy') else float(getattr(wm.opt,k)))
                 for k in metadata['options'] if hasattr(wm.opt,k)}
            save()
            wt=wp.array(tape.astype(np.float32),dtype=wp.float32)
            tick=wp.zeros(1,dtype=wp.int32)
            out=wp.zeros(records.shape,dtype=wp.float32)
            nc=wp.constant(len(COLUMNS)); l=wp.constant(left);rr=wp.constant(right);b=wp.constant(box)
            jl=wp.constant(joints[0]);jr=wp.constant(joints[1])
            @wp.kernel
            def command(tape:wp.array2d[wp.float32], t:wp.array[int], ctrl:wp.array2d[float]):
                for j in range(ctrl.shape[1]):
                    ctrl[0,j]=tape[t[0],j]
            @wp.kernel
            def record(geom_type:wp.array[int], cone:int, naconmax:int, njmax:int,
                       nacon:wp.array[int], nefc:wp.array[int], overflow:wp.array[int],
                       qpos:wp.array2d[float], qvel:wp.array2d[float],
                       geom:wp.array[wp.vec2i], dist:wp.array[float], frame:wp.array[wp.mat33],
                       friction:wp.array[vec5], condim:wp.array[int], adr:wp.array2d[int],
                       adhesion:wp.array[float], efc_force:wp.array2d[float],
                       t:wp.array[int], out:wp.array2d[float]):
                row=t[0]
                out[row,0]=float(nacon[0]);out[row,1]=float(nefc[0])
                out[row,2]=float(overflow[0])
                out[row,13]=qpos[0,jl];out[row,14]=qpos[0,jr]
                for i in range(wp.min(nacon[0],naconmax)):
                    g0=geom[i][0];g1=geom[i][1]
                    out[row,12]=wp.min(out[row,12],dist[i])
                    if ((geom_type[g0]==0 and geom_type[g1]==7) or
                        (geom_type[g0]==7 and geom_type[g1]==0)):
                        out[row,11]+=1.0
                    if g0==b or g1==b:
                        k=int(-1)
                        if g0==l or g1==l:k=0
                        if g0==rr or g1==rr:k=1
                        if k>=0:
                            force=contact_force_fn(cone,frame,friction,
                                condim,adr,adhesion,
                                efc_force,njmax,nacon,0,i,False)
                            out[row,3+k]+=1.0
                            out[row,5+k]=wp.min(out[row,5+k],dist[i])
                            out[row,7+k]+=force[0]
                            out[row,9+k]+=wp.sqrt(force[1]*force[1]+force[2]*force[2])
                            out[row,15+k]=wp.max(out[row,15+k],float(condim[i]))
                for j in range(qpos.shape[1]):out[row,nc+j]=qpos[0,j]
                for j in range(qvel.shape[1]):out[row,nc+qpos.shape[1]+j]=qvel[0,j]
                t[0]=row+1
            def record_inputs(data):
                return [wm.geom_type,wm.opt.cone,data.naconmax,data.njmax,data.nacon,data.nefc,
                        data.overflow,data.qpos,data.qvel,data.contact.geom,data.contact.dist,
                        data.contact.frame,data.contact.friction,data.contact.dim,
                        data.contact.efc_address,data.contact.adhesion,data.efc.force,tick,out]
            # Warm compilation is discarded; replay starts at the same reset.
            wp.launch(command,dim=1,inputs=[wt,tick,wd.ctrl]);mjw.step(wm,wd)
            wp.launch(record,dim=1,inputs=record_inputs(wd));wp.synchronize()
            with unused_efm(m,d):wd=mjw.put_data(m,d,nworld=1,nconmax=ncon,njmax=njmax)
            tick.zero_();out.zero_()
            # Sixteen divides the frozen 400-step control tick; no dt/command change.
            with wp.ScopedCapture() as cap:
                for _ in range(16):
                    wp.launch(command,dim=1,inputs=[wt,tick,wd.ctrl]);mjw.step(wm,wd)
                    wp.launch(record,dim=1,inputs=record_inputs(wd))
            for begin in range(0,total,400):
                for _ in range(25):wp.capture_launch(cap.graph)
                wp.synchronize();done=begin+400
                if np.any(wd.overflow.numpy()):raise RuntimeError('capacity overflow')
                if done % 4000==0:
                    metadata.update(steps_done=done,sim_s=done*dt);save()
            records=out.numpy()
        if not np.isfinite(records[:done]).all():raise RuntimeError('nonfinite step record')
        metadata['status']='complete'
    except KeyboardInterrupt:
        metadata.update(status='cap_end',cap_end=True)
        if a.engine=='warp':records=out.numpy()
    except Exception as error:
        import traceback
        metadata.update(status='HOST_ERROR',error=str(error),traceback=traceback.format_exc())
        if a.engine=='warp' and 'out' in locals():records=out.numpy()
    finally:
        np.savez_compressed(a.out/'steps.npz',records=records[:done])
        # 10Hz evaluator state ring, for C post-hoc rendering, never control input.
        values=records[399:done:400,len(COLUMNS):]
        np.savez_compressed(a.out/'states.npz',**{a.case:values})
        metadata.update(steps_done=done,sim_s=done*dt,wall_s=time.perf_counter()-started,
                        steps_sha256=digest(a.out/'steps.npz'),
                        recording_only=True, online_RGB_ring=False,
                        recording_bytes=(a.out/'steps.npz').stat().st_size)
        save()
    print(json.dumps(metadata,indent=2))


if __name__=='__main__':
    main()
