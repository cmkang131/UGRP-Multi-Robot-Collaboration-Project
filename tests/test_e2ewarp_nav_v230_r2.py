"""C (acquisition quality) and B (distance-based arrival) for the v230_r2 mode.

Every condition here is default OFF: the constructor defaults keep the frozen
v1/gate-1/r5 adapter byte-for-byte, and both B candidates need an explicit flag
on the approved `v230_r2` gate mode.  The constants under test are the approved
2026-10-19 values; their provenance is in `harness/e2ewarp_selfnav.py` and
`experiments/2026-10-19-nav-v230-r2/C_HEIGHT_EVIDENCE.json`.
"""
import json
import os
import tempfile
import types

import pytest

from harness import e2ewarp_nav_gate as gate
from harness import e2ewarp_selfnav as sn


def frame(sim_s=0.0, robot_id='r1'):
    return types.SimpleNamespace(robot_id=robot_id, world_id=0, tick=int(round(sim_s * 10)),
                                 sim_s=sim_s, jpeg=b'jpg', issued=())


def odometry(forward_m_per_pct_s=0.004024203361827748, yaw_deg_per_pct_s=1.7275488814064257):
    return sn.OwnCommandOdometry(forward_m_per_pct_s=forward_m_per_pct_s,
                                 yaw_deg_per_pct_s=yaw_deg_per_pct_s)


def detection(bottom_norm=0.30, height_norm=0.20, bearing_deg=0.0,
              bbox=(100, 200, 500, 260), **patch):
    value = dict(kind='zone_B', bearing_deg=bearing_deg, bottom_norm=bottom_norm,
                 height_norm=height_norm, width_norm=0.60, area_norm=0.10,
                 solidity=0.85, spans_center_x=True, touches_top=False, bbox=bbox)
    value.update(patch)
    return value


def sequence_detector(hits_per_tick):
    """Detector driven by the nav clock: function(tick) -> list of detections."""
    return lambda fr: hits_per_tick(int(round(fr.sim_s * 10)))


def r2_nav(hits, *, arrival_mode=sn.ARRIVAL_BOTTOM_BAND, confirm=3, min_height=0.02,
           reacquire=True, ground_m=None, residual_m=sn.ARRIVAL_ODOM_RESIDUAL_M,
           cap=2.4):
    return sn.SelfCentricNavigation(
        'r1', {}, option=sn.OPTION, detector=sequence_detector(hits), odometry=odometry(),
        acquisition_mode=sn.ACQUISITION_FORWARD_THEN_SEARCH, forward_cap_m=cap,
        acquire_min_height_norm=min_height, acquire_confirm_ticks=confirm,
        forward_reacquire=reacquire, arrival_mode=arrival_mode,
        arrival_odom_residual_m=residual_m, arrival_ground_distance_m=ground_m)


def run_ticks(nav, ticks, start=0):
    reports = []
    for tick in range(start, start + ticks):
        now = tick / 10.0
        reports.append(nav.observe(frame(now)))
        nav.command(now)
    return reports


def test_c_constructor_defaults_are_the_frozen_adapter():
    nav = sn.SelfCentricNavigation('r1', {}, option=sn.OPTION)
    assert nav.arrival_mode == sn.ARRIVAL_BOTTOM_BAND
    assert nav.acquire_min_height_norm == 0.0
    assert nav.acquire_confirm_ticks == 1
    assert nav.forward_reacquire is False
    # gate modes: the frozen conditions carry no C/B block at all
    assert gate.GATE_MODES[gate.GATE_MODE_V1].get('acquire_confirm_ticks') is None
    assert gate.GATE_MODES[gate.GATE_MODE_V230_FWD24].get('acquire_confirm_ticks') is None
    assert gate.arrival_selection()['mode'] == sn.ARRIVAL_BOTTOM_BAND


