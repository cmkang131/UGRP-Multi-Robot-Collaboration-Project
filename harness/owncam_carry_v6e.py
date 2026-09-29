"""v6e: the pair carry's dead-reckoning error model and open-loop lateral timing, from the loaded-plant calibration.

Two independent opt-in flags (``PairPolicy.carry_dr_model``, ``PairPolicy.carry_lateral_lag``); this module
holds the pieces both need. With both off nothing here is reached and the v6c behaviour is unchanged.

Root causes (2026-09-29 carry stage probes, PR #266, baseline b-v6c 0 of 33 staged cells):

1. ``carry_dr_model``. The registered LOADED error model (``motion_loaded``: ``noise_abs`` yaw 0.0976 rad/s,
   applied on every 0.05 s step, also at rest; per-particle scales still spread by the UNLOADED 0.2148) makes
   the reported yaw sigma grow as 0.0218 rad/sqrt(s) and reach the 3 degree hold gate 2.4-3.3 s into a leg
   that takes 11-18 s. That model was fitted on finite-difference ground-truth residuals treated as white
   rate noise. Woodman (2007, Cambridge TR-696) shows white rate noise integrates to sqrt(t) but a constant
   rate bias integrates to t; Borenstein & Feng (1996) show wheel odometry errors are systematic and change
   with the load. The dev box-carry data (``carry_dr_fit.json``, fitted by ``fit_carry_dr.py`` on the loaded
   plant with the horizon-matched window error, NOT on the 33 stage cells) say: loaded yaw drift is a
   zero-mean constant rate error per leg (lag-1 autocorrelation of the residual 0.96, per-leg means
   -0.0018 ... +0.0015 rad/s), the white part is ~0, and translation errors are white velocity noise plus a
   small relative scale error. This module makes the filter carry exactly that: motion-gated white noise, a
   per-particle constant yaw-rate bias (drawn when the load is picked up, resampled with the particles so a
   fix can still learn it), and loaded slip scales redrawn with the calibrated loaded spread. The gate, its
   thresholds, the sweep-guard margin and the reported sigma are untouched: sigma still grows and still
   trips when the model says the pose is lost.
2. ``carry_lateral_lag``. ``CARRY_ODOM_SCALE['lateral'] = 0.697`` divides the leg length by a constant
   speed factor, but a first-order-lag plant (loaded ``tau_s`` 0.8 s) travels ``v (T - tau (1 - e^{-T/tau}))``
   in a command of length T, so a factor measured on one leg length cannot carry over to another; the lateral
   legs (0.717 m) then travel 15.6% too far. This module inverts the calibrated loaded plant for T.
"""
from __future__ import annotations

import copy
import hashlib
import json
import math
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
# carry_dr_fit.json (dev box carry, first fit) + the yaw bias std refitted on the cal cohort only after the cal
# honesty gate failed (refit_carry_dr_cal.py; the 33-cell grid and the held-out placements were not read).
FIT = 'experiments/2026-09-29-pair-v6e-carry/carry_dr_fit_cal1.json'
# Yaw flags (carry_pair_yaw / carry_beam_edge): the per-particle yaw-rate bias std of each estimator variant and the
# beam-edge slope-to-yaw ratio, fitted on the cal cohort only (fit_carry_pair_yaw.py; grid and held-out unread).
PAIR_FIT = 'experiments/2026-09-29-pair-v6e-carry/carry_pair_fit.json'
# v6g flag ``carry_dr_general``: the loaded plant's lateral deadband, the distance-proportional cross-axis drift ratio and
# the yaw-flag biases refitted on the cal cohort that spans several y offsets and beam headings (fit_carry_general.py).
GENERAL_FIT = 'experiments/2026-09-29-pair-v6e-carry/carry_general_fit.json'
# Axes whose open-loop leg length uses the lag model (flag ``carry_lateral_lag``).
LAG_AXES = ('lateral',)


def _digest(value):
    return hashlib.sha256(json.dumps(value, sort_keys=True, separators=(',', ':')).encode()).hexdigest()


def profile_from_fit(fit, unloaded_scale_std):
    """Loaded-plant error keys from the dev fit. Every spread is the largest leave-one-episode-out value."""
    loeo = fit['loeo_range']
    return {
        'rest_noise': False,
        'noise_rel': [0., 0., 0.],
        'noise_abs': [loeo['x']['white_vel_std_m_s'][1], loeo['y']['white_vel_std_m_s'][1],
                      loeo['yaw']['white_rate_std_rad_s'][1]],
        'scale_walk': 0.,
        'yaw_bias_std_rad_s': loeo['yaw']['bias_rate_std_rad_s'][1],
        'load_transition': {'scale_std': [loeo['x']['scale_std'][1], loeo['y']['scale_std'][1], 0.],
                            'unloaded_scale_std': unloaded_scale_std},
    }


