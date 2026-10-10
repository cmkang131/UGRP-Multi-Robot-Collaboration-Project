"""Opt-in continuous own-RGB goal navigation and temporal teach/repeat.

VT&R source/allowed adaptations and fixed gates: egomap56 README.
No simulator, world coordinates, static geometry, peer inputs or reset-PF.
"""
import copy
import math
from types import SimpleNamespace
import cv2
import numpy as np
from harness.active_camera import bind, goal_camera
from harness.active_wall_mapping import compose, inverse, pulse_command
from harness.active_navfn_start import StartRecoveryNavigator
from harness.own_teach_capture import TeachGraph
from harness.own_traversal_graph import own_sample, heading_twist
from harness.self_map_closed_loop import remembered_goal, own_measurement, HUES
from harness.self_map_landmark_sensor import Sensor
from harness.self_map_csm import sample_segments
from harness.public_navigation_unknown import from_observed_grid
from harness.public_navigation_recovery import issued_twist
from harness.self_odom_grid import transform
from harness.self_map_prob import wrap

OPTION='continuous_v1'
PITCH='stationary_ultrasonic_v1'


def attach(explorer, *, goal_route='off', heading_mode='path_tangent_v1',heading_host='off',dev_light=False):
    if goal_route=='off':return explorer
    if goal_route!=OPTION:raise ValueError('UNKNOWN_GOAL_ROUTE')
    return GoalRoute(explorer,heading_mode=heading_mode,heading_host=heading_host,dev_light=dev_light)


def box_detector():
    from harness import markerless_box as box, zone_color_boxes as colors
    measured=SimpleNamespace(**{**vars(box),'camera_extrinsics':lambda servo:goal_camera(servo,'camera_v3')})
    detect=bind(colors.detect_own,_mb=measured)
    return lambda rgb,servo:detect(cv2.cvtColor(rgb,cv2.COLOR_RGB2BGR),servo,
        kinds=('cyan',),profile=colors.OWN_PROFILE_ZONE)['detections']


class MissionNavigator(StartRecoveryNavigator):
    """eg50 persistent mission; only failed local navigation action is reset."""
    def __init__(self):
        super().__init__();self.mission=None

    def blocked(self,goal,resolution):
        if self.mission is not None and np.linalg.norm(np.asarray(goal)-self.mission)<.01:return False
        return super().blocked(goal,resolution)

    def action_failed(self,t,reason):
        mission=copy.deepcopy(self.mission)
        self.requested_goal=None
        super().action_failed(t,reason)
        if mission is not None:
            self.blacklist=[p for p in self.blacklist if np.linalg.norm(p-mission)>.01]
            self.event(t,'mission_retained_local_action_failed',cause=reason,mission=mission.tolist())

    def update(self,costmap,pose,t,static_goal=None):
        self.mission=None if static_goal is None else np.asarray(static_goal).copy()
        return super().update(costmap,pose,t,static_goal=static_goal)


