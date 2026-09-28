"""새 장면만 v3를 선택하며 기존 장면/소스는 바꾸지 않는다. mj_forward 전용."""
import hashlib
import json
from pathlib import Path

import pytest

pytest.importorskip('mujoco')

from sim.zone_masterpi_v3_scene import MAP_IDS, MasterPiV3ZoneScene, scene_robot_model, static_map
from sim.zone_own_scene_provider import own_scene
from sim.multi_masterpi_production import build_multi_robot_xml


def spec(name):
    return {'map': name, 'seed': 700, 'goal': {'A': {'cyan': 1}}, 'team_cargo': []}


@pytest.fixture(autouse=True)
def no_physics(monkeypatch):
    import mujoco
    def forbidden(*args, **kwargs):
        raise AssertionError('정적 테스트는 mj_step을 호출할 수 없음')
    monkeypatch.setattr(mujoco, 'mj_step', forbidden)


@pytest.mark.parametrize('name', MAP_IDS)
def test_registered_v3_scene(name):
    import mujoco
    s = own_scene(spec(name), 'cargo_noslip_v1')
    assert isinstance(s, MasterPiV3ZoneScene)
    assert scene_robot_model(s) == 'masterpi_v3'
    public = static_map(name)
    assert public == s.config['static_map']
    assert not any('tag' in k.lower() or 'landmark' in k.lower() for k in public)
    xml = s.robot_transform(s.transform(build_multi_robot_xml(None, navigation_camera=True)))
    m = mujoco.MjModel.from_xml_string(xml)
    d = mujoco.MjData(m)
    mujoco.mj_forward(m, d)
    assert s.record()['scene_xml_sha256'] == hashlib.sha256(xml.encode()).hexdigest()
    import xml.etree.ElementTree as ET
    for node in ET.fromstring(xml).find('worldbody'):
        if node.get('name', '').endswith('__robot'):
            assert s.manifest['robot_xml_sha256'][node.get('name')] == hashlib.sha256(ET.tostring(node)).hexdigest()
    for rid in ('r1', 'r2', 'r3'):
        assert m.body(rid + '__arm_base').pos[0] == pytest.approx(.0482)
        assert m.camera(rid + '__nav_cam').id >= 0


def test_legacy_model_and_frozen_sources_unchanged():
    s = own_scene(spec('zone_wide_door_geometry_v2'), 'cargo_noslip_v1')
    assert scene_robot_model(s) == 'masterpi_v2'
    receipt = json.loads(Path('configs/masterpi_v3_scenes.json').read_text())
    for name, expected in receipt['legacy_files_sha256'].items():
        assert hashlib.sha256(Path(name).read_bytes()).hexdigest() == expected, name


def test_injected_v2_scene_cannot_impersonate_v3():
    old = own_scene(spec('zone_wide_door_geometry_v2'), 'cargo_noslip_v1')
    with pytest.raises(ValueError, match='registered v3'):
        own_scene(spec(MAP_IDS[0]), 'cargo_noslip_v1', old)
    old.config['robot_model'] = 'masterpi_v3'
    with pytest.raises(ValueError, match='cannot override'):
        scene_robot_model(old)
    new = own_scene(spec(MAP_IDS[0]), 'cargo_noslip_v1')
    new.config['robot_model'] = 'masterpi_v2'
    with pytest.raises(ValueError, match='identity changed'):
        scene_robot_model(new)


def test_hook_uses_actual_template_hardware(monkeypatch):
    from sim import multi_masterpi_production as multi
    from sim.zone_masterpi_v3_scene import build_world
    class FakeWorld:
        def __init__(self, xml_transform, **kwargs):
            self.physical_params = {'track_m': .133, 'wheelbase_m': .120}
            self.calibration_parameters = {'track_m': .133}
            self.scene_xml = xml_transform(build_multi_robot_xml(self.physical_params))
    monkeypatch.setattr(multi, 'MultiMasterPiProductionV2', FakeWorld)
    s = own_scene(spec(MAP_IDS[0]), 'cargo_noslip_v1')
    world = build_world(s, 'cargo_noslip_v1')
    assert world.physical_params['track_m'] == .133
    assert world.physical_params['wheelbase_m'] == .1188
    assert s.manifest['scene_xml_sha256'] == hashlib.sha256(world.scene_xml.encode()).hexdigest()


@pytest.mark.parametrize('name', MAP_IDS)
def test_v3_refuses_legacy_consumers_before_world_construction(name, monkeypatch):
    from harness.zone_own_team_host import OwnCamTeamHost
    from sim import multi_masterpi_production as multi
    def forbidden(**kwargs):
        pytest.fail('v2 소비자 거부 전에 물리 world를 생성하면 안 됨')
    monkeypatch.setattr(multi, 'MultiMasterPiProductionV2', forbidden)
    with pytest.raises(ValueError, match='v3 skill'):
        OwnCamTeamHost({**spec(name), 'contact_profile': 'cargo_noslip_v1'},
                       {'skill_module': 'harness.wrist_zone_skill_v9'}, root=Path.cwd(),
                       study_layer=lambda *a: None)
