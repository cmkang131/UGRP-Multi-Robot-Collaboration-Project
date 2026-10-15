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
from warp_act_core import SERVOS, control_tape


class Transport:
    native_render = False

    def __init__(self, host, source_sha, backend, out):
        self.host, self.source_sha, self.backend, self.out = host, source_sha, backend, Path(out)
        self.seconds = defaultdict(float)
        self.samples = []
        self.rgb = []
        self.contact_forces = None

    def capture(self, index, world):
        if self.native_render:
            return world.render_jpeg(robot_id='r1', camera='robot_cam')
        return self.rgb[index]

    def record_state(self, index, tick, world):
        if index == 0:
            self.samples.append((tick, world.data.qpos.copy(), world.data.qvel.copy()))

    def forces(self, index, model, data, targets, fingers):
        if not self.native_render:
            return self.contact_forces[index].tolist()
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
            world, port = row['world'], row['port']
            until = float(world.data.time)+.1
            for _ in range(round(.1/world.model.opt.timestep)):
                port.tick(float(world.data.time))
                world._physics_step_for(world.robot('r1'))
            # The C path itself is unchanged; this transport is a new pilot caller.
        self.seconds['physics_and_command_decode'] += time.perf_counter()-start

    def sync_render(self, contexts):
        pass


class WarpTransport(Transport):
    def initialize(self, contexts, *, compiled_reference=None, compiled_geometry=None):
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
        m, d = contexts[0]['world'].model, contexts[0]['world'].data
        self.m, self.dt = m, float(m.opt.timestep)
        xml = self.out/'runtime-scene.xml'
        xml.write_text(contexts[0]['world'].scene_xml)
        self.compat = {}
        if compiled_geometry:
            self.compat['geometry'] = apply_geometry(m, xml, compiled_geometry)
        if compiled_reference:
            self.compat['damping'] = apply_reference(m, xml, compiled_reference)
        if m.opt.noslip_iterations != 10 or np.any(d.eq_active):
            raise ValueError('noslip10 / weld OFF required')
        # This initial implementation admits replicated SAME-model starts only.
        # Mixed scene batching requires explicit per-model grouping, not silent sharing.
        for c in contexts[1:]:
            other = c['world']
            if other.scene_xml != contexts[0]['world'].scene_xml:
                raise ValueError('same-model batch required; scene XML differs')
        wp.init()
        self.wm = mjw.put_model(m)
        self.wm.opt.tolerance.fill_(float(m.opt.tolerance))
        if self.wm.opt.noslip_iterations != 10:
            raise RuntimeError('noslip lost in Warp conversion')
        self.compat['collision'] = install_legacy_plane(m)
        # Existing simalt4 dense trace observed max nefc134, rounded to256.
        # Full scene import is added; these are workspace sizes, not physics changes.
        ncon = 1 << (max(32, int(d.ncon))-1).bit_length()
        njmax = 1 << (max(256, int(d.nefc))-1).bit_length()
        with unused_efm(m, d):
            self.wd = mjw.put_data(m,d,nworld=self.n,nconmax=ncon,njmax=njmax)
        wp.copy(self.wd.qpos, wp.array(np.stack([c['world'].data.qpos for c in contexts]).astype(np.float32), dtype=float))
        wp.copy(self.wd.qvel, wp.array(np.stack([c['world'].data.qvel for c in contexts]).astype(np.float32), dtype=float))
        self.origin = float(d.time)
        self.tick = 0
        self.relay_state = np.zeros((self.n,4), int)
        self.tape = wp.zeros((round(.1/self.dt),self.n,m.nu),dtype=float)
        self.graph_tick = wp.zeros(1,dtype=int)
        self.force_out = wp.zeros((self.n,2),dtype=float)
        self.init_kernels(contexts)
        # Compile once, then discard the warm-up state before any rollout.
        mjw.step(self.wm,self.wd); wp.synchronize()
        with unused_efm(m,d):
            self.wd = mjw.put_data(m,d,nworld=self.n,nconmax=ncon,njmax=njmax)
        # Capture exactly the 400 physics ticks, not a host wall budget.
        with wp.ScopedCapture() as capture:
            for _ in range(16):
                wp.launch(self.command_kernel, dim=(self.n,m.nu),inputs=[self.tape,self.graph_tick,self.wd.ctrl])
                mjw.step(self.wm,self.wd)
                wp.launch(self.advance_kernel,dim=1,inputs=[self.graph_tick])
        self.graph = capture.graph
        # Capture does not run the physics. First render uses canonical initialized state.
        self.rc = mjw.create_render_context(m,nworld=self.n,cam_res=(640,480),
            render_rgb=True,render_depth=False,render_seg=False,use_textures=True,
            use_shadows=True,enabled_geom_groups=[0,1,2,3],cam_active=['r1__robot_cam'])
        self.device_rgb = wp.zeros((self.n,480,640),dtype=wp.vec3)
        self.mx,self.my = raw_fisheye_remap(640,480)
        self.camera = dict(resolution=[640,480],hz=10,K=scaled_camera_matrix(640,480).tolist(),
            D=list(CAMERA_FISHEYE_D),mount_pos=m.cam_pos[m.camera('r1__robot_cam').id].tolist(),
            mount_quat=m.cam_quat[m.camera('r1__robot_cam').id].tolist(),
            remap_sha256=hashlib.sha256(self.mx.tobytes()+self.my.tobytes()).hexdigest(),
            renderer='MJWarp batch RGB; known partial-alpha difference from C remains')
        self.capacities = dict(nconmax=ncon,njmax=njmax,naconmax=int(self.wd.naconmax))
        self.build_lookup(contexts[0]['world'].robot('r1'))
        self.sync_render(contexts)

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
        target = wp.constant(contexts[0]['gids'][0])
        if len(contexts[0]['gids']) != 1:
            raise ValueError('warp1 evaluator currently supports the single box collision geom only')
        fingers = sorted(contexts[0]['finger_ids'],key=contexts[0]['finger_ids'].get)
        left,right=wp.constant(fingers[0]),wp.constant(fingers[1])
        @wp.kernel
        def evaluate(nacon:wp.array[int],worldid:wp.array[int],geom:wp.array[wp.vec2i],
                     cone:int,njmax:int,frame:wp.array[wp.mat33],friction:wp.array[vec5],
                     condim:wp.array[int],adr:wp.array2d[int],adhesion:wp.array[float],
                     efc_force:wp.array2d[float],out:wp.array2d[float]):
            i=wp.tid()
            if i<nacon[0]:
                a,b=geom[i][0],geom[i][1]
                k=int(-1)
                if a==target or b==target:
                    if a==left or b==left:k=0
                    if a==right or b==right:k=1
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
        rows=[]
        for i,c in enumerate(contexts):
            p,w=c['port'],c['world']
            rows.append(dict(ctrl=w.data.ctrl.copy(),wheels=p._motor_commands if active[i] else [0.]*4,
                deadlines=[v or 0. for v in p._wheel_deadlines],
                applied=[p._servo_applied[s] for s in SERVOS],
                target=[p._servo_targets.get(s,p._servo_applied[s]) for s in SERVOS],
                servo_active=[s in p._servo_targets for s in SERVOS],
                now=self.origin+self.tick*.1,servo_time=p._servo_tick_time))
        params=contexts[0]['world'].drive_parameters
        tape,state=control_tape(rows,self.relay_state,dt=self.dt,steps=round(.1/self.dt),
            lookup=self.lookup,wheel_ids=self.wheel_ids,servo_ids=self.servo_ids,
            start_fraction=params.start_fraction,kinetic_fraction=params.kinetic_fraction,
            torque_cap_nm=params.torque_cap_nm)
        self.relay_state=state['relay']
        wp.copy(self.tape,wp.array(tape,dtype=float))
        for i,c in enumerate(contexts):
            p,w=c['port'],c['world']
            p._servo_applied=dict(zip(SERVOS,state['applied'][i]))
            p._servo_targets={s:int(state['target'][i,k]) for k,s in enumerate(SERVOS) if state['servo_active'][i,k]}
            p._servo_tick_time=float(state['servo_time'][i])
            p._motor_commands=tuple(state['wheels'][i])
            p._wheel_deadlines=[d if d is not None and d>p._servo_tick_time else None for d in p._wheel_deadlines]
            w.data.ctrl[:]=tape[-1,i]
            w.robot('r1').servo_command_pulses.update(dict(zip(SERVOS,map(int,state['pwm'][i]))))
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
        import mujoco
        wp,mjw=self.wp,self.mjw
        start=time.perf_counter()
        # Refresh post-integration transforms, matching simalt3 RGB path.
        mjw.kinematics(self.wm,self.wd)
        mjw.camlight(self.wm,self.wd)
        mjw.refit_bvh(self.wm,self.wd,self.rc)
        mjw.render(self.wm,self.wd,self.rc)
        mjw.get_rgb(self.rc,0,self.device_rgb)
        wp.synchronize()
        self.seconds['render']+=time.perf_counter()-start
        start=time.perf_counter()
        image=np.clip(self.device_rgb.numpy()*255,0,255).astype(np.uint8)
        qpos,qvel=self.wd.qpos.numpy(),self.wd.qvel.numpy()
        if not np.isfinite(qpos).all() or not np.isfinite(qvel).all():
            raise RuntimeError('nonfinite Warp state')
        self.rgb=[]
        for i,c in enumerate(contexts):
            rgb=cv2.remap(image[i],self.mx,self.my,cv2.INTER_LINEAR,borderMode=cv2.BORDER_CONSTANT)
            ok,jpg=cv2.imencode('.jpg',cv2.cvtColor(rgb,cv2.COLOR_RGB2BGR))
            if not ok:raise RuntimeError('JPEG encode failed')
            self.rgb.append(jpg.tobytes())
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
            d.contact.efc_address,d.contact.adhesion,d.efc.force,self.force_out])
        self.contact_forces=self.force_out.numpy()
