"""Summaries, pre-registered verdicts and the error-budget update of the carry-relocalization B1 measurement (numpy only).

Reads the `run` rows written by `relocalize_grid.py` and writes `results.json` + markdown tables. All thresholds below
were fixed in README.md BEFORE the cohort was run (see "Pre-registered criteria").

usage: python analyze.py <out_dir> <runs.jsonl> [<runs.jsonl> ...] [--renders <render_dir> ...]
"""
from __future__ import annotations

import json
import math
import sys
from collections import defaultdict
from pathlib import Path

import numpy as np

# ---- pre-registered thresholds (README "Pre-registered criteria") --------------------------------------------------
POS_A_M, YAW_A_DEG = 0.05, 2.0        # tier A: slot registration limit (PR #276 result 3: release 0.05 m / 2.0 deg; M1 `release`)
POS_B_M, YAW_B_DEG = 0.07, 3.0        # tier B: carry gate GATE_LOADED (sigma_xy 0.07 m, sigma_yaw 3 deg), harness/zone_own_guards.py
FAIL_POS_M, FAIL_YAW_DEG = 0.10, 4.0  # a run is WRONG when it ends beyond twice the tier-A limits (0.10 m: leg-end error limit of the audit)
MAX_FAIL_RATE, MAX_SILENT_RATE = 0.10, 0.05
ACCEPT_STD_XY_M = 0.06                # run_m2_pair.PREGRASP_FIX_STD_M: the existing acceptance rule of a checkpoint fix
ACCEPT_STD_YAW_DEG = 3.0              # GATE_LOADED yaw
MID_CHECKPOINTS = tuple(range(1, 8))  # after_L0 .. after_L6: the seven re-localization points of option B
# ---- PR #277 assumptions and quoted rates (README "Comparison with the PR #277 assumptions") -------------------------
PR277_SIGMA0_YAW_DEG, PR277_SIGMA0_XY_M = 1.3, 0.038
B_MRAD = {'v6e_pm+edge': 1.56, 'v6g_pm+edge': 2.04, 'registered_E0_cal2': 2.33, 'registered_E0_v6g_refit': 2.55}
K_MM_S = {'low_1.1': 1.1, 'high_1.5': 1.5}
LEGS_S = {'L0': 18.5, 'L1': 24.4, 'L2': 23.3, 'L3': 20.75, 'L4': 20.75, 'L5': 20.75, 'L6': 21.15, 'L7': 21.15}
GATE_YAW_DEG, GATE_XY_M = 3.0, 0.07
CHECKPOINT_ROUND_TRIP_S = 18.0        # PR #277 sec. 4.1 (measured, regrasp `stored`, tag map)
SWEEP_S = 0.8 + 0.6 + 7 * (0.4 + 0.6)  # run_m2_pair `_queue_grasp` / `_pregrasp_look`: first look 0.8+0.6 s, seven more pans 0.4+0.6 s each


def pct(a, q):
    a = np.asarray(a, float)
    return float('nan') if a.size == 0 else float(np.percentile(a, q))


def stats(runs: list[dict], frame: int | None = None) -> dict:
    """Error statistics of one group of runs (final frame unless `frame` is the index of the frame to score)."""
    if not runs:
        return {'n': 0}
    def pick(r, key_final, key_frame):
        return r[key_final] if frame is None else r['frames'][frame][key_frame]
    pos = np.array([pick(r, 'final_err_xy', 'err_xy') for r in runs])
    yaw = np.degrees(np.abs([pick(r, 'final_err_yaw', 'err_yaw') for r in runs]))
    sxy = np.array([r['final_std_xy'] if frame is None else r['frames'][frame]['std_xy'] for r in runs])
    syw = np.degrees([r['final_std_yaw'] if frame is None else r['frames'][frame]['std_yaw'] for r in runs])
    start_pos = np.array([math.hypot(r['start_err'][0], r['start_err'][1]) for r in runs])
    start_yaw = np.degrees(np.abs([r['start_err'][2] for r in runs]))
    wrong = (pos > FAIL_POS_M) | (yaw > FAIL_YAW_DEG)
    flagged = (sxy > ACCEPT_STD_XY_M) | (syw > ACCEPT_STD_YAW_DEG)
    return {'n': len(runs),
            'start_pos_p50': pct(start_pos, 50), 'start_pos_p90': pct(start_pos, 90),
            'start_yaw_p50': pct(start_yaw, 50), 'start_yaw_p90': pct(start_yaw, 90),
            'pos_p50': pct(pos, 50), 'pos_p90': pct(pos, 90), 'pos_p99': pct(pos, 99), 'pos_max': float(pos.max()),
            'yaw_p50': pct(yaw, 50), 'yaw_p90': pct(yaw, 90), 'yaw_p99': pct(yaw, 99), 'yaw_max': float(yaw.max()),
            'pos_rms': float(np.sqrt((pos ** 2).mean())), 'yaw_rms': float(np.sqrt((yaw ** 2).mean())),
            'fail_rate': float(wrong.mean()), 'flagged_rate': float(flagged.mean()),
            'silent_fail_rate': float((wrong & ~flagged).mean()),
            'std_xy_mean': float(sxy.mean()), 'std_yaw_mean_deg': float(syw.mean())}


