"""New v93 admission: v92 measured HIGH calibration, no v88 relabelling."""
from __future__ import annotations

import copy
import re
import numpy as np

from harness import zone_final_pair_contract as previous
from harness import zone_pair_highpose as pose

base, ROOT = previous.base, previous.ROOT
BUNDLE_ID = 'zone-final-pair-highpose-v93'
WORKFLOW_ID, WORKFLOW_VERSION = 'zone-final-pair-highpose-v93', '3.5.0'
REGISTRY = 'configs/zone_pair_highpose_v93.json'
WORKFLOW = 'configs/simulation_workflows.d/pair_highpose_v93.json'
CALIBRATION_CONTRACT = 'configs/calibration/zone_pair_highpose_v93_contract.json'
PROVIDER_ID = 'opencv_owncam_final_pair_highpose_v93'
PRECONDITION = 'V92_MEASURED_SIM_HIGHPOSE_CALIBRATION_REQUIRED'
CHECKS, ROBOTS = ('p03', 'carry'), previous.ROBOTS
RESET_CAP_S, TICK_S, COLLECTION_FRAME_S = previous.RESET_CAP_S, previous.TICK_S, previous.COLLECTION_FRAME_S
camera_record = previous.camera_record


def registry():
    reg = base.read(ROOT / REGISTRY)
    if (reg['execution_bundle_id'] != BUNDLE_ID or reg['workflow_id'] != WORKFLOW_ID
            or reg['workflow_version'] != WORKFLOW_VERSION or reg['runnable'] is not False
            or reg['precondition'] != PRECONDITION or reg['provider_id'] != PROVIDER_ID
            or reg['calibration_contract_sha256'] != base.sha(ROOT / CALIBRATION_CONTRACT)):
        raise ValueError('v93 registry mismatch')
    return reg


def resolve(map_id):
    static, row, _ = previous.resolve(map_id)
    reg = registry()
    contract = base.read(ROOT / CALIBRATION_CONTRACT)
    if (map_id not in reg['maps'] or contract['maps'][map_id] != base.digest(static)
            or contract['loaded_pose_id'] != pose.POSE_ID
            or contract['loaded_camera_keys'] != ['896,2035,1894,1500']):
        raise ValueError('v93 static map/pose contract mismatch')
    for path, digest in contract['static_sources_sha256'].items():
        if base.sha(ROOT / path) != digest:
            raise ValueError('v93 static source mismatch: '+path)
    return static, row, contract


def _vector(value, size, *, positive=False):
    try:
        a = np.asarray(value, float)
        valid = a.shape == (size,) and np.isfinite(a).all() and (a > 0 if positive else a >= 0).all()
    except (TypeError, ValueError):
        valid = False
    if not valid:
        raise ValueError('invalid measured calibration vector')
    return a


