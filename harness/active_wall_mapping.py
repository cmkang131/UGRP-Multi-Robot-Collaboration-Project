"""Closed-loop own-camera SLAM adapter; no simulator/GT/static scene input.

Frozen PR409 v8 exploration/navfn/monitor and PR405 RBPF/graph are imported,
not retuned. Local odometry and graph map coordinates remain distinct.
"""
import math
import json
from pathlib import Path
import numpy as np
from harness.self_wall_memory_robust import SelfWallMemory
from harness.self_odom_grid import transform
from harness.self_map_prob import wrap
from harness.self_pulse_odom import model,response
from harness.own_map_navigation import ObservedGrid,DoorMemory
from harness.public_navigation_monitor import MonitorNavigator
from harness.public_navigation_unknown import clear_current_footprint,from_observed_grid
from harness.public_navigation_raytrace import receive_rays
from harness.public_navigation_recovery import issued_twist
from harness.active_information_gain import forecast
from harness.active_camera import goal_detector
from harness.floor_goal_v3 import FloorGoalMemoryV3

ROOT=Path(__file__).resolve().parents[1]
OPTIONS=dict(self_map='odom_grid_v1',pose_correction='own_map_rbpf_v1',pose_correction_options={'particles':100},
    wall_projection_guard='positive_depth_v1',pose_graph='own_submap_v1',wall_confidence='inverse_sensor_v1',
    motion_model='s2_pulse_v122',loop_rejection='switchable_v1',wall_evidence='tsdf_weight_v1')


def active_output(legacy,*,active_mapping='off',controller=None,**kwargs):
    if active_mapping=='off':return legacy
    if active_mapping!='frontier_rbpf_v1' or controller is None:raise ValueError('EXPLICIT_ACTIVE_MAPPING_REQUIRED')
    return controller.receive(**kwargs)


def compose(a,b):
    return np.r_[transform([b[:2]],a)[0],wrap(a[2]+b[2])]


def inverse(p):
    a=-np.asarray(p,float)
    a[:2]=transform([-np.asarray(p[:2])],[0,0,-p[2]])[0]
    return a


def pulse_command(twist,t,*,costmap=None,pose=None,core=None,points=()):
    """Finite calibrated motion lattice approximates a 0.2s twist request.

    Select nearest endpoint in SE(2), yaw scaled by wheelbase .24m. Include zero.
    Every candidate is projected using its actual calibration curve, not M1 gain.
    """
    twist=np.asarray(twist,float)
    if twist.shape!=(3,) or not np.isfinite(twist).all():raise ValueError('FINITE_TWIST_REQUIRED')
    target=twist*.2
    scale=np.array([1.,1.,.24])
    best=(float(np.linalg.norm(target*scale)),None)
    for key,p in model()['profiles'].items():
        if not key.startswith('0:') or p['times'][-1]>.2+1e-8:continue
        end=response(p,.2)
        if costmap is not None and not all(costmap.pose_clear(compose(pose,response(p,s))) for s in np.arange(0,.20001,.025)):
            continue
        if core is not None:
            ttc=core.collision_time(points,end/.2)
            if 0<=ttc<1.2:continue  # cannot scale an uncalibrated pulse: select zero instead
        distance=float(np.linalg.norm((target-end)*scale))
        if distance<best[0]:best=(distance,p)
    p=best[1]
    if p is None:return dict(t=float(t),kind='hold'),dict(reason='zero_or_blocked',predicted_delta=[0.,0.,0.])
    return dict(t=float(t),kind='mecanum',duration_s=p['duration_s'],**{**dict(forward=0.,left=0.,turn=0.),p['axis']:p['u']}),dict(reason='calibrated_pulse',predicted_delta=response(p,.2).tolist())


