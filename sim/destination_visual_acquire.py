"""Default-off map-navigation recovery using own RGB and issued commands only.

Sources and every inherited bound: experiments/2026-10-16-reloc19/references.md.
No world/robot/score object is accepted. Ground range is nominal camera FK,
not measured depth. A painted patch is a homing feature, never a place verdict.
"""
from __future__ import annotations
import math
import cv2
import numpy as np
from sim.grasp_act_solo_lookback import transforms, _pixel_rays
from harness.zone_own_perception import PAINT_HUE, _usable_region, SLOT_MAX_RANGE_M

OPTION = 'destination_visual_acquire_v1'
CHI2_XY_95 = 5.991464547107979  # chi-square, 2 DOF, 95% contour (not calibrated coverage).


def floor_patch(bgr, pwm, zone, half_extents, *, excluded=None, clear=None):
    """Largest destination-colour ground hypothesis, excluding held pixels.

    Hue/S/V are the unchanged CarryToZone.place_visible limits. Minimum600
    is its inherited geometry pixel minimum. Range1.2m is own-perception's
    supported floor fit, not new camera reach. Extent uses authored zone size
    plus the existing RGBObstacleMemory range-error envelope .06+.08*range.
    """
    if bgr is None:
        return None, dict(reason='own_rgb_missing', pixels=0)
    h, w = bgr.shape[:2]
    hsv = cv2.cvtColor(bgr, cv2.COLOR_BGR2HSV)
    lo, hi = PAINT_HUE[zone]
    mask = ((hsv[...,0] >= lo-5) & (hsv[...,0] <= hi+5)
            & (hsv[...,1] >= 30) & (hsv[...,2] >= 30) & _usable_region(w,h))
    if clear is not None:
        mask &= clear
    if excluded is not None:
        mask &= ~excluded
    n, labels, stats, _ = cv2.connectedComponentsWithStats(mask.astype(np.uint8), 8)
    if n <= 1:
        return None, dict(reason='destination_colour_absent', pixels=0)
    i = 1+int(np.argmax(stats[1:,cv2.CC_STAT_AREA])); count=int(stats[i,cv2.CC_STAT_AREA])
    if count < 600:
        return None, dict(reason='destination_component_small', pixels=count)
    _, cam = transforms(pwm)
    rays = (_pixel_rays(w,h) @ cam[:3,:3].T).reshape(h,w,3)
    rr = rays[labels == i]
    valid = rr[:,2] < -1e-4  # same floor-ray numerical horizon as obstacle memory
    rr = rr[valid]
    if not len(rr):
        return None, dict(reason='destination_not_ground_ray', pixels=count)
    xyz = cam[:3,3] + (-cam[2,3]/rr[:,2,None])*rr
    xy = xyz[:,:2]; distance=np.linalg.norm(xy,axis=1)
    xy = xy[distance <= SLOT_MAX_RANGE_M]
    if len(xy) < 600:
        return None, dict(reason='destination_outside_floor_fit', pixels=count, ground_pixels=len(xy))
    extent=float(np.linalg.norm(np.ptp(xy,axis=0)))
    limit=2*float(np.linalg.norm(half_extents))+2*(.06+.08*SLOT_MAX_RANGE_M)
    if extent > limit:
        return None, dict(reason='destination_extent_not_zone', pixels=count, extent_m=extent, limit_m=limit)
    # Visible-patch centre; do not call a truncated patch the authored zone centre.
    centre=np.median(xy,axis=0)
    return centre, dict(reason='painted_ground_hypothesis', pixels=count, ground_pixels=len(xy),
        patch_xy=centre.tolist(), extent_m=extent, source='own_rgb_nominal_ground_projection')


