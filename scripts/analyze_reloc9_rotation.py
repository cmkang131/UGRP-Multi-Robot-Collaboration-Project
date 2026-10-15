"""Offline fit/holdout scoring from saved command and evaluator ledgers only."""
import argparse
import hashlib
import json
import math
from pathlib import Path
import subprocess
import numpy as np
from harness.reloc9_rotation import pure_turn

ROOT = Path(__file__).resolve().parents[1]
RAW = Path('/Users/changmin/projects/ugrp/outputs/gcp1-runs')


def read(path, sources):
    if not path.exists():
        path = Path(str(path)+'.zst')
    data = path.read_bytes()
    raw = subprocess.check_output(['zstd', '-dc', str(path)]) if path.suffix == '.zst' else data
    sources.append(dict(path=str(path), sha256=hashlib.sha256(data).hexdigest(),
                        decoded_sha256=hashlib.sha256(raw).hexdigest()))
    return [json.loads(line) for line in raw.splitlines()]


def segments(run, sources):
    commands = read(RAW/run/'raw/teacher-commands.jsonl', sources)
    evaluation = {round(r['t'], 6): r for r in read(RAW/run/'raw/eval-only.jsonl', sources)}
    rows = [r for r in commands if round(r['t'], 6) in evaluation
            and 'map_pose_error_yaw_rad' in evaluation[round(r['t'], 6)]]
    result, indices = [], []

    def finish(ids):
        if len(ids) < 2:
            return
        chunk = [rows[i] for i in ids]
        # Discard segments with an RGB correction: yaw jump is not wheel motion.
        if len({r['map_pose']['rgb_fixes'] for r in chunk}) != 1:
            return
        estimate = np.unwrap([r['map_pose']['pose_estimate'][2] for r in chunk])
        truth = np.unwrap([r['map_pose']['pose_estimate'][2]-evaluation[round(r['t'], 6)]['map_pose_error_yaw_rad'] for r in chunk])
        de, dg = float(estimate[-1]-estimate[0]), float(truth[-1]-truth[0])
        if abs(de) >= math.radians(8.):
            result.append(dict(id=f'{run}:{chunk[0]["t"]:.1f}-{chunk[-1]["t"]:.1f}', run=run,
                start_t=chunk[0]['t'], end_t=chunk[-1]['t'], estimated_rad=de, actual_rad=dg,
                actual_over_estimated=dg/de))

    last_rot = None
    for i, row in enumerate(rows):
        if pure_turn(row['command']):
            if last_rot is not None and row['t']-rows[last_rot]['t'] > .35:
                finish(indices); indices = []
            indices.append(i); last_rot = i
        elif indices and row['t']-rows[last_rot]['t'] > .35:
            finish(indices); indices = []; last_rot = None
    finish(indices)
    return result


def stats(rows, scale):
    ratios = np.array([r['actual_over_estimated']/scale for r in rows])
    return dict(N=len(rows), median=float(np.median(ratios)), p10=float(np.percentile(ratios, 10)),
        p90=float(np.percentile(ratios, 90)), within_0_9_to_1_1_N=int(((ratios >= .9) & (ratios <= 1.1)).sum()),
        outside_0_9_to_1_1_N=int(((ratios < .9) | (ratios > 1.1)).sum()),
        median_in_target=bool(.9 <= np.median(ratios) <= 1.1))


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('--calibration-runs', nargs='+', required=True)
    p.add_argument('--validation-runs', nargs='+', required=True)
    p.add_argument('--output', type=Path, required=True)
    p.add_argument('--calibration-out', type=Path)
    a = p.parse_args()
    if set(a.calibration_runs) & set(a.validation_runs):
        p.error('calibration and validation runs must be disjoint')
    sources = []
    strata = []
    for run in [*a.calibration_runs, *a.validation_runs]:
        path = RAW/run/'raw/result.json'
        if not path.exists(): path = Path(str(path)+'.zst')
        raw = subprocess.check_output(['zstd','-dc',str(path)]) if path.suffix=='.zst' else path.read_bytes()
        meta = json.loads(raw)
        sources.append(dict(path=str(path),sha256=hashlib.sha256(path.read_bytes()).hexdigest(),
                            decoded_sha256=hashlib.sha256(raw).hexdigest()))
        strata.append(dict(run=run,source_sha=meta['source_sha'],status=meta['status'],host=meta['execution_host']))
    if len({(s['host']['provider'],s['host']['project_id'],s['host']['instance'],s['host']['machine_type']) for s in strata}) != 1:
        raise ValueError('DO_NOT_POOL_MACHINE_STRATA')
    train = [row for run in a.calibration_runs for row in segments(run, sources)]
    check = [row for run in a.validation_runs for row in segments(run, sources)]
    if not train or not check:
        raise ValueError('nonempty fit and holdout required')
    x, y = np.array([[r['estimated_rad'], r['actual_rad']] for r in train]).T
    scale = float(x@y/(x@x))
    cal = dict(schema='ugrp.reloc9_rotation.v1', yaw_scale=scale,
        drive_model_sha256=hashlib.sha256((ROOT/'harness/drive_model.py').read_bytes()).hexdigest(),
        calibration_ids=[r['id'] for r in train], validation_ids=[r['id'] for r in check],
        method='zero-intercept least squares on signed pure-turn segment yaw; no RGB fix in segment',
        scope='v7 steady-state carry pure equal-duration turn only; mixed/XY unchanged; holdout is replay, not new physics',
        residual_rotation_fraction=max(.25, float(max(abs(r['actual_over_estimated']/scale-1.) for r in train))),
        sources=sources, source_runs=strata)
    result = dict(calibration=cal, before=stats(check, 1.), after=stats(check, scale),
        train_after=stats(train, scale), calibration_segments=train, validation_segments=check,
        physics_calls=0, render_calls=0, sources=sources,
        acceptance='median actual/estimated in [0.9,1.1]; report every outlying segment separately; fresh 90/180 check required')
    for path, value in ((a.output, result), (a.calibration_out, cal)):
        if path:
            path.parent.mkdir(parents=True, exist_ok=True)
            with path.open('x') as f:
                json.dump(value, f, indent=2, allow_nan=False); f.write('\n')
    print(json.dumps({k: result[k] for k in ('before', 'after', 'train_after')}))


if __name__ == '__main__':
    main()
