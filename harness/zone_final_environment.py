"""Static, opt-in v84 final environment contract. Never imports a simulator.

Runnable inspection is independent of preregistration sealing and of student
admission. Missing measured v3 calibration is never filled with v2 values.
"""
from __future__ import annotations

import copy
import hashlib
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
REGISTRY = 'configs/zone_final_environment_v84.json'
WORKFLOW = 'configs/simulation_workflows.d/final_environment_v84.json'
BUNDLE_ID = 'zone-final-environment-v84'
PROVIDER_ID = 'vision_zero_tag_final_v3_p03'


def digest(value):
    return hashlib.sha256(json.dumps(value, sort_keys=True, separators=(',', ':'),
                                     allow_nan=False).encode()).hexdigest()


def read(path):
    return json.loads(Path(path).read_text())


def sha(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def local_path(relative, *, root=ROOT):
    path = Path(root) / relative
    if Path(relative).is_absolute() or not path.resolve().is_relative_to(Path(root).resolve()):
        raise ValueError('nonlocal final environment asset')
    return path


def registry(*, root=ROOT):
    value = read(Path(root) / REGISTRY)
    if (value['schema'] != 'ugrp.final_environment.v84'
            or value['execution_bundle_id'] != BUNDLE_ID
            or value['status'] != 'DRAFT_UNSEALED' or value['research_result'] is not False
            or value['weld'] != 'off' or value['provider_id'] != PROVIDER_ID):
        raise ValueError('invalid DRAFT final environment registry')
    return value


def resolve(map_id, *, root=ROOT):
    reg = registry(root=root)
    if map_id not in reg['maps']:
        raise ValueError(f'final provider map is not allow-listed: {map_id}')
    row = reg['maps'][map_id]
    path = local_path(row['file'], root=root)
    parent_path = local_path(row['parent_file'], root=root)
    static, parent = read(path), read(parent_path)
    if sha(path) != row['sha256'] or digest(static) != row['static_map_sha256']:
        raise ValueError('final map file/static hash mismatch')
    if sha(parent_path) != row['parent_sha256']:
        raise ValueError('final map parent hash mismatch')
    if (static['map_id'] != map_id or static.get('robot_model') != row['robot_model']
            or row['robot_model'] != 'masterpi_v3'
            or static.get('parent_scene') != {'map_id': parent['map_id'], 'sha256': digest(parent)}
            or 'landmarks' in static or static['wall_profile']['id'] != 'walls_v3'):
        raise ValueError('final map/model/parent/tag identity mismatch')
    contract_path = local_path(row['calibration_contract'], root=root)
    contract = read(contract_path)
    if sha(contract_path) != row['calibration_contract_sha256']:
        raise ValueError('final calibration contract hash mismatch')
    if (contract['robot_model'] != 'masterpi_v3'
            or contract['maps'].get(map_id) != digest(static)
            or contract['render_profile'] != reg['render_profile']):
        raise ValueError('final calibration map/model/render mismatch')
    for rel, expected in contract['static_sources_sha256'].items():
        if sha(local_path(rel, root=root)) != expected:
            raise ValueError(f'final calibration static source mismatch: {rel}')
    camera = contract['camera']
    if sha(local_path(camera['mount_file'], root=root)) != camera['mount_sha256']:
        raise ValueError('final camera mount mismatch')
    return static, row, contract


def provider_spec(map_id, *, root=ROOT):
    """New allow-list; frozen P03/v2 registry and its factories stay unchanged."""
    static, row, contract = resolve(map_id, root=root)
    return {'provider_id': PROVIDER_ID, 'parent_provider_id': 'vision_zero_tag_v2_p03_v1',
            'factory': 'harness.vision_pose_source_final:FinalVisionPoseSource',
            'maps': list(registry(root=root)['maps']), 'robot_model': static['robot_model'],
            'uses_landmark_tags': False, 'research_result': False,
            'calibration_contract': row['calibration_contract'],
            'calibration_contract_sha256': row['calibration_contract_sha256'],
            'calibration_status': contract['status'], 'perception_delay_s': .16}


def measured_calibration(path, expected_sha, map_id, *, root=ROOT):
    """Explicit fixed measurement product, never an eval-only runtime channel."""
    _, row, contract = resolve(map_id, root=root)
    if path is None or expected_sha is None:
        raise ValueError('MEASURED_V3_CALIBRATION_REQUIRED; see PHYSICS_HANDOFF.md')
    if sha(path) != expected_sha:
        raise ValueError('measured calibration hash mismatch')
    value = read(path)
    if (value.get('schema') != 'ugrp.final_environment_measured_calibration.v1'
            or value.get('status') != 'MEASURED_SIM'
            or value.get('contract_sha256') != row['calibration_contract_sha256']
            or value.get('maps') != contract['maps'] or value.get('robot_model') != 'masterpi_v3'
            or value.get('render_profile') != contract['render_profile']):
        raise ValueError('measured calibration combination mismatch')
    if not value.get('measurement_manifest_sha256') or not value.get('source_sha'):
        raise ValueError('measured calibration requires source/measurement provenance')
    if not all(value.get(k) for k in ('params', 'camera_models', 'pan_base_yaw')):
        raise ValueError('measured calibration requires motion/camera/pan measurements')
    for state in ('loaded', 'unloaded'):
        if not value['camera_models'].get(state) or state not in value['pan_base_yaw']:
            raise ValueError('measured calibration requires loaded and unloaded camera measurements')
    if not all(key in value['params'] for key in ('motion', 'motion_loaded', 'motion_profiles')):
        raise ValueError('measured calibration requires unloaded/loaded/fine motion')
    if 'fine' not in value['params']['motion_profiles']:
        raise ValueError('measured calibration requires fine motion')
    digest(value)  # non-finite calibration is always invalid
    return value


def bundle(map_id, *, check='p01', root=ROOT):
    from harness.python_source_closure import source_closure
    reg = registry(root=root)
    if check not in reg['checks']:
        raise ValueError('unknown final environment check')
    static, row, contract = resolve(map_id, root=root)
    paths = [REGISTRY, WORKFLOW, row['file'], row['parent_file'], row['calibration_contract'],
             'harness/zone_final_environment.py', 'harness/vision_pose_source_final.py',
             'scripts/run_final_environment_checks.py', 'sim/zone_final_v3_scene.py',
             'sim/final_environment_checks.py', 'sim/workflow_manager.py',
             'configs/vision_loc_provider_p03.json', 'configs/vision_loc_worker.json',
             'configs/model_artifacts.json', 'configs/final_environment_measurement_v1.json',
             *contract['static_sources_sha256'], contract['camera']['mount_file']]
    # Explicit data reads and dynamic VIS3 modules are outside the AST closure.
    p03 = read(Path(root) / 'configs/vision_loc_provider_p03.json')
    paths.extend(p03['active']['files_sha256'])
    paths.append('maps/zones/' + static['base_map']['map_id'] + '.json')
    importable = [p for p in paths if not p.endswith('.py') or all(x.isidentifier() for x in p[:-3].split('/'))]
    files = set(source_closure(root, importable)) | set(paths)
    return {'schema': 'ugrp.final_environment_bundle.v84', 'execution_bundle_id': BUNDLE_ID,
            'status': 'DRAFT_UNSEALED', 'runnable': check != 'p03', 'research_result': False,
            'physical_ready': False, 'check': check, 'caps': copy.deepcopy(reg['checks'][check]),
            'map_id': map_id, 'map_sha256': digest(static), 'robot_model': 'masterpi_v3',
            'weld': reg['weld'], 'contact_profile': reg['contact_profile'],
            'render_profile': reg['render_profile'], 'sensors': reg['sensors'],
            'provider': provider_spec(map_id, root=root),
            'model': p03['active']['model'], 'calibration_contract': contract,
            'controller_inputs': ['own_rgb', 'static_map', 'own_command_history', 'delivered_messages'],
            'source_sha256': {p: sha(local_path(p, root=root)) for p in sorted(files)},
            'blocked_on': reg['checks'][check].get('requires', [])}
