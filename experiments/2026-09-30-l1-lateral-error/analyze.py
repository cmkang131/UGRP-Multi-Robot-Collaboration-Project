#!/usr/bin/env python3
"""Exploratory, conditional lateral-error prediction; NumPy only, no physics.

Frozen endpoint CSVs are created by extract.py. Resampling units are setup
placements, with repeated PF seeds averaged (shared priors remain dependent).
Select lag-on where available;
never count the registered acceptance replays as new training observations.
"""
import argparse
import csv
import importlib.util
import json
import math
from collections import defaultdict
from pathlib import Path

import numpy as np

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[1]
PLACEMENTS = ROOT / 'experiments/2026-09-30-l1-axial-offset/inputs/placements_confirmatory_DRAFT.json'
SAMPLES = ROOT / 'experiments/2026-09-29-pair-v6e-carry/hR2_samples.json'
LEVELS = (.5, .8, .9, .95)
COHORTS = {
    'b-v6h-gain-69c2a99a-cB': 'C',
    'b-v6h-gain-5bfd95f0-tR': 'R',
    'b-v6h-gain-5bfd95f0-tS': 'S',
    'b-v6h-gain-f5d83fdb-tX1': 'X',
    'b-v6h-gain-5bfd95f0-tX1b': 'X',
}
LEGACY = {'b-v6h-gain-69c2a99a-cB': 'C', 'b-v6h-gain-64abed88-rB': 'R', 'b-v6h-gain-b95d2016-sB': 'S'}


def read_rows(path):
    with path.open() as f:
        rows = list(csv.DictReader(f))
    for r in rows:
        for k, v in r.items():
            if not v:
                r[k] = None
                continue
            try:
                r[k] = float(v)
            except ValueError:
                pass
    return rows


def write_csv(path, rows):
    fields = list(dict.fromkeys(k for r in rows for k in r))
    with path.open('w', newline='') as f:
        w = csv.DictWriter(f, fieldnames=fields, lineterminator='\n')
        w.writeheader()
        for r in rows:
            w.writerow({k: (round(v, 7) if isinstance(v, (float, np.floating)) else v) for k, v in r.items()})


def fit(x, y):
    x, y = np.asarray(x, float), np.asarray(y, float)
    if len(x) <= x.shape[1] or not np.isfinite(x).all() or not np.isfinite(y).all():
        raise ValueError('need finite data and more independent units than parameters')
    beta, _, rank, _ = np.linalg.lstsq(x, y, rcond=None)
    if rank != x.shape[1]:
        raise ValueError('rank-deficient design')
    return beta, y - x @ beta


def group_bootstrap_indices(groups, rng):
    """Sample entire cohort families, then placements within each sampled family."""
    groups = np.asarray(groups)
    unique = np.unique(groups)
    out = []
    for g in rng.choice(unique, len(unique), replace=True):
        ix = np.flatnonzero(groups == g)
        out.extend(rng.choice(ix, len(ix), replace=True))
    return np.asarray(out, int)


def geometry(units):
    return np.array([[r['place_x'], r['place_y'], r['place_yaw_deg']] for r in units])


def holdout_train(groups, held, poses=None):
    """Exclude a whole family AND a held-out geometry repeated in other families."""
    train, test = groups != held, groups == held
    if poses is not None:
        near = (np.linalg.norm(poses[:, None, :2] - poses[None, test, :2], axis=-1) <= 1e-4)
        near &= np.abs(poses[:, None, 2] - poses[None, test, 2]) <= .01
        train &= ~near.any(axis=1)
    return train, test


def crossfit_residuals(x, y, groups, poses=None):
    groups = np.asarray(groups)
    residuals = np.zeros_like(y, dtype=float)
    for g in np.unique(groups):
        train, test = holdout_train(groups, g, poses)
        beta, _ = fit(x[train], y[train])
        residuals[test] = y[test] - x[test] @ beta
    return residuals


def coverage_summary(errors, halfwidth):
    inside = np.abs(errors) <= halfwidth
    return {'L0': float(inside[:, 0].mean()), 'L1': float(inside[:, 1].mean()),
            'both': float(inside.all(axis=1).mean())}


