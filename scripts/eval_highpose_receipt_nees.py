"""Evaluation-only NEES of the v98 HIGH checkpoint receipts ("σ 예산 영수증", sigma-budget receipts).

EVALUATION ONLY. Nothing here is fed back to control: the scorer runs after the simulation loop has ended
(``scripts/run_pair_highpose.student_run_case`` ``finally`` block), reads the eval-only truth that the simulator
backend wrote (``eval_only/<rid>/camera_labels.jsonl``) and writes ``eval_only/dr_receipt_nees.json``. No module
under ``harness/`` imports this file (``tests/test_highpose_receipt_nees.py`` checks it).

Why: the v98 HIGH checkpoint accepts an own report whose sigma is inside the derived 67.43 mm / 2.89 deg budget
(``GATE_LOADED`` 70 mm / 3 deg x (1 - 1.645/sqrt(2000)), decision v6-3; earlier records used 50 mm / 3 deg and are
not pooled) as a DR receipt (``harness/zone_pair_highpose_dr_checkpoint.py``). The scoring below does not use the
budget value. The particle filter was measured to be
over-confident (reported sigma 3.5-8 mm at 147-178 mm true error, independent review P1-3 of PR #363), so such a
receipt says "the filter *thinks* it is inside the budget", not "the robot *is* inside the budget". The
receipt is therefore named a sigma-budget receipt and every one is scored here with the Normalised Estimation
Error Squared,

    NEES = e^T P^-1 e,   e = truth - estimate (yaw error wrapped to (-pi, pi]),

for the 2-DOF position part (x, y; P = the xy block of the reported covariance) and the 3-DOF pose (x, y, yaw).
For a consistent filter with Gaussian error NEES is chi-square distributed with n degrees of freedom, so a value
above the 99.9 % bound is evidence against consistency (a single sample: a screening reference, not a test of
the filter on its own).

Sources (미확인 = not opened while writing this file):
* Y. Bar-Shalom, X. R. Li, T. Kirubarajan, "Estimation with Applications to Tracking and Navigation", Wiley,
  2001: the NEES state-estimation consistency test is in the chapter on estimator evaluation / consistency
  (chapter 5, "5.4" in the common citation); exact section and page numbers: 미확인.
* chi-square quantile constants below are checked against ``scipy.stats.chi2.ppf`` in the unit test; the
  scorer itself does not import scipy.

Frame convention (verified in ``tests/test_highpose_receipt_nees.py`` with a recorded run, see that file): the own
report ``x_m, y_m, yaw_rad`` is the chassis base pose in the static-map world frame, equal to the backend label
``base_position_m[:2]`` and ``yaw = atan2(base_rotation[1][0], base_rotation[0][0])`` (the same derivation as
``experiments/2026-10-01-p01-final-env-check/analyze_p01.py`` and
``experiments/2026-10-03-vo-feasibility/code/vocommon.py``).
"""
from __future__ import annotations

import argparse
import bisect
import hashlib
import json
import math
from pathlib import Path

import numpy as np

from harness.zone_pair_highpose_dr_checkpoint import DR_EVENT, FIX_EVENT, OVER_EVENT

SCHEMA = 'ugrp.v98.receipt_nees.eval_only.v1'
OUTPUT = 'eval_only/dr_receipt_nees.json'
RECEIPT_NAME_KO = 'σ 예산 영수증'
RECEIPT_NAME_EN = 'sigma-budget receipt'
NOTE = ('EVALUATION ONLY. Never fed to control; computed after the run from eval-only truth. Receipts are named '
        '"σ 예산 영수증" (sigma-budget receipt): the filter reported sigma inside the budget. They are NOT accuracy '
        'evidence; the particle filter was measured over-confident (sigma 3.5-8 mm at 147-178 mm error).')
KINDS = {FIX_EVENT: 'fix', DR_EVENT: 'dr_budget', OVER_EVENT: 'over_budget'}
# chi-square upper quantiles, 95 % / 99.9 %. df=2 closed form -2 ln(1-p); df=3 tabulated (verified against scipy in the test).
CHI2 = {2: {'p95': 5.99146454710798, 'p999': 13.815510557964274},
        3: {'p95': 7.8147279032511765, 'p999': 16.26623619623813}}
MAX_TRUTH_GAP_S = .1            # backend labels come every 0.05 s; more than this is flagged, not hidden
FRAME_CONVENTION = ('own report (x_m, y_m, yaw_rad) = chassis base pose in the map world frame = camera_labels '
                    'base_position_m[:2] and atan2(base_rotation[1][0], base_rotation[0][0])')


def _num(v):
    """Strict-JSON float: None for nan/inf (the runner writes with allow_nan=False)."""
    v = float(v)
    return v if math.isfinite(v) else None


def wrap(a):
    return (a + math.pi) % (2*math.pi) - math.pi


