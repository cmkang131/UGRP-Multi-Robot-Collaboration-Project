"""Opt-in cost-aware grid A* and finite dynamic peer observations.

Only the visible/issued world enters here. Inflation is the oriented body
Minkowski sum plus each obstacle's search22 geometric/covariance margin.
This is a holonomic 2-D graph, with heading constrained toward the assigned
visible end; completeness is on that finite graph, subject to the step budget.
"""
import heapq
import math
from functools import lru_cache
from collections import OrderedDict
import numpy as np

from sim.grasp_act_search22 import BodyNavigation as Previous, K, uncertainty
from sim.grasp_act_search21 import FRESH_MARGIN_M
from sim.grasp_act_search18 import HALF_X, HALF_Y
from sim.grasp_act_search20 import PlanningBudgetExceeded

MODES = {'search23': 'search23_v1'}
GRID_M = .025
HEURISTIC_WEIGHT = 2.0
COST_MULTIPLIER = 1.0  # Smac 2D's documented speed-oriented setting
PEER_TTL_S = 2.0
PEER_SIGMA_RATE_M_S = .05  # design assumption, not fitted to evaluation truth

_PICK_CLOUDS=OrderedDict()


@lru_cache(maxsize=1024)
def cached_capsules(items):
    from sim.grasp_act_pregrasp import capsules
    return capsules(dict(items))


@lru_cache(maxsize=512)
def cached_camera(items):
    from sim.grasp_act_gaze import camera_extrinsics
    return camera_extrinsics(dict(items))


def enabled(t):
    return t.search15_modes.get('search23', 'off') != 'off'


def expire_peer_state(t, world, now):
    """Prevent older free-space/reobservation caches from resurrecting peers."""
    for cache in (t.search18_space.ghosts, t.reobserver.hints, t.reobserver.pinned,
                  t.search22_targets):
        for key, m in list(cache.items()):
            if m.get('kind') == 'robot' and now-m['seen_t'] > PEER_TTL_S:
                cache.pop(key, None)
    return world


def rectangle_gaps(xy, yaw, rect):
    """Exact rectangle/rectangle Euclidean distance, batched over body poses."""
    co, si = np.cos(yaw), np.sin(yaw)
    offsets = np.array([[-HALF_X,-HALF_Y],[-HALF_X,HALF_Y],
                        [HALF_X,HALF_Y],[HALF_X,-HALF_Y]])
    body = xy[:,None,:] + np.stack((co[:,None]*offsets[:,0]-si[:,None]*offsets[:,1],
                                    si[:,None]*offsets[:,0]+co[:,None]*offsets[:,1]), axis=2)
    x,y,hx,hy,a = rect; c,s = math.cos(a),math.sin(a)
    q = body - (x,y)
    local = np.stack((q[:,:,0]*c+q[:,:,1]*s,-q[:,:,0]*s+q[:,:,1]*c),axis=2)
    dist1 = np.linalg.norm(np.maximum(np.abs(local)-(hx,hy),0),axis=2).min(axis=1)
    other = np.array([(x+c*u-s*v,y+s*u+c*v) for u,v in
                      ((-hx,-hy),(-hx,hy),(hx,hy),(hx,-hy))])
    q = other[None,:,:]-xy[:,None,:]
    local2 = np.stack((q[:,:,0]*co[:,None]+q[:,:,1]*si[:,None],
                       -q[:,:,0]*si[:,None]+q[:,:,1]*co[:,None]),axis=2)
    dist2 = np.linalg.norm(np.maximum(np.abs(local2)-(HALF_X,HALF_Y),0),axis=2).min(axis=1)
    overlap = np.ones(len(xy),dtype=bool)
    for axis in (np.stack((co,si),axis=1),np.stack((-si,co),axis=1),
                 np.tile((c,s),(len(xy),1)),np.tile((-s,c),(len(xy),1))):
        p = (body*axis[:,None,:]).sum(axis=2)
        q = (other[None,:,:]*axis[:,None,:]).sum(axis=2)
        overlap &= (p.max(axis=1)>=q.min(axis=1)) & (q.max(axis=1)>=p.min(axis=1))
    return np.where(overlap,0,np.minimum(dist1,dist2))


