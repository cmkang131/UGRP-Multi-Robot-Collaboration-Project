import xml.etree.ElementTree as ET
import numpy as np
import pytest
mujoco=pytest.importorskip('mujoco')
from sim.masterpi_drive_friction_v5 import transform_xml as old_xml
from sim.masterpi_drive_friction_v5_hard import DriveParameters, transform_xml
from sim.multi_masterpi_production import build_multi_robot_xml
from sim.masterpi_robot_models import v3_robot_xml_transform


def test_only_wheel_friction_impedance_changes():
    p=DriveParameters(); xml=v3_robot_xml_transform({})(build_multi_robot_xml({}))
    a,b=ET.fromstring(old_xml(xml,p)),ET.fromstring(transform_xml(xml,p))
    m0=mujoco.MjModel.from_xml_string(ET.tostring(a,encoding='unicode'))
    m1=mujoco.MjModel.from_xml_string(ET.tostring(b,encoding='unicode'))
    for rid in ('r1','r2','r3'):
        for w in ('fl','fr','rl','rr'):
            name=f'{rid}__wheel_{w}_joint'
            dof=m0.jnt_dofadr[m0.joint(name).id]
            assert m0.dof_solimp[dof,0]==pytest.approx(.9)
            assert m1.dof_solimp[dof,0]==pytest.approx(.9999)
            assert np.array_equal(m0.dof_solimp[dof,1:],m1.dof_solimp[dof,1:])
            b.find(f'.//joint[@name="{name}"]').attrib.pop('solimpfriction')
    b.find("custom/text[@name='drive_profile']").set('data','masterpi_drive_friction_v5')
    assert ET.tostring(a)==ET.tostring(b)
