"""Static native-motor and constitutive-law checks, no time integration."""
import xml.etree.ElementTree as ET
import numpy as np
import pytest

mujoco = pytest.importorskip('mujoco')
from sim.masterpi_drive_friction_v4 import DriveParameters, transform_xml
from sim.masterpi_drive_friction_v2 import transform_xml as v2_xml
from sim.multi_masterpi_production import build_multi_robot_xml
from sim.masterpi_robot_models import v3_robot_xml_transform


def test_native_dc_curve_includes_no_load_loss_once_and_preserves_contacts():
    p = DriveParameters()
    xml = v3_robot_xml_transform({})(build_multi_robot_xml({}))
    before, after = ET.fromstring(v2_xml(xml, p)), ET.fromstring(transform_xml(xml, p))
    assert [ET.tostring(g) for g in before.iter('geom')] == [ET.tostring(g) for g in after.iter('geom')]
    assert ET.tostring(before.find('contact')) == ET.tostring(after.find('contact'))
    m = mujoco.MjModel.from_xml_string(ET.tostring(after, encoding='unicode'))
    d = mujoco.MjData(m)
    aid = m.actuator('r1__wheel_fl_drive').id
    dof = m.jnt_dofadr[m.joint('r1__wheel_fl_joint').id]
    assert m.actuator_gaintype[aid] == mujoco.mjtGain.mjGAIN_DCMOTOR
    assert m.actuator_actnum[aid] == 0  # stateless motor; Stribeck constraint, not LuGre
    for u, omega in [(1, p.omega), (-1, -p.omega), (.3, 0), (.35, 0)]:
        d.ctrl[aid] = p.nominal_voltage*u
        d.qvel[dof] = omega
        mujoco.mj_forward(m, d)
        expected = p.torque_cap_nm*(u-omega/p.electrical_zero_torque_rad_s)
        assert d.actuator_force[aid] == pytest.approx(expected)
        if abs(u) == 1:
            assert abs(d.actuator_force[aid]) == pytest.approx(p.kinetic_loss_nm)
    assert p.torque_cap_nm*.3 == pytest.approx(p.static_loss_nm)
    assert p.torque_cap_nm*.35 > p.static_loss_nm
    assert p.record()['installed_motor_and_floor_verified'] is False


def test_stribeck_has_distinct_static_and_kinetic_limits_without_command_input():
    p = DriveParameters()
    assert p.kinetic_fraction == pytest.approx(1/12)
    assert p.static_loss_nm == pytest.approx(.03530394)
    assert p.kinetic_loss_nm == pytest.approx(.00980665)
    speeds = np.array([0, .05, .1, .2, 1])
    limits = p.friction_limit(speeds)
    assert limits[0] == p.static_loss_nm
    assert np.all(np.diff(limits) <= 0)
    assert limits[-1] == pytest.approx(p.kinetic_loss_nm)
    assert p.friction_limit(-speeds) == pytest.approx(limits)
    assert np.all(limits > 0)  # dissipative native constraint; no negative friction
    with pytest.raises(ValueError): p.friction_limit(float('nan'))
    with pytest.raises(ValueError): DriveParameters(no_load_current_a=1.2)


def test_reset_entry_updates_only_wheel_loss_and_voltage(monkeypatch):
    from contextlib import nullcontext
    from types import SimpleNamespace
    from sim.masterpi_drive_friction_v4 import StribeckWorld
    p = DriveParameters()
    xml = v3_robot_xml_transform({})(build_multi_robot_xml({}))
    m = mujoco.MjModel.from_xml_string(transform_xml(xml, p)); d = mujoco.MjData(m)
    world = StribeckWorld.__new__(StribeckWorld)
    world.model, world.data, world.drive_parameters, world.physics_lock = m, d, p, nullcontext()
    c = SimpleNamespace(wheel_act=np.array([m.actuator(f'r1__wheel_{w}_drive').id for w in ('fl','fr','rl','rr')]),
                        motor_command=np.array([.2, .3, .35, -.35]), motor_state=np.zeros(4))
    world.controllers = {'r1': c}
    monkeypatch.setattr(mujoco, 'mj_step', lambda m, d: None)  # no time integration
    d.xfrc_applied[:] = .123
    qpos, qvel = d.qpos.copy(), d.qvel.copy()
    world._physics_step_for(c)
    assert d.ctrl[c.wheel_act] == pytest.approx([1.2,1.8,2.1,-2.1])
    assert m.dof_frictionloss[world.drive_wheel_dofs] == pytest.approx([p.static_loss_nm]*4)
    assert np.array_equal(d.qpos, qpos) and np.array_equal(d.qvel, qvel)
    assert np.all(d.xfrc_applied == .123)
