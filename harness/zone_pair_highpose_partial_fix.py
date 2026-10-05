"""Degeneracy-aware fix receipt for the OpenCV wall-band observer (flag; default off).

Problem (offline replay of light2 r1 relook 135.1-138.8 s, recorded in
``experiments/2026-10-05-opencv-column-diagnosis``): the OpenCV observer kept 58-85 of 96 columns and their rows
matched the true wall/floor boundary within 4 px, yet no fix receipt followed. ``zone_final_pair_scan.quality``
requires the SMALLEST eigenvalue of the 3x3 numerical information matrix (x, y, yaw) to exceed 1. A robot facing one
straight wall (the divider, the east wall) cannot observe the translation along that wall, so that eigenvalue is 0
for every such view even though range and yaw are observed to millimetres. The gate therefore rejects every
single-wall view, however good the detection.

Standard handling of this aperture problem (Zhang, Kaess & Singh, "On degeneracy of optimization-based state
estimation problems", ICRA 2016: examine the eigenvalues of the information matrix, update only along the
well-conditioned directions and carry the rest from the prior; Thrun, Burgard & Fox 2005, section 7: a range-
bearing line observation constrains only the line normal and heading): a measurement is informative when the
information matrix has enough strong directions, not when it is full rank. The particle weights already behave
this way (the likelihood is flat along the unobserved direction, so the prior spread there is unchanged).

Rule (no new constant): the old gate's inlier fraction, posterior support, saturation and settled tests are kept;
only the curvature test changes from ``lambda_min > 1`` to ``lambda_second > 1`` (at least two strong directions;
the same unit threshold, same step sizes). The receipt records ``observed_rank`` and the weakest direction so a
consumer can see that the view was a partial fix; it never claims the weak direction was measured.

Installation is per PF instance on top of the existing wrappers (``zone_final_pair_scan.install``,
consistency, local redraw); no frozen file or module global changes. ``PartialFixHighPoseSource`` is the
provider with the rule on; the default provider (``HighPoseSource``) is untouched.
"""
from __future__ import annotations

import copy
import math
from types import SimpleNamespace

import numpy as np

from harness.owncam_recovery_v6 import MIN_INLIER_FRACTION

ID = 'v98_partial_fix_second_eigenvalue_v1'
STEP = np.array([.01, .01, .02])
UNIT_EIGENVALUE = 1.0          # the old gate's own threshold
MIN_STRONG_DIRECTIONS = 2


def record() -> dict:
    return {'id': ID, 'rule': 'curvature: lambda_second > 1 (old gate: lambda_min > 1); other tests unchanged',
            'min_strong_directions': MIN_STRONG_DIRECTIONS, 'unit_eigenvalue': UNIT_EIGENVALUE,
            'shared_sources_modified': False, 'default': 'off',
            'references': ['Zhang, Kaess, Singh, ICRA 2016 (degeneracy of state estimation, partial update)',
                           'Thrun, Burgard, Fox 2005 (line features constrain the normal and heading only)']}


def information_matrix(loglik, point, obs, pose):
    """Numerical 3x3 information matrix at ``point`` (same stencil as ``RecoveryLocalizer._curvature``)."""
    probes = [point]
    for i in range(3):
        for sign in (-1, 1):
            q = point.copy()
            q[i] += sign*STEP[i]
            probes.append(q)
    values = loglik(np.asarray(probes), obs, pose)
    info = np.diag([(2*values[0] - values[1+2*i] - values[2+2*i])/STEP[i]**2 for i in range(3)])
    for i in range(3):
        for j in range(i+1, 3):
            mixed = []
            for si, sj in ((1, 1), (1, -1), (-1, 1), (-1, -1)):
                q = point.copy()
                q[i] += si*STEP[i]
                q[j] += sj*STEP[j]
                mixed.append(q)
            v = loglik(np.asarray(mixed), obs, pose)
            info[i, j] = info[j, i] = -(v[0] - v[1] - v[2] + v[3])/(4*STEP[i]*STEP[j])
    return info


def verdicts(eigenvalues, base):
    """(old_informative, new_informative, strong_directions) from ascending eigenvalues and the unchanged tests."""
    strong = int((np.asarray(eigenvalues) > UNIT_EIGENVALUE).sum())
    return bool(base and eigenvalues[0] > UNIT_EIGENVALUE), bool(base and strong >= MIN_STRONG_DIRECTIONS), strong


