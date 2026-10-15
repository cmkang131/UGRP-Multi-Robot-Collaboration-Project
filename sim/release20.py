"""Default-off quantum-aware release alignment; compatible with release19 waits."""
from __future__ import annotations

import numpy as np

from sim import release14, release15, release17, release18, release19
from sim.release_regrasp_recovery import image_jacobian
from sim.settle_pulse import PulseSettler, proportional_pulse
from sim.visible_belief import odometry

SETTLE = 'release20_settle_v1'
MODES = ('off', SETTLE)


def validate(profile, record_training, options, plan):
    mode = options.get('release20_settle', 'off')
    if mode not in MODES or (mode != 'off' and (profile not in (release18.PROFILE, release19.PROFILE)
                                              or options.get('command_motion') != 'yaw_cal_v1')):
        raise ValueError('release20_settle requires release18/19 with yaw_cal_v1')
    release19.validate(profile, record_training, options, plan)


def polar_jacobian(camera, pwm):
    j, goal = image_jacobian(camera, pwm)
    eps = 1e-5
    transform = np.column_stack([
        (release14.polar_line(dict(center_error=(goal+np.eye(2)[i]*eps)[0], slope_error=(goal+np.eye(2)[i]*eps)[1]))-
         release14.polar_line(dict(center_error=(goal-np.eye(2)[i]*eps)[0], slope_error=(goal-np.eye(2)[i]*eps)[1])))/(2*eps)
        for i in range(2)])
    return transform@j


class LineAlign(release18.LineAlign):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.settlers = [PulseSettler(.025), PulseSettler(.06)]
        self.last_quantum = None

    def choose_step(self, f, period, now):
        step = super().choose_step(f, period, now)
        if step['kind'] != 'line_ibvs':
            self.settlers = [PulseSettler(.025), PulseSettler(.06)]
            self.last_quantum = None
            return step  # no missing/clipped/blocked image can certify settling
        model = polar_jacobian(self.camera, self.teacher.pwm)
        # Scale this coupled direction to one minimum wheel pulse, then run the
        # SAME wheel allocator/floor and command odometry as the real scheduler.
        w, d = release14.pulse_for(0., step['left'], step['yaw'], self.teacher.odometry_profile)
        if max(d) > 0:
            # Never enlarge an already sub-floor request before the deadband:
            # that can drop a different wheel pair and turn a lateral pulse
            # into yaw (round1 seed78526, world_t122.7).
            ratio = min(1., release17.YAW_FLOOR_S/max(d))
            w, d, _ = release17.floor_pulse(w, [v*ratio for v in d])
            actual = odometry([a*b/.1 for a,b in zip(w,d)], .1, self.teacher.odometry_profile)
            quantum = np.abs(model@np.array(actual[1:]))
        else:
            quantum = np.zeros(2)
        # During passive stability samples retain the quantum of the last
        # command direction; near zero error has no meaningful new direction.
        if self.last_quantum is not None and (self.stable is not None or step['aligned']):
            quantum = self.last_quantum
        self.last_quantum = quantum
        decisions = [s.observe(e, float(q)) for s,e,q in zip(self.settlers, step['error'], quantum)]
        aligned = all(d['settled'] for d in decisions)
        self.records.append(dict(t=now, event='release20_settle', axes=decisions, aligned=aligned,
                                 source='own RGB polar line and issued-wheel model'))
        if aligned:
            return dict(step, aligned=True, left=0., yaw=0.)
        # Quantize ONCE in the coupled wheel allocator. Applying a feature
        # quantum as a continuous gain first can change the deadband's active
        # wheel set. Keep the same proportional IBVS direction and bounds.
        error = np.array(step['error'])
        correction = np.array([proportional_pulse(float(e),float(q),quantize=False) for e,q in zip(error,quantum)])
        delta = -np.linalg.solve(model, correction)
        motion = np.array([0., *delta])
        motion /= max(1., abs(motion[1])/.004, abs(motion[2])/.025)
        w,d,_ = release17.yaw_pulse_for(*motion, self.teacher.odometry_profile)
        actual = odometry([a*b/.1 for a,b in zip(w,d)], .1, self.teacher.odometry_profile)
        if not release15.inside(release15.project_motion(f['points'], self.camera, self.teacher.pwm, actual)):
            return dict(step, kind='fov_blocked', aligned=False)
        # Base tick checks the realized command against map clearance and caps.
        # Mark history at the actual wheel callback, not on a rejected proposal.
        self._pending_errors = error.tolist()
        return dict(step, aligned=False, left=float(motion[1]), yaw=float(motion[2]))

    def tick(self, now, capture, schedule):
        original = self.wheel_command
        def issued(*args):
            original(*args)
            if any(args[2]) and hasattr(self, '_pending_errors'):
                for s,e in zip(self.settlers, self._pending_errors):
                    s.issued(e)
                del self._pending_errors
        self.wheel_command = issued
        try:
            return super().tick(now, capture, schedule)
        finally:
            self.wheel_command = original
            if hasattr(self, '_pending_errors'):
                del self._pending_errors

    def record(self):
        return dict(super().record(), release20=dict(settle=SETTLE))


map_motion_clear = release18.map_motion_clear
backoff_plan = release18.backoff_plan
approach_plan = release18.approach_plan