def validate(x, y, groups, units):
    """Outer cohort holdout. Inner holdouts calibrate without using the test cohort.

    Symmetric empirical intervals, not a conformal guarantee: only 3/4 families,
    unequal sizes, repeated posterior templates, exploratory feature selection.
    """
    groups = np.asarray(groups)
    folds, predictions = [], []
    raw_hits = {q: [] for q in LEVELS}
    nested_hits = {q: [] for q in LEVELS}
    residuals = np.zeros_like(y)
    poses = geometry(units)
    for g in np.unique(groups):
        train, test = holdout_train(groups, g, poses)
        beta, res = fit(x[train], y[train])
        err = y[test] - x[test] @ beta
        residuals[test] = err
        inner = crossfit_residuals(x[train], y[train], groups[train], poses[train])
        record = {'held_family': str(g), 'n': int(test.sum()), 'bias_mm': err.mean(0).tolist(),
                  'purged_near_duplicate_training_rows': int((groups != g).sum() - train.sum()),
                  'rmse_mm': np.sqrt((err ** 2).mean(0)).tolist(), 'intervals': {}}
        for q in LEVELS:
            a, b = np.quantile(np.abs(res), q, axis=0), np.quantile(np.abs(inner), q, axis=0)
            record['intervals'][str(q)] = {'raw_halfwidth_mm': a.tolist(), 'nested_halfwidth_mm': b.tolist(),
                                         'raw_coverage': coverage_summary(err, a),
                                         'nested_coverage': coverage_summary(err, b)}
            raw_hits[q].extend(np.abs(err) <= a)
            nested_hits[q].extend(np.abs(err) <= b)
        folds.append(record)
        for j in np.flatnonzero(test):
            predictions.append({'unit': units[j]['unit'], 'family': str(g), 'prior': units[j]['prior_id'],
                                'L0_error_mm': residuals[j, 0], 'L1_error_mm': residuals[j, 1]})
    def totals(hits):
        return {str(q): {'L0': float(np.mean(np.asarray(v)[:, 0])), 'L1': float(np.mean(np.asarray(v)[:, 1])),
                         'both': float(np.all(v, axis=1).mean())} for q, v in hits.items()}
    return {'n_placements': len(y), 'n_families': len(np.unique(groups)), 'folds': folds,
            'rmse_mm': np.sqrt((residuals ** 2).mean(0)).tolist(), 'raw_coverage': totals(raw_hits),
            'nested_coverage': totals(nested_hits)}, residuals, predictions


def seed_deviations(seed_y):
    """Paired single-seed deviations from each placement's seed mean."""
    return np.concatenate([np.asarray(v) - np.mean(v, axis=0) for v in seed_y], axis=0)


def convolve_seed_variation(residuals, groups, deviations):
    bank = (residuals[:, None, :] + deviations[None, :, :]).reshape(-1, 2)
    return bank, np.repeat(groups, len(deviations))


def bootstrap_validation(x, y, groups, seed_y, poses, *, draws=2000, seed=310930):
    """Coverage of the ACTUAL bootstrap+OOF marginal predictive intervals.

    Both coefficients and residual pools use only the outer training families.
    The cross-family residual pool is estimated anew inside each outer fold.
    """
    rng = np.random.default_rng(seed)
    groups = np.asarray(groups)
    folds, aggregate = [], {q: [] for q in LEVELS}
    for g in np.unique(groups):
        train, test = holdout_train(groups, g, poses)
        tx, ty, tg = x[train], y[train], groups[train]
        errors = crossfit_residuals(tx, ty, tg, poses[train])
        errors, error_groups = convolve_seed_variation(errors, tg, seed_deviations([seed_y[i] for i in np.flatnonzero(train)]))
        bank = []
        for _ in range(draws):
            for attempt in range(1000):
                ix = group_bootstrap_indices(tg, rng)
                try:
                    beta, _ = fit(tx[ix], ty[ix])
                    break
                except ValueError:
                    continue
            else:
                raise ValueError('bootstrap validation could not fit')
            e = draw_residuals(errors, error_groups, list(range(test.sum())), rng, 'iid')
            bank.append(x[test] @ beta + e)
        bank = np.asarray(bank)
        rec = {'held_family': str(g), 'n': int(test.sum()), 'intervals': {}}
        for q in LEVELS:
            lo, hi = np.quantile(bank, [(1 - q) / 2, (1 + q) / 2], axis=0)
            # A placement is covered only if both recorded single-seed outcomes
            # are covered. It is never two independent calibration observations.
            hit = np.array([np.all((np.asarray(seed_y[i]) >= lo[j]) & (np.asarray(seed_y[i]) <= hi[j]), axis=0)
                            for j, i in enumerate(np.flatnonzero(test))])
            aggregate[q].extend(hit)
            rec['intervals'][str(q)] = {'L0_coverage': float(hit[:, 0].mean()), 'L1_coverage': float(hit[:, 1].mean()),
                                       'both_coverage': float(hit.all(axis=1).mean()),
                                       'mean_width_mm': (hi - lo).mean(0).tolist()}
        folds.append(rec)
    return {'draws': draws, 'seed': seed, 'unit_coverage_rule': 'all observed seeds within interval, one vote per placement', 'folds': folds,
            'coverage': {str(q): {'L0': float(np.asarray(v)[:, 0].mean()), 'L1': float(np.asarray(v)[:, 1].mean()),
                                 'both': float(np.asarray(v).all(axis=1).mean())} for q, v in aggregate.items()}}


