"""r5 (2026-10-20): two-stage slot aim — component centre through the door, then 25/75.

r5 keeps r4's order-sheet slot and the frozen r3 claim exactly (0.52 m
projection along the armed component-centre bearing, 1.0 m path fail-safe).  The
only new behaviour is *when* the slot aim applies:

- stage 1 (before the visible destination component's bottom row projects onto
  the floor at <= 1.5 m): offset 0, i.e. the component-centre aim r2 passed the
  wide door with;
- stage 2 (after the one-shot latch): the order-sheet 25 %/75 % aim, with the
  applied offset clamped to +-15 deg.

Everything is default OFF: the constructor default ``slot_stage2_ground_m=None``
keeps the r4 behaviour byte-identical, and only
``E2EWARP_NAV_GATE_MODE=v230_r5`` writes the new queue markers.
"""
import json
import os
import types

import pytest

from harness import e2ewarp_nav_gate as gate
from harness import e2ewarp_selfnav as sn

FORWARD = 0.004024203361827748
YAW = 1.7275488814064257
ENV_KEYS = (gate.GATE_MODE_ENV, gate.ARRIVAL_ENV, gate.ARRIVAL_ODOM_M_ENV,
            gate.ARRIVAL_GROUND_M_ENV)
#: bbox bottom rows around the 1.5 m boundary under the measured camera model.
#: The detector reports an exclusive bottom edge, so the *last included* row is
#: ``bottom - 1``: bottom 138 -> row 137 -> 1.5036 m (closed), bottom 139 ->
#: row 138 -> 1.4915 m (open).
ROW_LAST_ABOVE = 138
ROW_LAST_INSIDE = 139


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


def navigator(*, slot='left', det=None, stage2=sn.SLOT_STAGE2_GROUND_M):
    value = det if det is not None else detection()
    return sn.SelfCentricNavigation(
        'r1', {}, option=sn.OPTION, detector=lambda _frame: [dict(value)],
        odometry=odometry(), acquisition_mode=sn.ACQUISITION_FORWARD_THEN_SEARCH,
        forward_cap_m=2.4, arrival_mode=sn.ARRIVAL_ODOM_PROJECTION,
        slot=slot, slot_stage2_ground_m=stage2)


def _calibration(tmp_path):
    payload = dict(schema=gate.CALIBRATION_SCHEMA, measured=True, measured_n=60,
                   source_sha='d182b67aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa',
                   constants=dict(forward_m_per_pct_s=FORWARD, yaw_deg_per_pct_s=YAW),
                   per_robot={r: dict(forward_m_per_pct_s=FORWARD, yaw_deg_per_pct_s=YAW)
                              for r in gate.ROBOTS})
    path = tmp_path / 'nav_gate_calibration.json'
    path.write_text(json.dumps(payload))
    return gate.load_calibration(path)


def _queue(mode, calibration, robots=None, **env):
    for key in ENV_KEYS:
        os.environ.pop(key, None)
    os.environ[gate.GATE_MODE_ENV] = mode
    for key, value in env.items():
        os.environ[key] = str(value)
    queue = gate.gate_queue_fields(601, calibration=calibration, robots=robots)
    queue['sim_budget_s'] = queue['nav_sim_budget_s']
    return queue


# --- stage 1 / stage 2 aim ---------------------------------------------------
def test_stage1_aims_the_component_centre_before_1_5_m():
    # bottom row 138 -> 1.5036 m > 1.5 m: the slot is not active, so the raw
    # +5 deg half aim is *measured* but not applied (the follower keeps 0 deg).
    det = detection(bbox=(100, 180, 500, ROW_LAST_ABOVE))
    nav = navigator(slot='left', det=det)
    report = nav.observe(frame(0.0))
    assert report['slot'] == 'left'
    assert report['slot_stage2_ground_m'] == 1.5
    assert report['slot_stage2_active'] is False
    assert report['slot_ground_distance_m'] == pytest.approx(1.5036, abs=5e-4)
    assert report['self_centric_memory'][0]['slot_bearing_offset_deg'] == pytest.approx(5.0)
    assert report['slot_bearing_offset_applied_deg'] == 0.0
    row = nav.command(0.0)
    assert row['duration_s'][0] == pytest.approx(row['duration_s'][1])
    assert row['duration_s'][0] > 0.0


