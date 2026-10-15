"""Linux gcp2 backend transport for the frozen solo teacher (default OFF).

The scalar teacher is a transitional client. Physics, command relay/interpolation
and RGB are batched. C MjData is a kinematic/raycast perception mirror only;
GPU contact forces have a separate evaluator-only channel.
"""
from collections import defaultdict
import copy
import json
import threading
import hashlib
import time
from pathlib import Path
import numpy as np
from warp_act_core import SERVOS, control_tape, model_key, varying_model_arrays, masked_restore, sleep_scene_xml, runtime_sleep_policy


class PerceptionWorld:
    """Independent C kinematic mirror; no C step/render capability.

    Native MjData.__copy__ copies state buffers. A runtime alias check also
    verifies that assumption on the installed binding before any rollout.
    Static model/indices are shared only for the exact same setup plan.
    """
    def __init__(self, prototype):
        self.model=prototype.model
        self.data=copy.copy(prototype.data)
        self.drive_parameters=prototype.drive_parameters
        self.scene_xml=prototype.scene_xml
        self.seed=prototype.seed
        self.physics_lock=threading.RLock()
        for name in ('qpos','qvel','ctrl','act','qacc_warmstart','qfrc_applied','xfrc_applied'):
            a,b=getattr(prototype.data,name,None),getattr(self.data,name,None)
            if isinstance(a,np.ndarray) and a.size and np.shares_memory(a,b):
                raise RuntimeError('per-world MjData alias: '+name)
            if isinstance(a,np.ndarray) and not np.array_equal(a,b):
                raise RuntimeError('native initial-state copy differs: '+name)
        self.controllers={}
        for rid,original in prototype.controllers.items():
            controller=copy.copy(original)
            controller.model=self.model;controller.data=self.data;controller._owner=self
            for name,value in vars(original).items():
                if isinstance(value,np.ndarray):setattr(controller,name,value.copy())
            controller.servo_command_pulses=dict(original.servo_command_pulses)
            self.controllers[rid]=controller

    def robot(self,rid='r1'):
        return self.controllers[rid]

    def _physics_step_for(self,*args,**kwargs):
        raise RuntimeError('C physics forbidden in the GPU perception mirror')

    def close(self):
        pass  # shared immutable model belongs to the prototype owner


