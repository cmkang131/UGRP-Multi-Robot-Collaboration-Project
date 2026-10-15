"""Reviewable release24 candidate comparison / disabled A40+B40 gate."""
import argparse
import hashlib
import json
from pathlib import Path
from scripts.prepare_release23_queue import build as previous,commands as previous_commands
from scripts.prepare_release_gate40_queue import FLAGS,compact
from sim import release24

ROOT=Path(__file__).resolve().parents[1]


def build(sha,table,*,stage='dev',round_number=1,proof=None,selected='gated'):
    q=previous(sha,table,stage=stage,round_number=round_number,proof=proof)
    q.update(schema='ugrp.release24.queue.v1',owner='release24',selected_axis_candidate=selected,
        teacher_version='release24',candidate_comparison='fusion vs fusion+consistency reobservation; same six scenes',
        runner_cwd='/Users/changmin/projects/ugrp-wt/gcp-sim-host')
    profiles=q['candidates'];base=q['runs']
    q['candidates']=[];q['runs']=[]
    for mode in (('fusion','gated') if stage=='dev' else (selected,)):
        for c in profiles:
            cp=dict(c,id=mode+'_'+c['id'],execution_profile=dict(c['execution_profile'],
                axis_fusion=release24.FUSION,
                axis_disagree_reobserve=release24.REOBSERVE if mode=='gated' else 'off',
                failure_rgb_recording='own_rgb_last10_10hz_v1'))
            q['candidates'].append(cp)
        for r in base:
            name=(f'r24{r["candidate"].lower()}g-{r["seed"]}-{sha[:8]}' if stage=='gate'
                  else f'r24d{round_number}-{mode[0]}-{r["episode"]:02d}-{sha[:8]}')
            q['runs'].append(dict(r,candidate=mode+'_'+r['candidate'],name=name,axis_candidate=mode))
    q['run_count']=len(q['runs']);q['storage_budget_mib']=dict(per_run=96,total=96*len(q['runs']),
        admission_wave=6,recording_ring='native own JPEG 10s at10Hz, failures/stops only')
    verify(q);return q


def commands(q,source):return previous_commands(q,source)


def verify(q):
    p=Path(q['rejection_table']);assert p.is_absolute() and p.is_file()
    assert hashlib.sha256(p.read_bytes()).hexdigest()==q['rejection_table_sha256']
    assert q['run_count']==len(q['runs'])==(12 if q['stage']=='dev' else 80)
    for r in [q,*q['runs']]:assert all(r[k] is False for k in FLAGS)
    assert q['round']<=3 and q['max_gcp1_total_concurrency']==40
    for c in q['candidates']:
        release24.validate(c['execution_profile'])
        rows=[r for r in q['runs'] if r['candidate']==c['id']]
        assert len(rows)==(3 if q['stage']=='dev' else 40)
    if q['stage']=='dev':
        assert [r['seed'] for r in q['runs'][:6]]==[r['seed'] for r in q['runs'][6:]]


if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('--sha',required=True);p.add_argument('--rejection-table',type=Path,required=True)
    p.add_argument('--out',type=Path,required=True);p.add_argument('--stage',choices=('dev','gate'),default='dev')
    p.add_argument('--round',type=int,default=1);p.add_argument('--proof',type=Path);p.add_argument('--selected',choices=('fusion','gated'),default='gated')
    a=p.parse_args();q=build(a.sha,a.rejection_table,stage=a.stage,round_number=a.round,proof=a.proof,selected=a.selected)
    with a.out.open('x') as f:f.write(compact(q).decode()+'\n')
    print(a.out)
