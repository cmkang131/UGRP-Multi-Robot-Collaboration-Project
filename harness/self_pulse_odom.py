"""Own issued-command finite-pulse odometry, no pose/scene/GT observations.

v122 calibration and profile_key/response copied from PR406 45b0c173.
Prediction mean: same .05 s initial-pulse-frame increments and stopping tail.
Uncertainty: original per-profile variance, independent time-fraction increments
propagated analytically instead of sampling PF particles. See experiment README.
"""
from functools import lru_cache
import hashlib
import json
import math
from pathlib import Path
import numpy as np
from harness.self_map_prob import V7CommandOdometry, wrap
from harness.self_map_csm import CSMOptions

OPTION = 's2_pulse_v122'
MODEL = Path(__file__).with_name('data')/'s2_motion_v7_pulse_cal_v122.json'
MODEL_SHA256 = '2245bb9fdcb69d872893dd6ffafb57151750dd42916394a287b6d10bab11d69d'
AXES = ('forward','left','turn')


def profile_key(action, loaded):
    u = [float(action.get(k,0.)) for k in AXES]
    if sum(v!=0 for v in u)!=1:
        raise ValueError('calibrated motion requires one axis')
    axis = int(np.argmax(np.abs(u)))
    return f"{int(loaded)}:{AXES[axis]}:{u[axis]:.2f}:{float(action['duration_s']):.2f}"


def response(profile, t):
    curve=np.asarray(profile['mean_curve'])
    return np.array([np.interp(t,profile['times'],curve[:,i]) for i in range(3)])


@lru_cache(maxsize=1)
def model():
    raw = MODEL.read_bytes()
    if hashlib.sha256(raw).hexdigest() != MODEL_SHA256:
        raise ValueError('PULSE_CALIBRATION_CHANGED')
    return json.loads(raw)


def command_odometry(start_time=0., *, motion_model='off'):
    if motion_model == 'off':
        return V7CommandOdometry(start_time)
    from harness.self_pulse_rotation import OPTION as ROTATION, RotationPulseOdometry
    if motion_model == ROTATION:
        return RotationPulseOdometry(start_time)
    if motion_model != OPTION:
        raise ValueError('UNKNOWN_MOTION_MODEL')
    return PulseOdometry(start_time)


class PulseOdometry:
    def __init__(self, start_time=0.):
        self.t = float(start_time)
        self._pose = np.zeros(3)
        self.servo, self.servo_since, self.has_servo = {}, self.t, False
        self.loaded, self.active = False, None
        self.covariance = CSMOptions().floor()
        self.step_callback = None
        self.profiles = model()['profiles']

    @property
    def pose(self):
        return tuple(map(float, self._pose))

    def advance(self, t):
        t = float(t)
        if not math.isfinite(t) or t < self.t-1e-8:
            raise ValueError('SELF_MAP_NON_MONOTONIC_TIME')
        while self.t < t-1e-9:
            dt = min(.05, t-self.t)
            if self.active is not None:
                started, p = self.active
                a, b = max(0., self.t-started), max(0., self.t+dt-started)
                va, vb = response(p, a), response(p, b)
                delta = vb-va
                c, s = math.cos(va[2]), math.sin(va[2])
                delta[:2] = np.array([[c,s],[-s,c]])@delta[:2]
                fraction = max(0., min(b,p['times'][-1])-min(a,p['times'][-1]))/p['times'][-1]
                variance = np.asarray(p['prediction_variance'])*fraction
                c, s = math.cos(self._pose[2]), math.sin(self._pose[2])
                R = np.array([[c,-s,0],[s,c,0],[0,0,1.]])
                world_delta = R@delta
                F = np.eye(3)
                F[:2,2] = [-world_delta[1],world_delta[0]]
                self.covariance = F@self.covariance@F.T+R@np.diag(variance)@R.T
                self._pose += world_delta
                self._pose[2] = wrap(self._pose[2])
                if self.step_callback is not None:
                    self.step_callback(delta, variance)
                if b >= p['times'][-1]-1e-9:
                    self.active = None
            self.t += dt
        self.t = max(self.t,t)
        return self.pose

    def command(self, row):
        kind, t = row['kind'], float(row['t'])
        if kind not in ('initial_servo_command','arm','look','mecanum','drive','hold','stop'):
            raise ValueError('SELF_MAP_UNKNOWN_COMMAND')
        self.advance(t)
        # A calibrated pulse includes its tail. Unknown early interruption has
        # no fixed curve; fail explicitly instead of inventing a continuation.
        if self.active is not None and t < self.active[0]+self.active[1]['duration_s']-1e-8:
            raise ValueError('UNCALIBRATED_EARLY_INTERRUPTION')
        before = self.servo.copy()
        if kind == 'initial_servo_command':
            self.servo = {int(k):int(v) for k,v in row['pulses'].items()}
        elif kind == 'arm':
            self.servo[int(row['servo_id'])] = int(row['pulse'])
        elif kind == 'look':
            self.servo[6] = int(row['pan_pulse'])
        if self.servo != before:
            self.servo_since = self.t
        self.has_servo = bool(self.servo)
        self.loaded = self.servo.get(1,2000) <= 1600
        if kind in ('mecanum','drive') and any(row.get(k,0) for k in AXES):
            key = profile_key(row,self.loaded)
            if key not in self.profiles:
                raise ValueError('UNCALIBRATED_PULSE '+key)
            p = self.profiles[key]
            # Reject values which would only match because of key rounding.
            if (float(row['duration_s']) != p['duration_s'] or
                    float(row[p['axis']]) != p['u']):
                raise ValueError('UNCALIBRATED_PULSE_ROUNDING')
            self.active = (self.t,p)

    def correct(self, pose, covariance):
        self._pose = np.asarray(pose,dtype=float).copy()
        self._pose[2] = wrap(self._pose[2])
        self.covariance = np.asarray(covariance,dtype=float).copy()
