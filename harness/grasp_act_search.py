"""ACT10 teacher-only reacquisition from visible memory and issued commands.

No world, measured joints, contacts, map anchor or evaluator is accepted.
The nominal wheel model is the pinned teacher's command dead reckoning, not
measured odometry. Its uncertainty motivates a bounded expanding search.
"""
from copy import deepcopy
import math

from harness.grasp_act_contract import command

SEARCH_MODE = 'recovery_active_search_v1'
SEARCH_LIMIT_S = 24.
ORIENT_LIMIT_S = 3.
PAN_STEP_S = .9
PANS = (1500, 1000, 500, 1000, 1500, 2000, 2500, 2000, 1500)
PAN_SWEEP_S = len(PANS)*PAN_STEP_S
YAW_RATE = (.0325*150*2*math.pi/60)*.35/.1255


def command_delta(issued, dt):
    """Same 65 mm/150 rpm mecanum model as teacher 6f057f7e."""
    a, b, c, d = [w*min(dt, t) for w, t in zip(issued['wheels'], issued['duration_s'])]
    gain = .0325*150*2*math.pi/60
    return (gain*(a+b+c+d)/4, gain*(-a+b+c-d)/4,
            gain*(-a+b-c+d)/(4*.1255))


def propagate(point, issued, dt):
    dx, dy, yaw = command_delta(issued, dt)
    x, y, z = point; x -= dx; y -= dy
    co, si = math.cos(yaw), math.sin(yaw)
    return [co*x+si*y, -si*x+co*y, z]


class CommandSearch:
    def __init__(self):
        self.point = self.seen_t = self.previous_t = None
        self.started = self.stage_t = None
        self.stage = None
        self.scan_yaw = 0.
        self.last_action_stage = None

    def observe(self, now, measurement, previous, *, holding=False, eligible=True):
        dt = 0. if self.previous_t is None else now-self.previous_t
        if self.previous_t is not None and not 0 < dt <= .15+1e-8:
            raise ValueError('strictly increasing 10 Hz search clock required')
        self.previous_t = now
        if holding or not eligible:
            self.point = self.seen_t = None
            self.reset_search()
            return
        if previous is not None:
            if self.point is not None:
                self.point = propagate(self.point, previous, dt)
            if self.last_action_stage == 'body_scan':
                self.scan_yaw += abs(command_delta(previous, dt)[2])
        self.last_action_stage = None
        if measurement is not None:
            if (set(measurement) != {'xyz', 'yaw'} or len(measurement['xyz']) != 3
                    or not all(math.isfinite(v) for v in (*measurement['xyz'], measurement['yaw']))):
                raise ValueError('finite visible relative measurement required')
            self.point, self.seen_t = list(measurement['xyz']), now
            self.reset_search()

    def reset_search(self):
        self.started = self.stage_t = self.stage = None
        self.scan_yaw = 0.
        self.last_action_stage = None

    def action(self, now, hold, gaze, slew):
        """Return (clean corrective label, exhausted, audit).

        gaze/slew are the pinned pure command-space camera FK and rate limit.
        A forward point at the remembered range selects the wrist/elbow tilt;
        the pan sweep then widens around it. No close-range scan posture.
        """
        if self.started is None:
            self.started = self.stage_t = now
            self.stage = 'orient'
        age = now-self.started
        value = deepcopy(hold)
        if self.point is None or age >= SEARCH_LIMIT_S-1e-8:
            return value, True, self.diagnostic(now)
        distance = math.hypot(*self.point[:2])
        bearing = math.atan2(self.point[1], self.point[0])
        if self.stage == 'orient' and (abs(bearing) <= .12 or now-self.stage_t >= ORIENT_LIMIT_S):
            self.stage, self.stage_t = 'pan_scan', now
        if self.stage == 'pan_scan' and now-self.stage_t >= PAN_SWEEP_S-1e-8:
            self.stage, self.stage_t = 'body_scan', now
        if self.stage == 'body_scan' and self.scan_yaw >= 2*math.pi-1e-8:
            return value, True, self.diagnostic(now)
        pose = {int(k): v for k, v in hold['pwm'].items()}
        target = gaze([distance, 0., self.point[2]], pose, visible=False)
        target[6] = (1500 if self.stage == 'orient' else
                     PANS[int((now-self.stage_t+1e-8)/PAN_STEP_S) % len(PANS)])
        value['pwm'] = {str(k): v for k, v in slew(pose, target).items()}
        if self.stage in ('orient', 'body_scan'):
            sign = (1 if bearing > 0 else -1) if self.stage == 'orient' else 1
            remaining = abs(bearing) if self.stage == 'orient' else 2*math.pi-self.scan_yaw
            duration = min(.1 if self.stage == 'orient' else .04, remaining/YAW_RATE)
            value['wheels'] = [sign*w for w in (-.35, .35, -.35, .35)]
            value['duration_s'] = [duration]*4
        self.last_action_stage = self.stage
        return command(value), False, self.diagnostic(now)

    def diagnostic(self, now):
        return {'stage': self.stage, 'search_s': now-self.started if self.started is not None else 0.,
                'last_seen_t': self.seen_t, 'expected_relative_xyz': deepcopy(self.point),
                'commanded_scan_yaw_rad': self.scan_yaw,
                'scope': 'visible memory + actual issued history only; not measured motion'}