def scan_quality(vl, pf, obs, pose):
    """Old-gate fields plus the eigenvalues; ``informative`` follows the second-eigenvalue rule.

    ``old_informative`` is the verdict of ``zone_final_pair_scan.quality`` computed from the same numbers.
    """
    m = pf.measurement
    vb, vt = pf.expected(pf.px, pose)
    probs = [vl.interval_prob(vb, obs.b_kind, obs.b_lo, obs.b_hi, m['sigma_px'], m.get('open_ends', True))[:, obs.b_kind != vl.NONE]]
    if pf.obs_params['use_top_edge']:
        probs.append(vl.interval_prob(vt, obs.t_kind, obs.t_lo, obs.t_hi, m['sigma_px'], m.get('open_ends', True))[:, obs.t_kind != vl.NONE])
    eps = m['outlier_prob']
    per_feature = np.log(eps + (1. - eps)*np.concatenate(probs, axis=1))
    if per_feature.shape[1] == 0 or not np.isfinite(per_feature).all():
        return {'accepted': False, 'informative': False, 'old_informative': False, 'settled': True, 'ambiguous': True,
                'reason': 'no_usable_geometry'}
    floor = math.log(eps)
    w = np.exp(pf.logw - np.max(pf.logw))
    w /= w.sum()
    fit = per_feature.mean(1)
    point = pf.px[int(np.argmax(fit + pf.logw))]
    best = int(np.argmax(fit + np.log(np.maximum(w, 1e-300))))
    inlier = per_feature > floor + math.log(2.)
    fraction = float(inlier[best].mean())
    support = float(w[inlier.mean(axis=1) >= MIN_INLIER_FRACTION].sum())
    saturated = bool(np.max(per_feature) <= floor + 1e-4)

    def loglik(points, _obs, _pose):
        b, t = pf.expected(points, _pose)
        return vl.column_loglik(b, t, _obs, {**m, 'use_top_edge': pf.obs_params['use_top_edge']})

    info = information_matrix(loglik, point, obs, pose)
    finite = bool(np.isfinite(info).all())
    eigval, eigvec = np.linalg.eigh(info) if finite else (np.zeros(3), np.eye(3))
    base = (not saturated and fraction >= MIN_INLIER_FRACTION and support >= .10 and finite)
    old, new, strong = verdicts(eigval, base)
    weak = eigvec[:, 0]
    return {'accepted': True, 'informative': new, 'old_informative': old, 'settled': True, 'ambiguous': not new,
            'inlier_fraction': fraction, 'posterior_support': support, 'saturated': saturated,
            'geometric_curvature': float(max(0., eigval[0])), 'eigenvalues': [float(v) for v in eigval],
            'observed_rank': strong, 'weakest_direction_xy_yaw': [float(v) for v in weak],
            'partial': bool(new and not old), 'rule': ID,
            'reason': 'informative' if new else 'residual_or_geometry_inconsistent'}


def install(pf, vl):
    """Wrap this PF's ``apply_scan``/``update_obs`` once more (outermost) so a partial fix sets the receipt."""
    if getattr(pf, 'partial_fix', None) is not None:
        raise ValueError('partial fix already installed')
    pf.partial_fix = {'record': record(), 'accepted_partial': 0, 'old_accepted': 0, 'scans': 0}
    apply, update = pf.apply_scan, pf.update_obs
    state = {'q': None}

    def apply_scan(t, obs, pose):
        state['q'] = scan_quality(vl, pf, obs, pose)
        pf.partial_fix['scans'] += 1
        return apply(t, obs, pose)

    def update_obs(t, obs, pose):
        previous = pf.last_scan_t
        state['q'] = None
        result = update(t, obs, pose)
        q = state['q']
        if result.get('measured'):
            pf.partial_fix['old_accepted'] += 1
        elif q is not None and q['informative']:
            # The inner gate refused (and restored last_scan_t); the scan itself was applied to the weights.
            pf.last_scan_t = t
            pf.v3_last_fix_quality = {k: v for k, v in q.items() if k not in ('eigenvalues',)} | {'t': t}
            result['measured'] = True
            pf.partial_fix['accepted_partial'] += 1
        pf.partial_fix_last = None if q is None else copy.deepcopy(q)
        return result

    pf.apply_scan, pf.update_obs = apply_scan, update_obs


def build_source_class():
    from harness.vision_pose_source_highpose import HighPoseSource

    class PartialFixHighPoseSource(HighPoseSource):
        """``HighPoseSource`` with the second-eigenvalue fix receipt. Everything else is inherited unchanged."""

        def __init__(self, *args, **kwargs):
            super().__init__(*args, **kwargs)
            from harness import vision_loc_protocol as vp
            install(self.loc._pf, vp.load_vis3()[0])
            self.m1_calibration = {**self.m1_calibration, 'partial_fix': record()}

    return PartialFixHighPoseSource


def build_provider(static_map, calibration, calibration_sha256, seed=0, *, worker=None):
    """Same shape as ``vision_pose_source_highpose.build_provider`` with the partial-fix rule on."""
    from harness.zone_study_pose_delay_p03 import DelayedPoseSource
    provider = build_source_class()(static_map, calibration, calibration_sha256, seed, worker=worker)
    try:
        return DelayedPoseSource(provider)
    except Exception:
        provider.close()
        raise
