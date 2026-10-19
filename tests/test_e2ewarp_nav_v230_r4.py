"""r4 (2026-10-19 steps ①–③): order-sheet slot aim + solo diagnostic + contact ledger.

r4 keeps the frozen r3 claim exactly (same 0.52 m projection along the armed
*component-centre* bearing and the same 1.0 m path fail-safe) and adds only:

- an order-sheet per-robot slot (`left`/`right`) realised from the own-camera
  component bbox as the centre of this robot's half of the visible marking;
- an opt-in *solo* diagnostic (one execution robot in the same nav scene);
- an eval-only cross-robot contact ledger read from the MJWarp contact buffer.

Everything is default OFF: v1 / v230_fwd24 / v230_r2 / v230_r3 queues and the
constructor defaults keep their bytes and behaviour, and only
``E2EWARP_NAV_GATE_MODE=v230_r4`` writes the new markers.
"""
import json
import os
import types

import numpy as np
import pytest

from harness import e2ewarp_nav_contacts as contacts
from harness import e2ewarp_nav_gate as gate
from harness import e2ewarp_nav_mode as navmode
from harness import e2ewarp_selfnav as sn

FORWARD = 0.004024203361827748
YAW = 1.7275488814064257
ENV_KEYS = (gate.GATE_MODE_ENV, gate.ARRIVAL_ENV, gate.ARRIVAL_ODOM_M_ENV,
            gate.ARRIVAL_GROUND_M_ENV)


@pytest.fixture(autouse=True)
def _clear_env():
    for key in ENV_KEYS:
        os.environ.pop(key, None)
    yield
    for key in ENV_KEYS:
        os.environ.pop(key, None)


def frame(sim_s=0.0, robot_id='r1'):
    return types.SimpleNamespace(robot_id=robot_id, world_id=0, tick=int(round(sim_s * 10)),
                                 sim_s=sim_s, jpeg=b'jpg', issued=())


def odometry():
    return sn.OwnCommandOdometry(forward_m_per_pct_s=FORWARD, yaw_deg_per_pct_s=YAW)


def detection(bottom_norm=0.30, height_norm=0.20, bearing_deg=0.0,
              left_edge=10.0, right_edge=-10.0, bbox=(100, 200, 500, 260), **patch):
    value = dict(kind='zone_B', bearing_deg=bearing_deg, bottom_norm=bottom_norm,
                 height_norm=height_norm, width_norm=0.60, area_norm=0.10, solidity=0.85,
                 spans_center_x=True, touches_top=False, bbox=bbox,
                 bearing_at_left_edge_deg=left_edge,
                 bearing_at_right_edge_deg=right_edge)
    value.update(patch)
    return value


def navigator(*, slot=None, bottom_norm=0.30, static=None, det=None):
    value = det if det is not None else detection(bottom_norm=bottom_norm)
    return sn.SelfCentricNavigation(
        'r1', static or {}, option=sn.OPTION, detector=lambda _frame: [dict(value)],
        odometry=odometry(), acquisition_mode=sn.ACQUISITION_FORWARD_THEN_SEARCH,
        forward_cap_m=2.4, arrival_mode=sn.ARRIVAL_ODOM_PROJECTION, slot=slot)


# --- slot aim ----------------------------------------------------------------
def test_slot_aim_is_the_centre_of_the_own_half_and_leaves_the_claim_centre():
    nav = navigator(slot='left')
    report = nav.observe(frame(0.0))
    landmark = report['self_centric_memory'][0]
    # left half centre = midpoint of the centre (0 deg) and left edge (+10 deg)
    assert landmark['slot_bearing_offset_deg'] == pytest.approx(5.0)
    assert landmark['bearing_deg'] == 0.0            # centre bearing untouched
    assert report['slot'] == 'left'
    assert report['arrival_armed'] is False
    # the follower aims left of the component centre: left wheel pulse < right
    row = nav.command(0.0)
    assert row['duration_s'][0] < row['duration_s'][1] > 0.0

    right = navigator(slot='right')
    right_report = right.observe(frame(0.0))
    assert right_report['self_centric_memory'][0]['slot_bearing_offset_deg'] == pytest.approx(-5.0)
    right_row = right.command(0.0)
    assert right_row['duration_s'][1] < right_row['duration_s'][0] > 0.0


