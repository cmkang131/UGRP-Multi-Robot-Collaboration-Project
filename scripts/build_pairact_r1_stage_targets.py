"""Build the pairact-r1 stage-target sidecar for a converted pair dataset (P3 -> P4).

Reads only: the audited ``ugrp.grasp_act.dataset.v1`` output (manifest,
samples.json, tensors.npz padding) and each episode's teacher label file
(``teacher_phase``), whose hash must match the manifest's source_hashes.
Writes a new directory; the dataset itself is never modified. Stage labels are
offline targets, never model inputs.
"""
from __future__ import annotations

import argparse
from collections import Counter
import json
from pathlib import Path
import sys

import numpy as np

if str(Path(__file__).resolve().parents[1]) not in sys.path:
    sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from harness import pairact_r1 as p
from harness.grasp_act_data import read_rows, safe_path, sha256, write_json


def teacher_file(episode):
    robot = episode['robot_id']
    names = [k for k in episode['source_hashes']
             if Path(k).name in (f'teacher-{robot}.jsonl', f'teacher-{robot}.jsonl.zst')]
    if len(names) != 1:
        raise ValueError(f'{episode["path"]}: exactly one hashed teacher file required')
    path = Path(episode['source_root']) / names[0]
    if sha256(path) != episode['source_hashes'][names[0]]:
        raise ValueError(f'{episode["path"]}: teacher label hash mismatch')
    return path


def build(dataset, output):
    dataset, output = Path(dataset), Path(output)
    manifest = json.loads((dataset / 'manifest.json').read_text())
    if not manifest.get('complete'):
        raise ValueError('complete audited dataset required')
    output.mkdir(parents=True, exist_ok=False)
    entries, totals = [], Counter()
    for episode in manifest['episodes']:
        folder = safe_path(dataset, episode['path'])
        samples = json.loads((folder / 'samples.json').read_text())
        with np.load(folder / 'tensors.npz', allow_pickle=False) as f:
            pad = f['action_is_pad']
        phases = {}
        for row in read_rows(teacher_file(episode)):
            if 'teacher_phase' not in row:
                raise ValueError(f'{episode["path"]}: teacher row without teacher_phase')
            phases[row['sample_id']] = row['teacher_phase']
        target = p.episode_stage_targets(samples, phases, pad)
        name = f'{episode["path"]}.stage_target.npy'
        np.save(output / name, target, allow_pickle=False)
        counts = Counter(p.STAGES[i] for i in target[:, 0].tolist() if i != p.PAD)
        totals.update(counts)
        entries.append(dict(path=episode['path'], split=episode['split'], file=name,
                            sha256=sha256(output / name), h0_stage_counts=dict(counts)))
    sidecar = dict(schema=p.TARGET_SCHEMA, stages=list(p.STAGES), dataset_manifest_sha256=sha256(dataset / 'manifest.json'),
                   phase_map=p.TEACHER_PHASE_TO_STAGE, episodes=entries, h0_stage_counts=dict(totals),
                   missing_stages=[s for s in p.STAGES if not totals[s]])
    write_json(output / 'stage-targets.json', sidecar)
    return sidecar


def main(argv=None):
    a = argparse.ArgumentParser()
    a.add_argument('--dataset', type=Path, required=True)
    a.add_argument('--output', type=Path, required=True)
    args = a.parse_args(argv)
    sidecar = build(args.dataset, args.output)
    print(json.dumps(dict(episodes=len(sidecar['episodes']), h0_stage_counts=sidecar['h0_stage_counts'],
                          missing_stages=sidecar['missing_stages']), indent=1))


if __name__ == '__main__':
    main()
