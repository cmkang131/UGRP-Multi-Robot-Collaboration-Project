"""Generate -> IK -> collision/visibility/connectors -> path-cost selection.

Pure command-space geometry. This predicts feasibility, not contact success.
Uses the authored v3 collision shapes; no World, measured joints or contacts.
"""
import math
from functools import lru_cache
import numpy as np
from harness import visual_arm as sdk
from harness.visual_arm_v3 import tool_pose
from sim.masterpi_geometry_v3 import PHYSICAL_V3, FINGER_PAD_LENGTH_M
from sim.masterpi_geometry import FINGER_HALF_WIDTH_M, FINGER_HALF_HEIGHT_M
from sim.zone_cargo import HANDLE_WIDTH_M, HANDLE_HEIGHT_M
from sim.grasp_act_teacher import grasp_poses, wrap, local
from sim.grasp_act_visible_route import constraints, free, segment_free
from scripts.zone_teacher import plan_path

# Physics uses +/-35mm jaw origins and 16mm commanded travel (dynamics_v2).
JAW_OPEN_M = .035
JAW_TRAVEL_M = .016
SWEEP_PAD_M = .004  # 5 PWM joint interpolation + 4mm capsule-axis samples


def jaw_geometry(offset, grip):
    """Opposed face contact must lie inside both finite pad projections.

    For a beam width w, the two side-face intersections along the tool axis
    shift +/- w*tan(offset)/2. The pitched pad's horizontal half extent is
    L/2*|cos(pitch)| + H/2*|sin(pitch)|. No wrist yaw is available to undo offset.
    """
    pitch = math.radians(tool_pose(grip).pitch_deg)
    longitudinal = FINGER_PAD_LENGTH_M/2*abs(math.cos(pitch)) + FINGER_HALF_HEIGHT_M*abs(math.sin(pitch))
    c = math.cos(offset)
    required_gap = HANDLE_WIDTH_M/max(c, 1e-12)
    shift = HANDLE_WIDTH_M/2*abs(math.tan(offset))
    open_gap = 2*(JAW_OPEN_M-FINGER_HALF_WIDTH_M)
    closed_gap = 2*(JAW_OPEN_M-JAW_TRAVEL_M-FINGER_HALF_WIDTH_M)
    allowed = c > 0 and shift <= longitudinal and closed_gap <= required_gap <= open_gap
    return {'allowed': allowed, 'opposed_contact_shift_m': shift, 'pad_projected_half_m': longitudinal,
            'required_gap_m': required_gap, 'open_gap_m': open_gap, 'closed_gap_m': closed_gap,
            'geometric_max_abs_offset_deg': min(math.degrees(math.atan(2*longitudinal/HANDLE_WIDTH_M)),
                math.degrees(math.acos(HANDLE_WIDTH_M/open_gap))),
            'pitch_deg': math.degrees(pitch), 'scope': 'geometric necessary condition, friction unverified'}


def capsules(pwm):
    """Conservative spheres sampled along authored arm/contact primitives."""
    g = PHYSICAL_V3
    nominal = lambda k: pwm[k]-sdk.SERVO_DEVIATION[k]
    sh = math.radians(90-(nominal(5)-1500)/sdk.PULSE_PER_DEGREE)
    el = sh-math.radians((nominal(4)-1500)/sdk.PULSE_PER_DEGREE)
    pitch = el+math.radians((nominal(3)-1500)/sdk.PULSE_PER_DEGREE)
    yaw = math.radians((pwm[6]-1500)/sdk.PULSE_PER_DEGREE)
    axis = lambda angle: np.array([math.cos(angle)*math.cos(yaw), math.cos(angle)*math.sin(yaw), math.sin(angle)])
    shoulder = np.array([g.yaw_axis_x_m, 0., g.shoulder_axis_z_floor_m])
    elbow = shoulder+g.upper_arm_m*axis(sh)
    wrist = elbow+g.forearm_m*axis(el)
    tool = axis(pitch)
    shapes = [(shoulder, elbow, .011, False), (elbow, wrist, .010, False),
              (wrist, wrist+.055*tool, .009, False)]
    # Camera bracket in the active v3 model, a conservative enclosing sphere.
    normal = np.array([-math.sin(pitch)*math.cos(yaw), -math.sin(pitch)*math.sin(yaw), math.cos(pitch)])
    center = wrist+.036*tool+.018*normal
    shapes.append((center, center, math.sqrt(.019**2+.026**2+.005**2), False))
    jaw = JAW_OPEN_M-JAW_TRAVEL_M*max(0., min(1., (2000-pwm[1])/500))
    lateral = np.array([-math.sin(yaw), math.cos(yaw), 0.])
    for side in (-1, 1):
        center = wrist+g.pad_center_from_wrist_m*tool+side*jaw*lateral
        shapes.append((center-FINGER_PAD_LENGTH_M/2*tool, center+FINGER_PAD_LENGTH_M/2*tool,
                       math.hypot(FINGER_HALF_WIDTH_M, FINGER_HALF_HEIGHT_M), True))
    points = []; radii = []; fingers = []
    for a, b, r, finger in shapes:
        n = max(1, math.ceil(float(np.linalg.norm(b-a))/.004))
        points.extend(a+(b-a)*i/n for i in range(n+1))
        radii.extend([r+SWEEP_PAD_M]*(n+1)); fingers.extend([finger]*(n+1))
    return np.array(points), np.array(radii), np.array(fingers)


