#!/usr/bin/env python3
"""Chain L0 -> L1 analysis of the b-v6h gain-fix cohorts (2026-09-30).

Usage: gain_cohort_analysis.py [--json out.json] <label>=<raw dir> ...

Builds on ``experiments/2026-09-30-door-relax-envelope/analysis/chain_analysis.py`` (leg class, contacts, clearance, sigma) and adds
what the gain-fix question needs:

* per-leg pass with Wilson 95 % intervals at the CASE level and at the effective INDEPENDENT-UNIT level. The independent unit is the
  placement (12 per cohort): the physics is deterministic and the two PF seeds (911, 913) of a placement give near-identical
  outcomes, so a placement counts once. A placement is "all seeds pass" (strict) or "any seed passes"; both are reported.
* per-axis honesty at each leg end (case-robot samples): mean signed PF error (estimate - ground truth), mean z^2 per axis
  (an honest sigma gives z^2 ~ 1), +-2 sigma coverage per axis with a Wilson interval whose n is the number of independent
  units, and the 3-DOF NEES (kept for continuity; it is NOT the acceptance criterion because y and yaw are conservative).
* contacts (wall tracker episodes), min GT clearance, end errors and the first-failure code per case.

Ground truth is used for evaluation only (never a controller input).
"""
import argparse
import collections
import json
import math
import sys
from pathlib import Path

import numpy as np

ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / 'experiments/2026-09-30-door-relax-envelope/analysis'))
sys.path.insert(0, str(ROOT / 'experiments/2026-09-29-door-guard-relax/analysis'))
import chain_analysis as ca  # noqa: E402
import door_relax_analysis as dra  # noqa: E402

wilson, fmt_ci = ca.wilson, ca.fmt_ci
PASS = ('PASS_CLEAN', 'PASS_CONTACT_RECOVERED')


def signed_error(trace, t, rid):
    rows = [x for x in trace if 'pf' in x and x['t'] <= t + 1e-6 and x['pf'][rid].get('initialized')]
    if not rows:
        return None
    x = rows[-1]
    p, g = x['pf'][rid], x['robots'][rid]
    e = np.array([p['x'] - g[0], p['y'] - g[1], dra.wrap(p['yaw'] - g[2])])          # estimate - truth
    C = np.array(p['cov'])
    sd = np.sqrt(np.diag(C))
    return {'e': e.tolist(), 'sd': sd.tolist(), 'z2': ((e / sd) ** 2).tolist(), 'nees': float(e @ np.linalg.solve(C, e))}


def unit_of(row):
    return row['cell']


