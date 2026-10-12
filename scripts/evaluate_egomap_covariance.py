"""Offline-only XY NEES replay. Evaluation truth never reaches the controller.

Fixed split by seed, never random time rows. Pooled/stratum scale is the scalar
Gaussian maximum-likelihood estimate mean(e' P^-1 e)/2, lower bounded by one.
The mean is episode-balanced to avoid making long correlated runs dominate.
Coverage is reported at 95% and 99.9%; passing a tail count is not consistency.
"""
import argparse
from collections import Counter, defaultdict
import hashlib
import json
import math
from pathlib import Path
import subprocess

import numpy as np

from harness.egomap_covariance import OPTION, stratum, validate

CHI2 = {'p95': -2 * math.log(.05), 'p999': -2 * math.log(.001)}


def read(path):
    path = Path(path)
    if not path.exists() and Path(str(path) + '.zst').exists():
        path = Path(str(path) + '.zst')
    raw = (subprocess.check_output(['zstd', '-dc', str(path)])
           if path.suffix == '.zst' else path.read_bytes())
    return raw, dict(path=str(path), bytes=path.stat().st_size,
                    sha256=hashlib.sha256(path.read_bytes()).hexdigest())


def lines(path):
    raw, provenance = read(path)
    return [json.loads(row) for row in raw.splitlines() if row.strip()], provenance


def nees(error, covariance):
    covariance = np.asarray(covariance, float)[:2, :2]
    error = np.asarray(error, float)
    if error.shape != (2,) or covariance.shape != (2, 2):
        return None
    if not np.isfinite(covariance).all() or not np.isfinite(error).all():
        return None
    if not np.allclose(covariance, covariance.T) or np.linalg.eigvalsh(covariance).min() <= 0:
        return None
    return float(error @ np.linalg.solve(covariance, error))


def extract(folder):
    folder = Path(folder)
    raw, receipt = read(folder / 'result.json')
    result = json.loads(raw)
    own, own_source = lines(folder / 'own-controller.jsonl')
    covs, cov_source = lines(folder / 'frontend-covariances.jsonl')
    truth, truth_source = lines(folder / 'eval_only/trajectory.jsonl')
    provenance = [receipt, own_source, cov_source, truth_source]
    if not truth:
        return [], dict(run=folder.name, status='HOST_ERROR', reason='NO_TRUTH', provenance=provenance)
    covs = {round(x['t'], 6): x for x in covs}
    actual = {round(x['t'], 6): x for x in truth}
    first = truth[0]
    angle = float(first['robot_yaw_rad'])
    rotation = np.array([[math.cos(angle), -math.sin(angle)], [math.sin(angle), math.cos(angle)]])
    origin = np.asarray(first['robot_xyz_m'][:2])
    records, skipped = [], Counter()
    previous = None
    for row in own:
        stamp = round(row['t'], 6)
        past = previous
        previous = row
        if row['t'] < result['start_sim_s']:
            continue
        if stamp not in covs or stamp not in actual:
            skipped['missing_covariance_or_truth'] += 1
            continue
        # Error and covariance must share own-odom axes. Do not divide the
        # Euclidean error by lambda_max(P), which is only a lower NEES bound.
        estimate = np.asarray(row['local_pose'][:2])
        target = rotation.T @ (np.asarray(actual[stamp]['robot_xyz_m'][:2]) - origin)
        covariance = np.asarray(covs[stamp]['covariance'])
        error = target - estimate
        value = nees(error, covariance)
        if value is None:
            skipped['undefined_nees'] += 1
            continue
        key = stratum(past['stage'] if past else 'approach', past.get('command') if past else None)
        records.append(dict(run=folder.name, seed=int(result['seed']), t=row['t'], stratum=key,
            nees=value, error_xy_m=error.tolist(), covariance_xy=covariance[:2, :2].tolist()))
    return records, dict(run=folder.name, seed=result['seed'], status=result['status'],
                         scored=len(records), skipped=dict(skipped), provenance=provenance)


