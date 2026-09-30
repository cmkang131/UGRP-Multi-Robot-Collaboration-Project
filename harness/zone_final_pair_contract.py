"""Explicit v88 inputs for the v3 pair adapter; no simulator imports.

The v84/default-light records and all registered v2 sources remain immutable.
Calibration acquisition is a teacher measurement, never student acceptance.
"""
from __future__ import annotations

import copy
import math
import re
from pathlib import Path

from harness import zone_final_environment as base

ROOT = base.ROOT
REGISTRY = 'configs/zone_final_pair_v88.json'
WORKFLOW = 'configs/simulation_workflows.d/final_pair_v88.json'
CALIBRATION_CONTRACT = 'configs/calibration/zone_final_pair_v88_contract.json'
BUNDLE_ID = 'zone-final-pair-v88'
WORKFLOW_ID = 'zone-final-pair-v3'
PROVIDER_ID = 'vision_zero_tag_final_pair_v88'
CHECKPOINTS = ('before_door', 'after_door', 'before_destination')
CHECKS = ('p03', 'carry', 'calibration-unloaded', 'calibration-loaded', 'calibration-fine')
ROBOTS = ('r1', 'r2')
RESET_CAP_S = 5.


def registry():
    value = base.read(ROOT / REGISTRY)
    if (value['execution_bundle_id'] != BUNDLE_ID or value['status'] != 'DRAFT_UNSEALED'
            or value['render_profile'] != 'floor_light_v1' or value['weld'] != 'off'
            or value['contact_profile'] != 'cargo_noslip_v1'
            or value['sensors'] != {'ultrasonic_front': 'off'}):
        raise ValueError('invalid final pair registry')
    return value


def resolve(map_id):
    # v84's map/model/mount hashes remain useful provenance; its rendering and
    # unmeasured calibration are not inherited as runtime calibration.
    static, row, _ = base.resolve(map_id)
    reg = registry()
    contract = base.read(ROOT / CALIBRATION_CONTRACT)
    if (map_id not in reg['maps'] or contract['maps'][map_id] != base.digest(static)
            or contract['render_profile'] != reg['render_profile']
            or contract['robot_model'] != 'masterpi_v3'
            or base.sha(ROOT / CALIBRATION_CONTRACT) != reg['calibration_contract_sha256']):
        raise ValueError('v88 map/render/calibration contract mismatch')
    return static, row, contract


def camera_record(calibration, state, servo):
    from harness.vision_pose_source_final import camera_key, CalibrationError
    import numpy as np
    key = camera_key(servo)
    record = calibration.get('camera_models', {}).get(state, {}).get(key)
    if record is None:
        raise CalibrationError(f'UNMEASURED_V3_CAMERA_POSTURE: {state}:{key}')
    origin, rotation = np.asarray(record['origin_m']), np.asarray(record['rotation'])
    if (origin.shape != (3,) or rotation.shape != (3, 3)
            or not np.isfinite(origin).all() or not np.isfinite(rotation).all() or origin[2] <= 0
            or not np.allclose(rotation.T @ rotation, np.eye(3), atol=1e-5)
            or not np.isclose(np.linalg.det(rotation), 1., atol=1e-5)):
        raise CalibrationError('invalid measured v3 camera transform')
    return copy.deepcopy(record)


