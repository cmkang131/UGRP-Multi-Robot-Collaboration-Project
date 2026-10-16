"""Opt-in carry geometry, heading-forward and RGB stationarity, no plant inputs.

Constants/provenance: experiments/2026-10-16-reloc20/references.md.
The footprint is a rotation-invariant enclosure of the old arm envelope and
issued-FK cargo corners. This deliberately trades narrow-route availability
for checking the entire load at every heading, including turn-in-place.
"""
from collections import Counter, deque
import copy
import heapq
import json
import math
from pathlib import Path

import cv2
import numpy as np

from harness.static_keepouts import rect_distance

ROOT = Path(__file__).resolve().parents[1]
# locdiag largest observed geometric penetration + one maximum carry tick.
# DEV engineering clearance, not a certified bound on localization error.
MARGIN_M = .007014 + .08 * .1
GRID_M = .05  # existing zone_teacher.GRID_M
BUDGET = 40000  # existing reloc14 node budget, never wall time


def wrap(a):
    return math.atan2(math.sin(a), math.cos(a))


def heading_forward(pose, target):
    """Turn first; the inherited .04rad carry yaw tolerance releases forward.

    Speeds/gains are unchanged carry bounds (.08m/s, .1rad/s, .9 and .6).
    No mixed or lateral command is generated, even at an acquisition waypoint.
    """
    distance = math.dist(pose[:2], target)
    if distance <= 1e-12:
        return (0., 0., 0.)
    error = wrap(math.atan2(target[1]-pose[1], target[0]-pose[0])-pose[2])
    if abs(error) > .04:
        return (0., 0., max(-.1, min(.1, .6*error)))
    return (min(.08, .9*distance), 0., 0.)