def ellipse_candidates(pose, covariance, half_extents):
    """Finite two-dimensional95% covariance lattice, near rings first.

    Spacing is the destination's smaller full width: a sweep of that footprint
    covers adjacent lattice cells. Lattice bound derives from covariance only.
    The returned count is finite; no wall-clock search budget is involved.
    """
    C=np.asarray(covariance,float)[:2,:2]
    if not np.isfinite(C).all() or np.min(np.linalg.eigvalsh(C)) < 0:
        raise ValueError('finite positive semidefinite covariance required')
    vals,axes=np.linalg.eigh(C); radii=np.sqrt(CHI2_XY_95*np.maximum(vals,0))
    step=2*min(half_extents)
    if step <= 0: raise ValueError('positive region footprint required')
    limits=np.ceil(radii/step).astype(int)
    out=[]
    for i in range(-limits[0],limits[0]+1):
        for j in range(-limits[1],limits[1]+1):
            q=np.array([i,j])*step
            if not np.any(q):continue
            if np.sum((q/np.maximum(radii,np.finfo(float).eps))**2) <= 1:
                p=np.asarray(pose[:2])+axes@q
                out.append((float(np.linalg.norm(q)),float(p[0]),float(p[1])))
    return [(x,y) for _,x,y in sorted(out)]


def information_views(static,pose,P,pwm):
    """Existing static-landmark/Fisher view planner, actual issued loaded camera.

    Reuse15degree sampling, K=3 and MIN_GAIN from setdown_lookaround_v1;
    predicted visibility never counts as an observed landmark or accepted fix.
    """
    from sim.lookaround_localization import map_landmarks, wall_rects, _segment_hits_rect
    from sim.active_lookaround import plan_views, PANS_DEG, BODY_YAWS_DEG
    from sim.grasp_act_solo_lookback import project
    landmarks=map_landmarks(static);rects=wall_rects(static)
    yaws=[0.]+sorted({float(((p+y+180)%360)-180) for p in PANS_DEG for y in BODY_YAWS_DEG}-{0.})
    _,cam=transforms(pwm)
    def visible(x,yaw,pan,lm):
        a=x[2]+math.radians(yaw);c,ss=math.cos(a),math.sin(a)
        dx,dy=lm['xy'][0]-x[0],lm['xy'][1]-x[1]
        body=(c*dx+ss*dy,-ss*dx+c*dy,0.)
        if math.hypot(dx,dy)>lm['range']:return False
        cw=(x[0]+c*cam[0,3]-ss*cam[1,3],x[1]+ss*cam[0,3]+c*cam[1,3])
        lx,ly=lm['xy']
        if not lm.get('two_sided') and (cw[0]-lx)*lm['normal'][0]+(cw[1]-ly)*lm['normal'][1]<=0:return False
        uv,front=project([body],pwm)
        # Same12px field margin as the existing landmark visibility predictor.
        if not front[0] or not (12<=uv[0,0]<628 and 12<=uv[0,1]<468):return False
        L=math.dist(cw,(lx,ly))
        if L<=np.finfo(float).eps:return False
        end=(lx-.03*(lx-cw[0])/L,ly-.03*(ly-cw[1])/L)
        return not any(_segment_hits_rect(cw,end,r) for r in rects)
    plan=plan_views(pose,P,landmarks,visible,pans=(0.,),body_yaws=yaws)
    # plan_views prefers current yaw when informative, and uses body yaws otherwise.
    return plan


def bounded_translation(forward,left):
    """One common scale preserves a safe ray under the EXISTING speed bounds.

    Independent clipping rotates a diagonal command. R2 frozen replay210/210
    safe-waypoint prefixes were then rejected. No clearance/acceptance bound
    is changed; the existing segment_free veto still checks the result.
    """
    scale=min(1.,(.08 if forward>=0 else .05)/abs(forward) if forward else math.inf,
              .06/abs(left) if left else math.inf)
    return forward*scale,left*scale


def direction_drive(pose,target):
    x,y,a=pose;dx,dy=target[0]-x,target[1]-y
    f,l=bounded_translation(.9*(math.cos(a)*dx+math.sin(a)*dy),
                            .9*(-math.sin(a)*dx+math.cos(a)*dy))
    return (f,l,0.)


