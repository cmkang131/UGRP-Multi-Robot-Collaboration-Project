"""Switchable Constraints (Suenderhauf/Protzel 2012, eq. 1), own graph only.

Independent implementation of the published objective, not vendored Vertigo.
Frozen constants/provenance: experiments/2026-10-07-robust-wall-map/README.md.
No GT, map geometry, motion-model fitting, hard edge removal, or solver install.
"""
from __future__ import annotations

import copy
from collections import Counter

import numpy as np
from scipy.optimize import least_squares
from scipy.sparse import lil_matrix

from harness.self_pose_graph import GraphOptions, between, compose, validate_rows, wrap

VALUES = ('off', 'switchable_v1')
SWITCH_PRIOR_VARIANCE = 1.
DIAGNOSTIC_SWITCH_THRESHOLD = .5  # Reporting only; the objective is continuous.


def optimize_switchable(submaps, rows, constraints, options=None):
    """Joint sparse SE2 / bounded linear switches; prior mean and variance one.

    Pose residual/covariance are both rotated into the measurement frame, as in
    Vertigo's inverseMeasurement * (pose_a^-1 * pose_b). This preserves the old
    submap-frame Mahalanobis norm, including correlated XY/yaw covariance.
    """
    o = options or GraphOptions()
    m = len(submaps)
    initial = np.vstack([s['pose'] for s in submaps] + [r['pose'] for r in rows])
    a = np.array([c['submap'] for c in constraints], dtype=int)
    b = np.array([m+c['scan'] for c in constraints], dtype=int)
    target = np.asarray([c['relative_pose'] for c in constraints], float)
    covariance = np.asarray([c['covariance'] for c in constraints], float)
    if (not len(constraints) or not np.isfinite(initial).all() or
            target.shape != (len(a), 3) or covariance.shape != (len(a), 3, 3) or
            not np.isfinite(target).all() or not np.isfinite(covariance).all() or
            not np.allclose(covariance, covariance.transpose(0, 2, 1)) or
            np.linalg.eigvalsh(covariance).min() <= 0 or
            np.any(a < 0) or np.any(a >= m) or np.any(b < m) or np.any(b >= len(initial)) or
            any(c['kind'] not in ('intra', 'loop') for c in constraints)):
        raise ValueError('INVALID_SWITCHABLE_GRAPH')
    loops = np.flatnonzero([c['kind'] == 'loop' for c in constraints])
    if not len(loops):
        return initial, dict(accepted=False, reason='no_loop_constraints', switches=[])
    rotation = np.zeros_like(covariance)
    c, s = np.cos(target[:, 2]), np.sin(target[:, 2])
    rotation[:, 0, 0] = rotation[:, 1, 1] = c
    rotation[:, 0, 1], rotation[:, 1, 0], rotation[:, 2, 2] = s, -s, 1.
    rotated_cov = rotation @ covariance @ rotation.transpose(0, 2, 1)
    whiten = np.linalg.cholesky(np.linalg.inv(rotated_cov)).transpose(0, 2, 1)
    npose = 3*(len(initial)-1)

    def unpack(x):
        return np.vstack([initial[0], x[:npose].reshape(-1, 3)])

    def errors(x):
        poses = unpack(x)
        error = between(target, between(poses[a], poses[b]))
        return np.einsum('nij,nj->ni', whiten, error)

    def residual(x):
        error = errors(x)
        switches = x[npose:]
        error[loops] *= switches[:, None]
        return np.r_[error.ravel(), (1.-switches)/np.sqrt(SWITCH_PRIOR_VARIANCE)]

    sparsity = lil_matrix((3*len(a)+len(loops), npose+len(loops)), dtype=int)
    for i, (ia, ib) in enumerate(zip(a, b)):
        for j in (ia, ib):
            if j:
                sparsity[3*i:3*i+3, 3*(j-1):3*j] = 1
    for k, i in enumerate(loops):
        sparsity[3*i:3*i+3, npose+k] = 1
        sparsity[3*len(a)+k, npose+k] = 1
    x = np.r_[initial[1:].ravel(), np.ones(len(loops))]
    before = float(residual(x) @ residual(x)/2)
    fit = least_squares(residual, x, jac_sparsity=sparsity.tocsr(), method='trf',
                        tr_solver='lsmr', bounds=(np.r_[np.full(npose, -np.inf), np.zeros(len(loops))],
                                                 np.r_[np.full(npose, np.inf), np.ones(len(loops))]),
                        max_nfev=o.max_nfev, ftol=1e-7, xtol=1e-7, gtol=1e-7)
    valid = bool(fit.success and np.isfinite(fit.x).all() and fit.cost <= before+1e-10)
    result = unpack(fit.x) if valid else initial.copy()
    result[:, 2] = wrap(result[:, 2])
    chi2 = np.sum(errors(fit.x)[loops]**2, axis=1)
    switches = []
    for k, i in enumerate(loops):
        value = float(fit.x[npose+k])
        kept = valid and value >= DIAGNOSTIC_SWITCH_THRESHOLD
        switches.append(dict(constraint_index=int(i), submap=int(a[i]), scan=int(b[i]-m),
                             switch=value, information_scale=value**2, unscaled_chi2=float(chi2[k]),
                             retained=kept, reason=('optimizer_failed' if not valid else
                                                   'switch_retained' if kept else 'switch_suppressed')))
    return result, dict(accepted=valid, reason='converged' if valid else 'optimizer_failed',
                        initial_cost=before, final_cost=float(fit.cost), nfev=fit.nfev,
                        status=fit.status, message=fit.message, switches=switches,
                        switch_prior_mean=1., switch_prior_variance=SWITCH_PRIOR_VARIANCE,
                        max_translation_change_m=float(np.linalg.norm(result[:, :2]-initial[:, :2], axis=1).max()))


