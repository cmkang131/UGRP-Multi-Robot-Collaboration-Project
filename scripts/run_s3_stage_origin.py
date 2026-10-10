"""v170: isolate the reconstructed-stage/public-route entrance contract."""
import argparse
import hashlib
from pathlib import Path
from types import SimpleNamespace

from harness.python_source_closure import source_closure
from harness.zone_final_pair_binding import bind
from harness.zone_s3_host import pair_task
from sim.s3_stage_origin import OPTION, initialize
from scripts import run_s3_integer_carry as previous

BUNDLE_ID = 'zone-s3-stage-origin-v170'
WORKFLOW_VERSION = '7.63.0'
WORKFLOW = 'configs/simulation_workflows.d/s3_stage_origin_v170.json'
PLAN = 'experiments/2026-10-11-s3-stage-origin/registration.json'
ROUTE_RETRY = 'experiments/2026-10-11-s3-stage-origin/route-retry.json'
ROOT = previous.previous.stage.ROOT


def public_start(b):
    if 'registered_route' in b:
        return list(b['registered_route'][0])
    contract = previous.previous.stage.previous.parent
    static = contract.hp.resolve(b['map_id'])[0]
    order = next(o for o in contract.inputs()[2]['orders'] if o['kind'] == 'long_beam')
    task = pair_task(static, order)
    from harness import zone_final_pair_skill as skill
    planner = bind(skill.make_plan, task=lambda _: task)
    return planner(static, task['sheet'], task['target'])['route'][0]


def bundle(sha, case, condition, option='off', route_case='single'):
    if option not in ('off', OPTION):
        raise ValueError('unregistered stage origin option')
    b = previous.bundle(sha, case, condition, 'integer_ticks_v1', route_case)
    b.update(execution_bundle_id=BUNDLE_ID, workflow_version=WORKFLOW_VERSION,
        schema='ugrp.s3_stage_origin.v170',
        stage_origin=dict(option=option, public_start_xy_m=public_start(b),
            scope='synthetic probe setup only; not live mission localization',
            runtime_truth_feedback=False, controller_pose_prior=False),
        parent_bundles=[*b['parent_bundles'], previous.BUNDLE_ID])
    paths = set(source_closure(ROOT, ['scripts/run_s3_stage_origin.py',
        'scripts/run_s3_stage_origin_cohort.py', 'scripts/evaluate_s3_stage_origin.py'])) | {WORKFLOW, PLAN}
    if route_case != 'single':
        b['route_binding'] = 'captured_own_link_callback_v1'
        paths.add(ROUTE_RETRY)
    b['source_sha256'].update({p: hashlib.sha256((ROOT/p).read_bytes()).hexdigest() for p in paths})
    return b


def run(b, out):
    # Private function binding keeps the registered v167/default-off path intact.
    stage = previous.previous.stage
    def setup(case, condition):
        return initialize(stage.varied_setup(case, condition), case,
            b['stage_origin']['public_start_xy_m'], b['stage_origin']['option'])
    stage_ns = SimpleNamespace(**{**vars(stage), 'run': bind(stage.run, varied_setup=setup)})
    old_ns = SimpleNamespace(**{**vars(previous.previous), 'stage': stage_ns})
    return bind(previous.run, previous=old_ns)(b, out)


def main():
    p = argparse.ArgumentParser()
    p.add_argument('--expected-source-sha', required=True)
    p.add_argument('--output', type=Path, required=True)
    p.add_argument('--case', choices=('pair', 'cyan'), default='pair')
    p.add_argument('--condition', type=int, choices=range(6), default=0)
    p.add_argument('--stage-origin', choices=('off', OPTION), default='off')
    p.add_argument('--route-case', choices=('single', 'multi-left', 'multi-right', 'multi-three'), default='single')
    p.add_argument('--execute', action='store_true')
    a = p.parse_args()
    if not a.execute:
        print(BUNDLE_ID)
        return 0
    previous.previous.stage.archive_guard(a.expected_source_sha, a.output)
    from harness.zone_pair_highpose_exact_speedups import install
    _, undo = install('v98-exact-v6')
    try:
        r = run(bundle(a.expected_source_sha, a.case, a.condition, a.stage_origin, a.route_case), a.output)
    finally:
        undo()
    print(r)
    return int(r['status'] in ('HOST_ERROR', 'EARLY_STOP'))


if __name__ == '__main__':
    raise SystemExit(main())
