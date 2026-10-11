"""Finite v147 DEV continuation; v146 contract and source remain intact."""
from harness import zone_s3_host_heading_contract as old
from harness.python_source_closure import source_closure

ROOT, hp, SEEDS = old.ROOT, old.hp, old.SEEDS
BUNDLE_ID = 'zone-s3-continue-v147'
WORKFLOW_VERSION = '7.40.0'
PLAN = 'experiments/2026-10-09-s3-no-prior/s3fix/registration.json'
WORKFLOW = 'configs/simulation_workflows.d/s3_continue_v147.json'
inputs = old.inputs


def bundle(sha, *, seed=14201, speedups='v98-exact-v6'):
    b = old.bundle(sha, seed=seed, speedups=speedups)
    b['controller_config']['options'].update(s3_dev_light='continue_estimate_v1',
        global_diversity='kld_augmented_v2', mode_head_look='mode_information_v1')
    b.update(schema='ugrp.s3_continue_bundle.v147', execution_bundle_id=BUNDLE_ID,
        workflow_version=WORKFLOW_VERSION, options=b['controller_config']['options'],
        preregistration=hp.base.read(ROOT/PLAN), raw_budget_bytes=3*1024**3,
        parent_bundles=[*b['parent_bundles'], old.BUNDLE_ID], particle_recovery_changed=True)
    paths = set(b['source_sha256']) | set(source_closure(ROOT, [
        'harness/zone_s3_continue_contract.py', 'harness/zone_s3_continue.py',
        'scripts/run_s3_continue.py']))
    paths.update((PLAN, WORKFLOW, 'experiments/2026-10-09-s3-no-prior/s3fix/README.md'))
    b['source_sha256'] = {p: hp.base.sha(ROOT/p) for p in sorted(paths)}
    return b


def verify(value):
    if value != bundle(value['source_sha'], seed=value['seed'], speedups=value['speedups']):
        raise ValueError('S3 continuation source/config mismatch')