def test_stage2_activates_just_inside_1_5_m_and_applies_the_25_75_aim():
    det = detection(bbox=(100, 180, 500, ROW_LAST_INSIDE))
    nav = navigator(slot='left', det=det)
    report = nav.observe(frame(0.0))
    assert report['slot_stage2_active'] is True
    assert report['slot_stage2_sim_s'] == 0.0
    assert report['slot_ground_at_activation_m'] == pytest.approx(1.4915, abs=5e-4)
    # 25 % aim of the left half = midpoint of component centre (0) and left edge
    # (+10) = +5 deg, and the applied offset is exactly that measured aim.
    assert report['slot_bearing_offset_raw_deg'] == pytest.approx(5.0)
    assert report['slot_bearing_offset_applied_deg'] == pytest.approx(5.0)
    assert report['slot_offset_limit_deg'] == 15.0
    row = nav.command(0.0)
    assert row['duration_s'][0] < row['duration_s'][1] > 0.0

    # right slot mirrors it: 75 % aim = -5 deg, right wheel pulse is shorter.
    right = navigator(slot='right', det=detection(bbox=(100, 180, 500, ROW_LAST_INSIDE)))
    right_report = right.observe(frame(0.0))
    assert right_report['slot_bearing_offset_applied_deg'] == pytest.approx(-5.0)
    right_row = right.command(0.0)
    assert right_row['duration_s'][1] < right_row['duration_s'][0] > 0.0


def test_stage2_clamps_the_applied_offset_to_15_deg():
    # a wide component gives a +20 deg half aim (left edge +40, centre 0); the
    # applied offset must be clamped to +15 while the raw measurement is kept.
    det = detection(bbox=(20, 100, 620, ROW_LAST_INSIDE), left_edge=40.0, right_edge=-40.0)
    nav = navigator(slot='left', det=det)
    report = nav.observe(frame(0.0))
    assert report['slot_bearing_offset_raw_deg'] == pytest.approx(20.0)
    assert report['slot_bearing_offset_applied_deg'] == pytest.approx(15.0)
    right = navigator(slot='right', det=detection(bbox=(20, 100, 620, ROW_LAST_INSIDE),
                                                  left_edge=40.0, right_edge=-40.0))
    right_report = right.observe(frame(0.0))
    assert right_report['slot_bearing_offset_raw_deg'] == pytest.approx(-20.0)
    assert right_report['slot_bearing_offset_applied_deg'] == pytest.approx(-15.0)
    # the controller sees the clamped bearing: |turn| = 15 / 45 of full scale
    assert sn.SLOT_OFFSET_LIMIT_DEG == 15.0


def test_stage2_activation_is_one_shot_and_never_reopens():
    nav = navigator(slot='left', det=detection(bbox=(100, 180, 500, ROW_LAST_INSIDE)))
    assert nav.observe(frame(0.0))['slot_stage2_active'] is True
    # re-acquired far away (bottom row 129 -> 1.61 m): the latch stays on.
    # columns centred on the principal column (cx = 287.689): (228+348-1)/2
    far = detection(bbox=(228, 150, 348, 130))
    nav.detector = lambda _frame: [dict(far)]
    report = nav.observe(frame(1.0))
    assert report['slot_ground_distance_m'] == pytest.approx(1.6079, abs=5e-4)
    assert report['slot_stage2_active'] is True
    assert report['slot_stage2_sim_s'] == 0.0
    assert nav.command(1.0)['duration_s'][0] < nav.command(1.0)['duration_s'][1]


def test_stage2_fails_closed_without_a_bbox():
    det = detection()
    det.pop('bbox')
    nav = navigator(slot='left', det=det)
    report = nav.observe(frame(0.0))
    assert report['slot_stage2_active'] is False
    assert report['slot_ground_distance_m'] is None
    assert report['slot_bearing_offset_applied_deg'] == 0.0
    row = nav.command(0.0)
    assert row['duration_s'][0] == pytest.approx(row['duration_s'][1])


