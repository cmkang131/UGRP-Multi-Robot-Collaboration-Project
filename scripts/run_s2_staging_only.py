"""s2v51 locked full DEV, staged approach option, unchanged v136 settings."""
import argparse,copy,functools,json,os
from pathlib import Path
from harness import zone_s2_staging_only_contract as contract
from harness.zone_final_pair_binding import bind
from scripts import run_s2_look_before_move as previous
from scripts.run_final_environment_checks import check_source,write

def runtime_factory(b):
    from harness.zone_solo_cyan_look_before_move import attach
    clean=copy.deepcopy(b);mode=clean['options'].pop('final_approach')
    return bind(previous.runtime_factory,attach=functools.partial(attach,final_approach=mode))(clean)

def run(b,out):
    return bind(previous.run,contract=contract,runtime_factory=runtime_factory)(b,out)

def main():
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('--execute',action='store_true')
    p.add_argument('--expected-source-sha',required=True);p.add_argument('--seed',type=int,required=True)
    p.add_argument('--output',type=Path,required=True)
    p.add_argument('--look-before-move',choices=('off','rgb_sweep_v1'),default='off')
    p.add_argument('--final-approach',choices=('off','staging_v133_v1'),default='off')
    p.add_argument('--regression-proof',type=Path,action='append',default=[]);a=p.parse_args()
    proofs=[dict(path=str(p.resolve()),sha256=contract.old.old.original_contract.old.hp.base.sha(p)) for p in a.regression_proof] or None
    b=contract.bundle(a.expected_source_sha,a.seed,look_before_move=a.look_before_move,final_approach=a.final_approach,proofs=proofs)
    if not a.execute:print(json.dumps(dict(execution_started=False,bundle=b['execution_bundle_id'])));return
    check_source(a.expected_source_sha);contract.require_execution(b)
    root=Path('/Users/changmin/projects/ugrp/outputs').resolve()
    if not a.output.is_absolute() or not a.output.resolve().is_relative_to(root) or a.output.exists():raise ValueError('new primary output required')
    from scripts import agent_lock
    from harness.zone_pair_highpose_exact_speedups import install
    held=agent_lock.acquire(agent_lock.DEFAULT_ROOT,owner='codex',branch='codex/s2-realism',
        purpose=f's2v51 staging-only condition A seed{a.seed}',pid=os.getpid(),expected_minutes=35,timing_sensitive=True)
    undo=None
    try:
        _,undo=install('v98-exact-v6');result=run(b,a.output)
        print(json.dumps({k:result.get(k) for k in ('status','failure','evaluation','wall_per_sim')}),flush=True)
    finally:
        if undo:undo()
        released=agent_lock.release(agent_lock.DEFAULT_ROOT,owner='codex')
        write(a.output/'lock.json',dict(acquired=held,released=released,status_after=agent_lock.status(agent_lock.DEFAULT_ROOT)))

if __name__=='__main__':main()
