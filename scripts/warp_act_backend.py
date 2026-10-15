"""Linux gcp2 backend transport for the frozen solo teacher (default OFF).

The scalar teacher is a transitional client. Physics, command relay/interpolation
and RGB are batched. C MjData is a kinematic/raycast perception mirror only;
GPU contact forces have a separate evaluator-only channel.
"""
from collections import defaultdict
import hashlib
import time
from pathlib import Path
import numpy as np
from warp_act_core import SERVOS, control_tape, multi_control_tape, model_key, contact_maps, varying_model_arrays


def ports_for(context):
    return context.get('ports') or {'r1': context['port']}


class Transport:
    native_render = False

    def __init__(self, host, source_sha, backend, out):
        self.host, self.source_sha, self.backend, self.out = host, source_sha, backend, Path(out)
        self.seconds = defaultdict(float)
        self.samples = []
        self.rgb = []
        self.contact_forces = None

    def capture(self, index, world, robot_id='r1'):
        if self.native_render:
            return world.render_jpeg(robot_id=robot_id, camera='robot_cam')
        return self.rgb_by_robot[robot_id][index]

    def record_state(self, index, tick, world):
        if index == 0:
            self.samples.append((tick, world.data.qpos.copy(), world.data.qvel.copy()))

    def forces(self, index, model, data, targets, fingers):
        if not self.native_render:
            channels = [self.finger_channels[g] for g in sorted(fingers, key=fingers.get)]
            return self.contact_forces[index, channels].tolist()
        import mujoco
        result = [0., 0.]
        force = np.zeros(6)
        for i, contact in enumerate(data.contact):
            a, b = map(int, contact.geom)
            finger = a if b in targets else b if a in targets else None
            if finger in fingers:
                mujoco.mj_contactForce(model, data, i, force)
                result[fingers[finger]] += abs(float(force[0]))
        return result

    def save_states(self):
        if self.samples:
            np.savez_compressed(self.out/'world0-states.npz',
                ticks=[s[0] for s in self.samples], qpos=[s[1] for s in self.samples],
                qvel=[s[2] for s in self.samples])


class CTransport(Transport):
    native_render = True

    def step(self, contexts, active):
        start = time.perf_counter()
        for i in np.flatnonzero(active):
            row = contexts[i]
            world, ports = row['world'], ports_for(row)
            until = float(world.data.time)+.1
            for _ in range(round(.1/world.model.opt.timestep)):
                for port in ports.values():
                    port.tick(float(world.data.time))
                world._physics_step_for(world.robot('r1'))
            # The C path itself is unchanged; this transport is a new pilot caller.
        self.seconds['physics_and_command_decode'] += time.perf_counter()-start

    def sync_render(self, contexts):
        pass


