"""s2v48 one own-RGB side scan, seed1054, no pickup/transport; lock mandatory."""
import argparse
import copy
import json
import os
from pathlib import Path
from types import SimpleNamespace
from harness import zone_s2_side_scan_contract as contract
from harness.zone_final_pair_binding import bind
from harness.zone_solo_cyan_bias_tempering import attach,closure,replace_cell
from harness.zone_solo_cyan_side_scan import runtime_class
from scripts import run_s2_landmarks_dev as frozen
from scripts.run_final_environment_checks import check_source,write


def runtime_factory(b):
    clean=copy.deepcopy(b)
    for key in ('side_scan','forward_scale','likelihood_tempering'):clean['options'].pop(key)
    clean['mode']='full';base=frozen.runtime_factory(clean)
    def factory(*args,**kw):
        # Wrap the same complete v133 class without constructing it twice.
        previous=closure(base)['Runtime']
        patched=runtime_class(previous)
        make=replace_cell(base,'Runtime',patched)
        runtime=make(*args,**kw,side_scan=b['options']['side_scan'])
        return attach(runtime,forward_scale=b['options']['forward_scale'],
            likelihood_tempering=b['options']['likelihood_tempering'],calibration=b['bias_calibration'],servo_stiffness='real_v1')
    return factory


def run(b,out):
    contract.require_execution(b)
    reached=lambda runtime,stage:getattr(runtime,'side_scan_done',False)
    fake_loop=SimpleNamespace(run=frozen.loop.run,stage_reached=reached)
    def writer(p,value):
        if p.name=='result.json':
            value.update(seed=1054,diagnostic_only=True,transport_attempted=False,physical_success=None,
                complete_transport=False,options=b['options'])
        write(p,value)
    return bind(frozen.run,c=contract,runtime_factory=runtime_factory,loop=fake_loop,write=writer)(b,out)


def main():
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('--execute',action='store_true')
    p.add_argument('--expected-source-sha',required=True);p.add_argument('--output',type=Path,required=True)
    p.add_argument('--side-scan',choices=('off','side_scan_v1'),default='off');a=p.parse_args()
    b=contract.bundle(a.expected_source_sha,side_scan=a.side_scan)
    if not a.execute:print(json.dumps(dict(execution_started=False,bundle=b['execution_bundle_id'],options=b['options'])));return
    check_source(a.expected_source_sha);contract.require_execution(b)
    root=Path('/Users/changmin/projects/ugrp/outputs').resolve()
    if not a.output.is_absolute() or not a.output.resolve().is_relative_to(root) or a.output.exists():raise ValueError('new primary output required')
    from scripts import agent_lock
    from harness.zone_pair_highpose_exact_speedups import install
    held=agent_lock.acquire(agent_lock.DEFAULT_ROOT,owner='codex',branch='codex/s2-realism',
        purpose='s2v48 one seed1054 own RGB side scan, no transport',pid=os.getpid(),expected_minutes=15,timing_sensitive=True)
    undo=None
    try:
        _,undo=install('v98-exact-v6');result=run(b,a.output)
        print(json.dumps({k:result.get(k) for k in ('status','failure','check_sim_s','wall_s')}),flush=True)
    finally:
        if undo:undo()
        released=agent_lock.release(agent_lock.DEFAULT_ROOT,owner='codex')
        write(a.output/'lock.json',dict(acquired=held,released=released,status_after=agent_lock.status(agent_lock.DEFAULT_ROOT)))


if __name__=='__main__':main()
