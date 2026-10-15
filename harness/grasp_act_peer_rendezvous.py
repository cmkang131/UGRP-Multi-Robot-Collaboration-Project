"""Default-off visible/issued rendezvous retry, shared by teacher adapters.

ORCA (https://gamma-web.iacs.umd.edu/ORCA/) motivates moving-peer prediction;
PIBT (https://doi.org/10.24963/ijcai.2019/76) motivates replan/yield instead of
declaring failure at a local wait deadline. This is neither algorithm's full
implementation and inherits no completeness/safety theorem.
"""
from copy import deepcopy
import math

MODE='peer_rendezvous_v1'
BOUNDED_MODE='peer_rendezvous_v2'


class PeerRendezvous:
    def __init__(self,mode='off'):
        if mode not in ('off',MODE,BOUNDED_MODE):raise ValueError('unknown rendezvous mode')
        self.mode=mode;self.previous={};self.velocity={};self.events=[]
        self.yield_goal=None;self.visits={};self.retired=set();self.last_choice=None
        self.yield_until=None

    def expire_yield(self,t,world,now):
        if (self.mode!=BOUNDED_MODE or self.yield_goal is None
                or self.yield_until is None or now<self.yield_until):return
        # Reuse the existing visible_route refresh/prediction horizon (1 SIMs).
        # This invalidates an old motion plan; it never declares arrival. In
        # 8318611 R2 the proportional drive approached the wait point forever:
        # remaining distance always exceeded its shrinking issued pulse. See
        # experiments/2026-10-15-beampair3/r2-yield-analysis.json. No new distance
        # tolerance, physical success criterion or wall-clock budget is added.
        if world.get('beam') is not None:
            row=self.audit(t,world,now,'yield_plan_expired',self.yield_goal)
            row['reason_category']='prediction_horizon_elapsed'
        else:
            self.events.append(dict(t=now,event='yield_plan_expired',robot=t.rid,
                reason_category='prediction_horizon_elapsed',blocked_object='assigned_band_not_visible',
                min_gap_m=None,gap_scope='not_geometric; no hidden cargo query'))
        self.yield_goal=None;self.yield_until=None
        t.peer_route=[];t.peer_route_next=now
        t.path=[];t.path_goal=None;t.next_plan=now;t.progress.reset()

    def observe(self,world,rid,now):
        """Two admitted own RGB measurements, in the own issued-odometry frame."""
        fresh=set(world['visibility'][rid]['peers'])
        self.velocity={}
        for peer in fresh:
            xy=tuple(world['robots'][peer]['pose'][:2]);old=self.previous.get(peer)
            if old and now>old[0]:
                self.velocity[peer]=tuple((a-b)/(now-old[0]) for a,b in zip(xy,old[1]))
            self.previous[peer]=(now,xy)

    def predicted_discs(self,world,rid,radius,horizon):
        from scripts.zone_teacher import PeerDisc
        extra=.17-radius  # Unchanged folded/unfolded margin from visible_route.
        return [PeerDisc((v['pose'][0]+self.velocity.get(peer,(0.,0.))[0]*horizon,
                          v['pose'][1]+self.velocity.get(peer,(0.,0.))[1]*horizon,.17+extra))
                for peer,v in world['robots'].items() if peer!=rid]

    def audit(self,teacher,world,now,event,goal=None,*,start=None,predicted=()):
        """Named signed gaps, including failure outside any geometric overlap."""
        from sim.grasp_act_visible_route import constraints
        from harness.static_keepouts import rect_distance
        radius,discs,rects=constraints(world,teacher.rid,teacher.folded_ready)
        from scripts.zone_teacher import PeerDisc
        if goal is None:goal=teacher._geometry(world)[3]
        rows=[]
        # constraints has a stable order: peers, other cargo, five beam discs.
        names=[r for r in world['robots'] if r!=teacher.rid]
        names += [k for k in world['objects'] if k!='beam_1']+['beam_1']*5
        names += [r+'_predicted' for r in world['robots'] if r!=teacher.rid][:len(predicted)]
        discs=list(discs)+list(predicted)
        def disc_gap(d):
            if start is None:return math.dist(goal,d[:2])-d[2]-radius
            dx,dy=goal[0]-start[0],goal[1]-start[1];norm=dx*dx+dy*dy
            u=max(0.,min(1.,((d[0]-start[0])*dx+(d[1]-start[1])*dy)/norm)) if norm else 0.
            return math.hypot(start[0]+u*dx-d[0],start[1]+u*dy-d[1])-d[2]-radius
        for name,d in zip(names,discs):
            rows.append(dict(blocked_object=name,min_gap_m=disc_gap(d),
                reason_category='peer_goal' if isinstance(d,PeerDisc) else 'cargo_goal'))
        observations=world['visibility'][teacher.rid].get('observations',{})
        walls=[k for k,m in observations.items() if m['kind']=='wall']
        for i,r in enumerate(rects):
            # Same 1cm segment sampling as visible_route.segment_free.
            n=max(1,math.ceil(math.dist(start,goal)/.01)) if start is not None else 1
            points=[goal] if start is None else [(start[0]+(goal[0]-start[0])*j/n,start[1]+(goal[1]-start[1])*j/n) for j in range(n+1)]
            rows.append(dict(blocked_object=walls[i] if i<len(walls) else f'visible_wall_{i}',
                min_gap_m=min(rect_distance(p,r)-radius for p in points),reason_category='wall_goal'))
        nearest=min(rows,key=lambda r:r['min_gap_m'])
        row=dict(t=now,event=event,robot=teacher.rid,goal=list(goal),**nearest,
            blocked=nearest['min_gap_m']<0,blockers=[r for r in rows if r['min_gap_m']<0],
            fresh_peers=world['visibility'][teacher.rid]['peers'],
            observed_peer_velocity_m_s=deepcopy(self.velocity),
            gap_scope='visible_model_goal_signed_clearance; not physical clearance')
        self.events.append(row)
        return row

    def retry(self,t,world,now,reason):
        """A local deadline invalidates the plan, never the entire rendezvous.

        The unchanged 12 SIMs encounter timer now triggers replanning. No new
        timeout/tolerance is fitted to this single failure. The runner's same
        60 SIMs cap bounds the episode and is reported separately as cap_end.
        """
        visible=world['beam'] is not None and world['visibility'][t.rid]['visible_probes']>=5
        if visible:
            self.audit(t,world,now,reason)
            # Existing route refresh is 1 SIMs (_peer_route), reused as the
            # prediction horizon. Prediction never removes current keepouts.
            self.yield_goal=self.select_wait(t,world,now,horizon=1.)
            self.yield_until=now+1. if self.yield_goal is not None else None
        else:
            # No hidden cargo geometry read to select a wait position.
            self.events.append(dict(t=now,event=reason,robot=t.rid,reason_category='target_not_visible',
                blocked_object='assigned_band_not_visible',min_gap_m=None,
                gap_scope='not_geometric; no cargo position read'))
            self.yield_goal=None
            self.yield_until=None
        if t.reobserver.active:t.reobserver.finish(t,now,'rendezvous_replan')
        t.peer_wait_since=None;t.peer_wait_ids.clear();t.peer_clear_since=None
        t.peer_route=[];t.path=[];t.path_goal=None;t.next_plan=now;t.peer_route_next=now
        t.peer_trigger.reset();t.peer_progress.reset();t.progress.reset()
        t.peer_motion={};t.peer_motion_t=now;t.outcome=None

    def select_wait(self,t,world,now,*,horizon):
        from sim.grasp_act_visible_route import constraints,free,segment_free
        pose=world['robots'][t.rid]['pose'];goal=t._geometry(world)[3]
        radius,discs,rects=constraints(world,t.rid,t.folded_ready)
        predicted=self.predicted_discs(world,t.rid,radius,horizon)
        blockers=[(peer,v) for peer,v in world['robots'].items() if peer!=t.rid]
        if not blockers:return None
        peer,v=min(blockers,key=lambda kv:math.dist(goal,kv[1]['pose'][:2]))
        px,py=v['pose'][:2];vx,vy=self.velocity.get(peer,(0.,0.))
        # Positive dot product means the current blocker is leaving the goal.
        if (px-goal[0])*vx+(py-goal[1])*vy>0:
            self.audit(t,world,now,'moving_peer_replan',goal)
            return None
        dx,dy=pose[0]-px,pose[1]-py;norm=math.hypot(dx,dy)
        if norm==0:return None
        ux,uy=dx/norm,dy/norm
        # One existing inflated peer exclusion diameter, not a new tolerance.
        step=radius+.17+(.17-radius)
        candidates=[('back',(pose[0]+step*ux,pose[1]+step*uy)),
                    ('left',(pose[0]-step*uy,pose[1]+step*ux)),
                    ('right',(pose[0]+step*uy,pose[1]-step*ux))]
        candidates.sort(key=lambda x:(math.dist(x[1],goal),x[0]))
        for name,p in candidates:
            if name in self.retired:continue
            row=self.audit(t,world,now,'wait_candidate',p,start=pose[:2],predicted=predicted)
            valid=(free(p,discs+predicted,rects,radius)
                and segment_free(pose[:2],p,discs+predicted,rects,radius)
                and t.bounds[0]<=p[0]<=t.bounds[1] and t.bounds[2]<=p[1]<=t.bounds[3])
            row['accepted']=valid;row['candidate']=name
            if not valid:continue
            self.visits[name]=self.visits.get(name,0)+1 if self.last_choice==name else 1
            self.last_choice=name
            # User 2026-10-15: remove an unchanged choice after three repeats.
            if self.visits[name]>=3:self.retired.add(name);row['accepted']=False;row['reason_category']='unchanged_choice_3';continue
            return p
        return None


