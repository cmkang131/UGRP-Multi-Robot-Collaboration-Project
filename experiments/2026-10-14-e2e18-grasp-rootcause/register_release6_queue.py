"""Register a blocked, reviewable queue after verified push. Never execute it."""
import datetime
import hashlib
import json
from pathlib import Path
import subprocess

ROOT=Path(__file__).resolve().parents[2]
BASE=Path(__file__).parent
QUEUE=Path('/Users/changmin/projects/ugrp/outputs/e2e18-admin/vm3-queue')
OLD='e96386d319fee37cbf109867f55a1b9aefac4229'


def digest(path):return hashlib.sha256(path.read_bytes()).hexdigest()


def main():
    sha=subprocess.check_output(['git','rev-parse','HEAD'],cwd=ROOT,text=True).strip()
    branch=subprocess.check_output(['git','branch','--show-current'],cwd=ROOT,text=True).strip()
    assert branch=='claude/grasp-act-probes' and sha!=OLD
    assert not subprocess.check_output(['git','status','--porcelain'],cwd=ROOT,text=True)
    remote=subprocess.check_output(['git','ls-remote','origin','refs/heads/'+branch],cwd=ROOT,text=True).split()[0]
    assert sha==remote
    validation=json.loads((BASE/'release6-offline-summary.json').read_text())
    assert validation['tests']['failures']==validation['tests']['errors']==0
    assert validation['tests']['passed']==26
    oldpath=QUEUE/f'20261015-release-gate-{OLD[:8]}.json'
    source=json.loads(oldpath.read_text())
    def replace(v):
        if isinstance(v,str):
            for a,b in ((OLD,sha),(OLD[:8],sha[:8]),('release5-','release6-')):v=v.replace(a,b)
            return v
        if isinstance(v,list):return [replace(x) for x in v]
        if isinstance(v,dict):return {k:replace(x) for k,x in v.items()}
        return v
    q=replace(source)
    for k in ('blocked_reason','blocked_at','pre_block_backup','superseded_by_sha','superseded_by_queue','superseded_at'):
        q.pop(k,None)
    now=datetime.datetime.now().astimezone().isoformat()
    plans={s:json.loads((BASE/f'release6-{s}-plan.json').read_text()) for s in ('diagnostic','gate')}
    q.update(sha=sha,branch=branch,created_local=now,ready=False,status='awaiting_coordinator_review',
        stage_ready=dict(diagnostic=False,gate=False),gate_promotion_authorized_if_all_conditions_pass=False,
        supersedes_source_sha=OLD,offline_validation=validation,
        remote_source_verification=dict(local_head=sha,remote_head=remote,matches=True),run_count=48,
        profile=plans['diagnostic']['execution_profile'],
        order='74940 reproduction (index 7) first -> first-30-SIM review -> 7 fresh diagnostics -> explicit coordinator approval -> gate 40',
        blocked_reason='User requested ready=false; coordinator must authorize diagnostics. Gate40 requires a separate explicit approval.',
        seed_reservation=json.loads((BASE/'release6-seed-reservation.json').read_text()))
    q['plan_sha256']={str((BASE/f'release6-{s}-plan.json').relative_to(ROOT)):digest(BASE/f'release6-{s}-plan.json') for s in plans}
    q['storage_budget_mib'].update(diagnostic=768,gate=3840,total=4608)
    q['preconditions']=[s.replace('7/7','8/8') for s in q['preconditions']]
    q['preconditions'].extend([
        'Check original per-episode map ID/hash against runtime scene manifest; use that map for NBV visibility/clearance.',
        'NBV: at most 3 extra rounds x 3 own views; existing 180 SIM s cap stays. Map-predicted gain is not measured success.',
        'Verify candidate uncertainty, all exposed own alternatives, used view keys, safe-motion skips, pan settling and body-turn return.',
        'No cross-robot pose, RGB or landmark exchange. The release teacher keeps own NBV planning independent.',
        'All 8 diagnostics must pass, including 7 fresh seeds and exact 74940 reproduction; keep denominators separate.',
    ])
    q['report_needed']+=' NBV expected/motion entropy versus measured new detections, acceptance and actual displacement; verify no acceptance-threshold change.'
    templates={s:next(r for r in source['runs'] if r['stage']==s) for s in plans}
    rows=[]
    repro=f'release6-diagnostic-07-{sha[:8]}'
    diagnostic_names=[f'release6-diagnostic-{i:02d}-{sha[:8]}' for i in range(8)]
    for stage,indices in (('diagnostic',[7,*range(7)]),('gate',list(range(40)))):
        for index in indices:
            row=replace(templates[stage]);row['name']=f'release6-{stage}-{index:02d}-{sha[:8]}'
            row['seed']=plans[stage]['episodes'][index]['seed']
            row['max_parallel']=1 if stage=='diagnostic' and index==7 else (7 if stage=='diagnostic' else 16)
            row['depends_on']=[] if stage=='diagnostic' and index==7 else ([repro] if stage=='diagnostic' else diagnostic_names)
            row['condition']=('Coordinator approval required; reproduce first and review first 30 SIM seconds before fresh seeds.'
                              if stage=='diagnostic' else 'Separate explicit coordinator gate approval required after 8/8 and source/input/video review.')
            command=row['command'];name_index=command.index('--per-run-mb')+3
            assert command[name_index].startswith('release6-')
            command[name_index]=row['name']
            command[command.index('--episode')+1]=str(index)
            command[command.index('--out')+1]='/home/ugrp/ugrp-sim/runs/'+row['name']+'/raw'
            command.extend(['--active-recovery','map_nbv_v1'])
            rows.append(row)
    q['runs']=rows
    out=QUEUE/f'20261015-release-gate-{sha[:8]}.json'
    assert not out.exists()
    # Validate all executable text and hashes before mutating either queue.
    assert len(rows)==q['run_count']==48
    assert [r['seed'] for r in rows if r['stage']=='diagnostic']==[74940,*range(74950,74957)]
    for row in rows:
        c=row['command'];index=int(c[c.index('--episode')+1]);path=ROOT/c[c.index('--plan')+1]
        assert digest(path)==q['plan_sha256'][str(path.relative_to(ROOT))]
        assert row['seed']==json.loads(path.read_text())['episodes'][index]['seed']
        assert c[c.index('--per-run-mb')+3]==row['name']
        assert c[c.index('--active-recovery')+1]=='map_nbv_v1'
        assert c[c.index('--out')+1]=='/home/ugrp/ugrp-sim/runs/'+row['name']+'/raw'
    serialized=json.dumps(q,ensure_ascii=False,separators=(',',':'))+'\n'
    assert len(serialized.encode())<65536
    source.update(ready=False,status='superseded',superseded_by_sha=sha,superseded_by_queue=str(out),
        stage_ready=dict(diagnostic=False,gate=False),superseded_at=now)
    oldpath.write_text(json.dumps(source,ensure_ascii=False,separators=(',',':'))+'\n')
    out.write_text(serialized)
    saved=json.loads(out.read_text());old=json.loads(oldpath.read_text())
    assert saved['sha']==remote and saved['run_count']==len(saved['runs'])==48
    assert saved['ready'] is False and saved['gate_promotion_authorized_if_all_conditions_pass'] is False
    assert old['ready'] is False and old['status']=='superseded'
    assert out.stat().st_size<65536
    assert [r['seed'] for r in rows if r['stage']=='diagnostic']==[74940,*range(74950,74957)]
    for row in rows:
        c=row['command'];index=int(c[c.index('--episode')+1]);path=ROOT/c[c.index('--plan')+1]
        assert digest(path)==saved['plan_sha256'][str(path.relative_to(ROOT))]
        assert row['seed']==json.loads(path.read_text())['episodes'][index]['seed']
        assert c[c.index('--active-recovery')+1]=='map_nbv_v1'
        assert c[c.index('--out')+1]=='/home/ugrp/ugrp-sim/runs/'+row['name']+'/raw'
    receipt=dict(queue=str(out),sha=sha,ready=False,diagnostic=8,gate=40,
        gate_promotion_authorized_if_all_conditions_pass=False,old_status=old['status'],
        sha256=digest(out),bytes=out.stat().st_size,remote_source_verified=True,remote_execution=False)
    receipt_path=ROOT/'outputs/release6-review/queue-receipt.json'
    receipt_path.write_text(json.dumps(receipt,indent=2)+'\n')
    print(json.dumps(receipt))


if __name__=='__main__':main()