def make_units(rows, cohorts):
    """Keep both endpoints of a completed chain together; collapse seed repeats."""
    chains = defaultdict(dict)
    for r in rows:
        if r['cohort'] in cohorts and r['stage'] == 'chain' and r['leg'] in (0., 1.):
            chains[(r['cohort'], r['cell'], r['seed'])][int(r['leg'])] = r
    by = defaultdict(list)
    for (cohort, cell, seed), legs in chains.items():
        if set(legs) != {0, 1}:
            continue
        by[(cohorts[cohort], cell)].append(legs)
    units = []
    for (family, cell), chains in sorted(by.items()):
        a = chains[0][0]
        for chain in chains:
            for key in ('place_x', 'place_y', 'place_yaw_deg', 'prior_id', 'sheet_x'):
                if chain[0][key] != a[key]:
                    raise ValueError('cell merges different placements')
        units.append({**a, 'unit': family + '/' + cell, 'family': family, 'n_seeds': len(chains),
                      'y': np.mean([[c[0]['lateral_mm'], c[1]['lateral_mm']] for c in chains], axis=0).tolist(),
                      'seed_y': [[c[0]['lateral_mm'], c[1]['lateral_mm']] for c in chains],
                      'axial': np.mean([[c[0]['axial_mm'], c[1]['axial_mm']] for c in chains], axis=0).tolist()})
    return units


def select_model_units(rows):
    """A repeated station placement with a different sheet is not a new unit.

    Prefer the matched lag-on/coarse-sheet treatment. Recorded hR2 robot setups
    remain a different diagnostic domain, but geometric overlap is purged in CV.
    """
    all_units = make_units(rows, COHORTS)
    selected, excluded = [], []
    ordered = sorted(all_units, key=lambda r: (-r['axial_lag'], r['unit']))
    for r in ordered:
        twin = next((q for q in selected if r['prior_id'] == q['prior_id']
                     and (r['setup'] == 'hR2') == (q['setup'] == 'hR2')
                     and math.hypot(r['place_x'] - q['place_x'], r['place_y'] - q['place_y']) <= 1e-4
                     and abs(r['place_yaw_deg'] - q['place_yaw_deg']) <= .01), None)
        if twin:
            excluded.append({'excluded_unit': r['unit'], 'retained_unit': twin['unit'],
                             'reason': 'same station placement/prior; retain lag-on, do not count a second sheet as a new placement'})
        else:
            selected.append(r)
    return sorted(selected, key=lambda r: r['unit']), excluded


def features(units, kind):
    keys = ['intercept', 'placement_yaw_deg', 'placement_y_offset_mm']
    values = [[1., r['place_yaw_deg'], 1000 * (r['place_y'] - .05)] for r in units]
    if kind in ('prior', 'extended'):
        keys += ['prior_yaw_error_deg']
        values = [v + [r['prior_yaw_error_deg']] for v, r in zip(values, units)]
    if kind == 'extended':
        keys += ['prior_y_error_mm', 'sheet_dx_mm']
        values = [v + [r['prior_y_error_mm'], r['dx_mm']] for v, r in zip(values, units)]
    return np.array(values, float), keys