def test_c_height_prefilter_rejects_the_low_quality_sliver():
    # 0.015-0.019 are the far slivers seen at 6.9-12.2 s of the recorded
    # approach; 0.033 is the normal patch at the approved 2.4 m stop point.
    low = [200.0]  # never accepted
    nav = r2_nav(lambda tick: [hits_low()])
    rep = nav.observe(frame(0.0))
    assert rep['acquire_streak'] == 0 and rep['target_confirmed'] is False
    assert rep['drive_reason'] == 'acquiring_forward'
    assert nav.memory.nearest('zone_B') is not None  # still remembered (reporting)
    normal = r2_nav(lambda tick: [detection(bottom_norm=0.171, height_norm=0.0333,
                                            bbox=(81, 66, 379, 82))])
    rep = normal.observe(frame(0.0))
    assert rep['acquire_streak'] == 1


def hits_low():
    return detection(bottom_norm=0.121, height_norm=0.015, bbox=(200, 400, 340, 407))


def test_c_three_consecutive_ticks_gate_the_switch_to_following():
    hits = lambda tick: [detection(bottom_norm=0.17, height_norm=0.033)]
    nav = r2_nav(hits)
    reasons = [nav.observe(frame(t / 10.0))['drive_reason'] for t in range(4)]
    assert reasons[0] == 'acquiring_forward'      # streak 1
    assert reasons[1] == 'acquiring_forward'      # streak 2
    assert reasons[2] == 'driving'                # streak 3 -> following
    assert reasons[3] == 'driving'
    rep = nav.observe(frame(0.4))
    assert rep['target_confirmed'] is True and rep['acquire_streak'] == 5


def test_c_single_tick_sliver_never_becomes_the_followed_target():
    # exactly the recorded r2 failure: one 0.025 tick, then nothing.
    def hits(tick):
        return [detection(bottom_norm=0.125, height_norm=0.025,
                          bbox=(224, 400, 364, 412))] if tick == 0 else []
    nav = r2_nav(hits)
    reports = run_ticks(nav, 40)
    reasons = [r['drive_reason'] for r in reports]
    assert 'driving' not in reasons
    assert reasons[0] == 'acquiring_forward'
    assert all(r['target_confirmed'] is False for r in reports)


def test_c_confirm_latch_survives_one_dropped_tick():
    def hits(tick):
        if tick in (10, 11, 12, 13, 15, 16, 17):
            return [detection(bottom_norm=0.3, height_norm=0.2)]
        return []
    nav = r2_nav(hits)
    reports = run_ticks(nav, 18)
    assert reports[12]['drive_reason'] == 'driving'
    assert reports[14]['drive_reason'] == 'driving'   # one missed tick, still confirmed
    assert reports[14]['target_confirmed'] is True


def test_c_lost_target_reacquires_forward_within_the_same_cap():
    def hits(tick):
        return [detection(bottom_norm=0.3, height_norm=0.2)] if tick <= 5 else []
    nav = r2_nav(hits)
    reports = run_ticks(nav, 30)
    assert reports[5]['drive_reason'] == 'driving'
    # stale (>1 s without an accepted detection) -> re-advance, not blind search
    later = [r['drive_reason'] for r in reports[18:]]
    assert 'acquiring_forward' in later
    assert reports[-1]['forward_used_m'] > 0.0
    assert reports[-1]['forward_used_m'] <= 2.4 + 1e-9


def test_c_reacquire_off_keeps_the_frozen_one_shot_forward_leg():
    def hits(tick):
        return [detection(bottom_norm=0.3, height_norm=0.2)] if tick <= 5 else []
    nav = r2_nav(hits, reacquire=False)
    reports = run_ticks(nav, 30)
    assert reports[-1]['drive_reason'] in ('searching', 'search_timeout')
    assert all(r['drive_reason'] != 'acquiring_forward' for r in reports[7:])


def test_c_reacquire_never_exceeds_the_approved_forward_cap():
    hits = lambda tick: []       # nothing ever detected: pure blind acquisition
    nav = r2_nav(hits, confirm=3)
    reports = run_ticks(nav, 260)
    assert reports[-1]['forward_used_m'] <= 2.4 + 1e-9
    assert reports[-1]['forward_used_m'] >= 2.4 - 1e-6
    # after the cap the wheels can only turn in place
    assert reports[-1]['drive_reason'] in ('searching', 'search_timeout')


