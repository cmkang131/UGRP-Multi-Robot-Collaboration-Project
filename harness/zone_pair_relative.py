"""Own-wrist beam shape report, extending v5's segment-local resting track.

Uses the unchanged beam body colour to select silhouette/paired edges. Dark
grip bands are neither detected nor assigned a position. Complete catalogue
length and both end boundaries are required to establish endpoint identity.
An interior colour boundary alone never identifies an end. Partial views only
support the propagated track. Complementary stationary views may jointly show
the complete catalogue shape. Loaded images never use this plane.
"""
from __future__ import annotations

from dataclasses import asdict, dataclass, replace
import math
import cv2
import numpy as np

from harness import owncam_pair_beam as beam_v1
from harness.owncam_pair_beam_v2 import beam_colour_mask
from harness.owncam_view import base_rays
from harness.zone_pair_beam_track import RestingBeamTrack, MAX_AGE_S

PROFILE = 'beam_relative_shape_v6'
MULTIVIEW_KEEP_S = 4.       # stationary complementary views retained for fusion
CLOSE_IN_MAX_BOUND_M = .10  # identified shape whose range-driven bound exceeds the 5 cm gate


@dataclass(frozen=True)
class BeamRelativeReport:
    frame_id: int
    sha256: str
    captured_at_s: float
    segment: int
    camera_pwm: tuple
    mode: str = 'resting_hypothesis'
    grip_base_m: tuple | None = None
    axis_heading_rad: float | None = None
    std_xy_m: float | None = None
    std_yaw_rad: float | None = None
    bias_bound_m: float | None = None
    observable_axes: tuple = ()
    reasons: tuple = ()
    endpoint_hypotheses: tuple = ('near', 'far')
    anchor_time_s: float | None = None
    anchor_sha256: str | None = None
    identity_time_s: float | None = None
    view_sha256: tuple = ()
    calibrated: bool = False
    marker_dependency: bool = False

    def ready(self, now):
        return (self.mode == 'resting_hypothesis' and self.grip_base_m is not None
                and self.observable_axes == ('forward', 'left', 'yaw')
                and self.endpoint_hypotheses == ('nearest_end',)
                and self.anchor_time_s is not None and 0 <= now-self.anchor_time_s <= MAX_AGE_S
                and (self.identity_time_s is None or 0 <= now-self.identity_time_s <= MAX_AGE_S)
                and 0 <= now-self.captured_at_s <= .3 + 1e-4
                and all(v is not None and math.isfinite(v) for v in
                        (*self.grip_base_m, self.axis_heading_rad, self.std_xy_m,
                         self.std_yaw_rad, self.bias_bound_m))
                and 0 <= self.std_xy_m + self.bias_bound_m <= .05
                and 0 <= self.std_yaw_rad <= math.radians(3))

    def closing_ready(self, now):
        """Fresh complete shape; every ready() check holds except the 5 cm bound.

        Monocular depth bias grows with range, so an identified far beam is
        approached (never aligned or closed on) until the unchanged gate passes.
        """
        if self.grip_base_m is None or self.ready(now) or self.anchor_time_s != self.captured_at_s:
            return False
        if not all(v is not None and math.isfinite(v) for v in (self.std_xy_m, self.bias_bound_m)):
            return False
        probe = replace(self, bias_bound_m=max(0., .05-self.std_xy_m))
        return probe.ready(now) and self.std_xy_m+self.bias_bound_m <= CLOSE_IN_MAX_BOUND_M

    def closing_command(self, forward_range_m=None):
        """Forward-only step; worst-case travel keeps the true grip beyond standoff.

        forward_range_m is a reserved slot for the own ultrasonic range (separate
        PR claude/ultrasonic-range). It is ignored: no decision depends on it yet.
        """
        from harness.owncam_pair_beam import GRASP_RADIUS_M, MIN_COMMAND
        from harness.zone_own_guards import BACKOFF_GAIN_MAX
        room = self.grip_base_m[0]-(self.std_xy_m+self.bias_bound_m)-GRASP_RADIUS_M
        duration = .3
        speed = min(.08, room/BACKOFF_GAIN_MAX/duration)
        if speed < MIN_COMMAND:
            return None
        return {'kind': 'mecanum', 'forward': float(speed), 'left': 0., 'turn': 0., 'duration': duration}

    def beam(self):
        if self.grip_base_m is None:
            return None
        return {'visible': True, 'end_visible': True, 'grip_base_m': list(self.grip_base_m),
                'axis_heading_rad': self.axis_heading_rad,
                'std_xy_m': self.std_xy_m + self.bias_bound_m,
                'std_yaw_rad': self.std_yaw_rad, 'grip_source': 'shape_end_plus_catalogue_inset'}

    def as_dict(self):
        return asdict(self)


