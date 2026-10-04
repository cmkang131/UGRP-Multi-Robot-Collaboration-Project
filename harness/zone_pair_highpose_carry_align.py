"""v98-only: act on the door-axis align only when the own offset is significant; log every loaded-gate check.

Problem (offline replay of the 6727751b ``align_to_carry`` probe through the v98 provider; ground truth used for
scoring only, never here). Both robots reached HIGH and the carry barrier opened at 89.1 s. The first item of the
v3 carry schedule (``zone_final_pair_skill.V3Controller.door_schedule``) is a fixed 6 s door-axis align whose
command corrects the own estimated offset ``dy`` (world y) and heading error ``e_yaw``. The estimated corrections
were r1 -4.1 mm / +0.04 deg and r2 +9.6 mm / +0.18 deg against own sigmas of about 24 mm and 1.1 deg, i.e. noise
(0.2-0.4 sigma), and the two ends of the rigid beam pushed in opposite world directions (beam moved 0.7 mm). The
align command is not the planned pair leg, so ``pair_ok()`` is False while it runs and the provider's yaw
availability fallback switches from ``b['pm+edge']`` (0.00023 rad/s) to ``b['edge']`` (0.0174 rad/s). The own yaw
sigma grew from 1.14 deg to 3.02 deg in 2.9 s and the loaded gate (3 deg) stopped r1 at 92.2 s with
``POSE_UNCERTAIN``, 3.1 s into the 6 s align and before the axial leg (95.6 s). Under the same model the align
interval can never complete with any non-zero command (sigma_yaw ~6 deg at its end, model-predicted).

Rule (no tuned constant): each align component is kept only when its estimated correction differs from zero at the
two-sided 95 % level of the own Gaussian posterior, ``|dy| > Z * sigma_y`` and ``|e_yaw| > Z * sigma_yaw`` with
``Z = 1.959964`` (standard normal 0.975 quantile). An insignificant component is set to zero. With both components
insignificant the align window carries an all-zero ``mecanum`` command: no motion, ``pair_ok()`` stays True, no
fallback inflation. The window, its timing, the 0.5 s pause, the planned leg and its ``pair_plan`` are the parent's,
unchanged (both robots keep the same schedule without any message). ``sigma_y`` is the world-y standard deviation
of the own report covariance at schedule time (``std_xy_m`` if the covariance is unusable, which only makes skipping
more likely); with no usable own sigma the parent's command is kept. A component that is significant still runs
exactly as before (and can still trip the gate; that limit is recorded, not hidden).

The loaded-gate log (``loaded_gate_check``) records, at every ``CommandGuard.check`` that runs under the loaded
profile and evaluates arm/look/motion commands, the own report time (the guard sees a 0.16 s delayed report), its
``std_xy_m`` and ``std_yaw_rad``, the gate state and profile thresholds, the gate classification and whether the
check stopped the pair. Since 2026-10-05 (task B caveat 3) it also records the own report mean ``report_x_m``,
``report_y_m``, ``report_yaw_rad``, so an evaluation can compare the own estimate with the truth at each check. It only
observes.

Inputs: own report (own RGB + own commands), own grasp estimate, static plan, fixed calibration. No peer pose,
no world state, no ground truth. Shared/frozen modules are not modified.
"""
from __future__ import annotations

import math

import numpy as np

ID = 'v98_carry_align_significance_v1'
SCHEMA = 'ugrp.highpose_carry_align.v98.v1'
Z = 1.959963984540054          # standard normal 0.975 quantile (two-sided 95 %); not tuned
ALIGN_EVENT = 'door_align_gate'
GATE_EVENT = 'loaded_gate_check'
ZERO = {'forward': 0., 'left': 0., 'turn': 0.}


def record() -> dict:
    return {'id': ID, 'schema': SCHEMA, 'z': Z, 'events': [ALIGN_EVENT, GATE_EVENT],
            'rule': '|dy| > z*sigma_y and |e_yaw| > z*sigma_yaw per component, else 0; timing/pair_plan unchanged',
            'gate_thresholds_changed': False, 'shared_sources_modified': False}


def _finite(*values) -> bool:
    return all(isinstance(v, (int, float)) and not isinstance(v, bool) and math.isfinite(v) for v in values)


def own_sigmas(report):
    """(sigma_y_world_m, sigma_yaw_rad, source) from the own report, or None when it carries no usable sigma."""
    if report is None or not getattr(report, 'initialized', False):
        return None
    yaw = getattr(report, 'std_yaw_rad', None)
    if not _finite(yaw) or yaw < 0:
        return None
    cov = getattr(report, 'cov', ())
    try:
        var_y = float(cov[1][1])
    except (TypeError, IndexError, ValueError):
        var_y = float('nan')
    if _finite(var_y) and var_y >= 0:
        return math.sqrt(var_y), float(yaw), 'cov_yy'
    xy = getattr(report, 'std_xy_m', None)
    if _finite(xy) and xy >= 0:
        return float(xy), float(yaw), 'std_xy_m'
    return None


