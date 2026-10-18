"""Verify beampair8 archive and split by seed, refitting TRAIN-only stats.

No teacher/physics/render/model API. Original archive and tensors stay intact.
The 10% validation fraction is a preregistered development split, not an
acceptance threshold. ceil(185/10)=19 seeds, selected by a fixed hash ordering.
"""
import argparse
from collections import Counter
from copy import deepcopy
import hashlib
import json
import math
import os
from pathlib import Path
import subprocess

import numpy as np

from harness.grasp_act_data import GraspDataset, fit_stats, sha256, write_json, read_rows
from harness.beampair_recording import existing
from scripts.beamact1_runtime import require_gcp2

ARCHIVE_SHA = '739a9faeaf35cd0cf3d8c73b05bdab76ccb8866b1b55dc81d1bb9e9e05fae251'


def split_seeds(seeds, reserved):
    seeds, reserved = sorted(seeds), set(reserved)
    if len(seeds) != 185 or len(set(seeds)) != len(seeds) or set(seeds) & reserved:
        raise ValueError('185 unique recording seeds, disjoint from heldout20 required')
    ranked = sorted(seeds, key=lambda s: hashlib.sha256(f'beamact1-v1:{s}'.encode()).hexdigest())
    validation = sorted(ranked[:math.ceil(len(seeds) / 10)])
    return sorted(set(seeds) - set(validation)), validation


def prepare(source, output, *, raw_root):
    source, output, raw_root = Path(source), Path(output), Path(raw_root)
    original = json.loads((source / 'manifest.json').read_text())
    if not original['complete'] or len(original['episodes']) != 370:
        raise ValueError('complete beampair8 dataset required')
    reserved = original['protocol']['heldout_reserved_only']
    if reserved != list(range(8329000, 8329020)):
        raise ValueError('exact beampair8 heldout20 required')
    train, validation = split_seeds(original['protocol']['train_seeds'], reserved)
    output.mkdir(parents=True, exist_ok=False)
    report = deepcopy(original)
    report['protocol'].update(train_seeds=train, validation_seeds=validation,
        split_rule='sha256(beamact1-v1:seed), first ceil(N/10) validation; both robots grouped',
        weights='shared; identical robot/camera/action contract, alternating end token',
        source_manifest_sha256=sha256(source / 'manifest.json'))
    states, actions, fitseeds, stages = [], [], [], []
    counts = Counter()
    for episode in report['episodes']:
        folder = output / episode['path']
        folder.mkdir()
        for name, digest in episode['files'].items():
            src = source / episode['path'] / name
            if sha256(src) != digest:
                raise ValueError('beampair8 internal file hash mismatch')
            os.link(src, folder / name)
        episode['split'] = 'train' if episode['seed'] in train else 'validation'
        with np.load(folder / 'tensors.npz', allow_pickle=False) as f:
            if episode['split'] == 'train':
                states.extend(f['state']); actions.extend(f['action'][:, 0])
                fitseeds.extend([episode['seed']] * len(f['state']))
        metadata = json.loads((folder / 'samples.json').read_text())
        raw = raw_root / f"beampair8-record-{episode['seed']}-72c0e83d" / 'training'
        labels = read_rows(existing(raw, f"teacher-{episode['robot_id']}.jsonl"))
        labels = {r['sample_id']: r for r in labels}
        # Sidecar for OFFLINE stratification; absent from every input tensor.
        for row in metadata:
            label = labels[row['sample_id']]
            stages.append(dict(sample_id=row['sample_id'], seed=episode['seed'],
                robot_id=episode['robot_id'], split=episode['split'], t=row['t'],
                phase=label['teacher_phase']))
        counts[episode['split']] += len(metadata)
    stats = fit_stats(states, actions, fitseeds)
    write_json(output / 'normalization.json', stats)
    report['normalization'] = dict(path='normalization.json', sha256=sha256(output / 'normalization.json'))
    write_json(output / 'RUN_META.json', {'class': 'milestone', 'task': 'beamact1',
        'raw_source_retained': True, 'source_archive_sha256': ARCHIVE_SHA})
    report['files'] = {str(f.relative_to(output)): sha256(f) for f in sorted(output.rglob('*'))
                       if f.is_file() and f.name != 'manifest.json'}
    write_json(output / 'manifest.json', report)
    write_json(output.parent / 'stages.json', stages)
    for split in ('train', 'validation'):
        data = GraspDataset(output, split)
        assert len(data) == counts[split]
        for i in {0, len(data)//2, len(data)-1}:
            assert all(np.isfinite(v).all() for v in data[i].values())
    summary = dict(status='READY', train_seeds=train, validation_seeds=validation,
        heldout_reserved_only=reserved, seed_overlap=0, train_rows=counts['train'],
        validation_rows=counts['validation'], total_rows=sum(counts.values()),
        normalization_rows=stats['rows'], normalization_train_only=True,
        weights='shared', source_archive_sha256=ARCHIVE_SHA,
        source_manifest_sha256=sha256(source/'manifest.json'),
        dataset_manifest_sha256=sha256(output/'manifest.json'),
        stages_sha256=sha256(output.parent/'stages.json'),
        input_fields=['observation.images.own_history', 'observation.state'],
        phase_sidecar_evaluation_only=True, camera_conversion_changed=False,
        teacher_success=dict(n=185,N=200,percent=92.5,gate_95_percent_passed=False),
        admission='explicit user beamact1 request; prior beampair7 gate40/40; no new >=95% claim',
        original_files_modified=False)
    write_json(output.parent/'dataset-summary.json', summary)
    return summary


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('--archive', type=Path, required=True)
    p.add_argument('--output', type=Path, required=True)
    p.add_argument('--raw-root', type=Path, required=True)
    a = p.parse_args()
    require_gcp2(training=False)
    if sha256(a.archive) != ARCHIVE_SHA:
        raise ValueError('archive SHA mismatch')
    a.output.mkdir(parents=True, exist_ok=False)
    # GNU tar writes a new empty destination, with no owner/permission import.
    subprocess.run(['tar', '--zstd', '--no-same-owner', '--no-same-permissions',
                    '-xf', str(a.archive), '-C', str(a.output)], check=True)
    prepare(a.output/'dataset', a.output/'split-v1', raw_root=a.raw_root)


if __name__ == '__main__':
    main()