class RendezvousTeacherMixin:
    """Opt-in patch around the pinned common teacher, without copying its path."""
    def _step(self,world,now,*,permit_pick):
        rv=self.rendezvous
        if rv.mode=='off':return super()._step(world,now,permit_pick=permit_pick)
        rv.observe(world,self.rid,now)
        rv.expire_yield(self,world,now)
        # Intercept the legacy early return *before* it can terminate the peer.
        if self.peer_wait_since is not None and now-self.peer_wait_since>=12.-1e-8:
            rv.retry(self,world,now,'encounter_deadline_replan')
        value,done=super()._step(world,now,permit_pick=permit_pick)
        if self.outcome=='approach_blocked_handoff' and self.peer_wait_since is not None:
            rv.retry(self,world,now,'peer_no_progress_replan')
            return self._hold(now),False
        return value,done

    def _peer_route(self,world,goal,now):
        rv=self.rendezvous
        if rv.mode=='off':return super()._peer_route(world,goal,now)
        if rv.yield_goal is not None:
            from sim.grasp_act_visible_route import constraints,segment_free,drive
            from harness.grasp_act_visible_world import command_delta
            pose=world['robots'][self.rid]['pose'];radius,discs,rects=constraints(world,self.rid,self.folded_ready)
            # One actual control pulse (.1 SIMs), already fixed by the runner.
            predicted=rv.predicted_discs(world,self.rid,radius,.1)
            value=self._continuous(now,**drive(pose,rv.yield_goal,rv.yield_goal,world['beam']['ends'][self.end]))
            dx,dy,_=command_delta(value,.1,mode=self.search15_modes['search17_odometry']);co,si=math.cos(pose[2]),math.sin(pose[2])
            end=(pose[0]+co*dx-si*dy,pose[1]+si*dx+co*dy)
            if not segment_free(pose[:2],end,discs+predicted,rects,radius):
                rv.audit(self,world,now,'yield_pulse_blocked',end,start=pose[:2],predicted=predicted);rv.yield_goal=None
            else:
                # Mathematical completion at the current issued pulse's
                # reach, without introducing an arrival tolerance.
                if math.dist(pose[:2],rv.yield_goal)<=math.hypot(dx,dy):rv.yield_goal=None
                return value
        value=super()._peer_route(world,goal,now)
        if self.peer_wait_since is not None:
            rv.audit(self,world,now,'peer_wait')
        return value

    def diagnostic(self):
        d=super().diagnostic()
        d['peer_rendezvous']=self.rendezvous.mode;d['rendezvous_log']=self.rendezvous.events
        return d
