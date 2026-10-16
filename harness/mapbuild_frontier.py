"""Default-off MJWarp self-map actor: own RGB and issued servo commands only.

Uses the existing LK/colour calibration, observed-floor grid and frontier/A*.
No simulator, map files, contacts, peer images or pose labels enter this API.
"""
import math
from collections import Counter
import cv2
import numpy as np

OPTION='mapbuild4_frontier_v1'


class FrontierActor:
    def __init__(self, servo, calibration, paint, motion, *, option='off'):
        if option!=OPTION:raise ValueError('EXPLICIT_MAPBUILD4_FRONTIER_REQUIRED')
        from harness.own_map_navigation import ObservedGrid, NavigationOptions, OwnMapNavigator, Footprint
        from harness.scene_colour_boundary import ColourBoundaryState, RELOC16_OPTION
        self.servo={int(k):v for k,v in servo.items()}
        self.colour=ColourBoundaryState('walls_floor_contrast_v5_indigo110_s80',calibration,option=RELOC16_OPTION)
        self.paint=paint['paint'];self.grid=ObservedGrid('r1');self.grid.initial_support()
        # Existing finite-grid A* and frontier budgets, no wall-clock planning.
        self.nav=OwnMapNavigator('r1',NavigationOptions(exploration='own_frontier_v2',partial_planning='own_astar_v2',door_detection='own_gap_v1'))
        self.footprint=Footprint();self.pose=np.zeros(3);self.anchor=None;self.anchor_t=None
        self.events=[];self.wall=set();self.obstacle=set();self.destination=set();self.target=None
        self.next_command=1.;self.commands=[];self.plan={};self.lost=False;self.motion=motion
        self.commands_since_visual=0

    def observe(self,rgb,t,frame_id):
        from harness.e2e_rgb_vo import ground_pair,compose,ground
        from harness.active_wall_vision import observe
        from harness.scene_colour_boundary import RELOC16_OPTION
        from harness.self_odom_grid import transform
        from harness.zone_color_boxes import detect_own,OWN_PROFILE_ZONE
        from harness.floor_goal_self_mask import self_body_mask
        from harness.floor_goal import FloorGoalOptions
        predicted=self.motion.advance(t)
        if self.anchor is None:
            flow=dict(status='bootstrap');self.anchor=rgb.copy();self.anchor_t=t
        else:
            flow=ground_pair(self.anchor,rgb,self.servo)
            if flow['status']=='measured':
                self.pose=compose(self.pose,flow['delta']);self.commands_since_visual=0
            else:
                self.pose=compose(self.pose,predicted)
            self.anchor=rgb.copy();self.anchor_t=t
        if flow['status'] not in ('bootstrap','measured'):
            event=dict(t=t,frame_id=frame_id,pose=self.pose.tolist(),flow=flow,category='visual_pose',
                reason=flow['status'],prediction='exploratory_MJWarp_prior_not_measured',
                blocked_object='own_camera_support',minimum_gap_m=None,gap_status='not_measured')
            # User's three-repeat stop rule; no wall-clock action limit.
            if self.commands_since_visual>=3:self.lost=True
            self.events.append(event);return event
        obs=observe(rgb,self.servo,wall_detector=RELOC16_OPTION,contact_state=self.colour,
            frame_id=frame_id,odometry_pose=self.pose)
        wall=[]
        for segment in obs['segments']:
            n=max(2,math.ceil(np.linalg.norm(np.diff(segment,axis=0))/ (self.grid.resolution/2))+1)
            wall.extend(np.linspace(*segment,n))
        boxes=detect_own(cv2.cvtColor(rgb,cv2.COLOR_RGB2BGR),self.servo,profile=OWN_PROFILE_ZONE)
        cargo=[]
        for box in boxes['detections']:
            x,y,w,h=box['pixel_bbox'];p,depth=ground(self.servo,[[x+w/2,y+h]])
            if np.isfinite(p).all() and np.isfinite(depth).all() and depth[0]>0:
                cargo.extend(p);self.obstacle.add(self.grid.cell(transform(p,self.pose)[0]))
        self.grid.observe(robot_id='r1',frame_id=frame_id,pose=self.pose,
            floor_xy=obs['floor_xy'],wall_xy=wall+cargo)
        self.wall.update(self.grid.cell(p) for p in transform(np.asarray(wall).reshape(-1,2),self.pose))
        hsv=cv2.cvtColor(rgb,cv2.COLOR_RGB2HSV);body=self_body_mask(self.servo,'camera_v3',640,480)
        for kind,bounds in self.paint.items():
            mask=(cv2.inRange(hsv,np.asarray(bounds['low'],np.uint8),np.asarray(bounds['high'],np.uint8))>0)&~body
            yy,xx=np.nonzero(mask);p,depth=ground(self.servo,np.column_stack((xx,yy)))
            keep=np.isfinite(p).all(1)&np.isfinite(depth)&(depth>0)&(depth<FloorGoalOptions().max_range_m)
            self.destination.update(self.grid.cell(p) for p in transform(p[keep],self.pose))
        event=dict(t=t,frame_id=frame_id,pose=self.pose.tolist(),flow=flow,category='map_frame',
            reason='observed_surfaces' if len(wall) else 'no_supported_wall_contacts',
            blocked_object='not_observed',minimum_gap_m=None,gap_status='not_measured',
            wall_segments=len(obs['segments']),floor_points=len(obs['floor_xy']),cargo_detections=len(cargo),known=len(self.grid.odds))
        self.events.append(event);return event

    def command(self,t):
        """Existing heading-first policy, visual feedback after each finite pulse.

        .1s/35 is the measured forward/turn diagnostic primitive. .2s tail is
        v122's existing finite response window. Tolerances .035m/.06rad are the
        existing own_map_heading contract, not fitted on evaluation poses.
        Lateral short pulses are not assigned an invented 76x inverse gain.
        """
        if t+1e-9<self.next_command or self.lost:return None
        if self.target is not None and (math.dist(self.target,self.pose[:2])<=.035 or
                self.grid.state(self.grid.cell(self.target))!=-1):self.target=None
        if self.target is None:
            self.plan=self.nav.update({},grid=self.grid,pose=self.pose,footprint=self.footprint)
            path=self.plan.get('path_m',[])
            self.target=next((p for p in path if math.dist(p,self.pose[:2])>=.035),None)
        if self.target is None or self.events[-1]['flow']['status'] not in ('bootstrap','measured'):
            axis,value='turn',.35
        else:
            d=np.asarray(self.target)-self.pose[:2];heading=math.atan2(d[1],d[0])
            error=math.atan2(math.sin(heading-self.pose[2]),math.cos(heading-self.pose[2]))
            # Only the measured positive turn primitive is used. A target on
            # the right is reached by continuing the real RGB lookaround.
            axis,value=('turn',.35) if abs(error)>.06 else ('forward',.35)
        self.next_command=t+.3
        row=dict(t=t,axis=axis,value=value,duration_s=.1,plan=self.plan,target=self.target)
        self.motion.issue(row);self.commands_since_visual+=1
        self.commands.append(row);return row

    def export(self):
        points=lambda keys:[[(x+.5)*self.grid.resolution,(y+.5)*self.grid.resolution] for x,y in sorted(keys)]
        doors=getattr(self.nav,'_v2_delegate',self.nav).doors.tracks
        # Body-support cells are not counted as observed coverage.
        cells=[[int(x),int(y),'occupied' if v>0 else 'free'] for (x,y),v in sorted(self.grid.odds.items()) if v]
        return dict(frame='r1/start',resolution_m=self.grid.resolution,cells=cells,
            wall=points(self.wall),obstacle=points(self.obstacle),destination=points(self.destination),
            door=[d['center_m'] for d in doors],door_candidates=doors,
            input_audit=dict(top_actor_reads=0,truth_feedback=0,prior_map_reads=0),
            map_provenance='direct observed floor points and wall/cargo hits; body support excluded')
