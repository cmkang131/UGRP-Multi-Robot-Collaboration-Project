"""Shared, opt-in sensor tempering for static-map PF and own-map RBPF.

Only existing observation scores and independently calibrated motion tables
enter here. No truth, residual from an evaluation run, map substitution, seed
change, covariance floor tuning or process-global monkey patch.
"""
import copy
import functools
import hashlib
import json
import math
from pathlib import Path

import numpy as np

OPTIONS = ('off', 'effective_sqrt_v1', 'effective_mean_v1', 'effective_sqrt_alpha_v1')
ALPHA_ASSET = Path(__file__).with_name('calibrations')/'pulse_rotation_xy_alpha_v1.json'


def log_score(value, effective_count, *, option='off'):
    if option == 'off':
        return value
    if option not in OPTIONS:
        raise ValueError('unknown observation consistency option')
    n = max(1., float(effective_count))
    if not math.isfinite(n):
        raise ValueError('nonfinite effective observation count')
    return value / (n if option == 'effective_mean_v1' else math.sqrt(n))


def alpha_profiles(profiles, *, option='off'):
    """PR 5.4 squared-motion covariance; fixed independent calibration only."""
    if option != 'effective_sqrt_alpha_v1':
        if option not in OPTIONS:
            raise ValueError('unknown observation consistency option')
        return profiles
    cal = json.loads(ALPHA_ASSET.read_text())
    if cal['runtime_gt'] is not False:
        raise ValueError('independent calibration required')
    a1, a2, a3, a4 = cal['alpha_1_to_4']
    out = copy.deepcopy(profiles)
    for p in out.values():
        # The independent training set contains unloaded turn and forward
        # pulses only. Do not silently transfer it to loaded or lateral moves.
        if p['loaded'] or p['axis'] not in ('turn', 'forward'):
            continue
        x, y, yaw = p['mean_delta']
        trans2, rot2 = x*x+y*y, yaw*yaw
        variance = np.maximum(p['prediction_variance'],
            [(a3*trans2+a4*rot2)/2]*2+[a1*rot2+a2*trans2])
        p['prediction_variance'] = variance.tolist()
        # Retain the existing normal draw path and its RNG order. Existing
        # covariance profiles, when present, gain diagonal noise only.
        if 'prediction_covariance' in p:
            cov = np.asarray(p['prediction_covariance']).copy()
            cov += np.diag(np.maximum(variance-np.diag(cov), 0.))
            p['prediction_covariance'] = cov.tolist()
    return out


def _bind(function, **values):
    # Private function globals, same code/defaults/closure; no global patch.
    import types
    result = types.FunctionType(function.__code__, {**function.__globals__, **values},
        function.__name__, function.__defaults__, function.__closure__)
    result.__kwdefaults__ = function.__kwdefaults__
    return result


def _closure(function, name):
    cells = dict(zip(function.__code__.co_freevars, function.__closure__ or ()))
    if name not in cells:
        raise ValueError('unsupported PF observation boundary: '+name)
    return cells[name]


def _ownmap_alpha(grid, audit):
    """Add independent alpha Q at the actual GMapping own-scan boundary.

    That consumer intentionally discards per-pulse Q. Preserve its original
    mean/F propagation and noise interval; do not add the same Q twice.
    """
    from types import MethodType
    advance = getattr(grid.odom.advance, '__func__', None)
    callback = grid.odom.driver.step_callback
    if (advance is None or 'motion_variance' not in advance.__globals__
            or not hasattr(grid, '_selective_state') or not callable(callback)):
        raise ValueError('explicit GMapping motion covariance boundary required')
    original = advance.__globals__['motion_variance']
    cal = json.loads(ALPHA_ASSET.read_text())
    if cal['runtime_gt'] is not False:
        raise ValueError('independent calibration required')
    a1, a2, a3, a4 = cal['alpha_1_to_4']
    scopes = set()

    def propagate(delta, variance):
        if np.any(delta):
            active = grid.odom.driver.active
            if active is None:
                raise ValueError('own-map pulse scope unavailable')
            p = active[1]
            scopes.add((bool(p['loaded']), p['axis']))
        return callback(delta, variance)

    def motion_variance(delta):
        base = original(delta)
        audit['motion_noise_calls'] += 1
        supported = bool(scopes) and scopes <= {(False, 'forward'), (False, 'turn')}
        scopes.clear()
        if not supported:
            audit['motion_noise_scope_skipped'] += 1
            return base
        x, y, yaw = delta
        trans2, rot2 = x*x+y*y, yaw*yaw
        result = np.maximum(base, [(a3*trans2+a4*rot2)/2]*2+[a1*rot2+a2*trans2])
        audit['motion_noise_augmented'] += int(np.any(result > base))
        return result

    audit.update(alpha_asset_sha256=hashlib.sha256(ALPHA_ASSET.read_bytes()).hexdigest(),
        motion_noise_boundary='GMapping own-observation delta', motion_noise_calls=0,
        motion_noise_augmented=0, motion_noise_scope_skipped=0)
    grid.odom.driver.step_callback = propagate
    grid.odom.advance = MethodType(_bind(advance, motion_variance=motion_variance), grid.odom)


