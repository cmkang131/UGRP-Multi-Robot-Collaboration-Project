"""D2 v92 조립 산출물 전용 로더 계약 v2. v88 학생 계약은 바꾸지 않는다."""
from __future__ import annotations

import math
import re
from harness import zone_final_pair_contract as previous
from harness.zone_final_pair_loaded_schedule import POSES

base, ROOT = previous.base, previous.ROOT
CALIBRATION_CONTRACT = 'configs/calibration/zone_final_pair_v92_contract.json'
SCHEMA = 'ugrp.final_environment_measured_calibration.v92'
POSE_ID = 'masterpi-v3-pair-high-150mm-minus40-v1'
camera_record = previous.camera_record


def calibration_contract():
    value = base.read(ROOT/CALIBRATION_CONTRACT)
    if (value['schema'] != 'ugrp.final_environment_calibration_contract.v92'
            or value['loader_contract_version'] != 2 or value['measured_schema'] != SCHEMA
            or value['loaded_camera_scope'] != 'high_only' or value['loaded_pose_id'] != POSE_ID
            or value['loaded_camera_keys'] != ['896,2035,1894,1500']
            or value['maps'] != previous.resolve('zone_wide_two_doors_final_v3')[2]['maps']):
        raise ValueError('invalid v92 HIGH-only calibration contract')
    return value


def required_camera_poses():
    from harness.zone_final_pair_vision import required_camera_poses as legacy
    return {'unloaded': legacy()['unloaded'], 'loaded': [dict(POSES['edge_view_150'])]}


def measured_calibration(path, expected_sha, map_id):
    import numpy as np
    contract = calibration_contract()
    if map_id not in contract['maps']:
        raise ValueError('unregistered calibration map')
    if path is None or expected_sha is None:
        raise ValueError('MEASURED_V3_CALIBRATION_REQUIRED')
    if base.sha(path) != expected_sha:
        raise ValueError('measured calibration hash mismatch')
    cal = base.read(path)
    if (cal.get('schema') != SCHEMA
            or cal.get('status') != 'MEASURED_SIM'
            or cal.get('loader_contract_version') != 2
            or any(cal.get(k) != contract[k] for k in ('loaded_measurement_bundle_id', 'loaded_pose_id', 'loaded_camera_scope'))
            or cal.get('contract_sha256') != base.sha(ROOT / CALIBRATION_CONTRACT)
            or cal.get('maps') != contract['maps'] or cal.get('robot_model') != 'masterpi_v3'
            or cal.get('render_profile') != 'floor_light_v1'):
        raise ValueError('measured calibration combination mismatch')
    base.digest(cal)  # reject all nested non-finite values before comparisons
    for name, size in (('source_sha', 40), ('measurement_manifest_sha256', 64),
                       ('loaded_schedule_sha256', 64), ('criterion_sha256', 64), ('assembler_sha256', 64)):
        if not re.fullmatch('[0-9a-f]{%d}' % size, str(cal.get(name, ''))):
            raise ValueError('measured calibration requires source/measurement provenance')
    from harness import zone_final_pair_loaded as loaded
    if (cal['loaded_schedule_sha256'] != loaded.schedule_registration()['sha256']
            or cal['criterion_sha256'] != loaded.CRITERION_SHA256):
        raise ValueError('v92 schedule/criterion provenance mismatch')
    sources = cal.get('collection_sources', {})
    if (set(sources) != {'unloaded', 'fine', 'loaded'}
            or any(not re.fullmatch('[0-9a-f]{40}', str(v)) for v in sources.values())):
        raise ValueError('separate unloaded/fine/loaded collection sources required')
    if set(cal.get('camera_models', {}).get('loaded', {})) != set(contract['loaded_camera_keys']):
        raise ValueError('loaded camera keys must be HIGH only')
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
    if np.any(np.asarray(loaded['deadband']['c0']) >= np.asarray(loaded['deadband']['u1'])):
        raise ValueError('deadband ramp must have positive width')
    # b-v6h1's yaw availability model must also be fitted on v3. Old v2 fit
    # files are never injected by PairTeam.enable_provider in this adapter.
    pair = cal.get('pair_model', {})
    if (not isinstance(pair.get('slope_to_yaw_ratio'), (float, int))
            or not 0 < pair['slope_to_yaw_ratio'] < 3
            or set(pair.get('b_rad_s', {})) != {'', 'pm', 'edge', 'pm+edge'}
            or any(float(v) < 0 for v in pair['b_rad_s'].values())):
        raise ValueError('measured v3 pair yaw model required')
    for state in ('unloaded', 'loaded'):
        if not cal.get('camera_models', {}).get(state) or state not in cal.get('pan_base_yaw', {}):
            raise ValueError('measured loaded/unloaded camera and pan calibration required')
        for key in cal['camera_models'][state]:
            camera_record(cal, state, dict(zip((3, 4, 5, 6), map(int, key.split(',')))))
    for state, poses in required_camera_poses().items():
        for servo in poses:
            camera_record(cal, state, servo)
    base.digest(cal)  # also rejects non-finite nested values
    return cal
