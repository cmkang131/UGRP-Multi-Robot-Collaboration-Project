"""Opt-in T04 registry. No change to the sealed M1/colour-box dispatch.

The public catalogue dimensions are constants, not instance/setup information.
This registers control logic, not physical support or a study execution bundle.
"""
from dataclasses import asdict, dataclass
import hashlib
import json
from types import MappingProxyType


@dataclass(frozen=True)
class CanProfile:
    skill_id: str = 'can-ownrgb-v1-dev'
    kind: str = 'can'
    role: str = 'any'
    diameter_m: float = .038
    height_m: float = .050
    mass_kg: float = .080
    grasp_height_m: float = .024
    # v3 command IK rejects the catalogue teacher's legacy .155 m radius.
    # This is a candidate command geometry, NOT a physical calibration result.
    grasp_forward_m: float = .200
    lift_heights_m: tuple = (.080, .100)
    open_pwm: int = 2000
    close_pwm: int = 1500
    max_sim_s: float = 900.
    evidence: str = 'offline_only; physical_visibility_and_grasp_unverified'


CAN = CanProfile()
REGISTRY = MappingProxyType({'can': CAN})
CONDITIONS = ('no_comm', 'peer_ko', 'leader_ko', 'structured')


def profile_record():
    record = asdict(CAN)
    record['sha256'] = hashlib.sha256(json.dumps(record, sort_keys=True).encode()).hexdigest()
    return record


def create_skill(kind, *, role, condition, robot_id, static_map, destination_zone, pose_source):
    """Explicit new-kind entry point; never fall back to a box skill.

    The condition validates a caller's study vocabulary only. It cannot change
    configuration, observations, state vocabulary or controller behaviour.
    """
    if kind not in REGISTRY or role != CAN.role or condition not in CONDITIONS:
        raise ValueError('unsupported can kind/role/condition')
    from harness.zone_can_skill import CanSkill
    return CanSkill(robot_id, static_map, destination_zone=destination_zone, pose_source=pose_source)