def boot_p90(values, seed=0, n=1000) -> list:
    v = np.asarray(values, float)
    if v.size < 5:
        return [float('nan'), float('nan')]
    rng = np.random.default_rng(seed)
    p = [np.percentile(v[rng.integers(0, v.size, v.size)], 90) for _ in range(n)]
    return [float(np.percentile(p, 2.5)), float(np.percentile(p, 97.5))]


def tier(s: dict) -> str:
    """'A' (slot-registration precision), 'B' (carry-gate precision) or 'X' (neither)."""
    if not s.get('n'):
        return '-'
    ok = s['fail_rate'] <= MAX_FAIL_RATE and s['silent_fail_rate'] <= MAX_SILENT_RATE
    if ok and s['pos_p90'] <= POS_A_M and s['yaw_p90'] <= YAW_A_DEG:
        return 'A'
    if ok and s['pos_p90'] <= POS_B_M and s['yaw_p90'] <= YAW_B_DEG:
        return 'B'
    return 'X'


_ORDER = {'A': 0, 'B': 1, 'X': 2}


def worst(tiers) -> str:
    tiers = [t for t in tiers if t in _ORDER]
    return max(tiers, key=lambda t: _ORDER[t]) if tiers else '-'


def population(runs, name: str):
    cells = {'SY': ('S', 'Y'), 'S': ('S',), 'Y': ('Y',), 'L': ('L',)}[name]
    return [r for r in runs if r['cell'] in cells]


def summarize(runs: list[dict]) -> dict:
    """Group statistics for every (profile, obs, prior, look) config, checkpoint, robot and error population."""
    cfgs = defaultdict(list)
    for r in runs:
        cfgs[(r['render_profile'], r['obs'], r['prior'], r['look'])].append(r)
    out = {}
    for (profile, obs, prior, look), rs in sorted(cfgs.items()):
        key = f'{profile}|{obs}|{prior}|{look}'
        entry = {'profile': profile, 'obs': obs, 'prior': prior, 'look': look, 'groups': {}, 'checkpoints': {}, 'pooled': {}}
        for pop in ('SY', 'S', 'Y', 'L'):
            prs = population(rs, pop)
            if not prs:
                continue
            for cp in sorted({r['checkpoint'] for r in prs}):
                for rid in ('r1', 'r2'):
                    g = [r for r in prs if r['checkpoint'] == cp and r['robot'] == rid]
                    if not g:
                        continue
                    s = stats(g)
                    s['pos_p90_ci95'] = boot_p90([r['final_err_xy'] for r in g])
                    s['yaw_p90_ci95'] = boot_p90(np.degrees(np.abs([r['final_err_yaw'] for r in g])))
                    s['tier'] = tier(s)
                    entry['groups'][f'{pop}|cp{cp}|{rid}'] = s
            mid = [r for r in prs if r['checkpoint'] in MID_CHECKPOINTS]
            entry['pooled'][pop] = {'mid_checkpoints': stats(mid), 'all_checkpoints': stats(prs)}
            entry['pooled'][pop]['mid_checkpoints']['tier'] = tier(entry['pooled'][pop]['mid_checkpoints'])
        prs = population(rs, 'SY')
        for cp in sorted({r['checkpoint'] for r in prs}):
            ts = [entry['groups'][f'SY|cp{cp}|{rid}']['tier'] for rid in ('r1', 'r2') if f'SY|cp{cp}|{rid}' in entry['groups']]
            entry['checkpoints'][f'cp{cp}'] = worst(ts)
        entry['verdict_mid_checkpoints'] = worst([entry['checkpoints'][f'cp{cp}'] for cp in MID_CHECKPOINTS if f'cp{cp}' in entry['checkpoints']])
        entry['n_mid_checkpoints_tier'] = {t: sum(1 for cp in MID_CHECKPOINTS if entry['checkpoints'].get(f'cp{cp}') == t) for t in 'ABX'}
        # error after the first k sweep frames (pans 1500, 1230, 970, 700, 1770, 2030, 2300, 1500)
        ab = {}
        for k in (1, 3, 5, 8):
            mid = [r for r in prs if r['checkpoint'] in MID_CHECKPOINTS]
            if mid:
                s = stats(mid, frame=k - 1)
                ab[str(k)] = {x: s[x] for x in ('pos_p50', 'pos_p90', 'yaw_p50', 'yaw_p90', 'fail_rate', 'flagged_rate')}
        entry['sweep_length_mid_checkpoints_SY'] = ab
        out[key] = entry
    return out


