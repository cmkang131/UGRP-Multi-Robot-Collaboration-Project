"""B-prime step-fit/PRBS-score, r4 Euler mean and white process budget.

Only offline arrays enter here. No estimator factories or physical execution.
"""
from __future__ import annotations

import numpy as np
from scipy.optimize import least_squares, nnls

from harness.zone_final_pair_excitation import design
from scripts import fit_consumer_criterion_b as r4
from scripts import validate_consumer_criterion_b as b


def split_data(data, split):
    return {**data, 'segments': {axis: {split: spans[split]} for axis, spans in data['segments'].items()}}


def effective_data(data, profile):
    if 'deadband' not in profile:
        return data
    c0, u1 = (np.asarray(profile['deadband'][k]) for k in ('c0', 'u1'))
    if np.any(u1 <= c0):
        raise ValueError('unmeasured/degenerate deadband ramp')
    return {**data, 'u': data['u']*np.clip((np.abs(data['u'])-c0)/(u1-c0), 0., 1.)}


def increments(data, profile):
    return b.c.legacy_increments(effective_data(data, profile), profile)


def path_of(delta):
    yaw = np.r_[0., np.cumsum(delta[:, 2])]
    c, s = np.cos(yaw[:-1]), np.sin(yaw[:-1])
    xy = np.column_stack((c*delta[:, 0]-s*delta[:, 1], s*delta[:, 0]+c*delta[:, 1]))
    return np.column_stack((np.vstack((np.zeros(2), np.cumsum(xy, axis=0))), yaw))


def window_groups(data, gate):
    for axis, name in enumerate(b.AXES):
        for split, spans in data['segments'][name].items():
            for h in gate['horizons_s']:
                starts, k = b.c.windows(spans, h, data['dt'])
                if len(starts) < 100:
                    raise ValueError(f'{name}/{split}/{h}: fewer than 100 valid windows')
                yield axis, split, h, starts, k


def verify_fit(opt, count):
    rank = int(np.linalg.matrix_rank(opt.jac))
    if not opt.success or rank != count or np.any(opt.active_mask):
        raise ValueError(f'fit convergence/rank/boundary failure: rank {rank}/{count}')
    return {'rank': rank, 'success': True, 'rmse': float(np.sqrt(np.mean(opt.fun**2))), 'nfev': opt.nfev}


def deadband_support(data, gate):
    """Require the four signed plateaus in the surviving step-fit windows.

    Zero-command coast and PRBS cannot stand in for the below-breakaway
    command. Check every horizon after load selection, separately per robot.
    """
    levels = design('calibration-loaded')['magnitudes']
    support = {}
    for axis, name in enumerate(b.AXES):
        rows = []
        for h in gate['horizons_s']:
            starts, k = b.c.windows(data['segments'][name]['steps'], h, data['dt'])
            for role, magnitude in zip(('stop', 'ramp_low', 'ramp_high', 'saturation'), levels):
                for sign in (-1, 1):
                    command = sign*magnitude
                    outside = np.r_[0, np.cumsum(data['u'][:, axis] != command)]
                    count = int(np.count_nonzero(outside[starts+k] == outside[starts]))
                    if not count:
                        raise ValueError(f'{name}: loaded deadband support missing signed {role} '
                                         f'level {command:+g} in valid {h:g}s fit windows')
                    rows.append({'role': role, 'command': command, 'horizon_s': h, 'windows': count})
        support[name] = rows
    return support


def fit_shared(data_list, gate, *, deadband=False):
    """Restriction of r4 family to the loader's one scalar stopping tau.

    Optimize this restriction; never average independently fitted stop taus.
    Loaded adds the v6g ramp with measured breakaway and saturation support.
    """
    cached, support = [], []
    for data in data_list:
        for axis, name in enumerate(b.AXES):
            if not b.axis_supported(data, axis, gate):
                raise ValueError(f'{name}: both signed steps/PRBS and complete horizons required')
        if deadband:
            support.append(deadband_support(data, gate))
        groups = [(axis, s, k, b.c.endpoint_targets(data['pose'], s, k)[:, axis])
                  for axis, _, _, s, k in window_groups(split_data(data, 'steps'), gate)]
        cached.append((data, groups))

    def profile(theta):
        value = np.exp(theta[:7])
        p = r4.profile(0, [value[0], value[3], value[6]], gate)
        p.update(gain=np.diag(value[:3]).tolist(), tau_axis_s=value[3:6].tolist())
        if deadband:
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
    if deadband:
        # Four registered magnitudes: below c0, two inside ramp, >=u1.
        initial += [.010]*3+[.032]*3
        lower += [.006]*3+[.025]*3
        upper += [.015]*3+[.040]*3
    opt = least_squares(residual, initial, bounds=(lower, upper), max_nfev=150,
                        ftol=1e-9, xtol=1e-9, gtol=1e-9)
    report = verify_fit(opt, len(initial))
    distance = np.minimum(opt.x-np.asarray(lower), np.asarray(upper)-opt.x)
    if np.any(distance < 1e-6):
        raise ValueError('shared fit touches parameter bounds')
    fitted = profile(opt.x)
    if deadband:
        stop, ramp_low, ramp_high, saturation = design('calibration-loaded')['magnitudes']
        c0, u1 = np.asarray(fitted['deadband']['c0']), np.asarray(fitted['deadband']['u1'])
        if not np.all((stop < c0) & (c0 < ramp_low) & (ramp_low < ramp_high)
                      & (ramp_high < u1) & (u1 <= saturation)):
            raise ValueError('observed loaded levels do not bracket stop, two ramps and saturation')
        report['deadband_support'] = support
    return fitted, report


