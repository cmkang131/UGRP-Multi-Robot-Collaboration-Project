"""Offline ACT input interventions on recorded data; no simulation or training.

The small CPU probe is diagnostic, not an accuracy/causal-success estimate.
Full rollout/teacher autocorrelation uses saved commands, never model calls.
"""
from __future__ import annotations

import argparse
import itertools
import json
from pathlib import Path
import sys

import numpy as np

if str(Path(__file__).resolve().parents[1]) not in sys.path:
    sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from harness import grasp_act_contract as c
from harness.grasp_act_data import (IMAGE_KEYS, normalized_image, paired_segments,
    read_rows, sha256, write_summary)
from scripts.analyze_grasp_act_predictions import drive_components, metrics

VARIANTS = ('baseline', 'commands_zero', 'commands_mean', 'oldest_rgb_blank',
            'current_rgb_only', 'all_rgb_blank')


def change_metrics(prediction, baseline):
    """Sensitivity signs use both decoded operands after execution projection."""
    result = metrics(prediction, baseline, np.zeros(len(baseline), bool))
    for mode in ('raw', 'decoded'):
        p = drive_components(prediction, decoded=mode == 'decoded')
        b = drive_components(baseline, decoded=mode == 'decoded')
        for i, name in enumerate(('forward', 'lateral', 'yaw')):
            moving = np.abs(b[:, i]) > 1e-4
            same = (np.sign(p[:, i]) == np.sign(b[:, i])) & (np.abs(p[:, i]) > 1e-4)
            n, total = int((moving & same).sum()), int(moving.sum())
            result['direction'][mode+'_'+name] = {'match_n': n, 'moving_target_N': total,
                'rate': n/total if total else None, 'stationary_target_N': int((~moving).sum()),
                'activated_from_stationary_n': int(((~moving) & (np.abs(p[:, i]) > 1e-4)).sum()),
                'stopped_from_moving_n': int((moving & (np.abs(p[:, i]) <= 1e-4)).sum())}
    return result


def intervene(batch, variant, stats):
    """Raw zero != train mean. Keep task/clock tokens fixed in every intervention."""
    if variant not in VARIANTS:
        raise ValueError('unknown input intervention')
    out = {k: np.array(v, copy=True) for k, v in batch.items()}
    n = c.HISTORY * 14
    if variant == 'commands_zero':
        out['observation.state'][:n] = (-np.asarray(stats['state_mean'][:n]) /
                                       np.asarray(stats['state_std'][:n]))
    elif variant == 'commands_mean':
        out['observation.state'][:n] = 0.
    elif variant in ('oldest_rgb_blank', 'current_rgb_only', 'all_rgb_blank'):
        img = out[IMAGE_KEYS[0]]
        black = normalized_image(np.zeros_like(img, dtype=np.uint8))
        h, w = img.shape[-2] // 2, img.shape[-1] // 2
        if variant == 'oldest_rgb_blank':
            img[:, :h, :w] = black[:, :h, :w]
        elif variant == 'current_rgb_only':
            img[:, :h, :] = black[:, :h, :]
            img[:, h:, :w] = black[:, h:, :w]
        else:
            img[:] = black
    return out


def lag_metrics(actions, times, *, lag=1, selected=None):
    """Per-axis Pearson; constant channels are undefined, not correlation=1.

    Exclude gaps/task boundaries before calling. selected selects current ticks
    (e.g. inference boundaries); prior tick still comes from the full sequence.
    """
    a, t = np.asarray(actions), np.asarray(times)
    if a.ndim != 2 or a.shape[1] != c.ACTION_DIM or len(t) != len(a):
        raise ValueError('aligned action/time sequence required')
    valid = np.isclose(t[lag:] - t[:-lag], lag*c.PERIOD_S, atol=1e-6, rtol=0)
    if selected is not None:
        valid &= np.asarray(selected, bool)[lag:]
    now, previous = a[lag:][valid], a[:-lag][valid]
    if not len(now):
        return {'pairs_N': 0}
    d, p = drive_components(now), drive_components(previous)
    axes = {}
    for i, name in enumerate(('forward', 'lateral', 'yaw')):
        x, y = d[:, i], p[:, i]
        moving = np.abs(y) > 1e-4
        match = (np.sign(x) == np.sign(y)) & (np.abs(x) > 1e-4) & moving
        axes[name] = {'pearson': float(np.corrcoef(x, y)[0, 1]) if
            min(float(np.std(x)), float(np.std(y))) > 1e-10 else None,
            'same_sign_n': int(match.sum()), 'moving_previous_N': int(moving.sum()),
            'stationary_previous_N': int((~moving).sum()),
            'impulse_mae': float(np.abs(x-y).mean())}
    return {'pairs_N': len(now), 'wheel_mae_to_previous': float(np.abs(now[:, :4]-previous[:, :4]).mean()),
        'pwm_mae_to_previous': float(np.abs(now[:, 8:13]-previous[:, 8:13]).mean()*1000),
        'exact_command_n': int(np.all(np.isclose(now[:, :13], previous[:, :13], atol=1e-7, rtol=0), axis=1).sum()),
        'axes': axes}


