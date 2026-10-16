"""Offline full-dataset audit; numpy/Pillow only, no model or simulator execution."""
import argparse
from collections import deque
import json
from pathlib import Path

import numpy as np

from harness import grasp_act_contract as c
from harness.grasp_act_data import (GraspDataset, fit_stats, paired_segments, read_json,
    read_rows, safe_path, sha256, write_json)
from harness.grasp_act_perturb import verified_recovery_audit


def audit(root, *, raw_check=False):
    root = Path(root)
    manifest = read_json(root / 'manifest.json')
    protocol = manifest['protocol']
    files = {str(p.relative_to(root)) for p in root.rglob('*') if p.is_file()}
    if files != set(manifest['files']) | {'manifest.json'}:
        raise ValueError('dataset file inventory mismatch')
    for rel, digest in manifest['files'].items():
        if sha256(safe_path(root, rel)) != digest:
            raise ValueError('dataset file hash mismatch: ' + rel)
    splits = {split: GraspDataset(root, split) for split in ('train', 'validation')}
    seeds = [e['seed'] for e in manifest['episodes']]
    if len(seeds) != len(set(seeds)) or set(seeds) != set(protocol['train_seeds'] + protocol['validation_seeds']):
        raise ValueError('episode inventory mismatch')
    rows = 0
    raw_rows = 0
    recovery_episodes = 0
    train_states, train_actions, train_seeds = [], [], []
    for episode in manifest['episodes']:
        folder = safe_path(root, episode['path'])
        split = 'train' if episode['seed'] in protocol['train_seeds'] else 'validation'
        if episode['split'] != split:
            raise ValueError('split mismatch')
        with np.load(folder / 'tensors.npz', allow_pickle=False) as data:
            tensors = {k: data[k] for k in data.files}
        if set(tensors) != {'state', 'action', 'action_is_pad', 'image_index'}:
            raise ValueError('tensor whitelist mismatch')
        if not all(np.isfinite(x).all() for x in tensors.values()):
            raise ValueError('nonfinite tensors')
        rows += len(tensors['state'])
        if not raw_check:
            continue
        run = Path(episode['source_root'])
        for rel, digest in episode['source_hashes'].items():
            if sha256(safe_path(run, rel)) != digest:
                raise ValueError('source hash mismatch')
        raw = run / 'raw'
        robot = episode['robot_id']
        observations = read_rows(raw / f'student-{robot}.jsonl.zst')
        labels = read_rows(raw / f'teacher-{robot}.jsonl.zst')
        result_path = raw / 'result.json.zst'
        result = read_json(result_path)
        recovery = verified_recovery_audit(result, result_path)
        recovery_episodes += int(recovery['recovery_scene_N'] > 0 and result['physical_success'])
        ledger_name = Path(result['recovery']['ledger']).name
        ledger_path = run / ledger_name
        ledger = read_rows(ledger_path if ledger_path.exists() else Path(str(ledger_path) + '.zst'))
        if len(ledger) != len(observations):
            raise ValueError('issued ledger alignment mismatch')
        history = deque(observations[0]['issued'], maxlen=c.HISTORY)
        clock = c.IssuedClock()
        for obs, command_row in zip(observations, ledger):
            c.validate_observation(obs)
            if obs['issued'] != list(history) or obs['t'] != command_row['t']:
                raise ValueError('issued command history mismatch')
            clocks = clock.observe(obs['skill'], obs['t'], obs['issued'][-1]['pwm'])
            if any(abs(obs[k] - v) > 1e-8 for k, v in clocks.items()):
                raise ValueError('own command clock mismatch')
            history.append(c.command(command_row['applied_command']))
        raw_rows += len(observations)
        groups = paired_segments(observations, labels, done_label=manifest['done_label'],
            include_initial_approach_v1=protocol.get('include_initial_approach_v1', False))
        selected = [pair for group in groups for pair in group]
        metadata = read_json(folder / 'samples.json')
        provenance = read_json(folder / 'rgb-provenance.json')
        image_indices = {ref['path']: i for i, ref in enumerate(provenance)}
        if len(selected) != len(tensors['state']) or len(selected) != len(metadata):
            raise ValueError('selected row count mismatch')
        windows = [window for group in groups for window in c.training_windows(
            [p[0] for p in group], [p[1] for p in group])]
        for i, ((obs, label, _), window) in enumerate(zip(selected, windows)):
            if metadata[i]['sample_id'] != obs['sample_id']:
                raise ValueError('sample order mismatch')
            comparisons = {'state': np.asarray(c.context(obs), np.float32),
                'action': np.asarray(window['action'], np.float32),
                'action_is_pad': np.asarray(window['action_is_pad'], bool),
                'image_index': np.asarray([image_indices[r['path']] for r in obs['rgb']], np.int64)}
            if any(not np.array_equal(tensors[k][i], value) for k, value in comparisons.items()):
                raise ValueError('tensor/raw reconstruction mismatch')
            if split == 'train':
                train_states.append(c.context(obs))
                train_actions.append(c.encode_action(label['clean_teacher_command'], done=label['done']))
                train_seeds.append(episode['seed'])
    if raw_check:
        if fit_stats(train_states, train_actions, train_seeds) != splits['train'].stats:
            raise ValueError('train-only statistics mismatch')
    return {'schema': 'ugrp.grasp_act.dataset_audit.v1', 'class': 'dev',
        'dataset_manifest_sha256': sha256(root / 'manifest.json'),
        'files_verified': len(manifest['files']), 'episodes': len(seeds),
        'rows_selected': rows, 'raw_rows_audited': raw_rows,
        'split_rows': {k: len(v) for k, v in splits.items()},
        'split_episodes': {k: sum(e['split'] == k for e in manifest['episodes']) for k in splits},
        'successful_recovery_episodes': recovery_episodes if raw_check else None,
        'normalization_recomputed_train_only': raw_check,
        'all_raw_contexts_commands_clocks_reconstructed': raw_check,
        'input_keys': manifest['input_keys'], 'forbidden_input_fields': 0,
        'teacher_input_fields': 0, 'research_result': False, 'student_success': False}


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('--dataset', type=Path, required=True)
    p.add_argument('--output', type=Path, required=True)
    p.add_argument('--raw-check', action='store_true')
    a = p.parse_args()
    result = audit(a.dataset, raw_check=a.raw_check)
    write_json(a.output, result)
    print(json.dumps(result))


if __name__ == '__main__':
    main()