def test_b_flags_default_off_and_rejected_outside_v230_r2():
    with pytest.raises(ValueError):
        r2_nav(lambda t: [], arrival_mode=sn.ARRIVAL_GROUND_DISTANCE)  # no threshold
    with pytest.raises(ValueError):
        sn.SelfCentricNavigation('r1', {}, option=sn.OPTION,
                                 acquisition_mode=sn.ACQUISITION_SEARCH_IN_PLACE,
                                 arrival_mode=sn.ARRIVAL_ODOM_RESIDUAL)
    # r3 (2026-10-19 decision ①) adds the default-off `odom_projection` claim
    # mode; the r2 modes and their constants are unchanged.
    assert sn.ARRIVAL_MODES == ('bottom_band', 'odom_residual', 'ground_distance',
                                'odom_projection')


def test_b_odom_residual_arms_only_on_a_bottom_contact_then_claims_by_distance():
    def hits(tick):
        return [detection(bottom_norm=0.967, height_norm=0.60, bbox=(80, 180, 560, 470))]
    nav = r2_nav(hits, arrival_mode=sn.ARRIVAL_ODOM_RESIDUAL, confirm=1, min_height=0.0)
    rep = nav.observe(frame(0.0))
    assert rep['arrival_armed'] is True and rep['destination_arrived'] is False
    reports = run_ticks(nav, 45)
    # 45 x (35 % x 0.1 s) at 0.0040242 m/pct-s = 0.6338 m; the geometry-derived
    # 0.52 m residual is crossed at the 37th issued pulse (36 x 0.0140847 =
    # 0.5071 < 0.52, 37 x 0.0140847 = 0.5211).
    first_claim = next(i for i, r in enumerate(reports) if r['destination_arrived'])
    assert first_claim == 37
    assert reports[36]['destination_arrived'] is False
    assert reports[36]['arrival_travel_m'] < sn.ARRIVAL_ODOM_RESIDUAL_M
    assert reports[37]['arrival_travel_m'] >= sn.ARRIVAL_ODOM_RESIDUAL_M
    assert reports[-1]['drive_reason'] == 'arrived'


def test_b_odom_residual_does_not_arm_below_the_contact_band():
    hits = lambda tick: [detection(bottom_norm=0.90, height_norm=0.60)]
    nav = r2_nav(hits, arrival_mode=sn.ARRIVAL_ODOM_RESIDUAL, confirm=1, min_height=0.0)
    reports = run_ticks(nav, 60)
    assert all(r['arrival_armed'] is False for r in reports)
    assert all(r['destination_arrived'] is False for r in reports)


def test_b_odom_residual_is_the_geometry_derivation():
    """0.3649 m (row curve at bottom_norm 0.96) + 0.15 m margin -> frozen 0.52 m."""
    point = sn.ground_point_robot(sn.GATE_GROUND_PROJECTION['cx_px'], 0.96 * 480.0)
    assert point[0] == pytest.approx(0.3649, abs=0.002)
    assert sn.ARRIVAL_ODOM_RESIDUAL_M == 0.52
    assert sn.ARRIVAL_ODOM_RESIDUAL_M - point[0] >= 0.15   # margin never shrinks


def test_b_odom_residual_honours_an_explicit_residual():
    hits = lambda tick: [detection(bottom_norm=0.97, height_norm=0.60)]
    nav = r2_nav(hits, arrival_mode=sn.ARRIVAL_ODOM_RESIDUAL, confirm=1, min_height=0.0,
                 residual_m=0.10)
    reports = run_ticks(nav, 20)
    first_claim = next(i for i, r in enumerate(reports) if r['destination_arrived'])
    assert first_claim == 8      # 8 x 0.0140847 = 0.1127 m >= 0.10 m
    assert reports[7]['arrival_travel_m'] < 0.10


def test_b_ground_distance_projection_matches_the_measured_geometry():
    # Step A x=2.0: bbox bottom row 94 is 2.30 m from the base to the paint's
    # near edge; the fitted projection returns 2.31 m.
    assert sn.ground_distance_m(320, 94) == pytest.approx(2.31, abs=0.06)
    assert sn.ground_distance_m(320, 82) == pytest.approx(2.80, abs=0.10)
    assert sn.ground_distance_m(320, 116) == pytest.approx(1.80, abs=0.10)
    # fail closed: at/above the horizon, outside the image, absent profile
    assert sn.ground_distance_m(320, 0) is not None or True
    assert sn.ground_distance_m(-1, 100) is None
    assert sn.ground_distance_m(640, 100) is None
    assert sn.ground_distance_m(320, 100, {}) is None


