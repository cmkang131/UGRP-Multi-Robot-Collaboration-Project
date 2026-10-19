"""E0 student-clock/path audit + teacher-row done reanalysis (default OFF).

Pure Python, no torch. Reads existing rollout/evaluation/open-loop logs read-only
and writes every result under a new output directory. Metric definitions and
judgment thresholds come from the pre-registered JSON file
``experiments/2026-10-17-act18/E0_CLOCK_AUDIT_PREREG.json`` and are never
re-tuned after results are seen.

Metrics (design 2026-10-19 act-student-failure-design.md section 3 E0):
  M0.1 post-lift ``pwm_elapsed_s`` maximum, resets per 10 s, per-servo |delta|
  M0.2 ``skill_elapsed_s`` range
  M0.3 per-world base last movement tick and physical lift
  M0.4 open-loop hold-end done positives: h=0 done probability, episode rank,
       hold-phase distribution
  M0.5 open-loop teacher lookback onset +/-3 ticks: R8 projected wheel signs
  M0.6 close-prefix student vs same-seed teacher PWM and first unilateral touch
  R1a  deadband-2 IssuedClock recount of ``pwm_elapsed_s`` on dataset-r1
"""
from __future__ import annotations

import argparse
import gzip
import hashlib
import json
import sys
from pathlib import Path

PERIOD_S = 0.1
PWM_KEYS = ('1', '3', '4', '5', '6')
SERVO_SET = set(PWM_KEYS)
TRAIN4_SEEDS = (88600, 88601, 88602, 88603)
POST_LIFT_PWM3_MAX = 800  # M0.1: issued servo 3 (wrist pitch) lift pose threshold


def frozen_thresholds(prereg):
    if 'thresholds' in prereg and 'h1_fraction' not in prereg:
        return {**prereg, **prereg['thresholds']}
    return prereg


def sha256(path):
    digest = hashlib.sha256()
    with Path(path).open('rb') as handle:
        for block in iter(lambda: handle.read(1 << 20), b''):
            digest.update(block)
    return digest.hexdigest()


def read_json(path):
    return json.loads(Path(path).read_text())


def read_jsonl(path):
    path = Path(path)
    if not path.exists():
        raise FileNotFoundError(str(path))
    rows = []
    with path.open() as handle:
        for number, line in enumerate(handle, 1):
            line = line.strip()
            if not line:
                continue
            try:
                rows.append(json.loads(line))
            except json.JSONDecodeError as error:
                raise ValueError(f'{path}:{number}: invalid JSON: {error}') from error
    return rows


def open_jsonl(path):
    """Read plain or zstd-compressed JSONL without guessing the source format."""
    path = Path(path)
    if path.exists():
        return read_jsonl(path)
    compressed = Path(str(path) + '.zst')
    if compressed.exists():
        import subprocess
        data = subprocess.check_output(['zstd', '-dc', str(compressed)])
        return [json.loads(line) for line in data.decode().splitlines() if line.strip()]
    raise FileNotFoundError(str(path))


def quantiles(values):
    values = sorted(float(value) for value in values)
    if not values:
        return dict(n=0)
    def pick(fraction):
        index = min(len(values) - 1, max(0, int(round(fraction * (len(values) - 1)))))
        return values[index]
    return dict(n=len(values), min=round(values[0], 6), p25=round(pick(.25), 6),
                median=round(pick(.5), 6), p75=round(pick(.75), 6),
                p95=round(pick(.95), 6), max=round(values[-1], 6),
                mean=round(sum(values) / len(values), 6))


def pwm(obs):
    return {key: int(value) for key, value in obs['issued'][-1]['pwm'].items()}


def servo_delta(before, after):
    return {key: abs(after[key] - before[key]) for key in PWM_KEYS}


