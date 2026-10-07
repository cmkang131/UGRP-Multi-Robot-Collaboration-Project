"""Default-off pinned Nav2 Approach monitor + explore_lite launch defaults.

Own observed points/odometry only. No world, static-map or truth imports.
ROS-independent port: original kinematics/frontier/NavFn compiled unchanged,
polygon/TTC loop copied with Apache-2.0 attribution in the native adapter.
"""
import ctypes
import hashlib
import math
import subprocess
import numpy as np
from harness.public_navigation.native import PublicCore,ROOT,VENDOR,HERE
from harness.public_navigation_unknown import UnknownActor,UnknownNavigator,from_observed_grid
from harness.public_navigation.costmap import HALF
from harness.public_navigation.follower import command_from_twist
from harness.public_navigation_recovery import issued_twist
from harness.self_odom_grid import transform

OPTION='public_ros_v8'
PARAMETERS=dict(time_before_collision_s=1.2,simulation_time_step_s=.1,min_points=6,
    source_timeout_s=1.,base_shift_correction=True,costmap_update_hz=5.,replan_hz=1.,
    planner_frequency=.33,potential_scale=3.,gain_scale=1.,min_frontier_size_m=.75,
    progress_timeout_s=30.)


def navigation_output_v8(legacy,*,navigation='off',navigator=None,**kwargs):
    if navigation=='off':return legacy
    if navigation!=OPTION or navigator is None:raise ValueError('EXPLICIT_PUBLIC_ROS_V8_REQUIRED')
    return navigator.update(**kwargs)


def build():
    monitor=ROOT/'third_party/mapfree_navigation_monitor/navigation2/nav2_collision_monitor'
    sources=[VENDOR/'navigation/navfn/src/navfn.cpp',VENDOR/'m-explore/explore/src/frontier_search.cpp',
             ROOT/'harness/public_navigation_monitor.cpp',monitor/'src/kinematics.cpp']
    inputs=sources+[HERE/'bridge.cpp',ROOT/'harness/public_navigation_unknown.cpp']
    inputs+=sorted((HERE/'shim').rglob('*.h'))+sorted(VENDOR.rglob('*.h'))+sorted((monitor/'include').rglob('*.hpp'))
    digest=hashlib.sha256(b''.join(p.read_bytes() for p in inputs)).hexdigest()[:16]
    target=ROOT/'outputs/mapfree-public-navigation-build'/f'monitor-{digest}.so'
    if not target.exists():
        target.parent.mkdir(parents=True,exist_ok=True)
        subprocess.run(['c++','-std=c++17','-O2','-shared','-fPIC','-I'+str(HERE/'shim'),
            '-I'+str(VENDOR/'navigation/navfn/include'),'-I'+str(VENDOR/'m-explore/explore/include'),
            '-I'+str(monitor/'include'),*map(str,sources),'-o',str(target)],check=True,capture_output=True,text=True)
    return target


class MonitorCore(PublicCore):
    def __init__(self):
        self.lib=ctypes.CDLL(str(build()))
        u8=np.ctypeslib.ndpointer(dtype=np.uint8,flags='C_CONTIGUOUS')
        f64=np.ctypeslib.ndpointer(dtype=np.float64,flags='C_CONTIGUOUS')
        self.lib.ugrp_navfn.argtypes=[u8,*([ctypes.c_int]*6),np.ctypeslib.ndpointer(dtype=np.float32,flags='C_CONTIGUOUS'),ctypes.c_int]
        self.lib.ugrp_frontiers.argtypes=[u8,ctypes.c_int,ctypes.c_int,*([ctypes.c_double]*5),f64,ctypes.c_int]
        self.lib.ugrp_collision_time.argtypes=[f64,ctypes.c_int,f64,ctypes.c_int,f64]
        self.lib.ugrp_collision_time.restype=ctypes.c_double

    def collision_time(self,points,twist):
        points=np.ascontiguousarray(points,dtype=float).reshape(-1,2)
        twist=np.ascontiguousarray(twist,dtype=float)
        if twist.shape!=(3,) or not np.isfinite(twist).all() or not np.isfinite(points).all():
            raise ValueError('FINITE_OWN_POINTS_AND_TWIST_REQUIRED')
        polygon=np.ascontiguousarray(np.array([[-1,-1],[1,-1],[1,1],[-1,1]])*HALF,dtype=float)
        return self.lib.ugrp_collision_time(points,len(points),polygon,len(polygon),twist)


