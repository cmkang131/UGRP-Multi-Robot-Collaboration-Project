"""Opt-in Stribeck joint constraint and native DC motor, not hardware calibration.

Stribeck Eq. (10): MuJoCo DC motor technical note. Velocity-dependent
frictionloss hook: google-deepmind/mujoco#1366 (public proposal, not an
upstream validated robot model). See experiment README for parameter sources.
"""
from dataclasses import dataclass
import hashlib
import json
import xml.etree.ElementTree as ET

import mujoco
import numpy as np

from sim.masterpi_drive_friction import FrictionWorld
from sim.masterpi_drive_friction_v2 import DriveParameters as V2Parameters, transform_xml as v2_xml
from sim.multi_masterpi_production import MultiMasterPiProductionV2

PROFILE = 'masterpi_drive_friction_v4'


@dataclass(frozen=True)
class DriveParameters(V2Parameters):
    nominal_voltage: float = 6.
    no_load_current_a: float = .1
    stall_current_a: float = 1.2
    start_resistance_fraction: float = .30
    # Unidentified transition scale: unchanged from MuJoCo 3.12's public
    # derivative/dcmotor.xml LuGre example, NOT fitted to these diagnostics.
    stribeck_rad_s: float = .1

    def __post_init__(self):
        super().__post_init__()
        if not 0 < self.kinetic_fraction < self.start_resistance_fraction < 1:
            raise ValueError('requires 0 < I0/Is < static fraction < 1')

    @property
    def kinetic_fraction(self):
        return self.no_load_current_a / self.stall_current_a

    @property
    def kinetic_loss_nm(self):
        return self.torque_cap_nm * self.kinetic_fraction

    @property
    def static_loss_nm(self):
        return self.torque_cap_nm * self.start_resistance_fraction

    @property
    def electrical_zero_torque_rad_s(self):
        # Datasheet no-load RPM already includes mechanical loss. Undo that
        # offset before adding the explicit joint loss (no double counting).
        return self.omega / (1 - self.kinetic_fraction)

    def friction_limit(self, velocity):
        v = np.asarray(velocity, dtype=float)
        if not np.isfinite(v).all():
            raise ValueError('non-finite wheel velocity')
        return self.kinetic_loss_nm + (self.static_loss_nm-self.kinetic_loss_nm) * np.exp(
            -(v/self.stribeck_rad_s)**2)

    def record(self):
        r = super().record()
        r.update(profile=PROFILE, qualification='STRIBECK_CANDIDATE_UNIDENTIFIED',
            actuator_model='MuJoCo native dcmotor, normalized Board input times 6V hypothesis',
            friction_model='Stribeck magnitude in native joint frictionloss, gamma=2; not LuGre state',
            implementation_source='https://github.com/google-deepmind/mujoco/issues/1366',
            implementation_scope='published hook proposal plus official Stribeck equation; not a validated MasterPi model',
            static_loss_nm=self.static_loss_nm, kinetic_loss_nm=self.kinetic_loss_nm,
            electrical_zero_torque_rad_s=self.electrical_zero_torque_rad_s,
            no_load_rpm_includes_loss=True,
            current_ratio_source='Hiwonder encoder TT: I0=0.1 A, Is=1.2 A at nominal 6V',
            current_ratio_assumption='all no-load mechanical loss is Coulomb; I0/Is only, no absolute current identification',
            unconfirmed=['installed motor identity', 'stall torque scale', 'Board PWM-voltage transfer',
                         'Stribeck speed', 'viscous versus dry loss split', 'load dependence'],
            stribeck_speed_source='MuJoCo 3.12.0 test/engine/testdata/derivative/dcmotor.xml: 0.1 rad/s')
        r.pop('sha256')
        r['sha256'] = hashlib.sha256(json.dumps(r, sort_keys=True).encode()).hexdigest()
        return r


def transform_xml(xml, params):
    root = ET.fromstring(v2_xml(xml, params))
    for joint in root.iter('joint'):
        if any(joint.get('name', '').endswith(f'__wheel_{w}_joint') for w in ('fl','fr','rl','rr')):
            joint.set('frictionloss', str(params.static_loss_nm))
    for act in root.find('actuator'):
        if act.get('name', '').endswith('_drive') and '__wheel_' in act.get('name', ''):
            # One scalar voltage input per wheel; preserve actuator order.
            name, joint = act.get('name'), act.get('joint')
            act.clear(); act.tag = 'dcmotor'
            act.attrib.update(name=name, joint=joint, input='voltage',
                nominal=f'{params.nominal_voltage} {params.torque_cap_nm} {params.electrical_zero_torque_rad_s}',
                saturation=f'{params.torque_cap_nm} 0 0', ctrllimited='true',
                ctrlrange=f'{-params.nominal_voltage} {params.nominal_voltage}')
    root.find("custom/text[@name='drive_profile']").set('data', PROFILE)
    return ET.tostring(root, encoding='unicode')


class StribeckWorld(FrictionWorld):
    def _physics_step_for(self, active, commands=None):
        if any(getattr(self, key, None) is not None for key in ('_fast_drive_kernel', '_mixed_engine', '_warehouse_crew')):
            raise RuntimeError('legacy drive integration incompatible with '+PROFILE)
        with self.physics_lock:
            # Base __init__ calls reset(), which steps before build_world can
            # finish. Resolve transmission DOFs from the already compiled model.
            if not hasattr(self, 'drive_wheel_dofs'):
                self.drive_wheel_dofs = np.array([self.model.jnt_dofadr[self.model.joint(
                    f'{rid}__wheel_{w}_joint').id] for rid in self.controllers for w in ('fl','fr','rl','rr')])
            if commands is not None:
                active.set_motor_commands(commands)
            for c in self.controllers.values():
                c.motor_state[:] = c.motor_command
                self.data.ctrl[c.wheel_act] = c.motor_command * self.drive_parameters.nominal_voltage
            # Physics constitutive law only: no state is passed to a policy,
            # no command dead-zone, no qpos/qvel reset or chassis wrench.
            self.model.dof_frictionloss[self.drive_wheel_dofs] = self.drive_parameters.friction_limit(
                self.data.qvel[self.drive_wheel_dofs])
            mujoco.mj_step(self.model, self.data)
            for c in self.controllers.values():
                c._presentation_dirty = True


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
    world.calibration_status = 'STRIBECK_CANDIDATE_UNIDENTIFIED'
    world.drive_profile_record = world.drive_parameters.record()
    world.drive_profile_record['xml_sha256'] = hashlib.sha256(world.scene_xml.encode()).hexdigest()
    return world
