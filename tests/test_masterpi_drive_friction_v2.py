"""Public wheel port contracts; no stepping, rendering or parameter fitting."""
import hashlib
import xml.etree.ElementTree as ET

import pytest
mujoco = pytest.importorskip('mujoco')
import numpy as np

from sim.masterpi_drive_friction_v2 import ASSETS, DriveParameters, PROFILE, transform_xml
from sim.masterpi_drive_friction import transform_xml as v1_transform
from sim.multi_masterpi_production import build_multi_robot_xml
from sim.masterpi_robot_models import v3_robot_xml_transform


def source():
    return v3_robot_xml_transform({})(build_multi_robot_xml({}))


def test_compiled_public_port_retains_total_mass_and_continuous_45_degree_axes():
    before = mujoco.MjModel.from_xml_string(source())
    after = mujoco.MjModel.from_xml_string(transform_xml(source(), DriveParameters()))
    assert sum(after.body_mass) == pytest.approx(sum(before.body_mass), abs=1e-10)
    passive = [i for i in range(after.njnt) if after.joint(i).name.endswith('_passive')]
    assert len(passive) == 3 * 4 * 9
    data = mujoco.MjData(after)
    mujoco.mj_kinematics(after, data)  # geometry only: does not integrate/contact-solve
    for jid in passive:
        assert not after.jnt_limited[jid]
        bid = after.jnt_bodyid[jid]
        axis = data.xmat[bid].reshape(3, 3) @ after.jnt_axis[jid]
        assert abs(axis[1]) == pytest.approx(2**-.5, abs=1e-9)
        assert all(after.body_inertia[bid] > 0)


def test_reference_mesh_unchanged_and_own_assembly_filter_does_not_hide_peers():
    assert hashlib.sha256((ASSETS/'fuji_roller.stl').read_bytes()).hexdigest() == '2bea3228aa5766e2ce42f4f4a46cdf4bc3e63802958fa7f0ffb9688d9393a424'
    root = ET.fromstring(transform_xml(source(), DriveParameters()))
    assert root.find("custom/text[@name='drive_profile']").get('data') == PROFILE
    pairs = {(e.get('body1'), e.get('body2')) for e in root.findall('contact/exclude')}
    assert ('r1__robot', 'r1__v3_wheel_fl_roller_0_body') in pairs
    assert ('r2__robot', 'r1__v3_wheel_fl_roller_0_body') not in pairs
    contacts = [g for g in root.iter('geom') if g.get('mesh') == 'fuji_roller_v2']
    assert len(contacts) == 108
    assert all(g.get('condim') == '3' and g.get('friction') == '0.8 0 0' for g in contacts)


def test_cameras_and_rendered_roller_endpoints_preserved():
    before = ET.fromstring(v1_transform(source(), DriveParameters()))
    after = ET.fromstring(transform_xml(source(), DriveParameters()))
    assert [ET.tostring(e) for e in before.iter('camera')] == [ET.tostring(e) for e in after.iter('camera')]
    for body in before.iter('body'):
        if '_roller_' not in body.get('name', ''):
            continue
        center = np.fromstring(body.get('pos'), sep=' ')
        visual = next(g for g in body.findall('geom') if not g.get('name').endswith('_contact'))
        expected = np.fromstring(visual.get('fromto'), sep=' ').reshape(2, 3) + center
        actual = after.find(f".//geom[@name='{visual.get('name')}']")
        np.testing.assert_allclose(np.fromstring(actual.get('fromto'), sep=' ').reshape(2, 3), expected, atol=1e-12)