def load_profile(unloaded_scale_std):
    raw = (ROOT/FIT).read_bytes()
    profile = profile_from_fit(json.loads(raw), unloaded_scale_std)
    return profile, {'source': FIT, 'file_sha256': hashlib.sha256(raw).hexdigest(), 'profile_sha256': _digest(profile)}


def _inner(provider):
    while hasattr(provider, 'provider'):
        provider = provider.provider
    return provider


def _pf(provider):
    inner = _inner(provider)
    loc = getattr(inner, 'loc', None)
    pf = getattr(loc, '_pf', loc)
    if pf is None or not hasattr(pf, '_init_plant_state') or 'motion_loaded' not in getattr(pf, 'params', {}):
        raise ValueError('carry_dr_model needs a tag PF with a loaded motion model')
    return inner, pf


def variant_key(pair_yaw=False, beam_edge=False):
    """Estimator variant name in ``carry_pair_fit.json``; '' is the yaw-flags-off v6e profile."""
    return '+'.join(k for k, on in (('pm', pair_yaw), ('edge', beam_edge)) if on)


def load_pair_fit(general=False):
    path = GENERAL_FIT if general else PAIR_FIT
    raw = (ROOT/path).read_bytes()
    fit = json.loads(raw)
    return fit, {'source': path, 'file_sha256': hashlib.sha256(raw).hexdigest()}


def enable_provider(provider, pair_yaw=False, beam_edge=False, general=False):
    """Give this provider's PF the calibrated loaded profile (idempotent; other providers are untouched).

    ``pair_yaw`` / ``beam_edge`` (yaw flags) select the estimator variant: the per-particle yaw-rate bias std is the
    cal-fitted value of that variant, and ``beam_edge`` attaches the own-RGB beam-edge tracker. The pair-mean model
    itself is driven by the executor (partner command derived from the route plan). A provider stays bound to one
    variant. ``general`` (flag ``carry_dr_general``) adds the fitted lateral deadband and the distance-proportional
    cross-axis drift ratio to the loaded profile and takes the yaw-flag biases from the general fit.
    """
    inner, pf = _pf(provider)
    variant = variant_key(pair_yaw, beam_edge)
    if getattr(inner, 'carry_dr_v6e', None) is not None:
        if getattr(inner, 'carry_variant_v6e', '') != variant or bool(getattr(inner, 'carry_general_v6e', False)) != bool(general):
            raise ValueError(f'pose provider is bound to carry variant {getattr(inner, "carry_variant_v6e", "")!r}'
                             f'{" +general" if getattr(inner, "carry_general_v6e", False) else ""}; '
                             f'{variant!r}{" +general" if general else ""} needs a fresh provider')
        return inner.carry_dr_v6e
    unloaded = pf.params['motion']['scale_std']
    profile, info = load_profile(unloaded)
    if general:
        gfit, gfit_info = load_pair_fit(general=True)
        profile['deadband'] = {k: [float(v) for v in gfit['deadband_cmd'][k]] for k in ('c0', 'u1')}
        profile['drift_ratio_std'] = float(gfit['drift_ratio_std'])
        info = {**info, 'general_fit': gfit_info, 'deadband_cmd': profile['deadband'],
                'drift_ratio_std': profile['drift_ratio_std'], 'profile_sha256': _digest(profile)}
    if variant:
        fit, fit_info = load_pair_fit(general)
        profile['yaw_bias_std_rad_s'] = float(fit['b_rad_s'][variant])
        info = {**info, 'variant': variant, 'pair_fit': fit_info, 'yaw_bias_std_rad_s': profile['yaw_bias_std_rad_s'],
                'profile_sha256': _digest(profile)}
        if beam_edge:
            from harness.own_beam_edge import BeamEdgeTracker
            inner.beam_edge = BeamEdgeTracker(float(fit['slope_to_yaw_ratio']))
            info['slope_to_yaw_ratio'] = float(fit['slope_to_yaw_ratio'])
        # Availability fallback: b of the estimator actually in effect (pair-mean matched? edge tracked?), the
        # registered (yaw flags off) value when neither is.
        inner.carry_yaw_fallback = {'pair': bool(pair_yaw), 'edge': bool(beam_edge), 'b_full': profile['yaw_bias_std_rad_s'],
                                    'b': {'': float(load_profile(unloaded)[0]['yaw_bias_std_rad_s']),
                                          **{k: float(v) for k, v in fit['b_rad_s'].items()}},
                                    'level_frames': {}, 'pm_bad_until': -1.}
        info['fallback_b_rad_s'] = dict(inner.carry_yaw_fallback['b'])
    # Rebind, never mutate: the params dict may be shared with other providers of the same run.
    pf.params = {**pf.params, 'motion_loaded': {**pf.params['motion_loaded'], **copy.deepcopy(profile)}}
    if pf.initialized and pf.load.loaded:
        pf._draw_plant_state(True)
    inner.carry_dr_v6e = info
    inner.carry_variant_v6e = variant
    inner.carry_general_v6e = bool(general)
    return info


