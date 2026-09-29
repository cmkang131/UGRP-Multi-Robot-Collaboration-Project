"""Pure-python checks of the carry-relocalization B1 measurement (no renderer, no torch, no physics)."""
import ast
import math
import sys
from pathlib import Path

import numpy as np

ROOT = Path(__file__).resolve().parents[1]
B1 = ROOT / 'experiments' / '2026-09-29-carry-relocalization-b1'
sys.path.insert(0, str(B1))
import analyze  # noqa: E402
import common  # noqa: E402


def _literal(path: Path, name: str):
    for node in ast.parse(path.read_text()).body:
        if isinstance(node, ast.Assign) and any(getattr(t, 'id', None) == name for t in node.targets):
            return ast.literal_eval(node.value)
    raise KeyError(name)


def test_sweep_and_look_constants_follow_the_controller():
    assert common.SWEEP_PANS == _literal(ROOT / 'scripts/run_m2_pair.py', 'PREGRASP_PANS_V2')
    assert _literal(ROOT / 'scripts/run_m2_pair.py', 'PREGRASP_FIX_STD_M') == analyze.ACCEPT_STD_XY_M
    assert _literal(ROOT / 'harness/owncam_drive.py', 'LOOK_P20') == {3: 1072, 4: 2400, 5: 1482}
    assert _literal(ROOT / 'harness/owncam_drive.py', 'SEARCH_POSE') == {1: 2000, 3: 740, 4: 2320, 5: 1320, 6: 1500}


def test_start_error_cells_are_deterministic_and_bounded():
    for cell, lim_xy, lim_yaw in (('S', .05, 3.), ('L', .10, 6.)):
        a, b = common.offsets(cell, 40, 7), common.offsets(cell, 40, 7)
        assert np.array_equal(a, b) and not np.array_equal(a, common.offsets(cell, 40, 8))
        assert np.abs(a[:, :2]).max() <= lim_xy and np.degrees(np.abs(a[:, 2])).max() <= lim_yaw
    y = common.offsets('Y', 6, 0)
    assert np.allclose(np.abs(y[:, 1]), .05) and np.allclose(y[:, [0, 2]], 0) and set(np.sign(y[:, 1])) == {-1., 1.}


def _runs(pos_m, yaw_deg, std_xy=0.02, std_yaw_deg=1.0):
    return [{'final_err_xy': p, 'final_err_yaw': math.radians(y), 'final_std_xy': std_xy, 'final_std_yaw': math.radians(std_yaw_deg),
             'start_err': [0.03, 0.0, 0.02], 'frames': [{'err_xy': p, 'err_yaw': math.radians(y), 'std_xy': std_xy, 'std_yaw': math.radians(std_yaw_deg)}]}
            for p, y in zip(pos_m, yaw_deg)]


def test_tiers_follow_the_registered_limits():
    n = 40
    assert analyze.tier(analyze.stats(_runs([.03] * n, [1.0] * n))) == 'A'
    assert analyze.tier(analyze.stats(_runs([.06] * n, [1.0] * n))) == 'B'          # over 5 cm, inside the 7 cm carry gate
    assert analyze.tier(analyze.stats(_runs([.03] * n, [2.5] * n))) == 'B'          # over 2 deg, inside 3 deg
    assert analyze.tier(analyze.stats(_runs([.09] * n, [1.0] * n))) == 'X'
    assert analyze.tier(analyze.stats(_runs([.03] * (n - 6) + [.30] * 6, [1.0] * n))) == 'X'    # 15 % wrong runs
    # wrong AND flagged is a loud failure: still counted as failure, but not silent
    s = analyze.stats(_runs([.03] * 30 + [.30] * 2, [1.0] * 32, std_xy=0.02)[:30] + _runs([.30] * 2, [1.0] * 2, std_xy=0.5))
    assert s['fail_rate'] > 0 and s['silent_fail_rate'] == 0 and s['flagged_rate'] > 0


def test_budget_matches_pr277_table_and_partitions_legs():
    tg = analyze.t_gate_s(1.3, 0.038, 2.04, 1.5)
    assert abs(tg['t_yaw_s'] - 23.1) < 0.1                        # PR #277 sec. 4.2 table (sigma0 1.3 deg, b 2.04 mrad/s)
    part = analyze.partition(analyze.LEGS_S, 25.0)
    assert part['resets_between_legs'] == 7 and part['legs_over_budget_alone'] == []
    assert analyze.partition(analyze.LEGS_S, 45.0)['resets_between_legs'] == 3       # 2 legs per block: 4 blocks
    assert analyze.partition(analyze.LEGS_S, 10.0)['legs_over_budget_alone'] == list(analyze.LEGS_S)
    assert analyze.t_gate_s(3.0, 0.0, 2.0, 1.0)['t_yaw_s'] == 0.0    # no headroom left
