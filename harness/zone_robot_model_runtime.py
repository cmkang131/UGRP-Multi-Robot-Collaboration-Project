"""Explicit geometry selection for new scene consumers; no process-global patch."""
from dataclasses import dataclass
from functools import partial
import copy

from sim.zone_model_conventions import convention


@dataclass(frozen=True)
class ModelRuntime:
    robot_model: str
    arm: object
    guard: object
    stations: dict
    footprint: object


def for_scene(scene):
    from harness.zone_team_footprint_v3 import team_footprint
    profile = convention(scene)
    if profile['robot_model'] == 'masterpi_v3':
        from harness import visual_arm_v3 as arm
        from harness.zone_own_guards_v3 import SweepGuardV3 as Guard
    else:
        from harness import visual_arm as arm
        from harness.zone_own_guards import SweepGuard as Guard
    static = copy.deepcopy(scene.config['static_map'])
    return ModelRuntime(profile['robot_model'], arm, Guard(static), profile, partial(team_footprint, static))


def require_v3_consumers(student, pose_factory):
    """Fail before physics if a new scene would silently select v2 or tags.

V3 consumers must explicitly accept the model_runtime keyword. This prevents
old dynamically selected skills/pose providers from claiming v3 compatibility.
"""
    from harness.visual_arm_v3 import CONTROLLER_GEOMETRY_ID
    import importlib
    module = importlib.import_module(student['skill_module'])
    if (getattr(module, 'CONTROLLER_GEOMETRY_ID', None) != CONTROLLER_GEOMETRY_ID
            or getattr(pose_factory, 'controller_geometry_id', None) != CONTROLLER_GEOMETRY_ID
            or getattr(pose_factory, 'uses_landmark_tags', True)):
        raise ValueError('v3 scene requires explicit v3 skill and tag-free v3 pose consumers')
