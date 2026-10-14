"""Register locally only after verified push. Never submit or authorize gate40."""
import datetime
import hashlib
import json
from pathlib import Path
import subprocess

ROOT=Path(__file__).resolve().parents[2]
BASE=Path(__file__).parent
QUEUE=Path('/Users/changmin/projects/ugrp/outputs/e2e18-admin/vm3-queue')


def digest(path):return hashlib.sha256(path.read_bytes()).hexdigest()


def main():
    def git(*args):return subprocess.check_output(['git',*args],cwd=ROOT,text=True).strip()
    sha=git('rev-parse','HEAD');branch=git('branch','--show-current')
    assert branch=='claude/grasp-act-probes' and not git('status','--porcelain')
    assert git('ls-remote','origin','refs/heads/'+branch).split()[0]==sha
    validation=json.loads((BASE/'release11-offline-summary.json').read_text())
    assert validation['tests']['failures']==validation['tests']['errors']==0
    assert validation['tests']['passed']==28
    for path,h in validation['source_hashes'].items():assert digest(ROOT/path)==h
    bisect=QUEUE/'20261015-release-bisect-4a69e6bc.json'
    bisect_hash=digest(bisect);old=json.loads(bisect.read_text())
    assert old['ready'] is False and all(not r['ready'] for r in old['runs'])
    prior=QUEUE/'20261015-release-gate-8e520ea2.json'
    previous=json.loads(prior.read_text())
    assert previous['ready'] is False and all(not r['ready'] for r in previous['runs'])
    plans={s:json.loads((BASE/f'release11-{s}-plan.json').read_text()) for s in ('diagnostic','gate')}
    assert [e['seed'] for e in plans['diagnostic']['episodes']]==[74940,74963,*range(74970,74977)]
    assert [e['seed'] for e in plans['gate']['episodes']]==list(range(74200,74240))
    profile=plans['diagnostic']['execution_profile']
    assert profile==plans['gate']['execution_profile'] and profile['regrasp_check']=='own_rgb_lift_v1'
    assert all(p['gate_promotion_authorized_if_all_conditions_pass'] is False for p in plans.values())
    names=[f'release11-diagnostic-{i:02d}-{sha[:8]}' for i in range(9)]
    runs=[]
    for stage,plan in plans.items():
        for i,episode in enumerate(plan['episodes']):
            name=f'release11-{stage}-{i:02d}-{sha[:8]}'
            command=['python3','scripts/remote_run.py','--host','gcp1','--detach','--class','dev','--pr','491',
                '--per-run-mb','96',str(ROOT),name,'--','.venv-sim/bin/python','-m','scripts.run_grasp_act_release',
                '--plan',str((BASE/f'release11-{stage}-plan.json').relative_to(ROOT)), '--episode',str(i),
                '--cap-s','180','--out',f'/home/ugrp/ugrp-sim/runs/{name}/raw']
            for key,value in profile.items():command.extend(['--'+key.replace('_','-'),str(value)])
            repro=stage=='diagnostic' and i<2
            runs.append(dict(stage=stage,name=name,seed=episode['seed'],command=command,
                ready=repro,requires_coordinator_approval=stage=='gate',
                max_parallel=2 if repro else (7 if stage=='diagnostic' else 16),
                depends_on=[] if repro else (names[:2] if stage=='diagnostic' else names[2:]),
                condition='repro' if repro else ('fresh' if stage=='diagnostic' else 'gate')))
    queue=dict(owner='codex',branch=branch,sha=sha,pr=491,host='gcp1',
        created_local=datetime.datetime.now().astimezone().isoformat(),
        source_worktree=str(ROOT),runner_cwd='/Users/changmin/projects/ugrp-wt/gcp-sim-host',
        pr_head_note='PR #491 head is a different branch. Execute the pushed probes SHA, not the PR head.',
        ready=True,status='reproductions_ready_fresh_and_gate_blocked',stage_ready=dict(reproduction=True,fresh=False,gate=False),
        run_count=49,authorized_run_count=9,gate_promotion_authorized_if_all_conditions_pass=False,
        order='reproduce 74940/74963 -> fresh7 -> explicit coordinator approval -> gate40',profile=profile,
        conditions=dict(repro='authorized diagnosis only',fresh='both reproductions pass plus raw/input/video review',
                        gate='explicit coordinator approval after all nine diagnostics and review'),
        max_combined_concurrency=16,storage_budget_mib=dict(per_run_raw_upper=96,diagnostic=864,gate=3840,total=4704),
        criteria=dict(N=40,required=38,diagnostic_required=9,training_rgb=False,weld='off',held_world_reads=0,invisible_measurements=0),
        plan_sha256={str((BASE/f'release11-{s}-plan.json').relative_to(ROOT)):digest(BASE/f'release11-{s}-plan.json') for s in plans},
        offline_validation=dict(path=str((BASE/'release11-offline-summary.json').relative_to(ROOT)),sha256=digest(BASE/'release11-offline-summary.json')),
        report_required=plans['diagnostic']['report_required'],
        remote_source_verification=dict(local_head=sha,remote_head=sha,matches=True),
        bisect=dict(path=str(bisect),sha256=bisect_hash,ready=False),
        preconditions=[
            'Coordinator checks remote seed history, exact source/plan hashes and current launcher before submitting. No remote access in this registration.',
            'Check disk/cost/idle20m/8h/deallocation guards; raw persistent disk, fetch-lite only.',
            'Stop affected jobs immediately on a confirmed physical/control defect; preserve failures and HOST_ERROR.',
            'All new RGB checks are provisional; measure both held positives and empty-grip negatives with separate evaluator labels, never control truth.',
            'No correction wheel commands before both current-epoch RGB confirmations and code ACK. Record per-robot retry counts and reasons.',
            'New enabled full-trajectory equivalence on 74940 is unverified. Frozen placement choices are 5/5 equivalent, not a physical pass.',
            'Existing prefix remains observable_v2 and is separate from the RGB-only release input audit.',
            'Fresh7 and gate40 stay blocked on either reproduction failure. Nine passes never authorize gate40 automatically.',
        ],runs=runs)
    assert len(runs)==49 and sum(r['ready'] for r in runs)==2
    assert sum(r['requires_coordinator_approval'] for r in runs)==40
    path=QUEUE/f'20261015-release-gate-{sha[:8]}.json';assert not path.exists()
    blob=json.dumps(queue,ensure_ascii=False,separators=(',',':'))+'\n'
    assert len(blob.encode())<65536
    pending=path.with_suffix('.json.pending');pending.write_text(blob);pending.replace(path)
    assert json.loads(path.read_text())==queue and digest(bisect)==bisect_hash
    receipt=dict(queue=str(path),sha=sha,sha256=digest(path),ready_runs=2,
        fresh_ready=False,gate_ready=False,bisect_unchanged_sha256=bisect_hash,remote_execution=False)
    (ROOT/'outputs/release11-review/queue-receipt.json').write_text(json.dumps(receipt,indent=2)+'\n')
    print(json.dumps(receipt))


if __name__=='__main__':main()