class BodyNavigation(Previous):
    def __init__(self,t,world,*,admission=False):
        super().__init__(t,world,admission=admission)
        self.nodes = {}; self.node_blockers = {}; self.edges = {}; self.edge_gaps = {}
        self.edge_blockers = {}; self.last_path_audit = None
        self.endpoint_only=False;self.endpoints=[];self.preplanned={};self.candidate_rows=[]
        from sim.grasp_act_search26 import connector_cache
        self.connector_cache=connector_cache(t,world)
        self.blocked = {}; self.expanded = 0
        for detail in self.details:
            m=self.world_observations.get(detail['id'])
            if detail['sigma_m'] is not None:
                detail['margin_m']=FRESH_MARGIN_M+K*detail['sigma_m']
            if m is not None and m['kind']=='robot' and not detail['fresh']:
                age=max(0.,world['t']-m['seen_t'])
                base_sigma=(detail['sigma_m'] if detail['sigma_m'] is not None else
                            max(0.,detail['margin_m']-FRESH_MARGIN_M)/K)
                sigma=math.hypot(base_sigma,PEER_SIGMA_RATE_M_S*age)
                detail.update(sigma_m=sigma,margin_m=FRESH_MARGIN_M+K*sigma,
                              dynamic=True,age_s=age,expires_s=PEER_TTL_S)
        self.disc_margins=[d['margin_m'] for d in self.details]
        for i,r in enumerate(self.rects):
            m=next((m for m in self.world_observations.values() if m['kind']=='wall'
                and tuple((*m['xyz'][:2],*m['half_extents'],m['yaw']))==tuple(r)),None)
            info=uncertainty(m,self.pose) if m else None
            if info:self.rect_margins[i]=FRESH_MARGIN_M+K*info['sigma_m']
        self.audit_details=[*self.details,
            *[{'id':self._wall_name(r,i),'fresh':self.world_observations.get(self._wall_name(r,i),{}).get('seen_t',-math.inf)>=world['t']-1e-8,
                'margin_m':m} for i,(r,m) in enumerate(zip(self.rects,self.rect_margins))],
            {'id':'bounds','fresh':True,'margin_m':FRESH_MARGIN_M}]
        from sim.grasp_act_search25 import configure
        configure(self)
        from sim.grasp_act_search27 import enabled as search27,dependencies
        if search27(t,'search_dependency_cache'):
            self.body_dependency=dependencies(self)
            self.connector_dependency=dependencies(self,connector=True)

    def _wall_name(self,r,i):
        return next((k for k,m in self.world_observations.items() if m['kind']=='wall'
            and tuple((*m['xyz'][:2],*m['half_extents'],m['yaw']))==tuple(r)),f'wall:{i}')

    def measure(self,xy,yaw=None):
        self.check_budget()
        from sim.grasp_act_search27 import enabled, memo, dependencies
        if not enabled(self.teacher,'search_dependency_cache'):
            return self._measure(xy,yaw)
        query=(tuple(np.asarray(xy,dtype=float).reshape(-1)),
               None if yaw is None else tuple(np.asarray(yaw,dtype=float).reshape(-1)))
        def compute():
            result=self._measure(xy,yaw)
            return result,self.last_inflation_slack,self.last_blockers
        result,soft,blockers=memo(self.teacher,getattr(self,'check_stage','body_grid'),self.body_dependency,query,compute)
        self.last_inflation_slack=soft;self.last_blockers=blockers
        for row in blockers:
            old=self.blocked.get(row['id'])
            if old is None or row['slack_m']<old['slack_m']:self.blocked[row['id']]=row
        return result

    def _measure(self,xy,yaw=None):
        xy=np.asarray(xy,dtype=float).reshape(-1,2)
        if yaw is None:
            yaw=(np.full(len(xy),self.pose[2]) if self.target is None else
                 np.arctan2(self.target[1]-xy[:,1],self.target[0]-xy[:,0]))
        yaw=np.broadcast_to(yaw,(len(xy),));c,s=np.cos(yaw),np.sin(yaw)
        gaps=[]
        for x,y,r in self.discs:
            dx,dy=x-xy[:,0],y-xy[:,1]
            u=np.maximum(np.abs(c*dx+s*dy)-HALF_X,0.)
            v=np.maximum(np.abs(-s*dx+c*dy)-HALF_Y,0.)
            gaps.append(np.hypot(u,v)-r)
        gaps += [rectangle_gaps(xy,yaw,r) for r in self.rects]
        x0,x1,y0,y1=self.bounds
        ex=np.abs(c)*HALF_X+np.abs(s)*HALF_Y
        ey=np.abs(s)*HALF_X+np.abs(c)*HALF_Y
        gaps.append(np.minimum.reduce((xy[:,0]-ex-x0,x1-xy[:,0]-ex,
                                       xy[:,1]-ey-y0,y1-xy[:,1]-ey)))
        gaps=np.stack(gaps,axis=1)
        from sim.grasp_act_search25 import hard_margins
        margins=np.array(hard_margins(self))
        self.last_inflation_slack=gaps-np.array([d['margin_m'] for d in self.audit_details])
        slack=gaps-margins
        self.last_blockers=[]
        for j in np.flatnonzero((slack<0).any(axis=0)):
            i=int(np.argmin(slack[:,j]));d=self.audit_details[j];key=d['id']
            row={**d,'gap_m':float(gaps[i,j]),'slack_m':float(slack[i,j]),
                 'sample_pose':[*map(float,xy[i]),float(yaw[i])],
                 'category':'memory_margin' if not d['fresh'] and gaps[i,j]>=FRESH_MARGIN_M else 'current_geometry'}
            old=self.blocked.get(key)
            if old is None or row['slack_m']<old['slack_m']:self.blocked[key]=row
            self.last_blockers.append(row)
        return gaps,slack

    def free(self,p,discs,rects,radius,*,heading=None):
        if not self.fresh_target:return False
        _,slack=self.measure([p[:2]],self.heading(p) if heading is None else heading)
        return bool((slack>=0).all())

    def candidate_audit(self,p,heading):
        gaps,slack=self.measure([p[:2]],heading)
        return [{**d,'gap_m':float(gaps[0,j]),'blocked':bool(slack[0,j]<0),
            'category':'memory_margin' if not d['fresh'] and gaps[0,j]>=FRESH_MARGIN_M else 'current_geometry'}
            for j,d in enumerate(self.audit_details)]

    def pose_segment(self,a,b):
        da=math.atan2(math.sin(b[2]-a[2]),math.cos(b[2]-a[2]))
        n=max(1,math.ceil(math.dist(a[:2],b[:2])/.002),math.ceil(abs(da)/math.radians(.5)))
        u=np.linspace(0.,1.,n+1)
        xy=np.asarray(a[:2])+u[:,None]*(np.asarray(b[:2])-a[:2])
        self.check_stage='body_edge'
        try:_,slack=self.measure(xy,a[2]+u*da)
        finally:self.check_stage='body_grid'
        self.last_segment_gap=float((slack+np.array([d['margin_m'] for d in self.audit_details])).min())
        if self.inflation_soft:
            from sim.grasp_act_search25 import segment_envelope
            self.last_segment_gap=float(slack.min())
            envelope=segment_envelope(a,b,n)
            if (slack<=envelope).any() and not self.last_blockers:
                i,j=np.unravel_index(np.argmin(slack),slack.shape)
                self.last_blockers=[{**self.audit_details[j],'gap_m':float(slack[i,j]),
                    'slack_m':float(slack[i,j]-envelope),
                    'sample_pose':[*map(float,xy[i]),float(a[2]+u[i]*da)],
                    'margin_m':envelope,'category':'interpolation_envelope',
                    'gap_scope':'body gap versus nearest-sample displacement bound'}]
            return bool(self.fresh_target and (slack>envelope).all())
        return bool(self.fresh_target and (slack>=0).all())

    def connector_sample(self,prior,before,xy,yaw):
        from sim.grasp_act_search27 import enabled,memo,dependencies
        if not enabled(self.teacher,'search_dependency_cache'):
            return self._connector_sample(prior,before,xy,yaw)
        query=(tuple(prior),tuple(sorted(before.items())),tuple(xy),yaw)
        def compute():
            result=self._connector_sample(prior,before,xy,yaw)
            return result,list(getattr(self,'visibility_audit',[])),list(getattr(self,'connector_collision_audit',[]))
        result,view,arm=memo(self.teacher,'connector_view_arm',self.connector_dependency,query,compute)
        self.visibility_audit=view;self.connector_collision_audit=arm
        return result

    def _connector_sample(self,prior,before,xy,yaw):
        """Exact snapshot cache of the unchanged view and issued-arm checks."""
        from sim.grasp_act_pregrasp import band_view,issued_sweep_reason
        from sim.grasp_act_teacher import wrap
        key=(tuple(prior),tuple(sorted(before.items())),tuple(xy),yaw)
        if key in self.connector_cache:
            if self.teacher.search20_budget is not None:self.teacher.search20_budget.hits+=1
        if key not in self.connector_cache:
            count,after=band_view(self.world,self.rid,self.end,(*xy,yaw),before,navigation=self)
            reason=None;audit=[]
            if count>=5:
                c,s=math.cos(prior[2]),math.sin(prior[2]);dx,dy=xy[0]-prior[0],xy[1]-prior[1]
                da=wrap(yaw-prior[2])
                from sim.grasp_act_search27 import enabled as search27,arm_sweep
                sweep=(lambda *a,**kw:arm_sweep(self.teacher,*a,**kw)) if search27(self.teacher,'search_dependency_cache') else issued_sweep_reason
                reason=sweep(self.world,self.rid,prior,before,after,
                    (c*dx+s*dy,-s*dx+c*dy,da),audit=audit if self.teacher.search15_modes.get('search24_irm','off')!='off' else None)
            self.connector_cache[key]=(count,after,reason,list(getattr(self,'visibility_audit',[])),audit)
        count,after,reason,visibility,collision=self.connector_cache[key]
        self.visibility_audit=visibility;self.connector_collision_audit=collision
        return count,after,reason

    def camera_extrinsics(self,pwm):
        return cached_camera(tuple(sorted(pwm.items())))

    def wall_segment_free(self,start,end,radius):
        # SAME 1cm samples and margin-escape limits as visible_route.segment_free.
        from scripts.zone_teacher import _wall_limits
        dx,dy=end[0]-start[0],end[1]-start[1]
        n=max(1,math.ceil(math.sqrt(dx*dx+dy*dy)/.01));i=np.arange(n+1)
        x=start[0]+dx*i/n;y=start[1]+dy*i/n
        for wi,((cx,cy,hx,hy,a),limit) in enumerate(_wall_limits(start,self.rects,radius)):
            u,v=x-cx,y-cy
            if a:
                c,s=math.cos(a),math.sin(a);u,v=c*u+s*v,-s*u+c*v
            gap=np.hypot(np.maximum(np.abs(u)-hx,0.),np.maximum(np.abs(v)-hy,0.))
            if not np.all(gap>=limit):
                self.last_wall_blocker={'id':self._wall_name(self.rects[wi],wi),'gap_m':float(gap.min()),
                    'category':'visibility','gap_scope':'sampled sight ray to wall surface'}
                return False
        return True

    def pick_cloud(self,view,distance,z):
        from sim.grasp_act_teacher import grasp_poses
        from sim.grasp_act_pregrasp import actual_pick_cloud
        from sim.grasp_act_search24 import enabled as irm, certified_poses
        poses=certified_poses(distance,z) if irm(self.teacher) else None
        hover,descent=grasp_poses((distance,0.,z)) if poses is None else poses
        states=[view,{**view,**hover,1:2000}]
        states.extend({**states[-1],**p,1:2000} for p in descent)
        states.extend([{**states[-1],1:1500},{**states[-1],**hover,1:1500}])
        # Equivalent IK commands, not rounded distance/height, identify a cloud.
        key=tuple(tuple(sorted(p.items())) for p in states);self.check_budget()
        from sim.grasp_act_search27 import enabled as search27,stats
        if search27(self.teacher,'search_dependency_cache'):
            count=stats(self.teacher,'pick_cloud');count['calls']+=1
            count['cache_hits' if key in _PICK_CLOUDS else 'computed']+=1
        from sim.grasp_act_search24 import compute_budget
        deterministic=compute_budget(self.teacher)
        if deterministic:
            # Charge the SAME logical samples on cold and warm global caches.
            # Cache warmth may change runtime, never budget admission/results.
            for a,b in zip(states,states[1:]):
                n=max(1,math.ceil(max(abs(a[k]-b[k]) for k in a)/5))
                for _ in range(n+1):self.check_budget()
        if key not in _PICK_CLOUDS:
            _PICK_CLOUDS[key]=actual_pick_cloud(view,(distance,0.,z),check_budget=None if deterministic else self.check_budget,
                capsule_fn=lambda p:cached_capsules(tuple(sorted(p.items()))),poses=poses)
            if len(_PICK_CLOUDS)>32:_PICK_CLOUDS.popitem(last=False)
        _PICK_CLOUDS.move_to_end(key)
        return _PICK_CLOUDS[key]

    def path_for_goal(self,start,goal,discs,rects,radius):
        # Every replan searches the current inflated map. No static route family.
        if tuple(goal) in self.preplanned:return self.preplanned[tuple(goal)]
        return self.plan_path(start,goal,self.bounds,discs,rects=rects,radius=radius)

    def plan_path(self,start,goal,bounds,discs,*,rects=(),radius=.13):
        return self.plan_paths(start,[tuple(goal)])

    def plan_paths(self,start,goals):
        self.blocked={};self.expanded=0;path=None;prefix=[tuple(start)];status='no_path'
        self.best_prefix=prefix
        try:
            if self.free(start,(),(),0.,heading=self.pose[2]):
                goals=[tuple(g) for g in goals if self.free(g,(),(),0.)]
                if goals:path,prefix=self.grid_path(tuple(start),goals)
            if path:status='found'
            return path
        except PlanningBudgetExceeded:
            status='planning_budget';raise
        finally:
            attempted=path or self.best_prefix
            self.last_path_audit={'status':status,'grid_m':GRID_M,'heuristic_weight':HEURISTIC_WEIGHT,
                'expanded':self.expanded,'path_length_m':sum(math.dist(a,b) for a,b in zip(attempted,attempted[1:])),
                'length_scope':'accepted_path' if path else 'best_explored_prefix',
                'min_gap_m':None,'min_gap_scope':'accepted_path' if path else 'blocked_frontier',
                'blocked_obstacles':list(self.blocked.values())}
            # Collision samples carry exact finite gaps; a failed path has no
            # accepted full-path clearance. Do not invent a path length/gap.
            if path:
                self.last_path_audit['min_gap_m']=min(self.edge_gaps[(a,b)] for a,b in zip(path,path[1:]))
            elif self.blocked:self.last_path_audit['min_gap_m']=min(d['gap_m'] for d in self.blocked.values())
            self.path_blockers=[d for d in self.blocked.values() if d['category']=='memory_margin']
            if not path:
                for d in self.path_blockers:
                    if d['id'] in self.world_observations:
                        self.teacher.search22_targets[d['id']]=self.world_observations[d['id']]
            self.teacher.search23_log.append({'t':self.world['t'],'event':'grid_plan',
                'start':list(start),'goals':[list(g) for g in goals],**self.last_path_audit})

    def grid_path(self,start,goals):
        x0,x1,y0,y1=self.bounds;step=GRID_M
        def heuristic(p):return min(math.dist(p,g) for g in goals)
        def point(k):return (x0+k[0]*step,y0+k[1]*step)
        nx,ny=math.floor((x1-x0)/step),math.floor((y1-y0)/step)
        def inside(k):return 0<=k[0]<=nx and 0<=k[1]<=ny
        def nodes(keys):
            missing=[k for k in keys if k not in self.nodes and inside(k)]
            if missing:
                _,slack=self.measure([point(k) for k in missing])
                for k,s,soft in zip(missing,slack,self.last_inflation_slack):
                    cost_slack=soft if self.inflation_soft else s
                    # Nav2 documented cost_scaling_factor=10.0; existing
                    # search23 COST_MULTIPLIER=1.0 is unchanged.
                    self.nodes[k]=(bool((s>=0).all()),1.+COST_MULTIPLIER*math.exp(-10.*max(0.,float(cost_slack.min()))))
                    # Exact point audits are evaluated only for rejected nodes.
                    self.node_blockers[k]=[d for d in self.last_blockers
                        if d['sample_pose'][:2]==list(point(k))]
            for k in keys:
                for d in self.node_blockers.get(k,[]):self.blocked.setdefault(d['id'],d)
        def edge(a,b):
            key=(a,b)
            if key not in self.edges:
                self.edges[key]=self.segment_free(a,b,(),(),0.)
                self.edge_gaps[key]=self.last_segment_gap
                self.edge_blockers[key]=list(self.last_blockers)
            for d in self.edge_blockers[key]:self.blocked.setdefault(d['id'],d)
            return self.edges[key]
        for goal in sorted(goals,key=lambda g:math.dist(start,g)):
            if edge(start,goal):return [start,goal],[start,goal]
        # Reverse multi-source A*: escape the small stance region first,
        # instead of filling the entire room before entering its narrow mouth.
        queue=[];cost={};parent={};terminal={};best=None
        def push(k,g):heapq.heappush(queue,(g+HEURISTIC_WEIGHT*math.dist(point(k),start),g,k))
        def route(k):
            result=[point(k)]
            while parent[k] is not None:k=parent[k];result.append(point(k))
            return [start,*result,terminal[k]]
        for goal in goals:
            cell=(round((goal[0]-x0)/step),round((goal[1]-y0)/step))
            seeds=[(cell[0]+i,cell[1]+j) for i in (-1,0,1) for j in (-1,0,1)]
            nodes(seeds)
            for k in seeds:
                if k in self.nodes and self.nodes[k][0] and edge(point(k),goal):
                    g=math.dist(goal,point(k))*self.nodes[k][1]
                    if g>=cost.get(k,math.inf):continue
                    cost[k]=g;parent[k]=None;terminal[k]=goal;push(k,g)
        moves=((-1,-1),(-1,0),(-1,1),(0,-1),(0,1),(1,-1),(1,0),(1,1))
        expanded_cost={}
        while queue:
            self.check_budget();_,g,k=heapq.heappop(queue)
            if g!=cost[k] or g>=expanded_cost.get(k,math.inf):continue
            expanded_cost[k]=g;self.expanded+=1;p=point(k)
            if best is None or math.dist(p,start)<math.dist(point(best),start):best=k
            # A reverse-search prefix runs from a stance toward the actual start.
            self.best_prefix=list(reversed(route(best)[1:]))
            if math.dist(p,start)<=step*1.5 and edge(start,p):return route(k),self.best_prefix
            adjacent=[(k[0]+i,k[1]+j) for i,j in moves];nodes(adjacent)
            for n in adjacent:
                if n not in self.nodes or not self.nodes[n][0]:continue
                q=point(n);ng=g+math.dist(p,q)*(self.nodes[k][1]+self.nodes[n][1])/2
                if ng>=cost.get(n,math.inf) or not edge(q,p):continue
                cost[n]=ng;parent[n]=k;terminal[n]=terminal[k];push(n,ng)
        return None,self.best_prefix



