"""Native-frame GoalRoute owner. Inputs are RGB and issued servo/motor history.

No environment, scene, world, authored geometry or evaluator is accepted here.
"""
import base64
import copy
from dataclasses import replace
import math
from types import SimpleNamespace
import numpy as np
from harness import e2e_own_inputs as own
from harness.active_camera import SEARCH, bind, transform as camera_transform
from harness.active_wall_vision import observe
from harness.e2e_goal_route import GoalRoute, attach
from harness.e2e_setdown_relook import OwnRGBRelook
from harness.self_odom_grid import transform


def make_goal(rid, seed, covariance_profile, *, relook='off',goal_geometry='off'):
    if goal_geometry not in ('off','e2e_b80_v1'):raise ValueError('UNKNOWN_GOAL_GEOMETRY')
    from harness.active_navfn_start import make_mapper
    from harness.grid_acceleration import install
    from harness.self_graph_cache import install as graph_cache
    from scripts.run_active_wall_rotleft import install_profile
    explorer = make_mapper(rid, 0., SEARCH, active_mapping='frontier_rbpf_v1',
        active_loop='information_gain_v1', seed=seed, active_recovery='nav2_frontier_v1',
        navigation_map='public_ros_v8', motion_model='s2_pulse_v122_rotL_v1',
        navigation_start='navfn_recovery_v1', frontier_observation='yamauchi_cycle_v1')
    if goal_geometry=='e2e_b80_v1':
        # Fixed task dimensions only; no map/scene position or evaluation input.
        explorer.goal.options=replace(explorer.goal.options,known_region_width_m=.80)
    graph_cache(explorer.memory,graph_acceleration='match_cache_v1')
    install_profile(explorer.memory.self_map,profile='egomap27_wide')
    from harness.goal_route_heading import OPTION as HEADING
    goal = GoalRoute(explorer,heading_host=HEADING,dev_light=True)
    goal = attach(goal, own_route='goal_route_v1' if rid=='r1' else 'off',
        arrival_gate='rgb_geometry_v1', covariance_inflation='nees_frozen_v1',
        covariance_profile=covariance_profile,
        setdown_reobserve='boundary_reobserve_v1' if rid=='r1' else 'off',
        setdown_only_when_relook=relook)
    install(goal,map_acceleration='scalar_rays_v1')
    # This mission maps a beam route, not the old B+cyan+return benchmark.
    # Keep the same receive/localization/GoalRoute memory, but frontier exploration
    # owns locomotion until a fresh own beam and a fully observed corridor exist.
    goal._select=lambda t:None
    goal._arrival=lambda *args:None
    OwnRGBRelook(goal)
    return goal


def beam_observer():
    from harness import owncam_pair_beam as v1, owncam_pair_beam_v2 as v2
    from harness.owncam_view import _pixel_rays
    def rays(servo,step=8):
        origin,rotation=camera_transform(servo)
        xs,ys,normal,valid=_pixel_rays(step)
        directions=np.column_stack((normal,np.ones(len(normal))))@rotation.T
        directions/=np.linalg.norm(directions,axis=1,keepdims=True)
        return origin,directions,xs,ys,valid
    first=bind(v1.observe_beam,base_rays=rays)
    return bind(v2.observe_beam,v1=SimpleNamespace(**{**vars(v1),'observe_beam':first}),base_rays=rays)


