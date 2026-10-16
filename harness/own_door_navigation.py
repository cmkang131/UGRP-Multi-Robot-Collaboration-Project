"""Default-off own room/door topology and a single frontal confirmation view.

Confirmed cuts -> free-space components -> door edges (Thrun 1996); Xiang 2004
normal approach point. NavFn/RPP/recovery unchanged, unknown is not a room.
"""
from collections import deque
import copy
import math
import numpy as np
from scipy.ndimage import label
from harness.own_door_memory import DoorMemory,OPTION as DETECTOR,geometry
from harness.active_navfn_start import StartRecoveryNavigator
from harness.public_navigation.follower import command_from_twist
from harness.public_navigation_recovery import projection_clear
from harness.public_navigation_persistent import raytrace_cells
from harness.own_map_navigation import visible_unknown
from harness.active_wall_mapping import compose,inverse
from harness.self_map_prob import wrap

OPTION='room_doors_v1'


def topology(grid,doors,pose):
    state,lo=grid.dense(pose);free=state==-1
    for d in doors:
        if d['confirmed_t'] is None:continue
        ends=np.asarray(d['endpoints'])
        a,b=[np.asarray(grid.cell(p))-lo for p in ends]
        for x,y in raytrace_cells(a,b):
            if 0<=x<free.shape[1] and 0<=y<free.shape[0]:free[y,x]=False
    regions,n=label(free)
    def region(p):
        x,y=np.asarray(grid.cell(p))-lo
        return int(regions[y,x]) if 0<=x<free.shape[1] and 0<=y<free.shape[0] else 0
    edges=[]
    for d in doors:
        if d['confirmed_t'] is None:continue
        c,_,normal=geometry(d);a,b=region(c-.4*normal),region(c+.4*normal)
        if a and b and a!=b:edges.append(dict(door=d['id'],a=a,b=b,minus=(c-.4*normal).tolist(),plus=(c+.4*normal).tolist()))
    return dict(regions=n,edges=edges),region


def door_route(graph,start,goal):
    if not start or not goal:return None
    todo=deque([(start,[])]);seen={start}
    while todo:
        at,path=todo.popleft()
        if at==goal:return path
        for e in graph['edges']:
            nxt=e['b'] if e['a']==at else e['a'] if e['b']==at else None
            if nxt and nxt not in seen:
                seen.add(nxt);todo.append((nxt,path+[(e,at)]))
    return None


def crosses(path,door):
    c,tangent,normal=geometry(door)
    for a,b in zip(path,path[1:]):
        a,b=np.asarray(a),np.asarray(b)
        da,db=np.dot(a-c,normal),np.dot(b-c,normal)
        if da*db<=0 and abs(da-db)>1e-9:
            hit=a+(b-a)*da/(da-db)
            if abs(np.dot(hit-c,tangent))<=door['width_m']/2:return True
    return False


