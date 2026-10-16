"""Prepare a source-bound disabled ACT10 gate. No host access or execution."""
import argparse
from collections import Counter
from copy import deepcopy
import json
from pathlib import Path

from harness.grasp_act_data import sha256, write_json
from harness.grasp_act_search import SEARCH_MODE, SEARCH_LIMIT_S
from harness.grasp_act_perturb import LOSS_ATTRIBUTION_S
from scripts.grasp_act_training_guard import ROOT, source_sha
from scripts.queue_grasp_act_act9 import RECORD, build_queue as act9_queue, seed_inventory
from scripts.run_grasp_act_recovery import dependency_modules

SEEDS = list(range(8317000, 8317040))


def prepare(dependency_root, queue_dir):
    inventory = seed_inventory(queue_dir, proposed_seeds=SEEDS, exclude_tag='act10')
    counts = Counter(); episodes = []
    with dependency_modules(dependency_root):
        from scripts.make_solo_teacher_plan import episode
        for i, seed in enumerate(SEEDS):
            kind = ('cyan', 'red', 'green', 'yellow')[i % 4]
            e = episode(counts[kind], kind, seed, 'act10_gate'); counts[kind] += 1
            e.update(pr=504, negative_probe=False, gate_eligible=True, training_eligible=False)
            episodes.append(e)
    write_json(ROOT/RECORD/'act10-gate-plan.json', {'episodes':episodes, 'kinds':dict(counts),
        'seed_inventory_verified':False, 'approved':False, 'ready':False,
        'scope':'static setup only; remote seed non-use unverified'})
    noise = json.loads((ROOT/RECORD/'act9-noise.json').read_text())
    noise.update(mode=SEARCH_MODE, scope='ACT9 fixed yaw probe + opt-in command-only active teacher search; new gate required')
    write_json(ROOT/RECORD/'act10-noise.json', noise)
    write_json(ROOT/RECORD/'act10-seed-inventory.json', inventory)


def build_queue(source):
    q = deepcopy(act9_queue(source)); short = source[:8]
    q.update(schema='ugrp.vm3_queue.act10.v1', record=f'{RECORD}/act10.md',
        scope='fresh ACT10 active recovery teacher gate40 only; no recording/training',
        seed_reuse={'seeds':SEEDS, 'reused':False, 'local_inventory_checked':True,
                    'remote_inventory_verified':False, 'counts_toward_new_gate':True})
    for key, name in [('gate_plan','act10-gate-plan.json'), ('noise','act10-noise.json'),
                      ('seed_inventory','act10-seed-inventory.json'), ('evidence','act10-offline.json')]:
        q[key] = {'path':f'{RECORD}/{name}', 'sha256':sha256(ROOT/RECORD/name)}
    inventory = json.loads((ROOT/RECORD/'act10-seed-inventory.json').read_text())
    if inventory['proposed_seeds'] != SEEDS or inventory['overlap']:
        raise ValueError('invalid ACT10 seed inventory')
    prior = {p['path']:p for p in q['prior_queues_untouched']}
    prior.update({p['path']:p for p in inventory['files'] if 'vm3-queue' in p['path']})
    q['prior_queues_untouched'] = list(prior.values())
    gate = q['jobs'][0]
    gate.update(stage='act10-active-recovery-teacher-gate40', search_limit_s=SEARCH_LIMIT_S,
        loss_attribution_after_last_probe_tick_s=LOSS_ATTRIBUTION_S,
        recovery_definition='successful run with loss during probe or <=1s after last probe tick, then own-camera reacquisition',
        first30_review_before_fill=True)
    for i, (run, seed) in enumerate(zip(gate['runs'], SEEDS)):
        old = run['name']; name = f'act10-gate-{seed}-{short}'
        run.update(name=name, seed=seed)
        command = [s.replace(old, name) for s in run['command']]
        for flag, value in [('--episode',str(i)), ('--plan',q['gate_plan']['path']),
                            ('--noise',q['noise']['path']), ('--recovery-mode',SEARCH_MODE)]:
            command[command.index(flag)+1] = value
        run['command'] = command
    q['required_before_start'] += [
        'Restart all 40 on this source; never pool ACT8/ACT9 successes. All execution/admission flags remain false.',
        'Require held_world_reads=0 and invisible_measurements=0; inspect expected bearing, range-matched gaze, pan and body scan in first30 raw.',
        'Search yaw is command-estimated only, capped at 360deg and 24s; exhaustion is failure, never recovery success.',
        'Gate review must include queue path+SHA256; fresh_seeds and all 40 result seeds must equal this queue.']
    return q


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('--output-dir', type=Path, required=True)
    p.add_argument('--prepare', action='store_true')
    p.add_argument('--dependency-root', type=Path)
    a = p.parse_args()
    if a.prepare:
        if a.dependency_root is None:p.error('--prepare requires --dependency-root')
        prepare(a.dependency_root, a.output_dir)
        print(json.dumps({'planned_N':len(SEEDS), 'overlap':[], 'execution':False}))
        return
    source = source_sha(); q = build_queue(source)
    inventory = json.loads((ROOT/RECORD/'act10-seed-inventory.json').read_text())
    for item in inventory['files']:
        if sha256(item['path']) != item['sha256']:
            raise ValueError(f'prior queue/plan changed: {item["path"]}')
    a.output_dir.mkdir(parents=True, exist_ok=True)
    path = a.output_dir/f'20261015-act10-{source[:8]}.json'
    with path.open('x') as stream:stream.write(json.dumps(q, indent=2, allow_nan=False)+'\n')
    print(json.dumps({'path':str(path), 'sha256':sha256(path), 'source_sha':source, 'approved':False}))


if __name__ == '__main__':main()
