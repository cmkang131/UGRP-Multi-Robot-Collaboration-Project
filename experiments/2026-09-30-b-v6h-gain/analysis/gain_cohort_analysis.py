#!/usr/bin/env python3
"""Chain L0 -> L1 analysis of the b-v6h gain-fix cohorts (2026-09-30).

Usage: gain_cohort_analysis.py [--json out.json] <label>=<raw dir> ...

Builds on ``experiments/2026-09-30-door-relax-envelope/analysis/chain_analysis.py`` (leg class, contacts, clearance, sigma) and adds
what the gain-fix question needs:

* per-leg pass with Wilson 95 % intervals at the CASE level and at the placement-unit level (nominal intervals). The grouping unit is the
  placement (12 per cohort; independence between placements is not established): the physics is deterministic and the two PF seeds (911, 913) of a placement give near-identical
  outcomes, so a placement counts once. A placement is "all seeds pass" (strict) or "any seed passes"; both are reported.
* per-axis honesty at each leg end (case-robot samples): mean signed PF error (estimate - ground truth), mean z^2 per axis
  (an honest sigma gives z^2 ~ 1), +-2 sigma coverage per axis, and the 3-DOF NEES (kept for continuity; it is NOT the acceptance
  criterion because y and yaw are conservative). The sample-level coverage (``cov2sigma_xyyaw``) has NO interval: the samples of one
  placement (2 robots x the PF seeds) are not independent. The interval is at the PLACEMENT level and its n is the number of OBSERVED
  placements, i.e. those that reached that leg end with both fresh robot samples for every reached seed (``n_observed_placements``). A placement is covered
  on an axis if ALL its samples there have z^2 <= 4. Placements that never reached the leg are UNVERIFIED (검증되지 않음): they are
  listed and neither count as covered nor enter the denominator. (Before 2026-09-30 review P1-2 the interval used
  round(sample coverage x ALL placements) as n, which overstated n whenever few placements reached the leg, e.g. cD L1: 2 robot
  samples of 1 placement, n = 12.)
* coverage is a check against over-confidence only. A coverage of 100 % and a low mean z^2 do NOT show that sigma is calibrated: a
  sigma far larger than the error also gives both (cB L1 x mean z^2 0.03, NEES3 0.27). The over-conservatism diagnostic is the mean
  z^2 itself (reported, not a gate).
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


PF_MAX_AGE_S = .30
ROBOTS = ("r1", "r2")


def signed_error(trace, t, rid, max_age_s=PF_MAX_AGE_S):
    """Latest causal initialized posterior, age <= .30 SIM s; invalid/missing -> None.

    Use the GT in the SAME sampled row. Both row and posterior timestamps must
    be causal and fresh; 1e-6 s is floating-point tolerance only. Covariance must
    be finite, symmetric and positive definite; yaw error wraps to [-pi, pi].
    """
    rows = [x for x in trace if isinstance(x.get("pf"), dict)
            and isinstance(x["pf"].get(rid), dict)
            and x["pf"][rid].get("initialized") is True and x.get("t", math.inf) <= t + 1e-6]
    if not rows:
        return None
    x = max(rows, key=lambda v: v["t"])
    p = x["pf"][rid]
    try:
        age, posterior_age = t - x["t"], t - float(p["t"])
        if (not math.isfinite(age) or not math.isfinite(posterior_age)
                or not -1e-6 <= age <= max_age_s + 1e-6
                or not -1e-6 <= posterior_age <= max_age_s + 1e-6
                or p["t"] > x["t"] + 1e-6):
            return None
        g = np.asarray(x["robots"][rid], dtype=float)
        est = np.asarray([p["x"], p["y"], p["yaw"]], dtype=float)
        C = np.asarray(p["cov"], dtype=float)
        if (g.shape != (3,) or not np.isfinite(g).all() or not np.isfinite(est).all()
                or C.shape != (3, 3) or not np.isfinite(C).all()
                or not np.allclose(C, C.T, rtol=0, atol=1e-12)):
            return None
        np.linalg.cholesky(C)  # positive definite, not just positive diagonal
        e = est - g
        e[2] = dra.wrap(e[2])
        sd = np.sqrt(np.diag(C))
        z2 = (e / sd) ** 2
        nees = float(e @ np.linalg.solve(C, e))
        if not np.isfinite(z2).all() or not math.isfinite(nees):
            return None
        return {"e": e.tolist(), "sd": sd.tolist(), "z2": z2.tolist(), "nees": nees,
                "sample_sim_s": x["t"], "posterior_sim_s": p["t"], "sample_age_s": age}
    except (KeyError, TypeError, ValueError, np.linalg.LinAlgError):
        return None


def unit_of(row):
    return row['cell']


def placement_coverage(per_case, k, units, z2_max=4.):
    """Placement-level +-2 sigma coverage of leg ``k`` end (review P1-2).

    OBSERVED placement = complete fresh r1/r2 pairs for all reached seeds (``signed``) at the end of leg ``k``. COVERED on an axis = all samples of the
    placement on that axis have z^2 <= ``z2_max``. UNVERIFIED (검증되지 않음) = no sample at that leg: not covered, not in the CI n.
    """
    by_unit = collections.defaultdict(list)
    missing = set()
    for c in per_case:
        leg = c['legs'][k]
        if leg.get('reached') is False:
            continue
        sig = leg.get('signed') or {}
        if set(sig) != set(ROBOTS) or any(sig[r] is None for r in ROBOTS):
            missing.add(c['unit'])
            continue
        by_unit[c['unit']].extend(sig[r]['z2'] for r in ROBOTS)
    # One complete seed never hides another reached seed's missing evidence.
    for unit in missing:
        by_unit.pop(unit, None)
    observed = sorted(by_unit)
    covered = [sum(all(z[j] <= z2_max for z in by_unit[u]) for u in observed) for j in range(3)]
    return {'n_units': len(units), 'n_observed_placements': len(observed), 'n_unverified_placements': len(units) - len(observed),
            'unverified_placements': sorted(set(units) - set(observed)), 'missing_pf_placements': sorted(missing),
            'evidence_verdict': 'NOT_EVALUABLE' if missing else 'COMPLETE_REACHED_PAIRS',
            'covered_placements_xyyaw': covered,
            'placement_coverage_xyyaw': [c / len(observed) if observed else None for c in covered],
            'cov2sigma_ci_placements_nominal': [wilson(c, len(observed)) if observed else None for c in covered]}


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
        print(f'L{k}: cases pass {fmt_ci(sum(ok), len(ok))} (clean {clean}); placement units (nominal intervals) strict '
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
        samples = [s for c in per_case if c['legs'][k].get('signed')
                   and all(c['legs'][k]['signed'].get(r) is not None for r in ROBOTS)
                   for s in c['legs'][k]['signed'].values()]
        pc = placement_coverage(per_case, k, units)
        if not samples:
            summary['honesty'][f'L{k}'] = {'n_samples': 0, **pc}
            print(f'honesty L{k}: no robot sample reached this leg end; all {len(units)} placements UNVERIFIED (검증되지 않음)')
            continue
        z2 = np.array([s['z2'] for s in samples])
        e = np.array([s['e'] for s in samples])
        cov = (z2 <= 4.).mean(0)
        nees = np.array([s['nees'] for s in samples])
        # reached-only: samples come from legs that were recorded, i.e. the leg end exists
        summary['honesty'][f'L{k}'] = {'n_samples': len(samples), 'mean_signed_err_xyyaw': e.mean(0).tolist(),
                                       'mean_z2_xyyaw': z2.mean(0).tolist(), 'cov2sigma_xyyaw': cov.tolist(),
                                       'mean_nees3': float(nees.mean()), **pc}
        print(f'honesty L{k} (samples={len(samples)}, observed placements={pc["n_observed_placements"]}/{len(units)}): mean e x/y/yaw = '
              f'{e[:, 0].mean() * 1000:+.1f} mm / {e[:, 1].mean() * 1000:+.1f} mm / {math.degrees(e[:, 2].mean()):+.2f} deg; '
              f'mean z^2 x/y/yaw = {z2.mean(0).round(2).tolist()}; +-2sigma coverage (samples) {cov.round(3).tolist()}; NEES3 mean {nees.mean():.2f}')
        n_obs = pc['n_observed_placements']
        print(f'  L{k} placement-level +-2sigma coverage (covered = all samples of the placement inside; n = observed placements): '
              + ' / '.join(f'{name} {fmt_ci(c, n_obs)}' for name, c in zip(('x', 'y', 'yaw'), pc['covered_placements_xyyaw']))
              + (f'; UNVERIFIED (검증되지 않음) placements: {pc["n_unverified_placements"]} {pc["unverified_placements"]}'
                 if pc['n_unverified_placements'] else '; unverified placements: 0'))
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
