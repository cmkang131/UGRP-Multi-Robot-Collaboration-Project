"""Verified-push queue registration only. No remote execution or gate approval."""
import datetime
import hashlib
import json
from pathlib import Path
import subprocess

ROOT=Path(__file__).resolve().parents[2]; BASE=Path(__file__).parent
QUEUE=Path('/Users/changmin/projects/ugrp/outputs/e2e18-admin/vm3-queue')
OLD='a2314b16d6d3c52d843fbde59fe7bda4eb8273bf'


def sha256(p):return hashlib.sha256(p.read_bytes()).hexdigest()


def main():
    def git(*args):return subprocess.check_output(['git',*args],cwd=ROOT,text=True).strip()
    sha=git('rev-parse','HEAD');branch=git('branch','--show-current')
    assert branch=='claude/grasp-act-probes' and sha!=OLD and not git('status','--porcelain')
    assert git('ls-remote','origin','refs/heads/'+branch).split()[0]==sha
    validation=json.loads((BASE/'release8-offline-summary.json').read_text())
    assert validation['tests']['failures']==validation['tests']['errors']==0 and validation['tests']['passed']==34
    for path,h in validation['source_hashes'].items():assert sha256(ROOT/path)==h
    plans={s:json.loads((BASE/f'release8-{s}-plan.json').read_text()) for s in ('diagnostic','gate')}
    assert [e['seed'] for e in plans['diagnostic']['episodes']]==[74940,74963,*range(74970,74977)]
    assert [e['seed'] for e in plans['gate']['episodes']]==list(range(74200,74240))
    profile=plans['diagnostic']['execution_profile']; assert profile==plans['gate']['execution_profile']
    names=[f'release8-diagnostic-{i:02d}-{sha[:8]}' for i in range(9)]
    runs=[]
    for stage,plan in plans.items():
        for i,episode in enumerate(plan['episodes']):
            name=f'release8-{stage}-{i:02d}-{sha[:8]}'
            command=['python3','scripts/remote_run.py','--host','gcp1','--detach','--class','dev','--pr','491',
                '--per-run-mb','96',str(ROOT),name,'--','.venv-sim/bin/python','-m','scripts.run_grasp_act_release',
                '--plan',str((BASE/f'release8-{stage}-plan.json').relative_to(ROOT)), '--episode',str(i),
                '--cap-s','180','--out',f'/home/ugrp/ugrp-sim/runs/{name}/raw']
            for key,value in profile.items():command.extend(['--'+key.replace('_','-'),str(value)])
            runs.append(dict(stage=stage,name=name,seed=episode['seed'],command=command,
                ready=stage=='diagnostic',requires_coordinator_approval=stage=='gate',
                max_parallel=2 if stage=='diagnostic' and i<2 else (7 if stage=='diagnostic' else 16),
                depends_on=[] if stage=='diagnostic' and i<2 else (names[:2] if stage=='diagnostic' else names),
                condition='repro' if stage=='diagnostic' and i<2 else ('fresh' if stage=='diagnostic' else 'gate')))
    now=datetime.datetime.now().astimezone().isoformat()
    queue=dict(owner='codex',branch=branch,sha=sha,pr=491,created_local=now,host='gcp1',
        pr_head_note='PR #491 head is claude/grasp-act-release; execute the pushed probes branch at this SHA.',
        source_worktree=str(ROOT),runner_cwd='/Users/changmin/projects/ugrp-wt/gcp-sim-host',
        runner_note='Use current GCP-capable launcher and immutable source snapshot. This file does not submit runs.',
        ready=True,status='diagnostics_ready_gate_blocked',stage_ready=dict(diagnostic=True,gate=False),
        run_count=49,authorized_run_count=9,gate_promotion_authorized_if_all_conditions_pass=False,
        profile=profile,order='2 exact failure reproductions -> 7 new seeds -> explicit coordinator approval -> gate40',
        conditions=dict(repro='authorized',fresh='both reproductions pass and first30 raw review',gate='explicit coordinator approval after 9/9 and raw/input/video review'),
        max_combined_concurrency=7,storage_budget_mib=dict(per_run_raw_upper=96,diagnostic=864,gate=3840,total=4704),
        criteria=dict(N=40,required=38,diagnostic_required=9,training_rgb=False,weld='off',held_world_reads=0,invisible_measurements=0),
        plan_sha256={str((BASE/f'release8-{s}-plan.json').relative_to(ROOT)):sha256(BASE/f'release8-{s}-plan.json') for s in plans},
        seed_reservation=dict(path=str((BASE/'release8-seed-reservation.json').relative_to(ROOT)),sha256=sha256(BASE/'release8-seed-reservation.json')),
        offline_validation=dict(path=str((BASE/'release8-offline-summary.json').relative_to(ROOT)),sha256=sha256(BASE/'release8-offline-summary.json')),
        remote_source_verification=dict(local_head=sha,remote_head=sha,matches=True),supersedes_source_sha=OLD,
        preconditions=[
            'Coordinator verifies no remote seed collision for 74970-74976 and inherited 74200-74239 before submission.',
            'Check exact source and plan hashes, disk/cost/idle20m/8h guards; no other source mixed in.',
            'Stop affected running/waiting jobs on confirmed defect; preserve every result including failures/HOST_ERROR.',
            'First30: own JPEG hashes/counts, accepted AND rejected map poses, signed commanded/actual yaw from evaluation, opposite ends, real lower/open/backoff.',
            'Review >=6 evenly spaced overview/own frames and at least one per 60 SIM seconds for every diagnostic.',
            'No runtime truth anchor or truth action; held_world_reads=0/invisible=0 with nonzero native camera inputs. Acceptance/success thresholds unchanged.',
            'Corrected stored-input replay still rejects 74963 r2. New trajectory, inverse turns, margin consistency and regrasp are UNVERIFIED.',
            'Initial alias at 74963 r1 (before any body turn) is not proved fixed by the yaw-sign change. Diagnose, never count a false map acceptance as success.',
            '9/9 plus input/video review is necessary, never sufficient authorization for gate40. Explicit coordinator approval required.',
            'No training RGB; no pooling with release5/6/7 or other profiles. Fetch-lite only; keep raw on persistent host disk.',
        ],runs=runs)
    oldpath=QUEUE/f'20261015-release-gate-{OLD[:8]}.json';old=json.loads(oldpath.read_text())
    assert old['sha']==OLD and old['ready'] is False
    out=QUEUE/f'20261015-release-gate-{sha[:8]}.json';assert not out.exists()
    (ROOT/'outputs/release8-review/previous-queue-before-supersede.json').write_bytes(oldpath.read_bytes())
    old.update(ready=False,status='superseded',stage_ready=dict(diagnostic=False,gate=False),
               superseded_by_sha=sha,superseded_by_queue=str(out),superseded_at=now)
    for r in old['runs']:r['ready']=False
    blob=json.dumps(queue,ensure_ascii=False,separators=(',',':'))+'\n';assert len(blob.encode())<65536,len(blob.encode())
    oldpath.write_text(json.dumps(old,ensure_ascii=False,separators=(',',':'))+'\n')
    pending=out.with_suffix('.json.pending');pending.write_text(blob);pending.replace(out)
    assert json.loads(out.read_text())==queue
    assert json.loads(oldpath.read_text())['status']=='superseded'
    receipt=dict(queue=str(out),sha=sha,sha256=sha256(out),diagnostic=9,gate_ready=False,
                 old_ready=False,old_status='superseded',remote_execution=False)
    (ROOT/'outputs/release8-review/queue-receipt.json').write_text(json.dumps(receipt,indent=2)+'\n')
    print(json.dumps(receipt))


if __name__=='__main__':main()
