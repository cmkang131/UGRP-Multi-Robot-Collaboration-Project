"""Opt-in FOV-constrained teacher. No world, measured pose or top image input.

Switch translation/re-observation and line IBVS (Chesi 2004; Corke &
Hutchinson 2001). This bounded, nominal-plane implementation does not inherit
their convergence guarantees. See release15.md for sources and limitations.
"""
from __future__ import annotations

import math
import numpy as np

from sim import release14
from sim.release_regrasp import beam_mask, assigned_beam_mask
from sim.visible_belief import odometry

PROFILE = 'release15_fov_v1'
PROFILES = (*release14.PROFILES, PROFILE)
SAFE = release14.SAFE
INNER = np.array([64., 64., 575., 415.])


def validate(profile, record_training, options, plan):
    release14.validate(release14.PROFILE if profile == PROFILE else profile,
                       record_training, options, plan)


def wall_distances(static, poses):
    """Signed L-infinity clearance, matching GlobalLandmarkMatcher.free()."""
    q = np.asarray(poses, float); x, y = q[:, 0], q[:, 1]
    a, b, c, d = static['bounds_m']
    distances = [x-a, b-x, y-c, d-y]
    for o in static['obstacles']:
        if o.get('kind') == 'wall':
            cx, cy = o['center_m']; hx, hy = o['half_extents_m']
            distances.append(np.maximum(abs(x-cx)-hx, abs(y-cy)-hy))
    return np.column_stack(distances)


def map_motion_clear(localizer, dx, dy, yaw=0.):
    """Accepted RGB fixes may be inside the covariance-inflated margin.

    Preserve the SAME .18+halo target for every wall. Inside it, permit only
    non-decreasing distance to that wall; never cross another wall's margin.
    Localization support is an observation hypothesis, not motion clearance.
    """
    if not localizer.map_pose_known or not (localizer.decision or {}).get('accepted'):
        return False
    pose = np.asarray(localizer.own.x, float); P = np.asarray(localizer.own.P, float)
    if not np.isfinite(pose).all() or not np.isfinite(P).all() or not np.isfinite([dx, dy, yaw]).all():
        return False
    from sim.global_landmark_localization import PARAMS
    margin = PARAMS['robot_clearance_m']+max(.02, 2*math.sqrt(max(0., np.linalg.eigvalsh(P[:2, :2]).max())))
    c, s = math.cos(pose[2]), math.sin(pose[2])
    delta = np.array([c*dx-s*dy, s*dx+c*dy, yaw])
    count = max(2, int(math.ceil(math.hypot(dx, dy)/.004))+1)
    q = pose+np.linspace(0., 1., count)[:, None]*delta
    distances = wall_distances(localizer.global_matcher.static, q)
    if np.any(distances[0] <= 0.):
        return False
    violated = distances[0] < margin
    return bool((distances[1:, ~violated] >= margin-1e-9).all() and
                (np.diff(distances[:, violated], axis=0) >= -1e-9).all())


def backoff_plan(localizer, teacher):
    checked = []
    for distance in (.15, .10, .05):
        clear = map_motion_clear(localizer, -distance, 0.)
        checked.append(dict(direction='rear', distance_m=distance, clear=clear))
        if clear:
            return teacher.shift_plan(distance, -1.), dict(action='map_backoff', distance_m=distance, candidates=checked)
    return [], dict(action='stationary_relook', distance_m=0., candidates=checked,
                    reason='rear_clearance_unknown_or_unsafe')


def approach_plan(localizer, teacher, now):
    plan = teacher.approach_plan(now); offset = np.zeros(3)
    for wheels, durations in plan:
        offset += odometry([w*d/.1 for w, d in zip(wheels, durations)], .1, teacher.odometry_profile)
        if not map_motion_clear(localizer, *offset):
            raise ValueError('release15_approach_map_clearance')
    return plan


