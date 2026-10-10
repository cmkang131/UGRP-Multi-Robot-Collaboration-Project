"""v177: release epochs, expanded fresh-look backoff, visual checkpoint plan."""
import argparse
import hashlib
from pathlib import Path
from types import SimpleNamespace
from harness.python_source_closure import source_closure
from harness.zone_final_pair_binding import bind
from harness.zone_s3_checkpoint_correction import attach as attach_visual
from harness.zone_s3_reacquire_expanded import attach as attach_reacquire, Options
from sim.s3_release_epoch import PhysicsBackend
from scripts import run_s3_full_route as previous

BUNDLE_ID='zone-s3-checkpoint-correction-v177'
WORKFLOW_VERSION='7.70.0'
WORKFLOW='configs/simulation_workflows.d/s3_checkpoint_correction_v177.json'
PLAN='experiments/2026-10-11-s3-checkpoint-correction/registration.json'
ROOT=previous.ROOT
CANDIDATES=dict(baseline=dict(release_epoch=False,expanded_backoff=False,visual_checkpoint=False),
    recovery=dict(release_epoch=True,expanded_backoff=True,visual_checkpoint=False),
    visual=dict(release_epoch=True,expanded_backoff=True,visual_checkpoint=True))


def bundle(sha,condition,route_case,seed,candidate='baseline'):
    options=CANDIDATES[candidate]
    b=previous.bundle(sha,condition,route_case,seed,'pan_backoff')
    b.update(execution_bundle_id=BUNDLE_ID,workflow_version=WORKFLOW_VERSION,
        schema='ugrp.s3_checkpoint_correction.v177',cap_sim_s=240.,case_cap_s=240.,wall_cap_s=3600.,
        checkpoint_correction=dict(candidate=candidate,options=dict(options),runtime_gt=False,
            initial_reference='public synthetic route entrance + first own RGB; no robot dock prior',
            side_pulse_transfer='fixed first-order v7 calibration; not a new measured fit'),
        parent_bundles=[*b['parent_bundles'],previous.BUNDLE_ID])
    paths=set(source_closure(ROOT,['scripts/run_s3_checkpoint_correction.py',
        'scripts/run_s3_checkpoint_correction_cohort.py','scripts/evaluate_s3_checkpoint_correction.py']))|{WORKFLOW,PLAN}
    retry='experiments/2026-10-11-s3-checkpoint-correction/retry2.json'
    if (ROOT/retry).exists():paths.add(retry)
    b['source_sha256'].update({p:hashlib.sha256((ROOT/p).read_bytes()).hexdigest() for p in paths})
    return b


def run(b,out):
    options=b['checkpoint_correction']['options'];bus={};audits={}
    # The existing private runner injection is preserved at each dependency.
    resume=previous.previous;origin=resume.previous;integer=origin.previous
    private_integer=SimpleNamespace(**{**vars(integer),'run':bind(integer.run,PhysicsBackend=PhysicsBackend)})
    private_origin=SimpleNamespace(**{**vars(origin),'previous':private_integer,
        'run':bind(origin.run,previous=private_integer)})
    private_resume=SimpleNamespace(**{**vars(resume),'previous':private_origin,
        'run':bind(resume.run,previous=private_origin)})
    def configured(ep,ignored):
        result=attach_reacquire(ep,Options(True,True,options['expanded_backoff']))
        result=attach_visual(result,options['visual_checkpoint'],bus=bus,motion=b['controller_config']['motion_model'])
        audits[ep.own.robot_id]=dict(reacquire=ep.controller.s3_reacquire,
            visual=getattr(ep.controller,'s3_checkpoint_correction',{}))
        return result
    result=bind(previous.run,previous=private_resume,attach=configured)(b,out)
    writer=integer.previous.stage.previous
    writer.write(out/'checkpoint-correction.json',dict(options=options,robots=audits,command_plan_bus=bus))
    writer.write(out/'result.json',result);writer.artifact_manifest(out)
    return result


def main():
    p=argparse.ArgumentParser();p.add_argument('--expected-source-sha',required=True)
    p.add_argument('--output',type=Path,required=True);p.add_argument('--condition',type=int,choices=(0,3,5),required=True)
    p.add_argument('--route-case',choices=('multi-left','multi-right','multi-three'),required=True)
    p.add_argument('--seed',type=int,required=True);p.add_argument('--candidate',choices=tuple(CANDIDATES),default='baseline')
    p.add_argument('--execute',action='store_true');a=p.parse_args()
    if not a.execute:print(BUNDLE_ID);return 0
    previous.previous.previous.previous.previous.stage.archive_guard(a.expected_source_sha,a.output)
    from harness.zone_pair_highpose_exact_speedups import install
    _,undo=install('v98-exact-v6')
    try:r=run(bundle(a.expected_source_sha,a.condition,a.route_case,a.seed,a.candidate),a.output)
    finally:undo()
    print(r);return int(r['status'] in ('HOST_ERROR','EARLY_STOP'))


if __name__=='__main__':raise SystemExit(main())
