"""egomap54 four preregistered DEV slots after the recorded handoff check."""
from pathlib import Path
import argparse,json,os,signal
from scripts import run_teach_capture as teach
from scripts import run_own_map_return_repeat as old

ROOT=old.ROOT
EXP=ROOT/'experiments/2026-10-09-teach-return-dev'
RAW=Path('/Users/changmin/projects/ugrp/outputs/teach-return-dev-v1')
SEEDS=(54001,54002,54003,54004)
S2_ACQUIRED=1791526528.198967


def bundle(seed,source):
    if seed not in SEEDS:raise ValueError('PREREGISTERED_SEED_REQUIRED')
    b=teach.bundle(49002,source)
    b.update(execution_bundle_id=f'egomap54-teach-{seed}-v1',check='own-teach-return-dev',case=f'seed{seed}',
        preregistration='experiments/2026-10-09-teach-return-dev/README.md',
        admission='user_authorized_DEV;four_new_seeds;after_s2v59_and_S3_smoke')
    b['task']['seed']=seed
    return b


def queue_receipt(records):
    s2=next((r for r in records if r.get('branch')=='codex/s2-realism' and
        r.get('acquired_unix')==S2_ACQUIRED and 's2v59' in r.get('purpose','')),None)
    if s2 is None:raise ValueError('S2V59_NOT_RELEASED')
    s3=next((r for r in records if r.get('branch','').startswith('codex/s3') and
        any(s in r.get('purpose','').lower() for s in ('smoke','스모크')) and
        r.get('acquired_unix',0)>=s2['released_unix'] and not r.get('stale_release',False)),None)
    if s3 is None:raise ValueError('S3_SMOKE_NOT_RELEASED_AFTER_S2V59')
    return dict(s2=s2,s3=s3)


def preflight(source):
    receipt=old.base.verify_source(source)
    freeze=json.loads((EXP/'freeze.json').read_text())
    for p,h in freeze['files'].items():assert old.base.old.sha(ROOT/p)==h,('FROZEN_SOURCE_CHANGED',p)
    gate=RAW/'offline-transition/result.json';result=json.loads(gate.read_text())
    assert old.base.old.sha(gate)==freeze['offline_transition_sha256'],'OFFLINE_GATE_CHANGED'
    assert result['passed'] and result['errors']==0 and result['repeat_entered'] and result['gt_inputs']==0
    assert os.getpriority(os.PRIO_PROCESS,0)==0,'NICE_MUST_BE_ZERO'
    return dict(receipt,freeze=freeze,offline_transition_sha256=old.base.old.sha(gate),nice=0)


def main():
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('--seed',type=int,choices=SEEDS,required=True)
    p.add_argument('--output',type=Path,required=True);p.add_argument('--expected-source-sha',required=True)
    p.add_argument('--execute',action='store_true');a=p.parse_args()
    receipt=preflight(a.expected_source_sha)
    assert a.output.resolve()==RAW/f'seed{a.seed}' and not a.output.exists()
    if not a.execute:return 0
    from scripts.agent_lock import DEFAULT_ROOT,status,acquire,release
    receipt['predecessors']=queue_receipt([json.loads(l) for l in (DEFAULT_ROOT/'released.jsonl').read_text().splitlines()])
    assert status(DEFAULT_ROOT) is None,'physics lock occupied'
    lock=acquire(DEFAULT_ROOT,owner='codex',branch='claude/ego-wall-map',purpose=f'egomap54 teach/repeat seed{a.seed}',pid=os.getpid(),expected_minutes=60)
    collected=[]
    def factory(explorer,*,seed):
        c=teach.make_controller(explorer,seed=seed);collected.append(c);return c
    try:
        def timeout(*_):raise TimeoutError('HOST_BUDGET_60_MINUTES')
        signal.signal(signal.SIGALRM,timeout);signal.setitimer(signal.ITIMER_REAL,3600)
        from sim.own_map_closed_loop import PhysicsBackend
        result=old.previous.acquire(a.output,a.expected_source_sha,PhysicsBackend,bundle_override=bundle(a.seed,a.expected_source_sha),
            mapper_factory=old.actor,controller_factory=factory,progress_label=f'egomap54 seed{a.seed}')
        if collected:
            c=collected[0];c.traversal_graph.seal()
            old.base.dump(a.output/'teach-graph.json',c.traversal_graph.snapshot())
            old.base.dump(a.output/'teach-return.json',dict(route=None if c.traversal is None else c.traversal.route,
                matches=[] if c.traversal is None else c.traversal.match_events,
                failure=None if c.traversal is None else c.traversal.failure,
                loss_route=c.traversal_graph.route(c.traversal_graph.anchor)))
        old.base.dump(a.output/'source-admission.json',receipt);old.base.dump(a.output/'lock.json',lock)
        old.base.dump(a.output/'artifacts.sha256.json',{str(p.relative_to(a.output)):old.base.old.sha(p) for p in sorted(a.output.rglob('*')) if p.is_file() and p.name!='artifacts.sha256.json'})
    finally:
        signal.setitimer(signal.ITIMER_REAL,0);release(DEFAULT_ROOT,owner='codex')
    print(json.dumps(result,ensure_ascii=False),flush=True)
    return 0 if result['status']=='RECORDED' else 1


if __name__=='__main__':raise SystemExit(main())
