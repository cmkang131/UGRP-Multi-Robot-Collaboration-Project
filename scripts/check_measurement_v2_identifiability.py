"""Offline input design, not a physics run or fitted calibration product.

Use the v2 stop-fit ODE and VIS4 exact integral. Compare practical gain/drive
tau separation at #346's diagnostic candidates, including profiled stop tau.
The 0.1 mm residual floor is a design assumption, not an IID noise estimate.
"""
from __future__ import annotations

import argparse
import importlib.util
import json
from pathlib import Path

import numpy as np

ROOT = Path(__file__).resolve().parents[1]
INTEGRAL = 'experiments/2026-09-26-vision-loc/vision_motion.py'
CANDIDATES = {'forward': (1.78459, 1.44, .08), 'left': (2.40680, 3., .05)}
RESIDUAL_FLOOR_M = .0001


def prbs31():
    """One maximal-length x^5+x^2+1 sequence, initial state 11111."""
    bits = [1] * 5
    for i in range(26):
        bits.append(bits[i + 2] ^ bits[i])
    return [2 * b - 1 for b in bits]


def design_segments():
    """Proposed axis sequence, established offline BEFORE writing the config."""
    segments = []
    for magnitude in (.01, .02, .03):
        for sign in (1, -1):
            segments += [(15., sign * magnitude), (1., 0.)]
    segments += [(.5, .02 * bit) for bit in prbs31()]
    return segments + [(2.5, 0.)]


def response(segments, dt, tau, stop_tau):
    """Exact integrated velocity at sample times, vectorized over tau grid.

    As in v2, stop has a separate nuisance time constant. Sampling includes
    t=0 and the terminal coast; every command boundary lies on the sample grid.
    """
    spec = importlib.util.spec_from_file_location('measurement_v2_integral', ROOT / INTEGRAL)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    lag_integral = module.lag_integral
    shape = np.broadcast_shapes(np.shape(tau), np.shape(stop_tau))
    velocity, position = np.zeros(shape), np.zeros(shape)
    rows = [position.copy()]
    for duration, command in segments:
        n = round(duration / dt)
        if abs(n * dt - duration) > 1e-8:
            raise ValueError('sample grid must include command boundaries')
        for _ in range(n):
            velocity, delta = lag_integral(velocity, command, dt, tau if command else stop_tau)
            position = position + delta
            rows.append(position.copy())
    return np.asarray(rows)


def assess(segments, dt, gain, tau, stop_tau, *, independent_windows=None):
    """Each explicit fit window starts at x=v=0 and retains its initial sample.

    Generic `segments` remain one continuous trajectory (including v2). v1
    must supply its two real fit windows; never infer resets from command signs.
    """
    if independent_windows is not None and segments is not None:
        raise ValueError('supply a trajectory OR independent windows')
    windows = [segments] if independent_windows is None else independent_windows
    if not windows or any(not window for window in windows):
        raise ValueError('missing fit windows')
    def sampled(td, ts):
        return np.concatenate([response(window, dt, td, ts) for window in windows], axis=0)
    observed = gain * sampled(tau, stop_tau)
    # Log-parameter sensitivities make gain and seconds dimensionless.
    eps = 1e-4
    d_tau = gain * (sampled(tau * np.exp(eps), stop_tau)
                    - sampled(tau * np.exp(-eps), stop_tau)) / (2 * eps)
    jacobian = np.column_stack((observed, d_tau)) / RESIDUAL_FLOOR_M
    fisher = jacobian.T @ jacobian
    eig = np.linalg.eigvalsh(fisher)
    taus = np.unique(np.r_[np.geomspace(.05, 100., 241), tau, tau * .8, tau * 1.2])
    stops = np.array([.03, .05, .08, .12, .2, .3, .44, 1.])
    td, ts = np.meshgrid(taus, stops, indexing='ij')
    x = sampled(td.ravel(), ts.ravel())
    gains = observed @ x / np.sum(x * x, axis=0)
    rms = np.sqrt(np.mean((x * gains - observed[:, None]) ** 2, axis=0))
    far = np.abs(td.ravel() / tau - 1) >= .199999
    j = np.flatnonzero(far)[np.argmin(rms[far])]
    equivalent = rms <= RESIDUAL_FLOOR_M
    return {'samples': len(observed), 'sample_period_s': dt, 'independent_windows': len(windows),
            'initial_state_per_window': {'position_m': 0., 'velocity_m_s': 0.},
            'samples_per_drive_tau': tau / dt,
            'fisher_log_gain_log_tau': fisher.tolist(), 'fisher_condition': float(eig[-1] / eig[0]),
            'fisher_min_eigenvalue': float(eig[0]),
            'profiled_20pct_tau_alternative': {'gain': float(gains[j]), 'tau_s': float(td.ravel()[j]),
                                              'stop_tau_s': float(ts.ravel()[j]), 'rms_m': float(rms[j])},
            'within_residual_floor': {'gain_min': float(gains[equivalent].min()),
                                     'gain_max': float(gains[equivalent].max()),
                                     'tau_min_s': float(td.ravel()[equivalent].min()),
                                     'tau_max_s': float(td.ravel()[equivalent].max())},
            'practically_separated': bool(rms[j] > RESIDUAL_FLOOR_M * 5)}