class ApproachMonitor:
    def __init__(self,core=None):
        self.core=core if core is not None else MonitorCore()
        self.points=None
        self.stamp_ns=None

    def observe(self,points,pose,t):
        points=np.asarray(points,float).reshape(-1,2)
        pose=np.asarray(pose,float)
        if pose.shape!=(3,) or not np.isfinite(pose).all() or not np.isfinite(points).all() or not math.isfinite(t):
            raise ValueError('FINITE_OWN_OBSERVATION_REQUIRED')
        stamp=round(t*1e9)
        if self.stamp_ns is not None and stamp<self.stamp_ns:raise ValueError('NONMONOTONIC_OBSERVATION')
        self.points=transform(points,pose)
        self.stamp_ns=stamp

    def filter(self,command,pose,t):
        stamp=round(t*1e9)
        if self.stamp_ns is None or stamp-self.stamp_ns>1_000_000_000 or stamp<self.stamp_ns:
            return command_from_twist(np.zeros(3),t),dict(reason='invalid_source',ttc_s=None,scale=0.,points=0)
        pose=np.asarray(pose,float)
        c,s=math.cos(pose[2]),math.sin(pose[2])
        local=(self.points-pose[:2])@np.array([[c,-s],[s,c]])
        twist=issued_twist(command)
        ttc=self.core.collision_time(local,twist)
        ratio=min(1.,ttc/1.2) if ttc>=0 else 1.
        filtered=command_from_twist(twist*ratio,t,command['duration_s']) if ratio<1 else command
        return filtered,dict(reason='approach' if ratio<1 else 'clear',ttc_s=ttc,scale=ratio,points=len(local))


class MonitorNavigator(UnknownNavigator):
    def __init__(self):
        super().__init__()
        self.core=MonitorCore()
        self.next_frontier_ns=0

    def select_frontier(self,costmap,pose,t):
        # explore timer at .33 Hz; aborted navigation requests an immediate makePlan.
        now=round(t*1e9)
        if self.frontier is not None and now<self.next_frontier_ns:return
        self.next_frontier_ns=now+round(1e9/.33)
        super().select_frontier(costmap,pose,t)

    def command(self,costmap,pose,plan,t):
        # Service the exploration timer independently of the 1 Hz NavFn timer.
        # No fresh sensor sample or hidden geometry is requested by this timer.
        if not self.static_mode and not self.finished and not self.failed:
            self.select_frontier(costmap,pose,t)
        return super().command(costmap,pose,plan,t)


class MonitorActor(UnknownActor):
    def __init__(self,condition,static_grid=None,static_goal=None,*,navigation='off'):
        if navigation!=OPTION:raise ValueError('EXPLICIT_PUBLIC_ROS_V8_REQUIRED')
        super().__init__(condition,static_grid,static_goal,navigation='public_ros_v7')
        self.option,self.navigator=OPTION,MonitorNavigator()
        self.navigator.static_mode=static_goal is not None
        self.monitor=ApproachMonitor(self.navigator.core)
        self.monitor_log=[]
        self.last_costmap_ns=None
        self.map_dirty=True

    def receive(self,observation,patches):
        result=super().receive(observation,patches)
        self.monitor.observe(observation['wall_xy'],self.odom.pose,self.t)
        self.map_dirty=True
        return result

    def make_costmap(self):
        now=round(self.t*1e9)
        if self.map_dirty or self.last_costmap_ns is None or now-self.last_costmap_ns>=200_000_000:
            self.clear_footprint()
            self.costmap=from_observed_grid(self.grid,self.odom.pose,self.latest,self.static_hits)
            self.last_costmap_ns=now
            self.map_dirty=False
        return self.costmap

    def plan(self):
        if self.navigator.clear_requested:
            self.clear_obstacles()
            self.map_dirty=True
        pose=np.asarray(self.odom.pose)
        self.make_costmap()
        plan=navigation_output_v8(None,navigation=self.option,navigator=self.navigator,
            costmap=self.costmap,pose=pose,t=self.t,static_goal=self.static_goal)
        if self.last_patches and not self.navigator.phase and not self.navigator.failed:
            target=np.asarray(self.last_patches[-1]['center_odom_m'])
            delta=target-pose[:2]
            point=pose[:2]+.12*delta/max(np.linalg.norm(delta),1e-9)
            path=self.navigator.plan_to(self.costmap,pose,point)
            if path:plan=dict(status='goal_reobserve',path_m=path,heading_rad=math.atan2(delta[1],delta[0]),doors=[])
        plan['doors']=self.doors.update(self.grid,pose)
        self.counts[plan['status']]=self.counts.get(plan['status'],0)+1
        return plan

    def receive_contact(self,sample):
        result=super().receive_contact(sample)
        if result:self.map_dirty=True
        return result

    def command(self,plan):
        command=super().command(plan)
        filtered,info=self.monitor.filter(command,self.odom.pose,self.t)
        self.monitor_log.append(dict(t=self.t,**info))
        return filtered

    def wait_command(self):
        """Keep the final velocity filter alive while the controller is waiting.

        No frontier/planner advancement or hidden sensor refresh during the wait.
        A new active command must pass filter() again after the next observation.
        """
        command=command_from_twist(np.zeros(3),self.t)
        filtered,info=self.monitor.filter(command,self.odom.pose,self.t)
        self.monitor_log.append(dict(t=self.t,phase='observation_wait',**info))
        return filtered
