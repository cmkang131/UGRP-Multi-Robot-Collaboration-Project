"""장면별 station/dock/footprint가 같은 팔 장착 위치를 사용한다."""
import math

import pytest

from sim.zone_own_scene_provider import own_scene
from sim.zone_masterpi_v3_scene import MAP_IDS
from sim.zone_model_conventions import convention, static_spawn_keepouts, station_offset
from harness.zone_team_footprint_v3 import team_footprint
from scripts.zone_teacher_v3 import TeacherStationsV3


def spec(name):
    return {'map': name, 'seed': 700, 'goal': {'A': {'cyan': 1}}, 'team_cargo': []}


@pytest.mark.parametrize('name', MAP_IDS)
def test_scene_dock_and_keepout_share_authored_positions(name):
    scene = own_scene(spec(name), 'cargo_noslip_v1')
    assert convention(scene)['station_radius_m'] == pytest.approx(.2032)
    keepouts = static_spawn_keepouts(scene.config['static_map'])
    spawns = scene.config['setup_only']['spawns'].values()
    assert sorted(k['center_m'] for k in keepouts) == sorted(p[:2] for p in spawns)
    assert all(k['radius_m'] == pytest.approx(.2182) for k in keepouts)


@pytest.mark.parametrize('kind', ['cyan', 'long_beam', 'heavy_crate'])
def test_station_footprint_teacher_share_model(kind):
    from harness.zone_team_footprint import grasps
    scene = own_scene(spec(MAP_IDS[0]), 'cargo_noslip_v1')
    teacher = TeacherStationsV3(scene)
    fp = team_footprint(scene, kind)
    for g in grasps(kind):
        x, y, yaw = station_offset(scene, kind, g.role)
        assert math.hypot(g.grip_xyz[0]-x, g.grip_xyz[1]-y) == pytest.approx(.2032)
        assert teacher.station(kind, g.role, (0., 0., 0.)) == pytest.approx((x, y, yaw))
        if g.role in fp.stations:
            assert fp.stations[g.role] == pytest.approx((x, y, yaw))
    assert fp.record()['robot_model'] == 'masterpi_v3'


def test_v2_conventions_unchanged():
    from harness.zone_team_footprint import team_footprint as old_footprint
    from sim.zone_start_dock import static_spawn_keepouts as old_keepouts
    scene = own_scene(spec('zone_wide_door_geometry_v2'), 'cargo_noslip_v1')
    static = scene.config['static_map']
    assert convention(scene)['station_radius_m'] == .155
    assert team_footprint(scene, 'long_beam').record() == old_footprint('long_beam').record()
    assert static_spawn_keepouts(static) == old_keepouts(static)