def describe(values):
    a = np.asarray(values, float)
    if not len(a):
        return {'n': 0}
    sd = a.std()
    return {'n': len(a), 'mean': float(a.mean()), 'sd': float(sd),
            'min': float(a.min()), 'max': float(a.max()),
            'abs_p50': float(np.quantile(abs(a), .5)), 'abs_p90': float(np.quantile(abs(a), .9)),
            'abs_p95': float(np.quantile(abs(a), .95)), 'abs_max': float(abs(a).max()),
            'excess_kurtosis': float(np.mean(((a - a.mean()) / sd) ** 4) - 3) if sd > 1e-10 else None}


def distributions(rows):
    cohort, strata = defaultdict(list), defaultdict(list)
    for r in rows:
        cohort[(r['cohort'], int(r['leg']))].append(r)
        strata[tuple(r[k] for k in ('stage', 'load', 'axis', 'leg', 'axial_lag', 'lateral_lag', 'gain_fix'))].append(r)
    def flat(groups, keys):
        out = []
        for key, rr in sorted(groups.items()):
            d = dict(zip(keys, key))
            for field in ('axial_mm', 'lateral_mm', 'yaw_end_deg'):
                d.update({field + '_' + k: v for k, v in describe([r[field] for r in rr]).items()})
            out.append(d)
        return out
    return flat(cohort, ('cohort', 'leg')), flat(strata, ('stage', 'load', 'axis', 'leg', 'axial_lag', 'lateral_lag', 'gain_fix'))


def pass_mask(along_mm, lateral_mm):
    """BOTH leg endpoints must meet the inclusive 100 mm Euclidean gate."""
    return np.all(np.hypot(along_mm, lateral_mm) <= 100., axis=-1)


def along_model(placements):
    path = ROOT / 'experiments/2026-09-30-l1-axial-offset/analysis/plant_model.py'
    spec = importlib.util.spec_from_file_location('lateral_plant', path)
    pm = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(pm)
    out = []
    for phase in np.linspace(.495, .995, 40):
        rows = []
        for p in placements:
            sx = pm.sheet_of(p['x'])
            t0 = pm.ticks_l0(pm.T_lag(1.55 - sx, pm.PF_GAIN * pm.KAPPA))
            t1 = pm.ticks_l1(pm.T_lag(.85, pm.PF_GAIN * pm.KAPPA), phase)
            rows.append(np.array(pm.along_errors(p['x'] - sx, t0, t1, sx)) * 1000)
        out.append(rows)
    return np.asarray(out)


def expected_probabilities(along, means, residuals, groups, scale=1.):
    """Exact empirical marginal probability, equal weight to each residual family."""
    groups = np.asarray(groups)
    phases, phase_counts = np.unique(along, axis=0, return_counts=True)
    probs = []
    for group in np.unique(groups):
        y = scale * (means[None, :, :] + residuals[groups == group, None, :])
        # phase, residual, placement, leg
        by_phase = pass_mask(phases[:, None, :, :], y[None, :, :, :]).mean(axis=1)
        probs.append(np.average(by_phase, axis=0, weights=phase_counts))
    return np.mean(probs, axis=0)


def draw_residuals(residuals, families, prior_ids, rng, dependence):
    """Keep L0/L1 paired. Shared templates/cohort effects are explicit scenarios."""
    pool = np.arange(len(residuals))
    if dependence == 'shared_cohort_prior':
        family = rng.choice(np.unique(families))
        pool = np.flatnonzero(families == family)
    if dependence == 'iid':
        # Equal family weighting, as expected_probabilities.
        gs = rng.choice(np.unique(families), len(prior_ids))
        idx = [rng.choice(np.flatnonzero(families == g)) for g in gs]
    elif dependence == 'shared_cohort_prior':
        pick = {g: rng.choice(pool) for g in sorted(set(prior_ids))}
        idx = [pick[g] for g in prior_ids]
    else:
        raise ValueError(dependence)
    return residuals[idx]


