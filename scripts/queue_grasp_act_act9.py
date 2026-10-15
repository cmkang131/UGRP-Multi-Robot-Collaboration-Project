"""Prepare a disabled ACT9 recovery gate; never contact or launch a host."""
import argparse
from collections import Counter
from copy import deepcopy
import json
from pathlib import Path

from harness.grasp_act_data import sha256, write_json
from harness.grasp_act_perturb import PERTURB_MODE
from scripts.grasp_act_training_guard import ROOT, source_sha
from scripts.queue_grasp_act_act8 import build_queue as act8_queue
from scripts.run_grasp_act_recovery import dependency_modules

RECORD = 'experiments/2026-10-15-act-train'
SEEDS = list(range(8316900, 8316940))


def seed_inventory(queue_dir, *, proposed_seeds=SEEDS, exclude_tag='act9'):
    # Intentionally restricted to prior queue/plan JSONs. No git grep, branch
    # search, run-tree walk or remote inventory request belongs here.
    paths = set(Path(queue_dir).glob('*.json'))
    paths.update((ROOT/RECORD).glob('*plan*.json'))
    paths = {p for p in paths if exclude_tag not in p.name}
    for p in list(paths):
        def plan_paths(value):
            if isinstance(value, dict):
                for v in value.values(): yield from plan_paths(v)
            elif isinstance(value, list):
                for v in value: yield from plan_paths(v)
            elif isinstance(value, str) and value.endswith('.json') and 'plan' in Path(value).name:
                candidate = Path(value)
                candidate = candidate if candidate.is_absolute() else ROOT/candidate
                if candidate.is_file(): yield candidate
        paths.update(plan_paths(json.loads(p.read_text())))
    def integers(value):
        if type(value) is int: yield value
        elif isinstance(value, dict):
            for v in value.values(): yield from integers(v)
        elif isinstance(value, list):
            for v in value: yield from integers(v)
    entries = []; used = set()
    for p in sorted(paths):
        data = json.loads(p.read_text()); used.update(integers(data))
        entries.append({'path': str(p.resolve()), 'sha256': sha256(p)})
    overlap = sorted(set(proposed_seeds) & used)
    if overlap: raise ValueError(f'{exclude_tag.upper()} seeds already in prior queues/plans: {overlap}')
    return {'schema': 'ugrp.act9.local_seed_inventory.v1', 'files': entries,
        'proposed_seeds': proposed_seeds, 'overlap': overlap, 'local_inventory_checked': True,
        'remote_inventory_verified': False, 'scope': 'prior local queue/plan JSON values only'}


def prepare(dependency_root, queue_dir):
    inventory = seed_inventory(queue_dir)
    counts = Counter(); episodes = []
    with dependency_modules(dependency_root):
        from scripts.make_solo_teacher_plan import episode
        for i, seed in enumerate(SEEDS):
            kind = ('cyan', 'red', 'green', 'yellow')[i % 4]
            e = episode(counts[kind], kind, seed, 'act9_gate'); counts[kind] += 1
            e.update(pr=504, negative_probe=False, gate_eligible=True, training_eligible=False)
            episodes.append(e)
    write_json(ROOT/RECORD/'act9-gate-plan.json', {'episodes': episodes, 'kinds': dict(counts),
        'seed_inventory_verified': False, 'approved': False, 'ready': False,
        'scope': 'static setup; live remote non-use unverified'})
    write_json(ROOT/RECORD/'act9-noise.json', {'schema': 'ugrp.act9.perturb.v1',
        'mode': PERTURB_MODE, 'default': 'off', 'probability_per_eligible_tick': .1,
        'minimum_eligible_ticks': 12, 'burst_ticks': 9, 'max_injections_per_run': 1,
        'wheel_duty': .35, 'pulse_s': .1, 'phases': ['approach', 'align'],
        'held_noise': False, 'arm_noise': False, 'perturbation_targets_excluded': True,
        'scope': 'fixed command-only yaw probe, not optimized DART; physical coverage unmeasured'})
    write_json(ROOT/RECORD/'act9-seed-inventory.json', inventory)


