"""v98 particle-filter consistency: count one stationary camera view once, temper columns by measured correlation.

Problem (offline replay of the recorded v98 DEV probes, ground truth used for scoring only): the PF was far
over-confident (2-DOF xy NEES 100-1000 against a chi-square 99.9 % bound of 13.8). Two input-side causes:

1. Repeated views. Own frames arrive every 0.05 SIM s. While the robot holds still with an unchanged arm/pan
   posture every settled frame is a new scan of the *same* view; 91 % of all applied scans were such repeats
   (mean 11, max 144 per view). Their errors are the same error (same camera-model error, same wall band), so
   multiplying their likelihoods counts one measurement ~11 times. Probabilistic Robotics treats measurements as
   conditionally independent; the standard practical answer is Nav2/ROS AMCL ``update_min_d``/``update_min_a``
   (``AmclNode::shouldUpdateFilter``: no sensor update until the robot moved 0.25 m or turned 0.2 rad).
2. Correlated columns inside one frame. The frozen VIS3 likelihood already caps a frame at
   ``effective_columns`` independent columns (8 in ``selected_config_v3``); the columns of one frame share the
   camera extrinsic/sag error, so the PF weight update uses a lower calibrated cap.

Method (no frozen file changes, no extra random draws):

* A *view* is identified from own inputs only: the servo pulses the provider passes with the scan, the own load
  state, the own drive commands, and the PF's own commanded-velocity odometry (its lagged command velocity
  integrated over SIM time) since the view began. A new view starts when the posture or load state changes, when
  an own non-zero drive command (``mecanum``) was issued since the view began, or when the odometry exceeds
  ``update_min_d`` metres or ``update_min_a`` radians (the AMCL rule, kept as a fallback for drift without a new
  command). The drive-command trigger matters because the fine align pulses (~12 mm) are below any useful
  distance threshold yet each one is a real move. A re-initialised particle cloud also starts a new view. The k-th applied scan of one view has its log-likelihood multiplied by
  ``a_k = c_k - c_{k-1}`` with ``c_K = K / (1 + (K-1) * rho)`` (the design effect of K equally correlated
  measurements with correlation ``rho``; Kish 1965). ``rho = 1`` is AMCL's "do not update while stationary"
  except that the first scan of every new view still updates; ``rho = 0`` is the frozen behaviour.
* The PF weight update of a frame with ``n`` column terms is multiplied by
  ``min(1, E/n) / min(1, E0/n)`` (``E0`` = the frozen ``effective_columns``), which is exactly the frozen
  likelihood with ``effective_columns = E``. ``pf.measurement`` itself is NOT changed, so the registered
  informative-scan gate (``zone_final_pair_scan.quality``: inlier fraction, support, curvature > 1) and with it
  the measured receipts and ``fix_age`` stay as registered; only how far one frame moves the particle weights
  changes.

Both numbers come from the calibration split only (``CALIBRATION`` below records which runs); the held-out
runs are scored separately. Ground truth never enters this module.

v3 (2026-10-04): roughening after resampling. From the dock the case-start prior is one Gaussian over three public
spawn rows (y std 2.8 m) sampled by 2000 particles, and the PF has no roughening (``params['roughen']`` absent).
Offline, with noise-free synthetic observations of r2's true dock pose fed through this provider (five-pan look),
r2 still ended 179 mm off with sigma 2 mm under the frozen weighting and 78 mm off (sigma 95 mm) under the v2
weighting: after the first resamples only a few distinct particles near the true pose survive and the cloud cannot
move to it (particle deprivation / sample impoverishment). The standard remedy is the roughening of Gordon, Salmond and Smith
(1993): after each resample add zero-mean Gaussian jitter with per-dimension sigma ``K * range_k * N^(-1/d)``
(``range_k`` = spread of the resampled set in dimension k, ``d`` = 3, ``K`` = 0.2 is their suggested constant; yaw
range on the unwrapped angles). Only the resampled particles are jittered and only their spread sets the sigma
(random injected particles, if any, are left alone). No constant was tuned; the calibration split (staged starts)
was a non-regression check only.
"""
from __future__ import annotations

import copy
import math

import numpy as np

SCHEMA = 'ugrp.pf_consistency.v98.v3'
# Calibrated on the calibration split (raise_high_align ace8b257 r1/r2) by
# experiments/2026-10-03-pair-carry-highpose/pf_consistency/; held-out = raise_high 3358372e and 7623c4dc.
DEFAULT = {'schema': SCHEMA, 'repeat_rho': .5, 'effective_columns': 4.0,
           'update_min_d': .02, 'update_min_a': .035, 'roughen_k': .2}
# Frozen behaviour (bit-identical PF): every scan counted fully, frozen column cap.
NEUTRAL = {'schema': SCHEMA, 'repeat_rho': 0.0, 'effective_columns': 8.0,
           'update_min_d': .02, 'update_min_a': .035, 'roughen_k': 0.0}
CONFIG = DEFAULT