# --- claim definition unchanged ---------------------------------------------
def test_stage2_never_changes_the_armed_claim_direction_or_0_52():
    # The arming detection is inside 1.5 m, so the slot is active from tick 0;
    # u must still be the component-centre bearing (0 deg) and the claim the
    # frozen 0.52 m projection (37 ticks, 0.5211 m) exactly as r3/r4.
    nav = navigator(slot='left', det=detection(bottom_norm=0.967,
                                               bbox=(180, 300, 460, 469)))
    reports = []
    for tick in range(45):
        now = tick / 10.0
        reports.append(nav.observe(frame(now)))
        nav.command(now)
    assert reports[0]['slot_stage2_active'] is True
    assert reports[0]['arrival_armed'] is True
    assert reports[0]['arrival_bearing_armed_deg'] == 0.0
    assert reports[0]['arrival_u_deg'] == 0.0
    assert reports[0]['slot_bearing_offset_raw_deg'] == pytest.approx(5.0)
    claim = next(i for i, r in enumerate(reports) if r['destination_arrived'])
    assert claim == 37
    assert reports[claim]['arrival_projection_m'] >= sn.ARRIVAL_ODOM_PROJECTION_M
    assert sn.ARRIVAL_ODOM_PROJECTION_M == 0.52
    assert sn.ARRIVAL_PROJECTION_PATH_CAP_M == 1.0


def test_r4_default_keeps_the_slot_always_on_and_reports_no_stage2():
    nav = navigator(slot='left', det=detection(bbox=(100, 180, 500, ROW_LAST_ABOVE)),
                    stage2=None)
    report = nav.observe(frame(0.0))
    assert report['slot_stage2_ground_m'] is None
    assert report['slot_stage2_active'] is False
    assert report['slot_ground_distance_m'] is None
    assert report['slot_bearing_offset_applied_deg'] == pytest.approx(5.0)
    assert nav.command(0.0)['duration_s'][0] < nav.command(0.0)['duration_s'][1]


def test_stage2_requires_a_slot_and_the_projection_claim():
    with pytest.raises(ValueError, match='slot stage 2 requires a destination slot'):
        sn.SelfCentricNavigation(
            'r1', {}, option=sn.OPTION, detector=lambda _f: [], odometry=odometry(),
            acquisition_mode=sn.ACQUISITION_FORWARD_THEN_SEARCH, forward_cap_m=2.4,
            arrival_mode=sn.ARRIVAL_ODOM_PROJECTION, slot=None, slot_stage2_ground_m=1.5)
    with pytest.raises(ValueError, match='odom_projection'):
        sn.SelfCentricNavigation(
            'r1', {}, option=sn.OPTION, detector=lambda _f: [], odometry=odometry(),
            acquisition_mode=sn.ACQUISITION_FORWARD_THEN_SEARCH, forward_cap_m=2.4,
            arrival_mode=sn.ARRIVAL_ODOM_RESIDUAL, slot='left', slot_stage2_ground_m=1.5)
    with pytest.raises(ValueError, match='must be positive'):
        sn.SelfCentricNavigation(
            'r1', {}, option=sn.OPTION, detector=lambda _f: [], odometry=odometry(),
            acquisition_mode=sn.ACQUISITION_FORWARD_THEN_SEARCH, forward_cap_m=2.4,
            arrival_mode=sn.ARRIVAL_ODOM_PROJECTION, slot='left', slot_stage2_ground_m=0.0)


# --- gate wiring (default OFF) ----------------------------------------------
def test_v230_r5_is_default_off_and_binds_the_stage2_markers(tmp_path):
    assert gate.gate_mode()['name'] == gate.GATE_MODE_V1
    assert not gate.GATE_MODES[gate.GATE_MODE_V1].get('slots')
    assert gate.GATE_MODES[gate.GATE_MODE_V230_R5]['slot_stage2_ground_m'] == 1.5
    assert gate.GATE_MODES[gate.GATE_MODE_V230_R5]['slot_offset_limit_deg'] == 15.0
    cal = _calibration(tmp_path)
    queue = _queue(gate.GATE_MODE_V230_R5, cal, **{gate.ARRIVAL_ENV: 'odom_projection'})
    gate.validate_gate_queue(queue)
    assert queue['nav_gate_mode'] == 'v230_r5'
    assert queue['nav_slots'] == {'r1': 'left', 'r2': 'right'}
    assert queue['nav_slot_stage2_ground_m'] == 1.5
    assert queue['nav_slot_offset_limit_deg'] == 15.0
    assert queue['nav_arrival_mode'] == 'odom_projection'
    assert queue['nav_arrival_odom_projection_m'] == 0.52
    assert queue['nav_arrival_projection_path_cap_m'] == 1.0
    assert queue['nav_acquire_min_height_norm'] == sn.ACQUIRE_MIN_HEIGHT_NORM == 0.02
    assert queue['nav_acquire_confirm_ticks'] == sn.ACQUIRE_CONFIRM_TICKS == 3
    assert queue['nav_forward_cap_m'] == 2.4
    assert queue['nav_zone_profile'] == 'gpu_calib_v230'
    assert queue['nav_bearing_convention'] == 'positive_left'
    assert 'nav_solo_robot' not in queue


