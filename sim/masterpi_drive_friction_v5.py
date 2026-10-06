"""Karnopp zero-speed band around v4's source-qualified Stribeck constraint.

Static saturation within a velocity band, Stribeck sliding outside:
Kirk Roffi (2024) MATLAB File Exchange 155462; Song & Smedley (2010).
Native soft constraints replace their single-body force saturation; see README.
"""
from dataclasses import dataclass
import hashlib
import json
import xml.etree.ElementTree as ET
import numpy as np
import mujoco

from sim.masterpi_drive_friction_v4 import DriveParameters as V4Parameters, StribeckWorld, transform_xml as v4_xml
from sim.multi_masterpi_production import MultiMasterPiProductionV2

PROFILE = 'masterpi_drive_friction_v5'


@dataclass(frozen=True)
class DriveParameters(V4Parameters):
    # Reuse the already fixed 0.1 rad/s scale. Numerical zero-velocity band,
    # not an identified bearing parameter or an input-command threshold.
    zero_band_rad_s: float = .1

    def friction_limit(self, velocity):
        sliding = super().friction_limit(velocity)
        return np.where(np.abs(velocity) <= self.zero_band_rad_s, self.static_loss_nm, sliding)

    def record(self):
        r = super().record()
        r.update(profile=PROFILE, qualification='KARNOPP_BAND_CANDIDATE_UNIDENTIFIED',
            friction_model='Karnopp zero-velocity band with Stribeck sliding and native soft static constraint',
            static_branch='native constraint bounded by Ts for abs(w)<=DV; not explicit qvel reset',
            zero_band_source='unchanged v4 reference 0.1 rad/s used as numerical DV; unmeasured',
            karnopp_source='https://www.mathworks.com/matlabcentral/fileexchange/155462-karnopp-s-model-stick-slip-friction-dynamics-in-simulink',
            adaptation='single-body force cancellation delegated to coupled native joint constraint; soft sticking approximation')
        r['unconfirmed'] = r['unconfirmed'] + ['numerical zero-band sensitivity']
        r.pop('sha256')
        r['sha256'] = hashlib.sha256(json.dumps(r, sort_keys=True).encode()).hexdigest()
        return r


def transform_xml(xml, params):
    root = ET.fromstring(v4_xml(xml, params))
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
    world.calibration_status = 'KARNOPP_BAND_CANDIDATE_UNIDENTIFIED'
    world.drive_profile_record = world.drive_parameters.record()
    world.drive_profile_record['xml_sha256'] = hashlib.sha256(world.scene_xml.encode()).hexdigest()
    return world
