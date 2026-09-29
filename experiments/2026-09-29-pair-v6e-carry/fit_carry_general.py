"""Cal-cohort fit of the v6g ``carry_dr_general`` model: lateral deadband, cross-axis drift ratio, yaw-flag biases.

Inputs (recorded raws, eval-only GT used as the calibration target ONLY; no hA / hB / hC / hD / grid raw is read):
  the stage-F raws recorded with render profile floor_light_v1: cal placement (y 0.03, heading 0) and cal2 / cal3 / cal4
  (y offsets 0.08 / -0.01 / 0.14, beam heading 0 / +0.03 / -0.03 rad). Shadow-profile raws are not mixed in.
Method:
  1 steer phase (own-estimate route-line correction, |left| < 0.03, ~5.9 s): the loaded plant does not follow tiny lateral commands
    linearly. Model: body-lateral travel = gain_yy * u * r(|u|) * Teff with the breakaway ramp
    r = clip((|u| - c0)/(u1 - c0), 0, 1) (full calibrated gain above u1, nothing below c0); (c0, u1) least squares over case-robots
    (Teff = T - tau(1 - exp(-T/tau)), tau 0.8 s loaded).
  2 drift ratio: leg-phase (planned leg) residual of the PF body-cross-axis travel against GT, divided by the GT travel along the
    commanded axis (Thrun et al. 2005 alpha-type distance-proportional spread; AMCL omni alpha5); cell-balanced RMS.
  3 yaw flags: exactly fit_carry_pair_yaw.py (ratio through origin, cell-balanced RMS rate per variant) on the same raws.
Output: carry_general_fit.json (read by harness/owncam_carry_v6e.py when carry_dr_general is on) + carry_general_fit_rows.json.
"""
import hashlib
import json
import math
import sys
from pathlib import Path

import numpy as np

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[1]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(HERE))
sys.path.insert(0, str(HERE/'analysis'))
import fit_carry_pair_yaw as pfit  # noqa: E402
import y_error_phases as yph  # noqa: E402

OUT = Path('/Users/changmin/projects/ugrp/outputs')
FIT_RAWS = ['ece01311-fcal', '7cecaf9b-fcal2', '7cecaf9b-fcal3', '7cecaf9b-fcal4']   # floor_light_v1 raws only (stage F)
DIAGNOSTIC_RAWS = ['4fac772d-yawhA']         # scored by the fitted model, never fitted
GAIN_YY = 1.0159                             # calibration_loop_v2 motion_loaded gain[1][1]
TAU = .8


def raw_paths(names):
    return [OUT/f'pair-stage-probes-{n}' for n in names if (OUT/f'pair-stage-probes-{n}').exists()]


def teff(T):
    return T - TAU*(1 - math.exp(-T/TAU))


def ramp(u, c0, u1):
    return np.clip((np.abs(u) - c0)/max(u1 - c0, 1e-9), 0., 1.)


def fit_deadband(steer):
    u = np.array([r['u_left'] for r in steer]); T = np.array([teff(r['T']) for r in steer])
    gt = np.array([r['steer']['gt'][1] for r in steer])
    best = None
    for c0 in np.arange(0., .0121, .0002):
        for u1 in np.arange(c0 + .004, .0501, .001):
            m = GAIN_YY*u*ramp(u, c0, u1)*T
            rss = float(np.sum((gt - m)**2))
            if best is None or rss < best[0]:
                best = (rss, float(c0), float(u1))
    lin = float(np.sum((gt - GAIN_YY*u*T)**2))
    return best, lin, len(u)


def score_deadband(steer, c0, u1):
    u = np.array([r['u_left'] for r in steer]); T = np.array([teff(r['T']) for r in steer])
    gt = np.array([r['steer']['gt'][1] for r in steer]); pf = np.array([r['steer']['pf'][1] for r in steer])
    m = GAIN_YY*u*ramp(u, c0, u1)*T
    return dict(n=len(u), rms_new_mm=1e3*float(np.sqrt(np.mean((gt - m)**2))), rms_linear_pf_mm=1e3*float(np.sqrt(np.mean((gt - pf)**2))),
                mean_signed_new_mm=1e3*float(np.mean(np.sign(u)*(m - gt))), mean_signed_linear_mm=1e3*float(np.mean(np.sign(u)*(pf - gt))))


