"""Non-physical tests for the two-robot navigation-gate composition."""
import hashlib
import json
from pathlib import Path

import numpy as np
import pytest

from harness import e2ewarp_nav_gate as gate


def calibration(**overrides):
    value = dict(schema=gate.CALIBRATION_SCHEMA, measured=True, measured_n=40,
                 source_sha='a' * 40,
                 constants=dict(forward_m_per_pct_s=0.0095, yaw_deg_per_pct_s=1.25))
    value.update(overrides)
    return value


def write_calibration(tmp_path, value=None):
    path = tmp_path / 'calibration.json'
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value if value is not None else calibration()))
    return path


def test_pair_lane_spawns_move_r1_r2_to_the_wide_door_lane():
    scene = {'r1': (-0.925, -2.25, 0.0323, 0.0),
             'r2': (-0.925, -0.85, 0.0323, 0.0),
             'r3': (-0.925, 0.55, 0.0323, 0.0)}
    spawns = gate.pair_lane_spawns(scene)
    assert set(spawns) == {'r1', 'r2'}
    assert spawns['r1'][:2] == [-0.925, -2.375]
    assert spawns['r2'][:2] == [-0.925, -2.875]
    assert spawns['r1'][2:] == [0.0323, 0.0]
    with pytest.raises(ValueError):
        gate.pair_lane_spawns({'r1': (0, 0, 0, 0)})


def test_nav_orders_keep_only_the_two_robot_zone_b_order():
    orders = [{'order_id': 'order-1', 'kind': 'long_beam', 'required_robots': 2,
               'destination_zone': 'B'},
              {'order_id': 'order-2', 'kind': 'cyan', 'required_robots': 1,
               'destination_zone': 'A'},
              {'order_id': 'order-3', 'kind': 'red', 'required_robots': 2,
               'destination_zone': 'C'}]
    kept = gate.nav_orders(orders)
    assert [o['order_id'] for o in kept] == ['order-1']
    with pytest.raises(ValueError):
        gate.nav_orders([orders[1]])


def test_calibration_requires_measured_artifact(tmp_path):
    record = gate.load_calibration(write_calibration(tmp_path))
    assert record['constants']['forward_m_per_pct_s'] == 0.0095
    assert len(record['sha256']) == 64
    with pytest.raises(ValueError, match='MISSING'):
        gate.load_calibration(tmp_path / 'absent.json')


@pytest.mark.parametrize('value,message', [
    (calibration(measured=False), 'NOT_MEASURED'),
    (calibration(schema='other'), 'SCHEMA_MISMATCH'),
    (calibration(measured_n=0), 'MEASURED_N_REQUIRED'),
    (calibration(source_sha='short'), 'SOURCE_SHA_REQUIRED'),
    (calibration(constants=dict(forward_m_per_pct_s=0.0, yaw_deg_per_pct_s=1.0)),
     'CONSTANT_INVALID'),
    (calibration(constants=dict(forward_m_per_pct_s=0.01, yaw_deg_per_pct_s=-1.0)),
     'CONSTANT_INVALID'),
])
def test_calibration_fails_closed(tmp_path, value, message):
    with pytest.raises(ValueError, match=message):
        gate.load_calibration(write_calibration(tmp_path, value))


def test_navigation_factory_builds_self_centric_navigation(tmp_path):
    path = write_calibration(tmp_path)
    nav = gate.navigation_factory('r1', {'destination_zone': 'B'},
                                  calibration=gate.load_calibration(path))
    assert nav.ready is True
    assert nav.destination_kind == 'zone_B'
    # No observation yet: memory empty -> the wheel hold, never an arrival claim.
    row = nav.command(0.0)
    assert row['wheels'] == [0.0] * 4
    assert nav._drive_plan()['reason'] == 'no_destination'
    with pytest.raises(ValueError):
        gate.navigation_factory('r3', {})