def forecast(x, y, groups, target_x, along, prior_ids, *, seed_y, poses, draws=2000, seed=20260930, scale=1.):
    """Hierarchical bootstrap band of conditional means, separate predictive counts.

    Residuals are paired out-of-family errors, fixed across coefficient bootstrap
    fits. This is a conservative transfer-error sensitivity distribution, not a
    confidence interval with guaranteed coverage. Equal family residual weights.
    """
    if draws < 1:
        raise ValueError('draws must be positive')
    rng = np.random.default_rng(seed)
    groups = np.asarray(groups)
    beta, _ = fit(x, y)
    residuals = crossfit_residuals(x, y, groups, poses)
    residuals, residual_groups = convolve_seed_variation(residuals, groups, seed_deviations(seed_y))
    point = expected_probabilities(along, target_x @ beta, residuals, residual_groups, scale)
    conditional, iid_counts, shared_counts, pi = [], [], [], []
    rejected = 0
    for _ in range(draws):
        for attempt in range(1000):
            ix = group_bootstrap_indices(groups, rng)
            try:
                b, _ = fit(x[ix], y[ix])
                break
            except ValueError:
                rejected += 1
        else:
            raise ValueError('cannot construct a full-rank bootstrap fit')
        mean = target_x @ b
        prob = expected_probabilities(along, mean, residuals, residual_groups, scale)
        conditional.append(float(prob.sum()))
        pi.append(prob)
        al = along[rng.integers(len(along))]  # schedule phase common to the cohort, as PR #286
        for mode, dest in (('iid', iid_counts), ('shared_cohort_prior', shared_counts)):
            err = draw_residuals(residuals, residual_groups, prior_ids, rng, mode)
            dest.append(int(pass_mask(al, scale * (mean + err)).sum()))
    def counts_summary(v):
        a = np.asarray(v)
        return {'mean': float(a.mean()), 'p05_p50_p95': np.quantile(a, [.05, .5, .95]).tolist(),
                'P_ge_48': float(np.mean(a >= 48)), 'P_ge_54': float(np.mean(a >= 54)),
                'P_ge_48_MC_SE': float(np.sqrt(np.mean(a >= 48) * (1 - np.mean(a >= 48)) / len(a)))}
    return {'draws': draws, 'seed': seed, 'cross_scale': scale, 'bootstrap_rejected_rank_deficient': rejected,
            'fixed_fit_expected_count': float(point.sum()),
            'bootstrap_expected_count': float(np.mean(conditional)),
            'parameter_band_p05_p50_p95': np.quantile(conditional, [.05, .5, .95]).tolist(),
            'predictive_iid': counts_summary(iid_counts), 'predictive_shared_cohort_prior': counts_summary(shared_counts),
            'per_placement_probability': np.mean(pi, axis=0).tolist()}, residuals


def student_tail_stress(x, y, groups, target_x, along, priors, seed_y, poses, draws=5000):
    """Unvalidated t_3 tail sensitivity, same OOF covariance and paired legs.

    No tail-parameter estimation is claimed. Student t_3 has finite variance and
    infinite fourth moment, unlike the finite empirical residual bank.
    """
    rng = np.random.default_rng(930033)
    groups = np.asarray(groups)
    res = crossfit_residuals(x, y, groups, poses)
    chol = np.linalg.cholesky(np.cov(res.T) + np.cov(seed_deviations(seed_y).T))
    template_names = sorted(set(priors))
    indexes = [template_names.index(p) for p in priors]
    counts = []
    for _ in range(draws):
        for attempt in range(1000):
            ix = group_bootstrap_indices(groups, rng)
            try:
                beta, _ = fit(x[ix], y[ix])
                break
            except ValueError:
                continue
        else:
            raise ValueError('tail stress could not fit')
        # df=3: normal / sqrt(chi2_3), covariance equals chol @ chol.T.
        z = rng.normal(size=(len(template_names), 2)) / np.sqrt(rng.chisquare(3, (len(template_names), 1)))
        e = res.mean(0) + z @ chol.T
        counts.append(int(pass_mask(along[rng.integers(len(along))], target_x @ beta + e[indexes]).sum()))
    return {'distribution': 'Student t df=3, OOF covariance matched; common residual by prior template', 'draws': draws,
            'expected_count_MC': float(np.mean(counts)), 'P_ge_48': float(np.mean(np.array(counts) >= 48)),
            'count_p05_p50_p95': np.quantile(counts, [.05, .5, .95]).tolist(), 'validated_tail_model': False}


