"""Register authorized diagnostics after verified push; never submit remotely."""
import datetime
import hashlib
import json
from pathlib import Path
import subprocess

ROOT=Path(__file__).resolve().parents[2]
BASE=Path(__file__).parent
QUEUE=Path('/Users/changmin/projects/ugrp/outputs/e2e18-admin/vm3-queue')
OLD='63201b88ce5342d57fa81bc0e141ec2d10beec49'


def digest(p):return hashlib.sha256(p.read_bytes()).hexdigest()


def main():
    sha=subprocess.check_output(['git','rev-parse','HEAD'],cwd=ROOT,text=True).strip()
    branch=subprocess.check_output(['git','branch','--show-current'],cwd=ROOT,text=True).strip()
    assert branch=='claude/grasp-act-probes' and sha!=OLD
    assert not subprocess.check_output(['git','status','--porcelain'],cwd=ROOT,text=True)
    remote=subprocess.check_output(['git','ls-remote','origin','refs/heads/'+branch],cwd=ROOT,text=True).split()[0]
    assert sha==remote
    validation=json.loads((BASE/'release7-offline-summary.json').read_text())
    assert validation['tests']['failures']==validation['tests']['errors']==0
    assert validation['tests']['passed']==30
    for p,h in validation['source_hashes'].items():assert digest(ROOT/p)==h
    oldpath=QUEUE/f'20261015-release-gate-{OLD[:8]}.json'
    source=json.loads(oldpath.read_text())
    assert source['sha']==OLD and source['ready'] is False

    def replace(v):
        if isinstance(v,str):
            for a,b in ((OLD,sha),(OLD[:8],sha[:8]),('release6-','release7-')):v=v.replace(a,b)
            return v
        if isinstance(v,list):return [replace(x) for x in v]
        if isinstance(v,dict):return {k:replace(x) for k,x in v.items()}
        return v

    q=replace(source)
    for k in ('blocked_reason','blocked_at','pre_block_backup','superseded_by_sha','superseded_by_queue',
              'superseded_at','coordinator_diag_authorization'):
        q.pop(k,None)
    plans={s:json.loads((BASE/f'release7-{s}-plan.json').read_text()) for s in ('diagnostic','gate')}
    now=datetime.datetime.now().astimezone().isoformat()
    q.update(sha=sha,branch=branch,created_local=now,ready=True,status='diagnostics_ready_gate_blocked',
        stage_ready=dict(diagnostic=True,gate=False),gate_promotion_authorized_if_all_conditions_pass=False,
        supersedes_source_sha=OLD,run_count=48,authorized_run_count=8,max_combined_concurrency=8,
        profile=plans['diagnostic']['execution_profile'],
        order='8 diagnostics may be submitted together; gate40 is blocked pending explicit coordinator approval',
        diagnostic_authorization='User 2026-10-15: 74940 reproduction + 7 fresh seeds, ready=true, simultaneous diagnostic submission allowed',
        remote_source_verification=dict(local_head=sha,remote_head=remote,matches=True),
        seed_reservation=dict(path=str((BASE/'release7-seed-reservation.json').relative_to(ROOT)),
            sha256=digest(BASE/'release7-seed-reservation.json'),fresh=[74960,74966],reproduction=74940,gate=[74200,74239]),
        offline_validation=dict(path=str((BASE/'release7-offline-summary.json').relative_to(ROOT)),
            sha256=digest(BASE/'release7-offline-summary.json'),tests=validation['tests'],
            scope=validation['scope'],offline_replay_is_improvement_evidence=False),
        approval_conditions=dict(diagnostic='8 diagnostics authorized by user; no per-run reproduction dependency',
            gate='Separate explicit coordinator approval after 8/8 plus raw/input/video review; never automatic'))
    q['plan_sha256']={str((BASE/f'release7-{s}-plan.json').relative_to(ROOT)):digest(BASE/f'release7-{s}-plan.json') for s in plans}
    q['preconditions']=[s for s in q['preconditions'] if not any(t in s for t in ('NBV','candidate uncertainty','used view keys'))]
    q['preconditions'].extend([
        'Before submission check fresh 74960-74966 and inherited 74200-74239 against remote history; author made no host connection.',
        'setdown_lookaround_v1: after real lower/open/backoff, one extra front sweep then one bounded retrace and front/rear panorama; max total 180 SIM s.',
        'Verify actual unloaded body movement, return heading, map fit and regrasp; own wheel commands and static geometry are not motion/success evidence.',
        'Legacy teacher visible_counts are inapplicable for RGB-only perception. Use native input JPEGs and localizer wall/floor/door counts.',
        'final_map_pose_known is historical; final_map_pose_accepted and last decision control placement authorization.',
    ])
    q['report_needed']='Every run including failure/HOST_ERROR: raw/source/input hashes, first30 SIM s and >=6 review frames, '
    q['report_needed']+='opposite ends, actual lower/open/backoff/retrace/body yaw, fresh landmark counts/normal rank/score gap, '
    q['report_needed']+='all pair reports, all-run center-distance n/median/max, held_world_reads=0/invisible=0, regrasp, unchanged success criteria.'
    templates={s:next(r for r in source['runs'] if r['stage']==s) for s in plans}
    names=[f'release7-diagnostic-{i:02d}-{sha[:8]}' for i in range(8)]
    rows=[]
    for stage,indices in (('diagnostic',[7,*range(7)]),('gate',list(range(40)))):
        for index in indices:
            row=replace(templates[stage]);row.update(name=f'release7-{stage}-{index:02d}-{sha[:8]}',
                seed=plans[stage]['episodes'][index]['seed'],ready=stage=='diagnostic',
                requires_coordinator_approval=stage=='gate',max_parallel=8 if stage=='diagnostic' else 16,
                depends_on=[] if stage=='diagnostic' else names,
                condition='authorized' if stage=='diagnostic' else 'explicit gate approval required')
            command=row['command'];command[command.index('--per-run-mb')+3]=row['name']
            command[command.index('--episode')+1]=str(index)
            command[command.index('--out')+1]='/home/ugrp/ugrp-sim/runs/'+row['name']+'/raw'
            command[command.index('--active-recovery')+1]='setdown_lookaround_v1'
            rows.append(row)
    q['runs']=rows
    out=QUEUE/f'20261015-release-gate-{sha[:8]}.json'
    assert not out.exists()
    assert [r['seed'] for r in rows if r['stage']=='diagnostic']==[74940,*range(74960,74967)]
    for row in rows:
        c=row['command'];path=ROOT/c[c.index('--plan')+1];idx=int(c[c.index('--episode')+1])
        assert digest(path)==q['plan_sha256'][str(path.relative_to(ROOT))]
        assert json.loads(path.read_text())['episodes'][idx]['seed']==row['seed']
        assert c[c.index('--per-run-mb')+3]==row['name']
        assert c[c.index('--active-recovery')+1]=='setdown_lookaround_v1'
        assert row['ready']==(row['stage']=='diagnostic')
    serialized=json.dumps(q,ensure_ascii=False,separators=(',',':'))+'\n'
    assert len(serialized.encode())<65536, len(serialized.encode())
    backup=ROOT/'outputs/release7-review/release6-queue-before-supersede.json'
    backup.write_bytes(oldpath.read_bytes())
    source.update(ready=False,status='superseded',superseded_by_sha=sha,superseded_by_queue=str(out),
        stage_ready=dict(diagnostic=False,gate=False),superseded_at=now)
    oldpath.write_text(json.dumps(source,ensure_ascii=False,separators=(',',':'))+'\n')
    # Same-directory rename: workers never observe a partially written ready queue.
    temporary=out.with_suffix('.json.pending');temporary.write_text(serialized);temporary.replace(out)
    saved=json.loads(out.read_text());old=json.loads(oldpath.read_text())
    assert saved==q and old['status']=='superseded' and old['ready'] is False
    assert sum(r['ready'] for r in saved['runs'])==8
    assert not saved['stage_ready']['gate'] and not saved['gate_promotion_authorized_if_all_conditions_pass']
    receipt=dict(queue=str(out),sha=sha,ready=True,diagnostic_ready=8,gate_ready=0,
        gate_promotion_authorized_if_all_conditions_pass=False,old_status=old['status'],
        sha256=digest(out),bytes=out.stat().st_size,remote_source_verified=True,remote_execution=False)
    (ROOT/'outputs/release7-review/queue-receipt.json').write_text(json.dumps(receipt,indent=2)+'\n')
    print(json.dumps(receipt))


if __name__=='__main__':main()