def shape_points(image, servo):
    frame = beam_v1.decode(image)
    origin, rays, xs, ys, valid = base_rays(servo, beam_v1.RAY_STEP)
    hit = valid & beam_colour_mask(frame)[ys.astype(int), xs.astype(int)] & (rays[:,2] < -1e-6)
    selected = rays[hit]
    distance = (beam_v1.BEAM_TOP_Z_M-origin[2]) / selected[:,2]
    pts = (origin + distance[:,None]*selected)[:,:2]
    keep = (distance > 0) & (np.linalg.norm(pts, axis=1) < 2.5)
    # A 16 mm top/side/height ambiguity projected through the actual rays.
    depth = np.linalg.norm(selected[keep,:2]/selected[keep,2,None], axis=1)*.016
    return pts[keep], xs[hit][keep].astype(int), ys[hit][keep].astype(int), depth


def camera_xy(servo):
    from harness.visual_arm import camera_extrinsics
    return np.asarray(camera_extrinsics(servo)[0], float)[:2]


def _prior_inside(pts, prior):
    u = np.array([math.cos(prior['axis_heading_rad']), math.sin(prior['axis_heading_rad'])])
    delta = pts-np.asarray(prior['grip_base_m'])
    a, b = delta@u, delta@np.array([-u[1],u[0]])
    pad = 2*(prior['std_xy_m']+prior['bias_bound_m']+.6*prior['std_yaw_rad'])
    return (a >= -.03-pad) & (a <= .57+pad) & (abs(b) <= .02+pad)


def associate_component(pts, depth, comp, labels, big, prior=None):
    """Choose the beam's own foreground component; separate far/other objects.

    Review 3: a peer robot's yellow parts are a second colour component in real
    renders. It may be ignored only when (1) the prior track (or, without one,
    size) selects the beam component, (2) floor pixels separate it in the image,
    so it cannot be hiding any silhouette boundary, and (3) it cannot belong to
    one catalogue beam with the chosen component (joint axial extent > .66 m
    plus the near-face ambiguity, or laterally outside the beam corridor).
    Otherwise it is an occluder candidate and identity stays unknown.
    """
    ids = [i for i, _ in big]
    if prior is not None:
        inside = {i: float(_prior_inside(pts[comp == i], prior).mean()) for i in ids}
        chosen = [i for i in ids if inside[i] >= .95]
        if len(chosen) != 1:
            return None, ('DISCONNECTED_SHAPE_OR_OCCLUSION', 'PRIOR_ASSOCIATION_AMBIGUOUS')
        keep = chosen[0]
    else:
        keep = max(big, key=lambda row: row[1])[0]
    main = pts[comp == keep]
    centre = np.median(main, axis=0)
    _, vectors = np.linalg.eigh(np.cov((main-centre).T))
    u = vectors[:,-1]
    n = np.array([-u[1],u[0]])
    lo, hi = np.percentile((main-centre)@u, [1,99])
    slack = 2*float(np.max(depth[comp == keep]))
    near = cv2.dilate((labels == keep).astype(np.uint8), np.ones((7,7),np.uint8)) > 0
    for other in ids:
        if other == keep:
            continue
        o = pts[comp == other]
        if np.any(near[labels == other]):
            return None, ('DISCONNECTED_SHAPE_OR_OCCLUSION', 'ADJACENT_OCCLUDER_CANDIDATE')
        a, b = (o-centre)@u, (o-centre)@n
        joint = max(hi, float(np.max(a)))-min(lo, float(np.min(a)))
        lateral = float(np.min(np.abs(b-np.median((main-centre)@n))))
        if joint <= .66+slack and lateral <= .10:
            return None, ('DISCONNECTED_SHAPE_OR_OCCLUSION',)
    return keep, ('SEPARATE_COMPONENT_EXCLUDED',)


