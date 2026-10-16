"""ACT-private native contact adapter; common warp-act backend remains untouched.

The initialize method is copied from f0db6b1a, with only the two noslip guards
and their error texts changed. All allocation, reference, sleep, solver,
rendering and graph code stays byte-identical. This is an explicit profile
fork, never a bypass accepting noslip10: both CPU and GPU must be zero.
The profile itself is byte-identical to warpfit df5a1f86a.
"""
import copy
from contextlib import contextmanager
import hashlib
import json
from pathlib import Path
import sys
import numpy as np
import warp_act_backend as baseline
from warp_act_core import model_key, runtime_sleep_policy, physics_schedule

PROFILE = 'warp_native_contact_v1'
PROFILE_SHA = 'a5c8d370755034b9f9615f66a94b87883327b7d7ecc4e13082eac2c2d4751c6a'
BASE_SOURCE = 'f0db6b1abb842ea65b71c433738210254f300a7c'


def apply_scene(scene):
    from sim.warp_native_contact import apply, record
    source = Path(sys.modules[apply.__module__].__file__)
    if hashlib.sha256(source.read_bytes()).hexdigest() != PROFILE_SHA:
        raise ValueError('warpfit profile byte mismatch')
    original = scene.robot_transform
    def transform(xml, **kwargs):
        return apply(original(xml, **kwargs), PROFILE)
    scene.robot_transform = transform
    scene.manifest['act16w_native_contact'] = dict(**record(PROFILE),
        profile_source_sha256=PROFILE_SHA, source='df5a1f86aad420f2fab2c10e3ee77cdb5ec11807')
    return scene


class NativeScene:
    def make_world(self, plan, scene, factory, bind_camera, **kwargs):
        world, scene = super().make_world(plan, apply_scene(scene), factory, bind_camera, **kwargs)
        opt = world.model.opt
        if (opt.noslip_iterations != 0 or float(opt.impratio) != 5
                or opt.iterations != 80 or opt.ls_iterations != 50
                or int(opt.cone) != 1 or int(opt.integrator) != 3):
            raise ValueError('nativecontact CPU options differ from user-approved 0/5/80/50/elliptic/implicitfast')
        return world, scene


