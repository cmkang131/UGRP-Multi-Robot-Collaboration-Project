"""egomap49 one registered slot per invocation; no retries or GT control."""
from pathlib import Path
import argparse,json,os,signal
from scripts import run_own_map_goal_dev as previous
from scripts import run_active_navfn_start as frozen
from scripts import run_active_wall_rotleft as base
from harness.self_map_return_repeat import attach,OPTION
from harness.self_graph_cache import install as graph_cache
from harness.grid_acceleration import install as scalar_grid

ROOT=base.ROOT
EXP=ROOT/'experiments/2026-10-08-own-map-return-repeat'
RAW=Path('/Users/changmin/projects/ugrp/outputs/own-map-return-repeat-v1')
SEEDS=tuple(range(49001,49007))


def bundle(seed,source):
    if seed not in SEEDS:raise ValueError('PREREGISTERED_SEED_REQUIRED')
    b=frozen.bundle(source)
    b.update(execution_bundle_id=f'egomap49-return-{seed}-v1',check='own-map-return-repeat',
        preregistration='8a2fb7c8',case=f'seed{seed}',case_cap_s=630.,
        admission='user_authorized_frozen_six_DEV;360s_explore;egomap43_arrival_unchanged')
    b['task']['seed']=seed
    b['options'].update(map_utility=OPTION,map_acceleration='scalar_rays_v1',graph_acceleration='match_cache_v1',
        likelihood_tempering='pr_likelihood_half_v1',sensor_landmarks='floor_zones_doors_v1')
    b['schedule']=dict(explore_s=360.,suffix_cap_s=270.,relocalize_dev_timeout_s=60.)
    return b


def actor(*args,**kwargs):
    c=frozen.actor(*args,**kwargs)
    graph_cache(c.memory,graph_acceleration='match_cache_v1')
    return c


def controller(explorer,*,seed):
    return scalar_grid(attach(explorer,map_utility=OPTION,seed=seed),map_acceleration='scalar_rays_v1')


def preflight(source):
    receipts=base.verify_source(source)
    old=json.loads((ROOT/'experiments/2026-10-08-navfn-start-recovery/freeze.json').read_text())
    own=json.loads((EXP/'freeze.json').read_text())
    admitted=own['egomap47_acceleration_admission']
    for path,digest in old['files'].items():
        if path in admitted:
            assert digest==admitted[path]['original_sha256']
            assert base.old.sha(ROOT/path)==admitted[path]['accelerated_sha256']
        else:assert base.old.sha(ROOT/path)==digest,('EGOMAP47_FROZEN_SOURCE_CHANGED',path)
    assert all(base.old.sha(ROOT/p)==h for p,h in own['files'].items()),'EGOMAP49_FROZEN_SOURCE_CHANGED'
    equivalence=json.loads((ROOT/'experiments/2026-10-08-graph-runtime/results/performance.json').read_text())
    assert all(all(x['files_identical'].values()) for x in equivalence['equality'])
    receipts.update(freeze=own,egomap47_freeze=old,acceleration_equivalence=equivalence)
    return receipts


def main():
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('--seed',type=int,choices=SEEDS,required=True)
    p.add_argument('--output',type=Path,required=True);p.add_argument('--expected-source-sha',required=True)
    p.add_argument('--execute',action='store_true');a=p.parse_args()
    receipts=preflight(a.expected_source_sha)
    assert a.output.resolve()==RAW/f'seed{a.seed}' and not a.output.exists()
    if not a.execute:return 0
    from scripts.agent_lock import DEFAULT_ROOT,status,acquire,release
    assert status(DEFAULT_ROOT) is None,'physics lock occupied'
    lock=acquire(DEFAULT_ROOT,owner='codex',branch='claude/ego-wall-map',
        purpose=f'egomap49 return trial seed{a.seed}',pid=os.getpid(),expected_minutes=60)
    try:
        def timeout(*_):raise TimeoutError('HOST_BUDGET_60_MINUTES')
        signal.signal(signal.SIGALRM,timeout);signal.setitimer(signal.ITIMER_REAL,3600)
        from sim.own_map_closed_loop import PhysicsBackend
        result=previous.acquire(a.output,a.expected_source_sha,PhysicsBackend,bundle_override=bundle(a.seed,a.expected_source_sha),
            mapper_factory=actor,controller_factory=controller,progress_label=f'egomap49 seed{a.seed}')
        base.dump(a.output/'source-admission.json',receipts);base.dump(a.output/'lock.json',lock)
    finally:
        signal.setitimer(signal.ITIMER_REAL,0);release(DEFAULT_ROOT,owner='codex')
    print(json.dumps(result,ensure_ascii=False),flush=True)
    return 0 if result['status']=='RECORDED' else 1

if __name__=='__main__':raise SystemExit(main())
