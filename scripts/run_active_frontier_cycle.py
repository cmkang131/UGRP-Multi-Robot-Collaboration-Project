"""egomap45 one preregistered 180s DEV, frozen egomap34 + frontier cycle."""
from pathlib import Path
import argparse,json,os,signal
from scripts import run_active_wall_rotleft as base
from harness.active_frontier_cycle import make_mapper,OPTION
ROOT=base.ROOT
EXP=ROOT/'experiments/2026-10-08-frontier-visibility'
RAW=Path('/Users/changmin/projects/ugrp/outputs/frontier-visibility-v1')


def bundle(source):
    b=base.frozen_bundle('new-seed',source)
    b.update(execution_bundle_id='egomap45-frontier-cycle-dev-v1',check='active-frontier-cycle',
        admission='user_authorized_DEV_1; preregistered operational coverage criteria',preregistration='d19fe326')
    b['task']['seed']=45001
    b['options']['frontier_observation']=OPTION
    return b


def actor(*args,**kwargs):return make_mapper(*args,frontier_observation=OPTION,**kwargs)


def main():
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('--output',type=Path,required=True);p.add_argument('--expected-source-sha',required=True)
    p.add_argument('--execute',action='store_true');args=p.parse_args()
    receipts=base.verify_source(args.expected_source_sha)
    assert args.output.resolve()==RAW/'new-seed' and not args.output.exists()
    frozen=json.loads((EXP/'freeze.json').read_text())
    assert all(base.old.sha(ROOT/p)==h for p,h in frozen['files'].items())
    receipts['freeze']=frozen
    if not args.execute:return 0
    from scripts.agent_lock import DEFAULT_ROOT,status,acquire,release
    assert status(DEFAULT_ROOT) is None,'physics lock occupied'
    lock=acquire(DEFAULT_ROOT,owner='codex',branch='claude/ego-wall-map',purpose='egomap45 frontier sensing cycle seed45001',pid=os.getpid(),expected_minutes=30)
    try:
        def timeout(*_):raise TimeoutError('HOST_BUDGET_30_MINUTES')
        signal.signal(signal.SIGALRM,timeout);signal.setitimer(signal.ITIMER_REAL,1800)
        from sim.active_wall_map import PhysicsBackend
        result=base.acquire('new-seed',args.output,args.expected_source_sha,PhysicsBackend,
            bundle_override=bundle(args.expected_source_sha),mapper_factory=actor)
        base.dump(args.output/'source-admission.json',receipts);base.dump(args.output/'lock.json',lock)
    finally:release(DEFAULT_ROOT,owner='codex')
    print(json.dumps(result,ensure_ascii=False),flush=True)
    return 0 if result['status']=='RECORDED' else 1

if __name__=='__main__':raise SystemExit(main())
