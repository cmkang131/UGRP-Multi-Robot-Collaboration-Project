"""Training-only pre-hover oracle; default-off executable takeover on top.

Adapted from frozen ACT3f99 ShadowTeacher. Visibility uses qualified f0db's
GPU seven-probe boundary. In the default label-only lane only the student's
selected command updates issued memory; teacher targets go to a separate label
sink and are never applied, and the close boundary disables queries for that
episode. With the explicit ``--takeover`` opt-in a fresh teacher (seeded from
the student's last issued pwm) is executed through the unchanged owner.step
call path at the preregistered C1 trigger; see scripts/act18_takeover.py.
"""
from copy import deepcopy
import hashlib
import math

from act16w_dagger import OracleHoldBoundary, PHASES
from act18_takeover import TakeoverRgb, TakeoverTrigger, takeover_teacher


class VisibleOracle:
    def __init__(self, owner, index, *, takeover=False, takeover_hold_s=3.0,
                 takeover_after_s=6.0):
        from sim.grasp_act_solo_teacher import InputAudit, SoloTeacher, primitives
        from scripts.zone_teacher import plan_path, proportional_drive, OPEN
        from warp_act_scene import make_scene
        from warp_act_numpy import solve_grip_site_ik
        self.owner, self.i = owner, index
        self.ctx = owner.contexts[index]
        self.plan = owner.plans[index]
        initial = owner.previous[index]
        if initial['pwm']['1'] != OPEN:
            raise ValueError('oracle needs already-issued frozen OPEN; no extra action permitted')
        self.boundary = OracleHoldBoundary(initial)
        self.audit, self.valid, self.n = InputAudit(), True, 0
        self.discs, self.rects = [], []
        self.disc_names,self.rect_names,self.route_rejections=[],[],[]
        def route(goal, context):
            path=plan_path((0.,0.),goal[:2],(-2.,2.,-2.,2.),self.discs,rects=self.rects,radius=.17)
            if not path:
                from harness.static_keepouts import rect_distance
                gaps=[(math.hypot(goal[0]-x,goal[1]-y)-r-.17,name) for (x,y,r),name in zip(self.discs,self.disc_names)]
                gaps += [(rect_distance(goal[:2],rect)-.17,name) for rect,name in zip(self.rects,self.rect_names)]
                gap,name=min(gaps) if gaps else (None,'none_observed')
                self.route_rejections.append(dict(category='no_visible_route',reason='frozen A* found no path within existing40000-node budget',blocking_object=name,minimum_gap_m=gap,minimum_gap_scope='nearest currently visible object at requested goal; not unique blocker attribution',search_budget_nodes=40000))
                return 0.,0.,0.
            point=next((p for p in path if math.hypot(*p)>=.06),goal[:2])
            command=proportional_drive((0.,0.,0.),goal[:2],point,goal[2])
            return command['forward'],command['left'],command['turn']
        ops=primitives();ops.ik=solve_grip_site_ik  # exact qualified f0db NumPy51-pitch solver
        self.ops=ops
        self.teacher = SoloTeacher(self.plan['kind'],self.plan['role'],
            {int(k):v for k,v in initial['pwm'].items()},profile='solo_visible_only_v1',
            held_object_hidden_v1=True,teacher_stability='align_relook_v1',reach_mode='pad_window_v2',ops=ops,route=route,
            rgb_lift_mode='solo_lift_lookback_v1',solo_lift_lookback_margin_v1=True)
        self.route=route
        scene=make_scene({**self.plan,'end_color_scene':'off'})
        self.bodies={x.item_id:x.body for x in scene.cargo}
        self.bodies.update({k:v['body_name'] for k,v in scene.config['setup_only']['objects'].items()})
        m=self.ctx['world'].model
        import numpy as np
        from scripts.audit_grasp_act_visibility import BandVisibility
        geometry=BandVisibility.__new__(BandVisibility)
        geometry.model,geometry.body_gids=m,{}
        geometry.groups=np.array([1,1,1,1,0,0],dtype=np.uint8)
        def geoms(body):
            # Frozen teacher's descendant/visual-part selection, including its
            # existing largest-eight convention; no new visibility threshold.
            return geometry._body_geoms(m.body(body).id)
        self.geoms=geoms
        self.obstacles=[('robot:'+r,r+'__robot',geoms(r+'__robot')) for r in ('r2','r3')]
        self.obstacles += [(iid,name,geoms(name)) for iid,name in self.bodies.items() if iid!=self.plan['item_id']]
        self.walls=[g for g in range(m.ngeom) if 'wall' in (m.geom(g).name or '')]
        self.visibility_gids=set(self.ctx['gids'])|set(self.walls)|{g for _,_,gs in self.obstacles for g in gs}
        self.takeover_enabled=bool(takeover)
        self.takeover_hold_s=float(takeover_hold_s)
        self.takeover_trigger=(TakeoverTrigger(after_s=takeover_after_s)
                               if self.takeover_enabled else None)
        self.takeover=None
        self.takeover_rgb=None
        self.takeover_command=None
        self.last_takeover_command=None
        self.takeover_ticks=0

    def blocked(self):
        if not self.owner.active[self.i]:self.valid=False
        obs,_=self.owner.read_actor(self.i)
        self.boundary.closed_issued |= any(c['pwm']['1']<self.boundary.initial_open_pwm for c in obs['issued'])
        return self.boundary.closed_issued or not self.valid

    def _relative(self, teacher):
        import numpy as np
        world=self.ctx['world']
        b=world.data.body(self.bodies[self.plan['item_id']]);rot=b.xmat.reshape(3,3)
        point=b.xpos+rot@np.array([0.,0.,teacher.spec.grip_z_m-.016])
        base=world.robot('r1').base_xyz();yaw=float(world.robot('r1').base_rpy()[2]);dx,dy=point[0]-base[0],point[1]-base[1]
        return dict(xyz=[float(math.cos(yaw)*dx+math.sin(yaw)*dy),float(-math.sin(yaw)*dx+math.cos(yaw)*dy),float(point[2])],yaw=math.atan2(math.sin(math.atan2(rot[1,0],rot[0,0])-yaw),math.cos(math.atan2(rot[1,0],rot[0,0])-yaw)))

    def _refresh_obstacles(self, eyes):
        import numpy as np
        world=self.ctx['world']
        self.discs.clear();self.rects.clear();self.disc_names.clear();self.rect_names.clear()
        base=world.robot('r1').base_xyz();yaw=float(world.robot('r1').base_rpy()[2]);co,si=math.cos(yaw),math.sin(yaw)
        for iid,name,gids in self.obstacles:
            n_,N_=eyes.region_visible(self.i,gids)
            if N_ and n_>=math.ceil(N_/3):
                xy=world.data.body(name).xpos[:2]-base[:2]
                radius=.17 if iid.startswith('robot:') else max((float(np.linalg.norm(world.data.geom_xpos[g,:2]-world.data.body(name).xpos[:2]))+float(world.model.geom_rbound[g]) for g in gids),default=.2)
                self.discs.append((co*xy[0]+si*xy[1],-si*xy[0]+co*xy[1],radius))
                self.disc_names.append(iid)
        for g in self.walls:
            n_,N_=eyes.region_visible(self.i,[g])
            if N_ and n_>=math.ceil(N_/3):
                xy=world.data.geom_xpos[g,:2]-base[:2];rot=world.data.geom_xmat[g].reshape(3,3);a=math.atan2(rot[1,0],rot[0,0])-yaw
                self.rects.append((co*xy[0]+si*xy[1],-si*xy[0]+co*xy[1],*map(float,world.model.geom_size[g,:2]),math.atan2(math.sin(a),math.cos(a))))
                self.rect_names.append(world.model.geom(g).name)

    def query(self, eyes, selected):
        obs,jpgs=self.owner.read_actor(self.i);now=obs['t']
        self.takeover_command=None
        if self.takeover is not None and not self.owner.active[self.i]:
            # The takeover world already terminated: never step the teacher
            # again or emit a command the collector would not execute.
            return dict(sample_id=obs['sample_id'],t=now,
                teacher_phase=self.takeover.teacher.phase,
                phase_after=self.takeover.teacher.phase,label_valid=False,
                teacher_command=None,target_visible=False,done=True,takeover=True,
                command_complete=True,query_blocked_by_hold_boundary=False,
                rgb_holding='unknown',hold_s=self.takeover.hold_s)
        if self.takeover_enabled:
            elapsed=now-self.owner.origin
            # The world at this instant reflects the last APPLIED command
            # (owner.previous); the newly selected student command has not run.
            # Both the trigger streak and the seed therefore use that command.
            if self.takeover is None and self.takeover_trigger.observe(elapsed,self.owner.previous[self.i]):
                self._start_takeover(now)
            if self.takeover is not None:
                return self._takeover_query(eyes, selected, obs, jpgs, now)
        return self._label_query(eyes, selected, obs, now)

    def _label_query(self, eyes, selected, obs, now):
        teacher=self.teacher
        phase=teacher.phase
        rejected_before=len(self.route_rejections)
        def label():
            if not self.valid:return dict(label_valid=False,teacher_command=None,rejection_category='oracle_phase_outside_qualified_scope')
            n,N=eyes.region_visible(self.i,self.ctx['gids'])
            measurement=self.audit.measure(teacher.phase,visible_n=n,probe_N=N,holding=teacher.holding,read_relative=lambda:self._relative(teacher))
            if self.n%5==0:self._refresh_obstacles(eyes)
            target,_=teacher.step(now,measurement=measurement)
            self.valid=teacher.phase in PHASES
            return dict(label_valid=target is not None and self.valid,teacher_command=target if self.valid else None,target_visible=measurement is not None)
        row=self.boundary.query(obs['issued'],label)
        row.update(sample_id=obs['sample_id'],t=now,teacher_phase=phase,phase_after=teacher.phase,done=False)
        row['route_rejections']=self.route_rejections[rejected_before:]
        # Mirror only the command already selected by the student. The caller
        # separately applies that same command through the unchanged actor API.
        teacher.sink.pwm.update({int(k):v for k,v in selected['pwm'].items()})
        teacher.arm.commanded.update(teacher.sink.pwm);teacher.remember_applied(selected)
        self.n+=1
        return row

    def _start_takeover(self, now):
        # Fresh teacher seeded with the student's last issued (applied) pwm; its
        # phase clock is stamped through the teacher's own _set(now) path inside.
        self.takeover=takeover_teacher(self.plan,self.owner.previous[self.i],now=now,
            hold_s=self.takeover_hold_s,ops=self.ops,route=self.route)
        self.takeover_rgb=TakeoverRgb(self.plan['kind'],mode='solo_lift_lookback_v1',
            save=self._save_lift_rgb)
        (self.owner.out/'lift-rgb').mkdir(exist_ok=True)
        self.valid=False  # the label-only teacher is retired for this episode

    def _save_lift_rgb(self, tag, frame, now):
        import cv2
        path=self.owner.out/'lift-rgb'/f'{tag}-w{self.i:03d}.png'
        if not cv2.imwrite(str(path),frame):
            raise RuntimeError('failed to save takeover lift RGB evidence')
        return {'path':str(path.relative_to(self.owner.out)),'t':now,
                'sha256':hashlib.sha256(path.read_bytes()).hexdigest(),
                'pixel_sha256':hashlib.sha256(frame.tobytes()).hexdigest(),
                'shape':list(frame.shape)}

    def _takeover_query(self, eyes, selected, obs, jpgs, now):
        import cv2
        import numpy as np
        takeover=self.takeover;teacher=takeover.teacher
        # The previous tick's emitted teacher command must be the owner's
        # applied command: this is the proof that execution went through the
        # existing owner.step interface, not a side channel.
        if self.last_takeover_command is not None:
            applied=self.owner.previous[self.i]
            for key in ('t','wheels','duration_s','pwm'):
                if applied[key] != self.last_takeover_command[key]:
                    raise RuntimeError('takeover command was not executed through owner.step')
        n,N=eyes.region_visible(self.i,self.ctx['gids'])
        measurement=self.audit.measure(teacher.phase,visible_n=n,probe_N=N,
            holding=teacher.holding,read_relative=lambda:self._relative(teacher))
        if self.takeover_ticks%5==0:self._refresh_obstacles(eyes)
        if not jpgs:raise RuntimeError('takeover requires own RGB frames')
        frame=cv2.imdecode(np.frombuffer(jpgs[-1],np.uint8),cv2.IMREAD_COLOR)
        if frame is None:raise RuntimeError('takeover own RGB frame decode failed')
        previous=deepcopy(self.owner.previous[self.i])
        phase_before=teacher.phase
        answer=self.takeover_rgb.before_step(frame,now=now,previous=previous,
            phase=phase_before,teacher=teacher)
        rejected_before=len(self.route_rejections)
        value,done=takeover.step(now,measurement=measurement,rgb_holding=answer,
            own_rgb=lambda:cv2.cvtColor(frame,cv2.COLOR_BGR2RGB))
        self.takeover_rgb.after_step(frame,now=now,previous=previous,command=value,
            phase_before=phase_before,phase_after=teacher.phase)
        # Stop the episode on either teacher terminal result. Completion is the
        # only successful one; failures stay done=False at the command level but
        # still end this self-induced rollout instead of idling to the cap.
        terminal=bool(done) or teacher.result is not None
        row=dict(sample_id=obs['sample_id'],t=now,teacher_phase=phase_before,
            phase_after=teacher.phase,label_valid=True,teacher_command=value,
            target_visible=measurement is not None,done=terminal,takeover=True,
            teacher_result=teacher.result,hold_s=takeover.hold_s,
            rgb_holding=answer,command_complete=bool(done),
            query_blocked_by_hold_boundary=False)
        row['route_rejections']=self.route_rejections[rejected_before:]
        self.last_takeover_command=deepcopy(value)
        self.takeover_command=deepcopy(value)
        self.takeover_ticks+=1
        return row