class Robot:
    def __init__(self,rid,seed,covariance_profile,options,*,relook='off',goal_geometry='off'):
        self.robot_id=rid;self.study_options=options
        self.goal=make_goal(rid,seed,covariance_profile,relook=relook,goal_geometry=goal_geometry)
        self.observe_beam=beam_observer()
        self.servo=dict(SEARCH);self.now=0.;self.frame=None;self.last_obs=None
        self.nav_command=dict(kind='hold');self.packet=None;self.beam=None;self.events=[]
        self.call_ref=None;self.trace=None;self.revision=0
        self.wall_segments=[]

    def receive(self,obs,rgb):
        own.closed(obs,('frame_id','sim_time','sha256','image'),'OWN_CAPTURE')
        self.now=float(obs['sim_time']);self.last_obs=copy.deepcopy(obs)
        self.frame=SimpleNamespace(index=obs['frame_id'],t=self.now,sha256=obs['sha256'],
                                   jpeg=base64.b64decode(obs['image']))
        detection=observe(rgb,self.servo,body_settling=.7)
        self.wall_segments=copy.deepcopy(detection['segments'])
        command,trace=self.goal.receive(robot_id=self.robot_id,t=self.now,frame_id=obs['frame_id'],
            rgb=rgb,servo=self.servo,observation=detection,frame_sha256=obs['sha256'])
        self.nav_command={k:v for k,v in command.items() if k!='t'};self.trace=trace
        self.revision+=1
        b=self.observe_beam(obs['image'],self.servo)
        self.beam=None
        if b.get('visible') and b.get('end_visible'):
            pose=np.asarray(self.goal.explorer.local_pose,float)
            # A measured near end + known beam length; no scene placement.
            from harness.owncam_pair_beam import GRIP_INSET_M
            direction=np.array([math.cos(b['axis_heading_rad']),math.sin(b['axis_heading_rad'])])
            center=np.asarray(b['grip_base_m'])+(.30-GRIP_INSET_M)*direction
            xy=transform([center],pose)[0]
            yaw=math.atan2(math.sin(pose[2]+b['axis_heading_rad']),math.cos(pose[2]+b['axis_heading_rad']))
            self.beam=dict(rgb=copy.deepcopy(self.goal.e2e_observed[-1]),pose_own_m=[*xy.tolist(),yaw],
                           grip_base_m=b['grip_base_m'],axis_heading_rad=b['axis_heading_rad'])
        return trace

    def commanded(self,action,now):
        if action['kind']=='arm':self.servo[action['servo_id']]=action['pulse']
        elif action['kind']=='look':self.servo[6]=action['pan_pulse']
        self.goal.command(dict(t=now,**action))

    def route(self,profiles,pulse_budget):
        if self.robot_id!='r1' or self.beam is None:return None
        beam={k:self.beam[k] for k in ('rgb','pose_own_m')}
        return self.goal.route_to_B(beam,now=self.now,profiles=profiles,pulse_budget=pulse_budget)

    def own_inputs_at(self,now):
        refs=[r for r in self.goal.e2e_observed if r['t_sim']<=now]
        if not refs:raise own.ContractViolation('OWN_RGB_NOT_YET_RECEIVED')
        if self.packet is not None:
            mapped=copy.deepcopy(self.packet['route']['own_map'])
        else:
            # Snapshot wall segments are measured at this own frame, in own start.
            pose=np.asarray(self.goal.explorer.local_pose,float)
            lines=self.wall_segments
            walls=[dict(a=transform([a],pose)[0].tolist(),b=transform([b],pose)[0].tolist(),
                        sources=[refs[-1]]) for a,b in lines]
            ref=self.goal.e2e_gate.references.get('B')
            mapped=dict(robot_id=self.robot_id,frame=self.robot_id+'/own_start',map_version=self.revision,
                pose=dict(mean=pose.tolist(),covariance=np.asarray(self.goal.pose_covariance()).tolist(),sources=[refs[-1]]),
                walls=walls,goal=dict(label='B',sources=[ref['ref']]) if ref else None,sources=refs)
        own.validate_map(mapped,self.robot_id,now,refs)
        return dict(own_map=mapped,observed_rgb=refs,
                    own_route=self.packet['route'] if self.packet is not None else None)

    def frame_at(self,now):return self.frame if self.frame is not None and self.frame.t<=now else None
    def clock(self):return self.now
    def job(self):return None
    def belief(self):raise own.ContractViolation('LEGACY_BELIEF_FORBIDDEN')
    def call(self,*args,**kwargs):raise own.ContractViolation('UNBOUND_LEGACY_ACTION')


class Link:
    """Create an identity checked S4 link without the unrelated legacy stop API."""
    @staticmethod
    def build(robot,condition):
        from harness.s4_llm_host import Link as S4Link
        link=S4Link.__new__(S4Link)
        link.inner=robot;link.robot_id=robot.robot_id;link.origin_s=0.
        link.stop_adapter=None;link._counter=0;link._call_ref=None
        return link