def target_pixels(rgb, kind='cyan'):
    """Diagnostic largest color component only; no target identity/pose claim."""
    import cv2
    a = np.asarray(rgb, dtype=float)/255.
    r, g, b = a.transpose(2, 0, 1)
    if kind == 'cyan':
        mask = (g > r*1.4) & (b > r*1.4) & (g > .12) & (b > .12)
    elif kind == 'red':
        mask = (r > g*1.6) & (r > b*1.6) & (r > .15)
    else:
        raise ValueError('diagnostic supports cyan/red only')
    n, components, sizes, _ = cv2.connectedComponentsWithStats(mask.astype(np.uint8), 8)
    if n <= 1:
        return {'pixels': 0, 'center': None, 'wh': [0, 0]}
    mask = components == 1+np.argmax(sizes[1:, cv2.CC_STAT_AREA])
    yy, xx = np.where(mask)
    h, w = a.shape[:2]
    return {'pixels': len(xx), 'center': [float(xx.mean()/w), float(yy.mean()/h)],
            'wh': [int(xx.max()-xx.min()+1), int(yy.max()-yy.min()+1)]}


def visibility_summary(pixels, observations):
    if len(pixels) != len(observations) or any(p['sample_id'] != o['sample_id']
            for p, o in zip(pixels, observations)):
        raise ValueError('pixel/input alignment mismatch')
    by_path = {o['rgb'][-1]['path']: p['full']['pixels'] >= 20 for p, o in zip(pixels, observations)}
    intervals = []
    for lost, entries in itertools.groupby(pixels, key=lambda r: r['full']['pixels'] < 20):
        group = list(entries)
        if lost:
            intervals.append({'first_elapsed_s': group[0]['elapsed_s'],
                'last_elapsed_s': group[-1]['elapsed_s'], 'frames_N': len(group)})
    both = [p for p in pixels if p['full']['pixels'] >= 20 and p['tile']['pixels'] >= 5]
    error = np.array([np.abs(np.array(p['full']['center'])-p['tile']['center']) for p in both])
    return {'full_threshold_pixels': 20, 'tile_threshold_pixels': 5,
        'all_four_history_frames_absent_N': sum(not any(by_path[r['path']] for r in o['rgb']) for o in observations),
        'current_absent_intervals': intervals, 'matched_visible_frames_N': len(both),
        'centroid_abs_error_normalized_xy_median': np.median(error, axis=0).tolist() if len(error) else None,
        'centroid_abs_error_normalized_xy_max': np.max(error, axis=0).tolist() if len(error) else None,
        'note': 'color-component proxy, not detector or learned-feature accuracy'}


