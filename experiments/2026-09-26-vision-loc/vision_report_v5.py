"""Opt-in, observation-only VIS5 report head. No GT, files, simulator or RNG.

The yaw grid is a local MAP refiner of an already assimilated scan, not another
independent Bayesian update. The particle prediction and XY mean stay untouched.
All uncertainty claims require empirical offline calibration.
"""
from __future__ import annotations

import math
from collections.abc import Mapping

import numpy as np

import vision_loc as vl

STATES = ('unloaded_settled', 'unloaded_unsettled', 'loaded_settled', 'loaded_unsettled')
GRID = np.radians(np.arange(-6., 6.01, .5))
Q = math.radians(.1)**2


def state_key(loaded, settled):
    if not isinstance(loaded, bool) or not isinstance(settled, bool):
        raise ValueError('own state must be boolean')
    return ('loaded' if loaded else 'unloaded') + ('_settled' if settled else '_unsettled')


def finite(x, lo=0., hi=math.inf):
    if isinstance(x, bool) or not isinstance(x, (int, float)) or not math.isfinite(x) or not lo <= x <= hi:
        raise ValueError('invalid finite parameter')
    return float(x)


def validate(config):
    if config is None:
        return {'enabled': False}
    if not isinstance(config, Mapping) or set(config) - {'enabled', 'refine_yaw', 'yaw_states', 'mode_threshold'}:
        raise ValueError('unknown VIS5 options')
    if not isinstance(config.get('enabled', False), bool):
        raise ValueError('enabled must be boolean')
    if not config.get('enabled', False):
        if set(config) - {'enabled'}:
            raise ValueError('disabled VIS5 cannot carry active parameters')
        return {'enabled': False}
    if not isinstance(config.get('refine_yaw', False), bool):
        raise ValueError('refine_yaw must be boolean')
    out = {'enabled': True, 'refine_yaw': config.get('refine_yaw', False), 'yaw_states': None,
           'mode_threshold': None}
    states = config.get('yaw_states')
    if states is not None:
        if not isinstance(states, Mapping) or set(states) != set(STATES):
            raise ValueError('all four yaw states required')
        out['yaw_states'] = {}
        for key, values in states.items():
            if not isinstance(values, Mapping) or set(values) != {'a', 'b_rad2'}:
                raise ValueError('yaw state needs a,b_rad2')
            out['yaw_states'][key] = {'a': finite(values['a'], .0625, 256.),
                                      'b_rad2': finite(values['b_rad2'], 0., math.radians(16)**2 + 1e-12)}
    if config.get('mode_threshold') is not None:
        out['mode_threshold'] = finite(config['mode_threshold'], 0., 10.)
    return out


def edge_residual(vb, vt, obs, measurement):
    """Clipped standardized edge/interval distance; off-screen endpoints stay censored."""
    terms = []
    for predicted, kind, lo, hi in ((vb, obs.b_kind, obs.b_lo, obs.b_hi),
                                    (vt, obs.t_kind, obs.t_lo, obs.t_hi)):
        if predicted is vt and not measurement.get('use_top_edge', True):
            continue
        valid = (kind != vl.NONE) & np.isfinite(predicted) & np.isfinite(lo) & np.isfinite(hi)
        if valid.any():
            delta = np.maximum(np.maximum(lo[valid] - predicted[valid], predicted[valid] - hi[valid]), 0.)
            terms.extend(np.minimum(delta / float(measurement['sigma_px']), 10.).tolist())
    return (None if not terms else float(np.sqrt(np.mean(np.square(terms))))), len(terms)


def features(localizer, est, obs, pose, *, measured, ess_pre):
    """Uses only a saved/current student estimate, own scan, own arm and static map."""
    if not measured or obs is None or ess_pre is None:
        return {'available': False, 'yaw_delta': 0.}
    n = localizer.n
    finite(float(ess_pre), 0., float(n))
    mean = np.array([est['x'], est['y'], est['yaw'] - est.get('pan_yaw_offset', 0.)])
    poses = np.tile(mean, (len(GRID), 1)); poses[:, 2] += GRID
    vb, vt = localizer.expected(poses, pose)
    measurement = {**localizer.measurement, 'use_top_edge': localizer.obs_params['use_top_edge']}
    ll, n_terms = vl.column_loglik(vb, vt, obs, measurement, per_column=True)
    center = len(GRID)//2
    residual, valid = edge_residual(vb[center], vt[center], obs, measurement)
    sd = np.clip(est['std_yaw_rad'], math.radians(.5), math.radians(3.))
    objective = ll - .5*(GRID/sd)**2
    # Stable zero-first tie break; flat/edge maxima carry no yaw correction.
    best = min(range(len(GRID)), key=lambda j: (-float(objective[j]), abs(float(GRID[j])), j))
    span = float(np.ptp(ll))
    delta = float(GRID[best]) if span >= .25 and 0 < best < len(GRID)-1 else 0.
    return {'available': residual is not None and n_terms > 0, 'yaw_delta': delta,
            'residual_rms_sigma': residual, 'residual_terms': valid, 'll_range': span,
            'grid_edge': best in (0, len(GRID)-1), 'ess_ratio': float(ess_pre/n),
            'score': None if residual is None else max(residual/3., 1. - ess_pre/n)}


