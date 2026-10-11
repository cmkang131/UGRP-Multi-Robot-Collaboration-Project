"""v151: preregistered saved-input consistency decision and finite DEV poses."""
from harness import zone_s3_odometry_contract as old
from harness.python_source_closure import source_closure
from harness.pf_observation_consistency import OPTIONS, ALPHA_ASSET

ROOT, hp, SEEDS, inputs = old.ROOT, old.hp, old.SEEDS, old.inputs
BUNDLE_ID = 'zone-s3-consistency-v151'
WORKFLOW_VERSION = '7.44.0'
PLAN = 'experiments/2026-10-09-s3-no-prior/s3fix6/registration.json'
WORKFLOW = 'configs/simulation_workflows.d/s3_consistency_v151.json'
DECISION = 'experiments/2026-10-09-s3-no-prior/s3fix6/comparison.json'


def bundle(sha, *, seed=14201, speedups='v98-exact-v6'):
    b = old.bundle(sha, seed=seed, speedups=speedups)
    plan = hp.base.read(ROOT/PLAN)
    decision = hp.base.read(ROOT/DECISION)
    option = plan['observation_consistency']
    if (option not in OPTIONS or option != decision['smoke_option']
            or hp.base.sha(ROOT/DECISION) != plan['replay_selection_sha256']):
        raise ValueError('saved-input consistency decision is not sealed')
    for path, digest in decision['runtime_source_sha256'].items():
        if hp.base.sha(ROOT/path) != digest:
            raise ValueError('saved-input runtime source changed: '+path)
    if hp.base.sha(ALPHA_ASSET) != plan['observation_consistency_calibration']['sha256']:
        raise ValueError('independent motion calibration changed')
    b['controller_config']['options'].update(observation_consistency=option,
        pose_validity=plan['pose_validity'])
    b.update(schema='ugrp.s3_consistency_bundle.v151', execution_bundle_id=BUNDLE_ID,
        workflow_version=WORKFLOW_VERSION, options=b['controller_config']['options'],
        preregistration=plan, parent_bundles=[*b['parent_bundles'],old.BUNDLE_ID])
    paths=set(b['source_sha256'])|set(source_closure(ROOT,[
        'harness/zone_s3_consistency_contract.py','scripts/run_s3_consistency.py']))
    paths.update((PLAN, WORKFLOW, DECISION, str(ALPHA_ASSET.relative_to(ROOT)),
        'tests/test_s3_host_consistency.py','tests/test_s3_stage_sweep.py',
        'experiments/2026-10-09-s3-no-prior/s3fix6/README.md'))
    b['source_sha256']={p:hp.base.sha(ROOT/p) for p in sorted(paths)}
    return b


def verify(value):
    if value != bundle(value['source_sha'],seed=value['seed'],speedups=value['speedups']):
        raise ValueError('S3 consistency source/config mismatch')
