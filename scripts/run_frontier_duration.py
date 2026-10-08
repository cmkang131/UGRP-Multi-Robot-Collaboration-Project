"""egomap46 paired, separately locked 360s trials; frozen A/B algorithms."""
from pathlib import Path
import argparse,json,os,signal
from scripts import run_active_wall_rotleft as base
from harness.active_frontier_cycle import make_mapper,OPTION
ROOT=base.ROOT
EXP=ROOT/'experiments/2026-10-08-frontier-duration'
RAW=Path('/Users/changmin/projects/ugrp/outputs/frontier-duration-v1')
SEED=46001
CONDITIONS=('A','B')


def bundle(condition,source):
    if condition not in CONDITIONS:raise ValueError('EXPLICIT_PREREGISTERED_CONDITION_REQUIRED')
    b=base.frozen_bundle('new-seed',source)
    b.update(execution_bundle_id=f'egomap46-duration-{condition}-v1',check='frontier-duration',case_cap_s=360.,
        admission='user_authorized_DEV_pair; separate360s_condition; preserve_existing_local_holds',
        preregistration='12915e74',condition=condition)
    b['task']['seed']=SEED
    if condition=='B':b['options']['frontier_observation']=OPTION
    return b


def actor(condition):
    if condition not in CONDITIONS:raise ValueError('EXPLICIT_PREREGISTERED_CONDITION_REQUIRED')
    def create(*args,**kwargs):
        return make_mapper(*args,frontier_observation=OPTION if condition=='B' else 'off',**kwargs)
    return create


def main():
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('--condition',choices=CONDITIONS,required=True)
    p.add_argument('--output',type=Path,required=True);p.add_argument('--expected-source-sha',required=True)
    p.add_argument('--execute',action='store_true');args=p.parse_args()
    receipts=base.verify_source(args.expected_source_sha)
    assert args.output.resolve()==RAW/args.condition/'new-seed' and not args.output.exists()
    frozen=json.loads((EXP/'freeze.json').read_text())
    assert all(base.old.sha(ROOT/p)==h for p,h in frozen['files'].items())
    receipts['freeze']=frozen
    if not args.execute:return 0
    if args.condition=='B':
        previous=json.loads((RAW/'A/new-seed/result.json').read_text())
        assert previous['source_sha']==args.expected_source_sha
        # A can fail the scientific criterion or physically stop. Preserve it,
        # but never use its result to modify or omit the preregistered B trial.
    from scripts.agent_lock import DEFAULT_ROOT,status,acquire,release
    assert status(DEFAULT_ROOT) is None,'physics lock occupied'
    lock=acquire(DEFAULT_ROOT,owner='codex',branch='claude/ego-wall-map',
        purpose=f'egomap46 condition{args.condition} seed46001 360s',pid=os.getpid(),expected_minutes=30)
    try:
        def timeout(*_):raise TimeoutError('HOST_BUDGET_30_MINUTES')
        signal.signal(signal.SIGALRM,timeout);signal.setitimer(signal.ITIMER_REAL,1800)
        from sim.active_wall_map import PhysicsBackend
        result=base.acquire('new-seed',args.output,args.expected_source_sha,PhysicsBackend,
            bundle_override=bundle(args.condition,args.expected_source_sha),mapper_factory=actor(args.condition))
        base.dump(args.output/'source-admission.json',receipts);base.dump(args.output/'lock.json',lock)
    finally:release(DEFAULT_ROOT,owner='codex')
    print(json.dumps(result,ensure_ascii=False),flush=True)
    return 0 if result['status']=='RECORDED' else 1

if __name__=='__main__':raise SystemExit(main())