def refine_cached_graph(rows, poses, legacy_result, *, robot_id, loop_rejection='off'):
    """Replay the SAME candidate constraints from an own-input graph receipt.

    Off is object identity, with no inspection/mutation. Cache integrity is the
    caller's responsibility (the replay driver checks the original SHA receipts).
    """
    if loop_rejection not in VALUES:
        raise ValueError('UNKNOWN_LOOP_REJECTION')
    if loop_rejection == 'off':
        return legacy_result
    validate_rows(rows, robot_id)
    if any(p.get('robot_id') != robot_id for p in poses):
        raise ValueError('POSE_GRAPH_PEER_INPUT_FORBIDDEN')
    if any(np.asarray(p['pose']).shape != (3,) or not np.isfinite(p['pose']).all()
           or not np.isfinite(p['t']) for p in poses) or any(a['t'] >= b['t'] for a, b in zip(poses, poses[1:])):
        raise ValueError('POSE_GRAPH_INVALID_PATH')
    _, _, old = legacy_result
    diagnostic = copy.deepcopy(old)
    corrected, path = copy.deepcopy(rows), copy.deepcopy(poses)
    if not rows:
        diagnostic.update(loop_rejection=loop_rejection, changed=False,
                          optimization=dict(accepted=False, reason='empty_ledger', switches=[]))
        return corrected, path, diagnostic
    submaps = [{'pose':s['local_pose']} for s in old['submaps']]
    solution, report = optimize_switchable(submaps, rows, old['constraints'], GraphOptions(**old['options']))
    if report['accepted']:
        for row, pose in zip(corrected, solution[len(submaps):]):
            row['pose'] = pose.tolist()
        times = np.array([r['t'] for r in rows])
        for p in path:
            i = int(np.searchsorted(times, p['t'], side='right')-1)
            if i >= 0:
                p['pose'] = compose(corrected[i]['pose'], between(rows[i]['pose'], p['pose'])).tolist()
    for i, sub in enumerate(diagnostic['submaps']):
        sub['global_pose'] = solution[i].tolist()
    diagnostic.update(loop_rejection=loop_rejection, optimization=report, changed=report['accepted'],
                      switch_counts=dict(Counter(s['reason'] for s in report['switches'])))
    return corrected, path, diagnostic
