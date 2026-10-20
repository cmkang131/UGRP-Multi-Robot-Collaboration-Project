"""ACT18 C4c — teacher demonstration and R8 train-split aggregation by object kind.

CPU only, read-only. Joins the E0 teacher columns (`seed`) to the E0 dataset manifest
(`kind` per episode) and reports, per kind: demo count, first-open `skill_elapsed_s`,
release-entry `pwm_elapsed_s`, release pose (servo PWM at release entry and at the
pose-move onset) and the release tick count. Also reports the R8 training split's
kind distribution from the released dataset manifest. Default OFF.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import statistics
import sys
from collections import Counter, defaultdict
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SERVOS = ('1', '3', '4', '5', '6')
KINDS = ('cyan', 'green', 'red', 'yellow')


def sha256(path):
    digest = hashlib.sha256()
    with Path(path).open('rb') as handle:
        for block in iter(lambda: handle.read(1 << 20), b''):
            digest.update(block)
    return digest.hexdigest()


def read_rows(path):
    return [json.loads(line) for line in Path(path).read_text().splitlines() if line.strip()]


def episode_summary(rows):
    """Teacher release facts for one episode from its column rows in time order."""
    release = [row for row in rows if row['skill'] == 'release']
    if not release:
        raise ValueError('no release rows')
    entry = release[0]
    open_row = next((row for row in release if row['teacher_pwm']['1'] >= 1900), None)
    pose_row = None
    previous = None
    for row in release:
        if previous is not None and any(abs(row['teacher_pwm'][s] - previous['teacher_pwm'][s]) >= 3
                                        for s in SERVOS):
            pose_row = row
            break
        previous = row
    return dict(
        release_ticks=len(release),
        entry_pwm_elapsed_s=entry['pwm_elapsed_s'],
        entry_pwm={s: entry['teacher_pwm'][s] for s in SERVOS},
        open_skill_elapsed_s=None if open_row is None else open_row['skill_elapsed_s'],
        open_pwm_elapsed_s=None if open_row is None else open_row['pwm_elapsed_s'],
        pose_pwm_elapsed_s=None if pose_row is None else pose_row['pwm_elapsed_s'],
        pose_pwm=None if pose_row is None else {s: pose_row['teacher_pwm'][s] for s in SERVOS},
        max_pwm_elapsed_s=max(row['pwm_elapsed_s'] for row in release))


def quantiles(values):
    values = sorted(values)
    if not values:
        return None
    return dict(n=len(values), min=values[0], median=statistics.median(values), max=values[-1])


def summarize(episodes):
    report = {}
    for kind in KINDS:
        rows = [episode for episode in episodes if episode['kind'] == kind]
        if not rows:
            continue
        entry_pose = {s: [row['entry_pwm'][s] for row in rows] for s in SERVOS}
        pose_pose = {s: [row['pose_pwm'][s] for row in rows if row['pose_pwm']] for s in SERVOS}
        report[kind] = dict(
            demos=len(rows),
            release_ticks=quantiles([row['release_ticks'] for row in rows]),
            open_skill_elapsed_s=sort_counts([row['open_skill_elapsed_s'] for row in rows]),
            open_pwm_elapsed_s=sort_counts([row['open_pwm_elapsed_s'] for row in rows]),
            entry_pwm_elapsed_s=sort_counts([row['entry_pwm_elapsed_s'] for row in rows]),
            pose_pwm_elapsed_s=sort_counts([row['pose_pwm_elapsed_s'] for row in rows]),
            entry_pwm={s: dict(mean=statistics.mean(entry_pose[s]),
                               min=min(entry_pose[s]), max=max(entry_pose[s]),
                               spread=max(entry_pose[s]) - min(entry_pose[s])) for s in SERVOS},
            pose_pwm={s: dict(mean=statistics.mean(pose_pose[s]),
                              min=min(pose_pose[s]), max=max(pose_pose[s]),
                              spread=max(pose_pose[s]) - min(pose_pose[s]))
                      for s in SERVOS if pose_pose[s]},
            opens=sum(1 for row in rows if row['open_skill_elapsed_s'] is not None))
    return report


def c2c_kind_table(run_root):
    """C2c evaluation cohort by kind: worlds, grasp done, open issued, release success."""
    table = {}
    for run in sorted(p for p in Path(run_root).iterdir()
                      if p.is_dir() and p.name.startswith('C2c-')):
        for stage in sorted(p for p in run.iterdir() if p.is_dir()):
            for group in sorted(p for p in stage.iterdir() if p.is_dir()):
                summary = group / 'evaluation' / 'summary.json'
                if not summary.is_file():
                    continue
                for score in json.loads(summary.read_text())['student_scores']:
                    kind = str(score['assigned_item_id']).rsplit('_', 1)[0]
                    value = table.setdefault(kind, dict(worlds=0, grasp_done=0, release_open=0,
                                                        release_success=0, failure=Counter()))
                    value['worlds'] += 1
                    value['grasp_done'] += int(bool(score.get('grasp_done_requested')))
                    value['release_success'] += int(bool(score['release_success']))
                    done = score.get('issued_done_times') or {}
                    value['release_open'] += int('release' in done)
                    value['failure'][str(score['failure_reason'])] += 1
    for value in table.values():
        value['failure'] = dict(sorted(value['failure'].items()))
    return dict(sorted(table.items()))


def sort_counts(values):
    values = [round(value, 6) for value in values if value is not None]
    return dict(sorted(Counter(values).items()))


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--enabled', action='store_true')
    parser.add_argument('--columns', type=Path, required=True)
    parser.add_argument('--dataset-manifest', type=Path, required=True)
    parser.add_argument('--r8-manifest', type=Path, required=True,
                        help='R8 released dataset manifest (JSON, not zstd)')
    parser.add_argument('--out', type=Path, required=True)
    parser.add_argument('--split', default='train')
    parser.add_argument('--c2c-root', type=Path,
                        help='optional C2c run root for the evaluation-cohort kind table')
    args = parser.parse_args(argv)
    if not args.enabled:
        raise SystemExit('C4c kind aggregation is default OFF; pass --enabled')

    manifest = json.loads(args.dataset_manifest.read_text())
    kind_by_seed = {}
    split_by_seed = {}
    for episode in manifest['episodes']:
        kind_by_seed[int(episode['seed'])] = episode['kind']
        split_by_seed[int(episode['seed'])] = episode['split']
    selected = {seed for seed, split in split_by_seed.items() if split == args.split}

    rows_by_seed = defaultdict(list)
    for row in read_rows(args.columns):
        server_seed = int(row['seed'])
        if server_seed not in selected:
            continue
        rows_by_seed[server_seed].append(row)
    missing = sorted(selected - set(rows_by_seed))
    if missing:
        raise SystemExit('columns missing seeds: %s' % missing[:5])
    if len(rows_by_seed) != len(selected):
        raise SystemExit('seed count mismatch')
    for rows in rows_by_seed.values():
        rows.sort(key=lambda row: row['t'])

    episodes = []
    for seed, rows in sorted(rows_by_seed.items()):
        if rows[0]['split'] != args.split:
            raise SystemExit('split column mismatch for seed %s' % seed)
        summary = episode_summary(rows)
        summary.update(seed=seed, kind=kind_by_seed[seed])
        episodes.append(summary)

    r8 = json.loads(args.r8_manifest.read_text())
    r8_distribution = Counter((episode['split'], episode['kind']) for episode in r8['episodes'])

    configs = json.loads((ROOT / 'experiments' / '2026-10-17-act18' /
                          'protocol.json').read_text())
    report = dict(
        schema='ugrp.act18.c4c_kind.v1',
        inputs=dict(columns=str(args.columns), columns_sha256=sha256(args.columns),
                    dataset_manifest=str(args.dataset_manifest),
                    dataset_manifest_sha256=sha256(args.dataset_manifest),
                    r8_manifest=str(args.r8_manifest),
                    r8_manifest_sha256=sha256(args.r8_manifest)),
        split=args.split,
        episodes=len(episodes),
        kind_distribution=dict(Counter(episode['kind'] for episode in episodes)),
        protocol_train_seeds=len(configs['train_seeds']),
        protocol_validation8_seeds=len(configs['validation8_seeds']),
        r8_split_kind_distribution={f'{split}:{kind}': count for (split, kind), count
                                    in sorted(r8_distribution.items())},
        by_kind=summarize(episodes),
        c2c_cohort_kind=({} if args.c2c_root is None else c2c_kind_table(args.c2c_root)),
        per_episode=[dict(seed=episode['seed'], kind=episode['kind'],
                          release_ticks=episode['release_ticks'],
                          open_skill_elapsed_s=episode['open_skill_elapsed_s'],
                          entry_pwm_elapsed_s=episode['entry_pwm_elapsed_s'],
                          pose_pwm_elapsed_s=episode['pose_pwm_elapsed_s'],
                          entry_pwm=episode['entry_pwm'], pose_pwm=episode['pose_pwm'])
                      for episode in episodes],
        note=('teacher columns carry no object_kind column; kind is joined from the E0 '
              'dataset manifest episode list by seed. Release pose is the teacher command '
              'at the release-entry tick and at the first pose-move onset.'))
    args.out.parent.mkdir(parents=True, exist_ok=True)
    args.out.write_text(json.dumps(report, indent=2, sort_keys=True) + '\n')
    print(json.dumps(dict(episodes=report['episodes'],
                          kind_distribution=report['kind_distribution'],
                          r8_split_kind_distribution=report['r8_split_kind_distribution'],
                          open_se={kind: value['open_skill_elapsed_s']
                                   for kind, value in report['by_kind'].items()},
                          entry_pe={kind: value['entry_pwm_elapsed_s']
                                    for kind, value in report['by_kind'].items()},
                          pose_pe={kind: value['pose_pwm_elapsed_s']
                                   for kind, value in report['by_kind'].items()}), indent=1))
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
