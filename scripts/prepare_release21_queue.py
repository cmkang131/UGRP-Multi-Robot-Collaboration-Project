"""Prepare a disabled release21 A/B gate manifest; never submit or approve it."""
from __future__ import annotations
import argparse
import base64
from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path
import zlib

from scripts.prepare_release_gate40_queue import build as base_build, compact, FLAGS, GUARD, ENTRY
from sim import release21

ROOT = Path(__file__).resolve().parents[1]
RECORD = 'experiments/2026-10-14-e2e18-grasp-rootcause'


def build(sha, proof_path=RECORD+'/release21-summary.json'):
    q = base_build()
    payload = (ROOT/proof_path).read_bytes()
    proof = json.loads(payload)
    assert proof['source_sha'] == sha
    passed = proof['counts'] == dict(completed=6, success=6, N=6) and proof['verified']
    profile = {**q['candidates'][0]['execution_profile'], 'release20_settle':'release20_settle_v1',
               'release21':release21.MODE, 'review_top':'off'}
    q['candidates'] = [dict(id=c, source_sha=sha, execution_profile=dict(profile,
                       release_profile='release18_v1' if c=='A' else 'release19_v1')) for c in ('A','B')]
    q.update(owner='codex-release21', sha=sha, source_worktree=str(ROOT),
             created_utc=datetime.now(timezone.utc).isoformat(),
             status='PREPARED_NOT_APPROVED' if passed else 'BLOCKED',
             self_check_passed=bool(passed), remote_host_contacted=False,
             diagnostic_evidence=dict(path=proof_path, sha256=hashlib.sha256(payload).hexdigest(), source_sha=sha),
             max_combined_concurrency=6, max_gcp1_total_concurrency=40,
             priority_seeds=[110618,110613], gate_run_count=80, preflight_run_count=3,
             pooling='A/B separately n/40 from scratch. Never pool release20, DEV6, preflight, other source or host.',
             admission_policy='Reserve under gcp1 admission.lock; include full multi-worker reservations; total <=40, this task <=6; do not alter other jobs.',
             preflight_policy='110618 A/B, then 110613 A first, separate from gate. Any self-check failure => BLOCKED. All approval/execution flags remain false.')
    devraw = (ROOT/RECORD/'release21-dev6-plan.json').read_bytes()
    q['runs'] = [dict(stage='preflight', candidate=c, source_sha=sha, episode=i,
                      seed=seed, name=f'r21pre-{i:02d}-{sha[:8]}',
                      plan_zlib_base64=base64.b64encode(zlib.compress(devraw,9)).decode(),
                      plan_sha256=hashlib.sha256(devraw).hexdigest(), **{f:False for f in FLAGS})
                 for i,(seed,c) in enumerate(((110618,'A'),(110618,'B'),(110613,'A')))]
    plan = json.loads(zlib.decompress(base64.b64decode(q['plan_zlib_base64'])))
    order = sorted(range(40), key=lambda i:([110618,110613].index(plan['episodes'][i]['seed'])
                                          if plan['episodes'][i]['seed'] in (110618,110613) else i+2))
    for c in ('A','B'):
        for i in order:
            q['runs'].append(dict(stage='gate', candidate=c, source_sha=sha, episode=i,
                seed=plan['episodes'][i]['seed'],name=f'r21{c.lower()}g-{i:02d}-{sha[:8]}', **{f:False for f in FLAGS}))
    q.update(run_count=len(q['runs']), storage_budget_mib=dict(per_run=96,total=96*len(q['runs'])))
    return q


def commands(q, source, candidate, stage='gate'):
    c = next(c for c in q['candidates'] if c['id']==candidate)
    for r in q['runs']:
        if r['candidate']!=candidate or r['stage']!=stage:
            continue
        values=dict(source=str(source), sha=c['source_sha'], name=r['name'],
                    plan=r.get('plan_zlib_base64',q['plan_zlib_base64']),
                    plan_sha=r.get('plan_sha256',q['plan_sha256']), episode=str(r['episode']),
                    profile=compact(c['execution_profile']).decode())
        yield [v.format(**values) if v not in (GUARD,ENTRY) else v for v in q['command_template']]


def verify(q):
    assert len(q['sha'])==40 and all(v in '0123456789abcdef' for v in q['sha'])
    payload=(ROOT/q['diagnostic_evidence']['path']).read_bytes()
    assert hashlib.sha256(payload).hexdigest()==q['diagnostic_evidence']['sha256']
    proof=json.loads(payload)
    passed=proof['counts']==dict(completed=6,success=6,N=6) and proof['verified']
    assert proof['source_sha']==q['sha'] and q['self_check_passed']==passed
    assert q['status']==('PREPARED_NOT_APPROVED' if passed else 'BLOCKED')
    assert q['run_count']==len(q['runs'])==83 and q['gate_run_count']==80
    assert [(r['seed'],r['candidate']) for r in q['runs'][:3]]==[(110618,'A'),(110618,'B'),(110613,'A')]
    raw=zlib.decompress(base64.b64decode(q['plan_zlib_base64']))
    assert raw==(ROOT/q['plan_path']).read_bytes() and hashlib.sha256(raw).hexdigest()==q['plan_sha256']
    for c in q['candidates']:
        assert c['source_sha']==q['sha']
        p=c['execution_profile']
        assert p['release21']==release21.MODE and p['release20_settle']=='release20_settle_v1' and p['review_top']=='off'
        assert p['release_profile']==('release18_v1' if c['id']=='A' else 'release19_v1')
        gate=[r for r in q['runs'] if r['stage']=='gate' and r['candidate']==c['id']]
        assert len(gate)==40 and {r['seed'] for r in gate}==set(range(110600,110640))
        assert [r['seed'] for r in gate[:2]]==[110618,110613]
        assert len(list(commands(q,'/pinned-source',c['id'])))==40
    for r in [q,*q['runs']]:
        assert all(r[f] is False for f in FLAGS)
    for r in q['runs']:
        plan=json.loads(zlib.decompress(base64.b64decode(r.get('plan_zlib_base64',q['plan_zlib_base64']))))
        assert plan['episodes'][r['episode']]['seed']==r['seed']
    assert not q['stage_ready']['gate'] and not q['coordinator_approval']['approved']
    assert q['authorized_run_count']==0 and not q['gate_promotion_authorized_if_all_conditions_pass']


def main():
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('--sha');p.add_argument('--verify',type=Path);p.add_argument('--commands',type=Path)
    p.add_argument('--source-worktree',type=Path);p.add_argument('--candidate',choices=('A','B'),default='A')
    p.add_argument('--stage',choices=('preflight','gate'),default='gate')
    p.add_argument('--queue-root',type=Path,default=Path('/Users/changmin/projects/ugrp/outputs/e2e18-admin/vm3-queue'))
    a=p.parse_args()
    if a.verify or a.commands:
        q=json.loads((a.verify or a.commands).read_text());verify(q)
        if a.commands:
            if not a.source_worktree:p.error('--commands requires --source-worktree')
            for cmd in commands(q,a.source_worktree,a.candidate,a.stage):print(json.dumps(cmd))
        else:print('verified: A40/B40 unchanged seeds +3 preflights; approval/execution flags false; '+q['status'])
    else:
        if not a.sha:p.error('--sha required')
        q=build(a.sha);verify(q)
        path=a.queue_root/f'20261015-release-gate40-{a.sha[:8]}.json'
        with path.open('x') as f:f.write(compact(q).decode()+'\n')
        assert path.stat().st_size<65536
        print(path)


if __name__=='__main__':main()
