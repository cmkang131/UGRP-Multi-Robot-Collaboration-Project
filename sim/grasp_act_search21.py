"""Fresh relative-geometry admission and bounded collision-checked reobservation.

Only current own-camera measurements authorize a new grasp stance. Remembered
hazards keep search20's 140mm envelope; fresh geometry uses search19's geometric
5mm padding. Neither padding is a probabilistic safety bound. No truth inputs.
"""
import math
from sim.grasp_act_search20 import BodyNavigation as Search20Navigation, ADMIT_MARGIN_M
from sim.grasp_act_search18 import body_clearance

MODES = {'search21': 'search21_v1'}
FRESH_MARGIN_M = .005


def enabled(t):
    return t.search15_modes.get('search21', 'off') != 'off'


class BodyNavigation(Search20Navigation):
    def __init__(self, teacher, world, *, admission=False):
        super().__init__(teacher, world, admission=admission)
        self.admission = admission
        obs = world['visibility'][teacher.rid].get('observations', {})
        def fresh(key):
            return obs.get(key, {}).get('seen_t', -math.inf) >= world['t']-1e-8
        labels = [r for r in world['robots'] if r != teacher.rid]
        labels += [k for k in world['objects'] if k != 'beam_1']
        labels += ['band_'+teacher.end]*5 if world['beam'] else []
        self.disc_margins = [FRESH_MARGIN_M if fresh(k) else ADMIT_MARGIN_M for k in labels]
        self.rect_margins = [FRESH_MARGIN_M if any(m['kind']=='wall' and fresh(k)
            and tuple((*m['xyz'][:2],*m['half_extents'],m['yaw'])) == tuple(rect)
            for k,m in obs.items()) else ADMIT_MARGIN_M for rect in self.rects]
        self.fresh_target = fresh('band_'+teacher.end)

    def free(self, p, discs, rects, radius, *, heading=None):
        if not self.admission:
            return super().free(p, discs, rects, radius, heading=heading)
        self.check_budget()
        if not self.fresh_target:
            return False
        yaw = self.heading(p) if heading is None else heading
        pose = (*p[:2],yaw)
        key=('search21',self.scene_key,tuple(self.disc_margins),tuple(self.rect_margins),pose)
        cache=self.teacher.search20_cache
        if key in cache:
            if self.teacher.search20_budget is not None:self.teacher.search20_budget.hits+=1
            cache.move_to_end(key)
            return cache[key]
        result=(body_clearance(pose,[],[],bounds=self.bounds) >= FRESH_MARGIN_M
            and all(body_clearance(pose,[d],[],need=m) >= m for d,m in zip(self.discs,self.disc_margins))
            and all(body_clearance(pose,[],[r],need=m) >= m for r,m in zip(self.rects,self.rect_margins)))
        cache[key]=result
        if len(cache)>4096:cache.popitem(last=False)
        return result


    def pose_segment(self, a, b):
        if not self.admission:return super().pose_segment(a,b)
        da=math.atan2(math.sin(b[2]-a[2]),math.cos(b[2]-a[2]))
        n=max(1,math.ceil(math.dist(a[:2],b[:2])/.002),math.ceil(abs(da)/math.radians(.5)))
        return all(self.free((a[0]+(b[0]-a[0])*i/n,a[1]+(b[1]-a[1])*i/n),(),(),0.,
            heading=a[2]+da*i/n) for i in range(n+1))


    def plan_path(self,start,goal,bounds,discs,*,rects=(),radius=.13):
        if not self.admission:return super().plan_path(start,goal,bounds,discs,rects=rects,radius=radius)
        # Visibility-graph connectors before the grid search. Each complete
        # polyline is swept with exactly the same body/arm/view checks.
        heading=self.heading(goal);dx=goal[0]-start[0];dy=goal[1]-start[1]
        norm=max(math.hypot(dx,dy),1e-9);normal=(-dy/norm,dx/norm)
        routes=[[tuple(start),tuple(goal)]]
        for back in (.15,.30,.45):
            entry=(goal[0]-back*math.cos(heading),goal[1]-back*math.sin(heading))
            for side in (0.,-.25,.25,-.5,.5):
                mid=((start[0]+entry[0])/2+side*normal[0],(start[1]+entry[1])/2+side*normal[1])
                routes.append([tuple(start),mid,entry,tuple(goal)])
        for route in routes:
            if all(self.segment_free(a,b,discs,rects,radius) for a,b in zip(route,route[1:])):
                return route
        # Keep work finite; the recovery skill handles an empty connector set.
        return None


    def path_for_goal(self,start,goal,discs,rects,radius):
        old=self.teacher.path
        if len(old)>=2:
            i,_,_=route_projection(start,old)
            remaining=[tuple(start),*old[i+1:-1],tuple(goal)]
            if all(self.segment_free(a,b,discs,rects,radius) for a,b in zip(remaining,remaining[1:])):
                return remaining
        return self.plan_path(start,goal,self.bounds,discs,rects=rects,radius=radius)

    def waypoint(self,start,path,discs,rects,radius):
        if len(path)<2:return None
        i,_,_=route_projection(start,path)
        best=None
        for p in path[i+1:]:
            if math.dist(start,p)<.001:continue
            if self.segment_free(start,p,discs,rects,radius):
                best=p
                if math.dist(start,p)>=.12:break
            elif best is not None:break
        return best