class WarpTransport(Transport):
    def initialize(self, contexts, *, compiled_reference=None, compiled_geometry=None, per_world_model_references=None):
        import mujoco
        import warp as wp
        import mujoco_warp as mjw
        from simalt_physics_compare import unused_efm
        from simalt_collision_compat import install_legacy_plane
        from simalt_compiled_compat import apply_reference, apply_geometry
        from sim.masterpi_camera_profile import raw_fisheye_remap, scaled_camera_matrix, CAMERA_FISHEYE_D
        self.wp, self.mjw = wp, mjw
        self.contexts = contexts
        self.n = len(contexts)
        self.robot_ids = tuple(ports_for(contexts[0]))
        if any(tuple(ports_for(c)) != self.robot_ids for c in contexts):
            raise ValueError('consistent named robot ports across worlds required')
        self.camera_size = tuple(contexts[0].get('camera_size', (640, 480)))
        self.finger_channels = dict(contexts[0]['finger_ids'])
        m, d = contexts[0]['world'].model, contexts[0]['world'].data
        self.m, self.dt = m, float(m.opt.timestep)
        xml = self.out/'runtime-scene.xml'
        xml.write_text(contexts[0]['world'].scene_xml)
        self.compat = {}
        refs = per_world_model_references or {}
        models=[]
        for index,c in enumerate(contexts):
            model=c['world'].model
            scene_xml=Path(c.get('scene_xml_path', self.out/f'world-{index:03d}'/'scene.xml'))
            xml_hash=hashlib.sha256(scene_xml.read_bytes()).hexdigest()
            if index==0 or c['world'].scene_xml==contexts[0]['world'].scene_xml:
                actuator_asset,geometry_asset=compiled_reference,compiled_geometry
            elif refs:
                ref=refs.get(xml_hash)
                if ref is None:raise ValueError('missing exact-XML C312 per-world reference: '+xml_hash)
                actuator_asset,geometry_asset=Path(ref['actuator']),Path(ref['geometry'])
            elif model_key(c['world'].scene_xml)==model_key(contexts[0]['world'].scene_xml):
                # Existing same-model mode: only free-joint initial poses vary.
                actuator_asset=geometry_asset=None
                for name in dir(m):
                    if name.startswith(('geom_','mesh_','bvh_')):
                        value=getattr(m,name)
                        if isinstance(value,np.ndarray):getattr(model,name)[:]=value
            else:
                raise ValueError('same static model required; use explicit per-world compiled references')
            compat={}
            if geometry_asset:compat['geometry']=apply_geometry(model,scene_xml,geometry_asset)
            if actuator_asset:compat['damping']=apply_reference(model,scene_xml,actuator_asset)
            if model.opt.noslip_iterations!=10 or np.any(c['world'].data.eq_active):
                raise ValueError('noslip10 / weld OFF required in every world')
            self.compat[str(index)]=compat
            models.append(model)
        wp.init()
        if refs:
            self.wm,self.model_batch_audit=self.combine_models(models)
        else:
            self.wm=mjw.put_model(m)
            self.model_batch_audit={'mode':'same_static_model','varying_fields':[]}
        self.wm.opt.tolerance.fill_(float(m.opt.tolerance))
        if self.wm.opt.noslip_iterations != 10:
            raise RuntimeError('noslip lost in Warp conversion')
        self.compat['collision'] = install_legacy_plane(m)
        # Existing simalt4 dense trace observed max nefc134, rounded to256.
        # Full scene import is added; these are workspace sizes, not physics changes.
        ncon = 1 << (max(32, max(int(c['world'].data.ncon) for c in contexts))-1).bit_length()
        njmax = 1 << (max(256, max(int(c['world'].data.nefc) for c in contexts))-1).bit_length()
        with unused_efm(m, d):
            self.wd = mjw.put_data(m,d,nworld=self.n,nconmax=ncon,njmax=njmax)
        self.copy_initial_state(contexts)
        self.origin = float(d.time)
        self.tick = 0
        self.relay_state = np.zeros((self.n,4), int)
        self.robot_relay_states = {rid: np.zeros((self.n, 4), int) for rid in self.robot_ids}
        self.tape = wp.zeros((round(.1/self.dt),self.n,m.nu),dtype=float)
        self.graph_tick = wp.zeros(1,dtype=int)
        self.force_out = wp.zeros((self.n,len(self.finger_channels)),dtype=float)
        self.init_kernels(contexts)
        # Compile once, then discard the warm-up state before any rollout.
        mjw.step(self.wm,self.wd); wp.synchronize()
        with unused_efm(m,d):
            self.wd = mjw.put_data(m,d,nworld=self.n,nconmax=ncon,njmax=njmax)
        self.copy_initial_state(contexts)
        # Capture exactly the 400 physics ticks, not a host wall budget.
        with wp.ScopedCapture() as capture:
            for _ in range(16):
                wp.launch(self.command_kernel, dim=(self.n,m.nu),inputs=[self.tape,self.graph_tick,self.wd.ctrl])
                mjw.step(self.wm,self.wd)
                wp.launch(self.advance_kernel,dim=1,inputs=[self.graph_tick])
        self.graph = capture.graph
        # Capture does not run the physics. First render uses canonical initialized state.
        width, height = self.camera_size
        self.rc = mjw.create_render_context(m,nworld=self.n,cam_res=self.camera_size,
            render_rgb=True,render_depth=False,render_seg=False,use_textures=True,
            use_shadows=True,enabled_geom_groups=[0,1,2,3],cam_active=[r+'__robot_cam' for r in self.robot_ids])
        self.device_rgb = wp.zeros((self.n,height,width),dtype=wp.vec3)
        self.mx,self.my = raw_fisheye_remap(width,height)
        self.camera = dict(resolution=list(self.camera_size),robots=list(self.robot_ids),hz=10,K=scaled_camera_matrix(width,height).tolist(),
            D=list(CAMERA_FISHEYE_D),mount_pos=m.cam_pos[m.camera('r1__robot_cam').id].tolist(),
            mount_quat=m.cam_quat[m.camera('r1__robot_cam').id].tolist(),
            remap_sha256=hashlib.sha256(self.mx.tobytes()+self.my.tobytes()).hexdigest(),
            renderer='MJWarp batch RGB; known partial-alpha difference from C remains')
        self.capacities = dict(nconmax=ncon,njmax=njmax,naconmax=int(self.wd.naconmax))
        self.bindings = {}
        for rid in self.robot_ids:
            self.build_lookup(contexts[0]['world'].robot(rid))
            self.bindings[rid] = dict(lookup=self.lookup, wheel_ids=self.wheel_ids, servo_ids=self.servo_ids)
        self.sync_render(contexts)

    def copy_initial_state(self, contexts):
        wp=self.wp
        # mjSTATE_INTEGRATION owners; derived contacts/kinematics are recomputed.
        for name in ('qpos','qvel','act','ctrl','qacc_warmstart','qfrc_applied',
                     'xfrc_applied','mocap_pos','mocap_quat','eq_active','time'):
            target=getattr(self.wd,name,None)
            if target is None or not isinstance(target,wp.array):continue
            values=np.stack([np.asarray(getattr(c['world'].data,name)) for c in contexts])
            if values.size:wp.copy(target,wp.array(values,dtype=target.dtype))

    def combine_models(self, models):
        """Use the pinned API's '*' fields, including nested model statistics.

        Every differing converted array must explicitly support batching. Scalar
        or topology differences fail closed; no hidden object mass is discarded.
        """
        import dataclasses
        from mujoco_warp._src import warp_util
        wp,mjw=self.wp,self.mjw
        converted=[mjw.put_model(model) for model in models]
        arrays=[];batchable=set();objects=[];scalars=[]
        def flatten(obj,prefix='',result=None,locations=None,scalar=None):
            result={} if result is None else result
            locations={} if locations is None else locations
            scalar={} if scalar is None else scalar
            for field in dataclasses.fields(obj):
                value=getattr(obj,field.name)
                name=prefix+field.name
                if dataclasses.is_dataclass(value):
                    flatten(value,name+'.',result,locations,scalar)
                elif isinstance(value,wp.array):
                    result[name]=value.numpy();locations[name]=(obj,field.name,value.dtype)
                    if getattr(field.type,'shape',())[:1]==('*',):batchable.add(name)
                elif isinstance(value,(int,float,bool,str,type(None))):scalar[name]=value
            return result,locations,scalar
        for obj in converted:
            arr,loc,scalar=flatten(obj);arrays.append(arr);objects.append(loc);scalars.append(scalar)
        if any(scalar!=scalars[0] for scalar in scalars[1:]):
            raise ValueError('converted model scalar/topology/options differ')
        changed=varying_model_arrays(arrays,batchable)
        result=converted[0]
        for name,values in changed.items():
            obj,field,dtype=objects[0][name]
            setattr(obj,field,wp.array(values,dtype=dtype))
        warp_util.mark_batched(result)
        return result,{'mode':'per_world_model_v1','varying_fields':sorted(changed),
            'worlds':len(models),'all_unsupported_arrays_exact':True,
            'world_array_sha256':{k:hashlib.sha256(v.tobytes()).hexdigest() for k,v in changed.items()},
            'basis':'pinned MJWarp io.put_model batchable * fields; no parameter approximation'}

    def init_kernels(self, contexts):
        # No state/force is passed into command decoding or teacher objects.
        wp = self.wp
        from mujoco_warp._src.support import contact_force_fn
        from mujoco_warp._src.types import vec5
        @wp.kernel
        def command(tape:wp.array3d[float],tick:wp.array[int],ctrl:wp.array2d[float]):
            w,j=wp.tid()
            ctrl[w,j]=tape[tick[0],w,j]
        @wp.kernel
        def advance(tick:wp.array[int]):
            tick[0]+=1
        targets, fingers = contact_maps(contexts[0]['world'].model.ngeom,
            [c['gids'] for c in contexts], [c['finger_ids'] for c in contexts])
        self.target_mask = wp.array(targets, dtype=int)
        self.finger_map = wp.array(fingers, dtype=int)
        @wp.kernel
        def evaluate(nacon:wp.array[int],worldid:wp.array[int],geom:wp.array[wp.vec2i],
                     cone:int,njmax:int,frame:wp.array[wp.mat33],friction:wp.array[vec5],
                     condim:wp.array[int],adr:wp.array2d[int],adhesion:wp.array[float],
                     efc_force:wp.array2d[float],targets:wp.array2d[int],fingers:wp.array2d[int],out:wp.array2d[float]):
            i=wp.tid()
            if i<nacon[0]:
                a,b=geom[i][0],geom[i][1]
                w=worldid[i]
                k=int(-1)
                if targets[w,a] != 0:k=fingers[w,b]
                elif targets[w,b] != 0:k=fingers[w,a]
                if k>=0:
                    w=worldid[i]
                    force=contact_force_fn(cone,frame,friction,condim,adr,adhesion,efc_force,njmax,nacon,w,i,False)
                    wp.atomic_add(out,w,k,wp.abs(force[0]))
        self.command_kernel,self.advance_kernel,self.eval_kernel=command,advance,evaluate

    def build_lookup(self, robot):
        self.wheel_ids=robot.wheel_act
        self.servo_ids=[]
        tables=[]
        for servo,key in zip(SERVOS,('gripper','wrist','elbow','shoulder','yaw')):
            ids=list(robot.gripper_act) if key=='gripper' else [robot.servo_act[key]]
            joints=list(robot.gripper_joint) if key=='gripper' else [robot.arm_joint[key]]
            limits=[tuple(robot.model.jnt_range[j]) if robot.model.jnt_limited[j] else (-np.inf,np.inf) for j in joints]
            if len(set(limits))!=1:
                raise ValueError('nonidentical finger limits require separate lookup tables')
            tables.append([np.clip(robot.pulse_to_joint_targets({servo:p})[key],*limits[0]) for p in range(500,2501)])
            self.servo_ids.append(ids)
        self.lookup=np.asarray(tables)

    def step(self, contexts, active):
        wp,mjw=self.wp,self.mjw
        start=time.perf_counter()
        robot_rows = {}
        for rid in self.robot_ids:
            rows=[]
            for i,c in enumerate(contexts):
                p,w=ports_for(c)[rid],c['world']
                rows.append(dict(ctrl=w.data.ctrl.copy(),wheels=p._motor_commands if active[i] else [0.]*4,
                deadlines=[v or 0. for v in p._wheel_deadlines],
                applied=[p._servo_applied[s] for s in SERVOS],
                target=[p._servo_targets.get(s,p._servo_applied[s]) for s in SERVOS],
                servo_active=[s in p._servo_targets for s in SERVOS],
                    now=self.origin+self.tick*.1,servo_time=p._servo_tick_time))
            robot_rows[rid] = rows
        params=contexts[0]['world'].drive_parameters
        tape,states=multi_control_tape(robot_rows,self.robot_relay_states,self.bindings,dt=self.dt,steps=round(.1/self.dt),
            start_fraction=params.start_fraction,kinetic_fraction=params.kinetic_fraction,
            torque_cap_nm=params.torque_cap_nm)
        self.robot_relay_states={rid: state['relay'] for rid, state in states.items()}
        self.relay_state=self.robot_relay_states.get('r1')
        wp.copy(self.tape,wp.array(tape,dtype=float))
        for i,c in enumerate(contexts):
            w=c['world']
            for rid, state in states.items():
                p=ports_for(c)[rid]
                p._servo_applied=dict(zip(SERVOS,state['applied'][i]))
                p._servo_targets={s:int(state['target'][i,k]) for k,s in enumerate(SERVOS) if state['servo_active'][i,k]}
                p._servo_tick_time=float(state['servo_time'][i])
                p._motor_commands=tuple(state['wheels'][i])
                p._wheel_deadlines=[d if d is not None and d>p._servo_tick_time else None for d in p._wheel_deadlines]
                w.robot(rid).servo_command_pulses.update(dict(zip(SERVOS,map(int,state['pwm'][i]))))
            w.data.ctrl[:]=tape[-1,i]
        self.seconds['command_decode_upload']+=time.perf_counter()-start
        start=time.perf_counter()
        self.graph_tick.zero_()
        for _ in range(round(.1/self.dt)//16):
            wp.capture_launch(self.graph)
        wp.synchronize()
        self.tick+=1
        self.seconds['physics']+=time.perf_counter()-start
        if np.any(self.wd.overflow.numpy()):
            raise RuntimeError('MJWarp workspace overflow '+str(self.wd.overflow.numpy().tolist()))
        self.sync_render(contexts)

    def sync_render(self, contexts):
        import cv2
        import io
        from PIL import Image
        import mujoco
        wp,mjw=self.wp,self.mjw
        start=time.perf_counter()
        # Refresh post-integration transforms, matching simalt3 RGB path.
        mjw.kinematics(self.wm,self.wd)
        mjw.camlight(self.wm,self.wd)
        mjw.refit_bvh(self.wm,self.wd,self.rc)
        mjw.render(self.wm,self.wd,self.rc)
        wp.synchronize()
        self.seconds['render']+=time.perf_counter()-start
        start=time.perf_counter()
        self.rgb_by_robot = {}
        for camera_index, rid in enumerate(self.robot_ids):
            mjw.get_rgb(self.rc,camera_index,self.device_rgb)
            wp.synchronize()
            image=np.clip(self.device_rgb.numpy()*255,0,255).astype(np.uint8)
            encoded = []
            for frame in image:
                rgb=cv2.remap(frame,self.mx,self.my,cv2.INTER_LINEAR,borderMode=cv2.BORDER_CONSTANT)
                buffer=io.BytesIO()
                Image.fromarray(rgb).save(buffer,format='JPEG',quality=82)  # same frozen native JPEG writer
                encoded.append(buffer.getvalue())
            self.rgb_by_robot[rid] = encoded
        qpos,qvel=self.wd.qpos.numpy(),self.wd.qvel.numpy()
        if not np.isfinite(qpos).all() or not np.isfinite(qvel).all():
            raise RuntimeError('nonfinite Warp state')
        self.rgb=self.rgb_by_robot.get('r1', [])
        for i,c in enumerate(contexts):

            d=c['world'].data
            d.qpos[:]=qpos[i];d.qvel[:]=qvel[i];d.time=self.origin+self.tick*.1
            # Perception mirror only, no C physics or C contact-force reconstruction.
            mujoco.mj_kinematics(c['world'].model,d)
            mujoco.mj_camlight(c['world'].model,d)
        self.seconds['readback_remap_jpeg_kinematics']+=time.perf_counter()-start
        self.force_out.zero_()
        d=self.wd
        wp.launch(self.eval_kernel,dim=d.naconmax,inputs=[d.nacon,d.contact.worldid,d.contact.geom,
            int(self.m.opt.cone),int(d.njmax),d.contact.frame,d.contact.friction,d.contact.dim,
            d.contact.efc_address,d.contact.adhesion,d.efc.force,self.target_mask,self.finger_map,self.force_out])
        self.contact_forces=self.force_out.numpy()
