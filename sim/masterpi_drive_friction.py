"""Opt-in native passive-roller drive. Frozen wrench models are never edited.

Structural candidate, NOT a calibrated MasterPi digital twin. Parameter sources
and limitations: experiments/2026-10-06-drive-friction/README.md.
"""
from __future__ import annotations

from dataclasses import asdict, dataclass
import hashlib
import json
import math
import xml.etree.ElementTree as ET

import mujoco
import numpy as np

from sim.multi_masterpi_production import MultiMasterPiProductionV2

PROFILE = 'masterpi_drive_friction_v1'


@dataclass(frozen=True)
class DriveParameters:
    # Hiwonder TT product 150 rpm; installed MasterPi motor identity unconfirmed.
    no_load_rpm: float = 150.0
    # Hiwonder encoder TT analogue: 1.2 kgf cm. NOT a confirmed stall rating.
    # Used only as an exploratory actuator force cap, not a hardware claim.
    torque_cap_nm: float = 1.2 * 9.80665 / 100
    # MuJoCo's default sliding coefficient, not measured rubber/floor friction.
    sliding_mu: float = 1.0

    def __post_init__(self):
        for key, value in asdict(self).items():
            if not math.isfinite(value) or value <= 0:
                raise ValueError(f'{key} must be finite and positive')

    @property
    def omega(self):
        return self.no_load_rpm * 2 * math.pi / 60

    def record(self):
        data = {'profile': PROFILE, 'parameters': asdict(self),
                'qualification': 'STRUCTURAL_ONLY_UNCALIBRATED',
                'installed_motor_and_floor_verified': False,
                'actuator_model': 'bounded affine torque-speed, zero-command electrical brake',
                'roller_geometry': 'unchanged v3 visual capsules, 9 passive hinges/wheel',
                'roller_bearing': 'ideal frictionless', 'wheel_mass': 'legacy 50g, uniform-density split'}
        data['sha256'] = hashlib.sha256(json.dumps(data, sort_keys=True).encode()).hexdigest()
        return data


