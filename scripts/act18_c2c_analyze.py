"""C2c run analysis: per-world done/Pre/G/lift/release/cap_end and acceptance.

Reads only files written by the C2c runs under one new run root. Truth
(owner/evaluation-only.jsonl) is used after the rollout for timing only, never
as a policy input. Default off: requires --enabled.
"""
import argparse
import json
from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).resolve().parent))
from act16w_runtime import sha256


def read(path):
    return json.loads(Path(path).read_text())


def stable_lift_complete(path):
    """First tick at which a 3 s stable lift has completed (evaluation truth)."""
    result = {}
    events = {}
    for line in Path(path).read_text().splitlines():
        event = json.loads(line)
        if 'min_z' not in event:
            continue
        events.setdefault(event['world'], []).append(event)
    for world, rows in events.items():
        previous_t = None
        previous_good = False
        stable = 0.
        for event in rows:
            t = float(event['t'])
            dt = 0. if previous_t is None else t - previous_t
            if not 0 <= dt <= .15 + 1e-8:
                stable, previous_good = 0., False
            good = (event['min_z'] >= .012 and event['tilt_deg'] <= 10.
                    and min(event['finger_forces']) >= .5)
            stable = stable + dt if good and previous_good else 0.
            if good and stable >= 3. - 1e-8:
                result[world] = t
                break
            previous_t, previous_good = t, good
    return result


def done_prob(rows, world, pe):
    values = [row for row in rows if row['world'] == world]
    if not values:
        return None
    best = max(values, key=lambda row: max(row['done_probs']))
    first = next((row for row in values if max(row['done_probs']) >= .65), None)
    return dict(max=round(max(best['done_probs']), 6),
                p95=round(sorted(max(row['done_probs']) for row in values)[int(.95 * (len(values) - 1))], 6),
                first_ge_065_t=None if first is None else first['t'],
                first_ge_065_pe=None if first is None else pe.get(round(float(first['t']), 6)))


def backward_onset(path, lift_t):
    by_world = {}
    if not Path(path).exists():
        return {}
    for line in Path(path).read_text().splitlines():
        row = json.loads(line)
        for world, action in enumerate(row['actions']):
            if lift_t.get(world) is None:
                continue
            t = float(action['command']['t'])
            if t < lift_t[world] - 1e-8:
                continue
            wheels = action['command']['wheels']
            good = all(w < 0 for w in wheels)
            run = by_world.setdefault(world, [0, None])
            run[0] = run[0] + 1 if good else 0
            if run[0] == 5 and run[1] is None:
                run[1] = t
    return {world: value[1] for world, value in by_world.items()}


