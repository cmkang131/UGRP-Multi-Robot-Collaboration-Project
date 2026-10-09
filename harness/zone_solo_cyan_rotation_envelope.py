"""Own-RGB feedback envelope for optional S2 active rotations, default off.

Nav2 Spin (jazzy spin.cpp 110--139) accumulates measured relative yaw and
reserves stopping distance. Here the feedback is calibrated ground-plane LK
and rigid SE2 (existing Seegmiller pipeline), not TF, PF yaw or issued yaw.
Finite PWM pulses cannot decelerate continuously: reserve a complete pulse
including its coast, and cancel this optional action if it will not fit.
The confidence envelope is an empirical safeguard, not a formal plant bound.
"""
import copy
import math
import numpy as np

from harness.zone_solo_cyan_bias_tempering import closure
from harness.zone_solo_cyan_progress_noise import pair, PARAMS as FLOW
from harness.zone_solo_cyan_flow_fusion import pitch_uncertainty
from harness.zone_solo_cyan_pulse_cal import profile_key

OPTION = 'ground_yaw_bound_v1'
PARAMS = dict(max_abs_deg=90., confidence_sigma=3.,
              frame_max_age_s=FLOW['before_max_age_s'],
              uncertainty_accumulation='sum of interval sigma, no independence assumption',
              unknown_action='cancel optional rotation; hold, then mission replan',
              pulse_reserve='max fixed full pulse curve plus 3sigma, observed pulse plus uncertainty',
              gt_inputs=False)


def yaw_measurement(before, after, cm, pose, table):
    obs = pair(before, after, cm, pose, table, metric_observation=True)
    if obs['status'] != 'measured':
        return obs
    # Reuse the existing conservative +/-2.8deg common and +/-0.9deg
    # independent pitch model; unlike slip's radial-only correction, retain
    # its yaw component here. No camera/pose truth or online calibration.
    uncertain = pitch_uncertainty(obs, cm)
    return dict(status='measured', delta_yaw=float(obs['delta'][2]),
                sigma_yaw=math.sqrt(max(0., uncertain['covariance'][2][2])),
                inliers=obs['inliers'], cells=obs['cells'])


class RotationEnvelope:
    def __init__(self):
        self.yaw = 0.
        self.sigma_sum = 0.
        self.observed_pulse_bound = 0.
        self.rows = []

    def update(self, observation):
        if observation.get('status') != 'measured':
            return False
        d, s = observation['delta_yaw'], observation['sigma_yaw']
        if not np.isfinite([d, s]).all() or s < 0:
            return False
        self.yaw += d
        self.sigma_sum += s
        self.observed_pulse_bound = max(self.observed_pulse_bound,
            abs(d) + PARAMS['confidence_sigma'] * s)
        return True

    def permit(self, profile):
        curve = np.asarray(profile['mean_curve'])[:, 2]
        reserve = max(float(np.max(abs(curve))) + PARAMS['confidence_sigma'] *
            math.sqrt(profile['prediction_variance'][2]), self.observed_pulse_bound)
        sign = np.sign(profile['mean_delta'][2])
        # Full coast is in the stored pulse curve. Test both the current
        # extent and the next endpoint; the same rule covers the return leg.
        extent = max(abs(self.yaw), abs(self.yaw + sign * reserve))
        upper = extent + PARAMS['confidence_sigma'] * self.sigma_sum
        row = dict(yaw_deg=math.degrees(self.yaw),
            uncertainty_deg=math.degrees(PARAMS['confidence_sigma'] * self.sigma_sum),
            reserve_deg=math.degrees(reserve), upper_deg=math.degrees(upper),
            permitted=bool(upper <= math.radians(PARAMS['max_abs_deg'])))
        self.rows.append(row)
        return row


def attach(runtime, *, active_rotation_guard='off'):
    if active_rotation_guard == 'off':
        return runtime
    if active_rotation_guard != OPTION:
        raise ValueError('unknown active_rotation_guard')
    if not hasattr(runtime, 'active_observation'):
        raise ValueError('active observation attachment required')
    old_step, old_frames, old_record = runtime.step, runtime.on_frames, runtime.record
    active = closure(old_step)['state']
    state = dict(event=None, last=None, anchor=None, guard=None, pose=None, cm=None)
    audit = dict(option=OPTION, parameters=copy.deepcopy(PARAMS), events=[], gt_inputs=False)

    def frames(now, images):
        result = old_frames(now, images)
        obs, rgb = images[runtime.robot_id]
        state['last'] = (float(obs['sim_time']), rgb.copy())
        return result

    def cancel(e, now, reason):
        if not e.get('rotation_guard_stop'):
            e['rotation_guard_stop'] = dict(t=now, reason=reason)
            e['schedule'].clear()
            a = e['action']
            a['planned_added_s'] = a['added_s']
            from harness.zone_solo_cyan_active_observation import LIMITS
            a['added_s'] = min(a['added_s'], now-e['t'] +
                              LIMITS['settle_s'] + LIMITS['observation_wait_s'])
            audit['events'][-1]['stop'] = copy.deepcopy(e['rotation_guard_stop'])
        return [(runtime.robot_id, dict(kind='hold'))]

    def step(now):
        issued = old_step(now)
        e = active['event']
        if e is None:
            state['event'] = None
            return issued
        if state['event'] is not e:
            state.update(event=e, anchor=None, guard=RotationEnvelope(),
                         pose=dict(runtime.servo),
                         cm=runtime.pose.provider.loc._pf.column_model_for(runtime.servo))
            audit['events'].append(dict(t=now, checks=state['guard'].rows, observations=[]))
        moving = [(rid, a) for rid, a in issued if a.get('kind') == 'mecanum']
        if not moving:
            return issued
        if e.get('rotation_guard_stop'):
            return [(runtime.robot_id, dict(kind='hold'))]
        last = state['last']
        if last is None or not -1e-8 <= now-last[0] <= PARAMS['frame_max_age_s']+1e-8:
            return cancel(e, now, 'missing_fresh_own_rgb')
        if dict(runtime.servo) != state['pose']:
            return cancel(e, now, 'commanded_camera_changed')
        anchor = state['anchor'] or last
        try:
            measurement = yaw_measurement(anchor[1], last[1], state['cm'],
                                           state['pose'], runtime.flow.table)
        except (ValueError, np.linalg.LinAlgError, FloatingPointError):
            measurement = dict(status='unknown_numeric')
        audit['events'][-1]['observations'].append(dict(t=now, from_t=anchor[0], **measurement))
        if not state['guard'].update(measurement):
            return cancel(e, now, measurement['status'])
        state['anchor'] = last
        for _, command in moving:
            p = runtime.pulse_profiles[profile_key(command, runtime.pose.provider.loc._pf.load.loaded)]
            if not state['guard'].permit(p)['permitted']:
                return cancel(e, now, 'measured_yaw_plus_uncertainty_and_stop_reserve')
        return issued

    def record():
        out = old_record()
        out['active_rotation_guard'] = copy.deepcopy(audit)
        return out

    runtime.on_frames, runtime.step, runtime.record = frames, step, record
    runtime.rotation_guard_audit = audit
    return runtime
