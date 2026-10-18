"""Validation action MAE against last-issued persistence; no physics/teacher.

The all-row h0 metric and fixed 8-tick refresh grid are kept separate from
overlapping future chunks. Grid offsets reset at every contiguous segment;
this is an offline deployment proxy, not a claim about student-visited states.
"""
import argparse
from collections import defaultdict
import json
from pathlib import Path

import numpy as np

from harness import grasp_act_contract as c
from harness.grasp_act_data import GraspDataset, INPUT_KEYS, sha256, write_json
from scripts.beamact1_runtime import require_gcp2


def persistence(states):
    states = np.asarray(states)
    start = (c.HISTORY - 1) * 14
    out = np.zeros((len(states), c.ACTION_DIM), np.float32)
    out[:, :13] = states[:, start:start + 13]
    return out  # Completion is never asserted by the copy-last-action baseline.


def refresh_grid(metadata):
    selected, offset, previous = [], 0, None
    for row in metadata:
        identity = tuple(row[k] for k in ('robot_id', 'role', 'object_kind', 'skill'))
        if previous is None or identity != previous[0] or abs(row['t'] - previous[1] - c.PERIOD_S) >= 1e-5:
            offset = 0
        selected.append(offset % c.CHUNK == 0)
        offset += 1; previous = identity, row['t']
    return np.asarray(selected, bool)


def errors(prediction, target):
    error = np.abs(np.asarray(prediction) - np.asarray(target))
    if error.ndim != 2 or error.shape[1] != c.ACTION_DIM or not len(error):
        raise ValueError('nonempty action rows required')
    return dict(N=len(error), wheel_mae=float(error[:, :4].mean()),
        pulse_mae_ms=float(error[:, 4:8].mean() * 150),
        pwm_mae=float(error[:, 8:13].mean() * 1000))


def decoded(prediction):
    return np.asarray([c.encode_action({'t': 0., **{k: r[k] for k in ('wheels','duration_s','pwm')}},
                       done=r['done']) for r in map(c.decode_action, prediction)])


def summarize(prediction, baseline, target, phases, refresh):
    result = {}
    for grid, mask in [('all_h0', np.ones(len(target), bool)), ('refresh_h0', refresh)]:
        groups = [('all', np.ones(len(target), bool))]
        groups += [(phase, np.asarray(phases) == phase) for phase in sorted(set(phases))]
        result[grid] = {}
        for name, chosen in groups:
            chosen = chosen & mask
            if not chosen.any():
                continue
            base = errors(baseline[chosen], target[chosen])
            values = dict(persistence=base)
            if prediction is not None:
                actor = errors(decoded(prediction[chosen]), target[chosen])
                values.update(ACT=actor, wheel_improvement_percent=(
                    100*(1-actor['wheel_mae']/base['wheel_mae']) if base['wheel_mae'] else None))
            result[grid][name] = values
    return result


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('--dataset', type=Path, required=True)
    p.add_argument('--stages', type=Path, required=True)
    p.add_argument('--model', type=Path)
    p.add_argument('--output', type=Path, required=True)
    a = p.parse_args()
    host = require_gcp2(training=bool(a.model))
    a.output.mkdir(parents=True, exist_ok=False)
    data = GraspDataset(a.dataset, 'validation')
    stages = {r['sample_id']: r for r in json.loads(a.stages.read_text())}
    actor = None
    if a.model:
        import torch
        from harness.beamact_input import BeamActor, transform_batch
        actor = BeamActor.load(a.model, device='cuda')
        if actor.stats != data.stats:
            raise ValueError('checkpoint/dataset normalization mismatch')
    predictions, baselines, targets, phases, grids, episode_reports = [], [], [], [], [], []
    offset = 0
    for episode, shard in zip((e for e in data.manifest['episodes'] if e['split']=='validation'), data.shards):
        meta = json.loads((a.dataset/episode['path']/'samples.json').read_text())
        target, baseline = shard['action'][:, 0], persistence(shard['state'])
        phase = [stages[r['sample_id']]['phase'] for r in meta]
        grid = refresh_grid(meta)
        prediction = None
        if actor is not None:
            ps = []
            for start in range(0, len(meta), 8):  # Frozen ACT batch8, no tuned threshold.
                items = [data[offset+i] for i in range(start, min(start+8, len(meta)))]
                batch = torch.utils.data.default_collate(items)
                inputs = transform_batch({k: batch[k].to('cuda') for k in INPUT_KEYS}, actor.mode)
                with torch.inference_mode():
                    values = actor.policy.predict_action_chunk(inputs).cpu().numpy()
                ps.extend(actor.decode_predictions(values)[:, 0])
            prediction = np.asarray(ps); predictions.extend(prediction)
        baselines.extend(baseline); targets.extend(target); phases.extend(phase); grids.extend(grid)
        episode_reports.append(dict(seed=episode['seed'], robot_id=episode['robot_id'],
            metrics=summarize(prediction, baseline, target, phase, grid)))
        offset += len(meta)
    metrics = summarize(np.asarray(predictions) if actor else None, np.asarray(baselines),
                        np.asarray(targets), phases, np.asarray(grids))
    write_json(a.output/'summary.json', dict(status='complete', host=host,
        scope='offline held-within-recordings validation; no heldout20 or student-visits used',
        dataset_manifest_sha256=sha256(a.dataset/'manifest.json'), stages_sha256=sha256(a.stages),
        model_sha256=sha256(a.model/'model.safetensors') if a.model else None,
        ACT_measured=actor is not None, physical_runs=0, metrics=metrics, episodes=episode_reports,
        validation_seeds=data.manifest['protocol']['validation_seeds'],
        refresh_definition='h0 at fixed 8-tick intervals; reset at task/clock gaps; offline proxy',
        persistence_definition='last actual issued command in raw unmasked state; done=false'))


if __name__ == '__main__':
    main()