def group_rows(eval_dir, run, arm, queue, rep, group):
    plans = read(eval_dir / 'initial-plans.json')['episodes']
    summary = read(eval_dir / 'summary.json')
    scores = {row['seed']: row for row in summary.get('student_scores', [])}
    inputs = {}
    skills = {}
    inputs_path = eval_dir / 'actor-inputs.jsonl'
    for line in inputs_path.read_text().splitlines():
        row = json.loads(line)
        obs = row['observation']
        world = int(row['world'])
        inputs.setdefault(world, {})[round(float(obs['t']), 6)] = float(obs['pwm_elapsed_s'])
        skills.setdefault(world, []).append((float(obs['t']), obs['skill']))
    lift_t = stable_lift_complete(eval_dir / 'owner/evaluation-only.jsonl')
    backward = backward_onset(eval_dir / 'actor-actions.jsonl', lift_t)
    prob_rows = []
    prob_path = eval_dir.parent.parent / f'done-prob-group-{group:03d}.jsonl'
    if prob_path.exists():
        prob_rows = [json.loads(line) for line in prob_path.read_text().splitlines()]
    rows = []
    for world, plan in enumerate(plans):
        score = scores[plan['seed']]
        done = score.get('issued_done_times', {}).get('grasp')
        release_done = score.get('issued_done_times', {}).get('release')
        complete = lift_t.get(world)
        grasp = done is not None
        g = bool(grasp and complete is not None and complete <= done + 1e-8)
        pe = inputs.get(world, {})
        post = [value for t, value in pe.items() if complete is not None and t >= complete - 1e-8]
        release_t = next((t for t, skill in skills.get(world, []) if skill == 'release'), None)
        rows.append(dict(run=run, arm=arm, queue=queue, rep=rep, group=group, world=world,
                         seed=plan['seed'], done=done, release_done=release_done,
                         G=g, Pre=bool(grasp and not g),
                         lift=bool(score.get('lift_success')), max_stable_lift_s=score.get('max_stable_lift_s'),
                         release=bool(score.get('release_success')), task=bool(score.get('task_success')),
                         cap_end=bool(score.get('cap_end')), failure_reason=score.get('failure_reason'),
                         lift_complete_t=complete, backward_onset_t=backward.get(world),
                         release_skill_t=release_t,
                         post_lift_max_pe=None if not post else round(max(post), 6),
                         done_prob=done_prob(prob_rows, world, pe) if prob_rows else None))
    return rows


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('--enabled', action='store_true')
    p.add_argument('--run-root', type=Path, required=True)
    p.add_argument('--prereg', type=Path, required=True)
    p.add_argument('--out', type=Path)
    a = p.parse_args()
    if not a.enabled:
        p.error('C2c analysis is default OFF')
    prereg = read(a.prereg)
    order = prereg['cross_order']
    worlds = []
    runs = []
    for name in order:
        arm, queue, rep = name.split('-')
        rep = int(rep.replace('rep', ''))
        folder = a.run_root / name
        stage = 'diag' if queue == 'ho4' else 'train'
        run_worlds = []
        for group in (0, 1):
            evaldir = folder / f'R8-{stage}' / f'group-{group:03d}' / 'evaluation'
            if not (evaldir / 'summary.json').exists():
                raise ValueError(f'missing evaluation summary: {evaldir}')
            run_worlds.extend(group_rows(evaldir, name, arm, queue, rep, group))
        runs.append(dict(run=name, arm=arm, queue=queue, rep=rep, stage=stage,
                         N=len(run_worlds), G=sum(row['G'] for row in run_worlds),
                         Pre=sum(row['Pre'] for row in run_worlds),
                         lift=sum(row['lift'] for row in run_worlds),
                         done=sum(row['done'] is not None for row in run_worlds),
                         release=sum(row['release'] for row in run_worlds),
                         task=sum(row['task'] for row in run_worlds),
                         cap_end=sum(row['cap_end'] for row in run_worlds)))
        worlds.extend(run_worlds)
    aggregate = {}
    for arm in ('B0', 'C2c'):
        for queue in ('ho4', 'train4'):
            rows = [row for row in worlds if row['arm'] == arm and row['queue'] == queue]
            aggregate[f'{arm}-{queue}'] = dict(
                N=len(rows), G=sum(row['G'] for row in rows), Pre=sum(row['Pre'] for row in rows),
                lift=sum(row['lift'] for row in rows), done=sum(row['done'] is not None for row in rows),
                release=sum(row['release'] for row in rows), task=sum(row['task'] for row in rows),
                cap_end=sum(row['cap_end'] for row in rows),
                seeds={str(seed): dict(n=sum(row['seed'] == seed for row in rows),
                                       lift=sum(row['seed'] == seed and row['lift'] for row in rows),
                                       G=sum(row['seed'] == seed and row['G'] for row in rows))
                       for seed in sorted({row['seed'] for row in rows})})
    c2c_pre = sum(row['Pre'] for row in worlds if row['arm'] == 'C2c')
    c2c_ho4 = aggregate['C2c-ho4']['G']
    c2c_train = aggregate['C2c-train4']['G']
    b0_ho4 = aggregate['B0-ho4']['G']
    if c2c_ho4 >= 4 and c2c_train >= 4 and c2c_pre <= 2 and b0_ho4 <= 1:
        verdict = 'PASS'
    elif (c2c_ho4 <= 1 and c2c_train <= 1) or c2c_pre >= 5:
        verdict = 'FAIL'
    else:
        verdict = 'INCONCLUSIVE'
    first = order[0]
    first_stage = 'diag' if first.split('-')[1] == 'ho4' else 'train'
    first_receipt = a.run_root / first / f'R8-{first_stage}' / 'group-000' / 'evaluation' / 'act18-evaluator.json'
    source_sha = read(first_receipt).get('git_sha') if first_receipt.exists() else None
    result = dict(schema='ugrp.act18.c2c_summary.v1', prereg=dict(path=str(a.prereg), sha256=sha256(a.prereg)),
                  run_root=str(a.run_root), source_sha=source_sha,
                  runs=runs, worlds=worlds, aggregate=aggregate,
                  acceptance=dict(verdict=verdict, G_C2c_HO4=c2c_ho4, G_C2c_TRAIN4=c2c_train,
                                  Pre_C2c_total=c2c_pre, G_B0_HO4=b0_ho4,
                                  criteria=prereg['acceptance']),
                  pooling='forbidden; not pooled with finish-r3/20261019c/E0/E1/VAL8/FINAL40/act17/act16w',
                  scope='engineering-only C2c v7 clock closed-loop diagnostic; HO4 not a promotion gate')
    out = a.out or (a.run_root / 'analysis.json')
    out.write_text(json.dumps(result, indent=2) + '\n')
    print(json.dumps(dict(runs=runs, aggregate=aggregate, acceptance=result['acceptance']), indent=2))


if __name__ == '__main__':
    main()