def test_slot_is_off_by_default_and_the_follower_keeps_the_centre_bearing():
    nav = navigator(slot=None)
    report = nav.observe(frame(0.0))
    assert report['slot'] is None
    assert report['self_centric_memory'][0]['slot_bearing_offset_deg'] == 0.0
    row = nav.command(0.0)
    assert row['duration_s'][0] == pytest.approx(row['duration_s'][1])
    assert row['duration_s'][0] > 0.0


def test_slot_is_read_from_the_order_sheet_and_validated():
    nav = navigator(slot=None, static={'slots': {'r1': 'left', 'r2': 'right'}})
    assert nav.slot == 'left'
    with pytest.raises(ValueError, match='unknown destination slot'):
        navigator(slot=None, static={'slots': {'r1': 'middle'}})


def test_slot_aim_never_changes_the_armed_claim_direction():
    # arming latches on the same accepted detection; u must stay the centre
    # bearing (0 deg here), so the claim is the frozen straight projection.
    nav = navigator(slot='left', bottom_norm=0.967)
    reports, rows = [], []
    for tick in range(45):
        now = tick / 10.0
        reports.append(nav.observe(frame(now)))
        rows.append(nav.command(now))
    assert reports[0]['arrival_armed'] is True
    assert reports[0]['arrival_bearing_armed_deg'] == 0.0
    assert reports[0]['arrival_u_deg'] == 0.0
    assert reports[0]['drive_reason'] == 'driving_hold_heading'
    claim = next(i for i, r in enumerate(reports) if r['destination_arrived'])
    assert claim == 37                       # 0.5211 m of 0.52 m, as r3
    assert reports[claim]['arrival_projection_m'] >= sn.ARRIVAL_ODOM_PROJECTION_M
    assert sn.ARRIVAL_ODOM_PROJECTION_M == 0.52
    assert sn.ARRIVAL_PROJECTION_PATH_CAP_M == 1.0


def test_slot_requires_measured_component_edge_bearings():
    det = detection()
    det.pop('bearing_at_left_edge_deg')
    with pytest.raises(ValueError, match='slot aim requires measured component edge bearings'):
        navigator(slot='left', det=det).observe(frame(0.0))


def test_detector_reports_component_edge_bearings():
    pytest.importorskip('PIL')
    from PIL import Image
    # 640x480 with a solid zone-B patch (OpenCV hue 110-114 / S>=100 / V 30-230).
    rgb = np.zeros((480, 640, 3), dtype=np.uint8)
    # PURPLE/BLUE paint used by the frozen band: RGB (40, 60, 150) -> hue ~229 deg
    rgb[200:260, 100:500] = (55, 75, 150)
    det = sn.GpuCalibZoneDetector(profile='gpu_calib_v230',
                                  bearing_convention='positive_left')(Image.fromarray(rgb))
    assert len(det) == 1
    value = det[0]
    assert value['bearing_at_left_edge_deg'] > value['bearing_deg'] > value['bearing_at_right_edge_deg']
    assert value['bearing_deg'] == pytest.approx(value['bearing_at_left_edge_deg'] * 0.5
                                                 + value['bearing_at_right_edge_deg'] * 0.5,
                                                 abs=0.2)


# --- gate queue binding ------------------------------------------------------
def _calibration(tmp_path):
    payload = dict(schema=gate.CALIBRATION_SCHEMA, measured=True, measured_n=60,
                   constants=dict(forward_m_per_pct_s=FORWARD, yaw_deg_per_pct_s=YAW),
                   per_robot={r: dict(forward_m_per_pct_s=FORWARD, yaw_deg_per_pct_s=YAW)
                              for r in gate.ROBOTS},
                   source_sha='d' * 40)
    path = tmp_path / 'nav_gate_calibration.json'
    path.write_text(json.dumps(payload))
    return gate.load_calibration(path)


def _queue(mode, calibration, robots=None, **env):
    os.environ[gate.GATE_MODE_ENV] = mode
    for key, value in env.items():
        os.environ[key] = str(value)
    queue = gate.gate_queue_fields(601, calibration=calibration, robots=robots)
    queue['sim_budget_s'] = queue['nav_sim_budget_s']
    return queue