@lru_cache(maxsize=128)
def swept_cloud(start_items, distance, z):
    return actual_pick_cloud(dict(start_items),(distance,0.,z))


def actual_pick_cloud(start,target,*,check_budget=None,capsule_fn=None,poses=None):
    capsule_fn=capsules if capsule_fn is None else capsule_fn
    hover, descent = grasp_poses(target) if poses is None else poses
    # Exactly the issued pick sequence: folded -> hover/open -> descent -> close -> lift.
    states = [start, {**start, **hover, 1: 2000}]
    states.extend({**states[-1], **p, 1: 2000} for p in descent)
    states.extend([{**states[-1], 1: 1500}, {**states[-1], **hover, 1: 1500}])
    chunks = []
    for stage, (a, b) in enumerate(zip(states, states[1:])):
        n = max(1, math.ceil(max(abs(a[k]-b[k]) for k in a)/5))
        for i in range(n+1):
            if check_budget is not None:check_budget()
            p = {k: a[k]+(b[k]-a[k])*i/n for k in a}
            xyz, radii, fingers = capsule_fn(p)
            # Only intended pad/assigned-beam contact during closure/lift is excluded.
            chunks.append((xyz, radii, fingers & (stage >= 9)))
    return tuple(np.concatenate([c[i] for c in chunks]) for i in range(3))


def collision_reason(world, rid, base, xyz, radii, pad_contact, *, audit=None):
    co, si = math.cos(base[2]), math.sin(base[2])
    points = xyz.copy()
    points[:, 0] = base[0]+co*xyz[:, 0]-si*xyz[:, 1]
    points[:, 1] = base[1]+si*xyz[:, 0]+co*xyz[:, 1]
    def rejected(reason, name, gaps):
        if audit is not None:
            audit.append({'reason':reason,'id':name,'gap_m':float(np.min(gaps)),
                          'category':'current_geometry','gap_scope':'arm_surface_signed_clearance'})
        return reason
    # Floor contact is not allowed for arm primitives.
    if np.any(points[:, 2] < radii):
        return rejected('arm_floor_sweep','floor',points[:,2]-radii)
    for key, o in world['objects'].items():
        if key == 'beam_1':continue
        hit = (np.linalg.norm(points[:, :2]-o['xy'], axis=1) < o['radius']+radii)
        if np.any(hit & (points[:, 2]-radii <= o['top_z_bound_m'])):
            eligible=points[:,2]-radii<=o['top_z_bound_m']
            return rejected('arm_cargo_sweep:'+key,key,(np.linalg.norm(points[:,:2]-o['xy'],axis=1)-o['radius']-radii)[eligible])
    for key, r in world['robots'].items():
        if key == rid:continue
        hit = np.linalg.norm(points[:, :2]-r['pose'][:2], axis=1) < .17+radii
        if np.any(hit & (points[:, 2]-radii <= r.get('top_z_bound_m', .32))):
            eligible=points[:,2]-radii<=r.get('top_z_bound_m',.32)
            return rejected('arm_peer_sweep:'+key,key,(np.linalg.norm(points[:,:2]-r['pose'][:2],axis=1)-.17-radii)[eligible])
    # Walls are conservatively full-height, consistent with the existing planner.
    for wi,(x, y, hx, hy, a) in enumerate(world.get('walls', [])):
        dx, dy = points[:, 0]-x, points[:, 1]-y
        rx = np.maximum(0, np.abs(math.cos(a)*dx+math.sin(a)*dy)-hx)
        ry = np.maximum(0, np.abs(-math.sin(a)*dx+math.cos(a)*dy)-hy)
        if np.any(np.hypot(rx, ry) < radii):
            name=next((k for k,m in world['visibility'][rid].get('observations',{}).items()
                if m['kind']=='wall' and tuple((*m['xyz'][:2],*m['half_extents'],m['yaw']))==(x,y,hx,hy,a)),
                'static_wall:'+str(wi)) if audit is not None else 'wall'
            return rejected('arm_wall_sweep',name,np.hypot(rx,ry)-radii)
    if world['beam'] is not None:
        x, y, a = world['beam']['pose']
        dx, dy = points[:, 0]-x, points[:, 1]-y
        rx = np.maximum(0, np.abs(math.cos(a)*dx+math.sin(a)*dy)-.30)
        ry = np.maximum(0, np.abs(-math.sin(a)*dx+math.cos(a)*dy)-HANDLE_WIDTH_M/2)
        # VisibleWorld uses band-centre minus 8.6mm as the grasp target;
        # authored paint is 0.6mm above the 32mm bar, so bar centre is 8mm lower.
        z = next(iter(world['beam']['ends'].values()))[2]-.008
        rz = np.maximum(0, np.abs(points[:, 2]-z)-HANDLE_HEIGHT_M/2)
        if np.any((np.sqrt(rx*rx+ry*ry+rz*rz) < radii) & ~pad_contact):
            return rejected('arm_beam_sweep','beam_1',(np.sqrt(rx*rx+ry*ry+rz*rz)-radii)[~pad_contact])
    return None


