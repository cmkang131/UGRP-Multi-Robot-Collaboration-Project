"""Offline action-axis decomposition for act18: teacher command distribution vs model
predictions and the frozen decode clamp/deadzone. No physics, no contract change.

Runs the B2/C2 checkpoint on sampled TRAIN rows (CPU is fine), compares the
continuous wheel/duration/PWM estimates with the recorded teacher targets, and
counts how often the frozen decode_action deadzone (.155) / clamps (.31-.40,
duration <=.15 s) convert predictions into "stop" commands. This decomposes why
the near-field policy physically fails to lift (0-2/4 across candidates).
"""
import argparse
import json
from pathlib import Path
import sys

import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parent))
from act17_data import read
from act17_compact_records import original_sha256
from act16w_runtime import frozen_source, sha256
from act18_policy import CANDIDATES, ReferenceDataset, Actor, make_policy

SKILLS = ('grasp', 'release', 'approach', 'align', 'alignment')
WHEEL_DEADZONE = .155
WHEEL_MIN = .31
WHEEL_MAX = .40
DURATION_MAX = .15
PWM_GRIPPER_CLOSED = 1900


def teacher_raw_distribution(dataset):
    """Distribution of recorded teacher first-step commands over TRAIN episodes."""
    root = Path(dataset)
    manifest = read(root/'manifest.json')
    wheels = []; durations = []; pwm5 = []
    for episode in manifest['episodes']:
        if episode['split'] != 'train':
            continue
        with np.load(root/episode['path']/'tensors.npz') as archive:
            action = archive['action'][:, 0, :]
        wheels.append(action[:, :4]); durations.append(action[:, 4:8])
        pwm5.append(1500.0+1000.0*action[:, 11])
    wheels = np.concatenate(wheels); durations = np.concatenate(durations); pwm5 = np.concatenate(pwm5)
    abs_wheels = np.abs(wheels)
    return dict(rows=int(abs_wheels.size),
                wheel_zero_fraction=float((abs_wheels == 0).mean()),
                wheel_abs_quantiles=[float(x) for x in np.quantile(abs_wheels, [.25, .5, .75, .95, .99])],
                wheel_in_deadzone_fraction=float(((abs_wheels > 0) & (abs_wheels < WHEEL_DEADZONE)).mean()),
                wheel_below_min_fraction=float(((abs_wheels >= WHEEL_DEADZONE) & (abs_wheels < WHEEL_MIN)).mean()),
                wheel_above_max_fraction=float((abs_wheels > WHEEL_MAX).mean()),
                duration_zero_fraction=float((durations == 0).mean()),
                duration_quantiles=[float(x) for x in np.quantile(durations[durations > 0], [.5, .9, .99])]
                if (durations > 0).any() else None,
                duration_too_small_fraction=float(((durations > 0) & (durations*DURATION_MAX < .001)).mean()),
                gripper_closed_fraction=float((pwm5 > PWM_GRIPPER_CLOSED).mean()))


def decode_wheels(wheels, done=False):
    """Frozen contract.decode_action wheel projection (no measured-state correction)."""
    out = []
    for w, dt_ok in zip(wheels, [True]*len(wheels)):
        if done or abs(w) < WHEEL_DEADZONE:
            out.append(0.0)
        else:
            out.append(float(np.sign(w))*max(WHEEL_MIN, min(WHEEL_MAX, abs(w))))
    return np.asarray(out)


def model_predictions(actor, data, rows, seed, device='cpu'):
    import torch
    rng = np.random.default_rng(seed)
    picked = rng.choice(len(data), size=min(rows, len(data)), replace=False)
    results = dict(n=len(picked), teacher_wheels=[], model_wheels=[],
                   teacher_wheel_zero=[], model_wheel_zero=[], decoded_zero=[],
                   teacher_pwm5=[], model_pwm5=[], wheel_mae=[], duration_mae=[],
                   skills=[])
    for index in picked:
        item = data[int(index)]
        batch = {k: torch.from_numpy(np.asarray(v)[None]).to(device)
                 for k, v in item.items()
                 if k in ('observation.images.own_history', 'observation.state')}
        with torch.inference_mode():
            raw = actor.policy.predict_action_chunk(batch)[0].cpu().numpy()
        decoded = actor.decode(raw)
        target = np.asarray(data.shards[data.index[int(index)][0]]['action'][data.index[int(index)][1]])
        teacher = target[0]
        model = decoded[0]
        results['teacher_wheels'].append(np.abs(teacher[:4]))
        results['model_wheels'].append(np.abs(model[:4]))
        results['teacher_wheel_zero'].append(bool(np.all(np.abs(teacher[:4]) == 0)))
        results['model_wheel_zero'].append(bool(np.all(np.abs(model[:4]) < WHEEL_DEADZONE)))
        results['decoded_zero'].append(bool(np.all(np.abs(decode_wheels(model[:4])) == 0)))
        results['teacher_pwm5'].append(float(1500+1000*teacher[11]))
        results['model_pwm5'].append(float(1500+1000*model[11]))
        results['wheel_mae'].append(float(np.abs(model[:4]-teacher[:4]).mean()))
        results['duration_mae'].append(float(np.abs(model[4:8]-teacher[4:8]).mean()))
        results['skills'].append(data.metadata[int(index)].get('skill'))
    return results