def test_v230_r5_rejects_missing_or_retuned_stage2_markers(tmp_path):
    cal = _calibration(tmp_path)
    queue = _queue(gate.GATE_MODE_V230_R5, cal, **{gate.ARRIVAL_ENV: 'odom_projection'})
    missing = dict(queue)
    missing.pop('nav_slot_stage2_ground_m')
    with pytest.raises(ValueError, match='NAV_SLOT_STAGE2_MARKERS_REQUIRED'):
        gate.validate_gate_queue(missing)
    with pytest.raises(ValueError, match='NAV_SLOT_STAGE2_GROUND_MISMATCH'):
        gate.validate_gate_queue(dict(queue, nav_slot_stage2_ground_m=1.4))
    with pytest.raises(ValueError, match='NAV_SLOT_OFFSET_LIMIT_MISMATCH'):
        gate.validate_gate_queue(dict(queue, nav_slot_offset_limit_deg=20.0))
    with pytest.raises(ValueError, match='NAV_SLOTS_REQUIRED'):
        gate.validate_gate_queue(dict(queue, nav_slots={}))


def test_r4_and_frozen_modes_carry_no_stage2_markers(tmp_path):
    cal = _calibration(tmp_path)
    r4 = _queue(gate.GATE_MODE_V230_R4, cal, **{gate.ARRIVAL_ENV: 'odom_projection'})
    gate.validate_gate_queue(r4)
    assert 'nav_slot_stage2_ground_m' not in r4
    assert 'nav_slot_offset_limit_deg' not in r4
    # inserting an r5 marker into an r4 queue fails closed
    with pytest.raises(ValueError, match='NAV_SLOT_STAGE2_REQUIRE_V230_R5'):
        gate.validate_gate_queue(dict(r4, nav_slot_stage2_ground_m=1.5))
    for mode, env in ((gate.GATE_MODE_V1, {}),
                      (gate.GATE_MODE_V230_FWD24, {}),
                      (gate.GATE_MODE_V230_R2, {gate.ARRIVAL_ENV: 'odom_residual'}),
                      (gate.GATE_MODE_V230_R3, {gate.ARRIVAL_ENV: 'odom_projection'})):
        queue = _queue(mode, cal, **env)
        gate.validate_gate_queue(queue)
        assert 'nav_slots' not in queue
        assert 'nav_slot_stage2_ground_m' not in queue


def test_solo_diagnostic_queue_is_allowed_for_r5(tmp_path):
    cal = _calibration(tmp_path)
    solo = _queue(gate.GATE_MODE_V230_R5, cal, robots=('r1',),
                  **{gate.ARRIVAL_ENV: 'odom_projection'})
    gate.validate_gate_queue(solo)
    assert solo['nav_robots'] == ['r1']
    assert solo['nav_solo_robot'] == 'r1'
    assert solo['nav_slots'] == {'r1': 'left'}
    assert solo['nav_slot_stage2_ground_m'] == 1.5


def test_factory_binds_stage2_only_in_r5(tmp_path):
    cal = _calibration(tmp_path)
    gate._ADMITTED = cal
    slots = {'r1': 'left', 'r2': 'right'}
    _queue(gate.GATE_MODE_V230_R5, cal, **{gate.ARRIVAL_ENV: 'odom_projection'})
    nav = gate.navigation_factory('r1', {'slots': slots})
    assert nav.slot == 'left'
    assert nav.slot_stage2_ground_m == 1.5
    assert nav.arrival_projection_m == 0.52
    assert nav.arrival_projection_path_cap_m == 1.0
    with pytest.raises(ValueError, match='NAV_SLOT_REQUIRED'):
        gate.navigation_factory('r1', None)
    # r4 stays byte-identical: no stage-2 gate is bound.
    _queue(gate.GATE_MODE_V230_R4, cal, **{gate.ARRIVAL_ENV: 'odom_projection'})
    r4 = gate.navigation_factory('r1', {'slots': slots})
    assert r4.slot_stage2_ground_m is None
