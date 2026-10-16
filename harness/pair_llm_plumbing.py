"""PLUMBING-ONLY fixtures for the pair LLM stage-2 smoke. Never a measurement, never a result.

The v88 pair controller needs a measured v3 calibration that does not exist yet (the measured files are
PARTIAL and ``measured_calibration`` rejects them). To show that the LLM layer's wiring (frames -> calls ->
claims -> gate -> scripted skill -> physics -> evaluator) runs end to end, the smoke uses

* a FABRICATED calibration that passes the schema checks (``synthetic_calibration``), flagged
  ``synthetic_plumbing_only`` in the file and in the bundle, and
* a vision worker that refuses every frame (``blind_provider_factory``), so the controller has no pose.

With both, the robots cannot localize and cannot carry. A run shows the LLM layer's plumbing and the failure
path; it says NOTHING about carry success, the model, or any arm's efficiency.
"""
from __future__ import annotations

import copy
from pathlib import Path

from harness import zone_final_pair_contract as skill_layer
from harness.zone_final_environment import digest, sha

LABEL = 'SYNTHETIC-PLUMBING-ONLY-NOT-A-MEASUREMENT'


def synthetic_calibration(path, *, map_id=None) -> dict:
    """Write the fabricated calibration to ``path`` and return ``{'path', 'sha256'}``."""
    import numpy as np
    from harness.owncam_localizer import DEFAULT_PARAMS
    from harness.vision_pose_source_final import camera_key
    from harness.zone_final_pair_vision import required_camera_poses
    from scripts.run_final_environment_checks import write
    map_id = map_id or skill_layer.registry()['p03_map']
    params = copy.deepcopy(DEFAULT_PARAMS)
    params['particles'] = 100
    params['motion']['tau_stop_s'] = .02
    params['motion_loaded'] = copy.deepcopy(params['motion'])
    params['motion_loaded'].update(
        yaw_bias_std_rad_s=.01, drift_ratio_std=.01, deadband={'c0': [0., 0., 0.], 'u1': [0., 0., 0.]},
        load_transition={'scale_std': [.02, .02, .01], 'unloaded_scale_std': .05})
    params['motion_profiles'] = {'fine': copy.deepcopy(params['motion'])}
    rec = {'frame': 'optical_to_actual_chassis',
           'chassis_to_floor': {'origin_m': [0., 0., .03236], 'rotation': np.eye(3).tolist()},
           'origin_m': [.15, 0., .2], 'rotation': [[0., 0., 1.], [-1., 0., 0.], [0., -1., 0.]]}
    cal = {'schema': 'ugrp.final_environment_measured_calibration.v1', 'status': 'MEASURED_SIM',
           'synthetic_plumbing_only': True, 'label': LABEL,
           'contract_sha256': sha(skill_layer.ROOT / skill_layer.CALIBRATION_CONTRACT),
           'maps': skill_layer.resolve(map_id)[2]['maps'], 'robot_model': 'masterpi_v3',
           'render_profile': 'floor_light_v1', 'source_sha': 'a' * 40, 'measurement_manifest_sha256': 'b' * 64,
           'params': params, 'pan_base_yaw': {'loaded': 0., 'unloaded': 0.},
           'pair_model': {'slope_to_yaw_ratio': 1., 'b_rad_s': {'': .04, 'pm': .03, 'edge': .02, 'pm+edge': .01}},
           'camera_models': {state: {'740,2320,1320,1500': copy.deepcopy(rec)} for state in ('loaded', 'unloaded')}}
    for state, poses in required_camera_poses().items():
        for pose in poses:
            cal['camera_models'][state][camera_key(pose)] = copy.deepcopy(rec)
    write(Path(path), cal)
    return {'path': str(path), 'sha256': sha(Path(path)), 'canonical_sha256': digest(cal)}


def blind_provider_factory(static, calibration_path, calibration_sha, seed):
    """``Runtime`` provider factory whose vision worker refuses every frame (no pose is ever produced)."""
    from harness.vision_loc_client import InProcessWorker
    from harness.vision_pose_source_pair_v3 import build_provider
    return build_provider(static, calibration_path, calibration_sha, seed,
                          worker=InProcessWorker(lambda *a: None))


__all__ = ['LABEL', 'synthetic_calibration', 'blind_provider_factory']
