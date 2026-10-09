"""Observed-start-threshold candidate, not an identified motor/floor model.

The operator's <=30/100 no-motion observation identifies a resistance/drive
ratio only. Retain the public FUJI v2 contacts and exploratory motor scale;
represent that ratio with MuJoCo's native joint dry-friction constraint.
"""
from dataclasses import dataclass
import hashlib
import json
import math
import xml.etree.ElementTree as ET

from sim.masterpi_drive_friction import FrictionWorld
from sim.masterpi_drive_friction_v2 import DriveParameters as V2Parameters, transform_xml as v2_xml
from sim.multi_masterpi_production import MultiMasterPiProductionV2

PROFILE = 'masterpi_drive_friction_v3'


def wheel_input_normalized(value):
    """Signed legacy Board command magnitude; not a measured mm/s value."""
    if isinstance(value, bool) or not math.isfinite(value) or not -100 <= value <= 100:
        raise ValueError('wheel input must be finite in -100..100')
    return value / 100.


@dataclass(frozen=True)
class DriveParameters(V2Parameters):
    # Lower-bound representative of [0.30, 0.35); fixed BEFORE new measurements.
    # Not a unique estimate: motor scale and mechanism remain unidentifiable.
    start_resistance_fraction: float = .30

    def __post_init__(self):
        super().__post_init__()
        if not 0 < self.start_resistance_fraction < 1:
            raise ValueError('start resistance fraction must be inside (0,1)')

    @property
    def equivalent_loss_nm(self):
        return self.torque_cap_nm * self.start_resistance_fraction

    def record(self):
        r = super().record()
        r.update(profile=PROFILE, qualification='OBSERVATION_CONSTRAINED_UNIDENTIFIED',
            command_unit='signed legacy Board command / 100; linear duty-voltage hypothesis',
            observation='operator 2026-10-06 <=30 no motion; repository 2026-08-29 log reports motion at 35',
            equivalent_wheel_frictionloss_nm=self.equivalent_loss_nm,
            identified='effective start-resistance / full-command drive ratio only',
            unconfirmed=['installed stall torque', 'installed no-load RPM', 'PWM-voltage transfer',
                         'motor versus gearbox versus roller/floor loss split', 'static/kinetic difference'],
            loss_model='load-independent equivalent Coulomb joint loss; not floor sliding coefficient')
        r.pop('sha256')
        r['sha256'] = hashlib.sha256(json.dumps(r, sort_keys=True).encode()).hexdigest()
        return r


def transform_xml(xml, params):
    root = ET.fromstring(v2_xml(xml, params))
    for joint in root.iter('joint'):
        if any(joint.get('name', '').endswith(f'__wheel_{w}_joint') for w in ('fl','fr','rl','rr')):
            joint.set('frictionloss', str(params.equivalent_loss_nm))
    root.find("custom/text[@name='drive_profile']").set('data', PROFILE)
    return ET.tostring(root, encoding='unicode')


def build_world(scene, *, drive_profile, params=None, **kwargs):
    if drive_profile != PROFILE:
        raise ValueError('explicit '+PROFILE+' required')
    from sim.session_scenes import Scene
    from sim.masterpi_model_v3 import v3_hardware
    from sim.masterpi_robot_models import V3_DRAWING_HARDWARE_KEYS
    from sim.zone_cargo_contact import apply
    if not isinstance(scene, Scene) or not hasattr(scene, 'robot_transform'):
        raise ValueError('requires standard v3 Scene adapter')
    world = FrictionWorld.__new__(FrictionWorld)
    world.drive_parameters = params or DriveParameters()

    def transform(xml):
        xml = apply(scene.transform(xml), 'cargo_noslip_v1')
        xml = scene.robot_transform(xml, hardware=world.physical_params,
                                    calibrated_keys=world.calibration_parameters)
        return transform_xml(xml, world.drive_parameters)

    MultiMasterPiProductionV2.__init__(world, xml_transform=transform, **kwargs)
    hw = dict(world.physical_params)
    for key in V3_DRAWING_HARDWARE_KEYS:
        if key not in world.calibration_parameters:
            hw.pop(key, None)
    world.physical_params.update(v3_hardware(hw))
    world.calibration_status = 'OBSERVATION_CONSTRAINED_UNIDENTIFIED'
    world.drive_profile_record = world.drive_parameters.record()
    world.drive_profile_record['xml_sha256'] = hashlib.sha256(world.scene_xml.encode()).hexdigest()
    return world
