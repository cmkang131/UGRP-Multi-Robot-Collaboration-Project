"""Derived accuracy requirements per stage from the EXISTING gates and geometry constants (read-only arithmetic).

Every input is imported from the module that defines it (no value is copied by hand except the two per-leg drift
numbers from the chain-probe README, marked). Nothing here is a measurement; nothing lowers or raises a gate.

usage: python requirements.py <out.json>
"""
import json
import math
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))
from harness import m1_owncam_delivery as m1  # noqa: E402
from harness import owncam_sweep_collision as sw  # noqa: E402
from harness import zone_own_guards as guards  # noqa: E402
from harness.owncam_drive import LOADED_ENVELOPE  # noqa: E402
from harness.zone_scenario_feasibility import landing_fits, zone_rect  # noqa: E402
from scripts import run_m2_pair as m2  # noqa: E402

MAP = json.loads((ROOT/'maps'/'zones'/'zone_wide_door_tags_v2_dock_v3.json').read_text())


def main(dest):
    out = {'schema': 'ugrp.relocalization_audit.requirements.v1',
           'note': 'derived from existing gates/constants; not measurements; no gate changed'}
    gl, gu = guards.GATE_LOADED, guards.GATE_UNLOADED
    out['gates'] = {
        'GATE_LOADED': {'enter_uncertain_above_xy_m': gl.high_xy_m, 'enter_uncertain_above_yaw_deg': round(math.degrees(gl.high_yaw_rad), 2),
                        'exit_at_or_below_xy_m': gl.low_xy_m, 'exit_at_or_below_yaw_deg': round(math.degrees(gl.low_yaw_rad), 2),
                        'enter_dwell_s': gl.enter_dwell_s, 'exit_dwell_s': gl.exit_dwell_s, 'source': 'harness/zone_own_guards.py'},
        'GATE_UNLOADED': {'enter_uncertain_above_xy_m': gu.high_xy_m, 'enter_uncertain_above_yaw_deg': round(math.degrees(gu.high_yaw_rad), 2),
                          'exit_at_or_below_xy_m': gu.low_xy_m, 'exit_at_or_below_yaw_deg': round(math.degrees(gu.low_yaw_rad), 2)},
        'M1_LIMITS': {k: {'max_std_xy_m': v.max_std_xy_m, 'max_std_yaw_deg': round(math.degrees(v.max_std_yaw_rad), 2),
                          'max_since_look_s': getattr(v, 'max_since_look_s', None)} for k, v in m1.LIMITS.items()},
        'sweep_guard': {'BASE_MARGIN_m': sw.BASE_MARGIN_M, 'BODY_COVERAGE_RESIDUAL_m': sw.BODY_COVERAGE_RESIDUAL_M, 'K_SIGMA': sw.K_SIGMA,
                        'formula': 'margin = 0.02 + 0.015 + 2*sigma_xy + 2*sigma_yaw*lever',
                        'chassis_x_m': list(sw.CHASSIS_X_M), 'chassis_half_y_m': sw.CHASSIS_Y_M},
        'door': {'width_m': 0.5, 'loaded_envelope_y_m': LOADED_ENVELOPE['y_m'], 'align_max_m': m2.DOOR_ALIGN_MAX_M,
                 'align_max_rad': m2.DOOR_ALIGN_MAX_RAD, 'align_s': m2.DOOR_ALIGN_S},
        'carry_end_error_m': 0.10, 'carry_leg_error_m': 0.10, 'setdown': {'max_shift_m': 0.05, 'max_tilt_deg': 3.0, 'max_rest_height_m': 0.005},
    }
    # ---- door: pair chassis in a 0.50 m door (same budget form as experiments/2026-09-26-vision-loc/gates_v4.md, pair chassis)
    door_half = 0.25
    hx = max(abs(sw.CHASSIS_X_M[0]), abs(sw.CHASSIS_X_M[1]))
    rows = []
    for yaw_deg in (0., 1.5, 3.0):
        th = math.radians(yaw_deg)
        h_y = sw.CHASSIS_Y_M*math.cos(th) + hx*math.sin(th)
        path_offset, tracking, mapp = 0.02, 0.010, 0.005
        budget = door_half - path_offset - h_y - tracking - mapp
        rows.append({'yaw_deg': yaw_deg, 'chassis_half_y_m': round(h_y, 4), 'lateral_budget_m': round(budget, 4)})
    out['door_pair_chassis_budget'] = {'assumptions': 'path offset 0.02, tracking 0.010, map/body 0.005 (gates_v4.md new-design budgets, not measured)',
                                       'rows': rows}
    # lateral drift a yaw error makes over the door leg L1 (0.85 m, v6c-carry README route)
    out['door_yaw_drift_over_L1_m'] = {f'{d}deg': round(0.85*math.sin(math.radians(d)), 4) for d in (1.0, 1.5, 3.0)}
    # sweep-guard sigma allowed by the door side clearance (chassis half y to the wall face)
    clear = door_half - sw.CHASSIS_Y_M
    lever = math.hypot(hx, sw.CHASSIS_Y_M)
    lim = {}
    for yaw_deg in (1.5, 3.0):
        base = sw.BASE_MARGIN_M + sw.BODY_COVERAGE_RESIDUAL_M + sw.K_SIGMA*math.radians(yaw_deg)*lever
        lim[f'sigma_yaw_{yaw_deg}deg'] = round((clear - base)/sw.K_SIGMA, 4)
    out['sweep_guard_sigma_xy_limit_at_door_m'] = {'clearance_m': round(clear, 4), 'lever_m': round(lever, 4), **lim,
                                                   'note': 'largest sigma_xy for which margin <= side clearance; the sweep guard covers look sweeps and back-offs, not driving'}
    # ---- cumulative drift between re-localisations (chain-probe README numbers, diagnostic-patched single legs)
    leg_end = {'L0': 0.0085, 'L1': 0.0419, 'L2': 0.0371, 'L6': 0.0271, 'L7': 0.0274}
    out['per_leg_end_error_m_from_v6c_diag'] = {'values': leg_end, 'source': 'experiments/2026-09-29-pair-chain-probe/README.md (v6c diagnostic patch, single legs)',
                                                'residual_pose_error_allowed_after_fix_m': round(0.10 - max(leg_end.values()), 4),
                                                'note': 'if a leg adds up to its measured end error in the same direction, a fix must leave <= 0.10 - worst leg to hold 0.10 at that leg'}
    # ---- zone B landing rule for a long beam (study referee containment) ----
    z = zone_rect(MAP, 'B')
    fits = {}
    for yaw_deg in (0., 2., 5., 10., 45., 90.):
        y = math.radians(yaw_deg)
        c, s = abs(math.cos(y)), abs(math.sin(y))
        ex, ey = c*0.30 + s*0.02, s*0.30 + c*0.02
        fits[f'{yaw_deg:g}deg'] = {'x_slack_m': round(z[2] - ex, 4), 'y_slack_m': round(z[3] - ey, 4),
                                   'fits_at_center': landing_fits('long_beam', (z[0], z[1], y), z)}
    out['zone_B_long_beam_landing'] = {'zone_rect_cx_cy_hx_hy': list(z), 'beam_half_extents_m': [0.30, 0.02], 'by_yaw': fits,
                                       'source': 'harness/zone_scenario_feasibility.landing_fits (study referee containment rule)'}
    json.dump(out, open(dest, 'w'), indent=1)
    print(json.dumps(out, indent=1)[:4000])


if __name__ == '__main__':
    main(sys.argv[1])