def report(plan=None):
    result = {'status': 'SYNTHETIC_DESIGN_ONLY', 'model': 'dv/dt=(gain*u-v)/tau_drive_or_stop',
              'residual_floor_m': RESIDUAL_FLOOR_M, 'v1': {}, 'v2': {},
              'limitation': 'conditional on first-order model and #346 drive candidates; not physical identification; stop tau is a profiled nuisance, not qualified at 20 Hz'}
    for axis, (gain, tau, stop) in CANDIDATES.items():
        # The old fit uses two independent 4 s windows. Opposite signs only
        # repeat the same shape, so duplicate it for the information matrix.
        legacy = [[(1., .03), (3., 0.)], [(1., -.03), (3., 0.)]]
        segments = design_segments() if plan is None else [
            (s['duration_s'], s['value']) for s in plan['segments'] if s['axis'] == axis]
        result['v1'][axis] = assess(None, .2, gain, tau, stop, independent_windows=legacy)
        result['v2'][axis] = assess(segments, .05, gain, tau, stop)
    result['passed'] = all(not x['practically_separated'] for x in result['v1'].values()) and all(
        x['practically_separated'] and x['samples_per_drive_tau'] >= 10 for x in result['v2'].values())
    if plan is not None:
        from harness import final_environment_measurement_v2 as env
        static = env.parent.resolve(plan['map_id'])[0]
        positions = []
        for axis in plan['axes']:
            gain, tau, stop = CANDIDATES[axis]
            segments = [(plan['initial_hold_s'], 0.)] + [
                (s['duration_s'], s['value'] if s['axis'] == axis else 0.) for s in plan['segments']]
            positions.append(gain * response(segments, .05, tau, stop))
        xy = np.column_stack(positions) + plan['spawn_xy_yaw'][:2]
        gaps = [env.require_clearance(static, p, plan) for p in xy]
        result['nominal_clearance'] = {'minimum_m': min(gaps), 'xy_min_m': xy.min(axis=0).tolist(),
                                       'xy_max_m': xy.max(axis=0).tolist(),
                                       'scope': 'conditional prediction, not safety proof; private abort interlock required'}
        result['clearance_preflight'] = env.validate(plan, for_execution=False)['full_path']
        result['runnable'] = result['clearance_preflight']['admitted']
    return result


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--config', type=Path)
    parser.add_argument('--output', type=Path, required=True)
    args = parser.parse_args()
    value = report(json.loads(args.config.read_text()) if args.config else None)
    with args.output.open('x') as stream:
        json.dump(value, stream, indent=2, allow_nan=False)
        stream.write('\n')
    print(json.dumps({'passed': value['passed'], 'output': str(args.output)}))
    return int(not value['passed'])


if __name__ == '__main__':
    raise SystemExit(main())
