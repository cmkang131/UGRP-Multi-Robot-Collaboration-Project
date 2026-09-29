"""Yaw / xy uncertainty budget with a set-down re-localisation (arithmetic only; no simulator, no images).

Model (same form as the v6e/v6g README analysis, experiments/2026-09-29-pair-v6e-carry/README.md, branch claude/pair-v6g):
    sigma_yaw(t) = sqrt(sigma0^2 + (b t)^2)          b = constant yaw-rate bias std of the filter  (rad/s)
    sigma_xy(t)  = sqrt(sigma0_xy^2 + (k t)^2)       k fitted from the leg-end sigmas quoted in the v6g smoke table
Gate: GATE_LOADED sigma_yaw > 3 deg (0.05236 rad) = "self pose uncertain" (harness/zone_own_guards.py).
Inputs are quoted, not measured here. The re-localisation result sigma0 after a set-down is an ASSUMPTION (three values are tried).

usage: python sigma_budget.py <out.json>
"""
import json
import math
import sys

GATE_YAW = math.radians(3.0)
LEGS = {'L0': 18.5, 'L1': 24.4, 'L2': 23.3, 'L3': 20.75, 'L4': 20.75, 'L5': 20.75, 'L6': 21.15, 'L7': 21.15}   # live carry seconds (v6e README, yaw section)
B_MRAD = {'registered_E0_cal2': 2.33, 'registered_E0_v6g_refit': 2.55, 'v6g_pm+edge': 2.04, 'v6e_pm+edge_4fac772d': 1.56}
SIGMA0_DEG = {'no_new_info(e2e prior 0.6deg)': 0.6, 'VIS3 yaw p90 2.1deg -> sigma 1.3deg': 1.3, 'pessimistic sigma=p90 2.1deg': 2.1}
CELL_B_MRAD = {'nominal': 1.1, 'yaw+/same': 2.0, 'lat-/opp': 3.5}      # cell-wise physical yaw drift rates (v6e README (a) & v6g fit table)


def t_gate(b, sigma0):
    return math.sqrt(max(GATE_YAW ** 2 - sigma0 ** 2, 0.)) / b


def min_resets(times, budget):
    """Greedy split of consecutive legs into blocks each <= budget seconds (a block may not be split inside a leg)."""
    blocks, cur = [], 0.
    for name, t in times.items():
        if t > budget:
            blocks.append((name, t, 'LEG_ALONE_OVER_BUDGET'))
            cur = 0.
            continue
        if cur + t > budget:
            blocks.append(('|', cur, 'reset'))
            cur = 0.
        cur += t
    return blocks


def main(out):
    res = {'gate_deg': 3.0, 'legs_s': LEGS, 'total_carry_s': round(sum(LEGS.values()), 1), 'table': [], 'cells': {}}
    for bn, b in B_MRAD.items():
        for sn, s0 in SIGMA0_DEG.items():
            bb, s = b * 1e-3, math.radians(s0)
            tg = t_gate(bb, s)
            over = [k for k, t in LEGS.items() if t > tg]
            end_sigma = {k: round(math.degrees(math.sqrt(s ** 2 + (bb * t) ** 2)), 2) for k, t in LEGS.items()}
            res['table'].append({'b_mrad_s': b, 'b_name': bn, 'sigma0': sn, 'gate_reached_after_s': round(tg, 1),
                                 'legs_longer_than_budget': over, 'leg_end_sigma_yaw_deg': end_sigma})
    # no reset at all: from the e2e prior
    for bn, b in B_MRAD.items():
        bb = b * 1e-3
        res.setdefault('no_reset', {})[bn] = {'gate_reached_after_s': round(t_gate(bb, math.radians(0.6)), 1),
                                              'sigma_yaw_deg_at_route_end': round(math.degrees(math.sqrt(math.radians(0.6) ** 2 + (bb * sum(LEGS.values())) ** 2)), 1)}
    # physical (true) yaw drift per leg in the three cells, if the belief were reset exactly at each leg start
    for cn, cb in CELL_B_MRAD.items():
        res['cells'][cn] = {k: round(math.degrees(cb * 1e-3 * t), 2) for k, t in LEGS.items()}
        res['cells'][cn]['seconds_to_3deg'] = round(GATE_YAW / (cb * 1e-3), 1)
    # xy: k from v6g smoke (start 0.030 m; L0 end 0.036, L1 end 0.047)
    k_l0 = math.sqrt(0.036 ** 2 - 0.030 ** 2) / 18.5
    k_l1 = math.sqrt(0.047 ** 2 - 0.030 ** 2) / 24.4
    res['xy'] = {'k_mm_per_s_L0': round(k_l0 * 1e3, 2), 'k_mm_per_s_L1': round(k_l1 * 1e3, 2)}
    for s0 in (0.030, 0.038):
        res['xy'][f'sigma_xy_end_L1_from_{int(s0*1000)}mm_cm'] = round(100 * math.sqrt(s0 ** 2 + (k_l1 * 24.4) ** 2), 1)
    # extra set-down inside L1 (door threshold) -> two half legs
    res['split_L1_in_two_s'] = {'legs': [12.2, 12.2], 'sigma_yaw_end_deg_v6g_b2.04_s0_1.3': round(math.degrees(math.sqrt(math.radians(1.3) ** 2 + (2.04e-3 * 12.2) ** 2)), 2)}
    json.dump(res, open(out, 'w'), indent=1, ensure_ascii=False)
    for r in res['table']:
        if r['sigma0'].startswith('VIS3'):
            print(f"b={r['b_mrad_s']:.2f} ({r['b_name']}): gate after {r['gate_reached_after_s']} s; legs over: {r['legs_longer_than_budget']}")
    print(res['no_reset'])
    print(res['cells'])
    print(res['xy'], res['split_L1_in_two_s'])


if __name__ == '__main__':
    main(sys.argv[1])
