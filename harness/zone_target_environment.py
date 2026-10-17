"""T13 final-environment admission, based on PR #338's v84 contract.

The current target RGB projection and manipulation chain use v2 geometry.
Selecting a v3 map never certifies those consumers. Missing measured camera /
motion calibration and missing v3 consumers are explicit execution blockers.
This module performs no physics, inference or evaluation-state reads.
"""
from pathlib import Path

from harness import zone_final_environment as final


def environment_contract(cfg, *, root=final.ROOT):
    registry = final.registry(root=root)
    static, _, contract = final.resolve(cfg['map_id'], root=root)
    parent = {**registry, 'robot_model': static['robot_model'],
              'provider': final.provider_spec(cfg['map_id'], root=root),
              'calibration_contract': contract}
    if (cfg['final_environment_bundle_id'] != parent['execution_bundle_id']
            or cfg['robot_model'] != parent['robot_model']
            or cfg['pose_provider'] != parent['provider']['provider_id']
            or cfg['render_profile'] != parent['render_profile']
            or cfg['contact_profile'] != parent['contact_profile']
            or cfg['sensor'] != parent['sensors']['ultrasonic_front']
            or cfg['weld'] is not False):
        raise ValueError('T13 final environment differs from the v84 contract')
    return parent


def execution_blockers(cfg, *, root=final.ROOT):
    environment_contract(cfg, root=root)
    blockers = []
    path, sha = cfg['student']['calibration'], cfg['student']['calibration_sha256']
    if path is None or sha is None:
        blockers.append('measured_final_v3_calibration')
    else:
        final.measured_calibration(Path(root) / path, sha, cfg['map_id'], root=root)
    # This is an implementation capability check, not a configurable approval.
    # Do not remove it when only the map/provider or a model label changes.
    from harness.zone_target_executor import SUPPORTED_ROBOT_MODELS
    if cfg['robot_model'] not in SUPPORTED_ROBOT_MODELS:
        blockers.append('final_v3_target_rgb_and_manipulation_adapter')
    return blockers


def require_execution(cfg, *, root=final.ROOT):
    blockers = execution_blockers(cfg, root=root)
    if blockers:
        raise ValueError('T13_FINAL_ENVIRONMENT_NOT_READY: ' + ', '.join(blockers))