# ------------------------------------------------------------------------------------------------ error budget
def t_gate_s(sigma0_yaw_deg: float, sigma0_xy_m: float, b_mrad: float, k_mm_s: float) -> dict:
    """Seconds until the carry gate is reached: sigma_yaw(t)=sqrt(s0^2+(b t)^2) -> 3 deg, sigma_xy(t)=sqrt(s0^2+(k t)^2) -> 0.07 m."""
    s0 = math.radians(sigma0_yaw_deg)
    g = math.radians(GATE_YAW_DEG)
    t_yaw = math.sqrt(max(g ** 2 - s0 ** 2, 0.)) / (b_mrad * 1e-3)
    t_xy = math.sqrt(max(GATE_XY_M ** 2 - sigma0_xy_m ** 2, 0.)) / (k_mm_s * 1e-3)
    return {'t_yaw_s': t_yaw, 't_xy_s': t_xy, 't_gate_s': min(t_yaw, t_xy), 'binding': 'yaw' if t_yaw <= t_xy else 'xy'}


def partition(legs: dict, budget_s: float) -> dict:
    """Greedy split of the consecutive legs into blocks of at most `budget_s` seconds; a leg longer than the budget stays alone."""
    blocks, cur, cur_t, over = [], [], 0., []
    for name, t in legs.items():
        if cur and cur_t + t > budget_s:
            blocks.append(cur)
            cur, cur_t = [], 0.
        cur.append(name)
        cur_t += t
        if t > budget_s:
            over.append(name)
    if cur:
        blocks.append(cur)
    return {'blocks': blocks, 'resets_between_legs': len(blocks) - 1, 'legs_over_budget_alone': over}


def budget_table(sigma0_yaw_deg: float, sigma0_xy_m: float) -> dict:
    rows = {}
    for bn, b in B_MRAD.items():
        for kn, k in K_MM_S.items():
            tg = t_gate_s(sigma0_yaw_deg, sigma0_xy_m, b, k)
            part = partition(LEGS_S, tg['t_gate_s'])
            n = part['resets_between_legs']
            rows[f'{bn}|{kn}'] = {**{x: round(v, 1) if isinstance(v, float) else v for x, v in tg.items()},
                                  'resets': n, 'blocks': part['blocks'], 'legs_over_budget_alone': part['legs_over_budget_alone'],
                                  'extra_time_s_at_18s_per_checkpoint': n * CHECKPOINT_ROUND_TRIP_S}
    return rows


def budget_update(res: dict, key: str) -> dict:
    """Budget for the PR #277 assumption and for the values measured in config `key` (mid checkpoints, pooled S+Y)."""
    e = res[key]
    p = e['pooled']['SY']['mid_checkpoints']
    worst_cp_yaw = max(g['yaw_rms'] for k, g in e['groups'].items() if k.startswith('SY|') and int(k.split('|')[1][2:]) in MID_CHECKPOINTS)
    worst_cp_pos = max(g['pos_rms'] for k, g in e['groups'].items() if k.startswith('SY|') and int(k.split('|')[1][2:]) in MID_CHECKPOINTS)
    cases = {'pr277_assumption': (PR277_SIGMA0_YAW_DEG, PR277_SIGMA0_XY_M),
             'measured_pooled_rms': (p['yaw_rms'], p['pos_rms'] / math.sqrt(2)),
             'measured_worst_checkpoint_rms': (worst_cp_yaw, worst_cp_pos / math.sqrt(2))}
    return {'config': key, 'note': 'sigma0_xy is the per-axis RMS = radial RMS / sqrt(2); sigma0_yaw is the RMS of the yaw error',
            'sigma0': {k: {'yaw_deg': round(v[0], 3), 'xy_m': round(v[1], 4)} for k, v in cases.items()},
            'budgets': {k: budget_table(*v) for k, v in cases.items()}}