def line_features(frame, end=None):
    """Track visible shaft span AND assigned band; never extrapolate a cut line.

    The controlled line segment is the existing central 20--80% row window,
    not an assertion that the entire physical beam is in view. A short clipped
    shaft has no direction. Its visible pixels can only request reframing.
    """
    import cv2
    f = release14.line_features(frame)
    f.update(points=[], fov_safe=False)
    if frame is None or frame.shape != (480, 640, 3) or frame.dtype != np.uint8:
        return f
    mask = assigned_beam_mask(frame, end, colour_profile=PROFILE)
    count, labels, stats, _ = cv2.connectedComponentsWithStats(mask.astype('uint8'))
    ranked = sorted(range(1, count), key=lambda i: -stats[i, cv2.CC_STAT_AREA])
    if not ranked or stats[ranked[0], cv2.CC_STAT_AREA] < 300:
        return f
    if len(ranked) > 1 and stats[ranked[1], cv2.CC_STAT_AREA] > .3*stats[ranked[0], cv2.CC_STAT_AREA]:
        return f
    component = labels == ranked[0]
    # A valid row line is guarded on its actual central visible span. Include
    # the assigned band wherever visible, even outside that span.
    target = component.copy()
    if f.get('line') is not None:
        target[:96] = False; target[384:] = False
        target |= component & ~beam_mask(frame)
    ys, xs = np.nonzero(target)
    if not len(xs):
        return f
    box = [float(xs.min()), float(ys.min()), float(xs.max()), float(ys.max())]
    points = [[box[x], box[y]] for x, y in ((0, 1), (2, 1), (0, 3), (2, 3))]
    f.update(points=points, visible_box_px=box, fov_safe=inside(points),
             fov_margin_px=float(min(box[0]-INNER[0], box[1]-INNER[1], INNER[2]-box[2], INNER[3]-box[3])))
    return f


def inside(points):
    p = np.asarray(points)
    return bool(len(p) and (p >= INNER[:2]).all() and (p <= INNER[2:]).all())


def project_motion(points, camera, pwm, motion):
    """Nominal plane prediction from own pixels + fixed K + commanded arm FK.

    Used only to rank small pulses; the NEXT real RGB is always required.
    No measured depth, target position, camera motion or joint angles enter.
    """
    cam, reason = camera.pose(pwm)
    if cam is None:
        raise ValueError('camera_'+str(reason))
    origin, rot = map(np.asarray, cam); k = np.asarray(camera.K)
    uv = np.column_stack((points, np.ones(len(points))))
    rays = (rot@np.linalg.inv(k)@uv.T).T
    if np.any(rays[:, 2] >= -1e-4):
        raise ValueError('fov_plane_unobservable')
    depth = (.032-origin[2])/rays[:, 2]
    if np.any(depth <= 0.) or np.any(depth > 1.5):
        raise ValueError('fov_plane_unobservable')
    q = origin+depth[:, None]*rays-np.array([motion[0], motion[1], 0.])
    c, s = math.cos(motion[2]), math.sin(motion[2])
    q = q@np.array([[c, -s, 0.], [s, c, 0.], [0., 0., 1.]])
    optical = (q-origin)@rot
    if np.any(optical[:, 2] <= .01):
        raise ValueError('fov_behind_camera')
    px = optical@k.T
    return px[:, :2]/px[:, 2, None]


def fov_merit(points):
    p = np.asarray(points)
    return float(np.square(np.maximum(INNER[:2]+16-p, 0.)).sum()+
                 np.square(np.maximum(p-(INNER[2:]-16), 0.)).sum())


def recovery_keeps_features(current, predicted):
    """No newly violated edge and no worsening of an already clipped edge."""
    def distances(p):
        p = np.asarray(p)
        return np.column_stack((p-INNER[:2], INNER[2:]-p))
    before, after = distances(current), distances(predicted)
    return bool((after >= np.minimum(before, 0.)-1e-8).all())