def nees(error, cov):
    """e^T P^-1 e for a (n,) error and (n, n) covariance; ``(None, reason)`` when P is not usable."""
    e, p = np.asarray(error, float), np.asarray(cov, float)
    if p.shape != (e.size, e.size) or not (np.isfinite(e).all() and np.isfinite(p).all()):
        return None, 'cov_shape_or_nonfinite'
    p = .5*(p + p.T)
    if float(np.linalg.eigvalsh(p).min()) <= 0.:
        return None, 'cov_not_positive_definite'
    try:
        return float(e @ np.linalg.solve(p, e)), None
    except np.linalg.LinAlgError:
        return None, 'cov_singular'


def sha256(path):
    h = hashlib.sha256()
    with open(path, 'rb') as f:
        for chunk in iter(lambda: f.read(1 << 20), b''):
            h.update(chunk)
    return h.hexdigest()


def load_truth(path):
    """Sorted truth rows ``(t, x, y, yaw)`` of one robot from camera_labels.jsonl (eval only)."""
    rows = []
    with open(path) as f:
        for line in f:
            if not line.strip():
                continue
            r = json.loads(line)
            rot = r['base_rotation']
            rows.append((float(r['t']), float(r['base_position_m'][0]), float(r['base_position_m'][1]),
                         math.atan2(float(rot[1][0]), float(rot[0][0]))))
    rows.sort(key=lambda r: r[0])
    return rows


def nearest(rows, t):
    times = [r[0] for r in rows]
    i = bisect.bisect_left(times, t)
    return min((rows[j] for j in (i - 1, i) if 0 <= j < len(rows)), key=lambda r: abs(r[0] - t))


def receipts(record):
    """(robot id, event) of every FIX / DR / OVER receipt event in the pair controller events of a student record."""
    for session in (record or {}).get('pair') or []:
        for rid, robot in sorted((session.get('robots') or {}).items()):
            for event in robot.get('events') or []:
                if event.get('event') in KINDS:
                    yield rid, event


def score_receipt(rid, event, truth_rows):
    row = {'robot_id': rid, 'event': event['event'], 'receipt': KINDS[event['event']], 'seg': event.get('seg'),
           'sim_s': event.get('sim_s'), 'report_t_est': event.get('report_t_est'), 'status': 'SCORED'}
    est = [event.get(k) for k in ('x_m', 'y_m', 'yaw_rad')]
    cov = event.get('cov')
    if any(v is None for v in est) or cov is None:
        return {**row, 'status': 'NO_ESTIMATE_IN_RECEIPT',
                'reason': 'receipt event has no x_m/y_m/yaw_rad/cov (record from before the log-only fields)'}
    if truth_rows is None:
        return {**row, 'status': 'NO_TRUTH', 'reason': f'eval_only/{rid}/camera_labels.jsonl missing or empty'}
    if event.get('report_t_est') is None:
        return {**row, 'status': 'NO_REPORT_TIME', 'reason': 'receipt event has no report_t_est'}
    t, tx, ty, tyaw = nearest(truth_rows, float(event['report_t_est']))
    gap = t - float(event['report_t_est'])
    ex, ey, eyaw = tx - float(est[0]), ty - float(est[1]), wrap(tyaw - float(est[2]))
    p = np.asarray(cov, float)
    n_xy, why_xy = nees([ex, ey], p[:2, :2]) if p.shape == (3, 3) else (None, 'cov_shape_or_nonfinite')
    n_3, why_3 = nees([ex, ey, eyaw], p)
    sd = np.sqrt(np.maximum(np.diag(p), 0.)) if p.shape == (3, 3) and np.isfinite(p).all() else [float('nan')]*3
    ref_xy, ref_3 = CHI2[2], CHI2[3]
    return {**row, 'truth_t': t, 'truth_gap_s': _num(gap), 'truth_gap_flag': abs(gap) > MAX_TRUTH_GAP_S + 1e-9,
            'error_x_m': _num(ex), 'error_y_m': _num(ey), 'error_xy_m': _num(math.hypot(ex, ey)),
            'error_yaw_rad': _num(eyaw), 'error_yaw_deg': _num(math.degrees(eyaw)),
            'reported_std_xy_m': event.get('std_xy_m'), 'reported_std_yaw_rad': event.get('std_yaw_rad'),
            'sigma_x_m': _num(sd[0]), 'sigma_y_m': _num(sd[1]), 'sigma_yaw_rad': _num(sd[2]),
            'nees_xy_2dof': None if n_xy is None else _num(n_xy), 'nees_xy_error': why_xy,
            'nees_pose_3dof': None if n_3 is None else _num(n_3), 'nees_pose_error': why_3,
            'xy_above_chi2_95': None if n_xy is None else n_xy > ref_xy['p95'],
            'xy_above_chi2_99_9': None if n_xy is None else n_xy > ref_xy['p999'],
            'pose_above_chi2_95': None if n_3 is None else n_3 > ref_3['p95'],
            'pose_above_chi2_99_9': None if n_3 is None else n_3 > ref_3['p999']}


