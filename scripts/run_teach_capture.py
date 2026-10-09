"""egomap53 one source-frozen teach/repeat trial, staged 2 then 4 seeds."""
from pathlib import Path
import argparse,json,os,signal
from scripts import run_own_map_return_repeat as old
from harness.own_teach_capture import attach,OPTION

ROOT=old.ROOT
EXP=ROOT/'experiments/2026-10-09-teach-capture'
RAW=Path('/Users/changmin/projects/ugrp/outputs/teach-capture-v1')
SEEDS=old.SEEDS


def bundle(seed,source):
    b=old.bundle(seed,source)
    b.update(execution_bundle_id=f'egomap53-teach-{seed}-v1',check='own-teach-capture',
        preregistration='e9018927',admission='user_authorized_DEV;stage1_two_seeds;stage2_only_if_gate_passed')
    b['options'].update(teach_capture=OPTION,return_policy='temporal_graph_forward_only_v1')
    return b


def preflight(source):
    receipt=old.base.verify_source(source)
    freeze=json.loads((EXP/'freeze.json').read_text())
    for p,h in freeze['files'].items():assert old.base.old.sha(ROOT/p)==h,('FROZEN_SOURCE_CHANGED',p)
    assert os.getpriority(os.PRIO_PROCESS,0)==0,'NICE_MUST_BE_ZERO'
    return dict(receipt,freeze=freeze,nice=0)


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--seed',type=int,choices=SEEDS,required=True)
    parser.add_argument('--output',type=Path,required=True);parser.add_argument('--expected-source-sha',required=True)
    parser.add_argument('--execute',action='store_true');a=parser.parse_args()
    receipt=preflight(a.expected_source_sha)
    assert a.output.resolve()==RAW/f'seed{a.seed}' and not a.output.exists()
    if a.seed not in SEEDS[:2]:
        gate=json.loads((RAW/'stage1-gate.json').read_text())
        assert gate['passed'] and gate['seeds']==list(SEEDS[:2]),'STAGE1_GATE_REQUIRED'
        for s,h in gate['prediction_seals'].items():assert old.base.old.sha(RAW/f'seed{s}'/'teach-graph.json')==h
    if not a.execute:return 0
    from scripts.agent_lock import DEFAULT_ROOT,status,acquire,release
    assert status(DEFAULT_ROOT) is None,'physics lock occupied'
    lock=acquire(DEFAULT_ROOT,owner='codex',branch='claude/ego-wall-map',purpose=f'egomap53 teach/repeat seed{a.seed}',pid=os.getpid(),expected_minutes=60)
    collected=[]
    def controller(explorer,*,seed):
        c=attach(old.controller(explorer,seed=seed),teach_capture=OPTION);collected.append(c);return c
    try:
        def timeout(*_):raise TimeoutError('HOST_BUDGET_60_MINUTES')
        signal.signal(signal.SIGALRM,timeout);signal.setitimer(signal.ITIMER_REAL,3600)
        from sim.own_map_closed_loop import PhysicsBackend
        result=old.previous.acquire(a.output,a.expected_source_sha,PhysicsBackend,bundle_override=bundle(a.seed,a.expected_source_sha),
            mapper_factory=old.actor,controller_factory=controller,progress_label=f'egomap53 seed{a.seed}')
        if collected:
            c=collected[0]
            c.traversal_graph.seal()
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
