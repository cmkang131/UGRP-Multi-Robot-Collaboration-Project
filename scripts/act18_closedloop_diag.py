"""Closed-loop state-distribution diagnosis for act18 candidates (CPU, no GPU).

Compares the student's own closed-loop issued command stream (recorded actor
actions) with the teacher command distribution at the same skill/elapsed phase,
so early stopping and weakened wheel commands can be located in phase space.
Parts: (1) per phase-bin activity table, (2) halt-onset (last movement) table,
(3) wheel magnitude comparison. Default OFF.
"""
import argparse
import json
from pathlib import Path
import sys

import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parent))
from act17_data import read

SKILLS = ('grasp', 'release')
BINS = (0, 2, 5, 10, 15, 20, 30, 45)
MOVING_WHEEL = 1e-9
GRIPPER_CLOSED_PWM = 1900


def tick_features(command):
    wheels = np.abs(np.asarray(command['wheels'], np.float64))
    duration = np.asarray(command['duration_s'], np.float64)
    return dict(moving=bool(wheels.max() > MOVING_WHEEL),
                wheel_max=float(wheels.max()), wheel_mean=float(wheels.mean()),
                duration_mean=float(duration.mean()),
                displacement_proxy=float(wheels.sum()*duration.mean()),
                gripper_closed=bool(float(command['pwm']['5']) > GRIPPER_CLOSED_PWM))


def elapsed_bin(elapsed, bins=BINS):
    for i in range(len(bins)-1):
        if bins[i] <= elapsed < bins[i+1]:
            return f'{bins[i]}-{bins[i+1]}s'
    return f'{bins[-2]}+s'


def aggregate(rows):
    """rows: list of (skill, elapsed, features)."""
    out = {}
    for skill in SKILLS:
        subset = [(elapsed, feature) for name, elapsed, feature in rows if name == skill]
        if not subset:
            continue
        by_bin = {}
        for elapsed, feature in subset:
            key = elapsed_bin(elapsed)
            entry = by_bin.setdefault(key, dict(ticks=0, moving=0, wheel_abs_sum=0., wheel_n=0,
                                                displacement=0., gripper_closed=0))
            entry['ticks'] += 1
            entry['moving'] += int(feature['moving'])
            entry['displacement'] += feature['displacement_proxy']
            entry['gripper_closed'] += int(feature['gripper_closed'])
            for wheel in feature.get('wheel_values', [feature['wheel_mean']]):
                if wheel > MOVING_WHEEL:
                    entry['wheel_abs_sum'] += abs(wheel); entry['wheel_n'] += 1
        for key, entry in by_bin.items():
            entry['moving_fraction'] = entry['moving']/entry['ticks']
            entry['gripper_closed_fraction'] = entry['gripper_closed']/entry['ticks']
            entry['moving_wheel_abs_mean'] = (entry['wheel_abs_sum']/entry['wheel_n']) if entry['wheel_n'] else None
        # halt onset: last tick where any wheel moved, and first long stop gap
        moving_ticks = [elapsed for elapsed, feature in subset if feature['moving']]
        last_move = max(moving_ticks) if moving_ticks else None
        out[skill] = dict(ticks=len(subset), last_move_elapsed_s=last_move,
                          moving_fraction=sum(1 for _, f in subset if f['moving'])/len(subset),
                          by_elapsed=by_bin)
    return out


def teacher_rows(dataset):
    root = Path(dataset)
    manifest = read(root/'manifest.json')
    rows = []
    for episode in manifest['episodes']:
        if episode['split'] != 'train':
            continue
        with np.load(root/episode['path']/'tensors.npz', allow_pickle=False) as archive:
            action = archive['action']
        samples = read(root/episode['path']/'samples.json')
        skill_start = {}
        for index, sample in enumerate(samples):
            skill = sample['skill']
            if skill not in SKILLS:
                continue
            start = skill_start.setdefault(skill, sample['t'])
            elapsed = sample['t']-start
            wheels = np.abs(action[index, 0, :4].astype(np.float64))
            duration = action[index, 0, 4:8].astype(np.float64)*.15  # encoded dt/0.15 -> s
            pwm5 = 1500.0+1000.0*float(action[index, 0, 11])
            rows.append((skill, elapsed, dict(moving=bool(wheels.max() > MOVING_WHEEL),
                                              wheel_max=float(wheels.max()), wheel_mean=float(wheels.mean()),
                                              duration_mean=float(duration.mean()),
                                              displacement_proxy=float(wheels.sum()*duration.mean()),
                                              gripper_closed=bool(pwm5 > GRIPPER_CLOSED_PWM),
                                              wheel_values=wheels.tolist())))
    return aggregate(rows)


