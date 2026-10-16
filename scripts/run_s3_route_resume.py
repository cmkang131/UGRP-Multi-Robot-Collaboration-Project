"""v172: frozen DEV multi-route completion/inspect candidates on Oracle x86."""
import argparse
import hashlib
from pathlib import Path
from types import SimpleNamespace
from harness.python_source_closure import source_closure
from harness.zone_final_pair_binding import bind
from harness.zone_s3_route_resume import CANDIDATES, attach, release_completes_probe
from scripts import run_s3_stage_origin as previous

BUNDLE_ID = 'zone-s3-route-resume-v172'
WORKFLOW_VERSION = '7.65.0'
WORKFLOW = 'configs/simulation_workflows.d/s3_route_resume_v172.json'
PLAN = 'experiments/2026-10-11-s3-route-resume/registration.json'
ROOT = previous.ROOT


def bundle(sha, condition, route_case, seed, candidate='baseline'):
    if candidate not in CANDIDATES or route_case == 'single':
        raise ValueError('registered multi-route candidate required')
    if seed not in (14201+condition, 15201+condition):
        raise ValueError('two preregistered seeds only')
    b = previous.bundle(sha, 'pair', condition, 'public_stage_origin_v1', route_case)
    from dataclasses import asdict
    b.update(execution_bundle_id=BUNDLE_ID, workflow_version=WORKFLOW_VERSION,
        schema='ugrp.s3_route_resume.v172', seed=seed,
        provider_seeds={r:seed+i for i,r in enumerate(('r1','r2','r3'))},
        route_resume=dict(candidate=candidate, options=asdict(CANDIDATES[candidate]),
            runtime_gt=False), parent_bundles=[*b['parent_bundles'], previous.BUNDLE_ID])
    paths = set(source_closure(ROOT, ['scripts/run_s3_route_resume.py',
        'scripts/run_s3_route_resume_cohort.py', 'scripts/evaluate_s3_route_resume.py'])) | {WORKFLOW, PLAN}
    b['source_sha256'].update({p:hashlib.sha256((ROOT/p).read_bytes()).hexdigest() for p in paths})
    return b


def run(b, out):
    options = CANDIDATES[b['route_resume']['candidate']]
    integer = previous.previous
    audits = {}
    def configure(ep, *args, **kwargs):
        result = attach(integer.attach_endpoint(ep, *args, **kwargs), options)
        if hasattr(ep.controller, 's3_route_resume'):
            audits[ep.own.robot_id] = ep.controller.s3_route_resume
        return result
    dependencies = dict(attach_endpoint=configure)
    if options.final_release_only:
        dependencies['release_completes_probe'] = release_completes_probe
    private = SimpleNamespace(**{**vars(integer), 'run':bind(integer.run, **dependencies)})
    result = bind(previous.run, previous=private)(b, out)
    if options.final_release_only and result.get('stage_end') == 'first_setdown_release_commanded':
        result['stage_end'] = 'final_route_release_commanded'
    previous.previous.previous.stage.previous.write(out/'route-resume.json', audits)
    previous.previous.previous.stage.previous.write(out/'result.json', result)
    previous.previous.previous.stage.previous.artifact_manifest(out)
    return result


def main():
    p = argparse.ArgumentParser()
    p.add_argument('--expected-source-sha', required=True)
    p.add_argument('--output', type=Path, required=True)
    p.add_argument('--condition', type=int, choices=(0,3,5), required=True)
    p.add_argument('--route-case', choices=('multi-left','multi-right','multi-three'), required=True)
    p.add_argument('--seed', type=int, required=True)
    p.add_argument('--candidate', choices=tuple(CANDIDATES), default='baseline')
    p.add_argument('--execute', action='store_true')
    a = p.parse_args()
    if not a.execute:
        print(BUNDLE_ID)
        return 0
    previous.previous.previous.stage.archive_guard(a.expected_source_sha, a.output)
    from harness.zone_pair_highpose_exact_speedups import install
    _, undo = install('v98-exact-v6')
    try:
        r = run(bundle(a.expected_source_sha,a.condition,a.route_case,a.seed,a.candidate), a.output)
    finally:
        undo()
    print(r)
    return int(r['status'] in ('HOST_ERROR','EARLY_STOP'))


if __name__ == '__main__':
    raise SystemExit(main())
