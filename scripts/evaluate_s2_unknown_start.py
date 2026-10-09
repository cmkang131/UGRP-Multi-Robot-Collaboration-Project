"""Post-run GT scoring only; never imported into controller behavior."""
import json
import math

import numpy as np

from scripts.audit_s2_formal_stops import truth_at, wrap


def traveled(truth, end):
    t = np.asarray([r['t'] for r in truth])
    xy = np.asarray([r['robot_xyz_m'][:2] for r in truth])
    cutoff = float(np.clip(end, t[0], t[-1]))
    samples = np.vstack((xy[t < cutoff], [np.interp(cutoff, t, xy[:, j]) for j in (0, 1)]))
    return float(np.linalg.norm(np.diff(samples, axis=0), axis=1).sum())


def score(record, truth):
    from harness.zone_s2_unknown_start_contract import registration
    criteria = registration()
    threshold = criteria['convergence']['std_xy_m_lte']
    nees_limit = criteria['nees']['chi2_95']
    converged = next((p for p in record.get('poses', [])
                      if p.get('initialized', True) and p['std_xy_m'] <= threshold), None)
    first = None
    if converged:
        gt = truth_at(truth, converged['t_est'])
        error = math.dist([converged['x'], converged['y']], gt[:2])
        first = dict(released_t=converged['t'], estimate_t=converged['t_est'],
            std_xy_m=converged['std_xy_m'], actual_xy_error_m=error,
            actual_yaw_error_deg=abs(math.degrees(wrap(converged['yaw']-gt[2]))),
            wrong_mode=error > criteria['convergence']['wrong_mode_xy_error_m_gt'],
            actual_traveled_before_release_m=traveled(truth, converged['t']),
            actual_traveled_before_estimate_m=traveled(truth, converged['t_est']))
    rows = []
    for q in record.get('global_full_decisions', []):
        p = q['report']; gt = truth_at(truth, p['t_est'])
        error = np.asarray([p['x_m']-gt[0], p['y_m']-gt[1]])
        cov = np.asarray(p.get('cov', []))
        valid = (cov.shape == (3, 3) and np.isfinite(cov).all() and
                 np.linalg.eigvalsh(cov[:2, :2]).min() > 0)
        nees = float(error @ np.linalg.solve(cov[:2, :2], error)) if valid else None
        mode = (p.get('observation_quality') or {}).get('diagnostics', {}).get('pose_estimate', {})
        cluster = np.asarray(mode.get('selected_cluster_cov', []))
        comparable = (nees is not None and mode.get('cluster_count') == 1 and
                      cluster.shape == (3, 3) and np.allclose(cluster[:2, :2], cov[:2, :2], rtol=1e-7, atol=1e-10))
        rows.append(dict(t=q['t'], t_est=p['t_est'], state=q['state'],
            xy_error_m=float(np.linalg.norm(error)), pose_uncertain=q['pose_uncertain'],
            nees_xy=nees, comparable_nees_xy=nees if comparable else None))
    def nees_summary(key):
        data = [r[key] for r in rows if r[key] is not None]
        count = sum(v > nees_limit for v in data)
        return dict(valid=len(data), above_chi2_95=count, exceed_fraction=count/len(data) if data else None)
    no_alarm = [r for r in rows if not r['pose_uncertain'] and
                r['xy_error_m'] > criteria['nees']['unflagged_xy_error_m_gt']]
    return dict(gt_use='posthoc only', convergence_criterion_std_xy_m=threshold,
        first_convergence=first, converged=first is not None,
        actual_distance_until_end_m=traveled(truth, truth[-1]['t']),
        nees_comparable_to_v133=nees_summary('comparable_nees_xy'),
        nees_all_reported_covariances=nees_summary('nees_xy'),
        unflagged_gt_25cm=len(no_alarm), unflagged_rows=no_alarm,
        decision_count=len(rows), decision_rows=rows,
        would_stop=record.get('dev_light_would_stop', {}),
        global_handoff=record.get('particle_sampling', {}).get('handoff'))


def metrics(out, record):
    truth = [json.loads(x) for x in (out/'eval_only/trajectory.jsonl').read_text().splitlines()]
    if not truth:
        return dict(available=False, reason='no evaluation trajectory; retain execution failure')
    return score(record, truth)