def student_rows(run_root):
    """Closed-loop issued commands per world, with seed/kind from result.json."""
    run_root = Path(run_root)
    worlds = {}
    for group in sorted(run_root.glob('group-*')):
        world_count = len(list((group/'evaluation/owner').glob('world-*')))
        if not world_count:
            continue
        lines = [json.loads(line) for line in open(group/'evaluation/actor-actions.jsonl')]
        for world in range(world_count):
            result_path = group/'evaluation/owner'/f'world-{world:03d}'/'result.json'
            result = read(result_path) if result_path.exists() else {}
            key = f'{group.name}-w{world}'
            skill_start = {}
            rows = []
            for line in lines:
                command = line['actions'][world]['command']
                skill = line['skills'][world]
                if skill not in SKILLS:
                    continue
                t = float(command['t'])
                start = skill_start.setdefault(skill, t)
                features = tick_features(command)
                wheels = np.abs(np.asarray(command['wheels'], np.float64))
                features['wheel_values'] = wheels.tolist()
                rows.append((skill, t-start, features))
            worlds[key] = dict(seed=result.get('seed'), kind=result.get('kind'), rows=rows)
    return worlds


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--enabled', action='store_true')
    parser.add_argument('--run-root', type=Path, required=True)
    parser.add_argument('--dataset', type=Path, required=True)
    parser.add_argument('--out', type=Path, required=True)
    args = parser.parse_args()
    if not args.enabled:
        parser.error('closed-loop diagnosis default OFF')
    teacher = teacher_rows(args.dataset)
    worlds = student_rows(args.run_root)
    report = dict(schema='ugrp.act18.closedloop_diag.v1', run_root=str(args.run_root),
                  dataset=str(args.dataset), teacher=teacher, worlds={})
    for name, world in worlds.items():
        report['worlds'][name] = dict(seed=world['seed'], kind=world['kind'],
                                      closed_loop=aggregate(world['rows']))
    args.out.parent.mkdir(parents=True, exist_ok=True)
    args.out.write_text(json.dumps(report, ensure_ascii=False, indent=2)+'\n')
    # compact printable table
    for skill in SKILLS:
        print('==', skill)
        print('bin  teacher_move  model_move  teacher_wheel  model_wheel')
        for key in (f'{BINS[i]}-{BINS[i+1]}s' for i in range(len(BINS)-1)):
            t = teacher.get(skill, {}).get('by_elapsed', {}).get(key, {})
            model_entries = [w['closed_loop'].get(skill, {}).get('by_elapsed', {}).get(key, {})
                             for w in report['worlds'].values()]
            model_entries = [e for e in model_entries if e]
            model_move = (sum(e['moving_fraction'] for e in model_entries)/len(model_entries)
                          if model_entries else None)
            model_wheel = (np.mean([e['moving_wheel_abs_mean'] for e in model_entries
                                    if e.get('moving_wheel_abs_mean') is not None])
                           if any(e.get('moving_wheel_abs_mean') is not None for e in model_entries) else None)
            print(key, round(t.get('moving_fraction', 0), 3) if t else '-',
                  round(model_move, 3) if model_move is not None else '-',
                  round(t.get('moving_wheel_abs_mean') or 0, 3) if t else '-',
                  round(model_wheel, 3) if model_wheel is not None else '-')
    print('== halt onset (last moving tick elapsed s)')
    for name, world in report['worlds'].items():
        print(name, world['seed'], world['kind'],
              {skill: world['closed_loop'].get(skill, {}).get('last_move_elapsed_s') for skill in SKILLS})
    for skill in SKILLS:
        print('teacher', skill, 'last_move', teacher.get(skill, {}).get('last_move_elapsed_s'))


if __name__ == '__main__':
    main()