def receipt_nees(out_dir):
    """Score every receipt of the run in ``out_dir``; pure read, returns the JSON-able result dict."""
    out = Path(out_dir)
    record_path = out/'student_record.json'
    result = {'schema': SCHEMA, 'evaluation_only': True, 'fed_to_control': False, 'receipt_name': RECEIPT_NAME_KO,
              'receipt_name_en': RECEIPT_NAME_EN, 'note': NOTE, 'frame_convention': FRAME_CONVENTION,
              'chi2_reference': {'xy_2dof': CHI2[2], 'pose_3dof': CHI2[3],
                                 'source': 'scipy.stats.chi2.ppf(0.95 / 0.999, df) checked in the unit test'},
              'reference': 'Bar-Shalom, Li, Kirubarajan, Estimation with Applications to Tracking and Navigation '
                           '(2001), NEES consistency test (ch. 5.4; section/page unverified: 미확인)',
              'source': {'student_record': str(record_path), 'student_record_sha256': None}, 'truth_files': {},
              'receipts': [], 'summary': {}}
    if not record_path.is_file():
        result['summary'] = summarize([])
        result['summary']['status'] = 'NO_STUDENT_RECORD'
        return result
    result['source']['student_record_sha256'] = sha256(record_path)
    record = json.loads(record_path.read_text())
    truth = {}
    for rid, event in receipts(record):
        if rid not in truth:
            path = out/'eval_only'/rid/'camera_labels.jsonl'
            rows = load_truth(path) if path.is_file() else None
            truth[rid] = rows or None
            if rows:
                result['truth_files'][rid] = {'path': str(path), 'sha256': sha256(path), 'rows': len(rows)}
        try:
            row = score_receipt(rid, event, truth[rid])
        except Exception as exc:  # noqa: BLE001 - one malformed receipt must not hide the others
            row = {'robot_id': rid, 'event': event['event'], 'receipt': KINDS[event['event']], 'seg': event.get('seg'),
                   'sim_s': event.get('sim_s'), 'status': 'SCORE_ERROR',
                   'reason': f'{type(exc).__name__}: {exc}'[:200]}
        result['receipts'].append(row)
    result['summary'] = summarize(result['receipts'])
    return result


def summarize(rows):
    scored = [r for r in rows if r['status'] == 'SCORED']
    xy = [r['nees_xy_2dof'] for r in scored if r.get('nees_xy_2dof') is not None]
    pose = [r['nees_pose_3dof'] for r in scored if r.get('nees_pose_3dof') is not None]
    return {'status': 'OK', 'receipt_count': len(rows), 'scored_count': len(scored),
            'skipped_count': len(rows) - len(scored),
            'undefined_nees_count': len(scored) - len(xy),
            'max_nees_xy_2dof': max(xy) if xy else None, 'max_nees_pose_3dof': max(pose) if pose else None,
            'xy_above_chi2_99_9_count': sum(1 for v in xy if v > CHI2[2]['p999']),
            'pose_above_chi2_99_9_count': sum(1 for v in pose if v > CHI2[3]['p999']),
            'max_error_xy_m': max((r['error_xy_m'] for r in scored if r.get('error_xy_m') is not None), default=None),
            'by_receipt': {k: sum(1 for r in rows if r['receipt'] == k) for k in sorted(set(KINDS.values()))}}


def write_for_run(out_dir):
    """Score the run and write ``<out>/eval_only/dr_receipt_nees.json``; returns the short summary for result.json."""
    out = Path(out_dir)
    result = receipt_nees(out)
    path = out/OUTPUT
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(result, ensure_ascii=False, indent=2, allow_nan=False) + '\n')
    s = result['summary']
    return {'schema': SCHEMA, 'path': OUTPUT, 'count': s['receipt_count'], 'scored': s['scored_count'],
            'max_nees_xy': s['max_nees_xy_2dof'], 'max_nees_pose': s['max_nees_pose_3dof'],
            'evaluation_only': True, 'receipt_name': RECEIPT_NAME_KO}


def main(argv=None):
    p = argparse.ArgumentParser(description=__doc__.split('\n')[0])
    p.add_argument('run_dir', type=Path, help='run directory with student_record.json and eval_only/')
    p.add_argument('--write', action='store_true', help=f'write {OUTPUT} instead of printing')
    args = p.parse_args(argv)
    if args.write:
        print(json.dumps(write_for_run(args.run_dir), indent=2, ensure_ascii=False))
    else:
        print(json.dumps(receipt_nees(args.run_dir), indent=2, ensure_ascii=False))


if __name__ == '__main__':
    main()
