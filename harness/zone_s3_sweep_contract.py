"""v149: offline stage admission, matched GO handoff and exact snapshot cache."""
from harness import zone_s3_motion_contract as old
from harness.python_source_closure import source_closure

ROOT, hp, SEEDS, inputs = old.ROOT, old.hp, old.SEEDS, old.inputs
BUNDLE_ID = 'zone-s3-sweep-v149'
WORKFLOW_VERSION = '7.42.0'
PLAN = 'experiments/2026-10-09-s3-no-prior/s3fix4/registration.json'
WORKFLOW = 'configs/simulation_workflows.d/s3_sweep_v149.json'


def bundle(sha, *, seed=14201, speedups='v98-exact-v6'):
    b=old.bundle(sha,seed=seed,speedups=speedups)
    b['controller_config']['options']['s3_exact_cache']='posterior_content_v2'
    b.update(schema='ugrp.s3_sweep_bundle.v149',execution_bundle_id=BUNDLE_ID,
        workflow_version=WORKFLOW_VERSION,options=b['controller_config']['options'],
        preregistration=hp.base.read(ROOT/PLAN),parent_bundles=[*b['parent_bundles'],old.BUNDLE_ID])
    paths=set(b['source_sha256'])|set(source_closure(ROOT,[
        'harness/zone_s3_sweep_contract.py','scripts/run_s3_sweep.py']))
    paths.update((PLAN,WORKFLOW,'tests/s3_stage_probe.py','tests/test_s3_stage_sweep.py',
        'experiments/2026-10-09-s3-no-prior/s3fix4/README.md'))
    b['source_sha256']={p:hp.base.sha(ROOT/p) for p in sorted(paths)}
    return b


def verify(value):
    if value!=bundle(value['source_sha'],seed=value['seed'],speedups=value['speedups']):
        raise ValueError('S3 stage sweep source/config mismatch')
