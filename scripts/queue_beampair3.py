"""Prepare a fresh gate40 after all six beampair3 regressions pass; no submit."""
import argparse
import hashlib
import json
from pathlib import Path
import subprocess

from scripts.queue_beampair2 import build as prior_build, ROOT


def build(source, evidence, table):
    q = prior_build(source, evidence, table)
    report = json.loads(evidence.read_text())
    episodes = json.loads(subprocess.check_output(['git', 'show', source + ':' +
        'experiments/2026-10-15-beampair3/probe-plan.json'], cwd=ROOT))['episodes']
    seeds = [r['seed'] for r in report['runs']]
    if (seeds != [e['seed'] for e in episodes] or seeds[:2] != [8318611, 8318604]
            or len(seeds) != 6 or any(r['adapter_sha'] != source for r in report['runs'])):
        raise ValueError('8318611 and 8318604 must lead the verified short6')
    runs = q['runs']
    runs.sort(key=lambda r: (0 if r['seed'] == 8318611 else 1 if r['seed'] == 8318604 else 2,
                             r['episode']))
    for r in runs:
        old = r['name']
        r['name'] = old.replace('beampair2-', 'beampair3-', 1)
        r['command'] = [x.replace(old, r['name']).replace('peer_rendezvous_v1','peer_rendezvous_v2') for x in r['command']]
    for p in ('harness/json_encoding.py', 'harness/grasp_act_data.py',
              'scripts/run_beampair1_batch.py', 'scripts/analyze_beampair1.py',
              'scripts/review_beampair3.py'):
        q['source_hashes'][p] = hashlib.sha256(subprocess.check_output(
            ['git', 'show', source + ':' + p], cwd=ROOT)).hexdigest()
    q.update(schema='ugrp.beampair3.gate40_queue.v1', owner='beampair3',
        first_two_seeds=[8318611, 8318604], max_parallel=16,
        peer_rendezvous='peer_rendezvous_v2',
        held_object_hidden_v1=True, training_rgb=False,
        cohort_scope='Fresh all40 at beampair3 source; no beampair1/2 or short6 outcomes pooled',
        required_before_start=[
            'Coordinator creates/validates clean pin, full source/dependency SHA and every source hash.',
            'Existing absolute rejection_table and exploration_evidence must match their SHA256 and source.',
            '8318611 then8318604; start all40 from zero. Gate measured N=0.',
            'Host total<=40; this queue<=16. Recheck credit-stop, idle, memory, disk and VM runtime cap.',
            'Remeasure first30 at planned16 load and inspect whole first two trajectories/protocol before filling.',
            'Stop owned siblings on confirmed defects; preserve HOST_ERROR, interruptions and cap_end separately.',
            'Training cameras off, held_object_hidden_v1 on, weld off. No training data/student run admitted.'])
    return q


if __name__ == '__main__':
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('--source', required=True)
    p.add_argument('--evidence', type=Path, required=True)
    p.add_argument('--rejection-table', type=Path, required=True)
    p.add_argument('--output', type=Path, required=True)
    a = p.parse_args()
    q = build(a.source, a.evidence.resolve(), a.rejection_table.resolve())
    with a.output.open('x') as f:
        f.write(json.dumps(q, ensure_ascii=False, indent=2) + '\n')
    print(json.dumps({k: q[k] for k in ('source_sha', 'first_two_seeds', 'ready', 'submitted', 'rejection_table')}))