def transform_xml(xml: str, params: DriveParameters) -> str:
    """Make the existing v3 rollers physical; retain all visible geometry/cameras.

    Torque acts only at four wheel hinges. Isotropic sliding friction on freely
    rotating 45-degree rollers generates mecanum traction without a body wrench.
    """
    root = ET.fromstring(xml)
    for robot in root.findall('worldbody/body'):
        name = robot.get('name', '')
        if not name.endswith('__robot'):
            continue
        prefix = name[:-len('robot')]
        for wheel in ('fl', 'fr', 'rl', 'rr'):
            body = robot.find(f"body[@name='{prefix}wheel_{wheel}_body']")
            if body is None:
                raise ValueError('requires complete namespaced v3 robot')
            support = body.find(f"geom[@name='{prefix}wheel_{wheel}']")
            support.set('contype', '0'); support.set('conaffinity', '0')
            joint = body.find('joint')
            joint.set('damping', '0')  # ideal bearing, no unmeasured extra brake
            joint.set('frictionloss', '0')
            rollers = [g for g in body.findall('geom') if '_roller_' in g.get('name', '')]
            if len(rollers) != 9 or any(g.get('type') != 'capsule' for g in rollers):
                raise ValueError('profile requires the unchanged nine v3 capsule rollers')
            inertial = body.find('inertial')
            total_mass = float(inertial.get('mass'))
            radius, half_width = map(float, support.get('size').split())
            from sim.masterpi_geometry_v3 import WHEEL_HUB_DIAMETER_M
            hub_r = WHEEL_HUB_DIAMETER_M / 2
            hub_volume = math.pi * hub_r**2 * 2 * half_width
            volumes = []
            for visual in rollers:
                ends = np.array(list(map(float, visual.get('fromto').split()))).reshape(2, 3)
                rr = float(visual.get('size'))
                volumes.append(math.pi * rr**2 * np.linalg.norm(ends[1]-ends[0]) + 4/3*math.pi*rr**3)
            density = total_mass / (hub_volume + sum(volumes))
            hub_mass = density * hub_volume
            inertial.set('mass', str(hub_mass))
            transverse = hub_mass * (3*hub_r**2+(2*half_width)**2)/12
            inertial.set('diaginertia', f'{transverse} {hub_mass*hub_r**2/2} {transverse}')
            for visual, volume in zip(rollers, volumes):
                ends = np.array(list(map(float, visual.get('fromto').split()))).reshape(2, 3)
                centre = ends.mean(axis=0)
                axis = ends[1]-ends[0]; axis /= np.linalg.norm(axis)
                child = ET.SubElement(body, 'body', name=visual.get('name')+'_body',
                                      pos=' '.join(map(str, centre)))
                ET.SubElement(child, 'joint', name=visual.get('name')+'_passive', type='hinge',
                              axis=' '.join(map(str, axis)), damping='0', frictionloss='0', armature='0')
                body.remove(visual)
                visual.set('fromto', ' '.join(map(str, (ends-centre).ravel())))
                child.append(visual)
                ET.SubElement(child, 'geom', name=visual.get('name')+'_contact', type='capsule',
                    fromto=visual.get('fromto'), size=visual.get('size'), mass=str(density*volume),
                    rgba='0 0 0 0', group='3', contype='2', conaffinity='1', condim='3',
                    priority='2', friction=f'{params.sliding_mu} 0 0')
            act = root.find(f"actuator/velocity[@name='{prefix}wheel_{wheel}_drive']")
            if act is None:
                raise ValueError('missing native wheel actuator')
            # kv=cap/omega is the classical linear DC torque-speed slope. This
            # is not an encoder feedback loop in the robot policy.
            act.set('kv', str(params.torque_cap_nm/params.omega))
            act.set('ctrlrange', f'{-params.omega} {params.omega}')
            act.set('forcerange', f'{-params.torque_cap_nm} {params.torque_cap_nm}')
    custom = root.find('custom')
    if custom is None:
        custom = ET.SubElement(root, 'custom')
    if custom.find("text[@name='drive_profile']") is not None:
        raise ValueError('drive profile already installed')
    ET.SubElement(custom, 'text', name='drive_profile', data=PROFILE)
    return ET.tostring(root, encoding='unicode')


class FrictionWorld(MultiMasterPiProductionV2):
    """Explicit diagnostic world; does not silently install on a legacy runner."""

    def _physics_step_for(self, active, commands=None):
        if getattr(self, '_fast_drive_kernel', None) is not None:
            raise RuntimeError('legacy wrench speedups are incompatible with '+PROFILE)
        if getattr(self, '_mixed_engine', None) or getattr(self, '_warehouse_crew', None):
            raise RuntimeError('crew/mixed executor integration requires separate acceptance')
        with self.physics_lock:
            if commands is not None:
                active.set_motor_commands(commands)
            for c in self.controllers.values():
                c.motor_state[:] = c.motor_command
                self.data.ctrl[c.wheel_act] = c.motor_command * self.drive_parameters.omega
            # Do not write xfrc_applied/qfrc_applied or base qpos/qvel. Contacts
            # alone propel the chassis; external diagnostic forces remain valid.
            mujoco.mj_step(self.model, self.data)
            for c in self.controllers.values():
                c._presentation_dirty = True


def build_world(scene, *, drive_profile: str, params=None, **kwargs):
    if drive_profile != PROFILE:
        raise ValueError('explicit '+PROFILE+' required')
    from sim.session_scenes import Scene
    from sim.masterpi_model_v3 import v3_hardware
    from sim.masterpi_robot_models import V3_DRAWING_HARDWARE_KEYS
    from sim.zone_cargo_contact import apply
    if not isinstance(scene, Scene) or not hasattr(scene, 'robot_transform'):
        raise ValueError('requires a standard v3 Scene adapter')
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
    world.calibration_status = 'STRUCTURAL_ONLY_UNCALIBRATED'
    world.drive_profile_record = world.drive_parameters.record()
    world.drive_profile_record['xml_sha256'] = hashlib.sha256(world.scene_xml.encode()).hexdigest()
    return world
