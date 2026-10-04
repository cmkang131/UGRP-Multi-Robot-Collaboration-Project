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

Rule: after the unchanged minimum stop, a fresh own report whose sigma is inside the SAME thresholds as before
(std_xy <= 50 mm, std_yaw <= 3 deg; nothing widened) is accepted as a DR receipt, logged under its own event
(never as a re-observation). Without a fix sigma only grows, so an over-budget report aborts at once with its
own reason. A real fix after the stop keeps the old receipt and event. No report keeps the 8 s timeout.
Inputs: the own pose report only (own RGB + own commands through the v98 provider).

Receipt logging (2026-10-05, log only): every receipt detail also carries the own report mean ``x_m``, ``y_m``,
``yaw_rad`` and the full own covariance ``cov`` (3x3, order x, y, yaw; m^2, m*rad, rad^2, as the particle filter
reports it). They are own control-side data and never enter a decision here. They exist so that an
evaluation-only scorer (``scripts/eval_highpose_receipt_nees.py``, not imported by any harness module) can
compute the NEES of each receipt against the eval-only truth after the run. The receipt is a *sigma-budget
receipt* ("σ 예산 영수증"): the reported sigma stayed inside the 50 mm / 3 deg budget. It is NOT evidence of
accuracy: the particle filter was measured to be over-confident (sigma 3.5-8 mm at 147-178 mm true error).
NEES consistency test: Y. Bar-Shalom, X. R. Li, T. Kirubarajan, "Estimation with Applications to Tracking and
Navigation" (Wiley, 2001), ch. 5.4 (section and page: 미확인).
"""
from __future__ import annotations

import math

from harness.owncam_time import pose_report_fresh

ID = 'v98_high_checkpoint_dr_receipt_v1'
SCHEMA = 'ugrp.v98.high_checkpoint_dr_receipt.v1'
BUDGET_XY_M = .05                       # = the previous checkpoint fix threshold
BUDGET_YAW_RAD = math.radians(3.)       # = the previous checkpoint fix threshold
FIX_EVENT = 'checkpoint_high_reobserved'
DR_EVENT = 'checkpoint_high_dr_receipt'
OVER_EVENT = 'checkpoint_high_dr_over_budget'
OVER_REASON = 'HIGH_CHECKPOINT_DR_BUDGET_EXCEEDED'
RECEIPT_EVENTS = {FIX_EVENT: 'fix', DR_EVENT: 'dr_budget'}


def record():
    return {'id': ID, 'schema': SCHEMA, 'budget_xy_m': BUDGET_XY_M, 'budget_yaw_rad': BUDGET_YAW_RAD,
            'events': [FIX_EVENT, DR_EVENT, OVER_EVENT], 'over_reason': OVER_REASON,
            'receipt': 'fresh fix after the stop, else own DR report within the unchanged 50 mm / 3 deg budget',
            'scope': 'HIGH intermediate checkpoints only; no gate or threshold widened'}


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
    within = (math.isfinite(sxy) and math.isfinite(syaw)
              and sxy <= BUDGET_XY_M and syaw <= BUDGET_YAW_RAD)
    if float(now)-float(started) < min_stop_s:
        return 'wait', detail
    if fix_t is not None and fix_t > fix_after:
        return ('fix' if within else 'wait'), detail
    return ('dr' if within else 'over'), detail
