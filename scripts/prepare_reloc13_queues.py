"""Review-only follow-up queues; an existing rejection table is mandatory."""
import argparse
import copy
import hashlib
import json
from pathlib import Path
from scripts.prepare_reloc12_queues import queues as previous_queues


def queues(sha, source, rejection_table, selfmap, carry):
    table=Path(rejection_table).resolve()
    if not table.is_file():raise ValueError('REJECTION_TABLE_REQUIRED')
    if len(sha)!=40 or any(c not in '0123456789abcdef' for c in sha):raise ValueError('FULL_SOURCE_SHA_REQUIRED')
    # Parent supplies the fixed commands/plan, never its old approvals/admission.
    qs=previous_queues(sha,[],source)
    blockers=[]
    if not selfmap or any(r['termination']['status']!='RECORDED' for r in selfmap):blockers.append('selfmap_incomplete_or_HOST_ERROR')
    if any(r['false_registration_events'] for r in selfmap):blockers.append('false_first_registration')
    if not carry or any(r.get('physical_success') is not True for r in carry):blockers.append('carry_delivery_not_physically_verified')
    if any(r['registered_errors']['bad_N'] for r in selfmap):blockers.append('remaining_execution_errors_legacy_10cm_5deg')
    if any(r.get('pose_error',{}).get('true_yaw_over20_N',0)>0 and r['pose_error'].get('trigger_recall',0)<1 for r in carry):
        blockers.append('carry_budget_recal_missed_true_yaw_over20_ticks')
    ready=not blockers
    for kind,q in zip(('selfmap','carry-texture'),qs):
        q.update(schema='ugrp.reloc13.queue.v1',queue='reloc13-'+kind,
            rejection_table=str(table),rejection_table_sha256=hashlib.sha256(table.read_bytes()).hexdigest(),
            ready=ready,status='PREPARED_NOT_SUBMITTED' if ready else 'BLOCKED',
            admission=dict(ready=ready,reasons=blockers,criterion='No promotion while recorded execution errors or physical carry failures remain; no new fitted accuracy cutoff'),
            source_worktree=str(Path(source).resolve()),automatic_promotion=False,runs_enabled=False,
            physical_evidence_sources=sorted({r['source_sha'] for r in [*selfmap,*carry]}),
            source_pin_note='selfmap physical source; carry runtime modules must match its earlier physical source',
            failed_seed_order=[93571,93585,93583,93584] if kind=='selfmap' else [93266,93315,93261,93262])
        if kind=='selfmap':
            template=q['runs'][0];q['runs']=[]
            for seed in [93571,93585,93583,93584,93600,93601,93602,93603]:
                row=copy.deepcopy(template);row['name']=template['name'].replace('93571',str(seed));row['seed']=seed
                row['command']=[x.replace(template['name'],row['name']) for x in row['command']]
                row['command'][row['command'].index('--seed')+1]=str(seed);q['runs'].append(row)
            q['run_count']=len(q['runs'])
        if kind=='carry-texture':q['plan_path']='experiments/2026-10-15-reloc13/carry-texture-plan.json'
        for r in q['runs']:
            old=r['name'];r['name']=old.replace('reloc12-','reloc13-',1)
            r['command']=[s.replace(old,r['name']).replace('experiments/2026-10-15-reloc12/carry-texture-plan.json','experiments/2026-10-15-reloc13/carry-texture-plan.json') for s in r['command']]
            if kind=='selfmap':r['command']+=['--reloc13-execution-cov-v1','--reloc13-execution-frame-v1','--reloc13-live-r7-v1']
            r.update(ready=ready,approved=False,enabled=False,execute=False,submitted=False)
        order=q['failed_seed_order'];q['runs'].sort(key=lambda r:(order.index(r['seed']) if r['seed'] in order else len(order),r['seed']))
        q['execution_stages']=[dict(name='failed_seed_first',indices=[0],requires='coordinator original review and aggregate capacity admission'),
            dict(name='remaining',indices=list(range(1,len(q['runs']))),requires='first run reviewed; stop on confirmed recurrence')]
    return qs


def main():
    p=argparse.ArgumentParser();p.add_argument('--source-sha',required=True);p.add_argument('--source',type=Path,required=True)
    p.add_argument('--rejection-table',type=Path,required=True);p.add_argument('--selfmap',type=Path,required=True)
    p.add_argument('--carry',type=Path,required=True);p.add_argument('--out',type=Path,required=True);a=p.parse_args()
    data=queues(a.source_sha,a.source,a.rejection_table,json.loads(a.selfmap.read_text())['runs'],json.loads(a.carry.read_text())['runs'])
    a.out.mkdir(parents=True,exist_ok=True)
    for label,q in zip(('selfmap','carry-texture'),data):
        path=a.out/f'20261015-reloc13-{label}-{a.source_sha[:8]}.json'
        with path.open('x') as f:json.dump(q,f,indent=2);f.write('\n')
        print(json.dumps(dict(path=str(path),status=q['status'],runs=q['run_count'])))


if __name__=='__main__':main()