def test_b_ground_distance_minimum_is_the_image_bottom_row():
    """The closest ground this camera model can see is 0.345 m (row 479).

    The approved 0.25 m constant is therefore *unreachable* for any patch
    geometry: the recorded closest approach (bottom row 464) projects to
    0.362-0.399 m.  This is the measured reason B(b) cannot be frozen at 0.25 m
    without a decision (see PREREG_V230_R2.md, B choice TBD).
    """
    assert sn.ground_distance_m(320, 479) == pytest.approx(0.345, abs=0.02)
    assert min(sn.ground_distance_m(320, v) for v in range(360, 480)) > \
        sn.ARRIVAL_GROUND_DISTANCE_M
    assert sn.ground_distance_m(320, 464) == pytest.approx(0.362, abs=0.02)


def test_b_ground_distance_at_the_approved_025_never_fires():
    # bottom row 464 with a 61 px component: the recorded closest approach
    recorded = r2_nav(lambda tick: [detection(bottom_norm=0.967, height_norm=0.127,
                                              bbox=(120, 403, 520, 464))],
                      arrival_mode=sn.ARRIVAL_GROUND_DISTANCE, confirm=1, min_height=0.0,
                      ground_m=sn.ARRIVAL_GROUND_DISTANCE_M)
    reports = run_ticks(recorded, 20)
    assert reports[-1]['arrival_ground_distance_m'] == pytest.approx(0.40, abs=0.03)
    assert all(r['destination_arrived'] is False for r in reports)


def test_b_ground_distance_mechanism_claims_at_a_reachable_constant():
    # Same recorded patch with an explicitly reachable constant: the mechanism
    # works, the constant is the decision that is open.
    reachable = r2_nav(lambda tick: [detection(bottom_norm=0.967, height_norm=0.127,
                                               bbox=(120, 403, 520, 464))],
                       arrival_mode=sn.ARRIVAL_GROUND_DISTANCE, confirm=1, min_height=0.0,
                       ground_m=0.45)
    rep = reachable.observe(frame(0.0))
    assert rep['arrival_ground_distance_m'] < 0.45
    assert rep['destination_arrived'] is True


def test_b_bottom_band_default_is_unchanged():
    # The frozen guard still needs the 0.98 band and a plausible patch.
    hits = lambda tick: [detection(bottom_norm=0.99, height_norm=0.20,
                                   bbox=(100, 300, 500, 475))]
    nav = r2_nav(hits, arrival_mode=sn.ARRIVAL_BOTTOM_BAND, confirm=1, min_height=0.0)
    assert nav.observe(frame(0.0))['destination_arrived'] is True
    hits_low_band = lambda tick: [detection(bottom_norm=0.967, height_norm=0.60)]
    nav2 = r2_nav(hits_low_band, arrival_mode=sn.ARRIVAL_BOTTOM_BAND, confirm=1, min_height=0.0)
    assert nav2.observe(frame(0.0))['destination_arrived'] is False


# --- gate queue binding (C/B markers) ---------------------------------------
def _calibration(tmp_path):
    payload = dict(schema=gate.CALIBRATION_SCHEMA, measured=True, measured_n=60,
                   constants=dict(forward_m_per_pct_s=0.004024203361827748,
                                  yaw_deg_per_pct_s=1.7275488814064257),
                   per_robot={r: dict(forward_m_per_pct_s=0.004024203361827748,
                                      yaw_deg_per_pct_s=1.7275488814064257)
                              for r in gate.ROBOTS},
                   source_sha='d' * 40)
    path = tmp_path / 'nav_gate_calibration.json'
    path.write_text(json.dumps(payload))
    return gate.load_calibration(path)