def build_queue(source):
    q = deepcopy(act8_queue(source)); short = source[:8]
    q.update(schema='ugrp.vm3_queue.act9.v1', record=f'{RECORD}/act9.md',
        scope='fresh recovery-coverage gate40; no recording/training execution',
        seed_reuse={'seeds': SEEDS, 'reused': False, 'local_inventory_checked': True,
                    'remote_inventory_verified': False, 'counts_toward_new_gate': True})
    for key, name in [('gate_plan','act9-gate-plan.json'), ('noise','act9-noise.json'),
                      ('seed_inventory','act9-seed-inventory.json')]:
        q[key] = {'path': f'{RECORD}/{name}', 'sha256': sha256(ROOT/RECORD/name)}
    inventory = json.loads((ROOT/RECORD/'act9-seed-inventory.json').read_text())
    if inventory['proposed_seeds'] != SEEDS or inventory['overlap']:
        raise ValueError('invalid ACT9 seed inventory')
    q['prior_queues_untouched'] += [e for e in inventory['files'] if 'vm3-queue' in e['path']]
    gate = q['jobs'][0]
    gate.update(stage='act9-recovery-teacher-gate40', minimum_success=38,
        minimum_recovery_runs=20, recovery_definition='successful run with >=1 probe-attributed lost -> reacquired episode',
        required_run_audit=['recovery_scene_N','perturbation_fraction','recovery_failure_N'],
        training_rgb=False, max_parallel=40)
    for i, (run, seed) in enumerate(zip(gate['runs'], SEEDS)):
        old = run['name']; name = f'act9-gate-{seed}-{short}'
        run.update(name=name, seed=seed, source_sha=source, SOURCE_SHA_file=source)
        command = [s.replace(old, name) for s in run['command']]
        for flag, value in [('--episode',str(i)), ('--plan',q['gate_plan']['path']),
                            ('--noise',q['noise']['path']), ('--recovery-mode',PERTURB_MODE)]:
            command[command.index(flag)+1] = value
        run['command'] = command
    q['required_before_start'] = [
        'Explicit approval and fresh preflight required; all execution/admission flags false. No automatic promotion.',
        'Recheck live seed inventory before activation: local queue/plan overlap is zero; remote non-use is unverified.',
        'Concurrency is min(40 measured n4-highcpu-64 capacity, free admitted slots); review first30 before filling remaining slots. Never assume an idle VM.',
        'Require >=38/40 success AND >=20/40 successful runs each with >=1 lost -> reacquired episode. Recount hash-bound ledgers.',
        'Review first30 raw and >=6 evenly spaced frames (long runs >=1 per60 SIMs); actual loss and recovery must be visible.',
        'Fixed .35-duty 0.9s yaw magnitude is a project probe, independent of GT. Stop and fix on a confirmed defect; do not finish a defective gate.',
        'Record per-run recovery scenes, perturbation fraction and unresolved-loss failures; injection alone is not recovery.',
        'Exclude perturbation labels and split action chunks there; retain actual applied history. No RGB training recording before a reviewed new gate.',
        *[s for s in q['required_before_start'] if s.startswith(('Verify clean','Check actual','All gcloud','Gate and recording','Stop same-defect'))]]
    return q


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('--output-dir', type=Path, required=True)
    p.add_argument('--prepare', action='store_true')
    p.add_argument('--dependency-root', type=Path)
    a = p.parse_args()
    if a.prepare:
        if a.dependency_root is None: p.error('--prepare requires --dependency-root')
        prepare(a.dependency_root, a.output_dir)
        print(json.dumps({'planned_N': len(SEEDS), 'overlap': [], 'execution': False}))
        return
    source = source_sha(); q = build_queue(source)
    inventory = json.loads((ROOT/RECORD/'act9-seed-inventory.json').read_text())
    for item in inventory['files']:
        if sha256(item['path']) != item['sha256']: raise ValueError('prior queue/plan changed')
    path = a.output_dir/f'20261015-act9-{source[:8]}.json'
    with path.open('x') as stream: stream.write(json.dumps(q, indent=2, allow_nan=False)+'\n')
    print(json.dumps({'path': str(path), 'sha256': sha256(path), 'source_sha': source, 'approved': False}))


if __name__ == '__main__': main()
