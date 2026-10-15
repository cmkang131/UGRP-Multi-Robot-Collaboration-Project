"""Finite review queues, pinned to the actual tested source and real funnel."""
import argparse
import copy
import hashlib
import json
from pathlib import Path
from statistics import median
from scripts.prepare_reloc12_queues import queues as previous


def queues(sha,source,table,selfmap,carry):
    table=Path(table).resolve()
    if not table.is_file():raise ValueError('REJECTION_TABLE_REQUIRED')
    if len(sha)!=40 or any(c not in '0123456789abcdef' for c in sha):raise ValueError('FULL_SOURCE_SHA_REQUIRED')
    blockers=[]
    if len(selfmap)<4 or any(r['termination']['status']!='RECORDED' for r in selfmap):blockers.append('selfmap_unfinished_or_HOST_ERROR')
    if any(not r['registration_events'] for r in selfmap):blockers.append('missing_global_registration')
    if any(r['false_registration_events'] for r in selfmap):blockers.append('false_registration')
    # Preserve reloc13's promotion rule; do not invent a fitted accuracy cutoff
    # after inspecting this small exploratory cohort.
    if not selfmap or any(r['registered_errors']['bad_N'] for r in selfmap):blockers.append('remaining_10cm_5deg_execution_errors')
    if any(not r['funnel']['control_drive_used'] for r in selfmap):blockers.append('registered_drive_not_observed')
    if not carry or any(r.get('physical_success') is not True for r in carry):blockers.append('physical_destination_release_not_verified')
    if any(r['v7_scene_audit']['heavy_crate_bodies'] for r in carry):blockers.append('heavy_crate_remains_in_v7_cargo')
    if any(r['pose_error']['true_yaw_over20_N'] and r['pose_error']['trigger_recall']<1 for r in carry):blockers.append('carry_budget_undercoverage')
    reports=[*selfmap,*carry]
    if any(r['source_sha']!=sha for r in reports):blockers.append('candidate_source_not_physically_verified')
    if any(r.get('input_audit',{}).get('invisible_measurements')!=0 or r.get('input_audit',{}).get('held_world_reads')!=0 for r in reports):
        blockers.append('input_audit_missing_or_nonzero')
    speeds=[r.get('first30',{}).get('wall_per_sim') for r in reports]
    if not speeds or any(v is None for v in speeds) or median(speeds)>6: # user existing speed stop criterion
        blockers.append('first30_incomplete_or_median_over6')
    ready=not blockers;qs=previous(sha,[],source)
    for label,q in zip(('selfmap','carry-v7'),qs):
        q.update(schema='ugrp.reloc14.queue.v1',queue='reloc14-'+label,source_sha=sha,sha=sha,
            rejection_table=str(table),rejection_table_sha256=hashlib.sha256(table.read_bytes()).hexdigest(),
            ready=ready,status='PREPARED_NOT_SUBMITTED' if ready else 'BLOCKED',
            admission=dict(ready=ready,reasons=blockers,criterion='reloc13 promotion rule retained; global accuracy and actual release required'),
            source_worktree=str(Path(source).resolve()),max_parallel=16,aggregate_max_parallel=40,
            runs_enabled=False,automatic_promotion=False,physical_evidence_sources=sorted({r['source_sha'] for r in [*selfmap,*carry]}))
        if label=='selfmap':
            template=q['runs'][0];q['runs']=[]
            for seed in (93571,93584,93585,93583,93600,93601,93602,93603):
                r=copy.deepcopy(template);old=r['name'];r['name']=f'reloc14-selfmap-texture-{seed}-{sha[:8]}'
                r['command']=[x.replace(old,r['name']) for x in r['command']]
                r['command'][r['command'].index('--seed')+1]=str(seed)
                r['command']+=['--reloc13-execution-cov-v1','--reloc13-execution-frame-v1','--reloc13-live-r7-v1',
                    '--reloc14-continuous-tracking-v1','--reloc14-compute-budget-v1']
                r['seed']=seed;q['runs'].append(r)
        else:
            plan_path='experiments/2026-10-15-reloc14/carry-texture-v7-plan-r2.json'
            plan=json.loads((Path(__file__).resolve().parents[1]/plan_path).read_text())
            template=q['runs'][0];q['runs']=[]
            order=sorted(range(len(plan['episodes'])),key=lambda i:((0 if plan['episodes'][i]['seed']==93266 else 1 if plan['episodes'][i]['seed']==93315 else 2),i))
            for i in order:
                e=plan['episodes'][i];r=copy.deepcopy(template);old=r['name'];r['name']=f'reloc14-carry-v7-{e["seed"]}-{sha[:8]}'
                r['command']=[x.replace(old,r['name']) for x in r['command']]
                r['command'][r['command'].index('--plan')+1]=plan_path
                r['command'][r['command'].index('--episode')+1]=str(i)
                r.update(seed=e['seed'],candidate='continuous_pf_v7');q['runs'].append(r)
            q.update(plan_path=plan_path,scene_version='floor_light_textured_v1/scenarios_v7',pool_with_v6=False)
        for r in q['runs']:r.update(source_sha=sha,ready=ready,approved=False,enabled=False,execute=False,submitted=False)
        q['run_count']=len(q['runs'])
        q['execution_stages']=[dict(name='failed_seed_first',indices=[0],requires='coordinator original review and capacity admission'),
            dict(name='remaining',indices=list(range(1,len(q['runs']))),requires='first original reviewed; stop on confirmed recurrence')]
    return qs


def main():
    p=argparse.ArgumentParser();p.add_argument('--source-sha',required=True);p.add_argument('--source',type=Path,required=True)
    p.add_argument('--rejection-table',type=Path,required=True);p.add_argument('--report',type=Path,required=True);p.add_argument('--out',type=Path,required=True);a=p.parse_args()
    runs=json.loads(a.report.read_text())['runs'];ss=[r for r in runs if 'registered_errors' in r];cs=[r for r in runs if 'pose_error' in r]
    a.out.mkdir(parents=True,exist_ok=True)
    for label,q in zip(('selfmap','carry-v7'),queues(a.source_sha,a.source,a.rejection_table,ss,cs)):
        path=a.out/f'20261015-reloc14-{label}-{a.source_sha[:8]}.json'
        with path.open('x') as f:json.dump(q,f,indent=2);f.write('\n')
        print(json.dumps(dict(path=str(path),status=q['status'],runs=q['run_count'])))


if __name__=='__main__':main()