def component_points(image, servo, prior=None):
    """Beam-colour points of the associated foreground component only."""
    pts, x, y, depth = shape_points(image, servo)
    if len(pts) < beam_v1.MIN_POINTS:
        return (pts, x, y, depth), ()
    # Use foreground connectivity, not colour alone: an intact dark stripe
    # may belong to the same silhouette, while a floor gap separates two
    # objects. If the stripe blends into the floor, identity is ambiguous.
    from harness import zone_own_perception as perception
    frame = beam_v1.decode(image)
    origin, axes, k, d, size = perception._optics(frame,servo)
    model, rows = perception._floor_row_model(frame,origin,axes,k,d,size)
    foreground = ((np.max(np.abs(frame.astype(float)-model),axis=2) > perception.BLOCK_LIKE_DIST)
                  & rows[:,None])
    _, labels = cv2.connectedComponents(foreground.astype(np.uint8))
    comp = labels[y,x]
    ids, counts = np.unique(comp,return_counts=True)
    big = [(int(i),int(c)) for i,c in zip(ids,counts) if i != 0 and c >= beam_v1.MIN_POINTS]
    if len(big) <= 1:
        return (pts, x, y, depth), ()
    keep, why = associate_component(pts, depth, comp, labels, big, prior)
    if keep is None:
        return None, why
    sel = (comp == keep) | (comp == 0)
    return (pts[sel], x[sel], y[sel], depth[sel]), why


def shape_fit(image, servo, prior=None):
    got, extra = component_points(image, servo, prior)
    if got is None:
        return None, extra
    pts, x, y, depth = got
    inner = beam_v1._inner_valid()[y,x]
    fitted, reasons = fit_shape_points(pts, depth, inner, camera_xy(servo))
    return fitted, (*reasons, *extra)


def fit_shape_points(pts, depth, inner, origin_xy=None):
    """Top-plane silhouette fit with the near end-face ambiguity.

    The near silhouette boundary is the end face somewhere between its top
    edge (z=.032) and floor edge (z=0). Its projection onto the top plane lies
    up to 2*depth (depth = 16 mm half height through that ray) toward the
    camera. The near end is placed at the mid-height hypothesis with the
    unchanged depth bias bound, and the catalogue length gate is applied to
    the interval of lengths consistent with that face. The far end face is not
    visible from the near side, so the far boundary is the top edge.
    """
    if len(pts) < beam_v1.MIN_POINTS:
        return None, ('BEAM_NOT_VISIBLE',)
    centre = np.median(pts, axis=0)
    _, vectors = np.linalg.eigh(np.cov((pts-centre).T))
    u = vectors[:,-1]
    if u @ centre < 0:
        u = -u
    n = np.array([-u[1],u[0]])
    a, b = pts @ u, pts @ n
    lo, hi = np.percentile(a, [1,99])
    width = float(np.percentile(b,98)-np.percentile(b,2))
    near_boundary, far_boundary = a <= lo+.01, a >= hi-.01
    near_clipped = bool(np.any(~inner[near_boundary]))
    far_clipped = bool(np.any(~inner[far_boundary]))
    partial = near_clipped or far_clipped or hi-lo < .54
    # Incomplete catalogue support cannot identify a new end.
    if partial:
        # Colour breaks/occlusions are not new ends. The historical label
        # BAND_CLIPPED is handled as the same unobserved-axis case downstream.
        return None, ('END_CLIPPED', 'AXIAL_POSITION_UNKNOWN', 'END_ID_AMBIGUOUS')
    near_depth = float(np.percentile(depth[near_boundary],95))
    near_top = lo*u
    if origin_xy is None:
        ray = u
    else:
        ray = near_top-np.asarray(origin_xy,float)[:2]
        ray = ray/max(float(np.linalg.norm(ray)),1e-9)
    face = 2*near_depth*max(0.,float(ray@u))  # axial extent of the visible end face
    if not (hi-lo-face <= .66 and hi-lo >= .54 and .025 <= width <= .070):
        return None, ('SHAPE_AMBIGUOUS', 'MONOCULAR_DEPTH_AMBIGUOUS')
    strips = []
    for start in np.arange(lo, hi, .01):
        v = b[(a >= start) & (a < start+.01)]
        if len(v) < 4:
            continue
        left, right = np.percentile(v,[2,98])
        if .025 <= right-left <= .055:
            strips.append((start+.005,(left+right)/2))
    if len(strips) < 4 or np.ptp(np.asarray(strips)[:,0]) < .06:
        return None, ('PAIRED_EDGES_UNOBSERVABLE',)
    along, across = np.asarray(strips).T
    if len(along)*.01 < .55*(hi-lo-face) or np.max(np.diff(along))>.08:
        return None, ('DISCONNECTED_SHAPE_OR_OCCLUSION',)
    slope, intercept = np.polyfit(along, across, 1)
    residual = float(np.max(np.abs(across-slope*along-intercept)))
    heading = math.atan2(u[1],u[0])+math.atan(slope)
    # Mid-height end-face hypothesis; the +/- near_depth bias covers top..floor.
    near = lo*u+(slope*lo+intercept)*n+near_depth*ray
    far = hi*u+(slope*hi+intercept)*n
    bias = near_depth+.005  # bound at the observed grip end
    if abs(np.linalg.norm(far)-np.linalg.norm(near)) <= 2*(bias+.015):
        return None, ('END_ID_AMBIGUOUS',)
    syaw = max(math.radians(1), math.atan2(2*residual+.001,float(np.ptp(along))))
    grip = near + .03*np.array([math.cos(heading),math.sin(heading)])
    reasons = ('MONOCULAR_RESTING_PLANE_HYPOTHESIS',)
    return {'grip_base_m': grip.tolist(), 'axis_heading_rad': heading,
            'std_xy_m': max(.015,residual), 'std_yaw_rad': syaw,
            'bias_bound_m': bias, 'visible_length_m': float(hi-lo),
            'near_face_extent_m': face, 'edge_residual_m': residual}, reasons