def fallback(t,world,now,choices):
    """Stop at the first fully checked stance; no partial plan on budget expiry."""
    from sim.grasp_act_pregrasp import select_sampled_goal
    from sim.grasp_act_search22 import enabled as search22, BodyNavigation as Search22Navigation
    nav=(Search22Navigation if search22(t) else BodyNavigation)(t,world,admission=True)
    if search22(t):t.search22_targets={}
    checked=[]
    # Deterministic original choice order; jaw/IK/path/arm remain mandatory.
    for choice in sorted(choices,key=lambda q:(abs(q[0]),-q[1],q[0])):
        if search22(t):nav.path_blockers=[]
        selected,rows=select_sampled_goal(world,t.rid,t.end,t.bounds,t.folded_ready,
            t.sink.pwm,choices=[choice],navigation=nav)
        if search22(t):
            for row in rows:row['path_memory_blockers']=list(nav.path_blockers)
        checked+=rows
        if search22(t):
            from sim.grasp_act_search22 import record_candidates
            record_candidates(t,world,rows,now)
        if selected is not None:
            t.search19_body_active=True;t.sampled_stance=True
            t.search21_log.append({'t':now,'event':'fresh_stance_admitted','choice':choice,
                'fresh_margin_m':FRESH_MARGIN_M,'remembered_margin_m':ADMIT_MARGIN_M})
            return selected,checked
    return None,checked


def schedule(t, world, now, *, force=False):
    """Keep an executable reobserve skill after an empty stance set, twice only."""
    if not enabled(t) or t.outcome is not None or t.reobserver.active is not None:
        return
    if t.search21_recovery is not None or t.search21_encounters >= 2:
        return
    if not force and (t.approach_blocked_since is None or now-t.approach_blocked_since < 2.):
        return
    t.search21_encounters += 1
    t.search21_recovery = {'start':now,'origin':tuple(world['robots'][t.rid]['pose'][:2]),
        'direction':None,'unchanged':0,'distance':0.,'excluded':[]}
    t.approach_blocked_since = None
    from sim.grasp_act_search22 import enabled as search22
    if search22(t) and t.search22_targets:
        targets={k:m for k,m in t.search22_targets.items()
            if world['visibility'][t.rid]['observations'].get(k,m)['seen_t']<now-1e-8}
        if targets:t.search21_recovery['target']=min(targets.items(),
            key=lambda kv:math.dist(world['robots'][t.rid]['pose'][:2],kv[1]['xyz'][:2]))
    t.search21_log.append({'t':now,'event':'empty_set_reobserve','encounter':t.search21_encounters})


