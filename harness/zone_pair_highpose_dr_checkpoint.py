"""v98 HIGH intermediate checkpoint: own dead-reckoning (DR) budget receipt.

Why (offline, 2026-10-04, ground truth used for evaluation only): at HIGH the held beam fills the own image
from the top down to row ~170 (r1) / ~175 (r2). Below it the measured loaded HIGH camera model sees only the
floor 0.285-0.42 m ahead of the chassis, i.e. under the beam between the two robots, where no wall can be.
The static map therefore predicts 0 wall columns at every pose of the registered route, and the v98 OpenCV
observer found 0 wall columns in all 964 recorded loaded HIGH frames (v92 collection, pans 1480/1500/1520,
both robots). Panning does not help: with the beam held, 20 pan pulses turn the camera only 0.45 deg in
the world (the chassis counter-rotates 1.35 deg), no loaded camera model exists for pan != 1500, and the pair
guard forbids a relook while gripped. A fresh fix after a HIGH stop is therefore impossible, so the old
receipt (``last_fix_t`` after the stop) always ended in ``HIGH_CHECKPOINT_REOBSERVE_TIMEOUT``.

Rule: after the unchanged minimum stop, a fresh own report whose sigma is inside the DR budget is accepted as a DR
receipt, logged under its own event (never as a re-observation). Without a fix sigma only grows, so an over-budget
report aborts at once with its own reason. A real fix after the stop inside the fix thresholds (50 mm / 3 deg) keeps
the old receipt event; a fresh fix over them is judged as a DR report against the budget, so the one abort boundary
is the budget (#363 author agreement, issuecomment-5983294916). No report keeps the 8 s timeout. The 50 mm / 3 deg
fix thresholds are the pre-grasp align/close fix thresholds ``zone_pair_grasp.FIX_STD_XY_M`` / ``FIX_STD_YAW_RAD``,
copied as literals into the HIGH re-observe check by v96 48c18dd1; they were never derived for the carry and stay
unchanged here, as does the preclose gate.

DR budget (coordinator decision 5, 2026-10-04: one derivation shared with the sigma re-fix,
``zone_pair_highpose_refix``): the loaded gate in force (``GATE_LOADED`` 70 mm / 3 deg) times (1 - 1.645/sqrt(N)), the
one-sided 95 % Monte-Carlo margin between two independent N-particle spread estimates, N = the registered particle
count (``owncam_localizer.DEFAULT_PARAMS['particles']`` = 2000): 67.43 mm / 2.89 deg. This replaces the earlier 50 mm /
3 deg DR receipt (the old fix threshold reused). The margin is the one that makes a PREDICTED sigma inside the budget
land inside the gate (one-sided 95 %); a realized report has no prediction error, so the derivation-consistent
realized threshold would be the gate itself. By the one-value rule (coordinator decision v6-3, #363 author agreement
issuecomment-5983294916) realized reports are judged against the same budget too: a realized 67.4-70 mm report aborts
(or requests the re-fix), the conservative side; the band is recorded in ``record()``. All sigmas so far are the
over-confident particle-filter sigmas, so the budget, the pair entry 0.05 m and the arrival-confirm thresholds are
re-validated after the PF integration diff (measured gain + registered noise); results across this change are not
pooled with earlier v98 records.
Inputs: the own pose report only (own RGB + own commands through the v98 provider).

Receipt logging (2026-10-05, log only): every receipt detail also carries the own report mean ``x_m``, ``y_m``,
``yaw_rad`` and the full own covariance ``cov`` (3x3, order x, y, yaw; m^2, m*rad, rad^2, as the particle filter
reports it). They are own control-side data and never enter a decision here. They exist so that an
evaluation-only scorer (``scripts/eval_highpose_receipt_nees.py``, not imported by any harness module) can
compute the NEES of each receipt against the eval-only truth after the run. The receipt is a *sigma-budget
receipt* ("σ 예산 영수증"): the reported sigma stayed inside the 67.43 mm / 2.89 deg budget. It is NOT evidence of
accuracy: the particle filter was measured to be over-confident (sigma 3.5-8 mm at 147-178 mm true error).
NEES consistency test: Y. Bar-Shalom, X. R. Li, T. Kirubarajan, "Estimation with Applications to Tracking and
Navigation" (Wiley, 2001), ch. 5.4 (section and page: 미확인).
"""
from __future__ import annotations

import math

from harness.owncam_localizer import DEFAULT_PARAMS
from harness.owncam_time import pose_report_fresh
from harness.zone_own_guards import GATE_LOADED

ID = 'v98_high_checkpoint_dr_receipt_v2'
SCHEMA = 'ugrp.v98.high_checkpoint_dr_receipt.v2'
FIX_XY_M = .05                          # fresh-fix receipt: the previous checkpoint fix threshold, unchanged
FIX_YAW_RAD = math.radians(3.)
MC_Z = 1.645                            # one-sided 95 %
N_PARTICLES = int(DEFAULT_PARAMS['particles'])


