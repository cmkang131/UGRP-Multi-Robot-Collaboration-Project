"""v5 constitutive law with the official maximum wheel friction impedance.

Only the wheel joint friction solver impedance d0 changes. No fitted physical
parameter, native motor, roller, contact or observation changes. See #404 audit.
"""
from dataclasses import dataclass
import hashlib
import json
import xml.etree.ElementTree as ET
import mujoco
from sim.masterpi_drive_friction_v5 import DriveParameters as V5Parameters, transform_xml as v5_xml
from sim.masterpi_drive_friction_v4 import StribeckWorld
from sim.multi_masterpi_production import MultiMasterPiProductionV2
PROFILE='masterpi_drive_friction_v5_hard_v1'

@dataclass(frozen=True)
class DriveParameters(V5Parameters):
    def record(self):
        r=super().record()
        r.update(profile=PROFILE, qualification='HARD_FRICTION_CONSTRAINT_DIAGNOSTIC',
                 wheel_friction_impedance=0.9999,
                 solver_source='MuJoCo3.12 Modeling/Solver parameters: mjMAXIMP=0.9999',
                 solver_scope='numerical rigid static-friction approximation; no hardware stiffness claim')
        r.pop('sha256')
        r['sha256']=hashlib.sha256(json.dumps(r,sort_keys=True).encode()).hexdigest()
        return r


def transform_xml(xml,params):
    root=ET.fromstring(v5_xml(xml,params))
    for j in root.iter('joint'):
        if any(j.get('name','').endswith(f'__wheel_{w}_joint') for w in ('fl','fr','rl','rr')):
            j.set('solimpfriction','0.9999 0.95 0.001 0.5 2')
    root.find("custom/text[@name='drive_profile']").set('data',PROFILE)
    return ET.tostring(root,encoding='unicode')


def build_world(scene, *, drive_profile, params=None, **kwargs):
    if drive_profile != PROFILE:
        raise ValueError('explicit '+PROFILE+' required')
    from sim.session_scenes import Scene
    from sim.masterpi_model_v3 import v3_hardware
    from sim.masterpi_robot_models import V3_DRAWING_HARDWARE_KEYS
    from sim.zone_cargo_contact import apply
    if not isinstance(scene, Scene) or not hasattr(scene, 'robot_transform'):
        raise ValueError('requires standard v3 Scene adapter')
    world = StribeckWorld.__new__(StribeckWorld)
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
    if world.model.opt.integrator == mujoco.mjtIntegrator.mjINT_RK4:
        raise ValueError('per-step friction update requires Euler/implicit, not RK substeps')
    world.calibration_status = 'HARD_FRICTION_CONSTRAINT_DIAGNOSTIC'
    world.drive_profile_record = world.drive_parameters.record()
    world.drive_profile_record['xml_sha256'] = hashlib.sha256(world.scene_xml.encode()).hexdigest()
    return world