def fallback(t,world,now,choices):
    """One multi-goal search avoids starving later admissible stance endpoints."""
    from sim.grasp_act_pregrasp import select_sampled_goal
    from sim.grasp_act_search22 import record_candidates
    nav=BodyNavigation(t,world,admission=True);nav.endpoint_only=True
    from sim.grasp_act_search24 import enabled as irm, choices_for_world
    if irm(t):choices=choices_for_world(t,world)
    from sim.grasp_act_search27 import enabled as search27
    detailed=search27(t);endpoint_logged=False
    t.search22_targets={};rows=[]
    try:
        _,rows=select_sampled_goal(world,t.rid,t.end,t.bounds,t.folded_ready,
            t.sink.pwm,choices=choices,navigation=nav)
        if detailed:
            from copy import deepcopy
            record_candidates(t,world,deepcopy(rows),now);endpoint_logged=True
        nav.endpoint_only=False
        by_goal={tuple(e['goal']):e for e in nav.endpoints}
        while by_goal:
            path=nav.plan_paths(world['robots'][t.rid]['pose'][:2],list(by_goal))
            if path is None:
                for row in rows:
                    if row['reason']=='endpoint_feasible':row.update(reason='no_path',path_audit=nav.last_path_audit)
                return None,rows
            endpoint=by_goal.pop(tuple(path[-1]));nav.preplanned[tuple(path[-1])]=path
            selected,checked=select_sampled_goal(world,t.rid,t.end,t.bounds,t.folded_ready,
                t.sink.pwm,choices=[endpoint['choice']],navigation=nav)
            if detailed:record_candidates(t,world,checked,now)
            row=next(r for r in rows if r['offset_deg']==math.degrees(endpoint['choice'][0])
                and r['distance_m']==endpoint['choice'][1])
            row.update(checked[0])
            if selected is not None:
                t.search19_body_active=True;t.sampled_stance=True
                return selected,rows
            failure=row.get('connector_visibility_failure')
            if failure:
                heading=endpoint['heading'];goal=endpoint['goal']
                retreat=(goal[0]-.06*math.cos(heading),goal[1]-.06*math.sin(heading))
                route=[tuple(world['robots'][t.rid]['pose'][:2]),*path,retreat]
                i=failure['segment_index'];a,b=route[i:i+2]
                t.search23_log.append({'t':now,'event':'connector_visibility_replan',
                    'edge':[a,b],**failure})
                # Keep the unchanged >=5-probe rule: reject this failed route
                # edge and search again for the SAME endpoint as well as others.
                if a!=b and i<len(route)-2:
                    nav.edges[(a,b)]=False
                    nav.edges[(b,a)]=False
                    by_goal[tuple(goal)]=endpoint
        return None,rows
    finally:
        # Partial endpoint trials are explicitly labelled on a deadline.
        if not rows:rows=nav.candidate_rows
        if t.search20_budget is not None and t.search20_budget.exhausted:
            for row in rows:
                if row.get('reason') in (None,'endpoint_feasible'):row['reason']='planning_budget'
        if not detailed:
            record_candidates(t,world,rows,now)
        else:
            import sys
            error=sys.exc_info()[1]
            if error is not None or not endpoint_logged:
                partial=nav.candidate_rows
                from sim.grasp_act_search20 import PlanningSafetyCap
                reason='cap_end' if isinstance(error,PlanningSafetyCap) else 'budget_incomplete'
                for row in partial:
                    if row.get('reason') is None:row['reason']=reason
                if partial:record_candidates(t,world,partial,now)
