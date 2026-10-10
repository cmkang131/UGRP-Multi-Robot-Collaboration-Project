"""v175: unbroken registered routes, canonical inspection and RGB backoff."""
import argparse
import hashlib
from pathlib import Path
from dataclasses import asdict
from harness.python_source_closure import source_closure
from harness.zone_final_pair_binding import bind
from harness.zone_s3_reacquire import CANDIDATES, attach
from scripts import run_s3_route_resume as previous

BUNDLE_ID = 'zone-s3-full-route-v175'
WORKFLOW_VERSION = '7.68.0'
WORKFLOW = 'configs/simulation_workflows.d/s3_full_route_v175.json'
PLAN = 'experiments/2026-10-11-s3-full-route/registration.json'
ROOT = previous.ROOT


def bundle(sha, condition, route_case, seed, candidate='baseline'):
    options = CANDIDATES[candidate]
    b = previous.bundle(sha, condition, route_case, seed, 'combined')
    legs = len(b['registered_route'])-1
    b.update(execution_bundle_id=BUNDLE_ID, workflow_version=WORKFLOW_VERSION,
        schema='ugrp.s3_full_route.v175', cap_sim_s=legs*70.+30.,
        case_cap_s=legs*70.+30., wall_cap_s=3600.,
        reacquire=dict(candidate=candidate, options=asdict(options), runtime_gt=False),
        parent_bundles=[*b['parent_bundles'], previous.BUNDLE_ID])
    paths = set(source_closure(ROOT, ['scripts/run_s3_full_route.py',
        'scripts/run_s3_full_route_cohort.py','scripts/evaluate_s3_full_route.py'])) | {WORKFLOW, PLAN}
    b['source_sha256'].update({p:hashlib.sha256((ROOT/p).read_bytes()).hexdigest() for p in paths})
    return b


def run(b, out):
    audits = {}
    def configure(ep, *args, **kwargs):
        result = attach(previous.attach(ep,*args,**kwargs), CANDIDATES[b['reacquire']['candidate']])
        if hasattr(ep.controller,'s3_reacquire'):
            audits[ep.own.robot_id] = ep.controller.s3_reacquire
        return result
    result = bind(previous.run, attach=configure)(b,out)
    writer = previous.previous.previous.previous.stage.previous
    writer.write(out/'reacquire.json',audits)
    writer.write(out/'result.json',result)
    writer.artifact_manifest(out)
    return result


def main():
    p=argparse.ArgumentParser()
    p.add_argument('--expected-source-sha',required=True)
    p.add_argument('--output',type=Path,required=True)
    p.add_argument('--condition',type=int,choices=(0,3,5),required=True)
    p.add_argument('--route-case',choices=('multi-left','multi-right','multi-three'),required=True)
    p.add_argument('--seed',type=int,required=True)
    p.add_argument('--candidate',choices=tuple(CANDIDATES),default='baseline')
    p.add_argument('--execute',action='store_true')
    a=p.parse_args()
    if not a.execute:
        print(BUNDLE_ID);return 0
    previous.previous.previous.previous.stage.archive_guard(a.expected_source_sha,a.output)
    from harness.zone_pair_highpose_exact_speedups import install
    _,undo=install('v98-exact-v6')
    try:r=run(bundle(a.expected_source_sha,a.condition,a.route_case,a.seed,a.candidate),a.output)
    finally:undo()
    print(r)
    return int(r['status'] in ('HOST_ERROR','EARLY_STOP'))


if __name__=='__main__':raise SystemExit(main())
