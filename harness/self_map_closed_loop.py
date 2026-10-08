"""Opt-in own exploration -> causal snapshot -> unknown-start AMCL -> own B.

No scene, static geometry, truth, measured joints, peer map or model input.
The previously known pose is discarded, not passed to the new PF. Navigation
reuses v8/egomap29 while AMCL's prefix map remains immutable.
"""
import copy
import math
import cv2
import numpy as np
from harness.active_wall_mapping import pulse_command
from harness.active_wall_recovery import ExplorationRecoveryNavigator
from harness.own_map_navigation import ObservedGrid
from harness.public_navigation_unknown import from_observed_grid,clear_current_footprint
from harness.public_navigation_raytrace import receive_rays
from harness.public_navigation_recovery import issued_twist
from harness.public_navigation_resolution import RESOLUTION
from harness.self_map_causal import own_landmarks_before,landmark_object
from harness.self_map_relocalize import Relocalizer
from harness.self_map_landmark_sensor import Sensor
from harness.self_wall_segment_points import contact_points
from harness.self_pose_graph import between
from harness.self_pulse_rotation import RotationPulseOdometry,OPTION as MOTION
from harness.active_camera import transform as camera_transform
from harness.active_wall_vision import modules

OPTION='remembered_goal_v1'
# Same egomap42 detector vocabulary, color names only; no spatial geometry.
HUES=(12.35293960571289,107.58621215820312,112.,143.07691955566406)


def attach(explorer,*,map_utility='off',seed=43001):
    if map_utility=='off':return explorer
    if map_utility!=OPTION:raise ValueError('UNKNOWN_MAP_UTILITY')
    return RememberedGoal(explorer,seed=seed)


def own_measurement(rgb,servo):
    points=contact_points(rgb,servo)
    origin,rotation=camera_transform(servo)
    xy=np.asarray(points['points']).reshape(-1,2)
    optical=(np.c_[xy,np.zeros(len(xy))]-origin)@rotation
    project=optical@modules()[0].K.T
    points['uv']=(project[:,:2]/project[:,2,None]).tolist()
    return points


def remembered_goal(snapshot,*,t,frame_id,frame_sha256):
    assert snapshot['robot_id']=='r3' and snapshot['coordinate_frame']=='r3/own_odom'
    confirmed=[c for c in snapshot['candidates'] if c['state']=='locally_confirmed_region']
    if not confirmed:return None
    c=min(confirmed,key=lambda c:(c['confirmed_t'],c['id']))
    return dict(entity=dict(kind='floor_zone',id='B'),center_m=copy.deepcopy(c['center_m']),
        source='own',detector='floor_color_v3',candidate_id=c['id'],
        obs_id=f'r3-obs-{frame_id:06d}',t_sim=float(t),frame_sha256=frame_sha256,
        observations=c['observations'],first_t=c['first_t'],bounds_m=copy.deepcopy(c['bounds_m']),
        confidence=c['confidence'],partial_extent=True)