def test_v230_r4_is_default_off_and_binds_the_slots(tmp_path):
    assert gate.gate_mode()['name'] == gate.GATE_MODE_V1
    assert not gate.GATE_MODES[gate.GATE_MODE_V1].get('slots')
    cal = _calibration(tmp_path)
    queue = _queue(gate.GATE_MODE_V230_R4, cal, **{gate.ARRIVAL_ENV: 'odom_projection'})
    gate.validate_gate_queue(queue)
    assert queue['nav_gate_mode'] == 'v230_r4'
    assert queue['nav_slots'] == {'r1': 'left', 'r2': 'right'}
    assert queue['nav_spawn_y'] == gate.LANE_Y
    # the claim and every C/band marker are the r3 ones
    assert queue['nav_arrival_mode'] == 'odom_projection'
    assert queue['nav_arrival_odom_projection_m'] == 0.52
    assert queue['nav_arrival_projection_path_cap_m'] == 1.0
    assert queue['nav_acquire_min_height_norm'] == sn.ACQUIRE_MIN_HEIGHT_NORM == 0.02
    assert queue['nav_acquire_confirm_ticks'] == sn.ACQUIRE_CONFIRM_TICKS == 3
    assert queue['nav_forward_reacquire'] is True
    assert queue['nav_zone_profile'] == 'gpu_calib_v230'
    assert queue['nav_forward_cap_m'] == 2.4
    assert queue['nav_bearing_convention'] == 'positive_left'
    assert 'nav_solo_robot' not in queue


def test_v230_r4_rejects_missing_or_swapped_slots(tmp_path):
    cal = _calibration(tmp_path)
    queue = _queue(gate.GATE_MODE_V230_R4, cal, **{gate.ARRIVAL_ENV: 'odom_projection'})
    with pytest.raises(ValueError, match='NAV_SLOTS_REQUIRED'):
        gate.validate_gate_queue(dict(queue, nav_slots={}))
    with pytest.raises(ValueError, match='NAV_SLOTS_REQUIRED'):
        gate.validate_gate_queue(dict(queue, nav_slots={'r1': 'right', 'r2': 'left'}))
    with pytest.raises(ValueError, match='NAV_ARRIVAL_MODE_MISMATCH'):
        gate.validate_gate_queue(dict(queue, nav_arrival_mode='bottom_band'))


def test_frozen_modes_keep_no_slot_markers(tmp_path):
    cal = _calibration(tmp_path)
    for mode, env in ((gate.GATE_MODE_V1, {}),
                      (gate.GATE_MODE_V230_FWD24, {}),
                      (gate.GATE_MODE_V230_R2, {gate.ARRIVAL_ENV: 'odom_residual'}),
                      (gate.GATE_MODE_V230_R3, {gate.ARRIVAL_ENV: 'odom_projection'})):
        queue = _queue(mode, cal, **env)
        gate.validate_gate_queue(queue)
        assert 'nav_slots' not in queue
        assert 'nav_solo_robot' not in queue


def test_solo_diagnostic_queue_is_r4_only_and_single_robot(tmp_path):
    cal = _calibration(tmp_path)
    solo = _queue(gate.GATE_MODE_V230_R4, cal, robots=('r2',),
                  **{gate.ARRIVAL_ENV: 'odom_projection'})
    gate.validate_gate_queue(solo)
    assert solo['nav_robots'] == ['r2']
    assert solo['nav_solo_robot'] == 'r2'
    assert solo['nav_spawn_y'] == {'r2': gate.LANE_Y['r2']}
    assert solo['nav_slots'] == {'r2': 'right'}
    # pair robots with a solo marker fails closed
    with pytest.raises(ValueError, match='NAV_SOLO_MARKER_MISMATCH'):
        gate.validate_gate_queue(dict(solo, nav_robots=['r1', 'r2'], nav_spawn_y=gate.LANE_Y,
                                      nav_slots={'r1': 'left', 'r2': 'right'}))
    pair = _queue(gate.GATE_MODE_V230_R4, cal, **{gate.ARRIVAL_ENV: 'odom_projection'})
    with pytest.raises(ValueError, match='NAV_SOLO_MARKER_MISMATCH'):
        gate.validate_gate_queue(dict(pair, nav_solo_robot='r1'))
    # the same single-robot queue under r3 (last: it changes the mode env)
    r3_solo = _queue(gate.GATE_MODE_V230_R3, cal, robots=('r2',),
                     **{gate.ARRIVAL_ENV: 'odom_projection'})
    with pytest.raises(ValueError, match='NAV_SOLO_REQUIRES_V230_R4'):
        gate.validate_gate_queue(r3_solo)


