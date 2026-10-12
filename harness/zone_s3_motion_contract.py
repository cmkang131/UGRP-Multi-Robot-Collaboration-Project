"""v148: common heading pulse contract and explicit coupled-beam exception."""
import copy
from harness import zone_s3_continue_contract as old
from harness.python_source_closure import source_closure
from harness.zone_s3_coupled_motion import HEADING_EXCEPTIONS

ROOT, hp, SEEDS, inputs = old.ROOT, old.hp, old.SEEDS, old.inputs
BUNDLE_ID = 'zone-s3-motion-v148'
WORKFLOW_VERSION = '7.41.0'
PLAN = 'experiments/2026-10-09-s3-no-prior/s3fix3/registration.json'
WORKFLOW = 'configs/simulation_workflows.d/s3_motion_v148.json'


def bundle(sha, *, seed=14201, speedups='v98-exact-v6'):
    b = old.bundle(sha, seed=seed, speedups=speedups)
    b['controller_config']['options'].update(pair_heading='pair_heading_pulse_v1',
        s3_exact_cache='posterior_content_v1', s3_io='buffered_jsonl_v1')
    plan = hp.base.read(ROOT/PLAN)
    b.update(schema='ugrp.s3_motion_bundle.v148', execution_bundle_id=BUNDLE_ID,
        workflow_version=WORKFLOW_VERSION, options=b['controller_config']['options'],
        preregistration=plan, parent_bundles=[*b['parent_bundles'],old.BUNDLE_ID],
        heading_scope=plan['heading_scope'], heading_exceptions=copy.deepcopy(HEADING_EXCEPTIONS))
    paths = set(b['source_sha256']) | set(source_closure(ROOT, [
        'harness/zone_s3_motion_contract.py','harness/zone_s3_motion_runtime.py',
        'sim/s3_motion_ports.py','scripts/run_s3_motion.py']))
    paths.update((PLAN,WORKFLOW,'experiments/2026-10-09-s3-no-prior/s3fix3/README.md'))
    b['source_sha256'] = {p:hp.base.sha(ROOT/p) for p in sorted(paths)}
    return b


def verify(value):
    if value != bundle(value['source_sha'],seed=value['seed'],speedups=value['speedups']):
        raise ValueError('S3 motion source/config mismatch')
