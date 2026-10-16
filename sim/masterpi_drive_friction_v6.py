"""Opt-in observation dead-zone and affine DC shaft torque (Tao family).

D(u)=sign(u) max(|u|-b,0)/(1-b). Drive source torque is T0 D(u);
back-EMF plus lumped speed loss is joint damping T0/omega0. Thus the net
motor curve is T0*(D(u)-omega/omega0), including zero-command braking.
No explicit wheel dry loss: the empirical dead-zone replaces that model.
"""
from dataclasses import dataclass
import hashlib
import json
import xml.etree.ElementTree as ET
import numpy as np
import mujoco
from sim.masterpi_drive_friction import FrictionWorld
from sim.masterpi_drive_friction_v2 import DriveParameters as V2Parameters, transform_xml as v2_xml
from sim.multi_masterpi_production import MultiMasterPiProductionV2
PROFILE='masterpi_drive_friction_v6'

@dataclass(frozen=True)
class DriveParameters(V2Parameters):
    # User: <=30 stationary, >=35 moves; midpoint fixed before simulation.
    deadzone_fraction: float = .325

    def __post_init__(self):
        super().__post_init__()
        if not 0 < self.deadzone_fraction < 1:
            raise ValueError('deadzone must lie inside normalized input range')

    def effective_command(self, command):
        u=np.asarray(command,dtype=float)
        if not np.isfinite(u).all() or np.any(np.abs(u)>1):
            raise ValueError('requires finite normalized command in [-1,1]')
        return np.sign(u)*np.maximum(np.abs(u)-self.deadzone_fraction,0)/(1-self.deadzone_fraction)

    @property
    def speed_loss_nm_s(self):
        return self.torque_cap_nm/self.omega

    def record(self):
        r=super().record()
        r.update(profile=PROFILE, qualification='OBSERVATION_DEADZONE_UNCALIBRATED',
            actuator_model='native motor drive source T0*D(u) plus passive affine DC speed loss B*w',
            friction_model='empirical input dead-zone replaces wheel joint dry loss; roller bearing/contact retained',
            threshold_source='user 2026-10-06: <=30 rest, >=35 sustained; midpoint32.5/100, not identified under load',
            deadzone_source='Tao & Kokotovic1994; Wang, Su & Hong2004 Eq1 author-hosted full text',
            zero_command='zero active drive torque; passive electrical/lumped viscous braking remains',
            speed_loss_nm_s=self.speed_loss_nm_s,
            full_command_no_load_speed_mps=.0325*self.omega,
            unconfirmed=['installed TT motor identity and stall torque','PWM voltage mapping','actual speed curve',
                         'load-dependent threshold','back-drive/brake behavior','directional hysteresis'])
        r.pop('sha256'); r['sha256']=hashlib.sha256(json.dumps(r,sort_keys=True).encode()).hexdigest()
        return r


def transform_xml(xml,params):
    root=ET.fromstring(v2_xml(xml,params))
    for j in root.iter('joint'):
        if any(j.get('name','').endswith(f'__wheel_{w}_joint') for w in ('fl','fr','rl','rr')):
            j.set('frictionloss','0')
            j.set('damping',str(params.speed_loss_nm_s))
    for a in root.find('actuator'):
        if a.get('name','').endswith('_drive') and '__wheel_' in a.get('name',''):
            name,joint=a.get('name'),a.get('joint')
            a.clear();a.tag='motor'
            a.attrib.update(name=name,joint=joint,gear='1',ctrllimited='true',
                            ctrlrange=f'{-params.torque_cap_nm} {params.torque_cap_nm}')
    root.find("custom/text[@name='drive_profile']").set('data',PROFILE)
    return ET.tostring(root,encoding='unicode')


class DeadzoneWorld(FrictionWorld):
    def _physics_step_for(self, active, commands=None):
        if any(getattr(self,k,None) is not None for k in ('_fast_drive_kernel','_mixed_engine','_warehouse_crew')):
            raise RuntimeError('legacy drive incompatible with '+PROFILE)
        with self.physics_lock:
            if commands is not None:
                active.set_motor_commands(commands)
            for c in self.controllers.values():
                c.motor_state[:]=c.motor_command
                self.data.ctrl[c.wheel_act]=self.drive_parameters.torque_cap_nm*self.drive_parameters.effective_command(c.motor_command)
            mujoco.mj_step(self.model,self.data)
            for c in self.controllers.values(): c._presentation_dirty=True


def build_world(scene, *, drive_profile, params=None, **kwargs):
    if drive_profile != PROFILE:
        raise ValueError('explicit '+PROFILE+' required')
    from sim.session_scenes import Scene
    from sim.masterpi_model_v3 import v3_hardware
    from sim.masterpi_robot_models import V3_DRAWING_HARDWARE_KEYS
    from sim.zone_cargo_contact import apply
    if not isinstance(scene, Scene) or not hasattr(scene, 'robot_transform'):
        raise ValueError('requires standard v3 Scene adapter')
    world = DeadzoneWorld.__new__(DeadzoneWorld)
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
    world.calibration_status = 'OBSERVATION_DEADZONE_UNCALIBRATED'
    world.drive_profile_record = world.drive_parameters.record()
    world.drive_profile_record['xml_sha256'] = hashlib.sha256(world.scene_xml.encode()).hexdigest()
    return world
