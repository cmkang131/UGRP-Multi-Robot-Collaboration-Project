"""Offline NEES calibration from archived egomap70 errors; never a controller input reader."""
import argparse
import hashlib
import json
import math
from pathlib import Path
import subprocess

CHI2_XY_9973 = -2 * math.log(.0027)


def read_rows(root, relative, hashes):
    path = root / relative
    proc = None
    if path.exists():
        stream = path.open('rb')
    else:
        proc = subprocess.Popen(['zstd', '-dc', str(path) + '.zst'], stdout=subprocess.PIPE)
        stream = proc.stdout
    h, rows = hashlib.sha256(), []
    with stream:
        for line in stream:
            h.update(line)
            if line.strip(): rows.append(json.loads(line))
    if proc is not None and proc.wait(): raise ValueError('DECOMPRESSION_FAILED')
    manifest_path = root / 'artifacts.sha256.json'
    manifest = json.loads(manifest_path.read_bytes() if manifest_path.exists() else
                          subprocess.check_output(['zstd', '-dc', str(manifest_path)+'.zst']))
    if h.hexdigest() != manifest[relative]: raise ValueError('ARCHIVE_HASH_MISMATCH:' + relative)
    hashes[relative] = h.hexdigest()
    return rows


def measure(root):
    hashes = {}
    truth = read_rows(root, 'eval_only/trajectory.jsonl', hashes)
    trace = read_rows(root, 'own-controller.jsonl', hashes)
    covariance = read_rows(root, 'frontend-covariances.jsonl', hashes)
    origin = truth[0]['robot_xyz_m'][:2]
    c, s = math.cos(truth[0]['robot_yaw_rad']), math.sin(truth[0]['robot_yaw_rad'])
    by_t = {round(r['t'], 6): r for r in truth}
    by_p = {round(r['t'], 6): r for r in covariance}
    values, over3 = [], 0
    for r in trace:
        t = round(r['t'], 6)
        if t not in by_t or t not in by_p: continue
        x, y = r['local_pose'][:2]
        dx = c*x - s*y + origin[0] - by_t[t]['robot_xyz_m'][0]
        dy = s*x + c*y + origin[1] - by_t[t]['robot_xyz_m'][1]
        ex, ey = c*dx + s*dy, -s*dx + c*dy
        p = by_p[t]['covariance']; a, b, d = p[0][0], (p[0][1]+p[1][0])/2, p[1][1]
        det = a*d-b*b
        if a <= 0 or d <= 0 or det <= 0: raise ValueError('SPD_COVARIANCE_REQUIRED')
        value = (d*ex*ex-2*b*ex*ey+a*ey*ey)/det
        if not math.isfinite(value) or value < 0: raise ValueError('FINITE_NEES_REQUIRED')
        values.append(value)
        over3 += math.hypot(dx, dy) > 3*r['sigma_xy']
    if not values: raise ValueError('NO_PAIRED_ERRORS_AND_COVARIANCES')
    return values, dict(raw=str(root), files=hashes, samples=len(values), over3=over3,
                        mean_nees=sum(values)/len(values), max_nees=max(values))


def calibrate(root):
    rows, fit, heldout = [], [], []
    # One independent seed fits; another checks. Correlated frames and variants
    # are NOT counted as independent trials or a confidence guarantee.
    for seed in (63001, 63002):
        for condition in ('baseline', 'calib', 'calib_traversed', 'calib_traversed_zone'):
            values, row = measure(root / f'egomap70-{seed}-{condition}')
            row.update(seed=seed, condition=condition, split=(
                'fit' if seed == 63001 else 'check') if condition == 'calib_traversed' else 'context')
            rows.append((values, row))
            if condition == 'calib_traversed':
                (fit if seed == 63001 else heldout).extend(values)
    tail = sorted(fit)[min(len(fit)-1, math.ceil(.9973*len(fit))-1)]
    scale = max(1., sum(fit)/len(fit)/2, tail/CHI2_XY_9973)
    for values, row in rows:
        row.update(inflated_mean_nees=row['mean_nees']/scale,
                   inflated_tail_exceedances=sum(v/scale > CHI2_XY_9973 for v in values))
    return dict(schema='ugrp.e2e_nees_calibration.v1', evaluation_only=True,
                scope='8 archived egomap70 wave1 records, 2 seeds; not the full 24-condition cohort',
                fit_seeds=[63001], check_seeds=[63002], condition='calib_traversed', dimension=2,
                method='max(1, fit mean NEES / 2, fit q99.73 / chi2_2(99.73))',
                xy_scale=scale, chi2_xy_9973=CHI2_XY_9973,
                fit_samples=len(fit), check_samples=len(heldout),
                check_exceedance_rate=sum(v/scale > CHI2_XY_9973 for v in heldout)/len(heldout),
                new_physics=0, records=[r for _, r in rows])


if __name__ == '__main__':
    parser = argparse.ArgumentParser()
    parser.add_argument('--archive-root', type=Path, required=True)
    args = parser.parse_args()
    print(json.dumps(calibrate(args.archive_root), indent=2, allow_nan=False))