class DoorNavigator(StartRecoveryNavigator):
    def __init__(self,system):
        super().__init__();self.system=system;self.mission=None;self.local_id=None
        self.viewed=set();self.look=None;self.look_t=None;self.look_last=None;self.look_rotation=0.
        self.locked=False  # existing mapper's information hook consults this
        self.visited=[]

    def request_sweep(self,t,reason):
        # Compatibility seam: no unconditional CycleNavigator 360-degree sweep.
        self.event(t,'partial_view_requested',cause=reason)

    @property
    def sweep_pending(self):return None
    @property
    def sweep_last_yaw(self):return None

    def action_failed(self,t,reason):
        mission=copy.deepcopy(self.mission);waypoint=copy.deepcopy(self.target)
        self.requested_goal=None  # parent may blacklist only this local action
        super().action_failed(t,reason)
        if mission is not None:
            self.blacklist=[p for p in self.blacklist if np.linalg.norm(p-mission)>.01]
            self.event(t,'mission_retained_local_action_failed',cause=reason,mission=mission.tolist(),
                waypoint=None if waypoint is None else waypoint.tolist(),door=self.local_id)
        if self.local_id:self.viewed.add(self.local_id)
        self.local_id=None;self.look=None;self.locked=False

    def choose(self,costmap,pose,t,goal):
        s=self.system;doors=s.memory.snapshot(s.tf)
        graph,region=topology(s.grid,doors,pose);s.last_topology=graph
        blockers=set()
        if goal is not None:
            route=door_route(graph,region(pose[:2]),region(goal))
            if route:
                edge,at=route[0];target=np.array(edge['plus'] if at==edge['a'] else edge['minus'])
                if self.plan_to(costmap,pose,target):return target,edge['door'],None
            elif route==[]:
                path=self.plan_to(costmap,pose,goal)
                blockers={d['id'] for d in doors if d['confirmed_t'] is None and crosses(path,d)}
                if path and not blockers:return np.asarray(goal),None,None
        candidates=[]
        for d in doors:
            if d['confirmed_t'] is not None or d['id'] in self.viewed:continue
            if blockers and d['id'] not in blockers:continue
            c,_,n=geometry(d)
            # Xiang Eq2: perpendicular, 1m stand-off, closer reachable solution.
            views=sorted((c-n,c+n),key=lambda p:float(np.linalg.norm(p-pose[:2])))
            for target in views:
                if self.blocked(target,costmap.resolution):continue
                path=self.plan_to(costmap,pose,target)
                if not path:continue
                delta=c-target;heading=math.atan2(delta[1],delta[0])
                distance=sum(math.dist(a,b) for a,b in zip(path,path[1:]))
                candidates.append((distance,d['id'],target,heading));break
        if candidates:
            _,key,target,heading=min(candidates,key=lambda p:(p[0],p[1]))
            return target,key,heading
        # A failed/unreachable confirmation view does not authorize crossing.
        if blockers:return None,None,None
        return (None,None,None) if goal is None else (np.asarray(goal),None,None)

    def update(self,costmap,pose,t,static_goal=None):
        self.mission=None if static_goal is None else np.asarray(static_goal).copy()
        if self.phase:return super().update(costmap,pose,t,static_goal=self.target)
        target,key,heading=self.choose(costmap,pose,t,static_goal)
        if key!=self.local_id or (target is not None and self.target is not None and np.linalg.norm(target-self.target)>.05):
            self.reset_action();self.look=None
        self.local_id=key;self.locked=target is not None
        if target is not None and np.linalg.norm(target-pose[:2])<=.05 and key and heading is not None:
            if self.look is None:
                self.look=heading;self.look_t=t;self.look_last=pose[2];self.look_rotation=0.
                gain=visible_unknown(self.system.grid,pose[:2],heading,54.5,4.)
                self.full_look=self.system.sigma>=.15 and gain>0
                self.event(t,'door_confirmation_view',door=key,full_sweep=self.full_look,gain=gain)
            return self.idle(pose,'door_confirmation_view')
        plan=super().update(costmap,pose,t,static_goal=target)
        if key:plan={**plan,'door':key,'door_action':'confirm' if heading is not None else 'cross'}
        return plan

    def command(self,costmap,pose,plan,t):
        if self.look is not None:
            self.look_rotation+=abs(float(wrap(pose[2]-self.look_last)));self.look_last=pose[2]
            error=float(wrap(self.look-pose[2]));done=(self.look_rotation>=2*math.pi-.02 if self.full_look else abs(error)<=math.radians(10))
            if done or t-self.look_t>=30.:
                self.viewed.add(self.local_id);self.event(t,'door_view_finished',door=self.local_id,complete=done)
                self.look=None;self.local_id=None;self.target=None;self.path=[];self.locked=False
                return command_from_twist(np.zeros(3),t)
            twist=np.array([0.,0.,.5 if self.full_look else math.copysign(.5,error)])
            if not projection_clear(costmap,pose,twist,horizon=2.):twist[:]=0.
            return command_from_twist(twist,t)
        return super().command(costmap,pose,plan,t)


class DoorSystem:
    def __init__(self,robot_id,navigation):
        self.memory=DoorMemory(robot_id);self.navigation=navigation;self.tf=np.zeros(3)
        self.grid=None;self.sigma=0.;self.last_topology={}

    def prepare(self,*,grid,pose,local_pose,observation,t,frame_id,sigma):
        self.grid=grid;self.sigma=float(sigma);self.tf=compose(pose,inverse(local_pose))
        self.memory.observe(robot_id=grid.robot_id,t=t,frame_id=frame_id,pose=local_pose,observation=observation)

    def update(self,grid,pose):
        return self.memory.snapshot(self.tf)


def attach(explorer,*,door_detector='off',door_navigation='off'):
    if door_detector=='off' and door_navigation=='off':return explorer
    if door_detector!=DETECTOR or door_navigation not in ('off',OPTION):raise ValueError('EXPLICIT_OWN_DOOR_OPTIONS_REQUIRED')
    system=DoorSystem(explorer.robot_id,door_navigation)
    explorer.door_system=system;explorer.doors=system
    if door_navigation==OPTION:explorer.navigator=DoorNavigator(system)
    return explorer


def attach_return(controller,*,door_detector='off',door_navigation='off'):
    if door_detector=='off' and door_navigation=='off':return controller
    attach(controller.explorer,door_detector=door_detector,door_navigation=door_navigation)
    controller.door_system=controller.explorer.door_system
    old_lose=controller.lose
    def lose(t,frame_id):
        old_lose(t,frame_id)
        controller.snapshot['own_doors']=controller.door_system.memory.snapshot()
        if door_navigation==OPTION:controller.navigator=DoorNavigator(controller.door_system)
    controller.lose=lose
    return controller
