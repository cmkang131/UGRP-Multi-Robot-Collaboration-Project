"""Opt-in release14 teacher controls. Own RGB, commands and static map only.

Line IBVS: Espiau/Chaumette/Rives (1992), Chaumette/Hutchinson (2006).
The nominal interaction matrix is differentiated through issued camera FK;
it is not a measured pose, depth, wheel slip or calibrated plant model.
"""
from __future__ import annotations

import math
import numpy as np

from sim.grasp_act_port import duty_wheels
from sim.visible_belief import odometry, rates
from sim.release_regrasp_recovery import shaft_features, image_jacobian

PROFILE = 'release14_line_v1'
PROFILES = ('off', PROFILE)
SAFE = dict(own_pose_source='commands', pose_anchor='command_relative_v1',
            held_object='hidden_v1', placement='global_localized_release_v1',
            lookaround='setdown_global_v1', observe_mode='backoff_v3',
            command_motion='native_yaw_v1', regrasp_check='own_rgb_lift_v1',
            regrasp_recovery='own_rgb_realign_v1', reach_mode='pad_window_v2')


def validate(profile, record_training, options, plan):
    """Run before any backend, output or prefix is constructed (also Python API)."""
    if profile not in PROFILES:
        raise ValueError('unknown release profile')
    if record_training and profile != PROFILE:
        raise ValueError('training RGB requires release14 safe profile')
    if profile == PROFILE:
        bad = [k for k, v in SAFE.items() if options.get(k) != v]
        if bad:
            raise ValueError('release14 unsafe configuration: '+', '.join(bad))
        if plan.get('end_color_scene') != 'grasp_act_teal_blue_v1':
            raise ValueError('release14 requires versioned teal/blue end scene')
    if record_training:
        # This runner has never implemented a student writer. Do not silently
        # relabel review JPEGs as training data or bypass the new >=38/40 gate.
        raise ValueError('release training RGB unavailable: new-profile gate and student writer required')


def polar_line(feature):
    """x*cos(theta)+y*sin(theta)=rho in normalized centred image coordinates."""
    a = feature['slope_error']/.4
    theta = -math.atan(a)
    return np.array([feature['center_error']*math.cos(theta), theta])


def line_features(frame):
    f = shaft_features(frame)
    f['line'] = (polar_line(f).tolist() if f.get('unclipped') and
                 f.get('slope_error') is not None else None)
    return f


def line_step(feature, camera, pwm):
    """Two-feature feedback on EVERY image; no centroid-only lateral fallback."""
    j, goal = image_jacobian(camera, pwm)
    if feature.get('line') is None:
        # A bounded yaw probe may reframe the shaft. It never certifies its
        # direction. No translation is allowed until BOTH boundaries return.
        if not feature.get('valid'):
            return dict(kind='unobserved', left=0., yaw=0., aligned=False)
        error = feature['center_error']-goal[0]
        yaw = float(np.clip(-error/j[0, 1], -.025, .025))
        if abs(yaw) < .014:
            yaw = math.copysign(.014, yaw if yaw else -1.)
        return dict(kind='recover_direction', left=0., yaw=yaw, aligned=False)
    target = polar_line(dict(center_error=goal[0], slope_error=goal[1]))
    # Chain rule from row-line coordinates to (rho, theta), evaluated at
    # the desired line. This is the standard desired-Jacobian IBVS variant.
    eps = 1e-5
    transform = np.column_stack([
        (polar_line(dict(center_error=(goal+np.eye(2)[i]*eps)[0],
                         slope_error=(goal+np.eye(2)[i]*eps)[1]))-
         polar_line(dict(center_error=(goal-np.eye(2)[i]*eps)[0],
                         slope_error=(goal-np.eye(2)[i]*eps)[1])))/(2*eps)
        for i in range(2)])
    error = np.asarray(feature['line'])-target
    delta = -.5*np.linalg.solve(transform@j, error)
    # Coupled command, bounded before wheel allocation. Small pulses followed
    # by fresh orientation feedback correct uncommanded yaw without assuming
    # that issued yaw=0 means actual yaw=0. No GT-fitted feed-forward constant.
    scale = max(1., abs(delta[0])/.004, abs(delta[1])/.025)
    delta /= scale
    aligned = abs(error[0]) <= .025 and abs(error[1]) <= .06
    return dict(kind='line_ibvs', left=float(delta[0]), yaw=float(delta[1]),
                aligned=bool(aligned), error=error.tolist(),
                merit=float(np.linalg.norm(error/np.array([.025, .06]))))


def pulse_for(dx, dy, yaw, profile):
    """Preserve the coupled ratio; unlike v1 never floor each wheel separately."""
    ax, lat, turn = rates(profile)
    effort = np.array([dx/ax, dy/lat, yaw/turn])*.35/.1
    return duty_wheels(effort.tolist())