class RememberedGoal:
    def __init__(self,explorer,*,seed):
        self.explorer,self.seed=explorer,seed
        self.robot_id=explorer.robot_id
        self.started=explorer.started
        self.stage='explore'
        self.sensor=Sensor(HUES)
        self.measurements=[];self.poses=[];self.inputs=[];self.events=[]
        self.snapshot=None;self.last_snapshot=None;self.goal=None;self.pf=None
        self.loss_t=None;self.streak=0;self.declared=False
        self.navigator=None;self.plan=None;self.last_plan_t=-math.inf
        self.last_belief=None;self.odom=None;self.previous=np.zeros(3)

    def command(self,row):
        if self.stage=='explore':self.explorer.command(row)
        else:self.odom.command(row)

    def loss_due(self,t):
        return (t-self.started>=90 and self.goal is not None) or t-self.started>=180

    def make_navigator(self):
        return ExplorationRecoveryNavigator()

    def lose(self,t,frame_id):
        if self.last_snapshot is None:raise ValueError('NO_CAUSAL_SNAPSHOT')
        self.snapshot=copy.deepcopy(self.last_snapshot)
        assert self.snapshot['t']<t-1e-8
        assert all(r['t']<t-1e-8 for r in self.snapshot['ledger'])
        landmarks=own_landmarks_before(self.measurements,self.poses,t,robot_id=self.robot_id)
        self.snapshot.update(landmarks=landmarks,goal=copy.deepcopy(self.goal),loss_t=float(t))
        self.pf=Relocalizer(self.snapshot['grid'],seed=self.seed,sensor_landmarks='floor_zones_doors_v1',
            landmark_map=landmark_object(landmarks),likelihood_tempering='pr_likelihood_half_v1')
        # No previous estimate or world alignment enters this constructor.
        self.odom=RotationPulseOdometry(t)
        self.previous=np.zeros(3)
        self.navigator=self.make_navigator()
        self.grid=ObservedGrid(self.robot_id,RESOLUTION);self.latest={}
        # Replicate 0.1m map cells at the frozen v8 0.05m navigation resolution.
        factor=round(self.snapshot['grid']['resolution_m']/RESOLUTION)
        assert factor>=1 and abs(factor*RESOLUTION-self.snapshot['grid']['resolution_m'])<1e-8
        for x,y,v in self.snapshot['grid']['cells']:
            for dx in range(factor):
                for dy in range(factor):
                    cell=(int(x)*factor+dx,int(y)*factor+dy)
                    self.grid.odds[cell]=v;self.latest[cell]=v>0
        self.loss_t=float(t);self.stage='relocalize'
        self.events.append(dict(t=float(t),frame_id=frame_id,reason='unknown_start_reset',
            particles=self.pf.n,goal_observed=self.goal is not None,snapshot_t=self.snapshot['t'],
            scans=len(self.snapshot['ledger']),floor_edges=len(landmarks['edges']),doors=len(landmarks['doors']),
            excluded_loss_frame=True,previous_pose_prior=False))

    def receive(self,*,robot_id,t,frame_id,rgb,servo,observation,frame_sha256):
        if robot_id!=self.robot_id:raise ValueError('PEER_INPUT_FORBIDDEN')
        # Loss frame is excluded from both the prefix map and the suffix observations.
        if self.stage=='explore' and self.loss_due(t):
            self.lose(t,frame_id)
            cmd=dict(t=float(t),kind='hold')
            return cmd,dict(t=float(t),frame_id=frame_id,stage=self.stage,status='unknown_start_reset',
                pose=None,command=cmd,goal=self.goal,declared_goal=False)
        points=own_measurement(rgb,servo)
        features=self.sensor.measure(cv2.cvtColor(rgb,cv2.COLOR_RGB2BGR),servo,points)
        if self.stage=='explore':
            cmd,trace=self.explorer.receive(robot_id=robot_id,t=t,frame_id=frame_id,rgb=rgb,servo=servo,observation=observation)
            g=self.explorer.memory.self_map
            self.measurements.append(dict(robot_id=robot_id,t=float(t),frame_id=frame_id,frame_sha256=frame_sha256,features=features))
            self.poses.append(dict(t=float(t),frame_id=frame_id,pose=list(g.odom.pose),covariance=g.odom.covariance.tolist()))
            revision=(g.revision,g.best,g.resamples)
            if self.last_snapshot is None or revision!=self.last_snapshot['revision']:
                self.last_snapshot=dict(t=float(t),frame_id=frame_id,view='online_frontend',revision=revision,
                    grid=copy.deepcopy(g.export()),ledger=copy.deepcopy(g.ledger))
            if self.goal is None:self.goal=remembered_goal(trace['goal'],t=t,frame_id=frame_id,frame_sha256=frame_sha256)
            trace.update(stage=self.stage,remembered_B=self.goal,declared_goal=False)
        else:
            nominal=np.array(self.odom.advance(t));delta=between(self.previous,nominal);self.previous=nominal
            belief=self.pf.step(t=t,points=points['points'],delta=delta,servo=servo,features=features)
            self.last_belief=belief
            self.streak=self.streak+1 if belief['resolved'] else 0
            pose=np.asarray(belief['pose'])
            if self.stage=='relocalize' and (self.streak>=5 or t-self.loss_t>=60):
                reason='internally_resolved' if self.streak>=5 else 'would_stop_unresolved'
                self.stage='return' if self.goal else 'goal_unobserved'
                self.events.append(dict(t=float(t),reason=reason,next_stage=self.stage))
            if self.navigator.clear_requested:
                self.grid=ObservedGrid(robot_id,RESOLUTION);self.latest={}
                self.navigator.clear_requested=False
                self.navigator.event(t,'navigation_layer_reset',slam_reset=False)
            wall=np.asarray(points['points']).reshape(-1,2)
            floor=np.asarray(observation['floor_xy']).reshape(-1,2)
            receive_rays(self.grid,self.latest,set(),dict(robot_id=robot_id,frame_id=frame_id,
                floor_xy=floor,wall_xy=wall,floor_origins_xy=np.tile(observation['camera'],(len(floor),1)),
                wall_origins_xy=np.tile(observation['camera'],(len(wall),1))),pose)
            clear_current_footprint(self.grid,self.latest,set(),pose)
            cm=from_observed_grid(self.grid,pose,self.latest,set())
            if getattr(self,'door_system',None) is not None:
                self.door_system.prepare(grid=self.grid,pose=pose,local_pose=pose,observation=observation,
                    t=t,frame_id=frame_id,sigma=belief['global_std_xy_m'])
            target=None if self.goal is None else self.goal['center_m']
            self.declared=bool(self.stage=='return' and self.streak>=5 and np.linalg.norm(pose[:2]-target)<=.20)
            if self.declared:
                self.stage='declared';cmd=dict(t=float(t),kind='hold');pulse=None
                self.events.append(dict(t=float(t),reason='own_B_arrival_declaration',pose=pose.tolist(),goal=self.goal))
            else:
                if self.stage=='relocalize':twist=np.array([0.,0.,.5])
                else:
                    if self.plan is None or t-self.last_plan_t>=1.-1e-8:
                        self.plan=self.navigator.update(cm,pose,t,static_goal=target)
                        self.last_plan_t=t
                    if not self.navigator.phase and not self.navigator.failed and not self.navigator.finished:self.navigator.active_t+=.1
                    twist=issued_twist(self.navigator.command(cm,pose,self.plan,t))
                cmd,pulse=pulse_command(twist,t,costmap=cm,pose=pose,core=self.navigator.core,points=wall,motion_model=MOTION)
            trace=dict(t=float(t),frame_id=frame_id,stage=self.stage,status=(self.plan or {}).get('status',self.stage),
                pose=pose.tolist(),local_pose=pose.tolist(),sigma_xy=belief['global_std_xy_m'],belief=belief,
                stable_resolved=self.streak>=5,goal=self.goal,remembered_B=self.goal,declared_goal=self.declared,
                command=cmd,pulse=pulse,path=(self.plan or {}).get('path_m',[]))
        if getattr(self,'door_system',None) is not None:
            trace['doors']=self.door_system.update(None,None)
            trace['room_topology']=self.door_system.last_topology
        self.inputs.append(dict(t=float(t),frame_id=frame_id,points=points['points'],features=features,servo=servo,
            stage=self.stage,delta=delta.tolist() if self.stage!='explore' else None))
        return cmd,trace