def band_view(world, rid, end, base, previous, *, navigation=None):
    """At least five of 15 known top-band probes in the conservative view cone."""
    from sim.grasp_act_visible_gaze import gaze_pose
    from sim.grasp_act_gaze import camera_extrinsics
    point = world['beam']['ends'][end]
    x, y = local(base, point)
    view = gaze_pose((x, y, point[2]+.009), previous)
    origin, axes = (navigation.camera_extrinsics(view) if hasattr(navigation,'camera_extrinsics')
                    else camera_extrinsics(view))
    a = world['beam']['pose'][2]
    co, si = math.cos(base[2]), math.sin(base[2])
    count = 0
    audit=[] if hasattr(navigation,'teacher') and navigation.teacher.search15_modes.get('search24_irm','off')!='off' else None
    if audit is not None:navigation.visibility_audit=audit
    for along in (-.0144, 0., .0144):
        for across in (-.0164, -.0082, 0., .0082, .0164):
            q = (point[0]+along*math.cos(a)-across*math.sin(a),
                 point[1]+along*math.sin(a)+across*math.cos(a), point[2]+.0092)
            x, y = local(base, q)
            optical = np.array(axes)@(np.array([x, y, q[2]])-origin)
            from sim.grasp_act_search25 import enabled as search25, in_frame, frame_clearance
            rectangular=(hasattr(navigation,'teacher') and search25(navigation.teacher,'search25_view'))
            accepted=in_frame(optical) if rectangular else (optical[2]>0 and np.linalg.norm(optical[:2])/optical[2]<=math.tan(math.radians(18)))
            if not accepted:
                if audit is not None:audit.append({'id':'camera_frame' if rectangular else 'camera_view_cone',
                    'gap_m':float(frame_clearance(optical) if rectangular else optical[2]*math.tan(math.radians(18))-np.linalg.norm(optical[:2])),
                    'category':'visibility','gap_scope':'signed optical rectangle clearance; not body gap' if rectangular else 'signed optical cone clearance; not body gap'})
                continue
            eye = (base[0]+co*origin[0]-si*origin[1], base[1]+si*origin[0]+co*origin[1], origin[2])
            ds = [(k,o['xy'], o['radius'], o['top_z_bound_m']) for k, o in world['objects'].items() if k != 'beam_1']
            ds += [(k,r['pose'][:2], .17, r.get('top_z_bound_m', .32)) for k, r in world['robots'].items() if k != rid]
            clear = True
            for name, center, radius, top in ds:
                dx, dy = q[0]-eye[0], q[1]-eye[1]
                u = max(0., min(1., ((center[0]-eye[0])*dx+(center[1]-eye[1])*dy)/max(dx*dx+dy*dy, 1e-12)))
                if 0 < u < 1 and math.dist((eye[0]+u*dx, eye[1]+u*dy), center) < radius+.005 and eye[2]+u*(q[2]-eye[2]) <= top+.005:
                    if audit is not None:audit.append({'id':name,'gap_m':math.dist((eye[0]+u*dx,eye[1]+u*dy),center)-radius,
                        'category':'visibility','gap_scope':'sight ray to occluder surface'})
                    clear = False;break
            wall_clear=(navigation.wall_segment_free(eye[:2],q[:2],.005) if hasattr(navigation,'wall_segment_free')
                        else segment_free(eye[:2],q[:2],[],world.get('walls',[]),.005)) if clear else False
            if clear and wall_clear:
                count += 1
            elif clear and audit is not None and hasattr(navigation,'last_wall_blocker'):
                audit.append(navigation.last_wall_blocker)
    return count, view


