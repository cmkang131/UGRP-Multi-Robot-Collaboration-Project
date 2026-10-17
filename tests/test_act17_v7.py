import importlib.util
from pathlib import Path
import xml.etree.ElementTree as ET

ROOT=Path(__file__).resolve().parents[1]
spec=importlib.util.spec_from_file_location('act17_v7',ROOT/'scripts/act17_v7.py')
m=importlib.util.module_from_spec(spec);spec.loader.exec_module(m)


def test_all_v7_scenes_exclude_retired_cargo_and_preserve_authored_versions():
    for sid in m.SCENARIOS:
        data,path=m.scenario(sid)
        assert sid.endswith('_v7') and path.is_file()
        assert all(p['kind'] in (*m.KINDS,'long_beam') for p in data['eval']['setup']['placements'])


def test_color_adapter_changes_visual_bands_without_geometry_or_camera():
    raw='<mujoco><option noslip_iterations="0"/><worldbody><camera name="own" pos="1 2 3"/><body><geom name="cargo_beam_1__band_neg" size=".1 .2 .3"/><geom name="cargo_beam_1__band_pos" size=".4 .5 .6"/></body></worldbody></mujoco>'
    result=ET.fromstring(m.color_xml(raw))
    assert result.find('worldbody/camera').get('pos')=='1 2 3'
    assert result.find('.//geom').get('size')=='.1 .2 .3'
    assert result.find('.//geom').get('rgba')=='.02 .95 .60 1'
    assert result.find('option').get('noslip_iterations')=='0'
    assert result.find('custom/text').get('data')==m.SCENE


def test_color_enabled_profile_also_accepts_a_box_only_scene():
    result=ET.fromstring(m.color_xml('<mujoco><worldbody><geom name="box"/></worldbody></mujoco>'))
    assert result.find('worldbody/geom').attrib=={'name':'box'}
