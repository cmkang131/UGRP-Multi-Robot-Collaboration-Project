"""DEV range-stationarity fallback; own readings and issued commands only.

This is an increment-level ZUPT hypothesis, not a full inertial ZUPT filter.
A single echo cannot identify a wall or distinguish a co-moving obstacle.
Only unloaded SEARCH arm posture is admitted (the sonar can see our cargo).
"""
from collections import deque
import math

from harness.active_camera import SEARCH
from harness.range_provider import RangeReport, source_label
from harness.ultrasonic_model import DEFAULT_SPEC

OPTION = 'rgb_vo_us_v1'
PARAMS = dict(window_frames=5, max_gap_s=.25, max_age_s=.12,
              max_range_m=.5, spread_sigma=3., min_expected_m=.02,
              expected_noise_ratio=2., max_yaw_rad=.02)


class RangeStall:
    def __init__(self):
        self.frames = deque(maxlen=PARAMS['window_frames'])
        self.direction = None
        self.max_gap_s = PARAMS['max_gap_s']

    def reset(self):
        self.frames.clear()

    def command(self, row):
        direction = (row.get('forward', 0.), row.get('left', 0.), row.get('turn', 0.))
        if row['kind'] not in ('drive', 'mecanum') or not (direction[0] > 0 and direction[1:] == (0., 0.)):
            direction = None
        if direction is None or direction != self.direction:
            self.reset()
        self.direction = direction

    def observe(self, *, t, report, servo, delta, measured, rgb_motion=False):
        row = dict(status='unavailable', stationary=False, samples=0)

        def reject(reason):
            self.reset()
            return {**row, 'status': reason}

        if measured:
            return reject('vo_available')
        if rgb_motion:
            return reject('rgb_motion_veto')
        if self.direction is None or delta[0] <= 1e-6 or abs(delta[2]) > PARAMS['max_yaw_rad']:
            return reject('not_forward')
        if any(int(servo.get(k, -1)) != v for k, v in SEARCH.items() if k != 6):
            return reject('arm_or_load_excluded')
        if not isinstance(report, RangeReport):
            return reject('no_reading')
        values = (report.t_meas, report.range_m, report.sigma_m)
        if any(v is None or not math.isfinite(v) for v in values):
            return reject('invalid_reading')
        if not report.valid or report.status != 'ok' or report.source != source_label():
            return reject('invalid_reading')
        age = t-report.t_meas
        r = report.range_m
        if not 0 <= age <= PARAMS['max_age_s']+1e-8:
            return reject('stale_or_future')
        if not DEFAULT_SPEC.min_range_m <= r <= DEFAULT_SPEC.max_range_m:
            return reject('out_of_range')
        if r > PARAMS['max_range_m']:
            return reject('not_near')
        if self.frames and (report.t_meas <= self.frames[-1]['t'] or
                            report.t_meas-self.frames[-1]['t'] > self.max_gap_s+1e-8):
            return reject('duplicate_or_gap')
        self.frames.append(dict(t=report.t_meas, r=r, expected=float(delta[0]), yaw=abs(float(delta[2]))))
        # The first sample is the window anchor; its preceding motion is outside it.
        window = list(self.frames)
        spread = max(x['r'] for x in window)-min(x['r'] for x in window)
        noise = PARAMS['spread_sigma']*max(DEFAULT_SPEC.sigma_m(x['r']) for x in window)
        expected = sum(x['expected'] for x in window[1:])
        stationary = (len(window) == PARAMS['window_frames'] and spread <= noise and
                      expected >= max(PARAMS['min_expected_m'], PARAMS['expected_noise_ratio']*noise) and
                      sum(x['yaw'] for x in window[1:]) <= PARAMS['max_yaw_rad'])
        return dict(status='stationary_range' if stationary else 'unconfirmed', stationary=stationary,
                    samples=len(window), t_meas=report.t_meas, age_s=age, range_m=r,
                    spread_m=spread, noise_bound_m=noise, expected_m=expected)