class OracleBank:
    def __init__(self, owner, *, takeover=False, takeover_hold_s=3.0, takeover_after_s=6.0):
        from warp_act_visibility import BatchVisibility
        if not owner.training:raise ValueError('oracle requires private training owner')
        self.owner=owner
        self.takeover_enabled=bool(takeover)
        self.takeover_hold_s=float(takeover_hold_s)
        self.takeover_after_s=float(takeover_after_s)
        self.takeover_commands=None
        self.oracles=[VisibleOracle(owner,i,takeover=takeover,takeover_hold_s=takeover_hold_s,
            takeover_after_s=takeover_after_s) for i in range(owner.n)]
        contexts=[{**c,'visibility_gids':sorted(o.visibility_gids)} for c,o in zip(owner.contexts,self.oracles)]
        self.eyes=BatchVisibility(owner.hooks,contexts)
        self.queries=0

    def query(self, selected):
        import numpy as np
        owner=self.owner
        self.takeover_commands=None
        if len(selected)!=owner.n:raise ValueError('one selected student command per world')
        for i,cmd in enumerate(selected):
            owner.c.command(cmd)
            if abs(cmd['t']-owner.read_actor(i)[0]['t'])>1e-6:raise ValueError('oracle/student clock mismatch')
        before=owner.integration();public=deepcopy(owner.current);previous=deepcopy(owner.previous)
        if any(not o.blocked() or getattr(o,'takeover_enabled',False) for o in self.oracles):
            transforms={name:getattr(owner.hooks.wd,name).numpy() for name in ('geom_xpos','geom_xmat','cam_xpos','cam_xmat')}
            self.eyes.update(transforms)
        rows=[o.query(self.eyes,cmd) for o,cmd in zip(self.oracles,selected)]
        takeover=[getattr(o,'takeover_command',None) for o in self.oracles]
        if any(command is not None for command in takeover):
            self.takeover_commands=[None if command is None else
                dict(command=command,done=bool(row.get('done')))
                for command,row in zip(takeover,rows)]
        after=owner.integration()
        # Strict byte identity also handles unchanged NaN payloads in unused
        # compact workspace. Numeric array_equal can falsely reject those.
        changed = [k for k,v in before.items() if v.dtype != after[k].dtype
                   or v.shape != after[k].shape or v.tobytes() != after[k].tobytes()]
        if changed or public!=owner.current or previous!=owner.previous:
            owner.write('oracle-state-diff.json',dict(changed_fields=changed,
                actor_inputs_equal=public==owner.current,issued_equal=previous==owner.previous))
            np.savez_compressed(owner.out/'oracle-state-before.npz',**before)
            np.savez_compressed(owner.out/'oracle-state-after.npz',**after)
            raise RuntimeError('oracle query changed physics or student input history')
        self.queries+=1
        executed=sum(getattr(o,'takeover_ticks',0) for o in self.oracles)
        audit=dict(invisible_measurements=sum(o.audit.invisible_measurements for o in self.oracles),held_world_reads=sum(o.audit.held_world_reads for o in self.oracles),teacher_actions_executed=executed,queries=self.queries,integration_and_actor_inputs_unchanged=True,
            scope=('executed teacher takeover; commands applied through owner.step; not a non-executing label round' if executed else 'pre-hover h0-only training labels; no teacher action applied'))
        if getattr(self,'takeover_enabled',False):
            audit['takeover']=dict(enabled=True,hold_s=self.takeover_hold_s,
                after_s=self.takeover_after_s,commands_emitted=executed,
                worlds=[i for i,o in enumerate(self.oracles) if getattr(o,'takeover',None) is not None],
                triggers=[o.takeover_trigger.record() if getattr(o,'takeover_trigger',None) is not None else None for o in self.oracles])
        owner.write('oracle-audit.json',audit)
        return rows,audit
