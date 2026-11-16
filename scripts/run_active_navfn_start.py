"""egomap47: one preregistered B+NavFn-start run, locked and source-frozen."""
from pathlib import Path
import argparse,json,os,signal
from scripts import run_active_wall_rotleft as base
from scripts.run_frontier_duration import bundle as old_bundle
from harness.active_navfn_start import make_mapper,OPTION,CYCLE
ROOT=base.ROOT
EXP=ROOT/'experiments/2026-10-08-navfn-start-recovery'
RAW=Path('/Users/changmin/projects/ugrp/outputs/navfn-start-recovery-v1')

def bundle(source):
    b=old_bundle('B',source)
    b.update(execution_bundle_id='egomap47-navfn-start-v1',check='navfn-start-recovery',
        preregistration='0ff2b9cc',condition='B+navfn_start',admission='user_authorized_single_DEV; frozen360s; local_guards_retained')
    b['task']['seed']=47001;b['options']['navigation_start']=OPTION
    return b

def actor(*args,**kwargs):return make_mapper(*args,navigation_start=OPTION,frontier_observation=CYCLE,**kwargs)

def main():
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('--output',type=Path,required=True);p.add_argument('--expected-source-sha',required=True)
    p.add_argument('--execute',action='store_true');a=p.parse_args()
    receipts=base.verify_source(a.expected_source_sha)
    assert a.output.resolve()==RAW/'new-seed' and not a.output.exists()
    frozen=json.loads((EXP/'freeze.json').read_text())
    assert all(base.old.sha(ROOT/p)==h for p,h in frozen['files'].items())
    replay=json.loads((EXP/'results/replay.json').read_text())
    assert replay['off_paths']==0 and replay['on_paths']==4 and replay['input_unchanged']
    receipts.update(freeze=frozen,offline_gate=replay)
    if not a.execute:return 0
    from scripts.agent_lock import DEFAULT_ROOT,status,acquire,release
    assert status(DEFAULT_ROOT) is None,'physics lock occupied'
    lock=acquire(DEFAULT_ROOT,owner='codex',branch='claude/ego-wall-map',purpose='egomap47 seed47001 B+NavFn-start 360s',pid=os.getpid(),expected_minutes=30)
    try:
        def timeout(*_):raise TimeoutError('HOST_BUDGET_30_MINUTES')
        signal.signal(signal.SIGALRM,timeout);signal.setitimer(signal.ITIMER_REAL,1800)
        from sim.active_wall_map import PhysicsBackend
        result=base.acquire('new-seed',a.output,a.expected_source_sha,PhysicsBackend,bundle_override=bundle(a.expected_source_sha),mapper_factory=actor)
        base.dump(a.output/'source-admission.json',receipts);base.dump(a.output/'lock.json',lock)
    finally:release(DEFAULT_ROOT,owner='codex')
    print(json.dumps(result,ensure_ascii=False),flush=True)
    return 0 if result['status']=='RECORDED' else 1

if __name__=='__main__':raise SystemExit(main())
