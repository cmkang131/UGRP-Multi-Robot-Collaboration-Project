"""v98 render near-clip profile floor_light_nearclip_v1 (sim.final_pair_highpose_nearclip)."""
from types import SimpleNamespace
import xml.etree.ElementTree as ET

import pytest

from sim import final_pair_highpose_nearclip as nc


def test_apply_xml_sets_only_znear():
    xml = '<mujoco><visual><global offwidth="1280" offheight="720" /><map znear=".002" /></visual><worldbody/></mujoco>'
    root = ET.fromstring(nc.apply_xml(xml))
    assert root.find('visual/map').get('znear') == nc.ZNEAR_REL
    assert root.find('visual/global').attrib == {'offwidth': '1280', 'offheight': '720'}
    assert float(nc.ZNEAR_REL) * 11.112488 <= nc.NEAR_MAX_M


def test_apply_xml_adds_missing_map():
    assert ET.fromstring(nc.apply_xml('<mujoco/>')).find('visual/map').get('znear') == nc.ZNEAR_REL


def test_record_hash_is_stable_and_named():
    rec = nc.record()
    assert rec['id'] == 'floor_light_nearclip_v1' and rec['base_profile'] == 'floor_light_v1'
    assert rec['sha256'] == nc.sha256() and len(rec['sha256']) == 64
    assert rec['changes_physics'] is False


def test_wrap_requires_floor_light_and_records_hashes():
    with pytest.raises(ValueError):
        nc.wrap(SimpleNamespace(transform=lambda x: x, manifest={}))
    scene = SimpleNamespace(transform=lambda x: x, manifest={}, _render_profile_name='floor_light_v1')
    nc.wrap(scene)
    out = scene.transform('<mujoco><visual><map znear=".002"/></visual></mujoco>')
    assert 'znear="0.0004"' in out
    m = scene.manifest['render_nearclip']
    assert m['scene_xml_sha256_before_nearclip'] != m['scene_xml_sha256_after_nearclip']
    assert nc.wrap(scene) is scene


def test_scenes_context_restores_make_scene():
    from sim import final_pair_v3, final_pair_highpose_staged
    before = final_pair_v3.make_scene, final_pair_highpose_staged.make_scene
    with nc.scenes():
        assert final_pair_v3.make_scene is not before[0]
        assert final_pair_highpose_staged.make_scene is not before[1]
    assert (final_pair_v3.make_scene, final_pair_highpose_staged.make_scene) == before


def test_v98_backends_carry_nearclip_first():
    from sim.final_pair_highpose_clock import PhysicsBackend
    from sim.final_pair_highpose_staged import StagedBackend
    assert PhysicsBackend.__mro__[1] is nc.NearClip and StagedBackend.__mro__[1] is nc.NearClip


def test_audit_fails_closed():
    model = SimpleNamespace(vis=SimpleNamespace(map=SimpleNamespace(znear=.002)), stat=SimpleNamespace(extent=11.1125))
    with pytest.raises(RuntimeError):
        nc.audit(model)
    model.vis.map.znear = .0004
    assert nc.audit(model)['near_m'] == pytest.approx(.004445, abs=1e-6)