def budget_groups(data, profile, gate):
    """Diagonal covariance as C + L*a + A*a**2, exact r4 linearization.

    Reverse influence of each tick's noise at the endpoint accounts for
    heading coupling, including rotation. a is the three absolute noises.
    This is independently checked against legacy_windows in the tests.
    """
    delta = increments(data, profile)
    path = path_of(delta)
    relative = np.asarray(profile['noise_rel'])
    for axis, split, h, starts, k in window_groups(data, gate):
        pred = b.c.endpoint_targets(path, starts, k)
        error = pred-b.c.endpoint_targets(data['pose'], starts, k)
        error[:, 2] = np.arctan2(np.sin(error[:, 2]), np.cos(error[:, 2]))
        quad = np.zeros((len(starts), 3, 3))
        linear = np.zeros_like(quad)
        fixed = np.zeros((len(starts), 3))
        for j in range(k):
            angle = path[starts+j, 2]-path[starts, 2]
            c, s = np.cos(angle), np.sin(angle)
            after = b.c.endpoint_targets(path, starts, j+1)
            remaining = pred[:, :2]-after[:, :2]
            w = np.zeros_like(quad)
            w[:, 0, 0] = w[:, 1, 1] = c
            w[:, 0, 1], w[:, 1, 0] = -s, s
            w[:, 0, 2], w[:, 1, 2], w[:, 2, 2] = -remaining[:, 1], remaining[:, 0], 1.
            w = (w*data['dt'])**2
            rv = relative*np.abs(delta[starts+j]/data['dt'])
            quad += w
            linear += 2*w*rv[:, None, :]
            fixed += np.sum(w*rv[:, None, :]**2, axis=2)
        yield {'axis': b.AXES[axis], 'split': split, 'horizon': h, 'n': len(starts),
               'error': error, 'quad': quad, 'linear': linear, 'fixed': fixed}


def minimum_noise(groups, gate):
    """r4 order-statistic noise procedure generalized to rotating means.

    Later coefficients are unbounded by B. A window affected by one can be
    deferred when minimizing an earlier coefficient. Exact structural zeros
    (not a numeric tolerance) identify constraints that cannot be deferred.
    """
    absolute = np.asarray(gate['noise']['floor_noise_abs']).copy()
    order = (2, 0, 1)
    certificate = []
    for pos, j in enumerate(order):
        required = float(absolute[j])
        later = order[pos+1:]
        for group in groups:
            q, linear = group['quad'], group['linear']
            fixed = group['fixed']+np.sum(q*absolute[None, None, :]**2+linear*absolute, axis=2)
            fixed -= q[:, :, j]*absolute[j]**2+linear[:, :, j]*absolute[j]
            need = np.maximum(group['error']**2/4.-fixed, 0.)
            a, l = q[:, :, j], linear[:, :, j]
            denominator = l+np.sqrt(l*l+4*a*need)
            roots = np.divide(2*need, denominator, out=np.zeros_like(need), where=denominator > 0)
            roots[(need > 0) & (denominator == 0)] = np.inf
            if later:
                roots[np.any(q[:, :, later] > 0, axis=2)] = 0.
            index = int(np.ceil(.95*group['n']))-1
            required = max(required, float(np.max(np.partition(roots, index, axis=0)[index])))
        if not np.isfinite(required):
            raise ValueError('process noise constraints not identifiable/finite')
        floor = float(absolute[j])
        absolute[j] = required+(1e-12 if required > floor else 0.)
        certificate.append({'component': j, 'floor': floor, 'minimum': required})
    for group in groups:
        var = group['fixed']+np.sum(group['quad']*absolute**2+group['linear']*absolute, axis=2)
        if np.any(np.mean(group['error']**2 <= 4*var, axis=0) < .95):
            raise ValueError('minimum-noise coverage verification failed')
    return absolute.tolist(), certificate