class ActiveMapper:
    def __init__(self,robot_id,start,servo,*,active_mapping='off',active_loop='off',seed=22001):
        if active_mapping!='frontier_rbpf_v1':raise ValueError('EXPLICIT_ACTIVE_MAPPING_REQUIRED')
        if active_loop not in ('off','information_gain_v1'):raise ValueError('UNKNOWN_ACTIVE_LOOP')
        self.robot_id,self.active_loop,self.seed=robot_id,active_loop,seed
        self.memory=SelfWallMemory(robot_id,**OPTIONS,self_map_options={'start_time':start})
        self.memory.command(dict(t=start,kind='initial_servo_command',pulses=servo))
        self.navigator=MonitorNavigator()
        self.goal=FloorGoalMemoryV3(robot_id,options=json.loads((ROOT/'experiments/2026-10-07-mapfree-goal-floor/v3-selection.json').read_text())['selected']['options'])
        self.goal.detector=goal_detector()
        self.grid=ObservedGrid(robot_id,.1)
        self.latest={}
        self.doors=DoorMemory(robot_id)
        self.map_to_odom=np.zeros(3)
        self.frames=[]
        self.poses=[]
        self.events=[]
        self.graphs=[]
        self.next_graph=start+10.
        self.next_gain=start+10.
        self.revisit=None
        self.bootstrap_turn=0.
        self.started=start
        self.goal_target=None
        self.last_plan_t=-math.inf
        self.plan=None

    @property
    def local_pose(self):return np.asarray(self.memory.self_map.odom.pose)

    @property
    def pose(self):return compose(self.map_to_odom,self.local_pose)

    def command(self,row):self.memory.command(row)

    def _rays(self,record,pose):
        from harness.self_map_csm import sample_segments
        wall=sample_segments(record['segments']) if record['segments'] else np.empty((0,2))
        floor=np.asarray(record['floor_xy']).reshape(-1,2)
        obs=dict(robot_id=self.robot_id,frame_id=record['frame_id'],floor_xy=floor,wall_xy=wall,
            floor_origins_xy=np.tile(record['camera'],(len(floor),1)),wall_origins_xy=np.tile(record['camera'],(len(wall),1)))
        receive_rays(self.grid,self.latest,set(),obs,pose)
        clear_current_footprint(self.grid,self.latest,set(),pose)
        return wall

    def graph(self,t):
        if len(self.memory.self_map.ledger)<2:return
        result=self.memory.finalize_pose_graph(self.poses)
        corrected={r['t']:r['pose'] for r in result['poses']}
        local=self.local_pose
        previous_tf=self.map_to_odom.copy()
        self.map_to_odom=compose(corrected[self.poses[-1]['t']],inverse(local))
        change=compose(self.map_to_odom,inverse(previous_tf))
        self.navigator.blacklist=[transform([p],change)[0] for p in self.navigator.blacklist]
        self.grid=ObservedGrid(self.robot_id,.1)
        self.latest={}
        for row in self.frames:
            self._rays(row,corrected[row['t']])
        self.graphs.append(dict(t=t,diagnostics=result['diagnostics'],map_to_odom=self.map_to_odom.tolist()))
        # Existing global targets were represented in the previous map frame.
        # Clear target cache, preserve observed evidence and source blacklist via TF delta below.
        self.navigator.target=self.navigator.frontier=None
        self.navigator.path=[]
        self.navigator.finished=False
        self.navigator.reset_action()
        self.revisit=None
        self.plan=None
        # Goal tracks use local odom; transform latest goal only at consumption.

    def choose_information(self,t,costmap):
        if self.active_loop=='off' or t<self.next_gain:return
        self.next_gain=t+10.
        grid=self.memory.self_map
        cov=grid.odom.covariance
        uncertain=math.sqrt(float(np.linalg.eigvalsh(cov[:2,:2]).max()))>=.15 or math.sqrt(cov[2,2])>=math.radians(5)
        candidates=[]
        pose=self.pose
        for row in self.navigator.core.frontiers(costmap.raw,costmap.origin,.1,pose[:2]):
            if len(candidates)>=2:break
            if self.navigator.blocked(row[:2],.1):continue
            path=self.navigator.plan_to(costmap,pose,row[:2])
            if path:candidates.append(('frontier',path))
        if uncertain:
            places=[]
            for row in self.poses:
                target=compose(self.map_to_odom,row['pose'])[:2]
                if t-row['t']<10 or np.linalg.norm(target-pose[:2])<.5:continue
                if any(np.linalg.norm(target-p)<.5 for p in places):continue
                places.append(target)
                path=self.navigator.plan_to(costmap,pose,target)
                if path:candidates.append(('revisit',path))
                if sum(k=='revisit' for k,_ in candidates)>=2:break
        scored=[]
        for kind,path in candidates:
            local=transform(path,inverse(self.map_to_odom))
            result=forecast(grid,local,seed=self.seed+round(t*10))
            scored.append(dict(kind=kind,path=path,**result))
        if scored:
            selected=max(scored,key=lambda r:r['utility'])
            if selected['kind']=='revisit':
                self.revisit=np.asarray(selected['path'][-1])
            else:
                self.revisit=None
                self.navigator.target=np.asarray(selected['path'][-1])
                self.navigator.frontier=self.navigator.target.copy()
                self.navigator.path=selected['path']
                self.navigator.heading=math.atan2(*(self.navigator.target-pose[:2])[::-1])
                self.navigator.finished=False
        self.events.append(dict(t=t,reason='information_decision',uncertain=uncertain,candidates=scored,
                                selected=None if not scored else selected['kind']))

    def receive(self,*,robot_id,t,frame_id,rgb,servo,observation):
        if robot_id!=self.robot_id:raise ValueError('ACTIVE_PEER_INPUT_FORBIDDEN')
        grid=self.memory.self_map
        grid.odom.advance(t)
        if observation['segments']:
            grid.observe_contacts_confident(t=t,frame_id=frame_id,segments=observation['segments'],features=observation['features'],
                camera_xy=observation['camera'],robot_id=robot_id)
        self.poses.append(dict(robot_id=robot_id,t=float(t),pose=self.local_pose.tolist()))
        row=dict(t=float(t),frame_id=frame_id,**observation)
        self.frames.append(row)
        wall=self._rays(row,self.pose)
        patches,_,diagnostics=self.goal.observe(rgb,robot_id=robot_id,frame_id=frame_id,t=t,pose=self.local_pose,servo=servo,profile='camera_v3',settled=t-self.started>=.25)
        if t>=self.next_graph:
            self.graph(t)
            self.next_graph=t+10.
        pose=self.pose
        costmap=from_observed_grid(self.grid,pose,self.latest,set())
        self.choose_information(t,costmap)
        goal=None
        if patches:
            # Observed candidate: approach in .12m increments for v3 temporal confirmation.
            target=compose(self.map_to_odom,[*patches[-1]['center_odom_m'],0.])[:2]
            delta=target-pose[:2]
            goal=target if patches[-1]['confirmed_t'] is not None else pose[:2]+.12*delta/max(np.linalg.norm(delta),1e-9)
        if self.revisit is not None:
            if np.linalg.norm(self.revisit-pose[:2])<.1:
                self.events.append(dict(t=t,reason='active_revisit_reached'))
                self.revisit=None
                self.navigator.target=None
            elif goal is None:goal=self.revisit
        if self.navigator.clear_requested:
            self.navigator.clear_requested=False
            self.navigator.event(t,'costmap_rebuilt_persistent_reapplied',observed_hits=sum(self.latest.values()))
        if self.plan is None or t-self.last_plan_t>=1.-1e-8 or goal is not None:
            self.plan=self.navigator.update(costmap,pose,t,static_goal=goal)
            self.last_plan_t=t
        # Frozen v8 increments progress active time by .1 per command. Our
        # calibrated pulse cycle is .2s, so account for the other .1 explicitly.
        if not self.navigator.phase and not self.navigator.failed and not self.navigator.finished:
            self.navigator.active_t+=.1
        command=self.navigator.command(costmap,pose,self.plan,t)
        twist=issued_twist(command)
        # Only initial narrow-FOV acquisition may turn to uncover a frontier.
        if self.navigator.finished and t-self.started<20 and self.bootstrap_turn<2*math.pi:
            twist=np.array([0.,0.,.5])
            self.navigator.finished=False
            self.plan=None
        cmd,pulse=pulse_command(twist,t,costmap=costmap,pose=pose,core=self.navigator.core,points=wall)
        if self.navigator.target is None:self.bootstrap_turn+=abs(pulse['predicted_delta'][2])
        doors=self.doors.update(self.grid,pose)
        trace=dict(t=t,frame_id=frame_id,pose=pose.tolist(),local_pose=self.local_pose.tolist(),
            map_cells=len(self.grid.odds),wall_segments=len(observation['segments']),floor_points=len(observation['floor_xy']),
            status=(self.plan or {}).get('status','initial_camera_scan'),path=(self.plan or {}).get('path_m',[]),
            command=cmd,pulse=pulse,doors=doors,goal=self.goal.snapshot(),goal_diagnostics=diagnostics,
            sigma_xy=math.sqrt(float(np.linalg.eigvalsh(grid.odom.covariance[:2,:2]).max())))
        return cmd,trace