def audit_world(label, run_dir, world, input_rows, actions, events, prereg):
    observations = [row['observation'] for row in input_rows if row['world'] == world]
    action_rows = [row['actions'][world] for row in actions]
    if len(observations) != len(action_rows):
        raise ValueError(f'{run_dir}: world {world} has {len(observations)} observations but '
                         f'{len(action_rows)} action rows')
    times = [float(obs['t']) for obs in observations]
    if times != sorted(times):
        raise ValueError(f'{run_dir}: world {world} observation times not monotonic')
    issued = [pwm(obs) for obs in observations]
    pwm3 = [value['3'] for value in issued]
    lift_start = next((index for index, value in enumerate(pwm3) if value <= POST_LIFT_PWM3_MAX), None)

    pe = [float(obs['pwm_elapsed_s']) for obs in observations]
    skill = [float(obs['skill_elapsed_s']) for obs in observations]

    clock = dict(eligible=lift_start is not None)
    if lift_start is not None:
        segment = pe[lift_start:]
        resets = [index for index in range(max(1, lift_start + 1), len(pe))
                  if pe[index] < pe[index - 1] - 1e-9]
        deltas = {key: [] for key in PWM_KEYS}
        drivers = {key: 0 for key in PWM_KEYS}
        for index in resets:
            delta = servo_delta(issued[index - 1], issued[index])
            for key, value in delta.items():
                if value:
                    deltas[key].append(value)
            changed = [key for key, value in delta.items() if value]
            if changed:
                drivers[max(changed, key=lambda key: delta[key])] += 1
        duration_s = len(segment) * PERIOD_S
        clock.update(
            start_index=lift_start, start_t=round(times[lift_start], 3),
            start_pwm3=pwm3[lift_start], ticks=len(segment), duration_s=round(duration_s, 3),
            max_pwm_elapsed_s=round(max(segment), 3), final_pwm_elapsed_s=round(segment[-1], 3),
            resets=len(resets), resets_per_10s=round(len(resets) / (duration_s / 10.), 3),
            reset_delta_by_servo={key: quantiles(values) for key, values in deltas.items()},
            reset_driver_counts=drivers,
            reset_ticks=[round(times[index], 3) for index in resets])

    world_actions = [row['command'] for row in action_rows]
    wheels = [[float(value) for value in command['wheels']] for command in world_actions]
    moving = [index for index, row in enumerate(wheels) if any(abs(value) > 0.01 for value in row)]
    last_move = moving[-1] if moving else None
    world_events = [event for event in events if event.get('world') == world]
    lift_ticks = [float(event['t']) for event in world_events
                  if event.get('lift_success') or (event.get('max_stable_lift_s') or 0) > 0]
    forces = [(float(event['t']), [float(value) for value in event['finger_forces']])
              for event in world_events
              if event.get('finger_forces') is not None]
    unilateral = [tick for tick, values in forces
                  if max(values) >= .5 and min(values) <= .05]
    contact = [tick for tick, values in forces if max(values) >= .5]

    commands_pwm = [{key: int(command['pwm'][key]) for key in PWM_KEYS}
                    for command in world_actions]
    close_index = None
    for index in range(1, len(commands_pwm)):
        if abs(commands_pwm[index]['1'] - commands_pwm[index - 1]['1']) >= 100:
            close_index = index
            break

    result = dict(
        label=label, run_dir=str(run_dir), world=world, ticks=len(observations),
        first_t=round(times[0], 3), last_t=round(times[-1], 3),
        m01_clock=clock,
        m02_skill_elapsed=dict(min=round(min(skill), 3), max=round(max(skill), 3),
                               final=round(skill[-1], 3)),
        m03=dict(base_last_move_index=last_move,
                 base_last_move_t=round(times[last_move], 3) if last_move is not None else None,
                 physical_lift=bool(lift_ticks),
                 lift_first_t=round(lift_ticks[0], 3) if lift_ticks else None,
                 lift_ticks=len(lift_ticks)),
        m06=dict(close_index=close_index,
                 close_t=round(times[close_index], 3) if close_index is not None else None,
                 close_pwm1=commands_pwm[close_index]['1'] if close_index is not None else None,
                 unilateral_first_t=round(unilateral[0], 3) if unilateral else None,
                 contact_first_t=round(contact[0], 3) if contact else None,
                 student_pwm_prefix=[]),
    )
    if close_index is not None:
        result['m06']['student_pwm_prefix'] = [
            dict(offset=-offset, t=round(times[close_index - offset], 3),
                 pwm={key: commands_pwm[close_index - offset][key] for key in ('3', '4', '5')})
            for offset in range(10, 0, -1) if close_index - offset >= 0]
    return result


def _episode_rows(rows):
    grouped = {}
    for row in rows:
        grouped.setdefault(int(row['seed']), []).append(row)
    for value in grouped.values():
        value.sort(key=lambda row: float(row['t']))
    return grouped


