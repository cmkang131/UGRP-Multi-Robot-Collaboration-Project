"""Opt-in 35-speed/60-ms stopped-feedback alignment; prior S2 output stays frozen.

REAL source: physical_state_machine_reference.py MOTOR_SPEED=35,
CAPTURE_CREEP/RETREAT_SECONDS=.06 and CAMERA_DELAY_SECONDS=.12. Translating
its short pulse to the inherited v106 dominant lateral axis is a DEV adapter,
not a claim that the old physical face-align controller used pure strafe.
"""
import copy
import math
from harness.zone_solo_cyan_v7_motion import Runtime as Previous
from harness.zone_solo_cyan_camera_v3 import Runtime as CameraRuntime

OPTION = 'real_fine_v1'
SPEED, DURATION_S, OBSERVE_S = .35, .06, .12


def alignment_primitive(action, option='off'):
    if option == 'off':
        return action
    if option != OPTION:
        raise ValueError('unsupported alignment_pulse')
    if action['kind'] not in ('drive', 'mecanum'):
        return action
    u = [float(action.get(k, 0.)) for k in ('forward', 'left', 'turn')]
    if not all(math.isfinite(v) for v in u):
        raise ValueError('nonfinite alignment command')
    if not any(u):
        return action
    axis = max(range(3), key=lambda i: abs(u[i]))
    output = [0., 0., 0.]
    output[axis] = math.copysign(SPEED, u[axis])
    return dict(kind='mecanum', forward=output[0], left=output[1], turn=output[2], duration_s=DURATION_S)


class Runtime(Previous):
    def __init__(self, *args, alignment_pulse='off', **kwargs):
        if alignment_pulse not in ('off', OPTION):
            raise ValueError('unsupported alignment_pulse')
        if alignment_pulse != 'off' and kwargs.get('min_wheel_cmd', 'off') != 'real_v1':
            raise ValueError('fine alignment requires explicit real output')
        super().__init__(*args, **kwargs)
        self.alignment_pulse = alignment_pulse
        self.fine_until = None
        self.fine_observe_after = -float('inf')
        self.fine_rows = []

    def step(self, now):
        if self.alignment_pulse == 'off' or self.terminal:
            return super().step(now)
        if self.fine_until is not None:
            if now < self.fine_until-1e-8:
                return []
            self.fine_observe_after = self.fine_until+OBSERVE_S
            self.fine_until = None
            return [(self.robot_id, {'kind': 'hold'})]
        if self.state != 'align':
            return super().step(now)
        if self.real_pulse_until is not None:
            return super().step(now)
        if now < self.fine_observe_after-1e-8 or (
            self.fine_observe_after > 0 and
            (self.last_obs is None or self.last_obs['sim_time'] < self.fine_observe_after-1e-8)
        ):
            return []
        # Run the exact inherited vision/align/arm logic, bypassing only the
        # coarse REAL output conversion which would turn lateral into .65/.65s.
        proposed = CameraRuntime.step(self, now)
        result = []
        for rid, action in proposed:
            issued = alignment_primitive(action, OPTION)
            if issued is not action:
                self.fine_until = now+issued['duration_s']
                self.fine_rows.append(dict(t=now, state=self.state,
                    frame_id=self.last_obs['frame_id'], target_base_m=copy.deepcopy(self.target),
                    requested=copy.deepcopy(action), issued=copy.deepcopy(issued)))
            result.append((rid, issued))
        return result

    def record(self):
        out = super().record()
        if self.alignment_pulse != 'off':
            out['alignment_pulse'] = dict(option=self.alignment_pulse, speed=SPEED,
                duration_s=DURATION_S, post_stop_observation_s=OBSERVE_S,
                transformations=self.fine_rows, old_alignment_tolerance_m=.003,
                hardware_lateral_qualification=False, model='unchanged exploratory v7 model; short lateral transfer unqualified')
        return out