def align_command(motion_loaded, yaw, dy, e_yaw):
    """The parent's align command (``V3Controller.door_schedule``) for the given correction; same code path."""
    from harness import zone_final_pair_skill as skill
    from harness.owncam_carry_v6e import lag_travel
    mp = motion_loaded
    tau_axis = np.asarray(mp.get('tau_axis_s', [mp['tau_s']]*3), float)
    effective_s = np.array([lag_travel(skill.m2.DOOR_ALIGN_S, 1., tau, mp['tau_stop_s']) for tau in tau_axis])
    v = np.array([math.sin(yaw)*dy, math.cos(yaw)*dy, e_yaw]) / effective_s
    u = skill.motor_command(mp, v)
    return dict(zip(('forward', 'left', 'turn'), map(float, u)))


def gate_schedule(ctl, schedule, t0):
    """Return the parent's schedule with insignificant align components zeroed (decision logged and claimed)."""
    claim = ctl.claims.get('door_align') or {}
    if not schedule or not _finite(claim.get('dy_m'), claim.get('e_yaw_rad')):
        return schedule
    (a0, a1, align), rest = schedule[0], list(schedule[1:])
    dy, e_yaw = float(claim['dy_m']), float(claim['e_yaw_rad'])
    report = ctl.port.own.last_report
    sig = own_sigmas(report)
    decision = {'schema': SCHEMA, 'z': Z, 'dy_m': dy, 'e_yaw_rad': e_yaw, 'parent_cmd': dict(align),
                'report_t_est': None if report is None else round(float(report.t_est), 4)}
    if sig is None:
        decision.update(applied=False, reason='NO_OWN_SIGMA', cmd=dict(align))
        new = align
    else:
        sigma_y, sigma_yaw, source = sig
        keep_lat, keep_yaw = abs(dy) > Z*sigma_y, abs(e_yaw) > Z*sigma_yaw
        if keep_lat and keep_yaw:
            new = align
        elif not keep_lat and not keep_yaw:
            new = dict(ZERO)
        else:
            new = align_command(ctl.v3_params['motion_loaded'], float(ctl.grasp_estimate[2]),
                                dy if keep_lat else 0., e_yaw if keep_yaw else 0.)
        decision.update(applied=True, sigma_y_m=sigma_y, sigma_yaw_rad=sigma_yaw, sigma_source=source,
                        keep_lateral=keep_lat, keep_yaw=keep_yaw, cmd=dict(new))
    if new is not align:
        from sim.camera_robot_port import validate_raw_action
        validate_raw_action({'kind': 'mecanum', **new, 'duration_s': .15}, allow_reverse=True, allow_mecanum=True)
    claim['significance'] = decision
    ctl.log(ctl.rid, ALIGN_EVENT, t0, **decision)
    return [(a0, a1, new), *rest]


def _r(value, scale=1., nd=4):
    return round(float(value)*scale, nd) if _finite(value) else None


def log_gate_check(guard, now, commands, out):
    """Observation only: one ``loaded_gate_check`` event per loaded-profile command check (see module doc)."""
    try:
        ep, own = guard.ep, guard.ep.own
        if guard.approach or not any(c.get('kind') in ('arm', 'look', 'mecanum', 'drive') for c in commands):
            return
        gate, report = own.gate, own.last_report
        p = gate.profile
        initialized = bool(getattr(report, 'initialized', False))
        sxy, syaw = getattr(report, 'std_xy_m', None), getattr(report, 'std_yaw_rad', None)
        ep.log(own.robot_id, GATE_EVENT, now,
               state=getattr(ep.controller, 'state', None), seg=getattr(ep.controller, 'seg', None),
               report_t_est=_r(getattr(report, 't_est', None)),
               report_x_m=_r(getattr(report, 'x_m', None), nd=5), report_y_m=_r(getattr(report, 'y_m', None), nd=5),
               report_yaw_rad=_r(getattr(report, 'yaw_rad', None), nd=6), std_xy_m=_r(sxy, nd=5),
               std_yaw_rad=_r(syaw, nd=6), std_yaw_deg=_r(syaw, 180./math.pi, 3),
               fix_age_s=_r(getattr(report, 'fix_age_s', None), nd=3),
               gate_state=gate.state, gate_ok=bool(gate.ok), profile=p.name,
               high_xy_m=p.high_xy_m, low_xy_m=p.low_xy_m, high_yaw_rad=p.high_yaw_rad, low_yaw_rad=p.low_yaw_rad,
               classify=gate.classify(initialized, sxy, syaw),
               moving=any(c.get('kind') == 'mecanum' and any(c.get(k, 0.) != 0. for k in ('forward', 'left', 'turn'))
                          for c in commands),
               passed=out == commands and not ep.terminal, terminal=bool(ep.terminal))
    except Exception as exc:          # noqa: BLE001 - a log must never change the run
        try:
            guard.ep.log(guard.ep.own.robot_id, GATE_EVENT, now, log_error=type(exc).__name__)
        except Exception:             # noqa: BLE001
            pass
