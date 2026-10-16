"""Observation translation contracts; no simulation integration or fitting."""
import xml.etree.ElementTree as ET
import pytest
mujoco = pytest.importorskip('mujoco')
from sim.masterpi_drive_friction_v3 import DriveParameters, transform_xml, wheel_input_normalized
from sim.masterpi_drive_friction_v2 import transform_xml as v2_xml
from sim.multi_masterpi_production import build_multi_robot_xml
from sim.masterpi_robot_models import v3_robot_xml_transform


def test_threshold_is_joint_loss_not_a_command_clamp_or_floor_change():
    p=DriveParameters()
    xml=v3_robot_xml_transform({})(build_multi_robot_xml({}))
    before=ET.fromstring(v2_xml(xml,p)); after=ET.fromstring(transform_xml(xml,p))
    m=mujoco.MjModel.from_xml_string(ET.tostring(after,encoding='unicode'))
    wheels=[m.joint(f'{r}__wheel_{w}_joint').id for r in ('r1','r2','r3') for w in ('fl','fr','rl','rr')]
    assert list(m.dof_frictionloss[m.jnt_dofadr[wheels]])==pytest.approx([.03530394]*12)
    assert [ET.tostring(g) for g in before.iter('geom')]==[ET.tostring(g) for g in after.iter('geom')]
    assert ET.tostring(before.find('actuator'))==ET.tostring(after.find('actuator'))
    for q in (20,30):
        assert p.torque_cap_nm*wheel_input_normalized(q) <= p.equivalent_loss_nm
    assert p.torque_cap_nm*wheel_input_normalized(35) > p.equivalent_loss_nm
    assert p.record()['installed_motor_and_floor_verified'] is False


def test_command_units_and_invalid_inputs():
    assert [wheel_input_normalized(x) for x in (-100,20,30,35,50,100)]==[-1,.2,.3,.35,.5,1]
    for v in (float('nan'),float('inf'),101,True):
        with pytest.raises(ValueError): wheel_input_normalized(v)
    with pytest.raises(ValueError): DriveParameters(start_resistance_fraction=1)
