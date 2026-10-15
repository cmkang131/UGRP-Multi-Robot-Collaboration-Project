"""Bounded own-RGB alternatives to an FOV-rejected minimum pulse (default off).

Camera reframing is temporary: alignment is certified only after restoring the
original open/hover command and obtaining fresh RGB for the usual 0.3 s dwell.
No world state or measured joints enter this module. See release21.md.
"""
from __future__ import annotations

import math
import numpy as np

from sim import release15, release17, release20
from sim.settle_pulse import PulseSettler
from sim.visible_belief import odometry, rates

MODE = 'release21_v1'
MODES = ('off', MODE)
ATTEMPTS = 2
VIEW_WAIT_S = .8


def validate(profile, record_training, options, plan):
    mode = options.get('release21', 'off')
    if mode not in MODES or (mode != 'off' and options.get('release20_settle') != release20.SETTLE):
        raise ValueError('release21 requires release20_settle_v1')
    release20.validate(profile, record_training, options, plan)


def reproject(points, camera, before, after, motion=(0., 0., 0.)):
    """Own pixels on the same nominal plane as release15, commanded camera FK."""
    old, reason = camera.pose(before)
    new, reason2 = camera.pose(after)
    if old is None or new is None:
        raise ValueError('camera_'+str(reason if old is None else reason2))
    origin, rotation = map(np.asarray, old)
    target, target_rotation = map(np.asarray, new)
    k = np.asarray(camera.K)
    rays = (rotation @ np.linalg.inv(k) @ np.column_stack((points, np.ones(len(points)))).T).T
    if np.any(rays[:, 2] >= -1e-4):
        raise ValueError('fov_plane_unobservable')
    depth = (.032-origin[2])/rays[:, 2]
    if np.any(depth <= 0.) or np.any(depth > 1.5):
        raise ValueError('fov_plane_unobservable')
    q = origin+depth[:, None]*rays-np.array([motion[0], motion[1], 0.])
    c, s = math.cos(motion[2]), math.sin(motion[2])
    q = q @ np.array([[c, -s, 0.], [s, c, 0.], [0., 0., 1.]])
    optical = (q-target) @ target_rotation
    if np.any(optical[:, 2] <= .01):
        raise ValueError('fov_behind_camera')
    px = optical @ k.T
    return px[:, :2]/px[:, 2, None]


def margin(points):
    p = np.asarray(points)
    return float(min((p-release15.INNER[:2]).min(), (release15.INNER[2:]-p).min()))


class _Blocked(Exception):
    def __init__(self, feature, motion=None):
        self.feature, self.motion = feature, motion