class StationaryPitch:
    """Causal P0 range/plane root; at most 60s, no movement or GT requests."""
    def __init__(self,*,pitch_calibration='off',ultrasonic_front='off'):
        if pitch_calibration not in ('off',PITCH):raise ValueError('UNKNOWN_PITCH_CALIBRATION')
        if pitch_calibration!= 'off' and ultrasonic_front!='on_v1':raise ValueError('OWN_ULTRASONIC_MUST_BE_ENABLED')
        self.option=pitch_calibration;self.started=None;self.values=[];self.events=[];self.by_servo={};self.last_servo=None

    def command(self,t):
        if self.option=='off':return None
        return dict(t=float(t),kind='hold')

    def observe(self,legacy,*,t,reading,servo,observation,last_command):
        if self.option=='off':return legacy
        from harness.goal_route_p0 import pitch_sample,PITCH as ROOT_OPTION
        self.last_servo=tuple(sorted(servo.items())) if servo is not None else self.last_servo
        if self.started is None:self.started=t
        if t-self.started>60:return dict(done=True,pitch_offset_rad=self.offset)
        # A commanded move is not a measured standstill; require its finite tail
        # plus the frozen .7s body settling allowance before using a sample.
        if last_command and last_command['kind']!='hold' and t-last_command['t']<last_command.get('duration_s',0)+.7:
            return dict(done=False,accepted=False,reason='command_not_settled')
        origin=np.asarray(observation['camera_origin']);candidates=[]
        for segment in observation['segments']:
            a,b=np.asarray(segment);v=b-a
            if np.linalg.norm(v)<1e-8:continue
            n=np.array([-v[1],v[0]]);n/=np.linalg.norm(n)
            if n[0]<0:n=-n
            # Camera's ray through a projected floor contact encodes the raw
            # nominal pixel ray, without introducing a world wall position.
            if min(a[1],b[1])<=0<=max(a[1],b[1]) and abs(v[1])>1e-8:
                p=a+v*(-a[1]/v[1]);ray=np.r_[p,0.]-origin
                candidates.append((float(np.linalg.norm(p)),n,ray))
        if not candidates:return dict(done=False,accepted=False,reason='no_frontal_contact')
        _,normal,ray=min(candidates,key=lambda x:x[0])
        e=pitch_sample(None,reading=reading,camera_origin=origin,nominal_ray=ray,
            wall_normal=normal,pitch_bias=ROOT_OPTION)
        e.update(t=t,servo=copy.deepcopy(servo));self.events.append(e)
        if e['accepted']:
            self.values.append(e['pitch_offset_rad'])
            self.by_servo.setdefault(self.last_servo,[]).append(e['pitch_offset_rad'])
        return dict(done=t-self.started>=60,pitch_offset_rad=self.offset,**{k:v for k,v in e.items() if k not in ('t','servo','pitch_offset_rad')})

    @property
    def offset(self):
        values=self.by_servo.get(self.last_servo,[])
        return None if not values else float(np.median(values))

    def camera(self,legacy):
        if self.option=='off' or self.offset is None:return legacy
        origin,rotation=legacy;c,s=math.cos(self.offset),math.sin(self.offset)
        return origin,np.array([[c,0,-s],[0,1,0],[s,0,c]])@rotation