def select_sampled_goal(world, rid, end, bounds, folded, previous, *, current=None, choices=None, navigation=None):
    from sim.grasp_act_goal_set import geometry, ANGLES_DEG
    from sim.grasp_act_recovery import AXIAL_CHOICES
    from sim.grasp_act_visible_route import free, segment_free
    from scripts.zone_teacher import plan_path
    if navigation is not None:
        free,segment_free,plan_path=navigation.free,navigation.segment_free,navigation.plan_path
    radius, discs, rects = constraints(world, rid, folded)
    start = world['robots'][rid]['pose'][:2]
    if choices is None:choices = [(math.radians(a), d) for a in ANGLES_DEG for _, d in AXIAL_CHOICES]
    if current is not None:choices = [current]  # Revalidate the selected stance without oscillating.
    checked = []; feasible = []
    if hasattr(navigation,'candidate_rows'):navigation.candidate_rows=checked
    for choice in choices:
        if navigation is not None and hasattr(navigation, 'check_budget'):navigation.check_budget()
        pose, point, heading, goal = geometry(world, rid, end, choice)
        row = {'offset_deg': math.degrees(choice[0]), 'distance_m': choice[1], 'goal': goal}
        checked.append(row)
        try:
            if hasattr(navigation,'teacher') and navigation.teacher.search15_modes.get('search24_irm','off')!='off':
                from sim.grasp_act_search24 import certified_poses
                hover,descent=certified_poses(choice[1],point[2])
            else:hover,descent=grasp_poses((choice[1],0.,point[2]))
        except ValueError:row['reason'] = 'ik_unreachable';continue
        row['jaw_geometry'] = jaw_geometry(choice[0], descent[-1])
        if not row['jaw_geometry']['allowed']:row['reason'] = 'gripper_angle';continue
        x0, x1, y0, y1 = bounds
        if not (x0+radius <= goal[0] <= x1-radius and y0+radius <= goal[1] <= y1-radius):
            row['reason'] = 'outside_bounds';continue
        clear=free(goal,discs,rects,radius)
        if navigation is not None and hasattr(navigation,'candidate_audit'):
            row['collision_audit']=navigation.candidate_audit(goal,heading)
        if not clear:row['reason']='blocked_goal';continue
        retreat = (goal[0]-.06*math.cos(heading), goal[1]-.06*math.sin(heading))
        if not (x0+radius <= retreat[0] <= x1-radius and y0+radius <= retreat[1] <= y1-radius) or not segment_free(goal, retreat, discs, rects, radius):
            if hasattr(navigation,'last_blockers'):row['failure_audit']=list(navigation.last_blockers)
            row['reason'] = 'blocked_retreat';continue
        endpoint_only=getattr(navigation,'endpoint_only',False)
        path = ([tuple(start)] if endpoint_only else navigation.path_for_goal(start,goal,discs,rects,radius)
                if navigation is not None and hasattr(navigation,'path_for_goal') else
                [tuple(start), goal] if segment_free(start, goal, discs, rects, radius) else
                plan_path(start, goal, bounds, discs, rects=rects, radius=radius))
        if navigation is not None and hasattr(navigation,'last_path_audit'):
            row['path_audit']=navigation.last_path_audit
        if not path:row['reason'] = 'no_path';continue
        points = [tuple(start), *path]
        if not all(segment_free(a, b, discs, rects, radius) for a, b in zip(points, points[1:])):
            if hasattr(navigation,'last_blockers'):row['failure_audit']=list(navigation.last_blockers)
            row['reason'] = 'unsafe_body_sweep';continue
        base = (*goal, heading)
        visible, view = band_view(world, rid, end, base, previous, navigation=navigation)
        row['predicted_visible_probes'] = visible
        if visible < 5:
            if hasattr(navigation,'visibility_audit'):row['failure_audit']=list(navigation.visibility_audit)
            row['reason'] = 'band_not_visible';continue
        if hasattr(navigation,'pick_cloud'):
            xyz,radii,allowed=navigation.pick_cloud(view,choice[1],point[2])
        elif navigation is not None and hasattr(navigation,'check_budget'):
            xyz,radii,allowed=bounded_swept_cloud(tuple(sorted(view.items())),choice[1],point[2],navigation.check_budget)
        else:
            xyz, radii, allowed = swept_cloud(tuple(sorted(view.items())), choice[1], point[2])
        arm_audit=[] if hasattr(navigation,'teacher') and navigation.teacher.search15_modes.get('search24_irm','off')!='off' else None
        reason = collision_reason(world, rid, base, xyz, radii, allowed,audit=arm_audit)
        if arm_audit:row['failure_audit']=arm_audit
        if reason:row['reason'] = reason;continue
        if endpoint_only:
            row['reason']='endpoint_feasible'
            navigation.endpoints.append({'choice':choice,'goal':goal,'heading':heading})
            continue
        # Connect using the same finite compact-view family. Every yaw/PWM
        # transition is swept, including the initial in-place turn and retreat.
        route = [*points, retreat]
        before = dict(previous); prior = tuple(pose)
        reason = None
        for a, b in zip(route, route[1:]):
            n = max(1, math.ceil(math.dist(a, b)/.01))
            for i in range(n+1):
                if navigation is not None and hasattr(navigation, 'check_budget'):navigation.check_budget()
                xy = tuple(a[k]+(b[k]-a[k])*i/n for k in range(2))
                yaw = math.atan2(point[1]-xy[1], point[0]-xy[0])
                if hasattr(navigation,'connector_sample'):
                    count,after,cached_reason=navigation.connector_sample(prior,before,xy,yaw)
                else:count,after=band_view(world, rid, end, (*xy,yaw), before)
                if count < 5:
                    if hasattr(navigation,'visibility_audit'):row['failure_audit']=list(navigation.visibility_audit)
                    if navigation is not None and hasattr(navigation,'last_path_audit'):
                        row['connector_visibility_failure']={'visible_probes':count,'required':5,
                            'pose':[*xy,yaw],'segment_index':route.index(a),'fraction':i/n,
                            'offset_deg':math.degrees(choice[0]),'pwm':dict(after)}
                    reason='connector_band_not_visible';break
                co, si = math.cos(prior[2]), math.sin(prior[2])
                dx, dy = xy[0]-prior[0], xy[1]-prior[1]
                delta = (co*dx+si*dy, -si*dx+co*dy, wrap(yaw-prior[2]))
                reason = (cached_reason if hasattr(navigation,'connector_sample') else
                          issued_sweep_reason(world,rid,prior,before,after,delta))
                if reason and hasattr(navigation,'connector_collision_audit'):
                    row['failure_audit']=list(navigation.connector_collision_audit)
                if reason:break
                before=after;prior=(*xy,yaw)
            if reason:break
        if reason:row['reason'] = 'connector_'+reason;continue
        cost = sum(math.dist(a, b) for a, b in zip(points, points[1:]))+.06+.02*abs(wrap(heading-pose[2]))
        row.update(reason='feasible', cost=cost, arm_sweep=True, body_sweep=True, retreat=retreat)
        feasible.append({'choice': choice, 'goal': goal, 'heading': heading, 'path': path, 'cost': cost})
    return (min(feasible, key=lambda p: p['cost']) if feasible else None), checked