def run(args):
    from PIL import Image
    from harness.grasp_act_policy import GraspActor, observation_batch
    args.output.mkdir(parents=True, exist_ok=False)
    obs_path, cmd_path = args.rollout/'student-inputs.jsonl', args.rollout/'commands.jsonl'
    obs, cmds = read_rows(obs_path), read_rows(cmd_path)
    if len(obs) != 900 or len(cmds) != len(obs):
        raise ValueError('expected complete 900-tick 91100 trace')
    refs = {}
    for o, cmd in zip(obs, cmds):
        c.validate_observation(o)
        if o['skill'] != cmd['skill'] or abs(o['t']-cmd['command']['t']) > 1e-6:
            raise ValueError('rollout command/input alignment')
        for ref in o['rgb']:
            old = refs.setdefault(ref['path'], ref)
            if old != ref:
                raise ValueError('conflicting image provenance')
    for rel, ref in refs.items():
        if sha256(args.rgb/rel) != ref['sha256']:
            raise ValueError('rollout RGB hash mismatch: '+rel)
    report = {'schema': 'ugrp.grasp_act.act5.measurements.v1', 'complete': False,
        'physical_runs': 0, 'training_runs': 0, 'remote_execution_started': False,
        'source_sha': args.source_sha, 'model_sha256': sha256(args.model/'model.safetensors'),
        'rollout': {'input_rows': len(obs), 'verified_unique_rgb_N': len(refs),
            'inputs_path': str(obs_path), 'inputs_sha256': sha256(obs_path),
            'commands_path': str(cmd_path), 'commands_sha256': sha256(cmd_path),
            'rgb_root': str(args.rgb)},
        'heldout': {'seeds': list(range(86045, 86050)), 'available': False,
            'ablation_inputs': 0, 'reason': 'not present in supplied local raw/tensor roots'},
        'teacher': {}, 'image_geometry': {'raw_hw': [480, 640], 'per_tile_hw': [240, 320],
            'montage_hw': [480, 640], 'pixel_count_ratio': .25,
            'loss_of_control_relevant_information_proven': False}}
    write_summary(args.output/'summary.json', report)
    acts = [c.encode_action(x['command']) for x in cmds]
    report['rollout']['previous_issued_vs_saved_max_abs_error'] = float(max(np.max(np.abs(
        np.array(c.encode_action(o['issued'][-1]))-previous)) for o, previous in zip(obs[1:], acts[:-1])))
    report['rollout']['all_wheels_zero_N'] = sum(not any(x['command']['wheels']) for x in cmds)
    report['rollout']['last_nonzero_wheel_elapsed_s'] = max(o['t']-obs[0]['t']
        for o, x in zip(obs, cmds) if any(x['command']['wheels']))
    times = [o['t'] for o in obs]
    report['rollout']['autocorrelation'] = {str(lag): lag_metrics(acts, times, lag=lag) for lag in (1, 8)}
    report['rollout']['inference_boundary_lag1'] = lag_metrics(acts, times,
        selected=np.arange(len(obs)) % c.CHUNK == 0)
    pixels = []
    for o in obs:
        with Image.open(args.rgb/o['rgb'][-1]['path']) as im:
            rgb = im.convert('RGB')
            pixels.append({'sample_id': o['sample_id'], 'elapsed_s': o['t']-obs[0]['t'],
                'full': target_pixels(rgb), 'tile': target_pixels(rgb.resize((320, 240), Image.Resampling.BILINEAR))})
    write_summary(args.output/'pixel-trace.json', pixels)
    report['image_geometry']['visibility'] = visibility_summary(pixels, obs)
    visible = [p for p in pixels if p['full']['pixels'] >= 20]
    report['rollout']['color_proxy'] = {'threshold_pixels': 20, 'visible_frames_n': len(visible),
        'last_visible': visible[-1] if visible else None,
        'first': pixels[0], 'note': 'largest cyan component; visually audit distractors and edge truncation'}
    # Frozen sparse sample: six chunk boundaries spanning the event and rollout,
    # plus one local grasp sample from each of the two available TRAIN episodes.
    probes = [{'group': 'rollout', 'row': i, 'observation': obs[i], 'rgb': args.rgb, 'target': None}
              for i in (0, 32, 56, 112, 448, 896)]
    for seed in (86000, 86001):
        raw = args.teachers/f'solo-record-{seed}-6f057f7e/raw'
        op, lp = raw/'student-r1.jsonl.zst', raw/'teacher-r1.jsonl.zst'
        groups = paired_segments(read_rows(op), read_rows(lp), done_label='last_local_row_v1')
        pairs = [pair for group in groups for pair in group]
        skills = {}
        for skill in sorted({p[0]['skill'] for p in pairs}):
            chosen = [p for p in pairs if p[0]['skill'] == skill]
            skills[skill] = {str(lag): lag_metrics(
                [c.encode_action(p[1]['clean_teacher_command']) for p in chosen],
                [p[0]['t'] for p in chosen], lag=lag) for lag in (1, 8)}
        report['teacher'][str(seed)] = {'local_rows': len(pairs), 'by_skill': skills,
            'inputs_path': str(op), 'inputs_sha256': sha256(op), 'labels_path': str(lp), 'labels_sha256': sha256(lp)}
        o, label, _ = pairs[32]
        probes.append({'group': 'training', 'seed': seed, 'row': 32, 'observation': o, 'rgb': raw,
            'target': c.encode_action(label['clean_teacher_command'], done=label['done'])})
    import torch
    torch.set_num_threads(2)
    actor = GraspActor.load(args.model, device='cpu')
    # Eight samples/one batch per variant = six bounded CPU batches, no timing benchmark.
    original = [observation_batch(p['observation'], [(p['rgb']/r['path']).read_bytes()
        for r in p['observation']['rgb']], actor.stats) for p in probes]
    predictions = {}
    for variant in VARIANTS:
        batch = torch.utils.data.default_collate([intervene(b, variant, actor.stats) for b in original])
        with torch.inference_mode():
            predictions[variant] = actor.decode_predictions(actor.policy.predict_action_chunk(batch).cpu().numpy())
        print('completed CPU probe', variant, flush=True)
    rows = []
    for i, p in enumerate(probes):
        base = predictions['baseline'][i, :1]
        variants = {}
        for variant in VARIANTS:
            pred = predictions[variant][i, :1]
            variants[variant] = {'first_action': pred[0].tolist(),
                'change_vs_baseline': change_metrics(pred, base),
                'all_horizons_change_vs_baseline': change_metrics(predictions[variant][i], predictions['baseline'][i])}
            if p['target'] is not None:
                variants[variant]['teacher_first_action_error'] = metrics(pred, [p['target']], np.zeros(1, bool))
        row = {k: p[k] for k in ('group', 'row', 'target')}
        row.update(sample_id=p['observation']['sample_id'], t=p['observation']['t'], variants=variants)
        row['elapsed_s'] = p['observation']['t'] - obs[0]['t'] if p['group'] == 'rollout' else None
        if p['group'] == 'rollout':
            actual = np.array(acts[p['row']:p['row']+c.CHUNK])
            decoded = np.array([c.encode_action({'t': 0, **{k: v for k, v in c.decode_action(x).items()
                if k in ('wheels', 'duration_s', 'pwm')}}, done=c.decode_action(x)['done'])
                for x in predictions['baseline'][i, :len(actual)]])
            row['baseline_replay_max_abs_error'] = float(np.abs(decoded-actual).max())
        rows.append(row)
    write_summary(args.output/'probes.json', rows)
    report['cpu_probe'] = {'batches': len(VARIANTS), 'batch_size': len(probes),
        'unique_inputs': len(probes), 'rollout_inputs': 6, 'training_inputs': 2, 'heldout_inputs': 0,
        'device': 'cpu', 'threads': 2, 'variants': list(VARIANTS), 'sampling': 'fixed sparse diagnostic; not full heldout evaluation',
        'baseline_replay_max_abs_error': max(r.get('baseline_replay_max_abs_error', 0) for r in rows)}
    report['ablation_mean_first_action_wheel_change'] = {group: {variant: float(np.mean([
        r['variants'][variant]['change_vs_baseline']['wheel_mae'] for r in rows if r['group'] == group]))
        for variant in VARIANTS} for group in ('rollout', 'training')}
    report['status'] = 'partial_missing_heldout_inputs'
    report['artifacts'] = {f.name: sha256(f) for f in args.output.iterdir() if f.name != 'summary.json'}
    write_summary(args.output/'summary.json', report)


def main():
    p = argparse.ArgumentParser(description=__doc__)
    for name in ('rollout', 'rgb', 'teachers', 'model', 'output'):
        p.add_argument('--'+name, type=Path, required=True)
    p.add_argument('--source-sha', required=True)
    run(p.parse_args())


if __name__ == '__main__':
    main()