def load_runs(paths) -> list[dict]:
    runs = []
    for p in paths:
        for line in Path(p).read_text().splitlines():
            if line.strip():
                r = json.loads(line)
                if r.get('kind') == 'run':
                    runs.append(r)
    return runs


def consistency_summary(paths) -> dict:
    """Truth-pose consistency of the observations (eval-only diagnostic): how well the map rows expected at the TRUE pose explain them."""
    rows = []
    for p in paths:
        for line in Path(p).read_text().splitlines():
            if line.strip():
                r = json.loads(line)
                if r.get('kind') == 'consistency':
                    rows.append(r)
    out = {}
    groups = defaultdict(list)
    for r in rows:
        groups[(r['render_profile'], r['obs'], r['look'], r['checkpoint'])].append(r)
    for (profile, obs, look, cp), rs in sorted(groups.items()):
        fit = [r['mean_column_prob_at_truth'] for r in rs if r['mean_column_prob_at_truth'] is not None]
        edge = [r['edge_within_3px'] for r in rs if r['edge_within_3px'] is not None]
        out[f'{profile}|{obs}|{look}|cp{cp}'] = {'frames': len(rs), 'mean_column_prob_at_truth_mean': float(np.mean(fit)) if fit else None,
                                                  'mean_column_prob_at_truth_min': float(np.min(fit)) if fit else None,
                                                  'edge_within_3px_mean': float(np.mean(edge)) if edge else None,
                                                  'edge_within_3px_min': float(np.min(edge)) if edge else None}
    return out


def seg_agreement_summary(render_dirs) -> dict:
    out = {}
    for d in render_dirs:
        p = Path(d) / 'seg_agreement.json'
        man = Path(d) / 'render_manifest.json'
        if not p.exists():
            continue
        agree = json.loads(p.read_text())
        prof = json.loads(man.read_text())['render_profile']
        wall = [v['wall']['iou'] for v in agree.values() if v['wall']['iou'] is not None]
        floor = [v['floor']['iou'] for v in agree.values() if v['floor']['iou'] is not None]
        acc = [v['pixel_acc'] for v in agree.values()]
        out[prof] = {'frames': len(agree), 'pixel_acc_median': float(np.median(acc)), 'pixel_acc_p10': pct(acc, 10),
                     'wall_iou_median': float(np.median(wall)), 'wall_iou_p10': pct(wall, 10),
                     'floor_iou_median': float(np.median(floor)), 'floor_iou_p10': pct(floor, 10)}
    return out


def fmt(s: dict) -> str:
    return (f"n={s['n']} pos p50/p90 {100*s['pos_p50']:.1f}/{100*s['pos_p90']:.1f} cm, yaw p50/p90 {s['yaw_p50']:.2f}/{s['yaw_p90']:.2f} deg, "
            f"fail {100*s['fail_rate']:.0f}% flagged {100*s['flagged_rate']:.0f}% silent {100*s['silent_fail_rate']:.0f}%")


def main(argv=None):
    argv = list(sys.argv[1:] if argv is None else argv)
    out = Path(argv[0])
    out.mkdir(parents=True, exist_ok=True)
    renders = []
    if '--renders' in argv:
        i = argv.index('--renders')
        renders, argv = argv[i + 1:], argv[:i]
    runs = load_runs(argv[1:])
    res = summarize(runs)
    (out / 'results.json').write_text(json.dumps(res, indent=1))
    (out / 'consistency.json').write_text(json.dumps({'obs_vs_map_at_true_pose': consistency_summary(argv[1:]),
                                                      'segmentation_vs_teacher_labels': seg_agreement_summary(renders)}, indent=1))
    budgets = {}
    for key in res:
        if key.endswith('|vision|wide|p20') or key.endswith('|vision|wide|search'):
            if res[key]['pooled'].get('SY'):
                budgets[key] = budget_update(res, key)
    (out / 'budget.json').write_text(json.dumps(budgets, indent=1))
    for key, e in res.items():
        print(f'\n## {key}: mid-checkpoint verdict {e["verdict_mid_checkpoints"]} {e["n_mid_checkpoints_tier"]}')
        for pop, d in e['pooled'].items():
            print(f'  pooled {pop} mid: {fmt(d["mid_checkpoints"])} tier {d["mid_checkpoints"]["tier"]}')
    print(f'\n{len(runs)} runs, {len(res)} configs -> {out}')


if __name__ == '__main__':
    main()