class GoalRoute:
    def __init__(self,explorer,*,heading_mode='path_tangent_v1',heading_host='off',dev_light=False):
        if heading_mode not in ('off','path_tangent_v1'):raise ValueError('UNKNOWN_HEADING_MODE')
        self.explorer=explorer;self.robot_id=explorer.robot_id;self.started=explorer.started
        self.dev_light=dev_light;self.heading_mode=heading_mode;self.stage='explore';self.done=False;self.declared=False
        from harness.goal_route_heading import Host,OPTION as HOST
        if heading_host not in ('off',HOST):raise ValueError('UNKNOWN_HEADING_HOST')
        self.heading_host=Host(self.robot_id,explorer.motion_model) if heading_host==HOST and heading_mode!='off' else None
        self.entities={};self.reached={};self.active=None;self.leg_start=self.started
        self.graph=TeachGraph(self.robot_id);self.navigator=MissionNavigator()
        self.sensor=Sensor(HUES);self.detect_boxes=box_detector()
        self.events=[];self.cues=[];self.matches=[];self.inputs=[];self.last_command=None
        self.box_track=None;self.box_count=0;self.streak=0;self.route=None;self.cursor=0
        self.last_localize=-math.inf;self.match_nodes=set();self.offsets=[]
        self.last_trace=None;self.labels=None;self.current_patches=[];self.tracking_blocked=False
        original=explorer.goal.detector
        def capture(*args,**kwargs):
            patches,labels,diag=original(*args,**kwargs)
            self.labels=labels;self.current_patches=patches
            return patches,labels,diag
        explorer.goal.detector=capture
        original_observe=explorer.goal.observe
        def memory_observe(*args,**kwargs):
            patches,labels,diag=original_observe(*args,**kwargs)
            # Continue measuring/memorizing B, but do not let a reached B
            # replace the remaining box's frontier mission.
            return ([] if 'B' in self.reached else patches),labels,diag
        explorer.goal.observe=memory_observe

    def command(self,row):
        self.last_command=copy.deepcopy(row)
        self.explorer.command(row)  # continuous through approach and return

    def event(self,t,reason,**data):self.events.append(dict(t=float(t),reason=reason,**data))

    def _entity(self,name,center,t,frame_id,sha,**evidence):
        if name not in self.entities:
            self.entities[name]=dict(kind=name,center_m=list(center),first_t=t,first_frame_id=frame_id,
                frame_sha256=sha,source='own',node=self.graph.anchor,**evidence)
            observed=evidence.get('observation',{})
            self.entities[name]['first_observed_t']=observed.get('first_t',t)
            prior=[n for n in self.graph.nodes if n['t']<=self.entities[name]['first_observed_t']]
            self.entities[name]['first_observed_node']=prior[-1]['id'] if prior else 0
            self.event(t,'own_entity_confirmed',entity=name,node=self.graph.anchor,frame_id=frame_id)
            self.cues.append(copy.deepcopy(self.entities[name]))
            self.graph.nodes[self.graph.anchor]['entities'].append(copy.deepcopy(self.entities[name]))
        else:self.entities[name]['center_m']=list(center)
        self.entities[name]['last_t']=t

    def _localize(self,sample,t):
        cov=self.explorer.memory.self_map.odom.covariance
        uncertain=math.sqrt(float(np.linalg.eigvalsh(cov[:2,:2]).max()))>=.15 or math.sqrt(max(0,cov[2,2]))>=math.radians(5)
        if not uncertain:self.tracking_blocked=False
        wanted=None
        if self.stage=='return' and self.route:
            nearest=min(self.route['nodes'],key=lambda i:math.dist(sample['pose'][:2],self.graph.nodes[i]['pose'][:2]))
            if nearest not in self.match_nodes and math.dist(sample['pose'][:2],self.graph.nodes[nearest]['pose'][:2])<=.5:
                wanted=nearest
        if (not uncertain and wanted is None) or t-self.last_localize<10:return
        self.last_localize=t
        # Causal graph: observe(current frame) happens AFTER this call.
        e=self.graph.match(sample,wanted);e['trigger']='tracking_uncertainty' if uncertain else 'repeat_node'
        self.matches.append(e)
        if e['status']!='accepted':
            if uncertain:
                self.tracking_blocked=True
                self.event(t,'would_stop_tracking_uncertain' if self.dev_light else 'tracking_uncertain_stop',reason_detail=e.get('reason'),reset=False)
            return
        self.tracking_blocked=False
        if wanted is not None:self.match_nodes.add(wanted)
        g=self.explorer.memory.self_map
        delta=compose(e['pose'],inverse(sample['pose']))
        g.poses=np.array([compose(delta,p) for p in g.poses])
        c,s=math.cos(delta[2]),math.sin(delta[2]);R=np.array([[c,-s,0],[s,c,0],[0,0,1]])
        g.pending_cov=R@g.pending_cov@R.T  # correlated map: no variance shrink
        self.offsets.append(dict(t=t,delta=delta.tolist()))
        self.event(t,'route_local_match',node=e['node'],delta=delta.tolist(),reset=False)
        # Preserve map/odom TF; rebuild is performed by the frozen graph cycle.
        sample['pose']=list(g.odom.pose);sample['covariance']=g.odom.covariance.tolist()

    def _select(self,t):
        unseen=[k for k in self.entities if k not in self.reached]
        if self.active is None and unseen:
            self.active=min(unseen,key=lambda k:self.entities[k]['first_t'])
            self.stage='approach';self.streak=0
            self.navigator.reset_action();self.navigator.target=None
            self.event(t,'frontier_stopped_goal_approach',entity=self.active)

    def _arrival(self,t,frame_id,pose,box_visible):
        if self.active is None:return
        name=self.active;entity=self.entities[name]
        near=math.dist(pose[:2],entity['center_m'])<=.20
        if name=='B':
            fresh=any(p.get('confirmed_t') is not None for p in self.current_patches)
            lower=0 if self.labels is None else int(np.count_nonzero(self.labels[2*self.labels.shape[0]//3:]))
            evidence=fresh and lower>=self.explorer.goal.options.min_pixels
        else:evidence=box_visible
        self.streak=self.streak+1 if near and evidence else 0
        if self.streak<5:return
        self.reached[name]=dict(t=t,frame_id=frame_id,pose=pose.tolist(),node=self.graph.anchor)
        self.graph.nodes[self.graph.anchor]['entities'].append(dict(kind=name+'_reached',**self.reached[name]))
        self.cues.append(dict(kind=name+'_reached',**self.reached[name]))
        self.event(t,'goal_reached',entity=name,frame_id=frame_id,pose=pose.tolist())
        self.active=None;self.streak=0;self.leg_start=t
        if len(self.reached)==2:
            self.graph.seal();self.route=self.graph.route(self.graph.anchor,0)
            self.stage='return';self.cursor=0
            self.event(t,'teach_complete_repeat_started',nodes=len(self.graph.nodes),length_m=self.route['length_m'])
        else:
            self.stage='explore'
            n=self.explorer.navigator
            n.target=n.frontier=None;n.path=[];n.reset_action();n.finished=False
            self.explorer.revisit=None;self.explorer.plan=None
            if hasattr(n,'locked'):n.locked=False

    def _return_target(self,pose):
        points=self.route['samples']
        while self.cursor<len(points) and math.dist(pose[:2],points[self.cursor]['pose'][:2])<=.05:self.cursor+=1
        return points[self.cursor]['pose'][:2] if self.cursor<len(points) else self.graph.nodes[0]['pose'][:2]

    def receive(self,*,robot_id,t,frame_id,rgb,servo,observation,frame_sha256,own_range=None):
        if robot_id!=self.robot_id:raise ValueError('PEER_INPUT_FORBIDDEN')
        if self.done:
            trace=copy.deepcopy(self.last_trace);cmd=dict(t=float(t),kind='hold')
            trace.update(t=t,frame_id=frame_id,command=cmd,stage=self.stage,status=self.stage)
            return cmd,trace
        cmd,trace=self.explorer.receive(robot_id=robot_id,t=t,frame_id=frame_id,rgb=rgb,servo=servo,observation=observation)
        g=self.explorer.memory.self_map
        sample=own_sample(trace,observation,rgb=rgb,frame_sha256=frame_sha256,covariance=g.odom.covariance)
        self._localize(sample,t)
        pose=np.asarray(sample['pose'])
        if not self.graph.sealed:self.graph.observe(sample)
        points=own_measurement(rgb,servo)
        features=self.sensor.measure(cv2.cvtColor(rgb,cv2.COLOR_RGB2BGR),servo,points)
        if features:
            self.cues.append(dict(t=t,frame_id=frame_id,pose=pose.tolist(),features=features,source='own'))
        self.inputs.append(dict(t=t,frame_id=frame_id,sha256=frame_sha256,own_range=copy.deepcopy(own_range)))
        b=remembered_goal(trace['goal'],t=t,frame_id=frame_id,frame_sha256=frame_sha256)
        if b is not None and 'B' not in self.reached:
            self._entity('B',b['center_m'],t,frame_id,frame_sha256,observation=b)
        boxes=self.detect_boxes(rgb,servo);box_visible=False
        if boxes:
            box=min(boxes,key=lambda b:np.linalg.norm(b['estimated_box_center_base_m'][:2]))
            center=transform([box['estimated_box_center_base_m'][:2]],pose)[0]
            self.box_count=self.box_count+1 if self.box_track is not None and math.dist(center,self.box_track)<=.10 else 1
            self.box_track=center;box_visible=True
            if self.box_count>=3 and 'box' not in self.reached:self._entity('box',center,t,frame_id,frame_sha256,observation=box)
        else:self.box_count=0
        if self.stage!='return':
            self._select(t);self._arrival(t,frame_id,pose,box_visible);self._select(t)
        if t-self.leg_start>=270:
            self.done=True;self.stage='budget_exhausted';self.event(t,'leg_budget_exhausted',reached=list(self.reached),active=self.active)
        target=None;nav=self.navigator;shared_used=False
        if self.stage=='approach':target=np.asarray(self.entities[self.active]['center_m'])
        elif self.stage=='return':
            target=np.asarray(self._return_target(pose))
            near=math.dist(pose[:2],self.graph.nodes[0]['pose'][:2])<=.20 and self.cursor>=len(self.route['samples'])
            self.streak=self.streak+1 if near else 0
            if self.streak>=5:
                self.done=self.declared=True;self.stage='declared';self.event(t,'return_start_declared',pose=pose.tolist())
        costmap=from_observed_grid(self.explorer.grid,self.explorer.pose,self.explorer.latest,set())
        wall=sample_segments(observation['segments']) if observation['segments'] else np.empty((0,2))
        if target is not None and not self.done:
            world_target=compose(self.explorer.map_to_odom,[*target,0.])[:2]
            plan=nav.update(costmap,self.explorer.pose,t,static_goal=world_target)
            raw=nav.command(costmap,self.explorer.pose,plan,t)
            twist=issued_twist(raw)
            path=plan.get('path_m',[])
            # The taught edge itself is the path during repeat; no unverified
            # spatial shortcut or global replan across a temporal corner.
            if self.heading_host is not None:
                if self.stage=='return':
                    local_path=[target];end=self.graph.nodes[0]['pose'][:2]
                else:
                    local_path=transform(path,inverse(self.explorer.map_to_odom)) if path else []
                    end=target
                if self.stage=='return' or (path and not nav.phase):
                    shared_used=True
                    cmd,pulse=self.heading_host.command(t=t,pose=pose,path=local_path,goal=end,costmap=costmap,
                        core=nav.core,points=wall,map_pose=self.explorer.pose,dev_light=self.dev_light)
                else:
                    cmd,pulse=pulse_command(twist,t,costmap=costmap,pose=self.explorer.pose,core=nav.core,points=wall,
                        motion_model=self.explorer.motion_model,translation_policy='forward_only_v1')
            elif self.stage=='return':twist,_=heading_twist(pose,target)
            elif self.heading_mode!='off' and not nav.phase and path:
                future=next((p for p in path if math.dist(p,self.explorer.pose[:2])>.05),path[-1])
                twist,_=heading_twist(self.explorer.pose,future)
            if self.heading_host is None:
                cmd,pulse=pulse_command(twist,t,costmap=costmap,pose=self.explorer.pose,core=nav.core,points=wall,
                    motion_model=self.explorer.motion_model,translation_policy='forward_only_v1' if self.heading_mode!='off' else 'off')
            trace.update(path=path,status=plan['status'],pulse=pulse)
            if nav.clear_requested:self.explorer.clear_navigation(t);nav.clear_requested=False
        elif self.heading_mode!='off' and not self.done:
            # Reuse the same heading law in frontier traversal, not S2's
            # map-specific final east alignment. Recovery reverse becomes hold.
            path=trace.get('path',[]);n=self.explorer.navigator
            if self.heading_host is not None and not n.phase and path:
                shared_used=True
                local_path=transform(path,inverse(self.explorer.map_to_odom))
                cmd,pulse=self.heading_host.command(t=t,pose=pose,path=local_path,goal=local_path[-1],costmap=costmap,
                    core=n.core,points=wall,map_pose=self.explorer.pose,dev_light=self.dev_light)
            elif not n.phase and path:
                target=next((p for p in path if math.dist(p,self.explorer.pose[:2])>.05),path[-1])
                twist,_=heading_twist(self.explorer.pose,target)
            else:twist=np.zeros(3) if cmd['kind']=='hold' else issued_twist(cmd)
            if self.heading_host is None or n.phase or not path:
                cmd,pulse=pulse_command(twist,t,costmap=costmap,pose=self.explorer.pose,core=n.core,points=wall,
                    motion_model=self.explorer.motion_model,translation_policy='forward_only_v1')
            trace['pulse']=pulse
        if self.heading_host is not None and trace.get('pulse',{}).get('blocked'):
            self.event(t,'would_stop_collision_guard' if self.dev_light else 'collision_guard_stop',stage=self.stage,dev_light=self.dev_light)
        if self.dev_light and not shared_used and not self.done and cmd['kind']=='hold' and 'twist' in locals() and np.linalg.norm(twist)>0:
            trial,trial_pulse=pulse_command(twist,t,motion_model=self.explorer.motion_model,
                translation_policy='forward_only_v1' if self.heading_mode!='off' else 'off')
            if trial['kind']!='hold':
                self.event(t,'would_stop_collision_guard',stage=self.stage,dev_light=True)
                cmd=trial;trace['pulse']=trial_pulse
        if own_range is not None and own_range['valid'] and 0<=t-own_range['t']<=.2+1e-9:
            from harness.ultrasonic_model import DEFAULT_SPEC
            from harness.public_navigation.costmap import HALF
            # Same 1.2s Nav2 time-before-collision, static sensor/footprint CAD.
            speed=max(0.,trace.get('pulse',{}).get('predicted_delta',[0,0,0])[0]/.2)
            clearance=DEFAULT_SPEC.face_x_m+own_range['range_m']-HALF[0]
            if speed>0 and clearance<=1.2*speed:
                self.event(t,'would_stop_ultrasonic_margin' if self.dev_light else 'ultrasonic_stop',clearance_m=clearance)
                if not self.dev_light:cmd=dict(t=float(t),kind='hold')
        if self.done or (self.tracking_blocked and not self.dev_light):cmd=dict(t=float(t),kind='hold')
        trace.update(stage=self.stage,command=cmd,local_pose=pose.tolist(),pose=self.explorer.pose.tolist(),
            remembered_entities=copy.deepcopy(self.entities),reached=copy.deepcopy(self.reached),
            declared_goal='B' in self.reached,declared_return=self.declared,tracking_reset=False,
            route=dict(nodes=len(self.graph.nodes),edges=len(self.graph.edges),cursor=self.cursor,
                length_m=None if self.route is None else self.route['length_m'],matches=len(self.matches)),
            sigma_xy=math.sqrt(float(np.linalg.eigvalsh(g.odom.covariance[:2,:2]).max())))
        self.last_trace=copy.deepcopy(trace)
        return cmd,trace

    def snapshot(self):
        return dict(option=OPTION,coordinate_frame=f'{self.robot_id}/own_odom',graph=self.graph.snapshot(),
            entities=copy.deepcopy(self.entities),reached=copy.deepcopy(self.reached),cues=copy.deepcopy(self.cues),
            return_route=copy.deepcopy(self.route),matches=copy.deepcopy(self.matches),offsets=copy.deepcopy(self.offsets),
            events=copy.deepcopy(self.events),forced_loss=False,failed_P0_options='off')


def calibrated_observation(legacy, *, calibration, rgb, servo, **kwargs):
    """Apply a completed own stationary estimate to the existing wall frontend."""
    if calibration.option=='off':return legacy
    from harness import active_wall_vision as vision
    from harness.active_camera import transform as nominal
    detector=bind(vision.observe,camera_transform=lambda angles:calibration.camera(nominal(angles)))
    return detector(rgb,servo,**kwargs)