def _s3_alpha(runtime, audit):
    """Transform the profile actually selected by the final pulse predictor.

    Slip/rotation adapters may install or temporarily select another table.
    A dictionary captured by an older command wrapper is not the consumer.
    """
    pf = runtime.pose.provider.loc._pf
    predict = pf.predict_to
    seen = set()
    while 'active' not in predict.__code__.co_freevars:
        if id(predict) in seen:
            raise ValueError('cyclic pulse prediction boundary')
        seen.add(id(predict))
        links = {'predict', 'pulse_predict'} & set(predict.__code__.co_freevars)
        if len(links) != 1:
            raise ValueError('unsupported composed pulse prediction boundary')
        predict = _closure(predict, next(iter(links))).cell_contents
    active = _closure(predict, 'active')
    model = _closure(predict, 'model').cell_contents
    if model.get('noise_model') is not None:
        raise ValueError('explicit pulse variance predictor required')
    cache = {}
    original = pf.command

    def command(row):
        value = original(row)
        item = active.cell_contents
        if (item is not None and row['kind'] in ('drive', 'mecanum')
                and float(row['t']) == item[0]):
            started, profile = item
            if not profile['loaded'] and profile['axis'] in ('forward', 'turn'):
                key = id(profile)
                if key not in cache:
                    corrected = alpha_profiles({'selected': profile}, option='effective_sqrt_alpha_v1')['selected']
                    cache[key] = (profile, corrected)  # keep identities alive
                active.cell_contents = (started, cache[key][1])
                audit['motion_noise_commands'] += 1
        return value

    pf.command = command
    audit.update(motion_noise_boundary='final pulse predictor active profile', motion_noise_commands=0)


def attach_s3(runtime, *, observation_consistency='off'):
    option = observation_consistency
    if option == 'off':
        return runtime
    if option not in OPTIONS:
        raise ValueError('unknown observation consistency option')
    pf = runtime.pose.provider.loc._pf
    cell = _closure(pf.update_obs, 'selected')
    selected = cell.cell_contents
    original = selected.__globals__['likelihood']
    audit = dict(option=option, gt_inputs=False, scores=0, effective_counts={})

    def likelihood(field, px, packet):
        value = original(field, px, packet)
        n = max(1, int(bool(len(packet.wall)))+len(packet.features))
        audit['scores'] += 1
        audit['effective_counts'][str(n)] = audit['effective_counts'].get(str(n), 0)+1
        return np.exp(log_score(np.log(value), n, option=option))

    cell.cell_contents = _bind(selected, likelihood=likelihood)
    if option == 'effective_sqrt_alpha_v1':
        profiles = alpha_profiles(runtime.pulse_profiles, option=option)
        # install() returns the very dictionary captured by command(). Keep
        # its identity while replacing independent per-profile dictionaries.
        runtime.pulse_profiles.clear()
        runtime.pulse_profiles.update(profiles)
        runtime.pulse_model['profiles'] = copy.deepcopy(profiles)
        audit['alpha_asset_sha256'] = hashlib.sha256(ALPHA_ASSET.read_bytes()).hexdigest()
        _s3_alpha(runtime, audit)
    old_record = runtime.record
    runtime.record = lambda: {**old_record(), 'observation_consistency': copy.deepcopy(audit)}
    runtime.observation_consistency_audit = audit
    return runtime


def attach_ownmap(grid, *, observation_consistency='off'):
    """After egomap27 composition; all improved-proposal likelihood calls.

    The selected instance's private proposal uses the same tempered score in
    coarse matching, fine sampling and importance correction. Other maps,
    virtual forecasts, RNG and default-off code retain their original ABI.
    """
    option = observation_consistency
    if option == 'off':
        return grid
    if option not in OPTIONS:
        raise ValueError('unknown observation consistency option')
    proposal = grid._selective_proposal
    if not isinstance(proposal, functools.partial):
        raise ValueError('explicit egomap27 proposal boundary required')
    old = proposal.func.__globals__['likelihood']
    audit = dict(option=option, gt_inputs=False, scores=0, effective_counts={})

    def likelihood(field, points, poses, sigma, effective_points=12.):
        value = old(field, points, poses, sigma, effective_points=effective_points)
        n = max(1., min(len(points), effective_points))
        audit['scores'] += 1
        audit['effective_counts'][str(n)] = audit['effective_counts'].get(str(n), 0)+1
        return log_score(value, n, option=option)

    grid._selective_proposal = functools.partial(_bind(proposal.func, likelihood=likelihood),
        *proposal.args, **proposal.keywords)
    if option == 'effective_sqrt_alpha_v1':
        _ownmap_alpha(grid, audit)
    grid.observation_consistency_audit = audit
    return grid
