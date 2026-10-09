"""Separate opt-in bundle; never reseal the v107/off execution contract."""
from harness import zone_s3_contract as parent
from harness.zone_s3_door_yield import PROFILE, specification
from harness.python_source_closure import source_closure

BUNDLE_ID = 'zone-s3-door-yield-v108'
WORKFLOW_VERSION = '3.15.0'
README = 'experiments/2026-10-06-s3-door-yield/README.md'


def bundle(source_sha, *, seed=601, speedups='v98-exact-v6'):
    value = parent.bundle(source_sha, seed=seed, speedups=speedups)
    value.update(schema='ugrp.s3_door_yield_bundle.v108', execution_bundle_id=BUNDLE_ID,
                 workflow_version=WORKFLOW_VERSION, check='s3-door-yield-dev',
                 door_yield=PROFILE, door_protocol=specification())
    value['parent_bundles'] = [parent.BUNDLE_ID, *value['parent_bundles']]
    value['inter_robot_channels'] = [*value['inter_robot_channels'], PROFILE]
    paths = set(value['source_sha256']) | set(source_closure(parent.ROOT, [
        'harness/zone_s3_door_contract.py', 'scripts/run_s3_door_yield.py'])) | {README}
    value['source_sha256'] = {p: parent.hp.base.sha(parent.ROOT/p) for p in sorted(paths)}
    return value


def verify(value):
    expected = bundle(value['source_sha'], seed=value['seed'], speedups=value['speedups'])
    if parent.hp.base.digest(value) != parent.hp.base.digest(expected):
        raise ValueError('S3 door bundle/source/config mismatch')
