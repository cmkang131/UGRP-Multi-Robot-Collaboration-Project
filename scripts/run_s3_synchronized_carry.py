"""Frozen S3 coarse-base/fine-arm probe, Oracle x86 only, <=60 SIM seconds."""
import argparse
import hashlib
import json
from types import SimpleNamespace
from pathlib import Path

from harness.zone_final_pair_binding import bind
from harness.zone_s3_alignment_ownership import Options, ALL, LIMITS
from dataclasses import asdict
from harness.zone_s3_coarse_fine import OPTION, PARAMS, attach_endpoint, attach_solo
from scripts import run_s3_x86_probe as stage
from harness.zone_s3_synchronized_carry import attach, OPTION as CARRY, PLAN_OPTION, PARAMS as CARRY_PARAMS, joint_plan
from sim.s3_synchronized_carry import PhysicsBackend

BUNDLE_ID = 'zone-s3-synchronized-carry-v164'
WORKFLOW_VERSION = '7.57.0'
WORKFLOW = 'configs/simulation_workflows.d/s3_synchronized_carry_v164.json'


def bundle(sha, case, condition, option='off', cap=60., refinements=Options(), carry="off", pan="off"):
    if carry not in ('off',CARRY) or pan not in ('off',PLAN_OPTION):raise ValueError('unregistered carry/pan option')
    if cap not in (5., 60.):
        raise ValueError('only pathcheck5 or registered60 allowed')
    if option not in ('off', OPTION): raise ValueError('unknown option')
    if refinements.enabled and option!=OPTION:raise ValueError('refinements require coarse-fine owner')
    b = stage.bundle(sha, case, condition=condition)
    b.update(synchronized_carry=dict(option=carry,params=CARRY_PARAMS),joint_pan=pan,execution_bundle_id=BUNDLE_ID, workflow_version=WORKFLOW_VERSION,
        schema='ugrp.s3_synchronized_carry.v164', servo_option=option,
        coarse_fine=dict(option=option,params=PARAMS,refinements=asdict(refinements),limits=LIMITS), physical_supervisor='S3_common_and_cyan_StopGuard_v1', cap_sim_s=cap,
        concurrent_probe_limit=10, stop_after_close=False,
        stage_scope='align-hover-descent-close-lift-carry',
        qualification='DEV coarse/fine tuning; fixed capture constants; no GT control')
    from harness.python_source_closure import source_closure
    paths=set(source_closure(stage.ROOT,['scripts/run_s3_synchronized_carry.py']))
    paths.update((WORKFLOW, 'experiments/2026-10-10-s3-synchronized-carry/README.md',
                  'experiments/2026-10-10-s3-synchronized-carry/batch-plan.json'))
    b['source_sha256'].update({p:hashlib.sha256((stage.ROOT/p).read_bytes()).hexdigest() for p in paths})
    return b


def run(b, out):
    option=b['coarse_fine']['option']
    refinements=Options(**b['coarse_fine']['refinements'])
    def enter(rt, now, ignored):
        eps=stage.previous.enter_pair(rt,now,'off')
        for ep in eps.values():
            attach_endpoint(ep,option,refinements=refinements,planner=joint_plan if b["joint_pan"]!='off' else None)
            attach(ep,b["synchronized_carry"]["option"])
        return eps
    def configure(own, ignored):
        return attach_solo(own,option,refinements=refinements)
    # stage.run rebinds this function's globals; keep a real FunctionType.
    probe_run=bind(stage.previous.run,CAP=b['cap_sim_s'])
    probe_run.__kwdefaults__={**probe_run.__kwdefaults__, 'solo_configure':configure}
    previous=SimpleNamespace(**{**vars(stage.previous), 'enter_pair':enter, 'run':probe_run})
    result=bind(stage.run,previous=previous,StageBackend=PhysicsBackend)(b,out)
    environment=json.loads((out/'environment.json').read_text())
    environment['concurrent_probe_limit']=10
    stage.previous.write(out/'environment.json',environment)
    stage.previous.artifact_manifest(out)
    return result


def main():
    p=argparse.ArgumentParser();p.add_argument('--expected-source-sha',required=True)
    p.add_argument('--output',type=Path,required=True)
    p.add_argument('--condition',type=int,choices=range(6),default=0)
    p.add_argument('--case',choices=('pair','cyan'),default='pair')
    p.add_argument('--path-check',action='store_true')
    p.add_argument('--coarse-fine',choices=('off',OPTION),default='off')
    p.add_argument('--refinements',choices=('off','abc_v1'),default='off')
    p.add_argument('--carry',choices=('off',CARRY),default='off');p.add_argument('--pan',choices=('off',PLAN_OPTION),default='off')
    p.add_argument('--execute',action='store_true');a=p.parse_args()
    if not a.execute:
        print(json.dumps(dict(execution_started=False,bundle_id=BUNDLE_ID,host='oracle-x86')))
        return 0
    stage.archive_guard(a.expected_source_sha,a.output)
    from harness.zone_pair_highpose_exact_speedups import install
    _,undo=install('v98-exact-v6')
    try:
        r=run(bundle(a.expected_source_sha,a.case,a.condition,a.coarse_fine,5. if a.path_check else 60.,ALL if a.refinements=='abc_v1' else Options(),a.carry,a.pan),a.output)
    finally:
        undo()
    print(json.dumps(r));return int(r['status']=='HOST_ERROR')


if __name__=='__main__':raise SystemExit(main())
