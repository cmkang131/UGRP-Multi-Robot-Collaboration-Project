"""v87 acquisition contract: v84 plus floor_light_v1, no student admission.

Keep the executed v84 registry, source closure and acquisition schedule intact.
The inherited P03 provider is historical metadata, not a runnable bright-profile
provider. P03 still requires measured calibration and a separately migrated adapter.
"""
from __future__ import annotations

import copy

from harness import zone_final_environment as previous
from harness.zone_final_environment import ROOT, digest, local_path, read, sha
from sim.render_profile import profile_record

REGISTRY = 'configs/zone_final_environment_v87.json'
WORKFLOW = 'configs/simulation_workflows.d/final_environment_v87.json'
BUNDLE_ID = 'zone-final-environment-v87'
CALIBRATION = 'configs/calibration/zone_final_v3_floor_light_contract.json'
RENDER_PROFILE = 'floor_light_v1'


def registry(*, root=ROOT):
    value = read(local_path(REGISTRY, root=root))
    expected = previous.registry(root=root)
    expected.update(schema='ugrp.final_environment.v87', execution_bundle_id=BUNDLE_ID,
                    workflow_id='zone-final-environment-floor-light-check',
                    workflow_version='2.20.0', render_profile=RENDER_PROFILE)
    for row in expected['maps'].values():
        row.update(calibration_contract=CALIBRATION,
                   calibration_contract_sha256=sha(local_path(CALIBRATION, root=root)))
    if value != expected:
        raise ValueError('v87 differs from v84 beyond registered render/version changes')
    return value


def resolve(map_id, *, root=ROOT):
    reg = registry(root=root)
    static, _, old_contract = previous.resolve(map_id, root=root)
    row = reg['maps'][map_id]
    contract = read(local_path(row['calibration_contract'], root=root))
    expected = copy.deepcopy(old_contract)
    expected['render_profile'] = RENDER_PROFILE
    if contract != expected:
        raise ValueError('v87 calibration contract differs beyond render profile')
    return static, row, contract


def bundle(map_id, *, check='p01', root=ROOT):
    from harness.python_source_closure import source_closure
    reg = registry(root=root)
    _, _, contract = resolve(map_id, root=root)
    value = previous.bundle(map_id, check=check, root=root)
    value.update(schema='ugrp.final_environment_bundle.v87', execution_bundle_id=BUNDLE_ID,
                 render_profile=RENDER_PROFILE, calibration_contract=contract,
                 render_profile_contract=profile_record(RENDER_PROFILE),
                 parent_execution_bundle_id=previous.BUNDLE_ID,
                 parent_bundle_sha256=digest(previous.bundle(map_id, check=check, root=root)),
                 workflow_id=reg['workflow_id'], workflow_version=reg['workflow_version'])
    # The P03 factory remains the v84/default-render contract. It is not called
    # by either acquisition runner; do not relabel it as a qualified v87 provider.
    paths = [REGISTRY, WORKFLOW, CALIBRATION,
             'harness/zone_final_environment_floor_light.py',
             'scripts/run_final_environment_floor_light.py',
             'sim/final_environment_floor_light.py', 'sim/render_profile.py']
    files = set(source_closure(root, paths)) | set(paths) | set(value['source_sha256'])
    value['source_sha256'] = {p: sha(local_path(p, root=root)) for p in sorted(files)}
    return value
