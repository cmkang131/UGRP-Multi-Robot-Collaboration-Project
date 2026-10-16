"""Opt-in MJWarp adapter for existing relocation/E2E physics owners.

Only the physical owner retains MjData. Actor readers receive JPEG and issued
commands; evaluation can read exported GPU state. CPU rollout/render is disabled
after native scene initialization. Shared warp_act_backend.py is not modified.
"""
import ast, base64, hashlib, io, json, math, time
from collections import deque
from pathlib import Path
import numpy as np
from scripts.warp_act_backend import WarpTransport
from scripts.warp_act_core import SERVOS, control_tape, physics_schedule
from scripts.warp9_profile import phase


def sim_clock(origin,tick,period):
    # Preserve the native setup epoch exactly. R1d origin1.3000000000000178
    # became1.3 under absolute rounding, moving the port clock backwards by
    #1.78e-14s (2000PWM/s accumulation then exceeds its existing1e-12 guard).
    # Round only the integer-tick offset; no tolerance/command guard is relaxed.
    return origin+round(tick*period,9)


def review_due(cache,nworld,review_names,now):
    # Check the requested review keys, independently of any actor cache and
    # the native setup epoch. No playback request may receive a missing JPEG.
    missing=any((i,name) not in cache for i in range(nworld) for name,_,_ in review_names)
    return missing or abs(now*2-round(now*2))<=1e-6


def review_cameras(camera_names,actors):
    # PlaybackRecorder's exact existing contract is cctv_top. R2 selected the
    # lexicographically first CCTV (cctv_front_left), then failed on cctv_top.
    if not any(rid=='cctv_top' for rid,_,_ in camera_names):raise ValueError('playback cctv_top camera missing')
    return [entry for entry in camera_names if entry[0] not in actors and entry[0] in ('r1','r2','r3','cctv_top')]


