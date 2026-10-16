"""Training-only, non-executing pre-hover oracle on current MJWarp states.

Adapted from frozen ACT3f99 ShadowTeacher. Visibility uses qualified f0db's
GPU seven-probe boundary. Only the student's selected command updates issued
memory; teacher targets are returned to a separate label sink, never applied.
The close boundary disables queries permanently for that episode.
"""
from copy import deepcopy
import math

from act16w_dagger import OracleHoldBoundary, PHASES


class VisibleOracle:
    def __init__(self, owner, index):
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
        def route(goal, context):
            path=plan_path((0.,0.),goal[:2],(-2.,2.,-2.,2.),self.discs,rects=self.rects,radius=.17)
            if not path:return 0.,0.,0.
            point=next((p for p in path if math.hypot(*p)>=.06),goal[:2])
            command=proportional_drive((0.,0.,0.),goal[:2],point,goal[2])
            return command['forward'],command['left'],command['turn']
        ops=primitives();ops.ik=solve_grip_site_ik  # exact qualified f0db NumPy51-pitch solver
        self.teacher = SoloTeacher(self.plan['kind'],self.plan['role'],
            {int(k):v for k,v in initial['pwm'].items()},profile='solo_visible_only_v1',
            held_object_hidden_v1=True,teacher_stability='align_relook_v1',reach_mode='pad_window_v2',ops=ops,route=route,
            rgb_lift_mode='solo_lift_lookback_v1',solo_lift_lookback_margin_v1=True)
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

    def blocked(self):
        if not self.owner.active[self.i]:self.valid=False
        obs,_=self.owner.read_actor(self.i)
        self.boundary.closed_issued |= any(c['pwm']['1']<self.boundary.initial_open_pwm for c in obs['issued'])
        return self.boundary.closed_issued or not self.valid

    def query(self, eyes, selected):
        import numpy as np
        world,teacher=self.ctx['world'],self.teacher
        obs,_=self.owner.read_actor(self.i);now=obs['t'];phase=teacher.phase
        def label():
            if not self.valid:return dict(label_valid=False,teacher_command=None,rejection_category='oracle_phase_outside_qualified_scope')
            n,N=eyes.region_visible(self.i,self.ctx['gids'])
            def relative():
                b=world.data.body(self.bodies[self.plan['item_id']]);rot=b.xmat.reshape(3,3)
                point=b.xpos+rot@np.array([0.,0.,teacher.spec.grip_z_m-.016])
                base=world.robot('r1').base_xyz();yaw=float(world.robot('r1').base_rpy()[2]);dx,dy=point[0]-base[0],point[1]-base[1]
                return dict(xyz=[float(math.cos(yaw)*dx+math.sin(yaw)*dy),float(-math.sin(yaw)*dx+math.cos(yaw)*dy),float(point[2])],yaw=math.atan2(math.sin(math.atan2(rot[1,0],rot[0,0])-yaw),math.cos(math.atan2(rot[1,0],rot[0,0])-yaw)))
            measurement=self.audit.measure(teacher.phase,visible_n=n,probe_N=N,holding=teacher.holding,read_relative=relative)
            if self.n%5==0:
                self.discs.clear();self.rects.clear()
                base=world.robot('r1').base_xyz();yaw=float(world.robot('r1').base_rpy()[2]);co,si=math.cos(yaw),math.sin(yaw)
                for iid,name,gids in self.obstacles:
                    n_,N_=eyes.region_visible(self.i,gids)
                    if N_ and n_>=math.ceil(N_/3):
                        xy=world.data.body(name).xpos[:2]-base[:2]
                        radius=.17 if iid.startswith('robot:') else max((float(np.linalg.norm(world.data.geom_xpos[g,:2]-world.data.body(name).xpos[:2]))+float(world.model.geom_rbound[g]) for g in gids),default=.2)
                        self.discs.append((co*xy[0]+si*xy[1],-si*xy[0]+co*xy[1],radius))
                for g in self.walls:
                    n_,N_=eyes.region_visible(self.i,[g])
                    if N_ and n_>=math.ceil(N_/3):
                        xy=world.data.geom_xpos[g,:2]-base[:2];rot=world.data.geom_xmat[g].reshape(3,3);a=math.atan2(rot[1,0],rot[0,0])-yaw
                        self.rects.append((co*xy[0]+si*xy[1],-si*xy[0]+co*xy[1],*map(float,world.model.geom_size[g,:2]),math.atan2(math.sin(a),math.cos(a))))
            target,_=teacher.step(now,measurement=measurement)
            self.valid=teacher.phase in PHASES
            return dict(label_valid=target is not None and self.valid,teacher_command=target if self.valid else None,target_visible=measurement is not None)
        row=self.boundary.query(obs['issued'],label)
        row.update(sample_id=obs['sample_id'],t=now,teacher_phase=phase,phase_after=teacher.phase,done=False)
        # Mirror only the command already selected by the student. The caller
        # separately applies that same command through the unchanged actor API.
        teacher.sink.pwm.update({int(k):v for k,v in selected['pwm'].items()})
        teacher.arm.commanded.update(teacher.sink.pwm);teacher.remember_applied(selected)
        self.n+=1
        return row


class OracleBank:
    def __init__(self, owner):
        from warp_act_visibility import BatchVisibility
        if not owner.training:raise ValueError('oracle requires private training owner')
        self.owner=owner
        self.oracles=[VisibleOracle(owner,i) for i in range(owner.n)]
        contexts=[{**c,'visibility_gids':sorted(o.visibility_gids)} for c,o in zip(owner.contexts,self.oracles)]
        self.eyes=BatchVisibility(owner.hooks,contexts)
        self.queries=0

    def query(self, selected):
        import numpy as np
        owner=self.owner
        if len(selected)!=owner.n:raise ValueError('one selected student command per world')
        for i,cmd in enumerate(selected):
            owner.c.command(cmd)
            if abs(cmd['t']-owner.read_actor(i)[0]['t'])>1e-6:raise ValueError('oracle/student clock mismatch')
        before=owner.integration();public=deepcopy(owner.current);previous=deepcopy(owner.previous)
        if any(not o.blocked() for o in self.oracles):
            transforms={name:getattr(owner.hooks.wd,name).numpy() for name in ('geom_xpos','geom_xmat','cam_xpos','cam_xmat')}
            self.eyes.update(transforms)
        rows=[o.query(self.eyes,cmd) for o,cmd in zip(self.oracles,selected)]
        after=owner.integration()
        if any(not np.array_equal(v,after[k]) for k,v in before.items()) or public!=owner.current or previous!=owner.previous:
            raise RuntimeError('oracle query changed physics or student input history')
        self.queries+=1
        audit=dict(invisible_measurements=sum(o.audit.invisible_measurements for o in self.oracles),held_world_reads=sum(o.audit.held_world_reads for o in self.oracles),teacher_actions_executed=0,queries=self.queries,integration_and_actor_inputs_unchanged=True,scope='pre-hover h0-only training labels; no teacher action applied')
        owner.write('oracle-audit.json',audit)
        return rows,audit