def bound(provider):
    """True when this provider was switched to the v6e carry error model (providers are reused across runs)."""
    return getattr(_inner(provider), 'carry_dr_v6e', None) is not None


def lag_travel(duration_s, v_ss, tau_s, tau_stop_s):
    """Distance of a first-order-lag drive: command held ``duration_s``, then wheels commanded to zero."""
    ramp = 1. - math.exp(-duration_s/tau_s)
    return v_ss*(duration_s - tau_s*ramp) + v_ss*ramp*tau_stop_s


def lag_duration(distance_m, v_ss, tau_s, tau_stop_s):
    """Command length T with ``lag_travel(T) == distance_m`` (monotone in T, bisection)."""
    if not (distance_m > 0 and v_ss > 0 and tau_s > 0 and tau_stop_s >= 0):
        raise ValueError('lag_duration needs positive distance, steady speed and time constants')
    lo, hi = 0., distance_m/v_ss + 10.*tau_s
    for _ in range(80):
        mid = .5*(lo + hi)
        if lag_travel(mid, v_ss, tau_s, tau_stop_s) < distance_m:
            lo = mid
        else:
            hi = mid
    return .5*(lo + hi)


def steady_speed(calibration, axis, command):
    """Loaded steady body speed [m/s] along ``axis`` for a command vector [forward, left, turn]."""
    row = calibration['motion_loaded']['gain'][0 if axis == 'axial' else 1]
    return sum(float(g)*float(u) for g, u in zip(row, command))


def leg_duration(distance_m, axis, command, calibration):
    """Open-loop leg length from the calibrated loaded plant (spin-up and stop lag included)."""
    mp = calibration['motion_loaded']
    v = abs(steady_speed(calibration, axis, command))
    return lag_duration(distance_m, v, float(mp['tau_s']), float(mp.get('tau_stop_s', mp['tau_s'])))


def set_partner_plan(provider, t0, t1, *, own, partner):
    """Hand the PF the plan-derived partner command of the carry leg [t0, t1] (flag ``carry_pair_yaw``).

    ``own`` and ``partner`` are ``{'forward','left','turn'}`` commands built by the same plan function
    (route leg from the static map, role signs from the order sheet). The PF uses the partner command only for the
    yaw target while an issued own command equals ``own`` inside the window.
    """
    import numpy as np
    loc = getattr(_inner(provider), 'loc', None)
    if loc is None or not hasattr(loc, 'pair_plan'):
        raise ValueError('carry_pair_yaw needs a tag PF provider')
    vec = lambda c: np.array([c['forward'], c['left'], c['turn']], float)
    loc.pair_plan = {'t0': float(t0), 't1': float(t1), 'own': vec(own), 'partner': vec(partner)}


PM_HOLD_S = 2.       # a plan mismatch keeps the fallback for this long (no per-pulse flapping)


def fallback_std(cfg, pm_ok, edge_ok):
    """Extra constant yaw-rate std [rad/s] that brings the PF's bias spread from the variant's ``b_full`` up to the b
    of the estimator that is actually available (in quadrature; never negative)."""
    key = variant_key(cfg['pair'] and pm_ok, cfg['edge'] and edge_ok)
    b = cfg['b'][key]
    return math.sqrt(max(b*b - cfg['b_full']**2, 0.)), key


def update_availability(provider, now):
    """Per own frame (flags carry_pair_yaw / carry_beam_edge): set the PF's extra yaw std from what is available now."""
    inner = _inner(provider)
    cfg = getattr(inner, 'carry_yaw_fallback', None)
    if cfg is None:
        return
    loc = inner.loc
    if not loc.load.loaded:
        loc.set_extra_yaw_std(now, 0.)
        return
    if cfg['pair'] and not loc.pair_ok():
        cfg['pm_bad_until'] = float(now) + PM_HOLD_S
    pm_ok = float(now) >= cfg['pm_bad_until']
    edge = getattr(inner, 'beam_edge', None)
    edge_ok = edge is not None and edge.available(now)
    std, key = fallback_std(cfg, pm_ok, edge_ok)
    loc.set_extra_yaw_std(now, std)
    cfg['level_frames'][key or 'registered'] = cfg['level_frames'].get(key or 'registered', 0) + 1