class DestinationAcquire:
    def __init__(self, carry, *, camera_pan=False, direction_preserve=False, search_replan=False):
        self.carry=carry; self.started=None; self.acquired=None; self.confirmed=None
        self.mode='inactive'; self.last={}; self.events=[]; self.turn=0.; self.scan_start=0.
        self.points=[]; self.point=None; self.path=None; self.failure=None; self.valid_since=None
        self.views=0; self.last_fix_count=0; self.relocalizations=0; self.reloc_anchor=None
        self.reloc_t=None; self.reloc_scan=False; self.reloc_done=False
        self.reloc_views=[];self.reloc_view=None;self.reloc_settle=None;self.reloc_counts=0
        self._floor_cache=None
        self.camera_pan=camera_pan;self.direction_preserve=direction_preserve;self.search_replan=search_replan;self.pan_origin=None;self.pan_targets=[]
        self.desired_pan=None;self.pan_ready=0.;self.memory_target=None;self.memory_t=None

    def event(self,now,event,**kw):
        self.events.append(dict(t=now,event=event,**kw))

    def floor_clear(self,bgr):
        """Reuse reloc16's frozen scene RGB wall exclusion, no new thresholds."""
        if self._floor_cache is None or self._floor_cache[0] is not bgr:
            from harness.reloc16_floor_mask import floor_clear
            clear,audit=floor_clear(bgr,np.ones(bgr.shape[:2],bool))
            self._floor_cache=(bgr,clear,audit)
        return self._floor_cache[1],self._floor_cache[2]

    def issue(self,delta):
        self.turn += float(delta[2])
        if self.memory_target is not None:
            dx,dy,da=delta;x,y=self.memory_target-np.array([dx,dy])
            self.memory_target=np.array([math.cos(da)*x+math.sin(da)*y,-math.sin(da)*x+math.cos(da)*y])

    def reset_pan(self):
        # Existing setdown pan endpoints500/2500, always restore issued origin.
        self.pan_targets=[self.pan_origin,500,2500,self.pan_origin]
        self.desired_pan=None;self.mode='pan_scan'

    def request_pan(self,target,now,pwm):
        self.desired_pan=int(target)
        # Existing2000pulse/s slew +.3s settle; no camera/FOV/model edit.
        self.pan_ready=now+abs(pwm[6]-target)/2000.+(.3 if pwm[6]!=target else 0.)

    def pan_settled(self,now,pwm):
        return pwm[6]==self.desired_pan and now>=self.pan_ready-1e-8

    def start(self,now,pwm=None):
        c=self.carry; self.started=now; self.mode='scan_align'; self.scan_start=self.turn
        bearing=math.atan2(c.region['center_m'][1]-c.loc.pose[1],c.region['center_m'][0]-c.loc.pose[0])
        self.scan_target=self.turn+math.atan2(math.sin(bearing-c.loc.pose[2]),math.cos(bearing-c.loc.pose[2]))
        self.points=ellipse_candidates(c.loc.pose,c.loc.own.P,c.region['half_extents_m'])
        self.last_fix_count=c.loc.fixes
        if self.camera_pan:
            self.pan_origin=int(pwm[6]);self.reset_pan()
        self.event(now,'destination_acquire_start',ellipse_candidates=len(self.points),
            covariance=c.loc.own.P.tolist(),expected_bearing_rad=math.atan2(c.region['center_m'][1]-c.loc.pose[1],c.region['center_m'][0]-c.loc.pose[0]))

    def relocalize_step(self,now,pwm=None):
        """Information-ranked held views, else existing setdown/lookaround.

        Trigger and spatial retry interval derive from the destination width.
        The same existing observer consumes real RGB; no posterior is invented.
        """
        c=self.carry
        if c.started is None or c.goal is None:return None
        radius=math.sqrt(CHI2_XY_95*float(np.linalg.eigvalsh(c.loc.own.P[:2,:2]).max()))
        width=min(c.region['half_extents_m'])
        if not self.reloc_scan:
            if radius <= width:return None
            if self.reloc_anchor is not None and math.dist(c.loc.pose[:2],self.reloc_anchor) < 2*width:return None
            self.reloc_anchor=c.loc.pose[:2];self.reloc_t=now;self.last_fix_count=c.loc.fixes
            self.relocalizations+=1;self.reloc_counts=0
            # Actual full-pose observer explicitly rejects loaded metric FK.
            # Its admission tag is allowed controller metadata, not plant truth.
            tracker=getattr(c.loc,'tracker',None)
            if tracker is not None and tracker.last.get('camera_admission')=='loaded_or_unknown_prediction_only':
                context=dict(blocked_object='issued_loaded_camera_metric_fk_unqualified',minimum_gap_m=None,
                    gap_scope='not_applicable_camera_calibration')
                self.event(now,'rejection',category='camera_qualification',reason='loaded_metric_fix_unavailable',**context)
                c.rejection_context=context;c.request_recovery(now,'reloc19_loaded_metric_camera_unqualified')
                return (0.,0.,0.)
            plan=information_views(c.static,c.loc.pose,c.loc.own.P,pwm) if pwm is not None else dict(views=[])
            self.event(now,'held_relocalization_start',radius95_m=radius,zone_half_width_m=width,plan=plan)
            views=plan.get('views',[])
            if not views:
                self.event(now,'rejection',category='view_observability',reason='loaded_camera_no_informative_view',
                    blocked_object='static_landmarks_outside_issued_camera_fov',minimum_gap_m=None,
                    gap_scope='not_applicable_expected_view_information',fallback='existing_setdown_lookaround_v1')
                c.request_recovery(now,'reloc19_unobservable_loaded_view')
                return (0.,0.,0.)
            # Angles are relative to the current command epoch, unaffected by
            # any subsequent global pose correction while executing the view.
            self.reloc_views=[self.turn+math.radians(v['body_yaw_deg']) for v in views]
            self.reloc_scan=True;self.reloc_view=None;self.reloc_settle=None
        if self.reloc_view is None and self.reloc_views:
            self.reloc_view=self.reloc_views.pop(0);self.reloc_settle=None
        if self.reloc_view is not None:
            error=self.reloc_view-self.turn
            if abs(error)>.04:  # unchanged carry arrival yaw tolerance
                return (0.,0.,max(-.1,min(.1,.6*error)))
            if self.reloc_settle is None:self.reloc_settle=now
            # Existing lookaround VIEW_SETTLE_S=.8; actual RGB observer runs10Hz.
            if now-self.reloc_settle<.8-1e-8:return (0.,0.,0.)
            self.reloc_counts+=1;self.reloc_view=None
            if self.reloc_views:return (0.,0.,0.)
        self.reloc_scan=False;self.reloc_done=True
        self.event(now,'held_relocalization_end',sim_s=now-self.reloc_t,actual_dwelled_views=self.reloc_counts,
                   new_fixes=c.loc.fixes-self.last_fix_count,posterior=c.loc.own.P.tolist())
        return (0.,0.,0.)

    def step(self,now,bgr,pwm,low,kind):
        from sim.solo_carry_obstacles import held_mask
        from sim.grasp_act_visible_route import segment_free, waypoint
        from harness.reloc12_ledger import route_context
        c=self.carry
        if self.started is None:self.start(now,pwm)
        if self.camera_pan and self.mode=='pan_scan':
            if self.desired_pan is None and self.pan_targets:
                self.request_pan(self.pan_targets.pop(0),now,pwm)
            if not self.pan_settled(now,pwm):return (0.,0.,0.),False,None
        elif self.camera_pan and self.mode=='pan_restore':
            if not self.pan_settled(now,pwm):return (0.,0.,0.),False,None
            self.mode='servo_memory'
        clear,wall_audit=self.floor_clear(bgr)
        centre, rec=floor_patch(bgr,pwm,c.zone,c.region['half_extents_m'],clear=clear,
            excluded=held_mask(kind,{1:1500,**low},pwm,(bgr.shape[1],bgr.shape[0])))
        self.views+=1; self.last=dict(t=now,scene_floor_mask=wall_audit,**rec)
        # Unchanged existing full-footprint RGB/FK gate and .3s stable evidence.
        self.last['place_gate']=bool((not self.camera_pan or pwm[6]==self.pan_origin) and c.place_visible(bgr,pwm,low,kind))
        if self.last['place_gate']:
            if self.acquired is None:
                self.acquired=now;self.event(now,'destination_colour_acquired',sim_s=now-self.started,source='unchanged_full_footprint_gate')
            self.valid_since=now if self.valid_since is None else self.valid_since
            if now-self.valid_since >= .3-1e-8:
                self.confirmed=now; self.mode='confirmed'; self.event(now,'destination_confirmed')
                return (0.,0.,0.),True,None
            return (0.,0.,0.),False,None
        self.valid_since=None
        if centre is not None:
            self.memory_target=centre.copy();self.memory_t=now
            if self.camera_pan and pwm[6]!=self.pan_origin:
                if self.acquired is None:
                    self.acquired=now;self.event(now,'destination_colour_acquired',sim_s=now-self.started)
                self.request_pan(self.pan_origin,now,pwm);self.mode='pan_restore'
                return (0.,0.,0.),False,None
            if self.acquired is None:
                self.acquired=now; self.event(now,'destination_colour_acquired',sim_s=now-self.started)
            self.mode='servo'
            target=centre-np.array([c.grip_xy[0]+c.advance_m,c.grip_xy[1]])
            # Body-relative patch error, independent of global-pose XY/yaw.
            f=max(-.05,min(.08,.9*float(target[0]))); l=max(-.06,min(.06,.9*float(target[1])))
            if self.direction_preserve:f,l=bounded_translation(.9*float(target[0]),.9*float(target[1]))
            drive=(f,l,0.)
        elif self.camera_pan and self.mode=='pan_scan':
            if self.pan_targets:
                self.request_pan(self.pan_targets.pop(0),now,pwm)
                return (0.,0.,0.),False,None
            self.mode='expand';self.desired_pan=self.pan_origin;drive=(0.,0.,0.)
        elif self.camera_pan and self.mode in ('servo','servo_memory'):
            from sim.grasp_act_solo_teacher import MEMORY_S
            if self.memory_target is not None and now-self.memory_t<=MEMORY_S:
                target=self.memory_target-np.array([c.grip_xy[0]+c.advance_m,c.grip_xy[1]])
                drive=(max(-.05,min(.08,.9*float(target[0]))),max(-.06,min(.06,.9*float(target[1]))),0.)
                if self.direction_preserve:drive=(*bounded_translation(.9*float(target[0]),.9*float(target[1])),0.)
                self.mode='servo_memory'
                self.last.update(reason='issued_history_visible_patch_memory',memory_age_s=now-self.memory_t)
            else:
                self.reset_pan();drive=(0.,0.,0.)
        elif self.mode=='servo':
            self.mode='scan'; self.scan_start=self.turn; drive=(0.,0.,.1)
        elif self.mode=='scan_align':
            error=self.scan_target-self.turn
            if abs(error) <= .04:  # inherited map arrival yaw tolerance
                self.mode='scan';self.scan_start=self.turn
            drive=(0.,0.,max(-.1,min(.1,.6*error)))
        elif self.mode=='scan' and abs(self.turn-self.scan_start) < 2*math.pi:
            drive=(0.,0.,.1)
        else:
            if self.point is None:
                while self.points:
                    p=self.points.pop(0)
                    path=c.plan_path(c.loc.pose[:2],p,c.static['bounds_m'],c.obstacles.discs(now),rects=c.rects,radius=c.radius)
                    if path:self.point=p;self.path=path;break
                    context=route_context(c.loc.pose[:2],p,c.obstacles.discs(now),c.rects,c.radius,
                        names=[o['id'] for o in c.static['obstacles']],bounds=c.static['bounds_m'])
                    self.event(now,'rejection',category='route',reason='ellipse_waypoint_no_path',**context)
                if self.point is None:
                    self.failure='destination_visual_search_exhausted'; self.mode='failed'
                    self.event(now,'rejection',category='visual_acquisition',reason=self.failure,
                        blocked_object='zone_'+c.zone,minimum_gap_m=None,gap_scope='not_applicable_no_visual_evidence')
                    return (0.,0.,0.),False,self.failure
                self.event(now,'ellipse_search_waypoint',xy=list(self.point))
            self.mode='expand'
            if math.dist(c.loc.pose[:2],self.point) <= .025: # inherited map arrival tolerance
                self.point=None
                if self.camera_pan:self.reset_pan();drive=(0.,0.,0.)
                else:self.mode='scan';self.scan_start=self.turn;drive=(0.,0.,.1)
            else:
                target=waypoint(c.loc.pose[:2],self.path,c.obstacles.discs(now),c.rects,c.radius)
                if self.search_replan:
                    from sim.grasp_act_visible_route import free
                    if target is None or not free(self.point,c.obstacles.discs(now),c.rects,c.radius):
                        # R3 frozen93266: RGB introduced an obstacle at the
                        # selected goal; its old path returned no waypoint.
                        # Retire this candidate, never erase the obstacle or
                        # relax clearance. The finite remaining list is tried
                        # afresh from the current allowed pose next tick.
                        context=route_context(c.loc.pose[:2],self.point,c.obstacles.discs(now),c.rects,c.radius,
                            names=[o['id'] for o in c.static['obstacles']],bounds=c.static['bounds_m'])
                        self.last.update(category='route',reason='destination_search_path_obstructed',**context)
                        self.event(now,'rejection',category='route',reason='destination_search_path_obstructed',**context)
                        self.point=None;self.path=None
                        return (0.,0.,0.),False,None
                drive=((direction_drive(c.loc.pose,target) if self.direction_preserve else c.heading_drive(c.loc.pose,target,c.loc.pose[2]))
                       if target is not None else (0.,0.,0.))
        if getattr(c,'reloc20_heading',False) and (drive[0] or drive[1]):
            from harness.reloc20_motion import heading_forward
            # Reorient toward the same body-relative servo/waypoint ray.
            # Camera pan carries its own issued FK and must return before place.
            drive=heading_forward((0.,0.,0.),drive[:2])
        if getattr(c,'reloc20_route',None) is not None or getattr(c,'reloc20_stall',None) is not None:
            from harness.reloc20_motion import guard
            drive=guard(c,drive,now)
        # Every translation retains static/RGB obstacle veto using a single tick
        # at current10Hz. A rejected candidate never gets silently executed.
        dt=.1; x,y,a=c.loc.pose
        goal=(x+math.cos(a)*drive[0]*dt-math.sin(a)*drive[1]*dt,
              y+math.sin(a)*drive[0]*dt+math.cos(a)*drive[1]*dt)
        if not segment_free((x,y),goal,c.obstacles.discs(now),c.rects,c.radius):
            context=route_context((x,y),goal,c.obstacles.discs(now),c.rects,c.radius,
                names=[o['id'] for o in c.static['obstacles']],bounds=c.static['bounds_m'])
            self.last.update(reason='destination_motion_blocked',**context)
            # Rotation is inside the same circular loaded envelope.
            drive=(0.,0.,.1) if not self.camera_pan and segment_free((x,y),(x,y),c.obstacles.discs(now),c.rects,c.radius) else (0.,0.,0.)
        return drive,False,None

    def record(self):
        return dict(toggle=OPTION,destination_search_replan_v1=self.search_replan,destination_direction_preserve_v1=self.direction_preserve,destination_camera_pan_v1=self.camera_pan,desired_pan=self.desired_pan,mode=self.mode,started_t=self.started,acquired_t=self.acquired,
            confirmed_t=self.confirmed,acquisition_sim_s=None if self.acquired is None else self.acquired-self.started,
            views=self.views,last=self.last,events=self.events,relocalizations=self.relocalizations,
            failure=self.failure,truth_inputs=0,held_world_reads=0)