def measured_calibration(path, expected_sha, map_id):
    if path is None or expected_sha is None:
        raise ValueError(PRECONDITION)
    _, _, contract = resolve(map_id)
    if base.sha(path) != expected_sha:
        raise ValueError('measured calibration hash mismatch')
    cal = base.read(path)
    base.digest(cal)  # reject nested NaN/Inf before any numerical comparison
    required = {'schema': 'ugrp.final_pair_highpose_measured_calibration.v1', 'status': 'MEASURED_SIM',
        'contract_sha256': base.sha(ROOT / CALIBRATION_CONTRACT), 'maps': contract['maps'],
        'robot_model': 'masterpi_v3', 'render_profile': 'floor_light_v1',
        'loaded_measurement_bundle_id': 'zone-final-pair-v92', 'loaded_pose_id': pose.POSE_ID,
        'loaded_camera_scope': 'high_only'}
    if any(cal.get(k) != v for k, v in required.items()):
        raise ValueError('v92 measured HIGH calibration combination mismatch')
    for name, size in (('source_sha', 40), ('measurement_manifest_sha256', 64),
                       ('loaded_schedule_sha256', 64), ('criterion_sha256', 64), ('assembler_sha256', 64)):
        if not re.fullmatch('[0-9a-f]{%d}' % size, str(cal.get(name, ''))):
            raise ValueError('measured calibration missing provenance: '+name)
    params = cal['params']
    for profile in (params['motion'], params['motion_loaded'], params['motion_profiles']['fine']):
        gain = np.asarray(profile['gain'], float)
        if (gain.shape != (3, 3) or not np.isfinite(gain).all() or np.any(np.diag(gain) <= 0)
                or abs(np.linalg.det(gain)) < 1e-9):
            raise ValueError('invalid measured motion gain')
        _vector([profile['tau_s']], 1, positive=True)
        _vector([profile['tau_stop_s'], profile['scale_std'], profile['scale_walk']], 3)
        for key in ('noise_rel', 'noise_abs'):
            _vector(profile[key], 3)
        if 'tau_axis_s' in profile:
            _vector(profile['tau_axis_s'], 3, positive=True)
    loaded = params['motion_loaded']
    _vector([loaded['yaw_bias_std_rad_s'], loaded['drift_ratio_std']], 2)
    _vector(loaded['load_transition']['scale_std'], 3)
    _vector(np.broadcast_to(loaded['load_transition']['unloaded_scale_std'], (3,)), 3)
    for key in ('c0', 'u1'):
        _vector(loaded['deadband'][key], 3)
    if np.any(np.asarray(loaded['deadband']['c0']) > np.asarray(loaded['deadband']['u1'])):
        raise ValueError('deadband c0 exceeds u1')
    pair = cal['pair_model']
    if (not 0 < float(pair['slope_to_yaw_ratio']) < 3
            or set(pair['b_rad_s']) != {'', 'pm', 'edge', 'pm+edge'}):
        raise ValueError('invalid measured HIGH beam-edge model')
    _vector(list(pair['b_rad_s'].values()), 4)
    if set(cal['camera_models']['loaded']) != set(contract['loaded_camera_keys']):
        raise ValueError('loaded camera calibration is HIGH only (D2)')
    for state, poses in pose.required_camera_poses().items():
        if state not in cal['pan_base_yaw']:
            raise ValueError('missing measured pan calibration')
        for servo in poses:
            camera_record(cal, state, servo)
    return cal


def cases(check, map_id=None):
    if check not in CHECKS:
        raise ValueError('v93 supports student P03/carry only')
    return previous.cases(check, map_id)


def execution_timing(check):
    cases(check)
    timing = previous.execution_timing(check)
    timing['stabilization']['high_pose'] = pose.record()
    timing['parent_differences'].append('low lift -> finite HIGH raise -> carry -> reverse path -> floor release')
    return timing


def bundle(map_id, check):
    from harness.python_source_closure import source_closure
    static, _, contract = resolve(map_id)
    cases(check, map_id)
    value = copy.deepcopy(previous.bundle(map_id, check))
    value.update(schema='ugrp.final_pair_bundle.v93', execution_bundle_id=BUNDLE_ID,
        workflow_id=WORKFLOW_ID, workflow_version=WORKFLOW_VERSION, runnable=False,
        blocked_on=[PRECONDITION], provider_id=PROVIDER_ID,
        controller_variant='b-v6h1-v3-highpose-opencv', revision='D1 new candidate; no inherited acceptance',
        localization='OpenCV wall-band detector + static map particle filter; no learned segmentation',
        timing=execution_timing(check), high_pose=pose.record(), calibration_contract=contract,
        calibration_selection='v92 MEASURED_SIM + v93 contract hash; HIGH loaded only; no legacy fallback')
    entries = ['scripts/run_pair_highpose.py', 'harness/zone_pair_highpose_runtime.py',
               'harness/vision_pose_source_highpose.py']
    paths = set(value['source_sha256']) | set(source_closure(ROOT, entries)) | {REGISTRY, WORKFLOW, CALIBRATION_CONTRACT}
    value['source_sha256'] = {p: base.sha(ROOT / p) for p in sorted(paths)}
    return value