class LineAlign(release20.LineAlign):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.alternatives = dict(recenter=0, backoff=0, reverse=0)
        self.view_state = None
        self.tried_views = set()
        self.blocked_count = 0

    def reset_settling(self):
        self.settlers = [PulseSettler(.025), PulseSettler(.06)]
        self.last_quantum = self.stable = self.sign_pending = self.pending = None
        if hasattr(self, '_pending_errors'):
            del self._pending_errors

    def blocked_step(self, f, step, motion, actual):
        raise _Blocked(f, tuple(float(v) for v in motion))

    def choose_step(self, f, period, now):
        step = super().choose_step(f, period, now)
        if step['kind'] == 'fov_blocked':
            raise _Blocked(f)
        return step

    def pulse(self, motion):
        w, d, floor = release17.yaw_pulse_for(*motion, self.teacher.odometry_profile)
        actual = np.array(odometry([a*b/.1 for a, b in zip(w, d)], .1, self.teacher.odometry_profile))
        return w, d, actual, floor

    def allowed(self, f, actual):
        # Preserve the original cumulative motion cap and static clearance.
        if np.any(self.motion+abs(actual) > np.array([.10, .10, math.radians(18)])+1e-9):
            return False
        if not self.clearance(*actual):
            return False
        predicted = release15.project_motion(f['points'], self.camera, self.teacher.pwm, actual)
        return release15.inside(predicted) if f.get('fov_safe') else release15.recovery_keeps_features(f['points'], predicted)

    def issue(self, f, motion, now, action):
        try:
            w, d, actual, floor = self.pulse(motion)
            safe = any(d) and self.allowed(f, actual)
            sign = None
            if safe and self.sign_state == 'unchecked' and abs(actual[2]) > 1e-9 and f.get('center_error') is not None:
                expected, yaw, lateral = release17.yaw_expected_shift_px(self.camera, self.teacher.pwm,
                                                                        float(actual[1]), float(actual[2]))
                sign = dict(center_error=f['center_error'], expected_px=expected, yaw_px=yaw, lateral_px=lateral)
        except (ValueError, np.linalg.LinAlgError):
            safe = False
        if not safe:
            return False
        self.motion += abs(actual)
        self.wheel_command(self.teacher.rid, w, d, now)
        self.records.append(dict(t=now, event='release21_pulse', action=action, wheels=w, durations=d,
                                 realized_motion=actual.tolist(), yaw_floor=floor))
        self.reset_settling()
        self.sign_pending = sign
        self.progress = now
        self.until = now+max(.2, max(d)+.1)
        return True

    def camera_candidate(self, f, motion):
        before = self.teacher.pwm
        current = margin(f['points'])
        candidates = []
        # Pan (6) and wrist tilt (3), at most 10.8 degrees from the original
        # unloaded hover. FK joint ranges remain enforced; body stays still.
        for pan in (0, -60, 60, -120, 120):
            for tilt in (0, -60, 60, -120, 120):
                if (pan, tilt) == (0, 0) or (pan, tilt) in self.tried_views:
                    continue
                pwm = {**before, 6:before[6]+pan, 3:before[3]+tilt}
                try:
                    p = reproject(f['points'], self.camera, before, pwm)
                    after = reproject(f['points'], self.camera, before, pwm, motion or (0., 0., 0.))
                except (ValueError, np.linalg.LinAlgError):
                    continue
                score = min(margin(p), margin(after))
                if score > current+4. and release15.recovery_keeps_features(f['points'], p):
                    candidates.append((-score, abs(pan)+abs(tilt), pan, tilt, pwm))
        if not candidates:
            return None
        _, _, pan, tilt, pwm = min(candidates, key=lambda v:v[:4])
        self.tried_views.add((pan, tilt))
        return pwm

    def recover(self, blocked, now, schedule):
        self.blocked_count += 1
        f, motion = blocked.feature, blocked.motion
        self.records.append(dict(t=now, event='release21_fov_blocked', count=self.blocked_count,
                                 proposed_motion=motion, attempts=dict(self.alternatives)))
        self.reset_settling()
        # Attempts are lifetime bounds for this alignment, never reset by a
        # successful image or pulse. Rejected alternatives are counted too.
        while self.alternatives['recenter'] < ATTEMPTS:
            self.alternatives['recenter'] += 1
            pwm = self.camera_candidate(f, motion)
            self.records.append(dict(t=now, event='release21_alternative', action='recenter',
                                     attempt=self.alternatives['recenter'], accepted=pwm is not None))
            if pwm is not None:
                self.view_state = dict(home=dict(self.expected), target=pwm, motion=motion, phase='view')
                self.wheel_command(self.teacher.rid, [0.]*4, [0.]*4, now)
                schedule(self.teacher.rid, [(0., {3:pwm[3], 6:pwm[6]})], now)
                self.until = now+VIEW_WAIT_S
                return 'pending'
        for action in ('backoff', 'reverse'):
            while self.alternatives[action] < ATTEMPTS:
                self.alternatives[action] += 1
                if action == 'backoff':
                    candidate = (-rates(self.teacher.odometry_profile)[0]*.1, 0., 0.)
                elif motion is not None:
                    w, d, _, _ = self.pulse(motion)
                    scale = release17.YAW_FLOOR_S/max(d) if max(d) else 0.
                    # Invert the SAME coupled request, scaled down to one
                    # minimum pulse; the allocator remains the only quantizer.
                    candidate = tuple(-v*min(1., scale) for v in motion)
                else:
                    candidate = None
                inward = True
                if action == 'reverse' and candidate is not None:
                    predicted = release15.project_motion(f['points'], self.camera, self.teacher.pwm,
                                                         self.pulse(candidate)[2])
                    inward = margin(predicted) > margin(f['points'])+1e-6
                accepted = candidate is not None and inward and self.issue(f, candidate, now, action)
                self.records.append(dict(t=now, event='release21_alternative', action=action,
                                         attempt=self.alternatives[action], accepted=bool(accepted)))
                if accepted:
                    return 'pending'
        self.records.append(dict(t=now, event='release21_exhausted', attempts=dict(self.alternatives)))
        return self.fail('fov_no_safe_translation')

    def camera_ready(self, view, target, now):
        if self.teacher.pwm != target:
            return False
        if self.command_history is not None:
            ages = [self.command_history.servo_age(sid, target[sid], now) for sid in (3,6)]
            age = min(ages) if all(v is not None for v in ages) else 0.
        else:
            # Without a fresh scheduler history, start the dwell only once
            # the complete issued snapshot is actually observed.
            view.setdefault('command_seen', now)
            age = now-view['command_seen']
        if age < VIEW_WAIT_S-1e-8:
            self.until = now+max(.1, VIEW_WAIT_S-age)
            return False
        return True

    def restore_camera(self, view, now, schedule):
        schedule(self.teacher.rid, [(0., {3:view['home'][3], 6:view['home'][6]})], now)
        view['phase'] = 'restore'
        view.pop('command_seen', None)
        self.until = now+VIEW_WAIT_S

    def tick(self, now, capture, schedule):
        if self.view_state is not None:
            if self.failure:
                return 'failed'
            if now-self.started > 16.:
                return self.fail('line_timeout')
            if now < self.until-1e-8:
                return 'pending'
            view = self.view_state
            if view['phase'] == 'restore':
                if self.teacher.pwm != view['home']:
                    return self.fail('open_hover_command_changed')
                if not self.camera_ready(view, view['home'], now):
                    return 'pending'
                self.view_state = None
                self.reset_settling()
                self.progress = now
                if view.get('failure'):
                    return self.fail(view['failure'])
                # Continue the original deadline; camera recovery does not
                # extend the 16 s alignment or the episode's 180 s cap.
            else:
                if self.teacher.pwm != view['target']:
                    return self.fail('open_hover_command_changed')
                if view['phase'] == 'view' and not self.camera_ready(view, view['target'], now):
                    return 'pending'
                if view['phase'] == 'verify':
                    f = self.features(self.undistort(capture(self.teacher.rid, now, 'release21_verify')))
                    self.records.append(dict(t=now, event='release21_verify_view', **f))
                    self.check_yaw_sign(f, now)
                    if self.sign_pending is not None and now-view['pulse_at'] < 1.-1e-8:
                        self.until = now+.2
                        return 'pending'
                    if self.sign_state == 'mismatch':
                        view['failure'] = 'yaw_cal_sign_mismatch'
                    elif self.sign_pending is not None:
                        view['failure'] = 'shaft_unobserved_1s'
                    self.restore_camera(view, now, schedule)
                    return 'pending'
                f = self.features(self.undistort(capture(self.teacher.rid, now, 'release21_recenter')))
                self.records.append(dict(t=now, event='release21_view', **f))
                accepted = (now-self.started <= 16. and f.get('valid') and bool(f.get('points'))
                            and view['motion'] is not None and self.issue(f, view['motion'], now, 'recenter_correction'))
                self.records.append(dict(t=now, event='release21_recenter_result', accepted=bool(accepted)))
                if accepted:
                    # Check body yaw using a fresh image at the SAME camera
                    # command, before any camera restoration can contaminate it.
                    view.update(phase='verify', pulse_at=now)
                else:
                    self.restore_camera(view, now, schedule)
                return 'pending'
        try:
            return super().tick(now, capture, schedule)
        except _Blocked as blocked:
            try:
                return self.recover(blocked, now, schedule)
            except (ValueError, np.linalg.LinAlgError) as error:
                return self.fail(str(error))

    def record(self):
        return dict(super().record(), release21=dict(mode=MODE, fov_blocked=self.blocked_count,
                    alternatives=dict(self.alternatives), maximum_attempts_each=ATTEMPTS))


map_motion_clear = release20.map_motion_clear
backoff_plan = release20.backoff_plan
approach_plan = release20.approach_plan
