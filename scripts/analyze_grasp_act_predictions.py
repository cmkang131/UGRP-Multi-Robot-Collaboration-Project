"""CPU/numpy analysis of SAVED held-out predictions; no model/physics calls."""
import argparse
from collections import defaultdict
import json
from pathlib import Path
import sys

import numpy as np

if str(Path(__file__).resolve().parents[1]) not in sys.path:
    sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from harness import grasp_act_contract as c
from harness.grasp_act_data import read_rows, sha256, write_summary


def drive_components(actions, *, decoded=False):
    """Signed wheel impulse over one tick -> forward, lateral, yaw proxies.

    These are issued-command directions, NOT measured robot motion. Independent
    wheel pulse widths matter; sign(wheel velocity) alone is misleading.
    """
    x = np.asarray(actions, dtype=float)
    if decoded:
        x = np.asarray([c.encode_action({'t': 0., **{k: v for k, v in c.decode_action(row).items()
                        if k in ('wheels', 'duration_s', 'pwm')}}, done=c.decode_action(row)['done'])
                        for row in x.reshape(-1, c.ACTION_DIM)]).reshape(x.shape)
    w = x[..., :4] * np.clip(x[..., 4:8], 0, 1) * .15 / c.PERIOD_S
    return np.stack([w.sum(-1), -w[..., 0]+w[..., 1]+w[..., 2]-w[..., 3],
                     -w[..., 0]+w[..., 1]-w[..., 2]+w[..., 3]], axis=-1) / 4


def quantiles(values):
    return dict(zip(('min', 'p01', 'p50', 'p95', 'p99', 'max'),
                    np.quantile(values, [0, .01, .5, .95, .99, 1]).tolist())) if len(values) else None


def metrics(prediction, target, pad):
    p, y, mask = np.asarray(prediction), np.asarray(target), np.asarray(pad, bool)
    if (p.shape != y.shape or mask.shape != y.shape[:-1] or y.shape[-1] != c.ACTION_DIM
            or not np.isfinite(p).all() or not np.isfinite(y).all()):
        raise ValueError('invalid saved predictions')
    p, y = p[~mask], y[~mask]
    if not len(y):
        raise ValueError('no valid targets')
    direction = {}
    yd = drive_components(y)
    for mode in ('raw', 'decoded'):
        pd = drive_components(p, decoded=mode == 'decoded')
        for axis, name in enumerate(('forward', 'lateral', 'yaw')):
            moving = np.abs(yd[:, axis]) > 1e-4
            match = (np.sign(pd[:, axis]) == np.sign(yd[:, axis])) & (np.abs(pd[:, axis]) > 1e-4)
            n, total = int((moving & match).sum()), int(moving.sum())
            direction[f'{mode}_{name}'] = {'match_n': n, 'moving_target_N': total,
                'rate': n / total if total else None, 'stationary_target_N': int((~moving).sum())}
    positives, calls = y[:, -1] >= .5, p[:, -1] >= .65
    return {'valid_actions': len(y), 'mae_per_action_dimension': np.abs(p-y).mean(0).tolist(),
        'wheel_mae': float(np.abs(p[:, :4]-y[:, :4]).mean()),
        'pulse_width_mae_s': float(np.abs(p[:, 4:8]-y[:, 4:8]).mean()*.15),
        'pwm_mae': float(np.abs(p[:, 8:13]-y[:, 8:13]).mean()*1000),
        'direction': direction,
        'done': {'positive_N': int(positives.sum()), 'predicted_positive_N': int(calls.sum()),
                 'true_positive_n': int((calls & positives).sum()),
                 'false_positive_n': int((calls & ~positives).sum()),
                 'raw_score_quantiles': quantiles(p[:, -1]),
                 'positive_score_quantiles': quantiles(p[positives, -1]),
                 'negative_score_quantiles': quantiles(p[~positives, -1]),
                 'note': 'legacy L1 score is not a probability; BCE sigmoid is class-balanced, uncalibrated'}}


def analyze(predictions, manifest, output):
    manifest, predictions, output = Path(manifest), Path(predictions), Path(output)
    data = json.loads(manifest.read_text())
    episodes = {str(e['seed']): e for e in data['episodes'] if e['split'] == 'validation'}
    output.mkdir(parents=True, exist_ok=False)
    groups, seen = defaultdict(list), set()
    rows = read_rows(predictions)
    # Validation is all-or-nothing: no silent partial 5-episode denominator.
    for row in rows:
        sid = row['sample_id']; seed = sid.split(':')[0].removeprefix('train-')
        if sid in seen or seed not in episodes:
            raise ValueError('duplicate or non-validation sample')
        seen.add(sid); groups[seed].append(row)
    if set(groups) != set(episodes) or any(len(groups[s]) != episodes[s]['rows_selected'] for s in episodes):
        raise ValueError('incomplete held-out predictions')
    report = {'schema': 'ugrp.grasp_act.prediction_analysis.v1', 'complete': True,
              'physical_runs': 0, 'inference_batches': 0, 'episodes': {},
              'manifest_sha256': sha256(manifest), 'predictions_sha256': sha256(predictions)}
    with (output / 'timesteps.jsonl').open('x') as stream:
        for seed, entries in groups.items():
            p = np.asarray([r['prediction'] for r in entries]); y = np.asarray([r['target'] for r in entries])
            pad = np.asarray([r['action_is_pad'] for r in entries], bool)
            if p.shape[1:] != (c.CHUNK, c.ACTION_DIM) or pad[:, 0].any():
                raise ValueError('invalid first action or chunk shape')
            report['episodes'][seed] = {'first_action': metrics(p[:, :1], y[:, :1], pad[:, :1]),
                'all_horizons': metrics(p, y, pad),
                'by_horizon': [metrics(p[:, h:h+1], y[:, h:h+1], pad[:, h:h+1])
                               if (~pad[:, h]).any() else None for h in range(c.CHUNK)]}
            episode = episodes[seed]
            samples = manifest.parent / episode.get('path', '__missing__') / 'samples.json'
            metadata = {}
            if samples.exists():
                if sha256(samples) != episode['files']['samples.json']:
                    raise ValueError('sample metadata hash mismatch')
                metadata = {r['sample_id']: r for r in json.loads(samples.read_text())}
                if set(metadata) != {r['sample_id'] for r in entries}:
                    raise ValueError('saved predictions/sample metadata mismatch')
                report['episodes'][seed]['by_skill'] = {}
                for skill in sorted({r['skill'] for r in metadata.values()}):
                    chosen = np.array([metadata[r['sample_id']]['skill'] == skill for r in entries])
                    report['episodes'][seed]['by_skill'][skill] = {
                        'first_action': metrics(p[chosen, :1], y[chosen, :1], pad[chosen, :1]),
                        'all_horizons': metrics(p[chosen], y[chosen], pad[chosen])}
            else:
                report['episodes'][seed]['skill_and_absolute_time_unavailable'] = True
            for row, pred, truth in zip(entries, p, y):
                stream.write(json.dumps({'sample_id': row['sample_id'],
                    'metadata': metadata.get(row['sample_id']),
                    'first_action': metrics(pred[:1], truth[:1], [False])}, allow_nan=False)+'\n')
    report['timesteps_sha256'] = sha256(output / 'timesteps.jsonl')
    write_summary(output / 'summary.json', report)
    return report


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--predictions', type=Path, required=True)
    parser.add_argument('--manifest', type=Path, required=True)
    parser.add_argument('--output', type=Path, required=True)
    args = parser.parse_args()
    analyze(args.predictions, args.manifest, args.output)


if __name__ == '__main__':
    main()