def measured_calibration(path, expected_sha, map_id):
    import numpy as np
    _, _, contract = resolve(map_id)
    if path is None or expected_sha is None:
        raise ValueError('MEASURED_V3_CALIBRATION_REQUIRED')
    if base.sha(path) != expected_sha:
        raise ValueError('measured calibration hash mismatch')
    cal = base.read(path)
    if (cal.get('schema') != 'ugrp.final_environment_measured_calibration.v1'
            or cal.get('status') != 'MEASURED_SIM'
            or cal.get('contract_sha256') != base.sha(ROOT / CALIBRATION_CONTRACT)
            or cal.get('maps') != contract['maps'] or cal.get('robot_model') != 'masterpi_v3'
            or cal.get('render_profile') != 'floor_light_v1'):
        raise ValueError('measured calibration combination mismatch')
    for name, size in (('source_sha', 40), ('measurement_manifest_sha256', 64)):
        if not re.fullmatch('[0-9a-f]{%d}' % size, str(cal.get(name, ''))):
            raise ValueError('measured calibration requires source/measurement provenance')
    params = cal.get('params', {})
    for profile in (params.get('motion'), params.get('motion_loaded'),
                    params.get('motion_profiles', {}).get('fine')):
        if not isinstance(profile, dict):
            raise ValueError('measured calibration requires unloaded/loaded/fine motion')
        gain = profile.get('gain', [])
        if (len(gain) != 3 or any(len(row) != 3 for row in gain)
                or any(not math.isfinite(float(v)) for row in gain for v in row)
                or any(float(gain[i][i]) <= 0 for i in range(3))
                or abs(float(np.linalg.det(np.asarray(gain, float)))) < 1e-9
                or not 0 < float(profile.get('tau_s', 0))
                or not 0 <= float(profile.get('tau_stop_s', -1))):
            raise ValueError('invalid measured motion gain/lag')
        for key in ('noise_rel', 'noise_abs'):
            if len(profile.get(key, [])) != 3 or any(float(x) < 0 for x in profile[key]):
                raise ValueError('measured motion noise vectors required')
        if any(float(profile.get(key, -1)) < 0 for key in ('scale_std', 'scale_walk')):
            raise ValueError('measured motion scale parameters required')
        if ('tau_axis_s' in profile and (len(profile['tau_axis_s']) != 3
                or any(not float(v) > 0 for v in profile['tau_axis_s']))):
            raise ValueError('measured axis lag must contain three positive values')
    loaded = params['motion_loaded']
    transition = loaded.get('load_transition', {})
    if (float(loaded.get('yaw_bias_std_rad_s', -1)) < 0 or float(loaded.get('drift_ratio_std', -1)) < 0
            or len(transition.get('scale_std', [])) != 3
            or any(float(v) < 0 for v in transition['scale_std'])
            or 'unloaded_scale_std' not in transition
            or any(len(loaded.get('deadband', {}).get(k, [])) != 3 for k in ('c0', 'u1'))):
        raise ValueError('measured pair plant spread/deadband required')
    if (any(float(v) < 0 for k in ('c0', 'u1') for v in loaded['deadband'][k])
            or np.any(np.asarray(transition['unloaded_scale_std'], float) < 0)):
        raise ValueError('measured deadband/spread must be nonnegative')
    # b-v6h1's yaw availability model must also be fitted on v3. Old v2 fit
    # files are never injected by PairTeam.enable_provider in this adapter.
    pair = cal.get('pair_model', {})
    if (not isinstance(pair.get('slope_to_yaw_ratio'), (float, int))
            or pair['slope_to_yaw_ratio'] == 0
            or set(pair.get('b_rad_s', {})) != {'', 'pm', 'edge', 'pm+edge'}
            or any(float(v) < 0 for v in pair['b_rad_s'].values())):
        raise ValueError('measured v3 pair yaw model required')
    for state in ('unloaded', 'loaded'):
        if not cal.get('camera_models', {}).get(state) or state not in cal.get('pan_base_yaw', {}):
            raise ValueError('measured loaded/unloaded camera and pan calibration required')
        for key in cal['camera_models'][state]:
            camera_record(cal, state, dict(zip((3, 4, 5, 6), map(int, key.split(',')))))
    from harness.zone_final_pair_vision import required_camera_poses
    for state, poses in required_camera_poses().items():
        for servo in poses:
            camera_record(cal, state, servo)
    base.digest(cal)  # also rejects non-finite nested values
    return cal


def cases(check, map_id=None):
    reg = registry()
    if check not in CHECKS:
        raise ValueError('unknown final pair check')
    if map_id is not None and map_id not in reg['maps']:
        raise ValueError('unknown final v3 map')
    if check == 'p03':
        if map_id not in (None, reg['p03_map']):
            raise ValueError('P03 checkpoints require the registered one-door map')
        return [{'id': checkpoint, 'map_id': reg['p03_map'], 'checkpoint': checkpoint,
                 'sim_cap_s': 120.} for checkpoint in CHECKPOINTS]
    return [{'id': mid, 'map_id': mid, 'checkpoint': None, 'sim_cap_s': 120.}
            for mid in ([map_id] if map_id else reg['maps'])]


def bundle(map_id, check):
    from harness.python_source_closure import source_closure
    static, row, contract = resolve(map_id)
    if check not in CHECKS:
        raise ValueError('unknown final pair check')
    old = base.bundle(map_id)
    entries = ['scripts/run_final_pair_v3.py', 'sim/final_pair_v3.py',
               'harness/zone_final_pair_runtime.py', 'harness/zone_final_pair_skill.py',
               'harness/vision_pose_source_pair_v3.py', 'harness/zone_final_pair_calibration.py']
    paths = set(source_closure(ROOT, entries)) | set(old['source_sha256'])
    paths.update((REGISTRY, WORKFLOW, CALIBRATION_CONTRACT,
                  'configs/final_environment_measurement_v1.json'))
    return {'schema': 'ugrp.final_pair_bundle.v88', 'execution_bundle_id': BUNDLE_ID,
            'status': 'DRAFT_UNSEALED', 'check': check, 'map_id': map_id,
            'map_sha256': base.digest(static), 'robot_model': 'masterpi_v3',
            'render_profile': 'floor_light_v1', 'contact_profile': 'cargo_noslip_v1',
            'weld': 'off', 'sensors': {'ultrasonic_front': 'off'},
            'controller_family': 'b-v6h1', 'controller_variant': 'b-v6h1-v3-measured',
            'controller_inputs': ['own_rgb', 'static_map', 'own_command_history', 'delivered_messages'],
            'calibration_contract': contract, 'physical_ready': False,
            'research_result': False, 'source_sha256': {p: base.sha(ROOT / p) for p in sorted(paths)}}
