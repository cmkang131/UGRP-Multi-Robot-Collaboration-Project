#!/usr/bin/env python3
"""Physical check of the probe-only ``carry_axial_lag`` against the PR #286 prediction (2026-09-30). Evaluation only (GT never a controller input).

Usage: axial_lag_physical_check.py [--json out.json] <label>=<raw dir>[+<raw dir>...] [--control <label>=<label>] ...
   e.g. tS=.../tS  sB=.../sB  --pair tS:sB   (a "+" joins directories of one cohort, e.g. tX1+tX1b)

Per cohort and leg (the standard leg checks of harness.pair_chain_probe, the same as every other cohort of this study):
  * pass counts (cases; placements: strict = all seeds pass)
  * end-point error distribution (mm): mean / median / p90 / max, number above the 100 mm gate
  * along-track error minus dx (dx = beam x - rounded order-sheet x, the setup offset the sheet cannot say): mean, range
  * cross-track: |y| mean / p90 / max, and the PR #286 signed model  y = a + b*yaw + c*(y-0.05)  with its residual sd
    (L0: -5.2 +4.57*yaw_deg +0.43*(y-0.05 mm); L1: -6.1 +7.34*yaw_deg +0.21*(y-0.05 mm); residual sd 12.6 / 26.4 mm)
  * per-case pairing with a control cohort (same placements and seeds, no axial lag): change of along, cross and end error
The signed cross-track is beam y at the leg end minus the route line y = 0.05 m (checked against ``cross_track_m``).
"""
import argparse
import glob
import json
import math
import sys
from pathlib import Path

import numpy as np

ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / 'experiments/2026-09-30-door-relax-envelope/analysis'))
sys.path.insert(0, str(ROOT / 'experiments/2026-09-29-door-guard-relax/analysis'))
sys.path.insert(0, str(ROOT / 'experiments/2026-09-30-l1-axial-offset/analysis'))
from harness import pair_chain_probe as pcp  # noqa: E402
import plant_model as pm  # noqa: E402
import chain_analysis as ca  # noqa: E402

MODEL = {0: (-5.2, 4.57, 0.43, 12.6), 1: (-6.1, 7.34, 0.21, 26.4)}      # PR #286: a, b(yaw deg), c(y-0.05 mm), residual sd mm
ROUTE_Y = 0.05
GATE_MM = 100.
PREDICT = {'L1_worst_end_mm': 94., 'L1_along_minus_dx_mm': 4., 'cross_mean_abs_mm': 31.1, 'cross_p90_mm': 58.8, 'cross_max_mm': 68.5}


def case_dir(root, cid):
    name = 'chain_' + cid.split('@', 1)[1].replace(':', '_')
    return root / 'cases' / name


def load(root):
    out = []
    for line in open(root / 'cases.jsonl'):
        r = json.loads(line)
        d = case_dir(root, r['case_id'])
        cj = json.load(open(d / 'case.json'))
        bx, by, byaw = cj['beam_xyyaw']
        sheet_x = cj['coarse_order_sheet']['beam_xyyaw'][0]
        trace = [json.loads(x) for x in open(d / 'eval_only/trace.jsonl')] if (d / 'eval_only/trace.jsonl').exists() else []
        res = json.load(open(d / 'result.json'))
        row = {'cell': r['cell'], 'seed': r['seed'], 'case_id': r['case_id'], 'x': bx, 'y': by, 'yaw_deg': math.degrees(byaw),
               'sheet_x': sheet_x, 'dx_mm': 1000 * (bx - sheet_x), 'legs': {}, 'first_failure': (r.get('chain') or {}).get('first_failure'),
               'axial_lag': res.get('carry_axial_lag') is not None, 'axial_lag_legs': res.get('carry_axial_lag_legs')}
        for k in (0, 1):
            legs = (r.get('chain') or {}).get('legs', [])
            leg = legs[k] if len(legs) > k else {'recorded': False}
            if not leg.get('recorded'):
                row['legs'][k] = {'recorded': False, 'pass': False}
                continue
            t1 = leg['end_sim_s']
            past = [q for q in trace if q['t'] <= t1 + 1e-6]
            signed = 1000 * (past[-1]['beam_xyz'][1] - ROUTE_Y) if past else None
            a, b, c, _ = MODEL[k]
            pred = a + b * row['yaw_deg'] + c * (1000 * (by - ROUTE_Y))
            row['legs'][k] = {'recorded': True, 'pass': all(pcp.leg_checks(leg).values()), 'checks': pcp.leg_checks(leg),
                              'end_mm': 1000 * leg['end_error_m'], 'along_mm': 1000 * leg['along_error_m'],
                              'along_minus_dx_mm': 1000 * leg['along_error_m'] - row['dx_mm'], 'cross_abs_mm': 1000 * leg['cross_track_m'],
                              'cross_signed_mm': signed, 'cross_model_mm': pred, 'cross_resid_mm': None if signed is None else signed - pred}
        row['along_pred_mm'] = along_prediction(row)
        out.append(row)
    return out


def along_prediction(row):
    """PR #286 plant model (measured loaded-carry lag plant, leg time from the lag plan with PF gain x kappa, 0.1 s ticks): predicted
    along error (mm) at the L0 end and, for the two extreme tick phases f, at the L1 end. Only meaningful with the axial lag ON."""
    sheet = row['sheet_x']
    T0 = pm.T_lag(pm.ROUTE_X[1] - sheet, pm.PF_GAIN * pm.KAPPA)
    T1 = pm.T_lag(pm.ROUTE_X[2] - pm.ROUTE_X[1], pm.PF_GAIN * pm.KAPPA)
    e = [pm.along_errors((row['x'] - sheet), pm.ticks_l0(T0), pm.ticks_l1(T1, f), sheet) for f in (0.49, 1.0)]
    return {'L0': 1000 * e[0][0], 'L1_f049': 1000 * e[0][1], 'L1_f100': 1000 * e[1][1]}