class NativeTransport(NativeScene, baseline.WarpTransport):
    def initialize(self, contexts, *, compiled_reference=None, compiled_geometry=None, per_world_model_references=None, float32_solver_default_v1=False,sap_segmented_v1=False):
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
        self.control_steps,self.graph_chunk,self.graph_repeats=physics_schedule(.1,self.dt)
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
            if model.opt.noslip_iterations!=0 or np.any(c['world'].data.eq_active):
                raise ValueError('native contact noslip0 / weld OFF required in every world')
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
        if sap_segmented_v1:
            self.wm.opt.broadphase=mjw.BroadphaseType.SAP_SEGMENTED
        if getattr(self,'batch_sleep_v1',False):
            from warp_act_sleep import install
            lengths=np.concatenate([model.dof_length for model in models]).astype(np.float32)
            self.wm.dof_length=wp.array(lengths,dtype=float)
            self.model_batch_audit['world_sleep']=install(int(m.nv),self.out)
            self.model_batch_audit['world_sleep']['length_sha256']=hashlib.sha256(lengths.tobytes()).hexdigest()
        self.compat['broadphase']={'name':self.wm.opt.broadphase.name,'candidate':sap_segmented_v1,
            'basis':'pinned io.py439 default NXN; types.py124-135 upstream SAP_SEGMENTED; same geometry/contact parameters'}
        upstream_tolerance=float(self.wm.opt.tolerance.numpy().item())
        if not float32_solver_default_v1:
            self.wm.opt.tolerance.fill_(float(m.opt.tolerance))
        self.solver_numerics={'profile':'float32_solver_default_v1' if float32_solver_default_v1 else 'source_tolerance',
            'source_tolerance':float(m.opt.tolerance),'upstream_tolerance':upstream_tolerance,
            'effective_tolerance':float(self.wm.opt.tolerance.numpy().item()),
            'basis':'pinned io.py433 clamps float64 C tolerance to minimum1e-6 to avoid float32 needless iterations; task Score unchanged'}
        self.solver_samples=[]
        if self.wm.opt.noslip_iterations != 0:
            raise RuntimeError('native noslip0 lost in Warp conversion')
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
        self.tape = wp.zeros((self.control_steps,self.n,m.nu),dtype=float)
        self.graph_tick = wp.zeros(1,dtype=int)
        self.force_out = wp.zeros((self.n,2),dtype=float)
        self.init_kernels(contexts)
        # Compile once, then discard the warm-up state before any rollout.
        mjw.step(self.wm,self.wd); wp.synchronize()
        d.tree_asleep[:]=self.source_sleep[0]
        with unused_efm(m,d):
            self.wd = mjw.put_data(m,d,nworld=self.n,nconmax=ncon,njmax=njmax,nvmax=self.nvmax)
        self.copy_initial_state(contexts)
        self.solver_numerics.update(compact_ctol=self.wd.ctol.numpy().tolist(),
            compact_cls_tol=self.wd.cls_tol.numpy().tolist(),nvmax_pad=int(self.wd.cM.shape[-1]) if self.wd.ctol.size else None,
            compact_basis='pinned io.py1791-1797: max(source tolerance,1e-6)*nv/nvmax_pad; separate compact cohort')
        # Capture exactly the 400 physics ticks, not a host wall budget.
        with wp.ScopedCapture() as capture:
            for _ in range(self.graph_chunk):
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
        self.camera['quality_requested']='no_mip_v1' if self.scene_v5_v1 else 'native'
        self.capacities = dict(nconmax=ncon,njmax=njmax,naconmax=int(self.wd.naconmax),nvmax=int(self.wd.nvmax),control_steps=self.control_steps,graph_chunk=self.graph_chunk,graph_repeats=self.graph_repeats)
        self.build_lookup(contexts[0]['world'].robot('r1'))
        if getattr(self,'numpy_teacher_v1',False):
            from warp_act_visibility import BatchVisibility
            self.visibility=BatchVisibility(self,contexts)
        self.sync_render(contexts)
        if getattr(self,'numpy_teacher_v1',False):
            rows=[]
            for i,c in enumerate(contexts):
                reference=c['visibility_reference']()
                gpu=self.visibility.region_visible(i,c['gids'])
                rows.append(dict(world=i,c_reference=list(reference),gpu=list(gpu),exact=reference==gpu))
            (self.out/'visibility-initial-audit.json').write_text(json.dumps(dict(rows=rows,
                exact=sum(r['exact'] for r in rows),N=len(rows),scope='evaluation-only initial C/GPU ray definition check; no scalar result enters teacher; no C physics equivalence gate'),indent=2)+'\n')
        (self.out/'native-contact.json').write_text(json.dumps(dict(
            profile=PROFILE, profile_source_sha256=PROFILE_SHA,
            cpu_noslip=[int(c['world'].model.opt.noslip_iterations) for c in contexts],
            gpu_noslip=int(self.wm.opt.noslip_iterations), cpu_impratio=float(m.opt.impratio),
            cpu_iterations=int(m.opt.iterations), cpu_ls_iterations=int(m.opt.ls_iterations),
            common_backend_source=BASE_SOURCE, common_backend_edited=False,
            solver_numerics=self.solver_numerics), indent=2)+'\n')



@contextmanager
def installed():
    """Process-local opt-in only; never alter the frozen source files."""
    class NativeCTransport(NativeScene, baseline.CTransport):
        pass
    original, original_c = baseline.WarpTransport, baseline.CTransport
    baseline.WarpTransport = NativeTransport
    baseline.CTransport = NativeCTransport
    try:
        yield
    finally:
        baseline.WarpTransport = original
        baseline.CTransport = original_c
