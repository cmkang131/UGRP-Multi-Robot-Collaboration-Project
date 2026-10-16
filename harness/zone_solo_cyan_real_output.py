"""Opt-in REAL bounded primitives at the v106 command boundary; defaults unchanged.

Physical source: scripts/masterpi_control.py (0 or >=35),
scripts/red_block/primitive.py (35, short pulses; lateral 65/.65 s), and
physical_state_machine_reference.py (35-speed .10/.12 s fine turns).
The physical code rejects subminimum wheels; it does NOT independently clamp
four mixed wheels. A continuous v106 request is serialized onto its dominant
body axis, then executed in the simulator's existing logical wheel basis.
"""
import copy
import math
import numpy as np
from harness.zone_solo_cyan_camera_v3 import Runtime as CameraRuntime


def primitive(action, option='off'):
    if option == 'off':
        return action  # exact object/float/serialization preservation
    if option != 'real_v1':
        raise ValueError('unsupported min_wheel_cmd')
    if action['kind'] not in ('drive', 'mecanum'):
        return action
    u = [float(action.get(k, 0.)) for k in ('forward', 'left', 'turn')]
    if not all(math.isfinite(v) for v in u):
        raise ValueError('nonfinite command')
    if not any(u):
        return action
    axis = max(range(3), key=lambda i: abs(u[i]))
    output = [0., 0., 0.]
    output[axis] = math.copysign(.65 if axis == 1 else .35, u[axis])
    duration = max(.10, min(.80, float(action['duration_s'])))
    if axis == 1:
        duration = max(.65, duration)
    return dict(kind='mecanum', forward=output[0], left=output[1], turn=output[2], duration_s=duration)


def install_motion(pf, model):
    """Offline fixed coefficients only. No evaluation state is accepted here."""
    from harness.owncam_localizer import OwnCamLocalizer
    gain = np.asarray(model['gain'], float)
    if gain.shape != (3, 3) or not np.isfinite(gain).all() or abs(np.linalg.det(gain)) < 1e-8:
        raise ValueError('invalid diagnostic gain')
    for key in ('motion', 'motion_loaded'):
        profile = copy.deepcopy(pf.params[key])
        profile.update(gain=gain.tolist(), tau_s=model['tau_s'], tau_stop_s=model['tau_stop_s'])
        for obsolete in ('deadband', 'tau_axis_s', 'load_transition', 'yaw_bias_std_rad_s'):
            profile.pop(obsolete, None)
        pf.params[key] = profile
    # Bypass the archived solo-yaw / loaded-affine wrappers only for this option.
    pf.predict_to = lambda t: OwnCamLocalizer.predict_to(pf, t)
    pf._motion_params = lambda: pf.params['motion_loaded' if pf.load.loaded else 'motion']
    pf.real_v7_motion = copy.deepcopy(model)


class Runtime(CameraRuntime):
    def __init__(self, *args, min_wheel_cmd='off', dead_reckoning='off', motion_model=None, **kwargs):
        if min_wheel_cmd not in ('off', 'real_v1') or dead_reckoning not in ('off', 'v7_diag_v1'):
            raise ValueError('unsupported real output option')
        if dead_reckoning != 'off' and (min_wheel_cmd == 'off' or motion_model is None):
            raise ValueError('v7 motion requires real output and a frozen model')
        super().__init__(*args, **kwargs)
        self.real_options = dict(min_wheel_cmd=min_wheel_cmd, dead_reckoning=dead_reckoning)
        self.real_pulse_until = None
        self.real_observe_until = -float('inf')
        self.real_output_rows = []
        if dead_reckoning != 'off':
            install_motion(self.pose.provider.loc._pf, motion_model)

    def step(self, now):
        if self.real_options['min_wheel_cmd'] == 'off':
            return super().step(now)
        if self.terminal:
            return super().step(now)
        if self.real_pulse_until is not None:
            if now < self.real_pulse_until-1e-8:
                return []
            self.real_pulse_until = None
            self.real_observe_until = now+.10
            return [(self.robot_id, {'kind': 'hold'})]
        if now < self.real_observe_until-1e-8:
            return []
        rows = super().step(now)
        out = []
        for rid, requested in rows:
            issued = primitive(requested, 'real_v1')
            if issued is not requested:
                self.real_output_rows.append(dict(t=now, requested=copy.deepcopy(requested), issued=copy.deepcopy(issued)))
                self.real_pulse_until = now+issued['duration_s']
            out.append((rid, issued))
        return out

    def record(self):
        out = super().record()
        if any(v != 'off' for v in self.real_options.values()):
            out['real_output'] = dict(options=self.real_options, transformations=self.real_output_rows,
                                     strategy='dominant body axis; bounded REAL pulse; fresh post-stop frame')
            pf = self.pose.provider.loc._pf
            if hasattr(pf, 'real_v7_motion'):
                out['real_output']['motion_model'] = pf.real_v7_motion
        return out