def evaluate(data, profile, gate, split):
    effective = effective_data(split_data(data, split), profile)
    result = {}
    for axis, name in enumerate(b.AXES):
        # Count independently before the unchanged criterion B scorer.
        for h in gate['horizons_s']:
            starts, _ = b.c.windows(effective['segments'][name][split], h, data['dt'])
            if len(starts) < 100:
                raise ValueError(f'{name}/{split}: insufficient windows')
        result[name] = b.evaluate_axis(effective, axis, profile, gate)
    return result


def fit_profile(data_list, gate, *, loaded=False):
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
    profile, optimizer = fit_shared(data_list, gate, deadband=loaded)
    groups = [g for data in data_list for g in budget_groups(split_data(data, 'steps'), profile, gate)]
    profile['noise_abs'], certificate = minimum_noise(groups, gate)
    training = [evaluate(data, profile, gate, 'steps') for data in data_list]
    validation = [evaluate(data, profile, gate, 'prbs') for data in data_list]
    accepted = all(row['numerical_pass'] for result in validation for axis in result.values() for row in b.all_rows(axis))
    return profile, {'accepted': accepted, 'criterion': 'B-prime', 'fit': 'steps', 'validation_split': 'prbs',
        'axis_candidates': candidates, 'optimizer': optimizer, 'noise_certificate': certificate,
        'training': training, 'validation': validation,
        'scope': 'within-collection time blocks; no mixed-axis, independent cohort or task-success claim'}


def fit_spread(data_list, profile, gate):
    """v6e NNLS and maximum leave-one-step-out, without v2 constants.

    e^2=a*T+s2*d^2 (translation), e_yaw^2=a*T+b2*T^2 (yaw).
    Drift is v6g's cell-balanced cross error / along travel (>=.3m).
    """
    rows, drift = [], {}
    for data in data_list:
        path = path_of(increments(data, profile))
        for axis, name in enumerate(b.AXES):
            for index, (a, z) in enumerate(data['segments'][name]['steps']):
                # A complete signed 10s step + coast is needed for LOEO units.
                if (z-a)*data['dt'] < 11.-1e-7:
                    continue
                episode = f'{name}/{index}'  # both robot views belong to same block
                for h in gate['horizons_s']:
                    starts, k = b.c.windows([(a, z)], h, data['dt'])
                    pred = b.c.endpoint_targets(path, starts, k)
                    error = b.c.endpoint_targets(data['pose'], starts, k)-pred
                    error[:, 2] = np.arctan2(np.sin(error[:, 2]), np.cos(error[:, 2]))
                    rows.extend((episode, h, e, d) for e, d in zip(error, pred))
                if axis < 2:
                    gt = b.c.endpoint_targets(data['pose'], np.array([a]), z-a)[0]
                    pred = b.c.endpoint_targets(path, np.array([a]), z-a)[0]
                    if abs(gt[axis]) >= .3:
                        magnitude = float(np.max(np.abs(data['u'][a:z, axis])))
                        drift.setdefault(f'{name}/{magnitude}', []).append((gt[1-axis]-pred[1-axis])/abs(gt[axis]))
    episodes = sorted({r[0] for r in rows})
    if len(episodes) < 3:
        raise ValueError('load_transition: fewer than three complete lifted step blocks')
    T = np.asarray([r[1] for r in rows])
    error, distance = np.array([r[2] for r in rows]), np.array([r[3] for r in rows])
    names = np.asarray([r[0] for r in rows])
    fits = []
    for omit in [None, *episodes]:
        keep = names != omit
        scale = []
        for j in range(3):
            x = np.column_stack((T[keep], T[keep]**2 if j == 2 else distance[keep, j]**2))
            if np.linalg.matrix_rank(x) != 2:
                raise ValueError('load_transition spread rank deficient')
            fit, _ = nnls(x, error[keep, j]**2)
            scale.append(float(np.sqrt(fit[1])))
        fits.append(scale)
    if not drift or not all(any(key.startswith(axis+'/') for key in drift) for axis in ('forward', 'left')):
        raise ValueError('drift_ratio_std: no >=0.3m lifted translation per axis')
    maxima = np.max(fits, axis=0)
    return {'load_transition': {'scale_std': [float(maxima[0]), float(maxima[1]), 0.], 'unloaded_scale_std': 0.},
            'yaw_bias_std_rad_s': float(maxima[2]),
            'drift_ratio_std': float(np.sqrt(np.mean([np.mean(np.square(v)) for v in drift.values()])))}, {
            'accepted': True, 'complete_step_blocks': len(episodes), 'loeo_spreads': fits,
            'drift_cells': drift, 'yaw_scale': 'structural zero; yaw uncertainty represented by rate bias',
            'unloaded_scale': 'criterion B fixed white-only use_scale=false, not an empirical slip estimate'}
