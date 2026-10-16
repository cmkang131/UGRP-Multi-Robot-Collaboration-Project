"""Regression: visiting a blocked door's mouth is not traversing that door."""
import importlib.util
import json
from pathlib import Path

HERE = Path(__file__).resolve().parent
spec = importlib.util.spec_from_file_location('p09_audit', HERE / 'audit.py')
audit = importlib.util.module_from_spec(spec)
spec.loader.exec_module(audit)


def test_blocked_narrow_mouth_visit_is_not_a_narrow_crossing():
    static = json.loads((audit.ROOT / 'maps/zones_final/zone_wide_two_doors_final_v1.json').read_text())
    # Visits the north door's western mouth, then crosses the southern wide door.
    path = [(1.8, .05, 0.), (1.8, -2.625, 0.), (2.2, -2.625, 0.), (2.5, -2.625, 0.)]
    assert audit.passage_crossings(path, static) == [
        {'passage': 'door_wide', 'direction': 'west_to_east', 'cross_coordinate_m': -2.625}]
    assert audit.passage_crossings(path[::-1], static) == [
        {'passage': 'door_wide', 'direction': 'east_to_west', 'cross_coordinate_m': -2.625}]


def test_orders_keep_counts_identity_and_unbound_robot_assignment():
    path = audit.ROOT / 'configs/zone_study_scenarios_v2/s1_normal_mixed_v2.json'
    scenario = json.loads(path.read_text())
    static = json.loads((audit.ROOT / 'maps/zones/zone_wide_door_geometry_v2.json').read_text())
    row = audit.extract(scenario, path, static)
    assert (row['order_line_count'], row['item_count']) == (6, 7)
    assert row['orders'][0]['identity'] == 'kind_fungible'
    assert row['orders'][0]['count'] == 2
    assert [i['item_id'] for i in row['items'] if i['order_id'] == 'order-1'] == ['cyan_1', 'cyan_2']
    assert row['orders'][4]['item_ids'] == ['beam_1']
    assert row['orders'][4]['order_id'] != row['orders'][4]['item_ids'][0]
    assert row['robot_spawns']['actor_assignment'] is None
    assert all(v is None for v in row['physical'].values())


def test_touching_centre_plane_and_retreating_is_not_a_crossing():
    static = json.loads((audit.ROOT / 'maps/zones_final/zone_wide_two_doors_final_v1.json').read_text())
    path = [(1.8, .05, 0.), (2.2, .05, 0.), (1.8, .05, 0.)]
    assert audit.passage_crossings(path, static) == []
    assert audit.passage_crossings(path[:2], static) == []