def mc_margin(n):
    """Relative one-sided 95 % error of the difference of two independent n-particle spread estimates."""
    return MC_Z/math.sqrt(float(n))


def budget(n):
    keep = 1.-mc_margin(n)
    return GATE_LOADED.high_xy_m*keep, GATE_LOADED.high_yaw_rad*keep


BUDGET_XY_M, BUDGET_YAW_RAD = budget(N_PARTICLES)     # DR receipt: 67.43 mm / 2.89 deg (decision 5)
FIX_EVENT = 'checkpoint_high_reobserved'
DR_EVENT = 'checkpoint_high_dr_receipt'
OVER_EVENT = 'checkpoint_high_dr_over_budget'
OVER_REASON = 'HIGH_CHECKPOINT_DR_BUDGET_EXCEEDED'
RECEIPT_EVENTS = {FIX_EVENT: 'fix', DR_EVENT: 'dr_budget'}


def record():
    return {'id': ID, 'schema': SCHEMA, 'budget_xy_m': BUDGET_XY_M, 'budget_yaw_rad': BUDGET_YAW_RAD,
            'fix_xy_m': FIX_XY_M, 'fix_yaw_rad': FIX_YAW_RAD, 'gate': 'GATE_LOADED high 70 mm / 3 deg',
            'mc_z': MC_Z, 'n_particles': N_PARTICLES,
            'events': [FIX_EVENT, DR_EVENT, OVER_EVENT], 'over_reason': OVER_REASON,
            'receipt': 'fresh fix after the stop within 50 mm / 3 deg, else own DR report (a voided fix time counts)'
                       ' within the derived budget',
            'derivation': 'gate x (1 - 1.645/sqrt(N)); shared with zone_pair_highpose_refix (decision 5, 2026-10-04)',
            'scope': 'HIGH intermediate checkpoints only; the DR receipt moved from 50 mm to the derived budget'
                     ' by coordinator decision 5; the gate and the fix thresholds are unchanged',
            'realized_report': 'judged against the same budget (one value, decision v6-3); a realized 67.4-70 mm'
                               ' report aborts or requests the re-fix (conservative band, recorded)',
            'fresh_fix_over_fix_threshold': 'judged as a DR report against the budget (one abort boundary)',
            'revalidate': 'after the PF integration diff, with the pair entry 0.05 m and the arrival-confirm'
                          ' thresholds; not pooled with earlier v98 records'}


def _own_estimate(report):
    """Log-only copy of the own report mean and covariance; ``None`` fields when absent or not finite.

    Never raises and never feeds a decision (``decide`` computes its kind from the sigma fields only).
    """
    out = {'x_m': None, 'y_m': None, 'yaw_rad': None, 'cov': None}
    try:
        for key in ('x_m', 'y_m', 'yaw_rad'):
            v = float(getattr(report, key))
            out[key] = v if math.isfinite(v) else None
        cov = getattr(report, 'cov', None)
        if cov is not None and len(cov) == 3:
            rows = [[float(v) for v in row] for row in cov]
            if all(len(row) == 3 for row in rows) and all(math.isfinite(v) for row in rows for v in row):
                out['cov'] = rows
    except Exception:  # noqa: BLE001 - log only; the decision below must not depend on it
        pass
    return out


def decide(report, now, started, fix_after, min_stop_s):
    """('wait' | 'fix' | 'dr' | 'over', detail). Pure; ``detail`` is None without a usable report.

    ``last_fix_t is None`` on an initialized fresh report means "no fix since the stop": the runtime's
    checkpoint calls ``begin_relocalization`` (vision_pose_source_p03), which keeps the predicted belief and
    its sigma but sets ``_pf.last_scan_t = None`` to void the previous fix receipt. That is a DR report.
    """
    if not (report is not None and pose_report_fresh(report, now) and report.initialized):
        return 'wait', None
    fix_t = report.last_fix_t
    sxy, syaw = float(report.std_xy_m), float(report.std_yaw_rad)
    detail = {'std_xy_m': sxy, 'std_yaw_rad': syaw, 'fix_t': None if fix_t is None else float(fix_t),
              'fix_age_s': None if fix_t is None else float(now)-float(fix_t),
              'fix_receipt_voided': fix_t is None, 'report_t_est': float(report.t_est),
              'stop_s': float(now)-float(started), **_own_estimate(report)}
    finite = math.isfinite(sxy) and math.isfinite(syaw)
    if float(now)-float(started) < min_stop_s:
        return 'wait', detail
    if fix_t is not None and fix_t > fix_after and finite and sxy <= FIX_XY_M and syaw <= FIX_YAW_RAD:
        return 'fix', detail
    # No fix since the stop, or a fresh fix over the fix thresholds: one abort boundary, the derived budget.
    return ('dr' if finite and sxy <= BUDGET_XY_M and syaw <= BUDGET_YAW_RAD else 'over'), detail