def dist(v):
    v = np.array([x for x in v if x is not None], float)
    if not len(v):
        return None
    return {'n': int(len(v)), 'mean': float(v.mean()), 'median': float(np.median(v)), 'p90': float(np.percentile(v, 90)),
            'min': float(v.min()), 'max': float(v.max()), 'sd': float(v.std(ddof=1)) if len(v) > 1 else 0.}


def fd(s):
    return 'n/a' if s is None else (f"n {s['n']:2d} mean {s['mean']:+7.1f} med {s['median']:+7.1f} p90 {s['p90']:+7.1f} "
                                    f"range [{s['min']:+7.1f}, {s['max']:+7.1f}]")


def summarize(label, rows):
    units = sorted({r['cell'] for r in rows})
    s = {'label': label, 'n_cases': len(rows), 'n_placements': len(units), 'legs': {}, 'per_case': rows}
    print(f'\n## {label}: {len(rows)} cases, {len(units)} placements ({"axial lag ON" if any(r["axial_lag"] for r in rows) else "no axial lag"})')
    for k in (0, 1):
        ok = [r['legs'][k]['pass'] for r in rows]
        by = {u: [r['legs'][k]['pass'] for r in rows if r['cell'] == u] for u in units}
        strict = sum(all(v) for v in by.values())
        rec = [r['legs'][k] for r in rows if r['legs'][k]['recorded']]
        d = {'pass_cases': sum(ok), 'pass_placements_strict': strict,
             'end_mm': dist([x['end_mm'] for x in rec]), 'along_minus_dx_mm': dist([x['along_minus_dx_mm'] for x in rec]),
             'along_mm': dist([x['along_mm'] for x in rec]), 'cross_abs_mm': dist([x['cross_abs_mm'] for x in rec]),
             'cross_signed_mm': dist([x['cross_signed_mm'] for x in rec]), 'cross_resid_mm': dist([x['cross_resid_mm'] for x in rec]),
             'n_end_over_gate': sum(1 for x in rec if x['end_mm'] > GATE_MM)}
        if any(r['axial_lag'] for r in rows) and rec:
            if k == 0:
                res = [x['along_mm'] - r['along_pred_mm']['L0'] for r in rows for x in [r['legs'][0]] if x['recorded']]
            else:      # the L1 tick phase is unknown: take the closer of the two extreme phases
                res = []
                for r in rows:
                    x = r['legs'][1]
                    if x['recorded']:
                        c = [x['along_mm'] - r['along_pred_mm'][q] for q in ('L1_f049', 'L1_f100')]
                        res.append(min(c, key=abs))
            d['along_minus_plant_model_mm'] = dist(res)
            print(f'   along - plant-model prediction (PR #286, closer tick phase)  {fd(d["along_minus_plant_model_mm"])}')
        s['legs'][f'L{k}'] = d
        print(f'L{k}: pass {ca.fmt_ci(sum(ok), len(ok))} cases; placements strict {ca.fmt_ci(strict, len(units))}; end error > {GATE_MM:.0f} mm: {d["n_end_over_gate"]}')
        print(f'   end error mm         {fd(d["end_mm"])}')
        print(f'   along error mm       {fd(d["along_mm"])}')
        print(f'   along - dx mm        {fd(d["along_minus_dx_mm"])}')
        print(f'   |cross| mm           {fd(d["cross_abs_mm"])}')
        print(f'   signed cross mm      {fd(d["cross_signed_mm"])}')
        print(f'   cross - PR286 model  {fd(d["cross_resid_mm"])}  (model residual sd {MODEL[k][3]} mm)')
    return s


def pair(a, b):
    """Per-case change (a minus b) on the same placement and seed."""
    key = lambda r: (r['cell'], r['seed'])
    bb = {key(r): r for r in b['per_case']}
    out = {'a': a['label'], 'b': b['label'], 'n': 0, 'leg': {}}
    for k in (0, 1):
        diffs = {'end_mm': [], 'along_mm': [], 'cross_abs_mm': []}
        for r in a['per_case']:
            q = bb.get(key(r))
            if q and r['legs'][k]['recorded'] and q['legs'][k]['recorded']:
                for m in diffs:
                    diffs[m].append(r['legs'][k][m] - q['legs'][k][m])
        out['leg'][f'L{k}'] = {m: dist(v) for m, v in diffs.items()}
        out['n'] = max(out['n'], len(diffs['end_mm']))
        print(f'   pair {a["label"]} minus {b["label"]}, L{k} (n={len(diffs["end_mm"])}): along {fd(out["leg"][f"L{k}"]["along_mm"])}')
        print(f'        end {fd(out["leg"][f"L{k}"]["end_mm"])}')
    return out


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--json', type=Path)
    ap.add_argument('--pair', action='append', default=[], help='a:b  per-case difference of cohort a minus cohort b')
    ap.add_argument('raws', nargs='+')
    a = ap.parse_args()
    res = {}
    for spec in a.raws:
        label, _, paths = spec.partition('=')
        rows = []
        for p in paths.split('+'):
            rows += load(Path(p))
        res[label] = summarize(label, rows)
    pairs = [pair(res[x.split(':')[0]], res[x.split(':')[1]]) for x in a.pair]
    if a.json:
        a.json.write_text(json.dumps({'cohorts': res, 'pairs': pairs, 'model': MODEL, 'predict': PREDICT}, indent=1, default=float))


if __name__ == '__main__':
    main()
