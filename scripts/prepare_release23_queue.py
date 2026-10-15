"""Build reviewable, disabled release23 DEV6 / A40+B40 queues; never launch."""
from __future__ import annotations
import argparse
import base64
from datetime import datetime,timezone
import hashlib
import json
from pathlib import Path
import zlib
from scripts.prepare_release_gate40_queue import compact,FLAGS,GUARD,ENTRY

ROOT=Path(__file__).resolve().parents[1]
RECORD=ROOT/'experiments/2026-10-14-e2e18-grasp-rootcause'


def build(sha,table,*,stage='dev',round_number=1,proof=None):
    table=Path(table).resolve()
    if not table.is_file():raise ValueError('rejection_table missing')
    if len(sha)!=40 or any(c not in '0123456789abcdef' for c in sha):raise ValueError('full source SHA required')
    dev=json.loads((RECORD/'release23-dev6-plan.json').read_text())
    if stage=='gate':
        p=json.loads(Path(proof).read_text())
        if not (p['source_sha']==sha and p['counts']==dict(completed=6,success=6,N=6)
                and p['verified'] and p['failure_seeds_solved']):raise ValueError('DEV6 gate not satisfied')
        plan=json.loads((RECORD/'release18-gate40-plan.json').read_text())
        plan['episodes'][-1]=next(e for e in dev['episodes'] if e['seed']==88639)
        plan['execution_profile']=dev['execution_profile']
        order=sorted(range(40),key=lambda i:([110622,88639].index(plan['episodes'][i]['seed'])
            if plan['episodes'][i]['seed'] in (110622,88639) else i+2))
        items=[(i,c) for c in ('A','B') for i in order]
    else:
        if not 1<=round_number<=3:raise ValueError('at most three DEV rounds')
        plan=dev;items=list(enumerate(dev['candidates']))
    raw=compact(plan);planhash=hashlib.sha256(raw).hexdigest()
    profiles=[dict(id=c,source_sha=sha,execution_profile=dict(dev['execution_profile'],
        release_profile='release18_v1' if c=='A' else 'release19_v1')) for c in ('A','B')]
    runs=[dict(episode=i,candidate=c,seed=plan['episodes'][i]['seed'],source_sha=sha,stage=stage,
        name=f'r23{c.lower()}g-{plan["episodes"][i]["seed"]}-{sha[:8]}' if stage=='gate' else f'r23d{round_number}-{i:02d}-{sha[:8]}',
        **{k:False for k in FLAGS}) for i,c in items]
    q=dict(schema='ugrp.release23.queue.v1',owner='release23',pr=491,host='gcp1',
        source_sha=sha,sha=sha,source_worktree=str(ROOT),branch='claude/grasp-act-probes',
        created_utc=datetime.now(timezone.utc).isoformat(),rejection_table=str(table),
        rejection_table_sha256=hashlib.sha256(table.read_bytes()).hexdigest(),
        stage=stage,round=round_number,run_count=len(runs),runs=runs,candidates=profiles,
        plan_zlib_base64=base64.b64encode(zlib.compress(raw,9)).decode(),plan_sha256=planhash,
        max_combined_concurrency=16 if stage=='gate' else 6,max_gcp1_total_concurrency=40,
        storage_budget_mib=dict(per_run=96,total=96*len(runs)),training_rgb=False,model_calls=0,
        status='PREPARED_NOT_APPROVED',**{k:False for k in FLAGS},
        criteria=dict(required=38,N=40,cap_s=180,held_world_reads=0,invisible_measurements=0,control_top_camera_reads=0),
        pooling='A/B separately from scratch, no pooling with DEV or any previous source, round or cohort.',
        stop_rule='Confirmed control/physical defect: stop owned same-defect jobs and preserve originals; never fill denominator.',
        command_template=['python3','-c',GUARD,'{source}','{sha}','python3','scripts/remote_run.py',
            '--host','gcp1','--detach','--class','dev','--pr','491','--per-run-mb','96','{source}','{name}',
            '--','.venv-sim/bin/python','-c',ENTRY,'{plan}','{plan_sha}','{episode}',
            '/home/ugrp/ugrp-sim/runs/{name}/raw','{profile}'])
    if proof:q['diagnostic_proof']=dict(path=str(Path(proof).resolve()),sha256=hashlib.sha256(Path(proof).read_bytes()).hexdigest())
    verify(q)
    return q


def commands(q,source):
    for r in q['runs']:
        c=next(c for c in q['candidates'] if c['id']==r['candidate'])
        v=dict(source=str(source),sha=r['source_sha'],name=r['name'],plan=q['plan_zlib_base64'],
            plan_sha=q['plan_sha256'],episode=r['episode'],profile=compact(c['execution_profile']).decode())
        yield [a if a in (GUARD,ENTRY) else a.format(**v) for a in q['command_template']]


def verify(q):
    table=Path(q['rejection_table']);assert table.is_absolute() and table.is_file()
    assert hashlib.sha256(table.read_bytes()).hexdigest()==q['rejection_table_sha256']
    raw=zlib.decompress(base64.b64decode(q['plan_zlib_base64']));assert hashlib.sha256(raw).hexdigest()==q['plan_sha256']
    plan=json.loads(raw)
    assert q['run_count']==len(q['runs'])==(80 if q['stage']=='gate' else 6)
    for v in [q,*q['runs']]:assert all(v[k] is False for k in FLAGS)
    assert not q['training_rgb'] and q['max_gcp1_total_concurrency']==40
    for r in q['runs']:
        assert r['source_sha']==q['source_sha'] and len(r['source_sha'])==40
        assert plan['episodes'][r['episode']]['seed']==r['seed']
    if q['stage']=='gate':
        for c in ('A','B'):
            rows=[r for r in q['runs'] if r['candidate']==c]
            assert len(rows)==40 and len({r['seed'] for r in rows})==40
            assert [r['seed'] for r in rows[:2]]==[110622,88639]
        p=Path(q['diagnostic_proof']['path']);assert hashlib.sha256(p.read_bytes()).hexdigest()==q['diagnostic_proof']['sha256']
        proof=json.loads(p.read_text());assert proof['verified'] and proof['failure_seeds_solved']


if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('--sha');p.add_argument('--rejection-table',type=Path);p.add_argument('--out',type=Path)
    p.add_argument('--stage',choices=('dev','gate'),default='dev');p.add_argument('--round',type=int,default=1)
    p.add_argument('--proof',type=Path);p.add_argument('--verify',type=Path)
    a=p.parse_args()
    if a.verify:verify(json.loads(a.verify.read_text()));print('verified disabled queue')
    else:
        q=build(a.sha,a.rejection_table,stage=a.stage,round_number=a.round,proof=a.proof)
        with a.out.open('x') as f:f.write(compact(q).decode()+'\n')
        assert a.out.stat().st_size<65536
        print(a.out)
