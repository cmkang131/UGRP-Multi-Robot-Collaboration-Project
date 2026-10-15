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


def floor_patch(bgr, pwm, zone, half_extents, *, excluded=None):
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


class DestinationAcquire:
    def __init__(self, carry):
        self.carry=carry; self.started=None; self.acquired=None; self.confirmed=None
        self.mode='inactive'; self.last={}; self.events=[]; self.turn=0.; self.scan_start=0.
        self.points=[]; self.point=None; self.path=None; self.failure=None; self.valid_since=None
        self.views=0; self.last_fix_count=0; self.relocalizations=0; self.reloc_anchor=None
        self.reloc_t=None; self.reloc_scan=False; self.reloc_done=False

    def event(self,now,event,**kw):
        self.events.append(dict(t=now,event=event,**kw))

    def issue(self,delta):
        self.turn += float(delta[2])

    def start(self,now):
        c=self.carry; self.started=now; self.mode='scan_align'; self.scan_start=self.turn
        bearing=math.atan2(c.region['center_m'][1]-c.loc.pose[1],c.region['center_m'][0]-c.loc.pose[0])
        self.scan_target=self.turn+math.atan2(math.sin(bearing-c.loc.pose[2]),math.cos(bearing-c.loc.pose[2]))
        self.points=ellipse_candidates(c.loc.pose,c.loc.own.P,c.region['half_extents_m'])
        self.last_fix_count=c.loc.fixes
        self.event(now,'destination_acquire_start',ellipse_candidates=len(self.points),
            covariance=c.loc.own.P.tolist(),expected_bearing_rad=math.atan2(c.region['center_m'][1]-c.loc.pose[1],c.region['center_m'][0]-c.loc.pose[0]))

    def relocalize_step(self,now):
        """Held body sweep at a route view before destination arrival.

        Trigger:95% XY contour exceeds the smaller destination half width.
        Try once per translated footprint width; retain actual posterior and
        fall back to the existing setdown recovery if its hard budget fails.
        No covariance reset, accepted fix, or progress is fabricated.
        """
        c=self.carry
        if c.started is None or c.goal is None:return None
        radius=math.sqrt(CHI2_XY_95*float(np.linalg.eigvalsh(c.loc.own.P[:2,:2]).max()))
        width=min(c.region['half_extents_m'])
        if not self.reloc_scan:
            if radius <= width:return None
            if self.reloc_anchor is not None and math.dist(c.loc.pose[:2],self.reloc_anchor) < 2*width:return None
            self.reloc_scan=True; self.reloc_anchor=c.loc.pose[:2]; self.scan_start=self.turn
            self.reloc_t=now; self.last_fix_count=c.loc.fixes; self.relocalizations+=1
            self.event(now,'held_relocalization_start',radius95_m=radius,zone_half_width_m=width)
        # Same existing .1rad/s loaded chassis turn limit. Full scan =2pi radians.
        if abs(self.turn-self.scan_start) < 2*math.pi:
            return (0.,0.,.1)
        self.reloc_scan=False; self.reloc_done=True
        self.event(now,'held_relocalization_end',sim_s=now-self.reloc_t,
                   new_fixes=c.loc.fixes-self.last_fix_count,posterior=c.loc.own.P.tolist())
        return (0.,0.,0.)

    def step(self,now,bgr,pwm,low,kind):
        from sim.solo_carry_obstacles import held_mask
        from sim.grasp_act_visible_route import segment_free, waypoint
        from harness.reloc12_ledger import route_context
        c=self.carry
        if self.started is None:self.start(now)
        centre, rec=floor_patch(bgr,pwm,c.zone,c.region['half_extents_m'],
            excluded=held_mask(kind,{1:1500,**low},pwm,(bgr.shape[1],bgr.shape[0])))
        self.views+=1; self.last=dict(t=now,**rec)
        # Unchanged existing full-footprint RGB/FK gate and .3s stable evidence.
        if c.place_visible(bgr,pwm,low,kind):
            self.valid_since=now if self.valid_since is None else self.valid_since
            if now-self.valid_since >= .3-1e-8:
                self.confirmed=now; self.mode='confirmed'; self.event(now,'destination_confirmed')
                return (0.,0.,0.),True,None
            return (0.,0.,0.),False,None
        self.valid_since=None
        if centre is not None:
            if self.acquired is None:
                self.acquired=now; self.event(now,'destination_colour_acquired',sim_s=now-self.started)
            self.mode='servo'
            target=centre-np.array([c.grip_xy[0]+c.advance_m,c.grip_xy[1]])
            # Body-relative patch error, independent of global-pose XY/yaw.
            f=max(-.05,min(.08,.9*float(target[0]))); l=max(-.06,min(.06,.9*float(target[1])))
            drive=(f,l,0.)
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
                if self.point is None:
                    self.failure='destination_visual_search_exhausted'; self.mode='failed'
                    self.event(now,'rejection',category='visual_acquisition',reason=self.failure,
                        blocked_object='zone_'+c.zone,minimum_gap_m=None,gap_scope='not_applicable_no_visual_evidence')
                    return (0.,0.,0.),False,self.failure
                self.event(now,'ellipse_search_waypoint',xy=list(self.point))
            self.mode='expand'
            if math.dist(c.loc.pose[:2],self.point) <= .025: # inherited map arrival tolerance
                self.point=None;self.mode='scan';self.scan_start=self.turn;drive=(0.,0.,.1)
            else:
                target=waypoint(c.loc.pose[:2],self.path,c.obstacles.discs(now),c.rects,c.radius)
                drive=c.heading_drive(c.loc.pose,target,c.loc.pose[2]) if target is not None else (0.,0.,0.)
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
            drive=(0.,0.,.1) if segment_free((x,y),(x,y),c.obstacles.discs(now),c.rects,c.radius) else (0.,0.,0.)
        return drive,False,None

    def record(self):
        return dict(toggle=OPTION,mode=self.mode,started_t=self.started,acquired_t=self.acquired,
            confirmed_t=self.confirmed,acquisition_sim_s=None if self.acquired is None else self.acquired-self.started,
            views=self.views,last=self.last,events=self.events,relocalizations=self.relocalizations,
            failure=self.failure,truth_inputs=0,held_world_reads=0)