def valid_queue(**overrides):
    queue = dict(nav_scene=gate.NAV_SCENARIO, nav_map='zone_wide_two_doors_final_v3',
                 nav_robots=list(gate.ROBOTS), nav_spawn_y=dict(gate.LANE_Y),
                 nav_destination_kind=gate.DESTINATION_KIND, nav_static_map_input=False,
                 nav_cargo_spawned=False, nav_sim_budget_s=60.0, sim_budget_s=60.0,
                 nav_calibration=dict(sha256='b' * 64, source_sha='a' * 40,
                                      constants=dict(forward_m_per_pct_s=0.0095,
                                                     yaw_deg_per_pct_s=1.25)))
    queue.update(overrides)
    return queue


def test_gate_queue_accepts_the_lane_scene():
    assert gate.validate_gate_queue(valid_queue())['nav_scene'] == gate.NAV_SCENARIO


@pytest.mark.parametrize('overrides,message', [
    (dict(nav_scene='s1_normal_mixed_v7'), 'SCENE_MISMATCH'),
    (dict(nav_map='zone_wide_door_geometry_v3'), 'MAP_MISMATCH'),
    (dict(nav_sim_budget_s=1800.0, sim_budget_s=1800.0), 'SIM_BUDGET_INVALID'),
    (dict(sim_budget_s=30.0), 'SIM_BUDGET_MISMATCH'),
    (dict(nav_static_map_input=True), 'INPUT_BOUNDARY'),
    (dict(nav_spawn_y=dict(gate.LANE_Y, r1=-2.25)), 'SPAWN_LANE_MISMATCH'),
    (dict(nav_calibration={'sha256': 'x'}), 'CALIBRATION_SHA_REQUIRED'),
])
def test_gate_queue_rejects_non_compliant_settings(overrides, message):
    with pytest.raises(ValueError, match=message):
        gate.validate_gate_queue(valid_queue(**overrides))


def test_eval_geometry_is_eval_only():
    scene = type('Scene', (), {})()
    scene.config = dict(scenario_setup=dict(scenario_id='s7'), static_map=dict(
        map_id='zone_wide_two_doors_final_v3',
        regions={'zone_B': dict(center_m=[4.6, -2.1], half_extents_m=[.3, .7])}))
    spawns = {'r1': [-0.925, -2.375, .0323, 0.], 'r2': [-0.925, -2.875, .0323, 0.]}
    record = gate.eval_geometry(scene, spawns, {'r1': 10, 'r2': 20})
    assert record['eval_only'] is True
    assert record['destination']['center_m'] == [4.6, -2.1]
    assert record['robot_qpos_adr'] == {'r1': 10, 'r2': 20}


def test_recount_recomputes_arrival_from_raw_state(tmp_path):
    from scripts import e2ewarp_nav_recount as recount
    run = tmp_path / 'run'
    (run / 'world-00').mkdir(parents=True)
    nq = 30
    ticks = 5
    qpos = np.zeros((ticks, 1, nq))
    # r1 starts at (-0.925,-2.375) and ends inside zone B; r2 stops in the west room.
    for tick in range(ticks):
        qpos[tick, 0, 10] = -0.925 + 1.1 * tick
        qpos[tick, 0, 11] = -2.375 if tick < ticks - 1 else -2.375
        qpos[tick, 0, 20] = -0.925 + 0.1 * tick
        qpos[tick, 0, 21] = -2.875
    qpos[-1, 0, 10], qpos[-1, 0, 11] = 4.55, -2.10
    np.savez_compressed(run / 'evaluation-state.npz', qpos=qpos, dt=0.1)
    (run / 'result.json').write_text(json.dumps(dict(source_sha='a' * 40, status='cap_end', sim_s=0.4)))
    (run / 'nav-events.json').write_text(json.dumps({'0:r1': [dict(after='ARRIVED')], '0:r2': []}))
    (run / 'world-00' / 'eval-geometry.json').write_text(json.dumps(dict(
        destination=dict(center_m=[4.6, -2.1], half_extents_m=[.3, .7]),
        robot_qpos_adr={'r1': 10, 'r2': 20})))
    value = recount.recount(run)
    assert value['world_n'] == 1 and value['robot_n'] == 2
    assert value['arrival_gt_n'] == 1
    assert value['arrival_claim_n'] == 1
    assert value['claim_mismatch_n'] == 0
    assert value['research_result'] is False and value['eval_only'] is True
    assert value['inputs']['evaluation_state_sha256'] == hashlib.sha256(
        (run / 'evaluation-state.npz').read_bytes()).hexdigest()
    rows = {r['robot']: r for r in value['worlds'][0]['robots']}
    assert rows['r1']['inside_destination_gt'] is True
    assert rows['r2']['inside_destination_gt'] is False
    assert rows['r1']['distance_m'] > 5.0


