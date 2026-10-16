import xml.etree.ElementTree as ET
import pytest
from sim.warp_native_contact import apply, record

XML = '''<mujoco><option noslip_iterations="10" iterations="80"/>
<worldbody><body name="r1__robot"/></worldbody><contact>
<pair geom1="r1__left_finger" geom2="box" friction="3 3 .01 .001 .001" solreffriction="0 -6000"/>
<pair geom1="wheel" geom2="floor" friction=".9 .9 .01 .001 .001"/>
</contact><equality><weld active="false"/></equality></mujoco>'''


def test_default_preserves_source_bytes():
    assert apply(XML) == XML


def test_candidate_preserves_wheels_material_and_geometry():
    root = ET.fromstring(apply(XML, 'warp_native_contact_v2'))
    before = ET.fromstring(XML)
    assert ET.tostring(root.find('worldbody')) == ET.tostring(before.find('worldbody'))
    assert root.findall('contact/pair')[1].attrib == before.findall('contact/pair')[1].attrib
    assert root.findall('contact/pair')[0].get('friction') == before.findall('contact/pair')[0].get('friction')
    assert root.findall('contact/pair')[0].get('solreffriction') == '0 0'
    assert root.find('option').get('noslip_iterations') == '0'
    assert root.find('option').get('iterations') == '80'


def test_fail_closed_and_distinct_records():
    with pytest.raises(ValueError):
        apply(XML.replace('active="false"', 'active="true"'), 'warp_native_contact_v1')
    with pytest.raises(ValueError):
        apply(XML, 'typo')
    assert record('warp_native_contact_v1')['sha256'] != record('warp_native_fast_v1')['sha256']
