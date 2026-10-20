"""N1 (2026-10-20): stage-1 spawn-lane bearing bound (+-10 deg) on top of r5.

r5 passed, but through the wide door both robots aimed at the same visible
destination-centre and the pair closed to 0.1770 m centre / 0.0457 m base-box
separation.  N1 keeps r5's stage-1 *centre* aim and every r5 stage-2/claim
constant, and adds exactly one bound:

- stage 1 (until the visible destination component's bottom row projects onto
  the floor at <= 1.5 m, i.e. the ground-projection door pass): the aim
  direction in the own-odometry (spawn-lane) frame is clamped to +-10 deg, so a
  robot cannot turn across the neighbouring lane while chasing an off-lane part
  of the marking;
- stage 2 (after the one-shot latch): the bound is released and r5's aim
  (component centre + clamped +-15 deg slot offset) applies unchanged, as do the
  arming bearing and the 0.52 m / 1.0 m claim.

Everything is default OFF: the constructor default ``spawn_lane_limit_deg=None``
keeps r4/r5 behaviour and report bytes identical, and only
``E2EWARP_NAV_GATE_MODE=v230_n1`` writes/binds the lane-limit marker.
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
#: bbox bottom rows around the 1.5 m boundary (detector bottom is exclusive):
#: bottom 138 -> row 137 -> 1.5036 m (stage 1), bottom 139 -> row 138 ->
#: 1.4915 m (stage 2).
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


def navigator(*, slot='left', det=None, stage2=sn.SLOT_STAGE2_GROUND_M,
              lane=sn.SPAWN_LANE_LIMIT_DEG):
    value = det if det is not None else detection()
    return sn.SelfCentricNavigation(
        'r1', {}, option=sn.OPTION, detector=lambda _frame: [dict(value)],
        odometry=odometry(), acquisition_mode=sn.ACQUISITION_FORWARD_THEN_SEARCH,
        forward_cap_m=2.4, arrival_mode=sn.ARRIVAL_ODOM_PROJECTION,
        slot=slot, slot_stage2_ground_m=stage2, spawn_lane_limit_deg=lane)


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


# --- stage-1 spawn-lane bound ------------------------------------------------
def test_stage1_bounds_the_centre_aim_to_10_deg_around_the_spawn_lane():
    # r5's r2 followed +24.2 deg on its first samples; N1 must cap the *aim*
    # at +10 deg while stage 1 lasts, pinning the observed bearing to 10 deg.
    det = detection(bearing_deg=24.2, bbox=(100, 180, 500, ROW_LAST_ABOVE))
    nav = navigator(slot='left', det=det)
    report = nav.observe(frame(0.0))
    assert report['slot_stage2_active'] is False
    assert report['spawn_lane_limit_deg'] == 10.0
    assert report['spawn_lane_active'] is True
    assert report['spawn_lane_aim_raw_deg'] == pytest.approx(24.2)
    assert report['spawn_lane_aim_applied_deg'] == pytest.approx(10.0)
    assert report['follow_bearing_raw_deg'] == pytest.approx(24.2)
    assert report['follow_bearing_applied_deg'] == pytest.approx(10.0)
    # the stage-1 slot offset is still r5's 0 (the centre aim is unchanged).
    assert report['slot_bearing_offset_applied_deg'] == 0.0
    row = nav.command(0.0)
    assert row['duration_s'][0] < row['duration_s'][1]
    # controller sees the clamped bearing: left wheel = 1 - 10/45 of full scale.
    assert row['duration_s'][0] == pytest.approx((1.0 - 10.0 / sn.BEARING_FULL_DEG) * sn.PULSE_S)
    assert row['duration_s'][1] == pytest.approx(sn.PULSE_S)


def test_stage1_bounds_the_negative_side_too():
    det = detection(bearing_deg=-24.2, bbox=(100, 180, 500, ROW_LAST_ABOVE))
    nav = navigator(slot='right', det=det)
    report = nav.observe(frame(0.0))
    assert report['spawn_lane_active'] is True
    assert report['spawn_lane_aim_raw_deg'] == pytest.approx(-24.2)
    assert report['spawn_lane_aim_applied_deg'] == pytest.approx(-10.0)
    assert report['follow_bearing_applied_deg'] == pytest.approx(-10.0)
    row = nav.command(0.0)
    assert row['duration_s'][1] < row['duration_s'][0]


def test_the_bound_is_lane_referenced_not_camera_relative():
    # The lane frame is the own-odometry frame (x = heading at the first issued
    # command).  With 8 deg of own-odometry yaw already turned left and a +10 deg
    # camera bearing, the aim is 18 deg off the lane, so it is capped at +10 deg
    # in the lane frame -> +2 deg camera bearing.  A camera-relative clamp would
    # have applied +10 deg instead, so this separates the two readings.
    nav = navigator(slot='left', det=detection(bearing_deg=10.0,
                                               bbox=(100, 180, 500, ROW_LAST_ABOVE)))
    nav._odom_yaw_deg = 8.0
    report = nav.observe(frame(0.0))
    assert report['spawn_lane_active'] is True
    assert report['spawn_lane_aim_raw_deg'] == pytest.approx(18.0)
    assert report['spawn_lane_aim_applied_deg'] == pytest.approx(10.0)
    assert report['follow_bearing_raw_deg'] == pytest.approx(10.0)
    assert report['follow_bearing_applied_deg'] == pytest.approx(2.0)
    assert nav.command(0.0)['duration_s'][0] > (1.0 - 10.0 / sn.BEARING_FULL_DEG) * sn.PULSE_S


def test_aim_inside_the_lane_bound_is_left_untouched():
    nav = navigator(slot='left', det=detection(bearing_deg=6.0,
                                               bbox=(100, 180, 500, ROW_LAST_ABOVE)))
    report = nav.observe(frame(0.0))
    assert report['spawn_lane_active'] is True
    assert report['spawn_lane_aim_raw_deg'] == pytest.approx(6.0)
    assert report['spawn_lane_aim_applied_deg'] == pytest.approx(6.0)
    assert report['follow_bearing_applied_deg'] == pytest.approx(6.0)


# --- release at the ground-projection door pass ------------------------------
def test_stage2_releases_the_bound_and_keeps_the_r5_slot_aim():
    # bottom row 139 -> 1.4915 m: the one-shot latch opens, so the r5 +-15 deg
    # slot aim applies even though it exceeds the stage-1 10 deg lane bound.
    det = detection(bearing_deg=0.0, left_edge=40.0, right_edge=-40.0,
                    bbox=(20, 100, 620, ROW_LAST_INSIDE))
    nav = navigator(slot='left', det=det)
    nav._odom_yaw_deg = 8.0
    report = nav.observe(frame(0.0))
    assert report['slot_stage2_active'] is True
    assert report['spawn_lane_active'] is False
    assert report['spawn_lane_aim_raw_deg'] is None
    assert report['spawn_lane_aim_applied_deg'] is None
    assert report['slot_bearing_offset_raw_deg'] == pytest.approx(20.0)
    assert report['slot_bearing_offset_applied_deg'] == pytest.approx(15.0)
    assert report['follow_bearing_raw_deg'] == pytest.approx(15.0)
    assert report['follow_bearing_applied_deg'] == pytest.approx(15.0)
    # owner: r5's right slot mirrors the offset.
    right = navigator(slot='right', det=detection(bearing_deg=0.0, left_edge=40.0,
                                                  right_edge=-40.0,
                                                  bbox=(20, 100, 620, ROW_LAST_INSIDE)))
    right_report = right.observe(frame(0.0))
    assert right_report['spawn_lane_active'] is False
    assert right_report['follow_bearing_applied_deg'] == pytest.approx(-15.0)


def test_stage1_bound_never_touches_the_armed_direction_or_the_0_52_claim():
    # The arming detection is inside 1.5 m, so stage 2 is active from tick 0 and
    # the r5 claim must still be the component-centre 0.52 m projection (37
    # ticks, 0.5211 m) — the N1 bound may not change u or the claim.
    nav = navigator(slot='left', det=detection(bottom_norm=0.967,
                                               bbox=(180, 300, 460, 469)))
    reports = []
    for tick in range(45):
        now = tick / 10.0
        reports.append(nav.observe(frame(now)))
        nav.command(now)
    assert reports[0]['slot_stage2_active'] is True
    assert reports[0]['spawn_lane_active'] is False
    assert reports[0]['arrival_armed'] is True
    assert reports[0]['arrival_bearing_armed_deg'] == 0.0
    assert reports[0]['arrival_u_deg'] == 0.0
    assert reports[0]['slot_bearing_offset_raw_deg'] == pytest.approx(5.0)
    # After arming the r3 heading-hold owns the plan (the slot aim is not
    # recomputed), exactly as in r5; the stage-2 aim itself is checked by
    # test_stage2_releases_the_bound_and_keeps_the_r5_slot_aim.
    assert reports[0]['arrival_armed'] is True
    claim = next(i for i, r in enumerate(reports) if r['destination_arrived'])
    assert claim == 37
    assert reports[claim]['arrival_projection_m'] >= sn.ARRIVAL_ODOM_PROJECTION_M
    assert sn.ARRIVAL_ODOM_PROJECTION_M == 0.52
    assert sn.ARRIVAL_PROJECTION_PATH_CAP_M == 1.0


# --- default OFF / fail closed ----------------------------------------------
def test_default_off_keeps_r5_behaviour_and_report_bytes():
    # No lane option: the +24.2 deg r5 aim is applied unclamped and none of the
    # N1-only report keys appear, so r4/r5 rows stay byte-identical.
    nav = navigator(lane=None, det=detection(bearing_deg=24.2,
                                             bbox=(100, 180, 500, ROW_LAST_ABOVE)))
    assert nav.spawn_lane_limit_deg is None
    report = nav.observe(frame(0.0))
    assert 'spawn_lane_limit_deg' not in report
    assert 'spawn_lane_active' not in report
    assert 'spawn_lane_aim_raw_deg' not in report
    assert 'spawn_lane_aim_applied_deg' not in report
    assert 'follow_bearing_raw_deg' not in report
    assert 'follow_bearing_applied_deg' not in report
    # the r5 path: bearing 24.2 deg -> left wheel 1 - 24.2/45 of full scale.
    row = nav.command(0.0)
    assert row['duration_s'][0] == pytest.approx((1.0 - 24.2 / sn.BEARING_FULL_DEG) * sn.PULSE_S)
    # and the same navigator with the N1 bound *does* move that wheel sign to the
    # 10 deg value, so the default-off check is not vacuous.
    bounded = navigator(det=detection(bearing_deg=24.2,
                                      bbox=(100, 180, 500, ROW_LAST_ABOVE)))
    bounded.observe(frame(0.0))
    assert bounded.command(0.0)['duration_s'][0] == pytest.approx(
        (1.0 - 10.0 / sn.BEARING_FULL_DEG) * sn.PULSE_S)


def test_spawn_lane_limit_fails_closed_without_the_two_stage_latch():
    with pytest.raises(ValueError, match='spawn lane limit requires'):
        sn.SelfCentricNavigation(
            'r1', {}, option=sn.OPTION, detector=lambda _f: [], odometry=odometry(),
            acquisition_mode=sn.ACQUISITION_FORWARD_THEN_SEARCH, forward_cap_m=2.4,
            arrival_mode=sn.ARRIVAL_ODOM_PROJECTION, slot='left',
            slot_stage2_ground_m=None, spawn_lane_limit_deg=10.0)
    for bad in (0.0, -10.0, 91.0):
        with pytest.raises(ValueError, match='spawn lane limit must be'):
            sn.SelfCentricNavigation(
                'r1', {}, option=sn.OPTION, detector=lambda _f: [], odometry=odometry(),
                acquisition_mode=sn.ACQUISITION_FORWARD_THEN_SEARCH, forward_cap_m=2.4,
                arrival_mode=sn.ARRIVAL_ODOM_PROJECTION, slot='left',
                slot_stage2_ground_m=1.5, spawn_lane_limit_deg=bad)


# --- gate wiring (default OFF) ----------------------------------------------
def test_v230_n1_is_default_off_and_binds_every_r5_and_n1_marker(tmp_path):
    assert gate.gate_mode()['name'] == gate.GATE_MODE_V1
    assert gate.GATE_MODES[gate.GATE_MODE_V230_N1]['slot_stage2_ground_m'] == 1.5
    assert gate.GATE_MODES[gate.GATE_MODE_V230_N1]['slot_offset_limit_deg'] == 15.0
    assert gate.GATE_MODES[gate.GATE_MODE_V230_N1]['spawn_lane_limit_deg'] == 10.0
    assert sn.SPAWN_LANE_LIMIT_DEG == 10.0
    cal = _calibration(tmp_path)
    queue = _queue(gate.GATE_MODE_V230_N1, cal, **{gate.ARRIVAL_ENV: 'odom_projection'})
    gate.validate_gate_queue(queue)
    assert queue['nav_gate_mode'] == 'v230_n1'
    assert queue['nav_slots'] == {'r1': 'left', 'r2': 'right'}
    assert queue['nav_slot_stage2_ground_m'] == 1.5
    assert queue['nav_slot_offset_limit_deg'] == 15.0
    assert queue['nav_spawn_lane_limit_deg'] == 10.0
    assert queue['nav_arrival_mode'] == 'odom_projection'
    assert queue['nav_arrival_odom_projection_m'] == 0.52
    assert queue['nav_arrival_projection_path_cap_m'] == 1.0
    assert queue['nav_acquire_min_height_norm'] == sn.ACQUIRE_MIN_HEIGHT_NORM == 0.02
    assert queue['nav_acquire_confirm_ticks'] == sn.ACQUIRE_CONFIRM_TICKS == 3
    assert queue['nav_forward_cap_m'] == 2.4
    assert queue['nav_zone_profile'] == 'gpu_calib_v230'
    assert queue['nav_bearing_convention'] == 'positive_left'
    assert 'nav_solo_robot' not in queue


def test_v230_n1_rejects_missing_or_retuned_lane_marker(tmp_path):
    cal = _calibration(tmp_path)
    queue = _queue(gate.GATE_MODE_V230_N1, cal, **{gate.ARRIVAL_ENV: 'odom_projection'})
    missing = dict(queue)
    missing.pop('nav_spawn_lane_limit_deg')
    with pytest.raises(ValueError, match='NAV_SPAWN_LANE_LIMIT_REQUIRED'):
        gate.validate_gate_queue(missing)
    with pytest.raises(ValueError, match='NAV_SPAWN_LANE_LIMIT_MISMATCH'):
        gate.validate_gate_queue(dict(queue, nav_spawn_lane_limit_deg=11.0))
    # the r5 marker set still requires the r5 stage-2 markers in n1.
    with pytest.raises(ValueError, match='NAV_SLOT_STAGE2_MARKERS_REQUIRED'):
        gate.validate_gate_queue(dict(queue, nav_slot_stage2_ground_m=None))


def test_r5_stays_byte_identical_and_rejects_the_n1_lane_marker(tmp_path):
    cal = _calibration(tmp_path)
    r5 = _queue(gate.GATE_MODE_V230_R5, cal, **{gate.ARRIVAL_ENV: 'odom_projection'})
    gate.validate_gate_queue(r5)
    assert r5['nav_gate_mode'] == 'v230_r5'
    assert 'nav_spawn_lane_limit_deg' not in r5
    with pytest.raises(ValueError, match='NAV_SPAWN_LANE_LIMIT_REQUIRE_V230_N1'):
        gate.validate_gate_queue(dict(r5, nav_spawn_lane_limit_deg=10.0))
    # and an n1 queue cannot run as r5: flipping only the mode fails closed on
    # the mode binding before the lane marker is even consulted.
    n1 = _queue(gate.GATE_MODE_V230_N1, cal, **{gate.ARRIVAL_ENV: 'odom_projection'})
    with pytest.raises(ValueError, match='NAV_GATE_MODE_MISMATCH'):
        gate.validate_gate_queue(dict(n1, nav_gate_mode='v230_r5'))


def test_factory_binds_the_lane_limit_only_in_n1(tmp_path):
    cal = _calibration(tmp_path)
    gate._ADMITTED = cal
    slots = {'r1': 'left', 'r2': 'right'}
    _queue(gate.GATE_MODE_V230_N1, cal, **{gate.ARRIVAL_ENV: 'odom_projection'})
    nav = gate.navigation_factory('r1', {'slots': slots})
    assert nav.slot == 'left'
    assert nav.slot_stage2_ground_m == 1.5
    assert nav.spawn_lane_limit_deg == 10.0
    assert nav.arrival_projection_m == 0.52
    assert nav.arrival_projection_path_cap_m == 1.0
    with pytest.raises(ValueError, match='NAV_SLOT_REQUIRED'):
        gate.navigation_factory('r1', None)
    # r5 has the same stage-2 latch but no lane bound.
    _queue(gate.GATE_MODE_V230_R5, cal, **{gate.ARRIVAL_ENV: 'odom_projection'})
    r5 = gate.navigation_factory('r1', {'slots': slots})
    assert r5.slot_stage2_ground_m == 1.5
    assert r5.spawn_lane_limit_deg is None
    # r4 has neither.
    _queue(gate.GATE_MODE_V230_R4, cal, **{gate.ARRIVAL_ENV: 'odom_projection'})
    r4 = gate.navigation_factory('r1', {'slots': slots})
    assert r4.slot_stage2_ground_m is None
    assert r4.spawn_lane_limit_deg is None


def test_solo_diagnostic_queue_is_allowed_for_n1(tmp_path):
    cal = _calibration(tmp_path)
    solo = _queue(gate.GATE_MODE_V230_N1, cal, robots=('r1',),
                  **{gate.ARRIVAL_ENV: 'odom_projection'})
    gate.validate_gate_queue(solo)
    assert solo['nav_robots'] == ['r1']
    assert solo['nav_solo_robot'] == 'r1'
    assert solo['nav_slots'] == {'r1': 'left'}
    assert solo['nav_slot_stage2_ground_m'] == 1.5
    assert solo['nav_spawn_lane_limit_deg'] == 10.0