def analyse(label, root):
    base = ca.analyse(label, root)
    rows = [json.loads(l) for l in open(root / 'cases.jsonl')]
    rows.sort(key=lambda r: r['case_id'])
    per_case = []
    for r, item in zip(rows, base['cases']):
        d = dra.case_dir(root, r['case_id'])
        res = json.load(open(d / 'result.json'))
        trace = [json.loads(x) for x in open(d / 'eval_only/trace.jsonl')] if (d / 'eval_only/trace.jsonl').exists() else []
        item['unit'], item['seed'] = unit_of(r), r['seed']
        item['progress_relax'] = res.get('progress_relax') and res['progress_relax'].get('variant')
        item['carry_gain_fix'] = res.get('carry_gain_fix') and res['carry_gain_fix'].get('mode')
        item['gain_applied'] = res.get('carry_gain_fix_applied')
        item['p2f'] = res.get('progress_relax_p2f')
        for k, leg in item['legs'].items():
            if leg.get('reached') is False:
                continue
            leg['signed'] = {rid: signed_error(trace, leg['end_sim_s'], rid) for rid in ('r1', 'r2')}
        per_case.append(item)
    base['cases'] = per_case
    units = sorted({c['unit'] for c in per_case})
    base['units'] = units
    summary = {'n_cases': len(per_case), 'n_units': len(units), 'legs': {}}
    for k in (0, 1):
        cls = [c['legs'][k]['class'] for c in per_case]
        ok = [x in PASS for x in cls]
        by_unit = collections.defaultdict(list)
        for c, o in zip(per_case, ok):
            by_unit[c['unit']].append(o)
        strict = sum(all(v) for v in by_unit.values())
        anyp = sum(any(v) for v in by_unit.values())
        clean = sum(1 for x in cls if x == 'PASS_CLEAN')
        summary['legs'][f'L{k}'] = {'cases_pass': sum(ok), 'cases_clean': clean, 'units_strict': strict, 'units_any': anyp,
                                    'classes': dict(collections.Counter(cls)),
                                    'case_ci': wilson(sum(ok), len(ok)), 'unit_strict_ci': wilson(strict, len(units)),
                                    'unit_any_ci': wilson(anyp, len(units))}
        print(f'L{k}: cases pass {fmt_ci(sum(ok), len(ok))} (clean {clean}); independent units (placements) strict '
              f'{fmt_ci(strict, len(units))}, any-seed {fmt_ci(anyp, len(units))}; classes {dict(collections.Counter(cls))}')
    both_case = [all(c['legs'][k]['class'] in PASS for k in (0, 1)) for c in per_case]
    by_unit = collections.defaultdict(list)
    for c, o in zip(per_case, both_case):
        by_unit[c['unit']].append(o)
    strict = sum(all(v) for v in by_unit.values())
    anyp = sum(any(v) for v in by_unit.values())
    summary['both'] = {'cases_pass': sum(both_case), 'units_strict': strict, 'units_any': anyp, 'case_ci': wilson(sum(both_case), len(both_case)),
                       'unit_strict_ci': wilson(strict, len(units)), 'unit_any_ci': wilson(anyp, len(units))}
    print(f'chain L0->L1: cases {fmt_ci(sum(both_case), len(both_case))}; units strict {fmt_ci(strict, len(units))}, any {fmt_ci(anyp, len(units))}')
    # per-axis honesty
    summary['honesty'] = {}
    for k in (0, 1):
        samples = [s for c in per_case if c['legs'][k].get('signed') for s in c['legs'][k]['signed'].values() if s]
        if not samples:
            continue
        z2 = np.array([s['z2'] for s in samples])
        e = np.array([s['e'] for s in samples])
        cov = (z2 <= 4.).mean(0)
        nees = np.array([s['nees'] for s in samples])
        # reached-only: samples come from legs that were recorded, i.e. the leg end exists
        ci = [wilson(int(round(v * len(units))), len(units)) for v in cov]
        summary['honesty'][f'L{k}'] = {'n_samples': len(samples), 'n_units': len(units), 'mean_signed_err_xyyaw': e.mean(0).tolist(),
                                       'mean_z2_xyyaw': z2.mean(0).tolist(), 'cov2sigma_xyyaw': cov.tolist(),
                                       'cov2sigma_ci_units': ci, 'mean_nees3': float(nees.mean())}
        print(f'honesty L{k} (samples={len(samples)}, units={len(units)}): mean e x/y/yaw = {e[:, 0].mean() * 1000:+.1f} mm / '
              f'{e[:, 1].mean() * 1000:+.1f} mm / {math.degrees(e[:, 2].mean()):+.2f} deg; mean z^2 x/y/yaw = {z2.mean(0).round(2).tolist()}; '
              f'+-2sigma coverage {cov.round(3).tolist()}; NEES3 mean {nees.mean():.2f}')
    ends = [1000 * c['legs'][1]['end_error_m'] for c in per_case if c['legs'][1].get('end_error_m') is not None]
    summary['l1_end_error_mm'] = {'mean': float(np.mean(ends)), 'max': float(np.max(ends)), 'n': len(ends)} if ends else None
    contacts = sum(c['legs'][k].get('contact_episodes', 0) for c in per_case for k in (0, 1))
    summary['contact_episodes'] = contacts
    ff = collections.Counter((c['first_failure'] or {}).get('code') for c in per_case if c['first_failure'])
    summary['first_failure_codes'] = dict(ff)
    print(f'contact episodes (both legs): {contacts}; first-failure codes: {dict(ff)}')
    base['summary'] = summary
    return base


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--json', type=Path)
    ap.add_argument('raws', nargs='+')
    a = ap.parse_args()
    print(ca.CLASSIFIER_NOTE, end='')
    res = []
    for spec in a.raws:
        label, _, path = spec.partition('=')
        res.append(analyse(label, Path(path)))
    if a.json:
        a.json.write_text(json.dumps(res, indent=1, default=float))


if __name__ == '__main__':
    main()
