"""s2v48 two registered full DEV runs; own RGB only, exclusive agent_lock."""
import argparse
import copy
import json
import os
from pathlib import Path
from harness import zone_s2_look_before_move_contract as contract
from harness.zone_final_pair_binding import bind
from harness.zone_solo_cyan_bias_tempering import attach as bias_attach
from harness.zone_solo_cyan_look_before_move import attach
from scripts import run_s2_landmarks_dev as frozen
from scripts.run_final_environment_checks import check_source,write

def runtime_factory(b):
    clean=copy.deepcopy(b)
    for key in ('look_before_move','forward_scale','likelihood_tempering'):clean['options'].pop(key)
    base=frozen.runtime_factory(clean)
    def factory(*args,**kw):
        r=bias_attach(base(*args,**kw),forward_scale=b['options']['forward_scale'],
            likelihood_tempering=b['options']['likelihood_tempering'],calibration=b['bias_calibration'],servo_stiffness='real_v1')
        r.look_bias_calibration=b['bias_calibration']
        return attach(r,look_before_move=b['options']['look_before_move'],floor_table=b['floor_appearance'])
    return factory

def run(b,out):
    contract.require_execution(b)
    def writer(p,value):
        if p.name=='result.json':value.update(seed=b['task']['seed'],options=b['options'],dev_preregistration=b['dev_preregistration'])
        write(p,value)
    return bind(frozen.run,c=contract,runtime_factory=runtime_factory,write=writer)(b,out)

def main():
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('--execute',action='store_true')
    p.add_argument('--expected-source-sha',required=True);p.add_argument('--seed',required=True,type=int)
    p.add_argument('--output',type=Path,required=True)
    p.add_argument('--look-before-move',choices=('off','rgb_sweep_v1'),default='off');a=p.parse_args()
    b=contract.bundle(a.expected_source_sha,a.seed,look_before_move=a.look_before_move)
    if not a.execute:print(json.dumps(dict(execution_started=False,bundle=b['execution_bundle_id'],options=b['options'])));return
    check_source(a.expected_source_sha);contract.require_execution(b)
    root=Path('/Users/changmin/projects/ugrp/outputs').resolve()
    if not a.output.is_absolute() or not a.output.resolve().is_relative_to(root) or a.output.exists():raise ValueError('new primary output required')
    from scripts import agent_lock
    from harness.zone_pair_highpose_exact_speedups import install
    held=agent_lock.acquire(agent_lock.DEFAULT_ROOT,owner='codex',branch='codex/s2-realism',
        purpose=f's2v48 own RGB look-before-move full seed{a.seed}',pid=os.getpid(),expected_minutes=35,timing_sensitive=True)
    undo=None
    try:
        _,undo=install('v98-exact-v6');result=run(b,a.output)
        print(json.dumps({k:result.get(k) for k in ('status','failure','evaluation','wall_per_sim')}),flush=True)
    finally:
        if undo:undo()
        released=agent_lock.release(agent_lock.DEFAULT_ROOT,owner='codex')
        write(a.output/'lock.json',dict(acquired=held,released=released,status_after=agent_lock.status(agent_lock.DEFAULT_ROOT)))

if __name__=='__main__':main()
