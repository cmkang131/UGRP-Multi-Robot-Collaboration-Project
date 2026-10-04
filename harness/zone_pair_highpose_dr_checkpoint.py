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


def decide(report, now, started, fix_after, min_stop_s):
    """('wait' | 'fix' | 'dr' | 'over', detail). Pure; ``detail`` is None without a usable report."""
    if not (report is not None and pose_report_fresh(report, now) and report.initialized
            and report.last_fix_t is not None):
        return 'wait', None
    sxy, syaw = float(report.std_xy_m), float(report.std_yaw_rad)
    detail = {'std_xy_m': sxy, 'std_yaw_rad': syaw, 'fix_t': float(report.last_fix_t),
              'fix_age_s': float(now)-float(report.last_fix_t), 'report_t_est': float(report.t_est),
              'stop_s': float(now)-float(started)}
    within = (math.isfinite(sxy) and math.isfinite(syaw)
              and sxy <= BUDGET_XY_M and syaw <= BUDGET_YAW_RAD)
    if float(now)-float(started) < min_stop_s:
        return 'wait', detail
    if report.last_fix_t > fix_after:
        return ('fix' if within else 'wait'), detail
    return ('dr' if within else 'over'), detail
