"""v152: bounded door leases, own-RGB local servo, preregistered PF choice."""
from harness import zone_s3_odometry_contract as old
from harness.python_source_closure import source_closure
from harness.pf_resampling_diversity import OPTIONS

ROOT, hp, SEEDS, inputs = old.ROOT, old.hp, old.SEEDS, old.inputs
BUNDLE_ID = 'zone-s3-recovery-v152'
WORKFLOW_VERSION = '7.45.0'
PLAN = 'experiments/2026-10-09-s3-no-prior/s3fix7/registration.json'
WORKFLOW = 'configs/simulation_workflows.d/s3_recovery_v152.json'
DECISION = 'experiments/2026-10-09-s3-no-prior/s3fix7/comparison.json'


def bundle(sha, *, seed=14201, speedups='v98-exact-v6'):
    b=old.bundle(sha,seed=seed,speedups=speedups)
    plan=hp.base.read(ROOT/PLAN)
    decision=hp.base.read(ROOT/DECISION)
    option=plan['resampling_diversity']
    if (option not in OPTIONS or option!=decision['smoke_option']
            or hp.base.sha(ROOT/DECISION)!=plan['replay_selection_sha256']):
        raise ValueError('saved-input PF diversity decision is not sealed')
    for path,digest in decision['runtime_source_sha256'].items():
        if hp.base.sha(ROOT/path)!=digest:
            raise ValueError('saved-input PF consumer changed: '+path)
    if plan['door_lease']!='door_lease_v2' or plan['visual_alignment']!='own_rgb_align_v1':
        raise ValueError('unregistered S3 integration choice')
    b['controller_config']['options'].update(resampling_diversity=option,
        door_lease=plan['door_lease'],visual_alignment=plan['visual_alignment'],
        observation_consistency='off',pose_validity='defer_unmeasured_v1')
    b.update(schema='ugrp.s3_recovery_bundle.v152',execution_bundle_id=BUNDLE_ID,
        workflow_version=WORKFLOW_VERSION,options=b['controller_config']['options'],
        preregistration=plan,parent_bundles=[*b['parent_bundles'],old.BUNDLE_ID,
            'zone-s3-consistency-v151'])
    paths=set(b['source_sha256'])|set(source_closure(ROOT,[
        'harness/zone_s3_recovery_contract.py','scripts/run_s3_recovery.py']))
    paths.update((PLAN,WORKFLOW,DECISION,'tests/test_s3_recovery.py',
        'tests/test_s3_stage_sweep.py','experiments/2026-10-09-s3-no-prior/s3fix7/README.md'))
    b['source_sha256']={p:hp.base.sha(ROOT/p) for p in sorted(paths)}
    return b


def verify(value):
    if value!=bundle(value['source_sha'],seed=value['seed'],speedups=value['speedups']):
        raise ValueError('S3 recovery source/config mismatch')
