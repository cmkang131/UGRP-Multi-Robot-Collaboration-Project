"""New v92 loaded collection identity; no change to old bundles or criteria."""
import gzip
import hashlib

from harness import zone_final_pair_contract as previous
from harness import zone_final_pair_loaded_schedule as acquisition

BUNDLE_ID = 'zone-final-pair-v92'
REGISTRY = 'configs/zone_final_pair_v92.json'
SCHEDULE = 'configs/zone_final_pair_v92_schedule.json.gz'
WORKFLOW = 'configs/simulation_workflows.d/final_pair_v92.json'
WORKFLOW_ID = 'zone-final-pair-loaded-v92'
WORKFLOW_VERSION = '3.4.0'
CHECK, MAP_ID, SEED = acquisition.CHECK, acquisition.MAP_ID, 911
ROLE = {'collection_role': 'CALIBRATION_TRAINING', 'training_eligible': True, 'teacher_only': True}


def selected(check, map_id):
    return check == CHECK and map_id == MAP_ID


def schedule_registration():
    archive = (previous.ROOT/SCHEDULE).read_bytes()
    raw = gzip.decompress(archive)
    if raw != acquisition.schedule_bytes():
        raise ValueError('v92 registered schedule bytes differ from authored source')
    return {'path': SCHEDULE, 'encoding': 'gzip of UTF-8 JSON, indent=2, trailing LF',
            'sha256': hashlib.sha256(raw).hexdigest(), 'bytes': len(raw),
            'archive_sha256': hashlib.sha256(archive).hexdigest(), 'archive_bytes': len(archive)}


def registry():
    value = previous.base.read(previous.ROOT/REGISTRY)
    expected = {'schema': 'ugrp.final_pair_loaded.v92', 'execution_bundle_id': BUNDLE_ID,
        'status': 'DRAFT_UNSEALED', 'workflow_id': WORKFLOW_ID, 'workflow_version': WORKFLOW_VERSION,
        'check': CHECK, 'maps': [MAP_ID], 'seed': SEED, **ROLE,
        'robot_model': 'masterpi_v3', 'render_profile': 'floor_light_v1',
        'contact_profile': 'cargo_noslip_v1', 'weld': 'off', 'sensors': {'ultrasonic_front': 'off'},
        'sim_cap_s': acquisition.CAP_S, 'reset_cap_s': 5., 'schedule': schedule_registration()}
    if value != expected:
        raise ValueError('v92 registry differs from registered collection')
    return value


def design(check, map_id):
    registry()
    return acquisition.design(check, map_id)


def timing():
    value = previous.execution_timing(CHECK)
    value['stabilization'] = {
        'scene_setup': 'standard constructor 0.30s + Scene.setup within reset cap',
        'loaded_measurement_warmup_s': 8.,
        'selection': 'prospective camera_windows; all preparation raw retained; frozen B-prime unchanged'}
    return value


def cases(check, map_id):
    plan = design(check, map_id)
    return [{'id': map_id, 'map_id': map_id, 'checkpoint': None, 'sim_cap_s': plan['sim_cap_s']}]


def record(bundle):
    return {**ROLE, 'schedule': schedule_registration()} if bundle['execution_bundle_id'] == BUNDLE_ID else {}


def require_seed(bundle, seed):
    if bundle.get('execution_bundle_id') != BUNDLE_ID or seed != SEED:
        raise ValueError('v92 loaded collection requires its own bundle and seed 911')


def validate_bundle(bundle):
    reg = registry()
    if not selected(bundle.get('check'), bundle.get('map_id')):
        raise ValueError('v92 requires loaded training collection on the two-door map')
    static = previous.resolve(MAP_ID)[0]
    for key in ('execution_bundle_id', 'check', 'seed', *ROLE, 'robot_model', 'render_profile',
                'contact_profile', 'weld', 'sensors', 'workflow_id', 'workflow_version', 'schedule'):
        if bundle.get(key) != reg[key]:
            raise ValueError(f'v92 collection mismatch: {key}')
    if bundle.get('map_sha256') != previous.base.digest(static) or bundle.get('timing') != timing():
        raise ValueError('v92 map/timing mismatch')
    if bundle.get('caps') != {'reset_per_case_s': 5., 'per_case_s': acquisition.CAP_S,
                              'default_cases': 1, 'total_including_reset_s': acquisition.CAP_S+5.}:
        raise ValueError('v92 cap mismatch')
    if 'case' in bundle and bundle['case'] != cases(CHECK, MAP_ID)[0]:
        raise ValueError('v92 case mismatch')


def bundle(map_id, check):
    from harness.python_source_closure import source_closure
    from harness.zone_final_pair_loaded_clearance import path_preflight
    reg = registry()
    measurement = design(check, map_id)
    value = previous.bundle(MAP_ID, CHECK)
    value.update(schema='ugrp.final_pair_bundle.v92', execution_bundle_id=BUNDLE_ID,
        workflow_id=WORKFLOW_ID, workflow_version=WORKFLOW_VERSION, seed=SEED, **ROLE,
        controller_family='teacher_fixed_schedule', controller_variant='v92-loaded-measurement',
        controller_inputs=[], measurement=measurement, timing=timing(),
        caps={'reset_per_case_s': 5., 'per_case_s': acquisition.CAP_S, 'default_cases': 1,
              'total_including_reset_s': acquisition.CAP_S+5.},
        schedule=reg['schedule'], clearance_preflight=path_preflight(check, map_id),
        revision='v92 schedule only; v91 fast guard/SIM slots; old registrations and criteria unchanged',
        calibration_selection='none: raw teacher collection, unsupported by frozen v88 assembler')
    entries = ['harness/zone_final_pair_loaded.py', 'scripts/run_final_pair_loaded.py',
               'sim/final_pair_loaded.py']
    paths = set(value['source_sha256']) | set(source_closure(previous.ROOT, entries)) | {REGISTRY, WORKFLOW, SCHEDULE}
    value['source_sha256'] = {p: previous.base.sha(previous.ROOT/p) for p in sorted(paths)}
    validate_bundle(value)
    return value