class Transport:
    native_render = False

    def __init__(self, host, source_sha, backend, out, *, native_sleep_policy_compat_v1=False):
        self.host, self.source_sha, self.backend, self.out = host, source_sha, backend, Path(out)
        self.seconds = defaultdict(float)
        self.samples = []
        self.rgb = []
        self.contact_forces = None
        self.prototypes={}
        self.prototype_hits=0
        self.native_sleep_policy_compat_v1=native_sleep_policy_compat_v1

    def make_world(self, plan, scene, factory, bind_camera, **kwargs):
        if self.native_sleep_policy_compat_v1:
            original_transform,original_setup=scene.robot_transform,scene.setup
            def transform(xml,**settings):
                return sleep_scene_xml(original_transform(xml,**settings),plan['robot_id'])
            def setup(world):
                # Native documented -0.0 wake sentinel during setup placement.
                world.data.qfrc_applied[:]=-0.0
                original_setup(world)
                world.data.qfrc_applied[:]=0.0
                # Reuse Scene.setup's existing .4s folded-settle duration.
                # Extra quiet setup is not a success threshold or policy input.
                for _ in range(round(.4/world.model.opt.timestep)):
                    world._physics_step_for(world.robot(plan['robot_id']))
            scene.robot_transform,scene.setup=transform,setup
            scene.manifest['native_sleep_policy_compat_v1']={'active_robot':'never sleeps','other_free_bodies':'native allowed; collision wakes normally',
                'extra_quiet_setup_s':.4,'mass_friction_dt_unchanged':True}
        if self.native_render:
            world=factory(scene,**kwargs)
            for controller in world.controllers.values():bind_camera(controller)
            scene.setup(world)
            return world,scene
        key=hashlib.sha256(json.dumps(plan,sort_keys=True).encode()).hexdigest()
        if key not in self.prototypes:
            prototype=factory(scene,**kwargs)
            for controller in prototype.controllers.values():bind_camera(controller)
            scene.setup(prototype)
            self.prototypes[key]=(prototype,copy.deepcopy(scene))
        else:self.prototype_hits+=1
        prototype,saved_scene=self.prototypes[key]
        world=PerceptionWorld(prototype)
        # Refresh the copied controller closures against its own native data.
        sleep_state=prototype.data.tree_asleep.copy()
        for controller in world.controllers.values():bind_camera(controller)
        # mj_forward/kinematics may reset native sleep bookkeeping. Preserve
        # the actual settled state for put_data; no native stepping follows.
        world.data.tree_asleep[:]=sleep_state
        return world,copy.deepcopy(saved_scene)

    def close(self):
        for world,scene in self.prototypes.values():world.close()

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
    def initialize(self, contexts, *, compiled_reference=None, compiled_geometry=None, per_world_model_references=None, float32_solver_default_v1=False):
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
        refs = per_world_model_references or {}
        models=[]
        for index,c in enumerate(contexts):
            model=c['world'].model
            scene_xml=self.out/f'world-{index:03d}'/'scene.xml'
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
            if self.native_sleep_policy_compat_v1:
                enum=mujoco.mjtSleepPolicy
                original=model.tree_sleep_policy.copy()
                mapped=runtime_sleep_policy(original,auto=int(enum.mjSLEEP_AUTO),
                    auto_never=int(enum.mjSLEEP_AUTO_NEVER),auto_allowed=int(enum.mjSLEEP_AUTO_ALLOWED),
                    never=int(enum.mjSLEEP_NEVER),allowed=int(enum.mjSLEEP_ALLOWED))
                model.tree_sleep_policy[:]=mapped
                compat['sleep_policy']={'original':original.tolist(),'runtime_equivalent':mapped.tolist(),
                    'basis':'C3.16 engine_sleep.c125-126; pinned MJWarp sleep.py290-292; INIT rejected'}
            self.compat[str(index)]=compat
            models.append(model)
        wp.init()
        if refs:
            self.wm,self.model_batch_audit=self.combine_models(models)
        else:
            self.wm=mjw.put_model(m)
            self.model_batch_audit={'mode':'same_static_model','varying_fields':[]}
        upstream_tolerance=float(self.wm.opt.tolerance.numpy().item())
        if not float32_solver_default_v1:
            self.wm.opt.tolerance.fill_(float(m.opt.tolerance))
        self.solver_numerics={'profile':'float32_solver_default_v1' if float32_solver_default_v1 else 'source_tolerance',
            'source_tolerance':float(m.opt.tolerance),'upstream_tolerance':upstream_tolerance,
            'effective_tolerance':float(self.wm.opt.tolerance.numpy().item()),
            'basis':'pinned io.py433 clamps float64 C tolerance to minimum1e-6 to avoid float32 needless iterations; task Score unchanged'}
        self.solver_samples=[]
        if self.wm.opt.noslip_iterations != 10:
            raise RuntimeError('noslip lost in Warp conversion')
        self.compat['collision'] = install_legacy_plane(m)
        # Existing simalt4 dense trace observed max nefc134, rounded to256.
        # Full scene import is added; these are workspace sizes, not physics changes.
        ncon = 1 << (max(32, int(d.ncon))-1).bit_length()
        njmax = 1 << (max(256, int(d.nefc))-1).bit_length()
        self.source_sleep=np.stack([c['world'].data.tree_asleep.copy() for c in contexts])
        self.dof_tree=np.asarray(m.body_treeid[m.dof_bodyid])
        native_active=np.sum(self.source_sleep[:,self.dof_tree]<0,axis=1)
        active_bounds=[]
        for c in contexts:
            robot_tree=int(m.body_treeid[m.body('r1__robot').id])
            cargo_tree=int(m.body_treeid[m.geom_bodyid[c['gids'][0]]])
            active_bounds.append(int(np.count_nonzero(np.isin(self.dof_tree,[robot_tree,cargo_tree]))))
        bound=max(int(native_active.max()),max(active_bounds))
        self.nvmax=min(int(m.nv),1 << (max(1,bound)-1).bit_length()) if self.native_sleep_policy_compat_v1 else None
        self.sleep_audit={'enabled':self.native_sleep_policy_compat_v1,'native_initial_active_dofs':native_active.tolist(),
            'active_robot_plus_target_dofs':active_bounds,'nvmax':self.nvmax,
            'capacity_basis':'next power of2 of actual native active count and static robot+target DOFs; overflow rejects unexpected activation'}
        d.tree_asleep[:]=self.source_sleep[0]
        with unused_efm(m, d):
            self.wd = mjw.put_data(m,d,nworld=self.n,nconmax=ncon,njmax=njmax,nvmax=self.nvmax)
        self.copy_initial_state(contexts)
        self.origin = float(d.time)
        self.tick = 0
        self.relay_state = np.zeros((self.n,4), int)
        self.tape = wp.zeros((round(.1/self.dt),self.n,m.nu),dtype=float)
        self.graph_tick = wp.zeros(1,dtype=int)
        self.force_out = wp.zeros((self.n,2),dtype=float)
        self.init_kernels(contexts)
        # Compile once, then discard the warm-up state before any rollout.
        mjw.step(self.wm,self.wd); wp.synchronize()
        d.tree_asleep[:]=self.source_sleep[0]
        with unused_efm(m,d):
            self.wd = mjw.put_data(m,d,nworld=self.n,nconmax=ncon,njmax=njmax,nvmax=self.nvmax)
        self.copy_initial_state(contexts)
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
        self.capacities = dict(nconmax=ncon,njmax=njmax,naconmax=int(self.wd.naconmax),nvmax=int(self.wd.nvmax))
        self.build_lookup(contexts[0]['world'].robot('r1'))
        self.sync_render(contexts)

    def copy_initial_state(self, contexts):
        wp=self.wp
        self.initial_state={}
        # mjSTATE_INTEGRATION owners; derived contacts/kinematics are recomputed.
        for name in ('qpos','qvel','act','ctrl','qacc_warmstart','qfrc_applied',
                     'xfrc_applied','mocap_pos','mocap_quat','eq_active','time'):
            target=getattr(self.wd,name,None)
            if target is None or not isinstance(target,wp.array):continue
            values=np.stack([np.asarray(getattr(c['world'].data,name)) for c in contexts])
            if values.size:
                converted=wp.array(values,dtype=target.dtype)
                wp.copy(target,converted)
                self.initial_state[name]=converted.numpy().copy()
        for name,values in [('tree_asleep',self.source_sleep),('tree_awake',(self.source_sleep<0).astype(np.int32))]:
            target=getattr(self.wd,name)
            wp.copy(target,wp.array(values,dtype=target.dtype))
            self.initial_state[name]=target.numpy().copy()

    def initial_state_proof(self, contexts):
        expected=self.initial_state['qpos']
        actual=self.wd.qpos.numpy()
        if not np.array_equal(actual,expected):
            raise RuntimeError('P1: world-specific initial qpos lost after warmup')
        rows=[]
        folder=self.out/'first-rgb';folder.mkdir(exist_ok=True)
        for i,jpg in enumerate(self.rgb):
            (folder/f'world-{i:03d}.jpg').write_bytes(jpg)
            rows.append(dict(world=i,qpos_match=True,
                expected_qpos_sha256=hashlib.sha256(expected[i].tobytes()).hexdigest(),
                actual_qpos_sha256=hashlib.sha256(actual[i].tobytes()).hexdigest(),
                first_rgb_sha256=hashlib.sha256(jpg).hexdigest()))
        return dict(stage='after warmup reset and first batch RGB, before any teacher action',
            expected_unique_qpos=len({r['expected_qpos_sha256'] for r in rows}),
            measured_unique_qpos=len({r['actual_qpos_sha256'] for r in rows}),
            first_rgb_unique=len({r['first_rgb_sha256'] for r in rows}),rows=rows)

    def reset_physics_worlds(self, mask):
        # Frontend teacher/history resets are a separate caller responsibility.
        # This method is used only by the explicit pre-rollout diagnostic here.
        wp=self.wp
        current={name:getattr(self.wd,name).numpy() for name in self.initial_state}
        restored=masked_restore(current,self.initial_state,np.asarray(mask))
        checks={}
        for name,value in restored.items():
            target=getattr(self.wd,name)
            wp.copy(target,wp.array(value,dtype=target.dtype))
            after=target.numpy()
            checks[name]=dict(selected_match=bool(np.array_equal(after[mask],self.initial_state[name][mask])),
                untouched_match=bool(np.array_equal(after[~mask],current[name][~mask])))
        self.relay_state[mask]=0
        if not all(c['selected_match'] and c['untouched_match'] for c in checks.values()):
            raise RuntimeError('per-world reset changed untouched integration state')
        return dict(mask=np.asarray(mask).tolist(),fields=checks,
            scope='persistent physics integration + relay state only; no mid-episode teacher reset claim')

    def combine_models(self, models):
        """Use the pinned API's '*' fields, including nested model statistics.

        Every differing converted array must explicitly support batching. Scalar
        or topology differences fail closed; no hidden object mass is discarded.
        """
        import dataclasses
        from mujoco_warp._src import warp_util
        wp,mjw=self.wp,self.mjw
        converted_cache={}
        for model in models:
            if id(model) not in converted_cache:converted_cache[id(model)]=mjw.put_model(model)
        converted=[converted_cache[id(model)] for model in models]
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
        if any(len(c['gids']) != 1 for c in contexts):
            raise ValueError('warp1 evaluator currently supports the single box collision geom only')
        self.target_ids=wp.array([c['gids'][0] for c in contexts],dtype=int)
        self.finger_ids=wp.array([sorted(c['finger_ids'],key=c['finger_ids'].get) for c in contexts],dtype=int)
        @wp.kernel
        def evaluate(nacon:wp.array[int],worldid:wp.array[int],geom:wp.array[wp.vec2i],
                     cone:int,njmax:int,frame:wp.array[wp.mat33],friction:wp.array[vec5],
                     condim:wp.array[int],adr:wp.array2d[int],adhesion:wp.array[float],
                     efc_force:wp.array2d[float],targets:wp.array[int],fingers:wp.array2d[int],out:wp.array2d[float]):
            i=wp.tid()
            if i<nacon[0]:
                a,b=geom[i][0],geom[i][1]
                w=worldid[i]
                target=targets[w]
                left,right=fingers[w,0],fingers[w,1]
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
        niter=self.wd.solver_niter.numpy()
        self.solver_samples.append({'control_tick':self.tick,'max':int(niter.max()),
            'mean':float(niter.mean()),'min':int(niter.min()),
            'active_dofs_sample_max':int(np.sum(self.wd.tree_awake.numpy()[:,self.dof_tree]!=0,axis=1).max())})
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
            buffer=io.BytesIO()
            Image.fromarray(rgb).save(buffer,format='JPEG',quality=82)  # frozen World.render_jpeg default
            self.rgb.append(buffer.getvalue())
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
            d.contact.efc_address,d.contact.adhesion,d.efc.force,self.target_ids,self.finger_ids,self.force_out])
        self.contact_forces=self.force_out.numpy()