def map_motion_clear(localizer, dx, dy, yaw=0.):
    """Swept static clearance from an RGB fix propagated by issued commands.

    Unknown pose rejects translation/turning; no spawn/handoff error enters.
    The existing .18 m envelope is retained, plus covariance uncertainty.
    """
    dec = localizer.decision or {}
    if not localizer.map_pose_known or not dec.get('accepted'):
        return False
    pose = np.asarray(localizer.own.x, float)
    covariance = np.asarray(localizer.own.P, float)
    if not np.isfinite(pose).all() or not np.isfinite(covariance).all():
        return False
    halo = max(.02, 2*math.sqrt(max(0., float(np.linalg.eigvalsh(covariance[:2,:2]).max()))))
    c, s = math.cos(pose[2]), math.sin(pose[2])
    q = np.tile(pose, (11, 1))
    q += np.linspace(0., 1., 11)[:,None]*np.array([c*dx-s*dy, s*dx+c*dy, yaw])
    return bool(localizer.global_matcher.free(q, extra_clearance=halo).all())


def backoff_plan(localizer, teacher):
    """Choose rear distance using map clearance; blocked/unknown => in-place view.

    No lateral blind detour: that would discard the assigned-end direction.
    A stationary panorama is the progress alternative when rear is unsafe.
    """
    checked = []
    for distance in (.15, .10, .05):
        clear = map_motion_clear(localizer, -distance, 0.)
        checked.append(dict(direction='rear', distance_m=distance, clear=clear))
        if clear:
            return teacher.shift_plan(distance, -1.), dict(
                action='map_backoff', distance_m=distance, candidates=checked)
    return [], dict(action='stationary_relook', distance_m=0., candidates=checked,
                    reason='rear_clearance_unknown_or_unsafe')


def approach_plan(localizer, teacher, now):
    """Check the whole nominal reapproach, including its intermediate points."""
    plan = teacher.approach_plan(now)
    offset = np.zeros(3)
    for wheels, durations in plan:
        offset += odometry([w*d/.1 for w,d in zip(wheels,durations)], .1, teacher.odometry_profile)
        if not map_motion_clear(localizer, *offset):
            raise ValueError('release14_approach_map_clearance')
    return plan


class LineAlign:
    """Open-gripper alignment used before approach, after approach and retry.

    No open-loop assumption of beam orientation survives a motion boundary.
    Each pulse consumes a fresh image and must pass the map clearance guard.
    """
    def __init__(self, teacher, now, *, camera, undistort, wheel_command,
                 clearance, retry=False):
        from harness.visual_arm_v3 import MOUNT_X_M, solve_grip_site_ik
        self.teacher = teacher
        self.camera, self.undistort = camera, undistort
        self.wheel_command, self.clearance = wheel_command, clearance
        self.xy = (MOUNT_X_M+teacher.reach_mid(), 0.)
        self.hover = {k:int(v) for k,v in solve_grip_site_ik((*self.xy,.095)).items() if k in (3,4,5,6)}
        self.expected = {**teacher.pwm, **self.hover, 1:2000}
        self.started = now; self.until = now; self.state = 'open'; self.failure = None
        self.records = []; self.stable = None; self.best = math.inf; self.progress = now
        self.motion = np.zeros(3); self.search_yaw = 0.; self.retry = retry

    def fail(self, reason):
        self.failure = 'release14_'+reason; self.state = 'failed'
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
        if self.teacher.pwm != self.expected:
            return self.fail('open_hover_command_changed')
        f = line_features(self.undistort(capture(rid, now, 'line_recheck')))
        self.records.append(dict(t=now, event='image', **f))
        try: step = line_step(f, self.camera, self.teacher.pwm)
        except (ValueError, np.linalg.LinAlgError) as error: return self.fail(str(error))
        if step['aligned']:
            self.stable = now if self.stable is None else self.stable
            if now-self.stable >= .3-1e-8:
                self.state = 'done'
                self.records.append(dict(t=now, event='aligned_before_pick', xy=list(self.xy)))
                return 'ready'
            self.until = now+.1
            return 'pending'
        self.stable = None
        if step['kind'] == 'unobserved': return self.fail('shaft_unobserved')
        if step['kind'] == 'recover_direction':
            self.search_yaw += abs(step['yaw'])
            if self.search_yaw > math.radians(12): return self.fail('direction_search_cap')
        elif step['merit'] < self.best-.1:
            self.best = step['merit']; self.progress = now
        elif now-self.progress >= 3.: return self.fail('no_line_progress_3s')
        w, d = pulse_for(0., step['left'], step['yaw'], self.teacher.odometry_profile)
        actual_command = np.array(odometry([a*b/.1 for a,b in zip(w,d)], .1, self.teacher.odometry_profile))
        if np.any(self.motion+abs(actual_command) > np.array([.001,.10,math.radians(18)])):
            return self.fail('motion_cap')
        if not self.clearance(*actual_command): return self.fail('map_motion_clearance')
        self.motion += abs(actual_command)
        self.wheel_command(rid, w, d, now)
        self.records.append(dict(t=now,event=step['kind'],wheels=w,durations=d,**step))
        self.until = now+.2
        return 'pending'

    def record(self):
        return dict(robot=self.teacher.rid, state=self.state, failure=self.failure,
                    events=self.records, commanded_absolute_motion=self.motion.tolist(),
                    physical_validation='unverified', inputs='own RGB, issued PWM, static map and RGB pose estimate')