def audit_open_frames(path, prereg):
    prereg = frozen_thresholds(prereg)
    rows = []
    with gzip.open(path, 'rt') as handle:
        for line in handle:
            if line.strip():
                rows.append(json.loads(line))
    grouped = _episode_rows(rows)
    seeds = sorted(grouped)
    missing = [seed for seed in TRAIN4_SEEDS if seed not in grouped]
    if missing:
        raise ValueError(f'{path}: TRAIN4 seeds missing from open-loop frames: {missing}')
    metrics = []
    for seed in TRAIN4_SEEDS:
        episode = grouped[seed]
        grasp = [row for row in episode if row['skill'] == 'grasp']
        if not grasp:
            raise ValueError(f'{path}: seed {seed} has no grasp rows')
        positives = [row for row in grasp if float(row['teacher'][13]) >= .5]
        if len(positives) != 1:
            raise ValueError(f'{path}: seed {seed} has {len(positives)} hold-end done positives; '
                             'pre-registered analysis expects exactly one')
        positive = positives[0]
        probability = float(positive['prediction'][13])
        rank = 1 + sum(1 for row in grasp if float(row['prediction'][13]) > probability)
        hold = [row for row in episode if row.get('teacher_phase') == 'hold']
        hold_probabilities = [float(row['prediction'][13]) for row in hold]
        onset = next((index for index, row in enumerate(episode)
                      if row.get('teacher_phase') == 'lookback' and row['skill'] == 'grasp'), None)
        window = []
        if onset is not None:
            for index in range(max(0, onset - 3), min(len(episode), onset + 4)):
                row = episode[index]
                projected = [float(value) for value in row['projected'][:4]]
                window.append(dict(offset=index - onset, t=round(float(row['t']), 3),
                                   wheels=[round(value, 4) for value in projected],
                                   reverse=all(value <= prereg['m05_wheel_max_negative']
                                               for value in projected)))
        metrics.append(dict(
            seed=seed, rows=len(episode), grasp_rows=len(grasp), hold_rows=len(hold),
            positive_t=round(float(positive['t']), 3),
            positive_teacher_phase=positive.get('teacher_phase'),
            done_probability=round(probability, 6),
            rank=rank, rank_fraction=round(rank / len(grasp), 6),
            hold_done_probabilities=dict(min=round(min(hold_probabilities), 6) if hold_probabilities else None,
                                         median=round(sorted(hold_probabilities)[len(hold_probabilities) // 2], 6)
                                         if hold_probabilities else None,
                                         max=round(max(hold_probabilities), 6) if hold_probabilities else None,
                                         n=len(hold_probabilities)),
            lookback_onset_index=onset,
            lookback_onset_t=round(float(episode[onset]['t']), 3) if onset is not None else None,
            m05_window=window,
            m05_reverse=any(item['reverse'] for item in window),
            m05_onset_reverse=(window and next(item for item in window if item['offset'] == 0)['reverse'])
            if onset is not None else None))
    return dict(path=str(path), sha256=sha256(path), rows=len(rows), seeds=seeds, episodes=metrics)


def _dataset_clock(rows, deadband_reset):
    """Recount pwm_elapsed_s from per-tick issued PWM columns.

    ``deadband_reset`` is the absolute |delta| at which the clock resets (1 for
    the current exact-equality v6 clock, 3 for the v7 deadband-2 clock).  The
    baseline is the PWM at the last reset, so sub-threshold drift accumulates
    until a real command change resets the clock.
    """
    states = {}
    for row in rows:
        states.setdefault(int(row['seed']), []).append(row)
    output = {}
    for seed, episode in states.items():
        episode.sort(key=lambda row: float(row['t']))
        previous_t = None
        base = None
        elapsed = 0.
        values = []
        for row in episode:
            current = {key: int(row['issued_pwm'][key]) for key in PWM_KEYS}
            if base is None:
                elapsed = 0.
                base = dict(current)
            else:
                delta = max(abs(current[key] - base[key]) for key in PWM_KEYS)
                if delta >= deadband_reset:
                    elapsed = 0.
                    base = dict(current)
                else:
                    elapsed = elapsed + (float(row['t']) - previous_t)
            values.append((row, elapsed))
            previous_t = float(row['t'])
        output[seed] = values
    return output


def audit_dataset_columns(path, prereg):
    prereg = frozen_thresholds(prereg)
    rows = read_jsonl(path)
    train = [row for row in rows if row.get('split') == 'train']
    if not train:
        raise ValueError(f'{path}: no train rows')
    reset = prereg['r1a_deadband'] + 1
    exact = _dataset_clock(train, 1)
    deadband = _dataset_clock(train, reset)
    mismatches = total = changed = 0
    changed_rows = []
    for seed, values in exact.items():
        for row, value in values:
            if abs(value - float(row['pwm_elapsed_s'])) > .051:
                mismatches += 1
    for seed, values in deadband.items():
        for row, value in values:
            old = float(row['pwm_elapsed_s'])
            total += 1
            if abs(value - old) > .051:
                changed += 1
                if len(changed_rows) < 50:
                    changed_rows.append(dict(seed=seed, t=round(float(row['t']), 3),
                                             old=round(old, 3), new=round(value, 3),
                                             skill=row.get('skill'),
                                             teacher_phase=row.get('teacher_phase')))
    ratio = changed / total if total else None
    return dict(path=str(path), sha256=sha256(path), rows=len(rows), train_rows=total,
                episodes=len(deadband), deadband=prereg['r1a_deadband'], reset_at=reset,
                exact_recount_mismatches=mismatches,
                exact_recount_valid=mismatches == 0,
                changed_rows=changed, changed_ratio=round(ratio, 6) if ratio is not None else None,
                threshold=prereg['r1a_threshold'],
                changed_examples=changed_rows)


def audit_teacher_close(path, open_frames, runs):
    """M0.6 teacher side: same-seed close prefix from dataset action columns."""
    rows = read_jsonl(path)
    grouped = _episode_rows([row for row in rows if row.get('split') == 'train'])
    teacher = {}
    for seed in TRAIN4_SEEDS:
        episode = grouped.get(seed)
        if not episode:
            teacher[seed] = dict(available=False, reason='seed missing from dataset columns')
            continue
        close = None
        for index in range(1, len(episode)):
            before = int(episode[index - 1]['teacher_pwm'][str(1)])
            after = int(episode[index]['teacher_pwm'][str(1)])
            if abs(after - before) >= 100:
                close = index
                break
        prefix = []
        if close is not None:
            prefix = [dict(offset=-offset, t=round(float(episode[close - offset]['t']), 3),
                           pwm={key: int(episode[close - offset]['teacher_pwm'][key])
                                for key in ('3', '4', '5')})
                      for offset in range(10, 0, -1) if close - offset >= 0]
        teacher[seed] = dict(available=close is not None, close_index=close,
                             close_t=round(float(episode[close]['t']), 3) if close is not None else None,
                             pwm_prefix=prefix)
    comparisons = []
    for world in runs['worlds']:
        seed = int(world['seed'])
        info = teacher.get(seed)
        if not info or not info['available'] or world['m06']['close_index'] is None:
            comparisons.append(dict(label=world['label'], seed=seed, world=world['world'],
                                    available=False))
            continue
        student = {item['offset']: item['pwm'] for item in world['m06']['student_pwm_prefix']}
        demo = {item['offset']: item['pwm'] for item in info['pwm_prefix']}
        offsets = sorted(set(student) & set(demo))
        per_servo = {key: [abs(student[offset][key] - demo[offset][key]) for offset in offsets]
                     for key in ('3', '4', '5')}
        comparisons.append(dict(
            label=world['label'], seed=seed, world=world['world'], available=True,
            offsets=offsets,
            per_servo={key: quantiles(values) for key, values in per_servo.items()},
            max_abs_delta={key: (max(values) if values else None) for key, values in per_servo.items()},
            student_close_t=world['m06']['close_t'], teacher_close_t=info['close_t'],
            unilateral_first_t=world['m06']['unilateral_first_t'],
            contact_first_t=world['m06']['contact_first_t']))
    return dict(path=str(path), sha256=sha256(path), teacher=teacher, comparisons=comparisons)


def judge(prereg, worlds, done, dataset):
    prereg = frozen_thresholds(prereg)
    eligible = [world for world in worlds if world['m01_clock']['eligible']]
    low = [world for world in eligible
           if world['m01_clock']['max_pwm_elapsed_s'] < prereg['h1_max_pe_support_s']]
    high = [world for world in eligible
            if world['m01_clock']['max_pwm_elapsed_s'] >= prereg['h1_max_pe_refute_s']]
    fraction = prereg['h1_fraction']
    h1 = dict(
        eligible_world_runs=len(eligible),
        max_pe_lt_support=dict(count=len(low), fraction=round(len(low) / len(eligible), 4) if eligible else None),
        max_pe_ge_refute=dict(count=len(high), fraction=round(len(high) / len(eligible), 4) if eligible else None),
        support_rule=f'fraction(max pwm_elapsed_s < {prereg["h1_max_pe_support_s"]} s) >= {fraction}',
        refute_rule=f'fraction(max pwm_elapsed_s >= {prereg["h1_max_pe_refute_s"]} s) >= {fraction}',
        verdict=('support' if eligible and len(low) / len(eligible) >= fraction else
                 'refute' if eligible and len(high) / len(eligible) >= fraction else 'ambiguous'))
    normal = [episode for episode in done['episodes']
              if episode['done_probability'] >= prereg['done_p_normal']
              or episode['rank_fraction'] <= prereg['done_top_fraction']]
    c2 = [episode for episode in done['episodes'] if episode['done_probability'] < prereg['done_c2_p']]
    done_verdict = ('normal' if len(normal) >= prereg['done_normal_min'] else
                    'c2_support' if len(c2) == len(done['episodes']) == 4 else 'inconclusive')
    reverse = [episode for episode in done['episodes'] if episode['m05_reverse']]
    m05_available = [episode for episode in done['episodes'] if episode['lookback_onset_index'] is not None]
    m05 = dict(available_world_runs=len(m05_available), reverse_count=len(reverse),
               reverse_fraction=round(len(reverse) / len(m05_available), 4) if m05_available else None,
               rule=f'>= {prereg["m05_min"]} of 4 world-runs reverse within onset +/-3 ticks',
               verdict=('transition_possible' if len(reverse) >= prereg['m05_min'] else 'not_possible'))
    r1a_ratio = dataset['changed_ratio']
    r1a = dict(changed_ratio=r1a_ratio, threshold=prereg['r1a_threshold'],
               reconstruction_valid=dataset['exact_recount_valid'],
               verdict=('blocked' if not dataset['exact_recount_valid'] else
                        'pass' if r1a_ratio is not None and r1a_ratio <= prereg['r1a_threshold']
                        else 'fail'),
               rule='changed rows / train rows <= threshold -> R1a without retraining')
    return dict(H1=h1, done_head=done_verdict, done_head_counts=dict(normal=len(normal), c2=len(c2)),
                M0_5=m05, R1a=r1a)


def parse_run(spec):
    if '=' not in spec:
        raise ValueError(f'--run expects LABEL=DIR, got {spec!r}')
    label, value = spec.split('=', 1)
    path = Path(value)
    if not path.is_dir():
        raise FileNotFoundError(str(path))
    return label, path


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--enabled', action='store_true')
    parser.add_argument('--prereg', type=Path, required=True)
    parser.add_argument('--run', action='append', default=[],
                        help='LABEL=EVALUATION_DIR (actor-inputs/actor-actions/owner)')
    parser.add_argument('--open-frames', type=Path, required=True)
    parser.add_argument('--dataset-columns', type=Path, required=True)
    parser.add_argument('--done-logs', type=Path, nargs='*', default=[])
    parser.add_argument('--out', type=Path, required=True)
    args = parser.parse_args(argv)
    if not args.enabled:
        parser.error('E0 clock audit is default OFF; pass --enabled')
    if args.out.exists():
        parser.error(f'output already exists: {args.out}')
    prereg = read_json(args.prereg)
    if prereg.get('schema') != 'ugrp.act18.e0_clock_audit.prereg.v1':
        raise ValueError('unexpected E0 prereg schema')
    # Thresholds live in one frozen block; expose them flat to the metric code.
    if not isinstance(prereg.get('thresholds'), dict):
        raise ValueError('prereg thresholds block missing')
    prereg.update(prereg['thresholds'])
    required = ('h1_max_pe_support_s', 'h1_max_pe_refute_s', 'h1_fraction',
                'done_p_normal', 'done_top_fraction', 'done_c2_p', 'done_normal_min',
                'm05_wheel_max_negative', 'm05_min', 'r1a_threshold', 'r1a_deadband')
    missing = [key for key in required if key not in prereg]
    if missing:
        raise ValueError(f'prereg missing frozen thresholds: {missing}')

    inputs = [args.open_frames, args.dataset_columns, args.prereg]
    runs = []
    for spec in args.run:
        label, path = parse_run(spec)
        input_rows = read_jsonl(path / 'actor-inputs.jsonl')
        actions = read_jsonl(path / 'actor-actions.jsonl')
        events = open_jsonl(path / 'owner' / 'evaluation-only.jsonl')
        worlds = sorted({row['world'] for row in input_rows})
        if worlds != list(range(len(actions[0]['actions']))):
            raise ValueError(f'{path}: world sets differ between inputs and actions')
        per_world = {world: audit_world(label, path, world, input_rows, actions, events, prereg)
                     for world in worlds}
        runs.append(dict(label=label, path=str(path), worlds=list(per_world.values())))
        for name in ('actor-inputs.jsonl', 'actor-actions.jsonl', 'owner/evaluation-only.jsonl'):
            inputs.append(path / name)

    all_seeds = []
    for run in runs:
        seeds = []
        for world in run['worlds']:
            seed = _seed_for_run(run, world)
            world['seed'] = seed
            seeds.append(seed)
        all_seeds.extend(seeds)
        inputs.append(Path(run['path']) / 'initial-plans.json')
        run.pop('plans', None)
    if set(all_seeds) != set(TRAIN4_SEEDS):
        raise ValueError(f'run set must cover TRAIN4 seeds, got {all_seeds}')
    if len(all_seeds) not in (4, 8):
        raise ValueError(f'expected 4 or 8 TRAIN4 world-runs (original and/or repro), got {len(all_seeds)}')
    for run in runs:
        seeds = [world['seed'] for world in run['worlds']]
        if len(set(seeds)) != len(seeds):
            raise ValueError(f'{run["path"]}: duplicate seed inside one evaluation')

    done = audit_open_frames(args.open_frames, prereg)
    dataset = audit_dataset_columns(args.dataset_columns, prereg)
    close = audit_teacher_close(args.dataset_columns, done, dict(worlds=[
        world for run in runs for world in run['worlds']]))
    done_logs = []
    for path in args.done_logs:
        rows = read_jsonl(path)
        done_logs.append(dict(path=str(path), sha256=sha256(path), rows=len(rows),
                              max_raw=max((float(row['done_probs'][0]) for row in rows), default=None),
                              worlds=sorted({row.get('world') for row in rows})))
        inputs.append(path)
    worlds = [world for run in runs for world in run['worlds']]
    verdict = judge(prereg, worlds, done, dataset)

    args.out.mkdir(parents=True, exist_ok=False)
    manifest = dict(schema='ugrp.act18.e0_clock_audit.manifest.v1',
                    code='scripts/act18_clock_audit.py',
                    code_sha256=sha256(Path(__file__).resolve()),
                    prereg=dict(path=str(args.prereg), sha256=sha256(args.prereg)),
                    inputs=[dict(path=str(path), sha256=sha256(path)) for path in inputs],
                    argv=sys.argv if argv is None else ['act18_clock_audit.py', *argv],
                    outputs=dict(summary='summary.json'))
    summary = dict(schema='ugrp.act18.e0_clock_audit.v1',
                   labels=dict(scope='engineering-only / sim / TRAIN4-VAL8-FINAL40 gate non-target / no pooling',
                               computation='CPU only, zero GPU, zero new model inference',
                               causal='counterfactual recount of frozen logs; no replay'),
                   prereg=dict(path=str(args.prereg), sha256=sha256(args.prereg)),
                   runs=runs, m04_done=done, m05_lookback=done,
                   m06_close=close, r1a_dataset=dataset, done_probe_logs=done_logs,
                   verdict=verdict, warnings=[])
    if dataset['changed_ratio'] is None:
        summary['warnings'].append('R1a dataset recount produced zero train rows')
    (args.out / 'summary.json').write_text(json.dumps(summary, ensure_ascii=False, indent=2) + '\n')
    (args.out / 'manifest.json').write_text(json.dumps(manifest, ensure_ascii=False, indent=2) + '\n')
    print(json.dumps(dict(out=str(args.out), verdict=verdict,
                          worlds=[dict(label=world['label'], world=world['world'], seed=world['seed'],
                                       max_pe=world['m01_clock'].get('max_pwm_elapsed_s'),
                                       eligible=world['m01_clock']['eligible'],
                                       lift=world['m03']['physical_lift']) for world in worlds],
                          done=[dict(seed=episode['seed'], p=episode['done_probability'],
                                     rank=episode['rank'], rank_fraction=episode['rank_fraction'])
                                for episode in done['episodes']]), indent=1))
    return summary


def _seed_for_run(run, world):
    """Read the evaluation initial plans for the world seed (read-only)."""
    path = Path(run['path']) / 'initial-plans.json'
    if not path.exists():
        raise FileNotFoundError(f'{path}: seed provenance required for {run["path"]}')
    plans = read_json(path)['episodes']
    return int(plans[world['world']]['seed'])


if __name__ == '__main__':
    main()