def line_step(f, camera, pwm, *, clearance):
    zero = dict(forward=0., left=0., yaw=0., aligned=False)
    if not f.get('valid') or not f.get('points'):
        return dict(kind='unobserved', **zero)
    if f.get('line') is not None and f['fov_safe']:
        step = release14.line_step(f, camera, pwm)
        if step['aligned']:
            return dict(forward=0., **step)
        # Reject a predicted crossing BEFORE rotation; then also recheck the
        # observed boundary after every <=0.1 s pulse, separated by 0.1 s rest.
        for scale in (1., .5, .25):
            motion = np.array([0., step['left'], step['yaw']])*scale
            if inside(project_motion(f['points'], camera, pwm, motion)) and clearance(*motion):
                return dict(step, forward=0., left=float(motion[1]), yaw=float(motion[2]))
    # Partition: translation only. A truncated slope/centroid NEVER issues yaw.
    current = fov_merit(f['points']); candidates = []
    for dx, dy in ((-.004, 0.), (.004, 0.), (0., -.004), (0., .004),
                   (-.004, -.004), (-.004, .004), (.004, -.004), (.004, .004)):
        if not clearance(dx, dy, 0.):
            continue
        predicted = project_motion(f['points'], camera, pwm, (dx, dy, 0.))
        if not recovery_keeps_features(f['points'], predicted):
            continue
        merit = fov_merit(predicted)
        if merit < current-1. or (current == 0. and dx < 0. and dy == 0. and inside(predicted)):
            candidates.append((round(merit, 6), math.hypot(dx, dy), dx, dy))
    if not candidates:
        return dict(kind='fov_blocked', **zero)
    merit, _, dx, dy = min(candidates)
    return dict(kind='recover_fov', forward=dx, left=dy, yaw=0., aligned=False,
                merit=current, predicted_merit=merit)


class LineAlign(release14.LineAlign):
    def features(self, frame):
        return line_features(frame, self.teacher.end)

    def __init__(self, teacher, now, *, camera, undistort, wheel_command, clearance, pick_audit=None):
        super().__init__(teacher, now, camera=camera, undistort=undistort,
                         wheel_command=wheel_command, clearance=clearance)
        self.missing = None; self.mode = None; self.pick_audit = pick_audit

    def fail(self, reason):
        self.failure = 'release15_'+reason; self.state = 'failed'
        return 'failed'

    def tick(self, now, capture, schedule):
        if self.failure: return 'failed'
        if self.state == 'done': return 'ready'
        if now-self.started > 16.: return self.fail('line_timeout')
        if now < self.until-1e-8: return 'pending'
        rid = self.teacher.rid
        if self.state == 'open':
            schedule(rid, [(0., {1:2000}), (1.2, self.hover)], now)
            self.state = 'align'; self.until = now+2.6; self.progress = self.until
            self.records.append(dict(t=now, event='open_then_hover'))
            return 'pending'
        if self.teacher.pwm != self.expected: return self.fail('open_hover_command_changed')
        f = self.features(self.undistort(capture(rid, now, 'line_recheck')))
        self.records.append(dict(t=now, event='image', **f))
        try: step = line_step(f, self.camera, self.teacher.pwm, clearance=self.clearance)
        except (ValueError, np.linalg.LinAlgError) as error: return self.fail(str(error))
        if step['kind'] == 'unobserved':
            self.stable = None
            self.missing = now if self.missing is None else self.missing
            self.wheel_command(rid, [0.]*4, [0.]*4, now)
            if now-self.missing >= 1.-1e-8: return self.fail('shaft_unobserved_1s')
            self.until = now+.2
            return 'pending'
        self.missing = None
        if self.mode != step['kind']:
            self.mode = step['kind']; self.best = math.inf; self.progress = now
            self.records.append(dict(t=now, event='mode_enter', mode=self.mode))
        if step['aligned']:
            self.stable = now if self.stable is None else self.stable
            if now-self.stable >= .3-1e-8:
                self.state = 'done'
                if self.pick_audit: self.pick_audit(now, self.teacher, self.xy)
                self.records.append(dict(t=now, event='aligned_before_pick', xy=list(self.xy), target_source='commanded_station'))
                return 'ready'
            self.until = now+.1
            return 'pending'
        self.stable = None
        if step['kind'] == 'fov_blocked': return self.fail('fov_no_safe_translation')
        if step['merit'] < self.best-.1: self.best = step['merit']; self.progress = now
        elif now-self.progress >= 3.: return self.fail('no_'+self.mode+'_progress_3s')
        w, d = release14.pulse_for(step['forward'], step['left'], step['yaw'], self.teacher.odometry_profile)
        actual = np.array(odometry([a*b/.1 for a, b in zip(w, d)], .1, self.teacher.odometry_profile))
        if np.any(self.motion+abs(actual) > np.array([.10, .10, math.radians(18)])+1e-9): return self.fail('motion_cap')
        if not self.clearance(*actual): return self.fail('map_motion_clearance')
        self.motion += abs(actual)
        self.wheel_command(rid, w, d, now)
        self.records.append(dict(t=now, event=step['kind'], wheels=w, durations=d, **step))
        self.until = now+.2
        return 'pending'
