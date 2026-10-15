"""Opt-in cost-aware grid A* and finite dynamic peer observations.

Only the visible/issued world enters here. Inflation is the oriented body
Minkowski sum plus each obstacle's search22 geometric/covariance margin.
This is a holonomic 2-D graph, with heading constrained toward the assigned
visible end; completeness is on that finite graph, subject to the step budget.
"""
import heapq
import math
import numpy as np

from sim.grasp_act_search22 import BodyNavigation as Previous, K
from sim.grasp_act_search21 import FRESH_MARGIN_M
from sim.grasp_act_search18 import HALF_X, HALF_Y
from sim.grasp_act_search20 import PlanningBudgetExceeded

MODES = {'search23': 'search23_v1'}
GRID_M = .025
HEURISTIC_WEIGHT = 1.2
PEER_TTL_S = 2.0
PEER_SIGMA_RATE_M_S = .05  # design assumption, not fitted to evaluation truth


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
        self.blocked = {}; self.expanded = 0
        for detail in self.details:
            m=self.world_observations.get(detail['id'])
            if m is not None and m['kind']=='robot' and not detail['fresh']:
                age=max(0.,world['t']-m['seen_t'])
                sigma=math.hypot(detail['sigma_m'] or 0.,PEER_SIGMA_RATE_M_S*age)
                detail.update(sigma_m=sigma,margin_m=FRESH_MARGIN_M+K*sigma,
                              dynamic=True,age_s=age,expires_s=PEER_TTL_S)
        self.disc_margins=[d['margin_m'] for d in self.details]
        self.audit_details=[*self.details,
            *[{'id':self._wall_name(r,i),'fresh':m==FRESH_MARGIN_M,
                'margin_m':m} for i,(r,m) in enumerate(zip(self.rects,self.rect_margins))],
            {'id':'bounds','fresh':True,'margin_m':FRESH_MARGIN_M}]

    def _wall_name(self,r,i):
        return next((k for k,m in self.world_observations.items() if m['kind']=='wall'
            and tuple((*m['xyz'][:2],*m['half_extents'],m['yaw']))==tuple(r)),f'wall:{i}')

    def measure(self,xy,yaw=None):
        self.check_budget()
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
        margins=np.array([d['margin_m'] for d in self.audit_details])
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
        _,slack=self.measure(xy,a[2]+u*da)
        self.last_segment_gap=float((slack+np.array([d['margin_m'] for d in self.audit_details])).min())
        return bool(self.fresh_target and (slack>=0).all())

    def path_for_goal(self,start,goal,discs,rects,radius):
        # Every replan searches the current inflated map. No static route family.
        return self.plan_path(start,goal,self.bounds,discs,rects=rects,radius=radius)

    def plan_path(self,start,goal,bounds,discs,*,rects=(),radius=.13):
        self.blocked={};self.expanded=0;path=None;prefix=[tuple(start)];status='no_path'
        self.best_prefix=prefix
        try:
            if self.free(start,(),(),0.,heading=self.pose[2]) and self.free(goal,(),(),0.):
                path,prefix=self.grid_path(tuple(start),tuple(goal))
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
                'start':list(start),'goal':list(goal),**self.last_path_audit})

    def grid_path(self,start,goal):
        x0,x1,y0,y1=self.bounds;step=GRID_M
        def point(k):return (x0+k[0]*step,y0+k[1]*step)
        nx,ny=math.floor((x1-x0)/step),math.floor((y1-y0)/step)
        def inside(k):return 0<=k[0]<=nx and 0<=k[1]<=ny
        def nodes(keys):
            missing=[k for k in keys if k not in self.nodes and inside(k)]
            if missing:
                _,slack=self.measure([point(k) for k in missing])
                for k,s in zip(missing,slack):
                    self.nodes[k]=(bool((s>=0).all()),1.+2.*math.exp(-10.*max(0.,float(s.min()))))
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
        if edge(start,goal):return [start,goal],[start,goal]
        cell=(round((start[0]-x0)/step),round((start[1]-y0)/step))
        seeds=[(cell[0]+i,cell[1]+j) for i in (-1,0,1) for j in (-1,0,1)]
        nodes(seeds);queue=[];cost={};parent={};best=None
        def push(k,g):heapq.heappush(queue,(g+HEURISTIC_WEIGHT*math.dist(point(k),goal),g,k))
        def route(k):
            result=[point(k)]
            while parent[k] is not None:k=parent[k];result.append(point(k))
            return [start,*reversed(result)]
        for k in seeds:
            if k in self.nodes and self.nodes[k][0] and edge(start,point(k)):
                cost[k]=math.dist(start,point(k))*self.nodes[k][1];parent[k]=None;push(k,cost[k])
        moves=((-1,-1),(-1,0),(-1,1),(0,-1),(0,1),(1,-1),(1,0),(1,1))
        expanded_cost={}
        while queue:
            self.check_budget();_,g,k=heapq.heappop(queue)
            if g!=cost[k] or g>=expanded_cost.get(k,math.inf):continue
            expanded_cost[k]=g;self.expanded+=1;p=point(k)
            if best is None or math.dist(p,goal)<math.dist(point(best),goal):
                best=k;self.best_prefix=route(k)
            if math.dist(p,goal)<=step*1.5 and edge(p,goal):return [*route(k),goal],route(k)
            adjacent=[(k[0]+i,k[1]+j) for i,j in moves];nodes(adjacent)
            for n in adjacent:
                if n not in self.nodes or not self.nodes[n][0]:continue
                q=point(n);ng=g+math.dist(p,q)*(self.nodes[k][1]+self.nodes[n][1])/2
                if ng>=cost.get(n,math.inf) or not edge(p,q):continue
                cost[n]=ng;parent[n]=k;push(n,ng)
        return None,route(best) if best is not None else [start]
