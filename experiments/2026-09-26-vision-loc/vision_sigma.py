"""Optional VIS4 covariance-report calibration. No files, truth, or RNG inputs.

This head leaves the particle posterior and estimated mean untouched. The fitted
variance floor and stale growth represent errors missing from that posterior;
they are NOT extra diffusion of particles or proof of localization recovery.
sigma_xy is sqrt(trace(Pxy)). Use the full covariance for exact NEES offline.
"""
from __future__ import annotations

import math
from collections.abc import Mapping

import numpy as np

STATES = ('unloaded_settled', 'unloaded_unsettled', 'loaded_settled', 'loaded_unsettled')
VAR_FLOOR = 1e-10


def state_key(loaded: bool, settled: bool) -> str:
    if not isinstance(loaded, (bool, np.bool_)) or not isinstance(settled, (bool, np.bool_)):
        raise ValueError('load and settle state must be own-command booleans')
    return ('loaded' if loaded else 'unloaded') + ('_settled' if settled else '_unsettled')


def _number(value, name, minimum=0.):
    if isinstance(value, (bool, np.bool_)) or not isinstance(value, (int, float, np.number)):
        raise ValueError(f'{name} must be numeric')
    value = float(value)
    if not math.isfinite(value) or value < minimum:
        raise ValueError(f'{name} must be finite and >= {minimum}')
    return value


def validate_sigma(config: Mapping | None) -> dict:
    if config is None:
        return {'enabled': False}
    if not isinstance(config, Mapping) or set(config) - {'enabled', 'states', 'stale_envelope'}:
        raise ValueError('unknown sigma_v4 options')
    enabled = config.get('enabled', False)
    if not isinstance(enabled, bool):
        raise ValueError('sigma_v4.enabled must be boolean')
    if not enabled:
        if set(config) - {'enabled'}:
            raise ValueError('disabled sigma_v4 cannot carry ignored parameters')
        return {'enabled': False}
    states = config.get('states')
    envelope = config.get('stale_envelope')
    if not isinstance(envelope, bool) or not isinstance(states, Mapping) or set(states) != set(STATES):
        raise ValueError('enabled sigma_v4 needs all four states and stale_envelope boolean')
    result = {}
    for key in STATES:
        row = states[key]
        if not isinstance(row, Mapping) or set(row) != {'a', 'b_m2', 'q_m2_s'}:
            raise ValueError(f'invalid sigma state {key}')
        result[key] = {k: _number(v, f'{key}.{k}', VAR_FLOOR if k == 'a' else 0.) for k, v in row.items()}
        if envelope and result[key]['q_m2_s'] <= 0.:
            raise ValueError('stale envelope requires positive growth in every state')
    return {'enabled': True, 'states': result, 'stale_envelope': envelope}


class VarianceCalibrator:
    def __init__(self, config=None, *, start_t=0.):
        self.config = validate_sigma(config)
        self.start_t = _number(start_t, 'start_t')
        self.t = None
        self.last_scan_t = None
        self.variance = None

    def step(self, raw_variance, t, last_scan_t, loaded, settled):
        """Causal reporting step; a newer applied scan is the only reset event."""
        raw = _number(raw_variance, 'raw_variance')
        t = _number(t, 'time')
        key = state_key(loaded, settled)
        if t < self.start_t or (self.t is not None and t < self.t):
            raise ValueError('backwards time')
        if last_scan_t is not None:
            last_scan_t = _number(last_scan_t, 'last_scan_t')
            if last_scan_t > t + 1e-7:
                raise ValueError('future scan')
        if self.last_scan_t is not None and (last_scan_t is None or last_scan_t < self.last_scan_t):
            raise ValueError('applied scan time cannot regress')
        fresh = last_scan_t is not None and (self.last_scan_t is None or last_scan_t > self.last_scan_t)
        if self.config['enabled']:
            p = self.config['states'][key]
            age = max(0., t - (last_scan_t if last_scan_t is not None else self.start_t))
            value = p['a'] * max(raw, VAR_FLOOR) + p['b_m2'] + p['q_m2_s'] * age
            if self.config['stale_envelope'] and self.t is not None and not fresh:
                value = max(value, self.variance + p['q_m2_s'] * (t - self.t))
        else:
            value = raw
        self.t, self.last_scan_t, self.variance = t, last_scan_t, value
        return value

    def report(self, estimate, *, t, last_scan_t, loaded, settled):
        """Return a new calibrated report; never alter the caller's raw estimate."""
        if not estimate.get('initialized'):
            return estimate
        if not self.config['enabled']:
            # OFF still records the raw fields, without recomputing covariance
            # or advancing the calibration clock/state.
            return {**estimate, 'raw_cov': estimate['cov'], 'raw_std_xy_m': estimate['std_xy_m']}
        raw_cov = np.asarray(estimate['cov'], float)
        if (raw_cov.shape != (3, 3) or not np.isfinite(raw_cov).all()
                or not np.allclose(raw_cov, raw_cov.T, atol=1e-8, rtol=0.)
                or np.linalg.eigvalsh(raw_cov).min() < -2e-8):
            raise ValueError('raw covariance must be finite symmetric PSD')
        # M1 rounds covariance to 8 decimals; remove only round-off negatives.
        eig, vec = np.linalg.eigh((raw_cov + raw_cov.T) / 2.)
        cov = (vec * np.maximum(eig, 0.)) @ vec.T
        raw_trace = float(np.trace(cov[:2, :2]))
        value = self.step(raw_trace, t, last_scan_t, loaded, settled)
        p = self.config['states'][state_key(loaded, settled)]
        scale = np.diag([math.sqrt(p['a']), math.sqrt(p['a']), 1.])
        cov = scale @ cov @ scale
        extra = max(0., value - float(np.trace(cov[:2, :2])))
        cov[:2, :2] += np.eye(2) * extra / 2.
        out = dict(estimate)
        out.update(raw_cov=raw_cov.tolist(), raw_std_xy_m=estimate['std_xy_m'],
                   cov=cov.tolist(), std_xy_m=math.sqrt(float(np.trace(cov[:2, :2]))),
                   sigma_calibration_state=state_key(loaded, settled),
                   sigma_calibration='v4_report_only',
                   radius95_xy_m=math.sqrt(-2.*math.log(.05)*float(np.linalg.eigvalsh(cov[:2, :2]).max())))
        return out


def xy_nees(error_xy, covariance_xy):
    """Exact 2D NEES for offline evaluation with a recorded positive-definite C."""
    e, c = np.asarray(error_xy, float), np.asarray(covariance_xy, float)
    if (e.shape != (2,) or c.shape != (2, 2) or not np.isfinite(e).all() or not np.isfinite(c).all()
            or not np.allclose(c, c.T, atol=1e-12, rtol=0.) or np.linalg.eigvalsh(c).min() <= 0.):
        raise ValueError('exact NEES requires finite error and positive-definite covariance')
    return float(e @ np.linalg.solve(c, e))
