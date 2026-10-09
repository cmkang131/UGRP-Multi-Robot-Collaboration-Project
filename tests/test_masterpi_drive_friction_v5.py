"""Static zero-band branch regression; no physics integration or fitting."""
import xml.etree.ElementTree as ET
import numpy as np
import pytest
pytest.importorskip('mujoco')
from sim.masterpi_drive_friction_v4 import DriveParameters as V4Parameters, transform_xml as v4_xml
from sim.masterpi_drive_friction_v5 import DriveParameters, transform_xml, PROFILE
from sim.multi_masterpi_production import build_multi_robot_xml
from sim.masterpi_robot_models import v3_robot_xml_transform


def test_numerical_stick_band_retains_static_limit_without_increasing_parameters():
    p, old = DriveParameters(), V4Parameters()
    for key, val in vars(old).items():
        assert getattr(p,key) == val
    speeds=np.array([-.1,-.01,0,.01,.1])
    assert p.friction_limit(speeds) == pytest.approx([old.static_loss_nm]*len(speeds))
    assert p.friction_limit([-.2,.2,-1,1]) == pytest.approx(old.friction_limit([-.2,.2,-1,1]))
    assert p.friction_limit(.01) > old.friction_limit(.01)


def test_v5_changes_no_compiled_motor_geometry_or_static_friction_values():
    p=DriveParameters(); xml=v3_robot_xml_transform({})(build_multi_robot_xml({}))
    old=ET.fromstring(v4_xml(xml,p)); new=ET.fromstring(transform_xml(xml,p))
    assert new.find("custom/text[@name='drive_profile']").get('data')==PROFILE
    new.find("custom/text[@name='drive_profile']").set('data','masterpi_drive_friction_v4')
    assert ET.tostring(new)==ET.tostring(old)