class Batch(WarpTransport):
    def initialize(self, contexts, **kwargs):
        self.period=getattr(self,'period',.1)
        self.all_contexts=contexts
        self.actor_histories=[{} for _ in contexts]
        self.camera_cache={}
        self._multi_camera=False
        self.done=np.zeros(len(contexts),bool)
        # Host candidate starts from authored/issued controls, never an
        # evaluator readback. GPU ctrl is generated solely from this buffer.
        self.issued_ctrl=np.stack([c['world'].data.ctrl.copy() for c in contexts])
        for i,c in enumerate(contexts):
            p=self.out/f'world-{i:03d}';p.mkdir(parents=True,exist_ok=True)
            (p/'scene.xml').write_text(c['world'].scene_xml)
        if getattr(self,'native_model_batch_v1',False):
            from scripts.warp7_native_models import initialize
            initialize(self,contexts,**kwargs)
        else:super().initialize(contexts,**kwargs)
        self.camera.update(renderer='MJWarp own RGB + '+self.multi_renderer.audit['profile'],
            quality_requested='no_mip_v1',visual_adapter=self.multi_renderer.audit)
        if self.period!=.1:
            wp,mjw=self.wp,self.mjw
            self.control_steps,self.graph_chunk,self.graph_repeats=physics_schedule(self.period,self.dt)
            self.tape=wp.zeros((self.control_steps,self.n,self.m.nu),dtype=float)
            with wp.ScopedCapture() as capture:
                for _ in range(self.graph_chunk):
                    wp.launch(self.command_kernel,dim=(self.n,self.m.nu),inputs=[self.tape,self.graph_tick,self.wd.ctrl])
                    mjw.step(self.wm,self.wd)
                    wp.launch(self.advance_kernel,dim=1,inputs=[self.graph_tick])
            self.graph=capture.graph
            self.capacities.update(control_steps=self.control_steps,graph_chunk=self.graph_chunk,graph_repeats=self.graph_repeats)
        if getattr(self,'warp9_full_period_graph_v1',False):
            from scripts.warp9_graph import capture_period
            self.warp9_graph_audit=capture_period(self)
        if getattr(self,'warp9_physics_event_trace_v1',False):
            from scripts.warp9_graph import capture_trace
            self.warp9_trace_audit=capture_trace(self)
        self.initial_times=np.array([c['world'].data.time for c in contexts])
        # Initial native setup is separately recorded; rollout has no C step.
        def forbidden(*a,**kw):raise RuntimeError('warp5 native physics/render forbidden after setup')
        for i,c in enumerate(contexts):
            w=c['world'];w._physics_step_for=forbidden
            w.render_jpeg=lambda robot_id='r1',camera='robot_cam',quality=82,i=i,**kw:self.jpeg(i,robot_id,camera)
            w.render_rgb=lambda robot_id='r1',camera='robot_cam',i=i,**kw:self.rgb_arrays[(i,robot_id)]
            w.render_team_jpeg=lambda camera='cctv_top',i=i,**kw:self.camera_cache[(i,camera)]
        return self

    def init_kernels(self, contexts):
        # No target-dependent evaluator kernel: get_data_into exports genuine
        # GPU contacts/forces to the evaluation owner, never C recomputation.
        wp=self.wp
        @wp.kernel
        def command(tape:wp.array3d[float],tick:wp.array[int],ctrl:wp.array2d[float]):
            w,j=wp.tid();ctrl[w,j]=tape[tick[0],w,j]
        @wp.kernel
        def advance(tick:wp.array[int]):tick[0]+=1
        self.command_kernel,self.advance_kernel=command,advance

    def build_lookup(self, ignored):
        self.robot_tables={}
        for rid in self.all_contexts[0]['ports']:
            super().build_lookup(self.all_contexts[0]['world'].robot(rid))
            self.robot_tables[rid]=(self.lookup.copy(),self.wheel_ids.copy(),self.servo_ids.copy())
        self.relays={rid:np.zeros((self.n,4),int) for rid in self.robot_tables}

    def jpeg(self,i,rid,camera='robot_cam'):
        if camera!='robot_cam':raise ValueError('actor own camera required')
        return self.camera_cache[(i,rid)]

    def actor(self,i,rid):
        """No world/pose/contact/map truth can cross this capability boundary."""
        c=self.all_contexts[i];p=c['ports'][rid]
        return dict(robot_id=rid,sim_time=float(c['world'].data.time),camera='robot_cam',
                    jpeg=self.jpeg(i,rid),issued_pwm={s:float(p._servo_applied[s]) for s in SERVOS},
                    issued_wheels=list(p._motor_commands))

    def sync_render(self,contexts):
        import cv2,mujoco
        from PIL import Image
        wp,mjw=self.wp,self.mjw
        if not self._multi_camera:
            self.camera_names=[(rid,rid+'__robot_cam',(640,480)) for rid in ('r1','r2','r3')]
            # Overview is evaluation/review only, absent from actor().
            names={self.m.camera(i).name for i in range(self.m.ncam)}
            tops=sorted(name for name in names if name.startswith('cctv_'))
            self.camera_names += [(name,name,(320,240)) for name in tops]
            from scripts.warp5_render import Renderer
            actor_names=[entry for entry in self.camera_names if entry[0] in contexts[0]['ports']]
            self.review_names=review_cameras(self.camera_names,contexts[0]['ports'])
            self.multi_renderer=Renderer(self.m,self.wm,self.wd,actor_names if getattr(self,'camera_demand_v1',False) else self.camera_names,
                enabled=getattr(self,'warp5_native_visual_v1',False) or getattr(self,'warp5_native_visual_v2',False),
                texture_after_lighting=getattr(self,'warp5_native_visual_v2',False),profile=getattr(self,'warp9_profile',None),host_pipeline=getattr(self,'warp10_render_stage_v1',False))
            self.review_renderer=(Renderer(self.m,self.wm,self.wd,self.review_names,
                enabled=getattr(self,'warp5_native_visual_v1',False) or getattr(self,'warp5_native_visual_v2',False),
                texture_after_lighting=getattr(self,'warp5_native_visual_v2',False),profile=getattr(self,'warp9_profile',None),host_pipeline=getattr(self,'warp10_render_stage_v1',False)) if getattr(self,'camera_demand_v1',False) and self.review_names else None)
            if getattr(self,'camera_demand_v1',False):
                self.parity_renderer=Renderer(self.m,self.wm,self.wd,self.camera_names,
                    enabled=getattr(self,'warp5_native_visual_v1',False) or getattr(self,'warp5_native_visual_v2',False),
                    texture_after_lighting=getattr(self,'warp5_native_visual_v2',False),profile=getattr(self,'warp9_profile',None))
                self.parity_rows=[];self.parity_motion=False
            self._multi_camera=True
        start=time.perf_counter()
        if getattr(self,'warp10_render_stage_v1',False):
            from scripts.warp10_host import Readback
            if not hasattr(self,'render_staging'):self.render_staging=Readback(wp,self,'render')
            with phase(self,'render_batch_gpu',device=True):
                pending=[self.multi_renderer.enqueue_render(self.render_staging)]
                now=sim_clock(contexts[0]['origin'],self.tick,self.period)
                if self.review_renderer is not None and review_due(self.camera_cache,self.n,self.review_names,now):
                    pending.append(self.review_renderer.enqueue_render(self.render_staging))
                values=self.render_staging.finish()
            rendered={}
            for finish in pending:rendered.update(finish(values))
        else:rendered=self.multi_renderer.render()
        if getattr(self,'warp10_same_state_audit_v1',False) and not hasattr(self,'warp10_rgb_audit'):
            # Same GPU state, old reference renderer, no physics between calls.
            saved=self.multi_renderer.host_pipeline;self.multi_renderer.host_pipeline=False
            try:reference=self.multi_renderer.render()
            finally:self.multi_renderer.host_pipeline=saved
            self.warp10_rgb_audit=[]
            for rid in reference:
                aa,bb=(np.clip(x,0,255).astype(np.uint8) for x in (rendered[rid][0],reference[rid][0]))
                self.warp10_rgb_audit.append(dict(camera=rid,exact=bool(np.array_equal(aa,bb)),
                    sha256=hashlib.sha256(aa.tobytes()).hexdigest(),reference_sha256=hashlib.sha256(bb.tobytes()).hexdigest()))
            if not all(row['exact'] for row in self.warp10_rgb_audit):raise ValueError('staged rendering changed same-state RGB')
            (self.out/'warp10-rgb-audit.json').write_text(json.dumps(self.warp10_rgb_audit,indent=2)+'\n')
        if getattr(self,'camera_demand_v1',False):
            issued=tuple(tuple(p._motor_commands)+tuple(p._servo_applied.values()) for c in contexts for p in c['ports'].values())
            initial=not hasattr(self,'parity_initial_issued')
            if initial:self.parity_initial_issued=issued
            changed=issued!=self.parity_initial_issued
            if initial or (changed and not self.parity_motion):
                full=self.parity_renderer.render();checks=[]
                for rid in contexts[0]['ports']:
                    aa,bb=(np.clip(x,0,255).astype(np.uint8) for x in (rendered[rid][0],full[rid][0]))
                    checks.append(dict(robot=rid,exact=bool(np.array_equal(aa,bb)),max_delta=int(np.abs(aa.astype(int)-bb).max())))
                self.parity_rows.append(dict(tick=self.tick,own_command_changed=changed,checks=checks))
                (self.out/'camera-demand-parity.json').write_text(json.dumps(dict(scope='same GPU state/full vs demanded own cameras; no CPU reference',rows=self.parity_rows),indent=2)+'\n')
                if not all(c['exact'] for c in checks):raise ValueError('demand rendering changed actor RGB')
                if changed:self.parity_motion=True
        if self.review_renderer is not None and not getattr(self,'warp10_render_stage_v1',False):
            # Same exact2Hz predicate as PlaybackRecorder.observe. Actor RGB
            # stays10Hz; only unconsumed peer/overview render calls are omitted.
            now=sim_clock(contexts[0]['origin'],self.tick,self.period)
            if review_due(self.camera_cache,self.n,self.review_names,now):rendered.update(self.review_renderer.render())
        if not hasattr(self,'rgb_arrays'):self.rgb_arrays={}
        for camera,(rid,name,(width,height)) in enumerate(self.camera_names):
            if rid not in rendered:continue
            values=np.clip(rendered[rid][0],0,255).astype(np.uint8)
            for i,rgb in enumerate(values):
                if rid in ('r1','r2','r3'):
                    rgb=cv2.remap(rgb,self.mx,self.my,cv2.INTER_LINEAR,borderMode=cv2.BORDER_CONSTANT)
                    self.rgb_arrays[(i,rid)]=rgb
                with phase(self,'jpeg_cpu'):
                    b=io.BytesIO();Image.fromarray(rgb).save(b,format='JPEG',quality=82)
                self.camera_cache[(i,rid)]=b.getvalue()
        export=mjw.get_data_into
        profile=getattr(self,'warp9_profile',None)
        if getattr(self,'warp10_eval_export_v1',False):
            from scripts.warp10_host import EvaluationExport
            if not hasattr(self,'eval_staging'):self.eval_staging=EvaluationExport(self)
            self.eval_staging.stage();export=self.eval_staging.export
            self.export_profile_audit=self.eval_staging.audit()
        elif profile:
            from scripts.warp9_profile import exporter
            export,self.export_profile_audit=exporter(export,lambda a:profile.numpy(a,name='evaluator_d2h'))
        with phase(self,'evaluator_export_total'):
            for i,c in enumerate(contexts):
                if self.done[i]:continue
                # Native get_data_into copies GPU contacts/forces. Do not call
                # mj_forward/mj_step to invent CPU contacts for GPU evaluation.
                export(c['world'].data,c['world'].model,self.wd,world_id=i)
        if getattr(self,'warp10_same_state_audit_v1',False) and hasattr(self,'eval_staging') and not hasattr(self,'warp10_export_audit'):
            self.warp10_export_audit=self.eval_staging.compare(contexts)
            (self.out/'warp10-export-audit.json').write_text(json.dumps(self.warp10_export_audit,indent=2)+'\n')
            if not all(row['exact'] for row in self.warp10_export_audit):raise ValueError('staged evaluator export changed same-state fields')
        for i,c in enumerate(contexts):
            if not self.done[i]:c['world'].data.time=sim_clock(c['origin'],self.tick,self.period)
        self.rgb=[self.jpeg(i,c.get('rid','r3')) for i,c in enumerate(contexts)]
        self.seconds['render_and_evaluator_export']+=time.perf_counter()-start

    def step(self,contexts,active):
        wp=self.wp;active=np.asarray(active,dtype=bool);self.done=~active
        # Freeze terminal worlds' integration state, including warmstart,
        # command clock/history. Shared derived contact cache is regenerated.
        frozen={name:getattr(self.wd,name).numpy() for name in self.initial_state} if self.done.any() else {}
        start=time.perf_counter();ctrl=(self.issued_ctrl.copy() if getattr(self,'warp10_command_batch_v1',False) else np.stack([c['world'].data.ctrl.copy() for c in contexts]))
        tapes=[]
        row_groups=[]
        for rid,(lookup,wheels,servos) in self.robot_tables.items():
            rows=[]
            for i,c in enumerate(contexts):
                p=c['ports'][rid];now=float(c['world'].data.time)
                deadline=getattr(p,'_wheel_deadlines',[p._drive_expires_at]*4)
                rows.append(dict(ctrl=ctrl[i],wheels=p._motor_commands if active[i] else [0.]*4,
                    deadlines=[v or 0. for v in deadline],applied=[p._servo_applied[s] for s in SERVOS],
                    target=[p._servo_targets.get(s,p._servo_applied[s]) for s in SERVOS],
                    servo_active=[active[i] and s in p._servo_targets for s in SERVOS],now=now,servo_time=p._servo_tick_time))
                if p._command_expires_at is not None and p._command_expires_at<=now+self.period:
                    raise ValueError('sub-tick command revocation needs explicit command-tape event support')
            row_groups.append(rows)
        params=contexts[0]['world'].drive_parameters
        options=dict(dt=self.dt,steps=self.control_steps,start_fraction=params.start_fraction,
            kinetic_fraction=params.kinetic_fraction,torque_cap_nm=params.torque_cap_nm)
        if getattr(self,'warp10_command_batch_v1',False):
            from scripts.warp10_host import command_tapes
            outputs=command_tapes(row_groups,list(self.relays.values()),list(self.robot_tables.values()),**options)
        else:
            outputs=[control_tape(rows,self.relays[rid],lookup=lookup,wheel_ids=wheels,servo_ids=servos,**options)
                     for rows,(rid,(lookup,wheels,servos)) in zip(row_groups,self.robot_tables.items())]
        for (rid,(lookup,wheels,servos)),(tape,state) in zip(self.robot_tables.items(),outputs):
            self.relays[rid][active]=state['relay'][active]
            tapes.append((tape,np.concatenate([wheels,*[np.asarray(s) for s in servos]])))
            for i,c in enumerate(contexts):
                if not active[i]:continue
                p=c['ports'][rid];p._servo_applied=dict(zip(SERVOS,state['applied'][i]))
                p._servo_targets={s:int(state['target'][i,k]) for k,s in enumerate(SERVOS) if state['servo_active'][i,k]}
                p._servo_tick_time=float(state['servo_time'][i]);p._motor_commands=tuple(state['wheels'][i])
                if hasattr(p,'_wheel_deadlines'):p._wheel_deadlines=[d if d and d>p._servo_tick_time else None for d in p._wheel_deadlines]
                c['world'].robot(rid).servo_command_pulses.update(dict(zip(SERVOS,map(int,state['pwm'][i]))))
        combined=np.repeat(ctrl[None,:,:],self.control_steps,axis=0).astype(np.float32)
        for tape,ids in tapes:combined[:,:,ids]=tape[:,:,ids]
        if getattr(self,'warp10_command_batch_v1',False):self.issued_ctrl=combined[-1].copy()
        if getattr(self,'warp9_profile',None):
            self.warp9_profile.rows.append(dict(phase='command_python',wall_s=time.perf_counter()-start,
                submit_s=time.perf_counter()-start,wait_s=0.,device_s=None,bytes=0,implicit_syncs=0,explicit_syncs=0,status='COMPLETE'))
        with phase(self,'command_h2d',device=True,nbytes=combined.nbytes):
            if getattr(self,'warp10_command_batch_v1',False):
                if not hasattr(self,'pinned_tape'):self.pinned_tape=wp.empty(self.tape.shape,dtype=self.tape.dtype,device='cpu',pinned=True)
                self.pinned_tape.numpy()[:]=combined;wp.copy(self.tape,self.pinned_tape)
            else:wp.copy(self.tape,wp.array(combined,dtype=float))
            self.graph_tick.zero_()
        with phase(self,'physics_graph',device=True):
            for _ in range(self.graph_repeats):wp.capture_launch(self.graph)
        with phase(self,'physics_existing_sync',explicit_syncs=1):
            wp.synchronize()
        self.tick+=1
        if getattr(self,'warp9_physics_event_trace_v1',False):
            from scripts.warp9_graph import trace_summary
            (self.out/'physics-event-trace.json').write_text(json.dumps(trace_summary(self),indent=2)+'\n')
        for name,value in frozen.items():
            current=getattr(self.wd,name).numpy();current[self.done]=value[self.done]
            wp.copy(getattr(self.wd,name),wp.array(current,dtype=getattr(self.wd,name).dtype))
        with phase(self,'overflow_d2h',implicit_syncs=1,nbytes=self.n*4):
            if np.any(self.wd.overflow.numpy()):raise RuntimeError('MJWarp workspace overflow')
        self.seconds['command_and_physics']+=time.perf_counter()-start
        self.sync_render(contexts)


