"""B″ loaded 적합: 사전 고정 범위, 혼합 명령, 관측된 계단 지지.

B′ 수치 계산은 그대로 호출한다. c0 하한만 B″에서 가져오고, 실제 존재하는
양수 명령을 적합된 c0/u1과 비교한다. 낮은 명령을 미리 정지로 지정하지 않는다.
"""
from __future__ import annotations

import numpy as np
from scipy.optimize import least_squares

from scripts import fit_consumer_criterion_b as r4
from scripts import validate_consumer_criterion_b as b
from scripts.final_pair_calibration_motion import (
    split_data, increments, path_of, window_groups, verify_fit,
    budget_groups, minimum_noise, evaluate,
)


def deadband_support(data, profile, gate):
    support = {}
    for axis, name in enumerate(b.AXES):
        spans = data['segments'][name]['steps']
        driven = np.concatenate([data['u'][a:z, axis] for a, z in spans])
        levels = sorted(set(np.abs(driven))-{0.})
        c0, u1 = (profile['deadband'][key][axis] for key in ('c0', 'u1'))
        roles = {'stop': [v for v in levels if v < c0],
                 'ramp': [v for v in levels if c0 < v < u1],
                 'saturation': [v for v in levels if v >= u1]}
        if not roles['stop'] or len(roles['ramp']) < 2 or not roles['saturation']:
            raise ValueError(name+': observed levels do not bracket positive stop, two ramps and saturation')
        rows = []
        for h in gate['horizons_s']:
            starts, k = b.c.windows(spans, h, data['dt'])
            for role, magnitudes in roles.items():
                for magnitude in magnitudes:
                    for sign in (-1, 1):
                        command = sign*magnitude
                        outside = np.r_[0, np.cumsum(data['u'][:, axis] != command)]
                        keep = starts[outside[starts+k] == outside[starts]]
                        if not len(keep):
                            raise ValueError(f'{name}: missing signed {role} {command:+g} at {h:g}s')
                        actual = b.c.endpoint_targets(data['pose'], keep, k)[:, axis]/h
                        rows.append({'role': role, 'command': command, 'horizon_s': h,
                            'windows': len(keep), 'observed_rate_median': float(np.median(actual))})
        support[name] = rows
    return support


def fit_shared(data_list, gate, bounds):
    """Restriction of r4 family to the loader's one scalar stopping tau.

    Optimize this restriction; never average independently fitted stop taus.
    Loaded adds the v6g ramp with measured breakaway and saturation support.
    """
    cached = []
    for data in data_list:
        for axis, name in enumerate(b.AXES):
            if not b.axis_supported(data, axis, gate):
                raise ValueError(f'{name}: both signed steps/PRBS and complete horizons required')
        groups = [(axis, s, k, b.c.endpoint_targets(data['pose'], s, k)[:, axis])
                  for axis, _, _, s, k in window_groups(split_data(data, 'steps'), gate)]
        cached.append((data, groups))

    def profile(theta):
        value = np.exp(theta[:7])
        p = r4.profile(0, [value[0], value[3], value[6]], gate)
        p.update(gain=np.diag(value[:3]).tolist(), tau_axis_s=value[3:6].tolist())
        p['deadband'] = {'c0': theta[7:10].tolist(), 'u1': theta[10:13].tolist()}
        return p

    def residual(theta):
        p = profile(theta)
        errors = []
        for data, groups in cached:
            path = path_of(increments(data, p))
            for axis, starts, k, actual in groups:
                error = b.c.endpoint_targets(path, starts, k)[:, axis]-actual
                if axis == 2:
                    error = np.arctan2(np.sin(error), np.cos(error))
                errors.append(error)
        return np.concatenate(errors)

    initial = list(np.log([1., 1., 1., .8, .8, .8, .06]))
    lower = list(np.log([.05]*3+[.01]*3+[.005]))
    upper = list(np.log([4.]*6+[.5]))
    initial += bounds['initial_c0']+bounds['initial_u1']
    lower += bounds['c0_lower']+bounds['u1_lower']
    upper += bounds['c0_upper']+bounds['u1_upper']
    opt = least_squares(residual, initial, bounds=(lower, upper), max_nfev=150,
                        ftol=1e-9, xtol=1e-9, gtol=1e-9)
    report = verify_fit(opt, len(initial))
    distance = np.minimum(opt.x-np.asarray(lower), np.asarray(upper)-opt.x)
    if np.any(distance < bounds['interior_distance_min']):
        raise ValueError('shared fit touches parameter bounds')
    fitted = profile(opt.x)
    report['deadband_support'] = [deadband_support(data, fitted, gate) for data in data_list]
    return fitted, report


def fit_profile(data_list, criterion):
    gate = criterion['parent_text']
    # Preserve unconstrained three-parameter diagnostics too. These are never
    # used as a scalar-stop loader product without the restricted refit.
    candidates = []
    for data in data_list:
        candidate = {}
        for axis, name in enumerate(b.AXES):
            try:
                candidate[name] = r4.fit_mean(split_data(data, 'steps'), axis, gate)
            except ValueError as exc:
                candidate[name] = {'accepted': False, 'reason': str(exc)}
        candidates.append(candidate)
    profile, optimizer = fit_shared(data_list, gate, criterion['loaded_motion_bounds'])
    groups = [g for data in data_list for g in budget_groups(split_data(data, 'steps'), profile, gate)]
    profile['noise_abs'], certificate = minimum_noise(groups, gate)
    training = [evaluate(data, profile, gate, 'steps') for data in data_list]
    validation = [evaluate(data, profile, gate, 'prbs') for data in data_list]
    accepted = all(row['numerical_pass'] for result in validation for axis in result.values() for row in b.all_rows(axis))
    return profile, {'accepted': accepted, 'criterion': 'B-double-prime', 'fit': 'steps', 'validation_split': 'prbs',
        'axis_candidates': candidates, 'optimizer': optimizer, 'noise_certificate': certificate,
        'training': training, 'validation': validation,
        'scope': 'v92 HIGH steps/common-orbit fit; PRBS validation; relative-yaw excluded from plant fit; no independent cohort or task-success claim'}
