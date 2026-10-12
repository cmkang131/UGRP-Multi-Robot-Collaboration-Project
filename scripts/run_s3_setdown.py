"""Registered <=60SIM Oracle-only first set-down comparison, v166."""
import argparse,copy,hashlib,json
from pathlib import Path
from types import SimpleNamespace
from harness.zone_final_pair_binding import bind
from harness.python_source_closure import source_closure
from harness.zone_s3_alignment_ownership import ALL,Options
from harness.zone_s3_coarse_fine import OPTION,attach_endpoint,attach_solo
from harness.zone_s3_synchronized_carry import attach as attach_carry,joint_plan,OPTION as CARRY,PLAN_OPTION
from harness.zone_s3_setdown import attach as attach_setdown,OPTIONS,PARAMS
from sim.s3_setdown import PhysicsBackend,LIMITS
from scripts import run_s3_synchronized_start as previous
from scripts import run_s3_x86_probe as stage

BUNDLE_ID='zone-s3-setdown-v166'
WORKFLOW_VERSION='7.59.0'
WORKFLOW='configs/simulation_workflows.d/s3_setdown_v166.json'
PLAN='experiments/2026-10-10-s3-setdown/summary.json'


def bundle(sha,case,condition,option='off'):
    if option not in OPTIONS:raise ValueError('unknown setdown option')
    b=previous.bundle(sha,case,condition,OPTION,60.,ALL,CARRY,PLAN_OPTION)
    b.update(execution_bundle_id=BUNDLE_ID,workflow_version=WORKFLOW_VERSION,
        schema='ugrp.s3_setdown.v166',stage_scope='align-lift-carry-first-setdown-release',
        setdown=dict(option=option,params=copy.deepcopy(PARAMS),eval_supervisor='legacy' if option=='off' else 'supported_lower_v1',eval_limits=LIMITS))
    paths=set(source_closure(stage.ROOT,['scripts/run_s3_setdown.py','scripts/run_s3_setdown_cohort.py','scripts/evaluate_s3_setdown.py','scripts/diagnose_s3_setdown.py']))|{WORKFLOW,PLAN}
    b['source_sha256'].update({p:hashlib.sha256((stage.ROOT/p).read_bytes()).hexdigest() for p in paths})
    return b


def run(b,out):
    eps={}
    def backend(*args,**kwargs):
        host=PhysicsBackend(*args,**kwargs)
        host.states_getter=lambda:{r:ep.controller.state for r,ep in eps.items()}
        return host
    def enter(rt,now,ignored):
        eps.update(stage.previous.enter_pair(rt,now,'off'))
        for ep in eps.values():
            attach_endpoint(ep,OPTION,refinements=ALL,planner=joint_plan)
            attach_carry(ep,CARRY);attach_setdown(ep,b['setdown']['option'])
            ctl=ep.controller;old=ctl._cp_open
            def cp_open(now,idle,ctl=ctl,old=old):
                value=old(now,idle)
                if idle and not ctl.failure and ctl._issued().get(1)==2000:
                    ctl.s3_first_release_complete=True
                return value
            ctl._cp_open=cp_open
        return eps
    def stop():return bool(eps) and all(getattr(ep.controller,'s3_first_release_complete',False) for ep in eps.values())
    probe=bind(stage.previous.run,CAP=b['cap_sim_s'])
    probe.__kwdefaults__={**probe.__kwdefaults__,'solo_configure':lambda own,_:attach_solo(own,OPTION,refinements=ALL),'stop_when':stop}
    ns=SimpleNamespace(**{**vars(stage.previous),'enter_pair':enter,'run':probe})
    result=bind(stage.run,previous=ns,StageBackend=backend)(b,out)
    if 'DEV_INITIAL_CHECK_STOP' in result.get('failure',''):result['status']='EARLY_STOP'
    stage.previous.write(out/'result.json',result);stage.previous.artifact_manifest(out)
    return result


def main():
    p=argparse.ArgumentParser();p.add_argument('--expected-source-sha',required=True);p.add_argument('--output',type=Path,required=True)
    p.add_argument('--case',choices=('pair','cyan'),default='pair');p.add_argument('--condition',type=int,choices=range(6),default=0)
    p.add_argument('--setdown',choices=OPTIONS,default='off');p.add_argument('--execute',action='store_true');a=p.parse_args()
    if not a.execute:print(json.dumps(dict(execution_started=False,bundle_id=BUNDLE_ID,host='oracle-x86')));return 0
    stage.archive_guard(a.expected_source_sha,a.output)
    from harness.zone_pair_highpose_exact_speedups import install
    _,undo=install('v98-exact-v6')
    try:r=run(bundle(a.expected_source_sha,a.case,a.condition,a.setdown),a.output)
    finally:undo()
    print(json.dumps(r));return int(r['status'] in ('HOST_ERROR','EARLY_STOP'))

if __name__=='__main__':raise SystemExit(main())