def main():
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument('--results', type=Path, default=HERE / 'results')
    ap.add_argument('--draws', type=int, default=2000)
    a = ap.parse_args()
    rows = read_rows(a.results / 'endpoints.csv')
    cohort_stats, strata = distributions(rows)
    write_csv(a.results / 'cohort_distributions.csv', cohort_stats)
    write_csv(a.results / 'strata.csv', strata)
    units, excluded_units = select_model_units(rows)
    (a.results / 'duplicate_units.json').write_text(json.dumps(excluded_units, indent=1) + '\n')
    old = make_units(rows, LEGACY)
    env = [r for r in units if r['family'] != 'R']
    models, all_predictions = {}, []
    datasets = [('legacy_34', old, 'base'), ('updated_40', units, 'base'), ('updated_40_prior', units, 'prior'),
                ('target_ENV_30_base', env, 'base'), ('target_ENV_30_prior', env, 'prior'),
                ('target_ENV_30_extended', env, 'extended')]
    for name, data, kind in datasets:
        x, keys = features(data, kind)
        y, groups = np.array([r['y'] for r in data]), np.array([r['family'] for r in data])
        beta, residuals = fit(x, y)
        validation, oof, predictions = validate(x, y, groups, data)
        models[name] = {'features': keys, 'coefficients_L0_L1': beta.tolist(), 'validation': validation,
                        'fit_residual_L0': describe(residuals[:, 0]), 'fit_residual_L1': describe(residuals[:, 1]),
                        'OOF_residual_L1': describe(oof[:, 1]),
                        'fit_leg_correlation': float(np.corrcoef(residuals.T)[0, 1]),
                        'OOF_leg_correlation': float(np.corrcoef(oof.T)[0, 1])}
        if name in ('target_ENV_30_prior', 'updated_40'):
            models[name]['bootstrap_predictive_validation'] = bootstrap_validation(x, y, groups, [r['seed_y'] for r in data], geometry(data), draws=a.draws)
        all_predictions.extend({'model': name, **r} for r in predictions)
    write_csv(a.results / 'loco_predictions.csv', all_predictions)
    (a.results / 'models.json').write_text(json.dumps(models, indent=1, allow_nan=False) + '\n')
    plc = json.loads(PLACEMENTS.read_text())
    priors = {s['id']: s for s in json.loads(SAMPLES.read_text())['samples']}
    target = [{'place_x': p['x'], 'place_y': p['y'], 'place_yaw_deg': p['yaw_deg'],
               'prior_yaw_error_deg': math.degrees(np.mean([priors[p['prior']]['prior_err'][rid]['mean_err_xyyaw'][2]
                                                          for rid in ('r1', 'r2')]))} for p in plc]
    al = along_model(plc)
    forecasts = {}
    for name, data, kind in [('target_ENV_30_prior', env, 'prior'), ('updated_40', units, 'base')]:
        x, _ = features(data, kind)
        tx, _ = features(target, kind)
        y, groups = np.array([r['y'] for r in data]), np.array([r['family'] for r in data])
        for scale in (1., 1.5, 2.):
            f, _ = forecast(x, y, groups, tx, al, [p['prior'] for p in plc], seed_y=[r['seed_y'] for r in data],
                            poses=geometry(data), draws=a.draws, scale=scale)
            forecasts[name + '_x' + str(scale)] = f
            print(name, scale, 'expected', round(f['bootstrap_expected_count'], 3), 'parameter band',
                  np.round(f['parameter_band_p05_p50_p95'], 2), 'shared P48', f['predictive_shared_cohort_prior']['P_ge_48'], flush=True)
    (a.results / 'predictions.json').write_text(json.dumps(forecasts, indent=1, allow_nan=False) + '\n')
    x, _ = features(env, 'prior')
    tx, _ = features(target, 'prior')
    tail = student_tail_stress(x, np.array([r['y'] for r in env]), np.array([r['family'] for r in env]),
                              tx, al, [p['prior'] for p in plc], [r['seed_y'] for r in env], geometry(env))
    (a.results / 'tail_stress.json').write_text(json.dumps(tail, indent=1, allow_nan=False) + '\n')
    point = forecasts['target_ENV_30_prior_x1.0']['per_placement_probability']
    write_csv(a.results / 'placements.csv', [{**p, 'pass_probability': prob, 'L0_axial_min_mm': al[:, i, 0].min(),
                                            'L1_axial_min_mm': al[:, i, 1].min(), 'L1_axial_max_mm': al[:, i, 1].max()}
                                           for i, (p, prob) in enumerate(zip(plc, point))])
    unit_rows = [{k: v for k, v in r.items() if k not in ('y', 'seed_y', 'axial')}
                 | {'L0_lateral_mm': r['y'][0], 'L1_lateral_mm': r['y'][1]} for r in units]
    write_csv(a.results / 'model_units.csv', unit_rows)


if __name__ == '__main__':
    main()