def fit(records, fit_seeds, check_seeds):
    selected = [r for r in records if r['seed'] in fit_seeds]
    if not selected:
        raise ValueError('NO_FIT_ROWS')
    def factor(group):
        episodes = defaultdict(list)
        for row in group:
            episodes[row['run']].append(row['nees'])
        return max(1., float(np.mean([np.mean(v) for v in episodes.values()])) / 2)
    pooled = factor(selected)
    factors, counts = {}, {}
    for key in sorted({r['stratum'] for r in selected}):
        group = [r for r in selected if r['stratum'] == key]
        episodes = len({r['run'] for r in group})
        eligible = len(group) >= 30 and episodes >= 2
        factors[key] = factor(group) if eligible else pooled
        counts[key] = dict(samples=len(group), episodes=episodes, pooled_fallback=not eligible)
    return validate(dict(schema='ugrp.egomap_covariance.v1', option=OPTION, target='xy', dof=2,
        method='episode_balanced_scalar_gaussian_ML', pooled_factor=pooled, factors=factors,
        fit_seeds=fit_seeds, check_seeds=check_seeds, fit_counts=counts,
        min_samples=30, min_episodes=2, calibration_scope='previously_seen_DEV_replay_not_confirmation',
        source_runs=sorted({r['run'] for r in selected}), modifies_pose=False,
        notes='stage/last-command proxies do not establish the physical cause; temporal rows are correlated'))


def metrics(rows, factor):
    values = np.asarray([r['nees'] / factor(r) for r in rows])
    return dict(samples=len(rows), episodes=len({r['run'] for r in rows}),
        mean=float(np.mean(values)) if len(values) else None,
        variance=float(np.var(values)) if len(values) else None,
        quantiles={str(q):float(np.quantile(values, q)) for q in (.5, .95, .999)} if len(values) else {},
        exceedances={name:dict(count=int(np.count_nonzero(values > limit)), denominator=len(rows),
                              threshold=limit) for name, limit in CHI2.items()},
        error_bias_xy_m=np.mean([r['error_xy_m'] for r in rows], axis=0).tolist() if rows else None)


def evaluate(records, calibration):
    factors = dict(raw=lambda r:1., pooled=lambda r:calibration['pooled_factor'],
                   stratified=lambda r:calibration['factors'].get(r['stratum'], calibration['pooled_factor']))
    report = {}
    for split, seeds in [('fit', calibration['fit_seeds']), ('check', calibration['check_seeds'])]:
        selected = [r for r in records if r['seed'] in seeds]
        report[split] = dict(seeds=seeds, overall={k:metrics(selected, f) for k, f in factors.items()},
            strata={key:{k:metrics([r for r in selected if r['stratum'] == key], f)
                         for k, f in factors.items()} for key in sorted({r['stratum'] for r in selected})})
    return report


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--runs', type=Path, nargs='+', required=True)
    parser.add_argument('--fit-seeds', type=int, nargs='+', required=True)
    parser.add_argument('--check-seeds', type=int, nargs='+', required=True)
    parser.add_argument('--output', type=Path, required=True)
    args = parser.parse_args()
    if args.output.exists():
        raise FileExistsError(args.output)
    args.output.mkdir(parents=True)
    records, runs = [], []
    for path in args.runs:
        samples, receipt = extract(path)
        records.extend(samples)
        runs.append(receipt)
    calibration = fit(records, args.fit_seeds, args.check_seeds)
    summary = dict(gt_evaluation_only=True, sequential_rows_independent=False,
        experiment_scope='retrospective_DEV_covariance_replay_no_new_physics', runs=runs,
        calibration=calibration, results=evaluate(records, calibration),
        errors=dict(HOST_ERROR=[r['run'] for r in runs if r['status'] == 'HOST_ERROR']),
        historical_70c_claim=dict(status='UNVERIFIED_SOURCE_NOT_FOUND',
            reported_factor=4.154, reported_exceedances=41, reported_denominator=1260,
            note='factor units and threshold unavailable; not equated with this full-matrix NEES replay'))
    for name, value in [('calibration', calibration), ('summary', summary)]:
        (args.output / (name + '.json')).write_text(json.dumps(value, indent=2, allow_nan=False) + '\n')
    print(json.dumps({k:v['overall'] for k,v in summary['results'].items()}))


if __name__ == '__main__':
    main()