def summarize(pred):
    teacher_wheels = np.stack(pred['teacher_wheels']); model_wheels = np.stack(pred['model_wheels'])
    teacher_moving = ~np.asarray(pred['teacher_wheel_zero'])
    decoded_zero = np.asarray(pred['decoded_zero'])
    return dict(sampled_rows=pred['n'],
                teacher_moving_fraction=float(teacher_moving.mean()),
                teacher_moving_but_model_decodes_stop_fraction=float((teacher_moving & decoded_zero).mean()
                                                                     / max(teacher_moving.mean(), 1e-9)),
                teacher_stopped_fraction=float((~teacher_moving).mean()),
                model_decoded_stop_fraction=float(decoded_zero.mean()),
                model_raw_in_deadzone_fraction=float(np.mean(model_wheels < WHEEL_DEADZONE)),
                model_raw_below_min_fraction=float(np.mean((model_wheels >= WHEEL_DEADZONE) & (model_wheels < WHEEL_MIN))),
                model_raw_above_max_fraction=float(np.mean(model_wheels > WHEEL_MAX)),
                wheel_abs_median_teacher=float(np.median(teacher_wheels)),
                wheel_abs_median_model=float(np.median(model_wheels)),
                wheel_mae_median=float(np.median(pred['wheel_mae'])),
                duration_mae_median=float(np.median(pred['duration_mae'])),
                gripper_closed_fraction_teacher=float(np.mean(np.asarray(pred['teacher_pwm5']) > PWM_GRIPPER_CLOSED)),
                gripper_closed_fraction_model=float(np.mean(np.asarray(pred['model_pwm5']) > PWM_GRIPPER_CLOSED)))


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--enabled', action='store_true')
    parser.add_argument('--dataset', type=Path, required=True)
    parser.add_argument('--checkpoint', type=Path, required=True)
    parser.add_argument('--out', type=Path, required=True)
    parser.add_argument('--rows', type=int, default=2000)
    parser.add_argument('--seed', type=int, default=20261017)
    args = parser.parse_args()
    if not args.enabled:
        parser.error('action-axis offline analysis default OFF')
    source = frozen_source(Path(__file__).resolve().parents[1])
    meta = read(args.checkpoint/'adapter.json')
    chunk = meta['chunk']
    smooth = (meta.get('provenance', {}).get('probe', {}) or {}).get('base_smooth_window')
    data = ReferenceDataset(args.dataset, 'train', chunk=chunk, base_smooth_window=smooth)
    actor = Actor.load(args.checkpoint, device='cpu')
    pred = model_predictions(actor, data, args.rows, args.seed)
    report = dict(schema='ugrp.act18.action_axis.v1', source_sha=source,
                  checkpoint=dict(path=str(args.checkpoint), sha256=sha256(args.checkpoint/'model.safetensors')),
                  dataset=dict(path=str(args.dataset), manifest_sha256=original_sha256(args.dataset/'manifest.json')),
                  chunk=chunk, base_smooth_window=smooth,
                  teacher_raw=teacher_raw_distribution(args.dataset),
                  model=summarize(pred),
                  note='teacher targets are the smoothed/reconstructed training targets; teacher_raw is the recorded first-step command distribution')
    args.out.parent.mkdir(parents=True, exist_ok=True)
    args.out.write_text(json.dumps(report, ensure_ascii=False, indent=2)+'\n')
    print(json.dumps(dict(teacher_raw=report['teacher_raw'], model=report['model']), ensure_ascii=False, indent=1))


if __name__ == '__main__':
    main()
