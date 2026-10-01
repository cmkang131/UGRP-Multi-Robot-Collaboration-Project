"""Registered v90 held-out acquisition; v88 commands and safety are reused.

This is teacher-only validation data, never calibration training or student
acceptance. The frozen consumer criterion and its validator are not rewritten.
"""
from harness import zone_final_pair_contract as previous
from harness.zone_final_pair_excitation import design as training_design, MAP_ID

BUNDLE_ID = 'zone-final-pair-v90'
REGISTRY = 'configs/zone_final_pair_v90.json'
WORKFLOW = 'configs/simulation_workflows.d/final_pair_v90.json'
WORKFLOW_ID = 'zone-final-pair-heldout-v90'
WORKFLOW_VERSION = '3.2.0'
CHECK = 'calibration-unloaded'
MAPS = ('zone_wide_door_geometry_v3', 'zone_wide_corridor_final_v3')
SEED = 911
ROLE = {'collection_role': 'HELD_OUT_VALIDATION', 'training_eligible': False,
        'teacher_only': True}


def selected(check, map_id):
    return check == CHECK and map_id in MAPS


def registry():
    value = previous.base.read(previous.ROOT / REGISTRY)
    expected = {'schema': 'ugrp.final_pair_heldout.v90', 'execution_bundle_id': BUNDLE_ID,
        'status': 'DRAFT_UNSEALED', 'workflow_id': WORKFLOW_ID,
        'workflow_version': WORKFLOW_VERSION, 'check': CHECK, 'maps': list(MAPS),
        'seed': SEED, **ROLE, 'training_map': MAP_ID,
        'schedule_source': 'zone-final-pair-v88', 'robot_model': 'masterpi_v3',
        'render_profile': 'floor_light_v1', 'contact_profile': 'cargo_noslip_v1',
        'weld': 'off', 'sensors': {'ultrasonic_front': 'off'}}
    if value != expected:
        raise ValueError('v90 held-out registry differs from the registered collection')
    return value


def design(check, map_id):
    if not selected(check, map_id):
        raise ValueError('v90 requires unloaded collection on a registered held-out map')
    registry()
    return {**training_design(check), 'map_id': map_id}


def record(bundle):
    return dict(ROLE) if bundle['execution_bundle_id'] == BUNDLE_ID else {}


def require_seed(bundle, seed):
    if bundle['execution_bundle_id'] == BUNDLE_ID and seed != SEED:
        raise ValueError('v90 held-out collection requires seed 911')


def validate_bundle(bundle):
    reg = registry()
    design(bundle['check'], bundle['map_id'])
    static = previous.resolve(bundle['map_id'])[0]
    for key in ('execution_bundle_id', 'check', 'seed', *ROLE, 'robot_model',
                'render_profile', 'contact_profile', 'weld', 'sensors',
                'workflow_id', 'workflow_version'):
        if bundle.get(key) != reg[key]:
            raise ValueError(f'v90 held-out collection mismatch: {key}')
    if (bundle.get('map_sha256') != previous.base.digest(static)
            or bundle.get('timing') != previous.execution_timing(CHECK)):
        raise ValueError('v90 held-out map/timing mismatch')
    if 'case' in bundle and bundle['case'] != previous.cases(CHECK, bundle['map_id'])[0]:
        raise ValueError('v90 held-out case mismatch')


def bundle(map_id, check):
    from harness.zone_final_pair_clearance import path_preflight
    from harness.python_source_closure import source_closure
    reg = registry()
    measurement = design(check, map_id)
    # Copy the authored protocol, not a previous run or its success. The map
    # and source identities below belong to this newly registered acquisition.
    value = previous.bundle(MAP_ID, check)
    static = previous.resolve(map_id)[0]
    value.update(schema='ugrp.final_pair_bundle.v90', execution_bundle_id=BUNDLE_ID,
        workflow_id=WORKFLOW_ID, workflow_version=WORKFLOW_VERSION,
        map_id=map_id, map_sha256=previous.base.digest(static), seed=SEED, **ROLE,
        controller_family='teacher_fixed_schedule', controller_variant='v88-unloaded-heldout',
        controller_inputs=[], measurement=measurement,
        clearance_preflight=path_preflight(check, map_id),
        revision='v90 new held-out acquisition; v88 two-door protocol preserved',
        training_map=reg['training_map'])
    entries = ['harness/zone_final_pair_heldout.py', 'scripts/run_final_pair_heldout.py']
    files = (set(value['source_sha256']) | set(previous.base.bundle(map_id)['source_sha256'])
             | set(source_closure(previous.ROOT, entries)) | {REGISTRY, WORKFLOW})
    value['source_sha256'] = {p: previous.base.sha(previous.ROOT / p) for p in sorted(files)}
    validate_bundle(value)
    return value
