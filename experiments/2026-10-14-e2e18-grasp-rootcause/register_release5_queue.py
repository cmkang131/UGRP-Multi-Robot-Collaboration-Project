"""Register coordinator-only work after verified push; never submit remotely."""
import datetime
import hashlib
import json
from pathlib import Path
import subprocess

ROOT=Path(__file__).resolve().parents[2]
BASE=Path(__file__).parent
QUEUE=Path('/Users/changmin/projects/ugrp/outputs/e2e18-admin/vm3-queue')
OLD='14ddb6ad33b7a86ad68eee0e5c98762a8771e14c'


def digest(p):return hashlib.sha256(p.read_bytes()).hexdigest()


def main():
    sha=subprocess.check_output(['git','rev-parse','HEAD'],cwd=ROOT,text=True).strip()
    branch=subprocess.check_output(['git','branch','--show-current'],cwd=ROOT,text=True).strip()
    assert branch=='claude/grasp-act-probes' and sha!=OLD
    assert not subprocess.check_output(['git','status','--porcelain'],cwd=ROOT,text=True)
    remote=subprocess.check_output(['git','ls-remote','origin','refs/heads/'+branch],cwd=ROOT,text=True).split()[0]
    assert sha==remote
    validation=json.loads((BASE/'release5-offline-summary.json').read_text())
    assert validation['tests']['passed']==20 and validation['tests']['failures']==0
    oldpath=QUEUE/f'20261014-release-gate-{OLD[:8]}.json';original=oldpath.read_bytes()
    source=json.loads(original)
    def replace(v):
        if isinstance(v,str):
            for a,b in [(OLD,sha),(OLD[:8],sha[:8]),('release-global-','release5-')]:v=v.replace(a,b)
            return v
        if isinstance(v,list):return [replace(x) for x in v]
        if isinstance(v,dict):return {k:replace(x) for k,x in v.items()}
        return v
    q=replace(source)
    for key in ('blocked_reason','blocked_at','pre_block_backup'):q.pop(key,None)
    now=datetime.datetime.now().astimezone().isoformat()
    q.update(sha=sha,branch=branch,created_local=now,ready=True,status='ready_diagnostic',
        stage_ready=dict(diagnostic=True,gate=False),gate_promotion_authorized_if_all_conditions_pass=False,
        supersedes_source_sha=OLD,offline_validation=validation,
        remote_source_verification=dict(local_head=sha,remote_head=remote,matches=True))
    q['profile']['lateral_recovery']='bounded_v1'
    plans={s:json.loads((BASE/f'release5-{s}-plan.json').read_text()) for s in ('diagnostic','gate')}
    q['plan_sha256']={str((BASE/f'release5-{s}-plan.json').relative_to(ROOT)):digest(BASE/f'release5-{s}-plan.json') for s in plans}
    q['seed_reservation']=json.loads((BASE/'release5-seed-reservation.json').read_text())
    q['order']='diagnostic 7 (2 reproduced failures + 5 fresh) -> coordinator review and explicit gate authorization -> gate 40'
    q['preconditions'].append('Gate 40 requires explicit coordinator authorization even if every diagnostic condition passes; automatic promotion is forbidden.')
    q['report_needed']+=' Lateral bounds, full beam-envelope side clearance (distinct from gripper clear_m), commanded PWM vs realized displacement, and post-correction own RGB relocalization.'
    for row in q['runs']:
        command=row['command'];stage=row['stage'];idx=int(command[command.index('--episode')+1])
        row['seed']=plans[stage]['episodes'][idx]['seed']
        command.extend(['--lateral-recovery','bounded_v1'])
        if stage=='gate':row['condition']='Explicit coordinator approval required after 7/7 and first-30-SIM/source/input/video review; never automatically promote.'
    out=QUEUE/f'20261015-release-gate-{sha[:8]}.json'
    assert not out.exists()
    backup=QUEUE/f'20261014-release-gate-{OLD[:8]}.before-{sha[:8]}.json'
    backup.write_bytes(original);assert digest(backup)==hashlib.sha256(original).hexdigest()
    source.update(ready=False,status='superseded',superseded_by_sha=sha,superseded_by_queue=str(out),
        stage_ready=dict(diagnostic=False,gate=False),superseded_at=now)
    # Disable the known-defective queue before exposing the replacement.
    oldpath.write_text(json.dumps(source,ensure_ascii=False,separators=(',',':'))+'\n')
    out.write_text(json.dumps(q,ensure_ascii=False,separators=(',',':'))+'\n')
    saved=json.loads(out.read_text());old=json.loads(oldpath.read_text())
    assert saved['sha']==remote and saved['run_count']==len(saved['runs'])==47
    assert saved['gate_promotion_authorized_if_all_conditions_pass'] is False
    assert old['status']=='superseded' and old['ready'] is False
    assert len([r for r in saved['runs'] if r['stage']=='diagnostic'])==7
    assert out.stat().st_size<65536
    for row in saved['runs']:
        c=row['command'];stage=row['stage'];idx=int(c[c.index('--episode')+1])
        p=ROOT/c[c.index('--plan')+1]
        assert digest(p)==saved['plan_sha256'][str(p.relative_to(ROOT))]
        assert row['seed']==json.loads(p.read_text())['episodes'][idx]['seed']
        assert c[c.index('--out')+1]=='/home/ugrp/ugrp-sim/runs/'+row['name']+'/raw'
    print(json.dumps(dict(queue=str(out),sha=sha,ready=True,diagnostic=7,gate=40,
        gate_promotion_authorized_if_all_conditions_pass=False,old_status=old['status'],bytes=out.stat().st_size)))


if __name__=='__main__':main()