def test_factory_requires_the_r4_slot_for_this_robot(tmp_path):
    cal = _calibration(tmp_path)
    gate._ADMITTED = cal
    _queue(gate.GATE_MODE_V230_R4, cal, **{gate.ARRIVAL_ENV: 'odom_projection'})
    slots = {'r1': 'left', 'r2': 'right'}
    nav = gate.navigation_factory('r1', {'slots': slots})
    assert nav.slot == 'left'
    assert nav.arrival_mode == sn.ARRIVAL_ODOM_PROJECTION
    with pytest.raises(ValueError, match='NAV_SLOT_REQUIRED'):
        gate.navigation_factory('r1', None)
    with pytest.raises(ValueError, match='NAV_SLOT_MISMATCH'):
        gate.navigation_factory('r1', {'slots': {'r1': 'right', 'r2': 'left'}})


def test_nav_static_accepts_slots_and_still_rejects_map_geometry():
    static = navmode.nav_static({'orders': [], 'slots': {'r1': 'left', 'r2': 'right'}})
    assert static['slots'] == {'r1': 'left', 'r2': 'right'}
    with pytest.raises(ValueError, match='static map/GT input'):
        navmode.nav_static({'mission': {'slots': {'r1': 'left'}, 'pose': [0, 0, 0]}})


# --- solo nav-mode queue -----------------------------------------------------
def test_nav_mode_queue_supports_the_solo_robot_and_keeps_the_pair_default():
    pair = navmode.queue_fields(601)
    assert pair['robots'] == ['r1', 'r2'] and pair['leader_id'] == 'r2'
    navmode.validate_queue(pair, 601)
    solo = navmode.queue_fields(601, ('r2',))
    assert solo['robots'] == ['r2'] and solo['leader_id'] == 'r2'
    navmode.validate_queue(solo, 601, ('r2',))
    with pytest.raises(ValueError, match='NAV_ROBOTS_REQUIRED'):
        navmode.validate_queue(solo, 601)
    with pytest.raises(ValueError, match='NAV_LEADER_MISMATCH'):
        navmode.validate_queue(dict(solo, leader_id='r1'), 601, ('r2',))


def test_prune_robots_keeps_one_robot_for_the_solo_diagnostic():
    xml = ('<mujoco>'
           '<body name="r1__robot"><geom name="r1__base"/></body>'
           '<body name="r2__robot"><geom name="r2__base"/></body>'
           '<body name="r3__robot"><geom name="r3__base"/></body>'
           '<body name="cargo_box"/></mujoco>')
    solo = gate.prune_robots(xml, keep=('r2',))
    assert 'r2__' in solo and 'r1__' not in solo and 'r3__' not in solo
    assert 'cargo_box' in solo
    pair = gate.prune_robots(xml, keep=('r1', 'r2'))
    assert 'r1__' in pair and 'r2__' in pair and 'r3__' not in pair


# --- eval-only contact ledger ------------------------------------------------
class _Array:
    def __init__(self, value):
        self._value = np.asarray(value)

    def numpy(self):
        return self._value


class _Geom:
    def __init__(self, name):
        self.name = name


class _Model:
    def __init__(self, names):
        self._names = list(names)
        self.ngeom = len(self._names)
        self.geom_size = [[0.0905, 0.0435, 0.03] for _ in self._names]
        self.geom_pos = [[0.0, 0.0, 0.02] for _ in self._names]

    def geom(self, index):
        return _Geom(self._names[index])


def _hooks(names, geom, dist=None, worldid=None, nacon=(3,)):
    contact = types.SimpleNamespace(geom=_Array(geom))
    if dist is not None:
        contact.dist = _Array(dist)
    if worldid is not None:
        contact.worldid = _Array(worldid)
    return types.SimpleNamespace(m=_Model(names), wd=types.SimpleNamespace(
        nacon=_Array(nacon), contact=contact))