def transform_runner(text,namespace,bridge,kind):
    """Rewrite only advance scheduling; fail closed on an unexpected source AST."""
    tree=ast.parse(text);name='acquire' if kind=='selfmap' else 'run'
    function=next(n for n in tree.body if isinstance(n,ast.FunctionDef) and n.name==name)
    counts={'setup':0,'advance':0}
    class Rewrite(ast.NodeTransformer):
        def visit_While(self,node):
            if kind=='carry' and any(isinstance(n,ast.Call) and isinstance(n.func,ast.Attribute) and n.func.attr=='_physics_step_for' for n in ast.walk(node)) and not any(isinstance(n,ast.While) and n is not node for n in ast.walk(node)):
                counts['advance']+=1
                return ast.parse("yield {'kind':'step','target':until}").body[0]
            return self.generic_visit(node)
        def visit_Expr(self,node):
            if kind in ('selfmap','e2e') and isinstance(node.value,ast.Call) and isinstance(node.value.func,ast.Attribute) and node.value.func.attr=='advance_to':
                counts['advance']+=1
                return ast.Expr(ast.Yield(ast.Dict(keys=[ast.Constant('kind'),ast.Constant('target')],values=[ast.Constant('step'),node.value.args[0]])))
            return self.generic_visit(node)
        def visit_Assign(self,node):
            self.generic_visit(node)
            if kind=='carry' and any(isinstance(t,ast.Name) and t.id=='tick' for t in node.targets) and isinstance(node.value,ast.Constant) and node.value.value==0:
                counts['setup']+=1
                return [node,*ast.parse("yield __warp5_bridge__.setup_carry(locals())").body]
            return node
        def visit_Call(self,node):
            self.generic_visit(node)
            if kind=='selfmap' and isinstance(node.func,ast.Attribute) and node.func.attr=='reset' and isinstance(node.func.value,ast.Name) and node.func.value.id=='backend':
                # Insert setup yield after the statement via visit_Expr below.
                pass
            return node
    class SelfmapRewrite(Rewrite):
        def visit_Expr(self,node):
            out=super().visit_Expr(node)
            if isinstance(node.value,ast.Call) and isinstance(node.value.func,ast.Attribute) and node.value.func.attr=='reset' and isinstance(node.value.func.value,ast.Name) and node.value.func.value.id=='backend':
                counts['setup']+=1
                setup='setup_e2e' if kind=='e2e' else 'setup_selfmap'
                return [out,*ast.parse(f"yield __warp5_bridge__.{setup}(backend)").body]
            return out
    (SelfmapRewrite() if kind in ('selfmap','e2e') else Rewrite()).visit(function)
    expected={'setup':1,'advance':2 if kind=='selfmap' else 1}
    if counts!=expected:raise ValueError(f'warp5 frozen scheduling shape changed: {counts} != {expected}')
    namespace=dict(namespace,__warp5_bridge__=bridge)
    module=ast.fix_missing_locations(ast.Module(body=[function],type_ignores=[]))
    exec(compile(module,'<warp5-scheduling-adapter>','exec'),namespace)
    return namespace[name],dict(edits=counts,source_sha256=hashlib.sha256(text.encode()).hexdigest(),ast_sha256=hashlib.sha256(ast.dump(module).encode()).hexdigest())
