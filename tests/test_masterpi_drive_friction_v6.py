import xml.etree.ElementTree as ET
import numpy as np
import pytest
mujoco=pytest.importorskip('mujoco')
from sim.masterpi_drive_friction_v6 import DriveParameters, transform_xml
from sim.masterpi_drive_friction_v2 import transform_xml as old_xml
from sim.multi_masterpi_production import build_multi_robot_xml
from sim.masterpi_robot_models import v3_robot_xml_transform


def test_deadzone_continuity_and_signed_physical_endpoints():
    p=DriveParameters()
    assert p.effective_command([-.325,-.3,0,.2,.3,.325])==pytest.approx(np.zeros(6))
    assert p.effective_command([-1,1])==pytest.approx([-1,1])
    assert p.effective_command(.35)==pytest.approx(.025/.675)
    assert abs(p.effective_command(.325+1e-9))<2e-9
    for invalid in (np.nan,1.1):
        with pytest.raises(ValueError):p.effective_command(invalid)


def test_native_torque_and_passive_speed_loss_match_dc_equation_contacts_unchanged():
    p=DriveParameters();xml=v3_robot_xml_transform({})(build_multi_robot_xml({}))
    a,b=ET.fromstring(old_xml(xml,p)),ET.fromstring(transform_xml(xml,p))
    assert [ET.tostring(g) for g in a.iter('geom')]==[ET.tostring(g) for g in b.iter('geom')]
    assert ET.tostring(a.find('contact'))==ET.tostring(b.find('contact'))
    m=mujoco.MjModel.from_xml_string(ET.tostring(b,encoding='unicode'));d=mujoco.MjData(m)
    aid=m.actuator('r1__wheel_fl_drive').id;dof=m.jnt_dofadr[m.joint('r1__wheel_fl_joint').id]
    assert m.dof_frictionloss[dof]==0
    for u,w in [(0,2),(.3,2),(.35,0),(-.5,-3),(1,p.omega)]:
        d.ctrl[aid]=p.torque_cap_nm*p.effective_command(u);d.qvel[dof]=w;mujoco.mj_forward(m,d)
        assert d.qfrc_actuator[dof]==pytest.approx(p.torque_cap_nm*p.effective_command(u))
        assert d.qfrc_actuator[dof]+d.qfrc_passive[dof]==pytest.approx(p.torque_cap_nm*(p.effective_command(u)-w/p.omega))
        if abs(u)<=.325:assert d.actuator_force[aid]==0
    assert p.record()['installed_motor_and_floor_verified'] is False
