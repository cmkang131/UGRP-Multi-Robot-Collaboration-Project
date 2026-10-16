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


def test_recording_preserves_short_pulse_boundaries():
    from scripts.warpfit import recording_ticks
    meta=dict(kind='drive',groups={'group0':['left-.06','forward-.25']},cases=[
        dict(id='left-.06',settle_s=1,duration_s=.06,tail_s=1),
        dict(id='forward-.25',settle_s=1,duration_s=.25,tail_s=1)])
    ticks=recording_ticks(meta,'group0',24000,.00025)
    assert all(round(t/.00025) in ticks for t in (1,1.06,1.25,2.06,2.25))
    assert all((b-a)%10==0 for a,b in zip(ticks,ticks[1:]))
    assert ticks[0]==0 and ticks[-1]==24000