def test_contact_ledger_records_only_cross_robot_contacts_of_this_world():
    names = ['r1__base_lower_collision', 'r2__base_lower_collision',
             'r1__wheel_fl_geom', 'r1__arm_geom', 'r2__arm_geom',
             'floor', 'r1__finger_left']
    hooks = _hooks(names, geom=[[0, 1], [2, 3], [6, 0]], dist=[0.0, 0.01, 0.02],
                   worldid=[0, 0, 1])
    rows = contacts.read_contacts(hooks, 0, robots={'r1', 'r2'})
    assert rows == [dict(geom_a='r1__base_lower_collision',
                         geom_b='r2__base_lower_collision',
                         robot_a='r1', robot_b='r2', dist_m=0.0)]
    # same-robot and non-robot geoms are not cross-robot contacts
    hooks_same = _hooks(names, geom=[[2, 3]], dist=[0.0], worldid=[0], nacon=(1,))
    assert contacts.read_contacts(hooks_same, 0, robots={'r1', 'r2'}) == []


def test_contact_ledger_is_unavailable_instead_of_zero_when_fields_are_missing():
    hooks = types.SimpleNamespace(m=_Model(['r1__base']), wd=types.SimpleNamespace())
    assert contacts.read_contacts(hooks, 0, robots={'r1', 'r2'}) is None
    ledger = contacts.ledger(('r1', 'r2'), base_boxes={'r1': contacts.base_box(
        _Model(['r1__base_lower_collision']), 'r1')})
    contacts.record(ledger, None, 1.0)
    assert ledger['contacts_available'] is False
    assert ledger['contact_ticks'] == 0 and ledger['unavailable_reason']


def test_contact_ledger_counts_contact_ticks_and_times():
    names = ['r1__base', 'r2__base']
    ledger = contacts.ledger(('r1', 'r2'))
    contacts.record(ledger, [], 0.1)
    contacts.record(ledger, contacts.read_contacts(
        _hooks(names, geom=[[0, 1]], dist=[0.0], worldid=[0], nacon=(1,)), 0,
        robots={'r1', 'r2'}), 26.4)
    contacts.record(ledger, contacts.read_contacts(
        _hooks(names, geom=[[0, 1]], dist=[0.0], worldid=[0], nacon=(1,)), 0,
        robots={'r1', 'r2'}), 26.5)
    assert ledger['contacts_available'] is True
    assert ledger['contact_ticks'] == 2 and ledger['contact_pairs_total'] == 2
    assert ledger['first_contact_s'] == 26.4 and ledger['last_contact_s'] == 26.5


def test_solo_robot_runs_cannot_see_robot_geometry_when_pruned():
    assert contacts.geom_robot('r2__base_lower_collision') == 'r2'
    assert contacts.geom_robot('floor') is None
    assert contacts.geom_robot('cargo_box') is None


# --- runner wiring (no physics import) ---------------------------------------
def test_runner_accepts_the_solo_flag_only_for_the_r4_nav_mode(monkeypatch):
    from scripts import run_e2e_warp as runner
    parser = runner.build_parser()
    args = parser.parse_args(['--mode', 'nav', '--nav-solo-robot', 'r2', '--output', '/tmp/x'])
    assert args.nav_solo_robot == 'r2'
    assert gate.gate_robots('r2') == ('r2',)
    assert gate.gate_robots(None) == ('r1', 'r2')
    with pytest.raises(SystemExit):
        runner.main(['--mode', 'nav', '--nav-solo-robot', 'r2', '--output', '/tmp/x'])
    monkeypatch.setenv(gate.GATE_MODE_ENV, gate.GATE_MODE_V230_R3)
    with pytest.raises(SystemExit):
        runner.main(['--mode', 'nav', '--nav-solo-robot', 'r2', '--output', '/tmp/x'])
    assert runner.nav_slots_enabled() is False
    monkeypatch.setenv(gate.GATE_MODE_ENV, gate.GATE_MODE_V230_R4)
    assert runner.nav_slots_enabled() is True


def test_build_context_supports_one_robot_and_the_pair_default():
    import inspect
    from scripts import e2e_warp_physics as physics
    signature = inspect.signature(physics.build_context)
    assert signature.parameters['nav_keep'].default == ('r1', 'r2')
    assert signature.parameters['nav_spawns'].default is None
