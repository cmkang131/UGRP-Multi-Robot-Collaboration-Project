"""R3 data dry-run: done-window positive rows, priors and truncated chunks.

CPU only and read-only over the registered dataset. It builds the two exact
ReferenceDataset views used by R3-A/R3-B (default vs done_window_ticks) and
records the data delta before any GPU training:

  * grasp positive rows 200 -> 200*K (release rows are a different skill)
  * per-skill completion priors before/after
  * rows whose chunk target is truncated by the earlier completion window
  * R3-B clock-jitter eligible rows (verify_lift/hold) and offsets

The registered dataset may have been retrieved without JPEG frame files (the
E0 clock audit only needed tensors/samples). Targets, priors and labels do not
read images, so this tool then creates a derived root of symlinked episodes and
a manifest whose episode file list omits the absent frames.json. Every present
tensor/sample file is still sha256-verified against the registered manifest.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys
from datetime import datetime, timezone

import numpy as np

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / 'scripts'))
from act18_policy import (DONE_CLOCK_JITTER_PHASES, DONE_CLOCK_JITTER_SEED, ReferenceDataset)

DEFAULT_DATASET_MANIFEST_SHA = '44c1c46073aa08ea028324ffe924b67d862a2f01b56f4db11afad17000a9b198'
DEFAULT_NORMALIZATION_SHA = 'd08f8672434791ad68cf99fb36a87d76e6d089c908da7b2a27effbf729ba6ee6'
IMAGE_FILES = ('frames.json', 'frames.json.zst')


def sha256(path):
    digest = hashlib.sha256()
    with Path(path).open('rb') as stream:
        for block in iter(lambda: stream.read(1 << 20), b''):
            digest.update(block)
    return digest.hexdigest()


def read_manifest(path):
    path = Path(path)
    data = subprocess.check_output(['zstd', '-dc', str(path)]) if path.suffix == '.zst' else path.read_bytes()
    return json.loads(data), data


def derive_image_free_root(dataset, manifest, scratch):
    """Symlink episode folders and write a manifest without absent image files."""
    scratch = Path(scratch)
    if scratch.exists():
        raise ValueError('derived dry-run root already exists: %s' % scratch)
    scratch.mkdir(parents=True)
    derived = json.loads(json.dumps(manifest))
    episodes = []
    missing = set()
    replaced = 0
    for episode in manifest['episodes']:
        folder = Path(dataset) / episode['path']
        files = {}
        needs_frames = False
        for name, digest in episode['files'].items():
            if not (folder / name).is_file():
                if name not in IMAGE_FILES:
                    raise FileNotFoundError('registered non-image file missing: %s/%s' % (folder, name))
                missing.add(name)
                needs_frames = True
                continue
            files[name] = digest
        if not files:
            raise ValueError('episode has no verifiable files: %s' % folder)
        target = scratch / episode['path']
        target.mkdir()
        if needs_frames:
            # Targets, priors and labels never read images. Dataset.__init__
            # still opens frames.json, so the derived root gets an explicit
            # empty placeholder; the image-bearing manifest keys are dropped.
            frames = target / 'frames.json'
            frames.write_text('[]')
            files['frames.json'] = sha256(frames)
            replaced += 1
        for name, digest in files.items():
            if name == 'frames.json':
                continue
            os.symlink(folder.resolve() / name, target / name)
        entry = dict(episode)
        entry['files'] = files
        episodes.append(entry)
    derived['episodes'] = episodes
    norm = manifest['normalization']['path']
    shutil.copyfile(Path(dataset) / norm, scratch / norm)
    manifest_path = scratch / 'manifest.json'
    manifest_path.write_text(json.dumps(derived))
    return scratch, missing, manifest_path, replaced


def counter(dataset):
    counts = {}
    for index, (shard, row) in enumerate(dataset.index):
        skill = dataset.metadata[index]['skill']
        value = float(dataset.shards[shard]['action'][row, 0, -1])
        if value not in (0., 1.):
            raise ValueError('binary completion target required')
        counts.setdefault(skill, [0, 0])
        counts[skill][0] += int(value)
        counts[skill][1] += 1
    return {skill: dict(positive_n=n, rows_N=total, positive_fraction=n / total)
            for skill, (n, total) in counts.items()}


def chunk_stats(dataset):
    """Valid horizon length per row from the reconstructed pads."""
    lengths = np.asarray([int((~dataset.shards[shard]['action_is_pad'][row]).sum())
                          for shard, row in dataset.index], dtype=np.int64)
    return lengths


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--dataset', type=Path, required=True,
                        help='registered v7 dataset root (episode folders, manifest or manifest.json.zst)')
    parser.add_argument('--manifest', type=Path,
                        help='registered manifest (json or .zst); default dataset/manifest.json(.zst)')
    parser.add_argument('--out', type=Path, required=True, help='new data-delta.json path')
    parser.add_argument('--scratch', type=Path, help='derived image-free root (default next to --out)')
    parser.add_argument('--chunk', type=int, default=8)
    parser.add_argument('--window-ticks', type=int, default=10)
    parser.add_argument('--jitter-s', type=float, default=1.0)
    parser.add_argument('--expected-manifest-sha', default=DEFAULT_DATASET_MANIFEST_SHA)
    parser.add_argument('--expected-normalization-sha', default=DEFAULT_NORMALIZATION_SHA)
    args = parser.parse_args(argv)
    dataset = args.dataset
    manifest_path = args.manifest or next(
        path for path in (dataset / 'manifest.json', dataset / 'manifest.json.zst') if path.is_file())
    manifest, raw_manifest = read_manifest(manifest_path)
    manifest_sha = hashlib.sha256(raw_manifest).hexdigest()
    if args.expected_manifest_sha and manifest_sha != args.expected_manifest_sha:
        raise ValueError('dataset manifest sha != preregistered value: %s' % manifest_sha)
    if manifest.get('schema') != 'ugrp.act17.jpeg_dataset.v1' or not manifest.get('complete'):
        raise ValueError('complete registered v7 dataset required')
    norm_path = dataset / manifest['normalization']['path']
    normalization_sha = sha256(norm_path)
    if args.expected_normalization_sha and normalization_sha != args.expected_normalization_sha:
        raise ValueError('normalization sha != preregistered value: %s' % normalization_sha)
    missing = {name for episode in manifest['episodes'] for name in episode['files']
               if not (dataset / episode['path'] / name).is_file()}
    derived_manifest_sha = None
    used_root = dataset
    if missing:
        if not missing <= set(IMAGE_FILES):
            raise FileNotFoundError('registered files missing beyond image frames: %s' % sorted(missing))
        scratch = args.scratch or (args.out.parent / 'derived-dataset')
        used_root, missing, derived_path, replaced_frames = derive_image_free_root(dataset, manifest, scratch)
        derived_manifest_sha = sha256(derived_path)
    out = Path(args.out)
    out.parent.mkdir(parents=True, exist_ok=True)
    base = ReferenceDataset(used_root, 'train', chunk=args.chunk)
    window = ReferenceDataset(used_root, 'train', chunk=args.chunk,
                              done_window_ticks=args.window_ticks)
    jitter = ReferenceDataset(used_root, 'train', chunk=args.chunk,
                              done_window_ticks=args.window_ticks,
                              done_clock_jitter_s=args.jitter_s) if args.jitter_s else None
    base_counts, window_counts = counter(base), counter(window)
    prior_before = base.completion_priors('uniform_episode_v1')
    prior_after = window.completion_priors('uniform_episode_v1')
    base_lengths, window_lengths = chunk_stats(base), chunk_stats(window)
    if np.any(window_lengths > base_lengths):
        raise ValueError('done window extended a chunk target')
    truncated = np.flatnonzero(window_lengths < base_lengths)
    h0_changed = np.flatnonzero(
        np.asarray([base.shards[shard]['action'][row, 0, -1] != window.shards[shard]['action'][row, 0, -1]
                    for shard, row in window.index]))
    grasp_expected = args.window_ticks * base_counts.get('grasp', {}).get('positive_n', 0)
    release_unchanged = window_counts.get('release') == base_counts.get('release')
    boundaries_ok = True
    if args.window_ticks:
        receipt = window.done_window_receipt
        # Every added row must sit in the same episode+skill as its anchor and
        # be 0.1 s spaced; the helper guarantees it, recheck the aggregate.
        added = receipt['added_rows']
        boundaries_ok = receipt['added_rows'] == receipt['window_rows'] - receipt['positive_rows']
    else:
        receipt = dict(window_ticks=0, positive_rows=0, window_rows=0, added_rows=0,
                       stopped_by_boundary=0, episodes=0)
    jitter_info = None
    if jitter is not None:
        eligible = np.asarray([row.get('teacher_phase') in DONE_CLOCK_JITTER_PHASES
                               for row in jitter.metadata], dtype=bool)
        offsets = jitter.clock_jitter_offsets_s
        phases = {}
        for row, keep in zip(jitter.metadata, eligible):
            if keep:
                phases[row['teacher_phase']] = phases.get(row['teacher_phase'], 0) + 1
        jitter_info = dict(done_clock_jitter_s=args.jitter_s,
                           rng_seed=DONE_CLOCK_JITTER_SEED,
                           augmented_rows=jitter.clock_jitter_rows,
                           rows_by_phase=phases,
                           ineligible_nonzero=int(np.count_nonzero(offsets[~eligible])),
                           eligible_min_s=float(offsets[eligible].min()) if eligible.any() else None,
                           eligible_max_s=float(offsets[eligible].max()) if eligible.any() else None,
                           eligible_mean_s=float(offsets[eligible].mean()) if eligible.any() else None)
    checks = dict(
        grasp_window_rows_equal_window_ticks_times_base=window_counts.get('grasp', {}).get('positive_n') == grasp_expected,
        release_positives_untouched=release_unchanged,
        window_only_truncates=bool(np.all(window_lengths <= base_lengths)),
        window_added_rows_match_receipt=boundaries_ok,
        prior_both_classes_per_skill=all(0 < value['positive_fraction'] < 1
                                         for value in prior_after.values()),
        jitter_outside_target_phases_zero=(jitter_info is None or jitter_info['ineligible_nonzero'] == 0))
    if not all(checks.values()):
        raise ValueError('R3 data dry-run checks failed: %s' % checks)
    report = dict(
        schema='ugrp.act18.r3_data_delta.v1',
        generated_utc=datetime.now(timezone.utc).strftime('%Y-%m-%dT%H:%M:%SZ'),
        source=dict(dataset=str(dataset), manifest_path=str(manifest_path),
                    manifest_sha256=manifest_sha, normalization_sha256=normalization_sha,
                    used_root=str(used_root), derived_root=bool(derived_manifest_sha),
                    derived_manifest_sha256=derived_manifest_sha,
                    missing_files=sorted(missing),
                    replaced_image_metadata_rows=replaced_frames,
                    note=('image-free derived root: frozen image frames were not part of the '
                          'local retrieval; targets/priors/labels read only tensors+samples, whose '
                          'hashes are verified against the registered manifest')
                    if derived_manifest_sha else 'complete dataset used directly'),
        flags=dict(chunk=args.chunk, done_window_ticks=args.window_ticks,
                   done_clock_jitter_s=args.jitter_s, done_clock_jitter_seed=DONE_CLOCK_JITTER_SEED),
        rows=dict(train_rows=len(base), train_episodes=len(base.episode_indices)),
        positives=dict(before=base_counts, after=window_counts,
                       grasp_expected=window_counts.get('grasp', {}).get('positive_n'),
                       receipt=receipt),
        prior=dict(before=prior_before, after=prior_after),
        chunk_targets=dict(
            rows_with_earlier_truncation=int(len(truncated)),
            added_padded_slots=int((base_lengths - window_lengths).sum()),
            rows_with_h0_done_change=int(len(h0_changed)),
            max_valid_horizons_before=int(base_lengths.max()),
            max_valid_horizons_after=int(window_lengths.max()),
            samples=[dict(index=int(index), skill=base.metadata[index]['skill'],
                          teacher_phase=base.metadata[index]['teacher_phase'],
                          before=int(base_lengths[index]), after=int(window_lengths[index]))
                     for index in truncated[:20]]),
        jitter=jitter_info,
        checks=checks,
        reproduce=sys.argv)
    out.write_text(json.dumps(report, indent=2) + '\n')
    print(json.dumps(dict(out=str(out), positives=report['positives'],
                          prior=report['prior'], chunk_targets=report['chunk_targets'],
                          jitter=report['jitter']), indent=2))


if __name__ == '__main__':
    main()
