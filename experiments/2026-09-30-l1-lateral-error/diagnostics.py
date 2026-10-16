#!/usr/bin/env python3
"""Descriptive contrasts and dependence audit; no causal or independent-n claims."""
import csv
import json
import math
from collections import Counter, defaultdict
from pathlib import Path

import numpy as np

import analyze as a

HERE = Path(__file__).resolve().parent


def correlation(x, y):
    if len(x) < 3 or np.std(x) < 1e-9 or np.std(y) < 1e-9:
        return None
    return float(np.corrcoef(x, y)[0, 1])


def prior_icc(errors, labels):
    """One-way unequal-group ANOVA ICC, descriptive (not a causal random effect)."""
    labels = np.asarray(labels)
    groups = [np.asarray(errors)[labels == g] for g in np.unique(labels)]
    n, k = len(errors), len(groups)
    ms_between = sum(len(g) * (g.mean() - np.mean(errors)) ** 2 for g in groups) / (k - 1)
    ms_within = sum(np.sum((g - g.mean()) ** 2) for g in groups) / (n - k)
    n0 = (n - sum(len(g) ** 2 for g in groups) / n) / (k - 1)
    return float((ms_between - ms_within) / (ms_between + (n0 - 1) * ms_within))


def main():
    dest = HERE / 'results'
    rows = a.read_rows(dest / 'endpoints.csv')
    units, _ = a.select_model_units(rows)
    env = [r for r in units if r['family'] != 'R']
    contrasts = []
    pairs = [('lag_S', 'b-v6h-gain-5bfd95f0-tS', 'b-v6h-gain-b95d2016-sB'),
             ('lag_R', 'b-v6h-gain-5bfd95f0-tR', 'b-v6h-gain-64abed88-rB'),
             ('lag_X', 'b-v6h-gain-f5d83fdb-tX1', 'b-v6h-gain-5bfd95f0-tX0'),
             ('lag_X06', 'b-v6h-gain-5bfd95f0-tX1b', 'b-v6h-gain-5bfd95f0-tX0'),
             ('gain_C', 'b-v6h-gain-69c2a99a-cB', 'b-v6h-gain-69c2a99a-cA'),
             ('gain_R', 'b-v6h-gain-64abed88-rB', 'b-v6h-gain-64abed88-rA'),
             ('gain_S', 'b-v6h-gain-b95d2016-sB', 'b-v6h-gain-b95d2016-sA')]
    for name, on, off in pairs:
        left = {(r['cell'], r['seed'], r['leg']): r for r in rows if r['cohort'] == on}
        right = {(r['cell'], r['seed'], r['leg']): r for r in rows if r['cohort'] == off}
        for leg in (0., 1.):
            keys = sorted(k for k in left.keys() & right.keys() if k[2] == leg)
            diff = [left[k]['lateral_mm'] - right[k]['lateral_mm'] for k in keys]
            contrasts.append({'comparison': name, 'leg': int(leg), 'matched_cases': len(keys),
                              'matched_cells': len(set(k[0] for k in keys)), **a.describe(diff)})
    a.write_csv(dest / 'matched_contrasts.csv', contrasts)
    deps = []
    for group, uu in (('all_40', units), ('target_ENV_30', env)):
        chosen = {r['unit'] for r in uu}
        for leg in (0., 1.):
            by_unit = defaultdict(list)
            for r in rows:
                if r['cohort'] not in a.COHORTS or r['leg'] != leg:
                    continue
                key = a.COHORTS[r['cohort']] + '/' + r['cell']
                if key in chosen:
                    by_unit[key].append(r)
            for field in ('start_lateral_mm', 'start_yaw_deg', 'start_pf_yaw_error_deg',
                          'dx_mm', 'door_start_distance_mm'):
                xx, yy = [], []
                for rr in by_unit.values():
                    if all(r[field] is not None for r in rr):
                        xx.append(np.mean([r[field] for r in rr]))
                        yy.append(np.mean([r['lateral_mm'] for r in rr]))
                deps.append({'sample': group, 'leg': int(leg), 'covariate': field, 'placements': len(xx),
                             'pearson_r': correlation(xx, yy), 'min': float(min(xx)), 'max': float(max(xx))})
    a.write_csv(dest / 'dependence.csv', deps)
    x, _ = a.features(env, 'prior')
    y = np.array([r['y'] for r in env])
    _, res = a.fit(x, y)
    oof = a.crossfit_residuals(x, y, np.array([r['family'] for r in env]), a.geometry(env))
    seed_pairs = np.array([r['seed_y'][:2] for r in units if len(r['seed_y']) >= 2])
    summary = {'seed_pairs_placements': len(seed_pairs),
               'seed_repeat_L1_correlation': correlation(seed_pairs[:, 0, 1], seed_pairs[:, 1, 1]),
               'seed_repeat_abs_L0_difference_mm': a.describe(abs(seed_pairs[:, 0, 0] - seed_pairs[:, 1, 0])),
               'seed_repeat_abs_L1_difference_mm': a.describe(abs(seed_pairs[:, 0, 1] - seed_pairs[:, 1, 1])),
               'fit_residual_L1_prior_ICC': prior_icc(res[:, 1], [r['prior_id'] for r in env]),
               'OOF_residual_L1_prior_ICC': prior_icc(oof[:, 1], [r['prior_id'] for r in env]),
               'target_ENV_prior_counts': dict(Counter(r['prior_id'] for r in env)),
               'load_counts': dict(Counter(r['load'] for r in rows)),
               'all_endpoint_L1_gt_lateral_mm': a.describe([r['lateral_mm'] for r in rows if r['leg'] == 1.]),
               'unloaded_endpoints': 0, 'unused_unloaded_not_assumed_zero': True}
    (dest / 'dependence.json').write_text(json.dumps(summary, indent=1, allow_nan=False) + '\n')

    # NEW exploratory probes, never the fixed confirmatory placements. A crossed
    # geometry/prior design distinguishes prior effects from start yaw/offset.
    probes = []
    for geometry, xyz in (('A', (.951, -.025, -4.50)), ('B', (1.069, .109, 4.50)), ('C', (1.069, .109, -4.50))):
        for prior in ('hR2_04', 'hR2_07'):
            probes.append({'name': 'LE_' + geometry + '_' + prior[-2:], 'x': xyz[0], 'y': xyz[1], 'yaw_deg': xyz[2],
                           'prior': prior, 'sheet': 'coarse'})
    plc = json.loads(a.PLACEMENTS.read_text())
    overlap = [(p['name'], c['name']) for p in probes for c in plc
               if math.hypot(p['x'] - c['x'], p['y'] - c['y']) < .01 and abs(p['yaw_deg'] - c['yaw_deg']) < .5]
    if overlap:
        raise ValueError(f'probe contaminates fixed confirmatory placement: {overlap}')
    used_overlap = [(p['name'], r['unit']) for p in probes for r in units
                    if math.hypot(p['x'] - r['place_x'], p['y'] - r['place_y']) < .01
                    and abs(p['yaw_deg'] - r['place_yaw_deg']) < .5]
    if used_overlap:
        raise ValueError(f'probe too close to a fitted placement: {used_overlap}')
    (HERE / 'inputs/proposed_probes.json').write_text(json.dumps(probes, indent=1) + '\n')
    extra = [{**probes[i], 'name': probes[i]['name'][:-2] + '10', 'prior': 'hR2_10'} for i in (0, 4)]
    (HERE / 'inputs/proposed_probe_extra_priors.json').write_text(json.dumps(extra, indent=1) + '\n')
    print(json.dumps(summary, indent=1))


if __name__ == '__main__':
    main()