def test_nav_gate_module_does_not_import_simulator_or_gt():
    text = Path(gate.__file__).read_text()
    for forbidden in ('import mujoco', 'import warp', 'import mujoco_warp', 'evaluation-state',
                      'data.qpos', 'top_camera'):
        assert forbidden not in text


def test_manifest_writer_binds_the_factory_hash(tmp_path):
    from harness.e2e_warp_components import require_navigation
    from scripts import e2ewarp_nav_manifest as writer
    calibration_path = write_calibration(tmp_path)
    out = tmp_path / 'components.json'
    rc = writer.main(['--out', str(out), '--calibration', str(calibration_path),
                      '--source-sha', 'a' * 40])
    assert rc == 0
    manifest = require_navigation(out, gate.ROOT)
    assert manifest['navigation']['ready'] is True
    assert manifest['navigation_factory']['entry'] == 'harness.e2ewarp_nav_gate:navigation_factory'
    assert manifest['static_map_input'] is False
    # A manifest written with a non-measured artifact must be refused.
    bad = write_calibration(tmp_path / 'bad', calibration(measured=False))
    with pytest.raises(SystemExit):
        writer.main(['--out', str(tmp_path / 'bad.json'), '--calibration', str(bad),
                     '--source-sha', 'a' * 40])


def test_calibration_binding_rejects_a_changed_artifact(tmp_path, monkeypatch):
    path = write_calibration(tmp_path)
    record = gate.load_calibration(path)
    monkeypatch.setenv(gate.CALIBRATION_ENV, str(path))
    queue = valid_queue(nav_calibration=dict(sha256=record['sha256'], source_sha=record['source_sha'],
                                             constants=record['constants']))
    assert gate.validate_calibration_binding(queue)['sha256'] == record['sha256']
    with pytest.raises(ValueError, match='NAV_CALIBRATION_CHANGED'):
        gate.validate_calibration_binding(valid_queue(nav_calibration=dict(sha256='c' * 64)))


def test_nested_static_map_is_rejected_at_any_depth():
    from harness import e2ewarp_nav_mode as nav
    with pytest.raises(ValueError, match='forbidden'):
        nav.nav_static({'mission': {'static_map': {'walls': [1]}}})
    with pytest.raises(ValueError, match='forbidden'):
        nav.nav_static({'orders': [{'id': 'o1', 'geometry': {'doors': []}}]})
    assert nav.nav_static({'orders': [{'id': 'o1', 'destination_zone': 'B'}]}) == {
        'orders': [{'id': 'o1', 'destination_zone': 'B'}]}


def test_prune_robots_removes_only_the_dropped_robot():
    xml = """<mujoco><worldbody>
      <body name="r1__robot"><geom name="r1__base"/></body>
      <body name="r2__robot"><geom name="r2__base"/></body>
      <body name="r3__robot"><geom name="r3__base"/></body>
    </worldbody><contact><pair geom1="r1__left_finger" geom2="r3__left_finger"/>
      <pair geom1="r1__left_finger" geom2="r2__right_finger"/></contact><actuator>
      <motor name="r1__wheel_fl_drive"/><motor name="r2__wheel_fl_drive"/>
      <motor name="r3__wheel_fl_drive"/>
    </actuator><equality><weld name="r3__grasp_red"/><weld name="r1__grasp_blue"/></equality></mujoco>"""
    out = gate.prune_robots(xml, keep=('r1', 'r2'))
    assert 'r3__' not in out
    assert out.count('r1__') == 5 and out.count('r2__') == 3
    assert '<body name="r1__robot">' in out and '<body name="r2__robot">' in out
    assert out.count('<pair ') == 1
    with pytest.raises(ValueError):
        gate.prune_robots(xml, keep=('r1', 'r2', 'r3'))