def issued_sweep_reason(world, rid, pose, before, after, delta, *, audit=None):
    """Check the actual next pulse plus camera/arm PWM interpolation."""
    dx, dy, da = delta
    n = max(1, math.ceil(max(abs(after[k]-before[k]) for k in before)/5),
            math.ceil(math.hypot(dx, dy)/.004), math.ceil(abs(da)/math.radians(1)))
    co, si = math.cos(pose[2]), math.sin(pose[2])
    for i in range(n+1):
        u = i/n
        pwm = {k:before[k]+u*(after[k]-before[k]) for k in before}
        xyz, radii, fingers = capsules(pwm)
        base = (pose[0]+u*(co*dx-si*dy), pose[1]+u*(si*dx+co*dy), pose[2]+u*da)
        reason = collision_reason(world, rid, base, xyz, radii, np.zeros_like(fingers),audit=audit)
        if reason:return reason
    return None


# Complete results only; exact PWM/distance/height keys, finite memory.
from collections import OrderedDict
_BOUNDED_CLOUDS = OrderedDict()

def bounded_swept_cloud(start_items,distance,z,check_budget):
    key=(start_items,distance,z)
    check_budget()
    if key not in _BOUNDED_CLOUDS:
        _BOUNDED_CLOUDS[key]=actual_pick_cloud(dict(start_items),(distance,0.,z),check_budget=check_budget)
        if len(_BOUNDED_CLOUDS)>4:_BOUNDED_CLOUDS.popitem(last=False)
    else:_BOUNDED_CLOUDS.move_to_end(key)
    return _BOUNDED_CLOUDS[key]