def validate(cfg):
    cfg = {**DEFAULT, **(cfg or {})}
    if set(cfg) != set(DEFAULT) or cfg['schema'] != SCHEMA:
        raise ValueError('unknown pf_consistency keys or schema')
    for key, lo, hi in (('repeat_rho', 0., 1.), ('effective_columns', .5, 1e3),
                        ('update_min_d', 0., 1.), ('update_min_a', 0., math.pi), ('roughen_k', 0., 1.)):
        v = cfg[key]
        if isinstance(v, bool) or not isinstance(v, (int, float)) or not math.isfinite(v) or not lo <= v <= hi:
            raise ValueError(f'pf_consistency.{key}={v!r} outside [{lo}, {hi}]')
    return cfg


def cumulative(k, rho):
    """Information of k equally correlated scans in units of one scan (design effect)."""
    return 0. if k <= 0 else k/(1. + (k - 1)*rho)


def exponent(k, rho):
    """Likelihood exponent of the k-th applied scan of one view (k >= 1)."""
    return cumulative(k, rho) - cumulative(k - 1, rho)


def roughen_sigma(px, k):
    """Gordon et al. (1993) roughening sigma per dimension: K * range * N^(-1/d), yaw range on unwrapped angles."""
    px = np.asarray(px, float)
    n, d = px.shape
    if n < 2 or k <= 0.:
        return np.zeros(d)
    spread = np.ptp(px, axis=0)
    spread[2] = np.ptp(np.unwrap(px[:, 2]))
    return k*spread*n**(-1./d)


def install(pf, cfg=None):
    """Bind the v98 consistency rules to this PF instance (instance attributes only)."""
    cfg = validate(cfg)
    if getattr(pf, 'pf_consistency', None) is not None:
        raise ValueError('pf_consistency already installed')
    frozen_e = float(pf.measurement['effective_columns'])
    target_e = float(cfg['effective_columns'])
    state = {'key': None, 'k': 0, 'odo_d': 0., 'odo_a': 0., 'moved': False, 'alpha': 1.}
    pf.pf_consistency = {'config': copy.deepcopy(cfg), 'state': state}
    pf.stats.update(view_scans=0, repeat_scans=0, repeat_weight=0.)
    predict_to, apply_scan, scan_loglik = pf.predict_to, pf.apply_scan, pf.scan_loglik
    command, init_gaussian = pf.command, pf.init_gaussian

    def own_command(row):
        if row.get('kind') == 'mecanum' and any(float(row.get(k, 0.) or 0.) != 0. for k in ('forward', 'left', 'turn')):
            state['moved'] = True
        return command(row)

    def reinit(mean, std):
        state.update(key=None, k=0, odo_d=0., odo_a=0., moved=False)
        return init_gaussian(mean, std)

    def odometry_predict(t):
        # Own commanded-velocity odometry (the PF's lagged command velocity), never a measurement.
        t0 = float(pf.t)
        out = predict_to(t)
        dt = float(pf.t) - t0
        if dt > 0:
            v = np.asarray(pf.vel, float)
            state['odo_d'] += math.hypot(float(v[0]), float(v[1]))*dt
            state['odo_a'] += abs(float(v[2]))*dt
        return out

    def view_apply(t, obs, pose):
        key = (tuple(sorted((int(s), int(p)) for s, p in dict(pose).items())), bool(pf.load.loaded))
        if (key != state['key'] or state['moved'] or state['odo_d'] >= float(cfg['update_min_d'])
                or state['odo_a'] >= float(cfg['update_min_a'])):
            state.update(key=key, k=1, odo_d=0., odo_a=0., moved=False)
            pf.stats['view_scans'] += 1
        else:
            state['k'] += 1
            pf.stats['repeat_scans'] += 1
        state['alpha'] = exponent(state['k'], float(cfg['repeat_rho']))
        if state['k'] > 1:
            pf.stats['repeat_weight'] = round(pf.stats['repeat_weight'] + state['alpha'], 6)
        try:
            return apply_scan(t, obs, pose)
        finally:
            state['alpha'] = 1.

    def tempered_loglik(obs, pose):
        ll, n_terms = scan_loglik(obs, pose)
        n = max(int(n_terms), 1)
        columns = min(1., target_e/n)/min(1., frozen_e/n)
        return ll*(state['alpha']*columns), n_terms

    def roughened_resample():
        before = pf.stats['resamples']
        out = normalize_and_resample()
        if k_rough > 0. and pf.stats['resamples'] > before:
            m = pf.n - int(pf.diag.get('injected', 0) or 0)       # resampled particles come first
            if m >= 2:
                sigma = roughen_sigma(pf.px[:m], k_rough)
                pf.px[:m] = pf.px[:m] + pf.rng.normal(size=(m, pf.px.shape[1]))*sigma
                pf.px[:m, 2] = pf.wrap(pf.px[:m, 2])
                pf.stats['roughened'] += 1
                pf.diag['roughen_sigma'] = [round(float(v), 6) for v in sigma]
        return out

    k_rough = float(cfg['roughen_k'])
    pf.predict_to, pf.apply_scan, pf.scan_loglik = odometry_predict, view_apply, tempered_loglik
    pf.command, pf.init_gaussian = own_command, reinit
    if k_rough > 0.:                                  # roughen_k = 0 leaves the resampler (and stats) untouched
        normalize_and_resample = pf._normalize_and_resample
        pf.stats['roughened'] = 0
        pf._normalize_and_resample = roughened_resample
    return pf.pf_consistency


def record(cfg=None):
    return {'module': 'harness/zone_pair_highpose_pf_consistency.py', **validate(cfg)}