class RelativeBeamTrack(RestingBeamTrack):
    """Reuse issued-command propagation; separate relative state from world PF."""
    def __init__(self):
        super().__init__()
        self.last_report = None
        self.last_capture = -math.inf
        self.command_epoch = 0
        self.report_command_epoch = None
        self.views = {}

    def command(self, row, servo):
        super().command(row,servo)
        if row['kind'] in ('drive','mecanum'):
            self.views.clear()  # no image stitching across base commands
        if row['kind'] in ('drive','mecanum','look') or (row['kind']=='arm' and int(row['servo_id'])!=1):
            self.command_epoch += 1

    def observe(self, obs, servo, segment, *, now, mode='resting_hypothesis'):
        self.advance(now)
        pwm = tuple(sorted((int(k),int(v)) for k,v in servo.items() if int(k) in (3,4,5,6)))
        common = dict(frame_id=obs['frame_id'],sha256=obs['sha256'],captured_at_s=obs['sim_time'],
                      segment=segment,camera_pwm=pwm,mode=mode)
        def unknown(*reasons):
            self.last_report = BeamRelativeReport(**common,reasons=tuple(reasons))
            return self.last_report
        image_pwm = obs.get('actuator_state',{}).get('servo_pulses',{})
        try:
            observed = tuple(sorted((int(k),int(v)) for k,v in image_pwm.items() if int(k) in (3,4,5,6)))
        except (TypeError,ValueError):
            return unknown('CAMERA_COMMAND_MISMATCH')
        if observed != pwm or not 0 <= now-obs['sim_time'] <= .3+1e-4:
            return unknown('STALE_OR_CAMERA_MISMATCH')
        if mode != 'resting_hypothesis':
            self.beam = None
            self.views.clear()
            return unknown('LOADED_DEPTH_UNKNOWN')
        key = (segment,obs['frame_id'],obs['sha256'])
        if key == self.last_frame:
            if self.report_command_epoch == self.command_epoch:
                return self.last_report  # idempotent read, not a new measurement
            return unknown('IMAGE_PRECEDES_ISSUED_COMMAND')
        if self.last_report and self.last_report.sha256 == obs['sha256']:
            return unknown('DUPLICATE_IMAGE')
        if obs['sim_time'] <= self.last_capture:
            return unknown('OUT_OF_ORDER')
        self.last_frame, self.last_capture = key, obs['sim_time']
        self.report_command_epoch = self.command_epoch
        old = self.beam if self.segment == segment else None
        fitted, reasons = shape_fit(obs['image'],servo,old)
        if old is None:
            self.views.clear()
        identity_t = None if old is None else old.get('identity_time_s',old['anchor_time_s'])
        if fitted is not None:
            if old is not None:
                delta = math.dist(fitted['grip_base_m'],old['grip_base_m'])
                angle = abs(float((fitted['axis_heading_rad']-old['axis_heading_rad']+math.pi)%(2*math.pi)-math.pi))
                if (delta > 2*(old['std_xy_m']+fitted['std_xy_m']+old['bias_bound_m']+fitted['bias_bound_m'])
                        or angle > 2*(old['std_yaw_rad']+fitted['std_yaw_rad'])):
                    self.beam = None
                    return unknown('BEAM_MOVED_OR_ASSOCIATION_LOST')
            self.segment = segment
            self.beam = {**fitted,'anchor_time_s':obs['sim_time'],'anchor_sha256':obs['sha256'],
                         'identity_time_s':obs['sim_time']}
            self.views.clear()
        elif (old is not None and any(r in reasons for r in ('END_CLIPPED','BAND_CLIPPED'))
              and 0 <= now-identity_t <= MAX_AGE_S):
            got, why = component_points(obs['image'],servo,old)
            if got is None:
                # An adjacent occluder candidate or ambiguous association:
                # no support, no update; the propagated bound keeps growing.
                return unknown(*reasons,*why)
            pts,x,y,depth = got
            u = np.array([math.cos(old['axis_heading_rad']),math.sin(old['axis_heading_rad'])])
            delta = pts-np.asarray(old['grip_base_m'])
            a, b = delta@u,delta@np.array([-u[1],u[0]])
            pad = 2*(old['std_xy_m']+old['bias_bound_m']+.6*old['std_yaw_rad'])
            inside = (a>=-.03-pad)&(a<=.57+pad)&(abs(b)<=.02+pad)
            if not len(inside) or inside.mean()<.95:
                self.beam = None
                self.views.clear()
                return unknown('PARTIAL_INCONSISTENT_OR_BEAM_MOVED')
            reasons = (*reasons,'PARTIAL_SUPPORT_ONLY','MONOCULAR_RESTING_PLANE_HYPOTHESIS')
            # Unknown boundaries do not update any axis or shrink its bound.
            # Retain distinct camera views only while base motion has ended.
            if x is not None and now >= self.until:
                inner = beam_v1._inner_valid()[y,x]
                self.views[pwm] = (now,pts,depth,inner,obs['sha256'],camera_xy(servo))
                self.views = {k:v for k,v in self.views.items() if now-v[0] <= MULTIVIEW_KEEP_S}
                if len(self.views) >= 2:
                    # Use only interior pixels; a clipped edge cannot vote as
                    # an end. Both extremes must be supplied by complete views
                    # of those ends, jointly spanning the catalogue length.
                    clouds = [v for v in self.views.values()]
                    points = np.concatenate([v[1][v[3]] for v in clouds])
                    depths = np.concatenate([v[2][v[3]] for v in clouds])
                    # Uniform metric support prevents the near view's pixel
                    # density from hiding the far end in pooled percentiles.
                    _, indices = np.unique(np.floor(points/.003),axis=0,return_index=True)
                    origin = np.mean([v[5] for v in clouds],axis=0)
                    merged, why = fit_shape_points(points[indices],depths[indices],np.ones(len(indices),bool),origin)
                    if merged is not None:
                        # The full-shape gate already reserves projection bias;
                        # missing catalogue extent is additional axial ambiguity.
                        # Same robust 1-99 % extent as the fit (review 3), not ptp:
                        # a complete bar on the uniform 3 mm grid spans .98 of .60 m.
                        merged['bias_bound_m'] += max(0., .98*.60-merged['visible_length_m'])
                        merged['bias_bound_m'] += .0005*(now-min(v[0] for v in clouds))
                        angle = abs((merged['axis_heading_rad']-old['axis_heading_rad']+math.pi)%(2*math.pi)-math.pi)
                        associated = (math.dist(merged['grip_base_m'],old['grip_base_m']) <= 2*(
                            old['std_xy_m']+old['bias_bound_m']+merged['std_xy_m']+merged['bias_bound_m'])
                            and angle <= 2*(old['std_yaw_rad']+merged['std_yaw_rad']))
                        if associated and merged['std_xy_m']+merged['bias_bound_m'] <= .05:
                            self.beam = {**merged,'anchor_time_s':now,'anchor_sha256':obs['sha256'],
                                         'identity_time_s':identity_t,
                                         'view_sha256':[v[4] for v in clouds]}
                            reasons = ('STATIONARY_MULTIVIEW_COMPLETE_SHAPE', *why)
        else:
            return unknown(*reasons)
        b = self.beam
        self.last_report = BeamRelativeReport(**common,grip_base_m=tuple(b['grip_base_m']),
            axis_heading_rad=b['axis_heading_rad'],std_xy_m=b['std_xy_m'],std_yaw_rad=b['std_yaw_rad'],
            bias_bound_m=b['bias_bound_m'],observable_axes=('forward','left','yaw'),reasons=reasons,
            endpoint_hypotheses=('nearest_end',),anchor_time_s=b['anchor_time_s'],anchor_sha256=b['anchor_sha256'],
            identity_time_s=b.get('identity_time_s',b['anchor_time_s']),view_sha256=tuple(b.get('view_sha256',())))
        return self.last_report
