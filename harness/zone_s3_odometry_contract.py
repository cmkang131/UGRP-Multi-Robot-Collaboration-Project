"""v150: preregistered fixed-input odometry choice and DEV pre-GO re-wait."""
from harness import zone_s3_sweep_contract as old
from harness.python_source_closure import source_closure
from harness.pulse_rotation_odometry import ASSET, OPTION

ROOT, hp, SEEDS, inputs = old.ROOT, old.hp, old.SEEDS, old.inputs
BUNDLE_ID = 'zone-s3-odometry-v150'
WORKFLOW_VERSION = '7.43.0'
PLAN = 'experiments/2026-10-09-s3-no-prior/s3fix5/registration.json'
WORKFLOW = 'configs/simulation_workflows.d/s3_odometry_v150.json'


def bundle(sha, *, seed=14201, speedups='v98-exact-v6'):
    b=old.bundle(sha,seed=seed,speedups=speedups)
    plan=hp.base.read(ROOT/PLAN)
    mode=plan['pulse_odometry']
    if mode not in ('off',OPTION):
        raise ValueError('saved-input odometry decision not finalized')
    b['controller_config']['options']['pulse_odometry']=mode
    b.update(schema='ugrp.s3_odometry_bundle.v150',execution_bundle_id=BUNDLE_ID,
        workflow_version=WORKFLOW_VERSION,options=b['controller_config']['options'],
        preregistration=plan,parent_bundles=[*b['parent_bundles'],old.BUNDLE_ID],raw_budget_bytes=4*1024**3)
    paths=set(b['source_sha256'])|set(source_closure(ROOT,[
        'harness/zone_s3_odometry_contract.py','scripts/run_s3_odometry.py']))
    paths.update((PLAN,WORKFLOW,str(ASSET.relative_to(ROOT)),
        'tests/test_s3_host_odometry.py','experiments/2026-10-09-s3-no-prior/s3fix5/README.md',
        'experiments/2026-10-09-s3-no-prior/s3fix5/replay-evaluation.json'))
    b['source_sha256']={p:hp.base.sha(ROOT/p) for p in sorted(paths)}
    return b


def verify(value):
    if value!=bundle(value['source_sha'],seed=value['seed'],speedups=value['speedups']):
        raise ValueError('S3 odometry source/config mismatch')