class LoadedRoute:
    def __init__(self, static):
        self.static = static
        self.radius = .26 + MARGIN_M  # retain the pre-existing arm envelope
        self.footprint = None
        self.rects = [(o['id'], (*o['center_m'], *o['half_extents_m'], o.get('yaw_rad', 0.)))
                      for o in static['obstacles']]
        # Only an explicitly authored map extension is accepted. No setup/
        # scenario/eval dictionary is accepted by this controller.
        for o in static.get('fixed_floor_keepouts', []):
            self.rects.append((o['id'], (*o['center_m'], *o['half_extents_m'], o['yaw_rad'])))
        self.counts = Counter()
        self.minimum_gaps = {}
        self.last = {}
        self.events = []
        self.plan_funnel = Counter()

    def update_load(self, holding, kind, grasp_pwm, pwm):
        if not holding or grasp_pwm is None:
            return
        from sim.grasp_act_solo_lookback import object_transform
        from sim.grasp_act_solo_teacher import cargo
        T = object_transform(kind, grasp_pwm, pwm)
        h = np.asarray(cargo(kind).dims_m)/2
        corners = np.array([[x,y,z] for x in (-h[0],h[0]) for y in (-h[1],h[1]) for z in (-h[2],h[2])])
        p = corners @ T[:3,:3].T + T[:3,3]
        self.footprint = p[:,:2].tolist()
        self.radius = max(.26, float(np.linalg.norm(p[:,:2],axis=1).max())) + MARGIN_M

    def gap(self, point, discs, radius=None):
        r = self.radius if radius is None else radius
        gaps = [(rect_distance(point, rect)-r, name) for name, rect in self.rects]
        gaps += [(math.dist(point,d[:2])-r-d[2], f'own_rgb_disc_{i}') for i,d in enumerate(discs)]
        x0,x1,y0,y1 = self.static['bounds_m']
        gaps += [(min(point[0]-x0,x1-point[0],point[1]-y0,y1-point[1])-r, 'map_bounds')]
        gap, name = min(gaps)
        return dict(category='loaded_footprint', blocked_object=name, minimum_gap_m=gap,
                    gap_scope='rotation_invariant_body_cargo_enclosure_to_authored_map_or_own_rgb')

    def segment(self, start, end, discs, radius=None):
        # Distance to an obstacle is 1-Lipschitz. Midpoint samples plus half
        # their interval bound the entire continuous segment, not only nodes.
        length=math.dist(start,end);n=max(1,math.ceil(length/.01))
        values=[self.gap((start[0]+(end[0]-start[0])*i/n,start[1]+(end[1]-start[1])*i/n),discs,radius) for i in range(n+1)]
        context=min(values,key=lambda x:x['minimum_gap_m']).copy()
        context['minimum_gap_m'] -= length/(2*n)
        context['reason']='swept_enclosure_clear' if context['minimum_gap_m']>=0 else 'swept_enclosure_overlap'
        return context['minimum_gap_m']>=0,context

    def reject(self, context, *, now=None):
        self.last=dict(context)
        key=(context['reason'],context['blocked_object'])
        self.counts[key]+=1
        self.minimum_gaps[key]=min(self.minimum_gaps.get(key,math.inf),context['minimum_gap_m'])
        # Bounded event history; complete counts and per-tick last are retained.
        if len(self.events)<BUDGET:self.events.append(dict(t=now,**context))

    def plan(self,start,goal,bounds,discs,*,rects=(),radius=None,**kwargs):
        # During pickup callers use a body-relative frame. Only travel and
        # destination calls use the authored map frame and the loaded radius.
        from scripts.zone_teacher import plan_path
        if tuple(bounds)!=tuple(self.static['bounds_m']):
            return plan_path(start,goal,bounds,discs,rects=rects,radius=radius,budget=BUDGET)
        r=max(self.radius, radius or 0.)
        self.plan_funnel['candidates']+=1
        for label,p in [('start',start),('goal',goal)]:
            context=self.gap(p,discs,r)
            if context['minimum_gap_m']<0:
                context['reason']=label+'_enclosure_overlap';self.reject(context)
                self.plan_funnel['rejected_'+label]+=1;return None
        self.plan_funnel['endpoints_clear']+=1
        ok,context=self.segment(start,goal,discs,r)
        if ok:
            self.plan_funnel['accepted']+=1;return [start,goal]
        self.reject(dict(context,reason='direct_route_overlap_replan'))
        x0,x1,y0,y1=bounds
        # Origin at the exact start avoids an unchecked snap from an inflated
        # margin to a grid point. Goal is checked by its final connecting edge.
        def point(c):return (start[0]+c[0]*GRID_M,start[1]+c[1]*GRID_M)
        frontier=[(math.dist(start,goal),0.,(0,0))];cost={(0,0):0.};came={(0,0):None};visits=0;last=context
        while frontier and visits<BUDGET:
            _,g,c=heapq.heappop(frontier)
            if g!=cost[c]:continue
            visits+=1;p=point(c)
            if math.dist(p,goal)<=GRID_M*math.sqrt(2):
                ok,last=self.segment(p,goal,discs,r)
                if ok:
                    path=[goal,p]
                    while came[c] is not None:c=came[c];path.append(point(c))
                    self.plan_funnel['accepted']+=1;self.last=dict(reason='route_clear',category='loaded_footprint',blocked_object='none',minimum_gap_m=min(self.gap(x,discs,r)['minimum_gap_m'] for x in path),nodes=visits)
                    return list(reversed(path))
            for dx,dy in ((1,0),(-1,0),(0,1),(0,-1),(1,1),(1,-1),(-1,1),(-1,-1)):
                nc=(c[0]+dx,c[1]+dy);q=point(nc);ng=g+GRID_M*math.hypot(dx,dy)
                if ng>=cost.get(nc,math.inf):continue
                if not (x0+r<=q[0]<=x1-r and y0+r<=q[1]<=y1-r):continue
                ok,last=self.segment(p,q,discs,r)
                if not ok:continue
                cost[nc]=ng;came[nc]=c;heapq.heappush(frontier,(ng+math.dist(q,goal),ng,nc))
        self.plan_funnel['rejected_search']+=1
        self.reject(dict(last,reason='node_budget_exhausted' if visits>=BUDGET else 'no_enclosure_route',nodes=visits))
        return None

    def record(self):
        return dict(radius_m=self.radius,issued_cargo_corners_xy=self.footprint,clearance_m=MARGIN_M,
                    map_floor_keepouts=self.static.get('fixed_floor_keepouts',[]),last=self.last,
                    plan_funnel=dict(self.plan_funnel),rejections=[dict(category='loaded_footprint',reason=k[0],blocked_object=k[1],minimum_gap_m=self.minimum_gaps[k],N=v) for k,v in self.counts.items()],events=self.events)


