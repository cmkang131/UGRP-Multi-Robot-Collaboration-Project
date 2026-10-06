"""Structural contract only; physical checks use the locked managed workflow."""
import xml.etree.ElementTree as ET
import pytest

pytest.importorskip('mujoco')

from sim.masterpi_drive_friction import DriveParameters, PROFILE, transform_xml
from sim.multi_masterpi_production import build_multi_robot_xml
from sim.masterpi_robot_models import v3_robot_xml_transform


def xml():
    return v3_robot_xml_transform({})(build_multi_robot_xml({}))


def test_new_profile_preserves_visuals_camera_mass_and_has_passive_rollers():
    before = ET.fromstring(xml())
    after = ET.fromstring(transform_xml(ET.tostring(before, encoding='unicode'), DriveParameters()))
    assert ET.tostring(before.find('option')) == ET.tostring(after.find('option'))
    assert [ET.tostring(e) for e in before.iter('camera')] == [ET.tostring(e) for e in after.iter('camera')]
    for rid in ('r1', 'r2', 'r3'):
        for wheel in ('fl', 'fr', 'rl', 'rr'):
            name = f'{rid}__wheel_{wheel}_body'
            original = before.find(f".//body[@name='{name}']")
            updated = after.find(f".//body[@name='{name}']")
            roller_bodies = updated.findall('body')
            assert len(roller_bodies) == 9
            mass = float(updated.find('inertial').get('mass'))
            mass += sum(float(g.get('mass')) for b in roller_bodies for g in b.findall('geom') if g.get('name').endswith('_contact'))
            assert mass == pytest.approx(float(original.find('inertial').get('mass')), abs=1e-12)
            assert all(b.find('joint').get('damping') == '0' for b in roller_bodies)
            assert updated.find(f"geom[@name='{rid}__wheel_{wheel}']").get('contype') == '0'
    assert after.find("custom/text[@name='drive_profile']").get('data') == PROFILE


def test_profile_rejects_non_v3_and_repeat_application():
    with pytest.raises(ValueError, match='nine v3'):
        transform_xml(build_multi_robot_xml({}), DriveParameters())
    with pytest.raises(ValueError):
        transform_xml(transform_xml(xml(), DriveParameters()), DriveParameters())


@pytest.mark.parametrize('kw', [{'no_load_rpm': 0}, {'torque_cap_nm': float('nan')}, {'sliding_mu': -1}])
def test_parameters_require_physical_values(kw):
    with pytest.raises(ValueError):
        DriveParameters(**kw)
