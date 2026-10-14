"""Fixed held-out-seed action errors, not a closed-loop success estimate."""
import argparse
import json
from pathlib import Path

import numpy as np

import sys

if str(Path(__file__).resolve().parents[1]) not in sys.path:
    sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from harness.grasp_act_data import GraspDataset, INPUT_KEYS, sha256, write_json
from harness import grasp_act_contract as c
from scripts.grasp_act_training_guard import require_gcp, source_sha


def action_metrics(prediction, target, pad):
    prediction, target, pad = np.asarray(prediction), np.asarray(target), np.asarray(pad, bool)
    if prediction.shape != target.shape or pad.shape != target.shape[:-1] or not np.isfinite(prediction).all():
        raise ValueError('invalid evaluation tensors')
    p, y = prediction[~pad], target[~pad]
    if not len(y):
        raise ValueError('no valid actions')
    error = np.abs(p - y)
    pd = np.asarray([c.encode_action({'t': 0., **{k: v for k, v in c.decode_action(row).items()
                      if k in ('wheels', 'duration_s', 'pwm')}}, done=c.decode_action(row)['done']) for row in p])
    positives, calls = y[:, -1] >= .5, p[:, -1] >= .65
    return {'valid_actions': len(y), 'wheel_mae': float(error[:, :4].mean()),
            'pulse_width_mae_s': float(error[:, 4:8].mean() * .15),
            'pwm_mae': float(error[:, 8:13].mean() * 1000),
            'decoded_wheel_mae': float(np.abs(pd[:, :4] - y[:, :4]).mean()),
            'decoded_pwm_mae': float(np.abs(pd[:, 8:13] - y[:, 8:13]).mean() * 1000),
            'done_positive_N': int(positives.sum()), 'done_negative_N': int((~positives).sum()),
            'done_false_positive_n': int((calls & ~positives).sum()),
            'done_missed_n': int((~calls & positives).sum())}


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('--dataset', type=Path, required=True)
    p.add_argument('--model', type=Path, required=True)
    p.add_argument('--output', type=Path, required=True)
    a = p.parse_args()
    host, source = require_gcp(training=True), source_sha()
    a.output.mkdir(parents=True, exist_ok=False)
    report = {'status': 'running', 'complete': False, 'host': host, 'source_sha': source,
              'dataset_manifest_sha256': sha256(a.dataset / 'manifest.json'),
              'model_sha256': sha256(a.model / 'model.safetensors'), 'physical_runs': 0}
    write_json(a.output / 'summary.json', report)
    try:
        import torch
        from harness.grasp_act_policy import GraspActor
        actor = GraspActor.load(a.model, device='cuda')
        meta = json.loads((a.model / 'adapter.json').read_text())
        if meta['provenance']['dataset_manifest_sha256'] != report['dataset_manifest_sha256']:
            raise ValueError('model/dataset mismatch')
        data = GraspDataset(a.dataset, 'validation', blank=actor.blank)
        if data.stats != actor.stats:
            raise ValueError('model/dataset normalization mismatch')
        episodes, offset = [], 0
        with (a.output / 'predictions.jsonl').open('x') as log:
            for e in (e for e in data.manifest['episodes'] if e['split'] == 'validation'):
                metadata = json.loads((a.dataset / e['path'] / 'samples.json').read_text())
                ps, ys, masks = [], [], []
                for start in range(0, e['rows_selected'], 8):
                    items = [data[offset + i] for i in range(start, min(start + 8, e['rows_selected']))]
                    batch = torch.utils.data.default_collate(items)
                    inputs = {k: batch[k].to('cuda') for k in INPUT_KEYS}
                    with torch.inference_mode():
                        pred = actor.policy.predict_action_chunk(inputs).cpu().numpy()
                    target = batch['action'].numpy()
                    mean, std = np.asarray(actor.stats['action_mean']), np.asarray(actor.stats['action_std'])
                    pred, target = pred * std + mean, target * std + mean
                    pads = batch['action_is_pad'].numpy()
                    ps.extend(pred); ys.extend(target); masks.extend(pads)
                    for i in range(len(pred)):
                        log.write(json.dumps({'sample_id': metadata[start+i]['sample_id'],
                            'prediction': pred[i].tolist(), 'target': target[i].tolist(),
                            'action_is_pad': pads[i].tolist()}, allow_nan=False) + '\n')
                ps, ys, masks = np.asarray(ps), np.asarray(ys), np.asarray(masks)
                by_skill = {}
                for skill in sorted({r['skill'] for r in metadata}):
                    chosen = np.asarray([r['skill'] == skill for r in metadata])
                    by_skill[skill] = action_metrics(ps[chosen], ys[chosen], masks[chosen])
                by_task = {}
                for task in sorted({(r['robot_id'], r['object_kind'], r['role'], r['skill']) for r in metadata}):
                    chosen = np.asarray([tuple(r[k] for k in ('robot_id', 'object_kind', 'role', 'skill')) == task for r in metadata])
                    by_task['/'.join(task)] = action_metrics(ps[chosen], ys[chosen], masks[chosen])
                episodes.append({'seed': e['seed'], 'robot_id': e['robot_id'], 'by_skill': by_skill, 'by_task': by_task,
                    'all_horizons': action_metrics(ps, ys, masks),
                    'first_action': action_metrics(ps[:, :1], ys[:, :1], masks[:, :1])})
                offset += e['rows_selected']
        report.update(status='complete', complete=True, episodes=episodes,
                      validation_seeds=data.manifest['protocol']['validation_seeds'],
                      predictions_sha256=sha256(a.output / 'predictions.jsonl'))
    except BaseException as exc:
        report.update(status='HOST_ERROR', error_type=type(exc).__name__)
        raise
    finally:
        write_json(a.output / 'summary.json', report)


if __name__ == '__main__':
    main()
