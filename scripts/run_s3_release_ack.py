"""v187: paired release-ack on/off over the unchanged v186 distance diagnostic."""
import argparse
import hashlib
import json
import platform
from pathlib import Path
from types import SimpleNamespace

from harness.zone_final_pair_binding import bind
from harness.zone_s3_release_ack import attach, OPTION
from harness.python_source_closure import source_closure
from scripts import run_s3_continuous_distance as base

ROOT = base.ROOT
BUNDLE_ID = 'zone-s3-release-ack-v187'
WORKFLOW_VERSION = '7.80.0'
PLAN = 'experiments/2026-10-11-s3-release-ack/registration.json'
WORKFLOW = 'configs/simulation_workflows.d/s3_release_ack_v187.json'


def bundle(sha, distance, seed, option='off'):
    if option not in ('off', OPTION):
        raise ValueError('unregistered release ack option')
    plan = json.loads((ROOT/PLAN).read_text())
    if not any((r['distance_m'], r['seed'], r['option']) == (distance, seed, option)
               for r in plan['runs']):
        raise ValueError('unregistered distance/seed/option')
    b = base.bundle(sha, distance, seed)
    b.update(schema='ugrp.s3_release_ack.v187', execution_bundle_id=BUNDLE_ID,
        workflow_version=WORKFLOW_VERSION, release_ack=dict(option=option, runtime_gt=False))
    paths = set(source_closure(ROOT, ['scripts/run_s3_release_ack.py',
        'scripts/run_s3_release_ack_cohort.py'])) | {PLAN, WORKFLOW}
    b['source_sha256'].update({p: hashlib.sha256((ROOT/p).read_bytes()).hexdigest() for p in paths})
    return b


def run(b, out):
    endpoints = {}
    def configure(ep, *args, **kwargs):
        ep = attach(base.previous.attach_endpoint(ep, *args, **kwargs), b['release_ack']['option'])
        endpoints[ep.own.robot_id] = ep
        return ep
    parent = SimpleNamespace(**{**vars(base.previous), 'attach_endpoint': configure})
    result = bind(base.run, previous=parent)(b, out)
    writer = base.previous.previous.stage.previous
    writer.write(out/'release-ack.json', {r: getattr(ep.controller, 's3_release_ack',
        dict(option='off', audit=[])) for r, ep in endpoints.items()})
    writer.artifact_manifest(out)
    return result


def main():
    p = argparse.ArgumentParser()
    p.add_argument('--expected-source-sha', required=True)
    p.add_argument('--output', type=Path, required=True)
    p.add_argument('--distance', type=float, required=True)
    p.add_argument('--seed', type=int, required=True)
    p.add_argument('--release-ack', choices=('off', OPTION), default='off')
    p.add_argument('--execute', action='store_true')
    a = p.parse_args()
    if not a.execute:
        print(BUNDLE_ID)
        return 0
    base.previous.previous.stage.archive_guard(a.expected_source_sha, a.output)
    if platform.node() != 'ugrp-sim-azure':
        raise ValueError('registered running Azure host required')
    from harness.zone_pair_highpose_exact_speedups import install
    _, undo = install('v98-exact-v6')
    try:
        result = run(bundle(a.expected_source_sha, a.distance, a.seed, a.release_ack), a.output)
    finally:
        undo()
    print(json.dumps(result))
    return int(result['status'] in ('HOST_ERROR', 'EARLY_STOP'))


if __name__ == '__main__':
    raise SystemExit(main())
