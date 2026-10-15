"""Prepare unapproved beampair4 gate40 only after six exact-source successes."""
import argparse
import hashlib
import json
from pathlib import Path
import subprocess

from scripts.queue_beampair2 import build as previous, ROOT


def build(source, evidence, table):
    wanted=[8318620,8318626,8318600,8318604,8318611,8318631]
    frozen=json.loads(subprocess.check_output(['git','show',source+':experiments/2026-10-15-beampair1/gate-plan.json'],cwd=ROOT))
    bursts=[next(e['burst_ticks'] for e in frozen['episodes'] if e['seed']==s) for s in wanted]
    q=previous(source,evidence,table,expected_bursts=bursts)
    report=json.loads(evidence.read_text())
    if [r['seed'] for r in report['runs']] != wanted:
        raise ValueError('exact failed-seed-first short6 required')
    if any(r['adapter_sha']!=source for r in report['runs']):
        raise ValueError('all regressions must use the full source SHA')
    for r in q['runs']:
        old=r['name'];r['name']=old.replace('beampair2-','beampair4-',1)
        r['command']=[v.replace(old,r['name']).replace('peer_rendezvous_v1','peer_rendezvous_v2') for v in r['command']]
        idx=r['command'].index('--per-run-mb')+1;r['command'][idx]='256'
        r['command'] += ['--approach-repair','beampair_approach_v2','--failure-tail']
    q['runs'].sort(key=lambda r:(0 if r['seed']==8318620 else 1 if r['seed']==8318626 else 2,r['episode']))
    for p in ('harness/beampair_approach.py','harness/failure_rgb_tail.py','scripts/review_beampair3.py',
              'scripts/queue_beampair4.py','scripts/analyze_beampair4.py'):
        q['source_hashes'][p]=hashlib.sha256(subprocess.check_output(['git','show',source+':'+p],cwd=ROOT)).hexdigest()
    q.update(schema='ugrp.beampair4.gate40_queue.v1',owner='beampair4',
        first_two_seeds=wanted[:2],max_parallel=16,approach_repair='beampair_approach_v2',
        peer_rendezvous='peer_rendezvous_v2',failure_tail_recording=True,
        held_object_hidden_v1=True,training_rgb=False,
        cohort_scope='Fresh all40 beampair4; no beampair1/2/3 or short6 outcomes pooled',
        required_before_start=[
            'Coordinator verifies clean pin, source/dependency SHA and every source hash.',
            'Absolute rejection_table/evidence files must exist and match SHA256; ready/approved/submitted stay false here.',
            '8318620 then8318626; remeasure40 from zero. Gate measured N=0.',
            'This queue<=16, global host<=40. Recheck credit stop, memory, disk, idle and8h VM cap.',
            'At planned16 load inspect first30 timing/commands/own RGB/protocol before filling.',
            'Stop same-defect owned siblings immediately; preserve failures, HOST_ERROR, interruptions and cap_end.',
            'Training RGB off; held hidden on; weld off; recording-only10Hz failure tail on.'])
    return q


if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('--source',required=True);p.add_argument('--evidence',type=Path,required=True)
    p.add_argument('--rejection-table',type=Path,required=True);p.add_argument('--output',type=Path,required=True)
    a=p.parse_args();q=build(a.source,a.evidence.resolve(),a.rejection_table.resolve())
    with a.output.open('x') as f:f.write(json.dumps(q,ensure_ascii=False,indent=2)+'\n')
    print(json.dumps({k:q[k] for k in ('source_sha','first_two_seeds','ready','approved','submitted','rejection_table')}))