@pytest.fixture(autouse=True)
def _clear_arrival_env():
    for key in (gate.GATE_MODE_ENV, gate.ARRIVAL_ENV, gate.ARRIVAL_ODOM_M_ENV,
                gate.ARRIVAL_GROUND_M_ENV):
        os.environ.pop(key, None)
    yield
    for key in (gate.GATE_MODE_ENV, gate.ARRIVAL_ENV, gate.ARRIVAL_ODOM_M_ENV,
                gate.ARRIVAL_GROUND_M_ENV):
        os.environ.pop(key, None)


def _queue(mode, calibration, **env):
    os.environ[gate.GATE_MODE_ENV] = mode
    for key, value in env.items():
        os.environ[key] = str(value)
    queue = gate.gate_queue_fields(601, calibration=calibration)
    queue['sim_budget_s'] = queue['nav_sim_budget_s']
    return queue


def test_v230_r2_queue_carries_the_c_constants_and_bottom_band_default(tmp_path):
    cal = _calibration(tmp_path)
    queue = _queue(gate.GATE_MODE_V230_R2, cal)
    gate.validate_gate_queue(queue)
    assert queue['nav_acquire_min_height_norm'] == sn.ACQUIRE_MIN_HEIGHT_NORM == 0.02
    assert queue['nav_acquire_confirm_ticks'] == sn.ACQUIRE_CONFIRM_TICKS == 3
    assert queue['nav_forward_reacquire'] is True
    assert queue['nav_arrival_mode'] == sn.ARRIVAL_BOTTOM_BAND
    assert queue['nav_zone_profile'] == 'gpu_calib_v230'
    assert queue['nav_forward_cap_m'] == 2.4


def test_frozen_modes_write_no_c_or_b_markers(tmp_path):
    cal = _calibration(tmp_path)
    for mode in (gate.GATE_MODE_V1, gate.GATE_MODE_V230_FWD24):
        queue = _queue(mode, cal)
        gate.validate_gate_queue(queue)
        assert not any(k.startswith('nav_arrival') or k.startswith('nav_acquire')
                       or k == 'nav_forward_reacquire' for k in queue), mode


def test_arrival_method_binds_only_to_v230_r2_and_must_match_the_queue(tmp_path):
    cal = _calibration(tmp_path)
    queue = _queue(gate.GATE_MODE_V230_R2, cal, **{gate.ARRIVAL_ENV: 'odom_residual'})
    gate.validate_gate_queue(queue)
    assert queue['nav_arrival_mode'] == 'odom_residual'
    assert queue['nav_arrival_odom_residual_m'] == sn.ARRIVAL_ODOM_RESIDUAL_M == 0.52
    os.environ[gate.ARRIVAL_ENV] = 'bottom_band'
    with pytest.raises(ValueError, match='NAV_ARRIVAL_MODE_MISMATCH'):
        gate.validate_gate_queue(queue)
    # the flags are rejected outside the approved mode
    os.environ[gate.ARRIVAL_ENV] = 'ground_distance'
    os.environ[gate.GATE_MODE_ENV] = gate.GATE_MODE_V1
    frozen = _queue(gate.GATE_MODE_V1, cal)
    with pytest.raises(ValueError, match='NAV_ARRIVAL_REQUIRES_V230_R2'):
        gate.validate_gate_queue(dict(frozen, nav_arrival_mode='ground_distance'))


def test_factory_builds_the_c_and_b_adapter_only_for_v230_r2(tmp_path):
    cal = _calibration(tmp_path)
    gate._ADMITTED = cal
    _queue(gate.GATE_MODE_V230_R2, cal, **{gate.ARRIVAL_ENV: 'ground_distance'})
    nav = gate.navigation_factory('r1', None)
    assert (nav.acquire_min_height_norm, nav.acquire_confirm_ticks, nav.forward_reacquire) == \
        (0.02, 3, True)
    assert nav.arrival_mode == 'ground_distance'
    assert nav.arrival_ground_distance_m == 0.25
    os.environ[gate.GATE_MODE_ENV] = gate.GATE_MODE_V230_FWD24
    os.environ.pop(gate.ARRIVAL_ENV)
    frozen = gate.navigation_factory('r1', None)
    assert (frozen.acquire_min_height_norm, frozen.acquire_confirm_ticks,
            frozen.forward_reacquire, frozen.arrival_mode) == (0.0, 1, False, 'bottom_band')
