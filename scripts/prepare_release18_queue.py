"""Write a new, fully disabled release18 queue. Never contact an execution host."""
from __future__ import annotations

import argparse
from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path
import subprocess

ROOT = Path(__file__).resolve().parents[1]
PLAN = 'experiments/2026-10-14-e2e18-grasp-rootcause/release18-diagnostic-plan.json'
FLAGS = ('approved','enabled','ready','submitted','scheduled','executed')


def build(sha):
    plan = json.loads((ROOT/PLAN).read_text())
    runs = []
    for i, episode in enumerate(plan['episodes']):
        repro = i < 2
        name = f"r18{'d' if repro else 'n'}-{i if repro else i-2:02d}-{sha[:8]}"
        guard = ('import subprocess,sys\nworktree,expected=sys.argv[1:3]\n'
                 "actual=subprocess.check_output(['git','-C',worktree,'rev-parse','HEAD'],text=True).strip()\n"
                 "if actual!=expected: raise SystemExit('queued source SHA changed; do not execute')\n"
                 "if subprocess.check_output(['git','-C',worktree,'status','--porcelain']): raise SystemExit('dirty queued source; do not execute')\n"
                 'raise SystemExit(subprocess.call(sys.argv[3:]))\n')
        command = ['python3','-c',guard,str(ROOT),sha,'python3','scripts/remote_run.py',
                   '--host','gcp1','--detach','--class','dev','--pr','491','--per-run-mb','96',str(ROOT),name,
                   '--','.venv-sim/bin/python','-m','scripts.run_grasp_act_release','--plan',PLAN,
                   '--episode',str(i),'--cap-s','180','--out',f'/home/ugrp/ugrp-sim/runs/{name}/raw']
        for key,value in plan['execution_profile'].items():
            command += ['--'+key.replace('_','-'),value]
        runs.append(dict(stage='diagnostic',cohort='development_reproduction' if repro else 'fresh_diagnostic',
                         name=name,seed=episode['seed'],episode=i,source_sha=sha,
                         **{f:False for f in FLAGS},requires_coordinator_approval=True,
                         requires_reproduction_review=not repro,pooling='forbidden',command=command))
    return dict(owner='codex-release18',branch='claude/grasp-act-probes',pr=491,host='gcp1',
                source_worktree=str(ROOT),runner_cwd=str(ROOT),sha=sha,profile='release18_v1',
                created_utc=datetime.now(timezone.utc).isoformat(),
                **{f:False for f in FLAGS},stage_ready=dict(reproduction=False,fresh=False,gate=False),
                coordinator_approval=dict(approved=False),authorized_run_count=0,run_count=9,
                requested_diagnostic_count=9,denominators=plan['denominators'],gate40=plan['gate40'],
                gate_promotion_authorized_if_all_conditions_pass=False,
                training_rgb=False,weld='off',remote_host_contacted=False,
                max_combined_concurrency=2,storage_budget_mib=plan['storage_budget_mib'],
                status='AWAITING_INDEPENDENT_REVIEW_AND_COORDINATOR_APPROVAL',pooling='release18 only',
                preconditions=['independent Claude review after commit','coordinator approval',
                               'remote source/seed-history preflight by coordinator',
                               'review reproduction 2/2 before fresh7; stop on confirmed defect'],
                plan_sha256=hashlib.sha256((ROOT/PLAN).read_bytes()).hexdigest(),runs=runs)


def verify(queue):
    assert len(queue['sha']) == 40
    assert queue['plan_sha256'] == hashlib.sha256((ROOT/PLAN).read_bytes()).hexdigest()
    assert [r['seed']for r in queue['runs']] == [74963,74976,*range(78520,78527)]
    assert len(queue['runs']) == queue['run_count'] == 9
    for item in [queue,*queue['runs']]:
        assert all(item[f] is False for f in FLAGS)
    assert not any(queue['stage_ready'].values())
    assert queue['coordinator_approval']['approved'] is False
    assert queue['authorized_run_count']==0 and not queue['gate_promotion_authorized_if_all_conditions_pass']
    expected = build(queue['sha'])
    assert queue['runs'] == expected['runs']


def main():
    p = argparse.ArgumentParser()
    p.add_argument('--verify',type=Path)
    p.add_argument('--queue-root',type=Path,default=Path('/Users/changmin/projects/ugrp/outputs/e2e18-admin/vm3-queue'))
    args = p.parse_args()
    if args.verify:
        verify(json.loads(args.verify.read_text()))
        print('verified: 9 runs; all approval/execution flags false')
        return
    assert subprocess.check_output(['git','branch','--show-current'],cwd=ROOT,text=True).strip()=='claude/grasp-act-probes'
    assert not subprocess.check_output(['git','status','--porcelain'],cwd=ROOT)
    sha = subprocess.check_output(['git','rev-parse','HEAD'],cwd=ROOT,text=True).strip()
    queue = build(sha)
    verify(queue)
    path = args.queue_root/f'20261015-release-gate-{sha[:8]}.json'
    with path.open('x') as f:
        json.dump(queue,f,indent=2,ensure_ascii=False)
        f.write('\n')
    print(path)


if __name__=='__main__':
    main()