class ReportHead:
    def __init__(self, config=None):
        self.config = validate(config)
        self.t = None
        self.last_scan = None
        self.yaw_variance = None
        self.high = self.good = 0
        self.alarm = False
        self._last_input = self._last_output = None

    def step(self, *, raw_xy_var, raw_yaw_var, t, last_scan, loaded, settled, observation):
        key = state_key(loaded, settled)
        for x in (raw_xy_var, raw_yaw_var, t):
            finite(x)
        if last_scan is not None:
            finite(last_scan, 0., t + 1e-8)
        signature = (raw_xy_var, raw_yaw_var, t, last_scan, loaded, settled, tuple(sorted(observation.items())))
        if self.t is not None and t == self.t and signature == self._last_input:
            return dict(self._last_output)
        # Legacy captures can contain distinct estimates at the same SIM time.
        # Keep them all; unchanged last_scan is not fresh evidence, dt remains 0.
        if self.t is not None and (t < self.t or (self.last_scan is not None and
                (last_scan is None or last_scan < self.last_scan))):
            raise ValueError('backwards clock or applied observation')
        fresh = last_scan is not None and (self.last_scan is None or last_scan > self.last_scan)
        available = bool(observation.get('available', False)) and fresh
        threshold = self.config.get('mode_threshold')
        if available and threshold is not None:
            score = finite(observation['score'], 0., 10.)
            if score > threshold:
                self.high += 1; self.good = 0
                if self.high >= 3:
                    self.alarm = True
            else:
                self.high = 0; self.good += 1
                if self.good >= 5:
                    self.alarm = False
        yv = raw_yaw_var
        states = self.config.get('yaw_states')
        if states:
            coeff = states[key]
            age = max(0., t - (last_scan if last_scan is not None else (self.t if self.t is not None else t)))
            yv = coeff['a']*raw_yaw_var + coeff['b_rad2'] + Q*age
            if self.t is not None and not fresh:
                yv = max(yv, self.yaw_variance + Q*(t-self.t))
        xv = raw_xy_var
        if self.alarm:
            xv = max(xv, .09); yv = max(yv, math.radians(10)**2)
        delta = observation.get('yaw_delta', 0.) if available and self.config.get('refine_yaw') else 0.
        finite(float(delta), -math.radians(6), math.radians(6))
        out = {'xy_var': xv, 'yaw_var': yv, 'yaw_delta': delta, 'mode_alarm': self.alarm,
               'observation_available': available, 'state': key}
        self.t, self.last_scan, self.yaw_variance = t, last_scan, yv
        self._last_input, self._last_output = signature, dict(out)
        return out

    def report(self, est, *, t, last_scan, loaded, settled, observation):
        if not self.config['enabled'] or not est.get('initialized'):
            return est
        raw = np.asarray(est['cov'], float)
        if raw.shape != (3, 3) or not np.isfinite(raw).all() or not np.allclose(raw, raw.T, atol=1e-10):
            raise ValueError('invalid covariance')
        if np.linalg.eigvalsh(raw).min() < -1e-10:
            raise ValueError('non-PSD covariance')
        xv, yv = max(float(np.trace(raw[:2, :2])), 0.), max(float(raw[2, 2]), 0.)
        value = self.step(raw_xy_var=xv, raw_yaw_var=yv, t=float(t), last_scan=last_scan,
                          loaded=loaded, settled=settled, observation=observation)
        scale = math.sqrt(value['yaw_var']/yv) if yv > 0 else 1.
        D = np.diag([1., 1., scale]); cov = D @ raw @ D
        if yv == 0:
            cov[2, 2] = value['yaw_var']
        cov[:2, :2] += np.eye(2)*(value['xy_var']-xv)/2.
        out = dict(est)
        out.update(cov=cov.tolist(),
                   yaw=math.atan2(math.sin(est['yaw']+value['yaw_delta']), math.cos(est['yaw']+value['yaw_delta'])),
                   std_xy_m=math.sqrt(value['xy_var']), std_yaw_rad=math.sqrt(value['yaw_var']),
                   raw_std_yaw_rad=est['std_yaw_rad'], vis5={**value, 'observation': observation},
                   radius95_xy_m=math.sqrt(5.991464547*max(0., float(np.linalg.eigvalsh(cov[:2,:2]).max()))))
        return out
