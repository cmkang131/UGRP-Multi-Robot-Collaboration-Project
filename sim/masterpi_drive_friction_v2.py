"""Opt-in FUJI public barrel-roller model port; frozen v1 is unchanged.

Geometry/parameters: DaiGuard/fuji_mecanum at 646431a5 (MIT).
The model underlies the TIAGo paper's wheel geometry, not a MasterPi validation.
See assets/masterpi_drive_friction_v2/source.json and experiment README.
"""
from dataclasses import dataclass
import hashlib
import json
import math
from pathlib import Path
import xml.etree.ElementTree as ET

import mujoco
import numpy as np

from sim.masterpi_drive_friction import (
    DriveParameters as V1Parameters, FrictionWorld, transform_xml as v1_transform,
)
from sim.multi_masterpi_production import MultiMasterPiProductionV2

PROFILE = 'masterpi_drive_friction_v2'
ASSETS = Path(__file__).resolve().parent / 'assets/masterpi_drive_friction_v2'
SOURCE = json.loads((ASSETS / 'source.json').read_text())


@dataclass(frozen=True)
class DriveParameters(V1Parameters):
    sliding_mu: float = SOURCE['roller_sliding_friction']

    def record(self):
        record = super().record()
        record.update(profile=PROFILE, public_model=SOURCE,
            roller_geometry='unmodified FUJI barrel mesh; uniform 65/205 scale; MasterPi 9 rollers',
            roller_bearing='FUJI damping/frictionloss scaled with mass*length^2',
            wheel_mass='legacy 50g; FUJI hub:roller mass proportions at 9 rollers',
            self_collision='roller versus own robot excluded, matching source assembly self_collide=false',
            qualification='PUBLIC_MODEL_PORT_UNCALIBRATED')
        record.pop('sha256')
        record['sha256'] = hashlib.sha256(json.dumps(record, sort_keys=True).encode()).hexdigest()
        return record


def transform_xml(xml, params):
    """Keep MasterPi visuals/cameras; replace v1 capsule contacts with public mesh.

    The source wheel axis is X; MasterPi's is Y. Rollers remain 45-degree
    continuous passive hinges. Only size, count, assembly mass and mounting
    coordinates differ. MuJoCo solves contacts; no ground-truth control.
    """
    mesh = ASSETS / 'fuji_roller.stl'
    if hashlib.sha256(mesh.read_bytes()).hexdigest() != SOURCE['mesh_sha256']:
        raise ValueError('FUJI reference mesh hash mismatch')
    root = ET.fromstring(v1_transform(xml, params))
    from sim.masterpi_geometry_v3 import OFFICIAL_WHEEL_DIAMETER_M, WHEEL_ROLLER_COUNT
    scale = OFFICIAL_WHEEL_DIAMETER_M / (2 * SOURCE['source_radius_m'])
    count = WHEEL_ROLLER_COUNT
    asset = root.find('asset')
    if asset is None:
        asset = ET.SubElement(root, 'asset')
    ET.SubElement(asset, 'mesh', name='fuji_roller_v2', file=str(mesh),
                  scale=f'{scale} {scale} {scale}')
    contact = root.find('contact')
    if contact is None:
        contact = ET.SubElement(root, 'contact')
    for robot in root.findall('worldbody/body'):
        if not robot.get('name', '').endswith('__robot'):
            continue
        prefix = robot.get('name')[:-len('robot')]
        assembly = [b for b in (robot, *robot.iter('body'))
                    if '_roller_' not in b.get('name', '')]
        assembly = {b.get('name'): b for b in assembly}
        for wheel, handed in zip(('fl', 'fr', 'rl', 'rr'), (1, -1, -1, 1)):
            body = robot.find(f"body[@name='{prefix}wheel_{wheel}_body']")
            children = body.findall('body')
            if len(children) != count:
                raise ValueError('MasterPi roller count mismatch')
            total_mass = float(body.find('inertial').get('mass')) + sum(
                float(g.get('mass')) for b in children for g in b.findall('geom')
                if g.get('name', '').endswith('_contact'))
            mass_scale = total_mass / (SOURCE['hub_mass_kg'] + count * SOURCE['roller_mass_kg'])
            inertia_scale = mass_scale * scale**2
            hub = body.find('inertial')
            hub.set('mass', str(SOURCE['hub_mass_kg'] * mass_scale))
            ixx, iyy, izz = SOURCE['hub_inertia_kg_m2']
            hub.set('diaginertia', ' '.join(str(v * inertia_scale) for v in (iyy, ixx, izz)))
            for i, child in enumerate(children):
                # Keep the original visible shapes at exactly their old poses.
                old_center = np.fromstring(child.get('pos'), sep=' ')
                for geom in list(child.findall('geom')):
                    child.remove(geom)
                    if geom.get('name', '').endswith('_contact'):
                        continue
                    ends = np.fromstring(geom.get('fromto'), sep=' ').reshape(2, 3)
                    geom.set('fromto', ' '.join(map(str, (ends + old_center).ravel())))
                    body.append(geom)
                phase = 2 * math.pi * i / count
                radial = np.array([math.cos(phase), 0., math.sin(phase)])
                tangent = np.array([-math.sin(phase), 0., math.cos(phase)])
                axis = (handed * tangent - np.array([0., 1., 0.])) / math.sqrt(2)
                rot = np.column_stack((axis, radial, np.cross(axis, radial)))
                quat = np.zeros(4)
                mujoco.mju_mat2Quat(quat, rot.ravel())
                child.set('pos', ' '.join(map(str, radial * SOURCE['roller_ring_radius_m'] * scale)))
                child.set('quat', ' '.join(map(str, quat)))
                joint = child.find('joint')
                joint.set('axis', '1 0 0')
                joint.set('limited', 'false')
                joint.set('damping', str(SOURCE['roller_damping'] * inertia_scale))
                joint.set('frictionloss', str(SOURCE['roller_frictionloss'] * inertia_scale))
                ET.SubElement(child, 'inertial', pos='0 0 0',
                    mass=str(SOURCE['roller_mass_kg'] * mass_scale),
                    diaginertia=' '.join(str(v * inertia_scale) for v in SOURCE['roller_inertia_kg_m2']))
                ET.SubElement(child, 'geom', name=child.get('name')+'_contact', type='mesh',
                    mesh='fuji_roller_v2', mass='0', rgba='0 0 0 0', group='3',
                    contype='2', conaffinity='1', condim='3', priority='2',
                    friction=f'{params.sliding_mu} 0 0')
                # SDF's source assembly disables self collision. In MuJoCo a
                # passive child adds a body level, so parent filtering alone
                # no longer excludes contacts with the chassis/motor housing.
                # Preserve other robots, cargo and environment interactions.
                for name in assembly:
                    ET.SubElement(contact, 'exclude', body1=name, body2=child.get('name'))
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
    world.calibration_status = 'PUBLIC_MODEL_PORT_UNCALIBRATED'
    world.drive_profile_record = world.drive_parameters.record()
    world.drive_profile_record['xml_sha256'] = hashlib.sha256(world.scene_xml.encode()).hexdigest()
    return world