class VisualStall:
    """Pixel stationarity, not metric loaded VO or measured wheel speed.

    Independent nominal increments keep the test live after suppression.
    Unknown texture/camera motion is never converted into zero displacement.
    """
    def __init__(self, fit):
        self.fit=fit;self.frames=deque();self.pose=np.zeros(3);self.suppressed=False
        self.last={};self.events=[];self.recovering=False;self.backed=0.;self.started=None
        self.stall_ticks=0;self.stall_s=0.;self.raw_delta=np.zeros(3)

    def issue(self, delta, dt):
        from harness.natural_floor_slam import compose
        self.raw_delta=np.asarray(delta);self.pose=compose(self.pose,delta)
        if self.recovering:self.backed+=max(0.,-float(delta[0]))
        if self.suppressed:self.stall_ticks+=1;self.stall_s+=dt
        return (0.,0.,0.) if self.suppressed else delta

    def observe(self,bgr,now,pwm,active):
        from harness.e2e_stall_odometry import flow_pair,FLOW
        from harness.e2e_rgb_vo import between
        servo=tuple(sorted((int(k),int(v)) for k,v in pwm.items() if int(k)!=1))
        while self.frames and now-self.frames[0][0]>FLOW['max_window_s']+1e-8:self.frames.popleft()
        rec=dict(t=now,status='warming_up',category='visual_stall',reason='insufficient_command_window',blocked_object='own_camera_stationarity_evidence',minimum_gap_m=None,gap_scope='not_applicable_image_evidence')
        previous=self.suppressed;self.suppressed=False
        if not active:self.frames.clear()
        else:
            for t,frame,old_servo,pose in reversed(self.frames):
                d=between(pose,self.pose)
                if np.linalg.norm(d[:2])<FLOW['minimum_expected_m']:continue
                if old_servo!=servo or abs(d[2])>FLOW['maximum_expected_yaw_rad']:
                    rec.update(reason='camera_command_or_yaw_changed');break
                flow=flow_pair(cv2.cvtColor(frame,cv2.COLOR_BGR2RGB),cv2.cvtColor(bgr,cv2.COLOR_BGR2RGB))
                rec.update(flow,before_t=t,expected_delta=d.tolist(),window_s=now-t)
                limits=self.fit['stationary_thresholds']
                qualified=flow['median_px'] is not None and flow['mean_abs_diff'] is not None
                self.suppressed=bool(qualified and all(flow[k]<=limits[k]+1e-12 for k in limits))
                rec['reason']='command_rgb_stationary_mismatch' if self.suppressed else ('rgb_progress_observed' if qualified else 'unknown_texture')
                break
            self.frames.append((now,bgr.copy(),servo,self.pose.copy()))
        rec['suppressed']=self.suppressed;self.last=rec
        if self.suppressed and not previous:
            self.events.append(dict(event='stall_detected',**rec));self.recovering=True;self.backed=0.;self.started=now
        if previous and not self.suppressed:self.events.append(dict(event='stall_released',**rec))

    def recovery(self, now):
        from harness.e2e_stall_odometry import PROGRESS
        if not self.recovering:return None
        if self.backed>=PROGRESS['backup_distance_m'] or now-self.started>=PROGRESS['backup_time_allowance_s']:
            self.events.append(dict(t=now,event='backup_end_replan',issued_backward_m=self.backed,reason='issued_backup_complete' if self.backed>=PROGRESS['backup_distance_m'] else 'backup_sim_cap',category='visual_stall',blocked_object='unidentified_own_rgb_stall',minimum_gap_m=None,gap_scope='not_applicable_image_evidence'))
            self.recovering=False;self.frames.clear();return (0.,0.,0.)
        return (-.05,0.,0.)  # inherited reverse limit; collision-checked by caller

    def record(self):
        return dict(last=self.last,events=self.events,stall_ticks=self.stall_ticks,stall_sim_s=self.stall_s,recovering=self.recovering,metric_vo=False)


def install(carry,plan):
    """Called once before any integration; every feature is default off."""
    carry.reloc20_heading=plan.get('reloc20_heading_forward_v1',False)
    carry.reloc20_route=LoadedRoute(carry.static) if plan.get('reloc20_loaded_footprint_v1',False) else None
    carry.reloc20_stall=None
    if plan.get('reloc20_visual_stall_v1',False):
        fit=json.loads((ROOT/'experiments/2026-10-16-reloc20/flow-fit.json').read_text())
        carry.reloc20_stall=VisualStall(fit);carry.loc.reloc20_stall=carry.reloc20_stall
    if carry.reloc20_route is not None:
        carry.plan_path=carry.reloc20_route.plan
        carry.radius=carry.reloc20_route.radius
        carry.rects=tuple(r for _,r in carry.reloc20_route.rects)
    if plan.get('reloc20_contact_ode_v1',False):
        if not carry.loc.drive_model_enabled:raise ValueError('ODE requires command drive model')
        from harness.reloc20_drive_ode import CommandDriveModel
        carry.loc.drive_model=CommandDriveModel();carry.loc.reloc20_ode=True


def travel_drive(carry,pose,target):
    if getattr(carry,'reloc20_heading',False):return heading_forward(pose,target)
    return carry.heading_drive(pose,target,carry.travel_heading)


def guard(carry,drive,now):
    route=getattr(carry,'reloc20_route',None);stall=getattr(carry,'reloc20_stall',None)
    if stall is not None:
        recovery=stall.recovery(now)
        if recovery is not None:drive=recovery;carry.path=None;carry.last_plan=-math.inf
    if route is not None:
        x,y,a=carry.loc.pose;f,l,w=drive
        end=(x+.1*(math.cos(a)*f-math.sin(a)*l),y+.1*(math.sin(a)*f+math.cos(a)*l))
        ok,context=route.segment((x,y),end,carry.obstacles.discs(now))
        if not ok:
            route.reject(dict(context,reason='issued_motion_enclosure_overlap'),now=now)
            carry.rejection_context=context;carry.path=None;carry.last_plan=-math.inf
            return (0.,0.,0.)
    return drive