def recovery_step(t, world, now, before):
    from sim.grasp_act_search19 import admitted
    from sim.grasp_act_visible_gaze import gaze_pose
    from sim.grasp_act_gaze import slew
    from sim.grasp_act_teacher import local
    state = t.search21_recovery
    pose = world['robots'][t.rid]['pose']
    age = now-state['start']
    distance = math.dist(pose[:2],state['origin'])
    if age >= 1.4-1e-8:
        t.search21_log.append({'t':now,'event':'reobserve_replan','issued_distance_m':distance})
        t.search21_recovery = None
        t.path=[];t.path_goal=None;t.next_plan=now;t.approach_plan_valid=False
        t.progress.reset();t.search21_progress=None
        return t._hold(now),False
    # Real camera movement after the checked retreat/sidestep. An old bearing
    # is a search direction only; it cannot authorize an unseen grasp target.
    if age >= .8 or distance >= .04:
        goal = dict(t.sink.pwm)
        goal[6] = (1000 if age < 1.1 else 2000)
        t.sink.pwm.update(slew(t.sink.pwm,goal));t.arm.commanded.update(t.sink.pwm)
        return t._hold(now),False
    if world['beam'] is not None:
        q=local(pose,world['beam']['ends'][t.end])
        t.sink.pwm.update(slew(t.sink.pwm,gaze_pose((q[0],q[1],world['beam']['ends'][t.end][2]+.009),t.sink.pwm)))
        t.arm.commanded.update(t.sink.pwm)
    # A bounded velocity fan; both issued models and complete arm sweep admit
    # the actual pulse. No obstacle deletion or occupied-start clearing.
    t.search19_body_active=True;t.sampled_stance=True
    for direction in (math.pi, math.pi/2, -math.pi/2, 3*math.pi/4, -3*math.pi/4):
        if direction in state['excluded']:continue
        value=t._continuous(now,.04*math.cos(direction),.04*math.sin(direction),0.)
        if not admitted(t,world,value,before):continue
        state['unchanged']=(state['unchanged']+1 if state['direction']==direction and distance-state['distance']<.0001 else 0)
        if state['unchanged']>=3:
            state['excluded'].append(direction)
            t.search21_log.append({'t':now,'event':'unchanged_candidate_removed','direction':direction})
            continue
        state.update(direction=direction,distance=distance)
        t.search21_log.append({'t':now,'event':'reobserve_pulse','direction':direction})
        return value,False
    t.search21_log.append({'t':now,'event':'translation_blocked_camera_reobserve'})
    state['start']=now-.8
    return t._hold(now),False


def route_projection(start,path):
    """Nearest segment, with forward tie-breaking; never return a passed vertex."""
    arc=0.;choices=[]
    for i,(a,b) in enumerate(zip(path,path[1:])):
        dx,dy=b[0]-a[0],b[1]-a[1];length=math.hypot(dx,dy)
        u=max(0.,min(1.,((start[0]-a[0])*dx+(start[1]-a[1])*dy)/max(length*length,1e-15)))
        q=(a[0]+u*dx,a[1]+u*dy);s=arc+u*length
        choices.append((math.dist(start,q),-s,i,q));arc+=length
    _,minus_s,i,q=min(choices)
    return i,q,-minus_s


def route_progress(t,world,goal,heading,now):
    """Monotone arc progress on a fixed checked route; oscillation earns nothing."""
    pose=world['robots'][t.rid]['pose'];state=getattr(t,'search21_progress',None)
    choice=tuple(t.approach_choice)
    if state is None or state['choice']!=choice:
        if len(t.path)<2:return t.progress.observe_goal(pose,goal,heading,now)
        state={'path':[tuple(p) for p in t.path],'choice':choice,'best':None,'since':now,'retried':False}
        t.search21_progress=state
    _,_,arc=route_projection(pose[:2],state['path'])
    if state['best'] is None or arc-state['best']>.01:
        state.update(best=arc,since=now,retried=False)
        return None
    if now-state['since']<3.-1e-8:return None
    event='handoff' if state['retried'] else 'replan'
    state.update(since=now,retried=True)
    t.search21_log.append({'t':now,'event':'route_progress_'+event,'best_arc_m':state['best'],'arc_m':arc})
    return event
