"""Disabled ACT8 fresh gate only. No execution, remote access or ACT7 writes."""
import argparse
from collections import Counter
from copy import deepcopy
import json
from pathlib import Path

from harness.grasp_act_data import sha256
from harness.grasp_act_dart import PULSE_MODE
from scripts.grasp_act_training_guard import ROOT, source_sha
from scripts.queue_grasp_act_act7 import build_queue as act7_queue
from scripts.run_grasp_act_recovery import dependency_modules

RECORD = 'experiments/2026-10-15-act-train'
SEEDS = list(range(8316800, 8316840))


def prepare_plan(dependency_root):
    counts = Counter(); episodes = []
    with dependency_modules(dependency_root):
        from scripts.make_solo_teacher_plan import episode
        for i, seed in enumerate(SEEDS):
            kind = ('cyan','red','green','yellow')[i%4]
            e = episode(counts[kind], kind, seed, 'act8_gate'); counts[kind] += 1
            e.update(pr=504, negative_probe=False, gate_eligible=True, training_eligible=False)
            episodes.append(e)
    return {'episodes':episodes, 'kinds':dict(counts), 'seed_inventory_verified':False,
            'approved':False, 'ready':False, 'scope':'static setup; live remote non-use unverified'}


def build_queue(source):
    q = deepcopy(act7_queue(source)); short = source[:8]
    q.update(schema='ugrp.vm3_queue.act8.v1', record=f'{RECORD}/act8.md', status='AWAITING_APPROVAL',
        scope='fresh gate40 for opt-in effort/pulse noise only; no recording/training',
        seed_reuse={'seeds':SEEDS, 'reused':False, 'local_inventory_checked':True,
                    'remote_inventory_verified':False, 'counts_toward_new_gate':True})
    for key in ('gate_plan','noise'):
        name = 'act8-gate-plan.json' if key == 'gate_plan' else 'act8-noise.json'
        q[key] = {'path':f'{RECORD}/{name}', 'sha256':sha256(ROOT/RECORD/name)}
    q['evidence'] = {'path':f'{RECORD}/act8-audit.json', 'sha256':sha256(ROOT/RECORD/'act8-audit.json')}
    prior=json.loads((ROOT/RECORD/'act8-prior-inputs.json').read_text())
    q['prior_queues_untouched'].append(prior['prior_act7_queue'])
    gate = q['jobs'][0]; gate['stage'] = 'act8-noise-teacher-gate40'
    # Keep the prior host/budget/census contract and all disabled state flags.
    for i,(run,seed) in enumerate(zip(gate['runs'],SEEDS)):
        old = run['name']; name = f'act8-gate-{seed}-{short}'
        run.update(name=name, seed=seed, source_sha=source, SOURCE_SHA_file=source)
        command = run['command']
        command[:] = [s.replace(old,name).replace('act6-gate-plan.json','act8-gate-plan.json')
                      .replace('act6-noise.json','act8-noise.json').replace('dart_wheels_v1',PULSE_MODE)
                      for s in command]
        command[command.index('--episode')+1] = str(i)
        command[command.index('--plan')+1] = q['gate_plan']['path']
        command[command.index('--noise')+1] = q['noise']['path']
    q['required_before_start'] = [s for s in q['required_before_start'] if not s.startswith('8316600 reuse')]
    q['required_before_start'] += [
        'Fresh proposed 8316800..8316839: compare against live inventory before activation; local non-use is insufficient.',
        'ACT7 28/29 observed, 11 blocked: retain separately; no pooling or inherited success gate.',
        '40 ms pulse efficacy and contact obstruction remain unmeasured. First30 raw review before further submissions; stop on a confirmed defect.',
        'Inspect >=6 own/evaluation frames; command relay activation is not measured wheel rotation.',
        'Measure correction and loss/reacquisition coverage, achieved projected noise/correlation; success alone cannot admit training data.',
        'Verify ACT8 recovery-eval-only contains base/roller/non-target contacts and wheel velocities; 10 Hz snapshots may miss transient contacts. No GT returns to the teacher.']
    return q


def main():
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('--output-dir',type=Path,required=True); a=p.parse_args()
    source=source_sha(); q=build_queue(source)
    for item in q['prior_queues_untouched'][-1:]:
        if sha256(item['path'])!=item['sha256']:raise ValueError('ACT7 queue changed')
    a.output_dir.mkdir(parents=True,exist_ok=True)
    path=a.output_dir/f'20261015-act8-{source[:8]}.json'
    with path.open('x') as stream: stream.write(json.dumps(q,indent=2,allow_nan=False)+'\n')
    print(json.dumps({'path':str(path),'sha256':sha256(path),'source_sha':source,'approved':False}))


if __name__=='__main__':main()