def fit_drift(rows_phase):
    per = {}
    for r in rows_phase:
        b = r['leg_ph']
        if r['lateral_leg']:
            res, dist = b['gt'][0] - b['pf'][0], abs(b['gt'][1])          # forward drift while moving laterally
        else:
            res, dist = b['gt'][1] - b['pf'][1], abs(b['gt'][0])          # lateral drift while moving forward
        if dist < .3:
            continue
        per.setdefault(r['cell'], []).append(res/dist)
    cells = {k: float(np.sqrt(np.mean(np.square(v)))) for k, v in per.items()}
    return float(np.sqrt(np.mean([v**2 for v in cells.values()]))), cells, {k: len(v) for k, v in per.items()}


def main():
    raws = raw_paths(FIT_RAWS)
    print('fit raws:', [r.name for r in raws])
    phase = yph.collect([str(r) for r in raws])
    (rb, c0, u1), lin, n = fit_deadband(phase)
    print(f'steer phase: {n} case-robots; deadband c0 {c0:.4f} u1 {u1:.4f} rms {1e3*math.sqrt(rb/n):.2f} mm (linear model {1e3*math.sqrt(lin/n):.2f} mm)')
    drift, drift_cells, drift_n = fit_drift(phase)
    print(f'drift ratio std {drift:.4f} m/m  per cell {drift_cells} n {drift_n}')
    diag = yph.collect([str(p) for p in raw_paths(DIAGNOSTIC_RAWS)])
    diag_score = score_deadband(diag, c0, u1) if diag else None
    print('diagnostic (hA, not fitted): ', diag_score)

    # yaw flags: the pair fit on the same raws
    pfit.FIT_RAWS = ['ece01311-fcal', '7cecaf9b-fcal2', '7cecaf9b-fcal3', '7cecaf9b-fcal4']   # floor_light_v1 raws only (stage F)
    rows1 = pfit.rows_for([r.name.removeprefix('pair-stage-probes-') for r in raws], 1.)
    pairs = [(r['d_slope_total'], r['d_rel_gt']) for r in rows1 if r['d_rel_gt'] is not None]
    s, y = np.array([p[0] for p in pairs]), np.array([p[1] for p in pairs])
    ratio = float(s @ y/(y @ y))
    print('slope ratio %.4f corr %.4f n %d' % (ratio, np.corrcoef(s, y)[0, 1], len(pairs)))
    for r in rows1:
        r['edge'] = r['d_slope_total']/ratio
    out = {'slope_to_yaw_ratio': ratio, 'b_rad_s': {}, 'estimators': {}, 'deadband_cmd': {'c0': [0., c0, 0.], 'u1': [0., u1, 0.]},
           'drift_ratio_std': drift}
    for name, f in pfit.ESTIMATORS.items():
        b, per, cnt = pfit.balanced(rows1, f)
        out['estimators'][name] = {'balanced_rms_rad_s': b, 'per_cell_rms_rad_s': per, 'n_per_cell': cnt}
        if name != 'e0_registered':
            out['b_rad_s'][name] = b
        print('  %-14s b = %.5f  per cell %s' % (name, b, {k: round(v*1e3, 2) for k, v in per.items()}))
    out['steer_phase'] = {'n_case_robots': n, 'rms_mm_new': 1e3*math.sqrt(rb/n), 'rms_mm_linear_model': 1e3*math.sqrt(lin/n),
                          'diagnostic_not_fitted': diag_score}
    out['drift'] = {'per_cell_rms': drift_cells, 'n_per_cell': drift_n}
    out['rule'] = ('deadband ramp (c0, u1) least squares on steer-phase GT body-lateral travel; drift_ratio_std = cell-balanced RMS of '
                   'leg-phase cross-axis residual per GT axis travel; ratio and b as fit_carry_pair_yaw.py on the same raws')
    out['inputs'] = [{'raw': r.name, 'cases_jsonl_sha256': hashlib.sha256((r/'cases.jsonl').read_bytes()).hexdigest()} for r in raws]
    out['not_read'] = 'hB, hC, hD, the 33-cell grid; hA only as a diagnostic score of the deadband (never fitted)'
    out['n_case_robots'] = len(rows1)
    (HERE/'carry_general_fit.json').write_text(json.dumps(out, indent=1))
    json.dump(rows1, open(HERE/'carry_general_fit_rows.json', 'w'), indent=0)


if __name__ == '__main__':
    main()
