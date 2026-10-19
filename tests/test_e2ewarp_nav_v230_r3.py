"""r3 (2026-10-19 decision ①): projection arrival claim along the armed bearing.

The claim is re-defined, not re-tuned: the same approved 0.52 m geometry
(`B_A_DERIVATION.json`) is measured as the projection of the own-odometry
displacement onto the own-memory bearing direction latched at the arming event,
instead of the r2 integrated path length.  Heading is held on that bearing with
the existing proportional turn controller, and a 1.0 m path fail-safe records
`NO_CLAIM` and holds the wheels when the projection never reaches the threshold.

Every condition here is default OFF: the constructor default stays the frozen
`bottom_band` claim and only the explicit `v230_r3` gate mode plus the
`--arrival-odom-projection` flag bind the new claim.
"""
import json
import os
import types
from pathlib import Path

import pytest

from harness import e2ewarp_nav_gate as gate
from harness import e2ewarp_nav_mode as navmode
from harness import e2ewarp_selfnav as sn

ROOT = Path(__file__).resolve().parents[1]
B_A_DERIVATION = ROOT / 'experiments/2026-10-19-nav-v230-r2/B_A_DERIVATION.json'
FORWARD = 0.004024203361827748
YAW = 1.7275488814064257


def frame(sim_s=0.0, robot_id='r1'):
    return types.SimpleNamespace(robot_id=robot_id, world_id=0, tick=int(round(sim_s * 10)),
                                 sim_s=sim_s, jpeg=b'jpg', issued=())


def odometry(forward_m_per_pct_s=FORWARD, yaw_deg_per_pct_s=YAW):
    return sn.OwnCommandOdometry(forward_m_per_pct_s=forward_m_per_pct_s,
                                 yaw_deg_per_pct_s=yaw_deg_per_pct_s)


def detection(bottom_norm=0.30, height_norm=0.20, bearing_deg=0.0,
              bbox=(100, 200, 500, 260), **patch):
    value = dict(kind='zone_B', bearing_deg=bearing_deg, bottom_norm=bottom_norm,
                 height_norm=height_norm, width_norm=0.60, area_norm=0.10,
                 solidity=0.85, spans_center_x=True, touches_top=False, bbox=bbox)
    value.update(patch)
    return value


def r3_nav(hits, *, odom=None, bearing_deg=0.0, **kwargs):
    det = detection(bottom_norm=0.967, height_norm=0.60, bearing_deg=bearing_deg)
    detector = hits if callable(hits) else (lambda fr: [det])
    options = dict(acquire_min_height_norm=0.0, acquire_confirm_ticks=1,
                   forward_reacquire=True)
    options.update(kwargs)
    return sn.SelfCentricNavigation(
        'r1', {}, option=sn.OPTION, detector=detector, odometry=odom or odometry(),
        acquisition_mode=sn.ACQUISITION_FORWARD_THEN_SEARCH, forward_cap_m=2.4,
        arrival_mode=sn.ARRIVAL_ODOM_PROJECTION, **options)


def run_ticks(nav, ticks, start=0):
    reports, rows = [], []
    for tick in range(start, start + ticks):
        now = tick / 10.0
        reports.append(nav.observe(frame(now)))
        rows.append(nav.command(now))
    return reports, rows


def first_true(rows, key):
    return next((i for i, r in enumerate(rows) if r.get(key)), None)


# --- the claim definition ----------------------------------------------------
def test_r3_claim_is_the_projection_and_holds_the_frozen_0_52_m():
    nav = r3_nav(None)
    reports, _rows = run_ticks(nav, 60)
    assert reports[0]['arrival_armed'] is True
    assert reports[0]['drive_reason'] == 'driving_hold_heading'
    claim = first_true(reports, 'destination_arrived')
    # 36 x 0.0140847 = 0.5071 < 0.52, 37 x 0.0140847 = 0.5211.
    assert claim == 37
    assert reports[36]['arrival_projection_m'] < sn.ARRIVAL_ODOM_PROJECTION_M
    assert reports[37]['arrival_projection_m'] >= sn.ARRIVAL_ODOM_PROJECTION_M
    assert reports[37]['arrival_projection_m'] == pytest.approx(reports[37]['arrival_path_m'],
                                                                abs=1e-6)
    assert reports[-1]['drive_reason'] == 'arrived'
    assert sn.ARRIVAL_ODOM_PROJECTION_M == 0.52
    assert sn.ARRIVAL_ODOM_PROJECTION_M == sn.ARRIVAL_ODOM_RESIDUAL_M


def test_r3_threshold_is_the_frozen_b_a_derivation_not_a_new_fit():
    derivation = json.loads(B_A_DERIVATION.read_text())
    # 0.3649 m (row curve at bottom_norm 0.96) + 0.15 m design margin = 0.5149 m
    # -> frozen 0.52 m.  The r3 claim reuses that number unchanged.
    assert derivation['frozen_flag_value_m'] == 0.52
    assert derivation['derived_residual_m'] == pytest.approx(0.5149, abs=1e-4)
    assert sn.ARRIVAL_ODOM_PROJECTION_M == pytest.approx(derivation['frozen_flag_value_m'])
    assert sn.ARRIVAL_ODOM_PROJECTION_M >= derivation['row_curve'][0]['residual_m']


def test_r3_projection_differs_from_path_length_and_claims_on_the_projection():
    # Armed with the destination 40 deg to the left: the path must be driven
    # while turning, so path > projection at the claim.  r2's path claim would
    # have stopped later (or earlier than the x reach it stands for).
    nav = r3_nav(None, bearing_deg=40.0)
    reports, _rows = run_ticks(nav, 80)
    claim = first_true(reports, 'destination_arrived')
    assert claim is not None and claim > 37
    assert reports[claim]['arrival_projection_m'] >= sn.ARRIVAL_ODOM_PROJECTION_M
    assert reports[claim - 1]['arrival_projection_m'] < sn.ARRIVAL_ODOM_PROJECTION_M
    assert reports[claim]['arrival_path_m'] > reports[claim]['arrival_projection_m'] + 0.01
    assert reports[claim]['arrival_path_m'] > sn.ARRIVAL_ODOM_PROJECTION_M


def test_r3_projection_claim_needs_no_current_landmark():
    # The claim is odometric: after arming, a lost visual target cannot revoke it.
    calls = {'n': 0}

    def hits(fr):
        calls['n'] += 1
        return [detection(bottom_norm=0.967, height_norm=0.60, bearing_deg=0.0)] if calls['n'] <= 2 else []

    nav = r3_nav(hits)
    reports, _rows = run_ticks(nav, 60)
    assert nav.memory.nearest('zone_B') is None or reports[-1]['arrival_armed'] is True
    assert reports[-1]['destination_arrived'] is True or first_true(reports, 'destination_arrived') is not None


# --- heading hold ------------------------------------------------------------
def test_r3_heading_hold_uses_the_turn_controller_with_the_yaw_error():
    nav = r3_nav(None, bearing_deg=30.0)
    reports, rows = run_ticks(nav, 40)
    assert reports[0]['arrival_u_deg'] == pytest.approx(30.0)
    assert reports[0]['arrival_heading_error_deg'] == pytest.approx(30.0)
    # The first issued row turns left: the right wheel carries the longer pulse
    # (differential (f, l=0, t) -> (f-t, f+t, f-t, f+t)).
    assert rows[0]['duration_s'][1] > rows[0]['duration_s'][0]
    assert rows[0]['duration_s'][3] > rows[0]['duration_s'][2]
    errors = [r['arrival_heading_error_deg'] for r in reports[:30]]
    assert errors[0] > errors[10] > errors[20]
    assert abs(reports[30]['odom_pose'][2] - reports[30]['arrival_u_deg']) < 6.0
    assert abs(reports[-1]['arrival_heading_error_deg']) < 3.0
    # The hold drives forward (full-scale r2 follower magnitude), not in place.
    assert all(abs(row['duration_s'][0]) > 0.0 for row in rows[:5])


def test_r3_heading_hold_zero_bearing_is_a_straight_leg():
    nav = r3_nav(None, bearing_deg=0.0)
    _reports, rows = run_ticks(nav, 10)
    for row in rows:
        assert row['duration_s'] == pytest.approx([0.1, 0.1, 0.1, 0.1])


# --- fail-safe ---------------------------------------------------------------
class _ForwardOnlyOdometry:
    """Own-command odometry stub: 0.1 m forward, no yaw (heading never converges)."""

    def step(self, row):
        return 0.1, 0.0


def test_r3_fail_safe_stops_at_the_1_0_m_path_cap_and_records_no_claim():
    # Armed with the bearing at +90 deg but an odometry that never yields yaw:
    # the projection stays 0 while the path grows, so the cap must stop the run.
    nav = r3_nav(None, odom=_ForwardOnlyOdometry(), bearing_deg=90.0)
    reports, rows = run_ticks(nav, 20)
    assert reports[8]['arrival_no_claim'] is False and reports[8]['arrival_path_m'] < 1.0
    assert reports[9]['arrival_no_claim'] is False       # 0.9 m path, still driving
    assert reports[10]['arrival_no_claim'] is True       # 1.0 m path, no claim
    assert reports[10]['arrival_path_m'] >= sn.ARRIVAL_PROJECTION_PATH_CAP_M
    assert reports[10]['arrival_projection_m'] == 0.0
    assert reports[10]['drive_reason'] == 'no_claim'
    assert rows[10]['wheels'] == [0.0, 0.0, 0.0, 0.0]
    assert rows[10]['duration_s'] == [0.0, 0.0, 0.0, 0.0]
    assert all(r['destination_arrived'] is False for r in reports)
    assert all(r['arrival_path_m'] <= sn.ARRIVAL_PROJECTION_PATH_CAP_M + 1e-9 for r in reports)


def test_r3_path_cap_is_the_directive_1_0_m_and_is_the_tighter_bound():
    assert sn.ARRIVAL_PROJECTION_PATH_CAP_M == 1.0
    # The directive writes 1.0 m (= 0.52 / 0.5); the exact ratio is 1.04 m, so
    # the frozen 1.0 m is the tighter (never later) fail-safe bound.
    assert sn.ARRIVAL_ODOM_PROJECTION_M / 0.5 == pytest.approx(1.04)
    assert sn.ARRIVAL_PROJECTION_PATH_CAP_M <= sn.ARRIVAL_ODOM_PROJECTION_M / 0.5


def test_r3_no_claim_event_is_recorded_once_in_the_nav_events():
    class Stub:
        def observe(self, frame):
            return dict(destination_arrived=False, arrival_no_claim=True)

        def task_candidates(self, completed):
            return []

        def start(self, instruction, phase='approach'):
            pass

        def command(self, now_s):
            return dict(t=now_s, wheels=[0.0] * 4, duration_s=[0.0] * 4, pwm={})

    controller = navmode.NavigationOnlyController('r1', {}, Stub())
    controller.phase = 'NAVIGATE'
    controller.observe(frame(1.0))
    controller.observe(frame(1.1))
    events = [e for e in controller.events if e['reason'].startswith('NO_CLAIM')]
    assert len(events) == 1
    assert events[0]['after'] == 'NAVIGATE'


# --- default off / frozen modes ---------------------------------------------
def test_r3_is_default_off_and_the_frozen_adapter_is_unchanged():
    nav = sn.SelfCentricNavigation('r1', {}, option=sn.OPTION)
    assert nav.arrival_mode == sn.ARRIVAL_BOTTOM_BAND
    assert nav.arrival_projection_m == sn.ARRIVAL_ODOM_PROJECTION_M
    assert nav.arrival_projection_path_cap_m == sn.ARRIVAL_PROJECTION_PATH_CAP_M
    assert nav._arrival_no_claim is False and nav._arrival_proj_m == 0.0
    assert gate.DEFAULT_GATE_MODE == gate.GATE_MODE_V1
    assert gate.GATE_MODES[gate.GATE_MODE_V1].get('acquire_confirm_ticks') is None
    assert gate.GATE_MODES[gate.GATE_MODE_V230_FWD24].get('acquire_confirm_ticks') is None
    # the r3 mode copies the r2 band/acquisition/C block exactly
    r2 = gate.GATE_MODES[gate.GATE_MODE_V230_R2]
    r3 = gate.GATE_MODES[gate.GATE_MODE_V230_R3]
    assert r3 == r2
    assert sn.ARRIVAL_ODOM_PROJECTION not in (sn.ARRIVAL_BOTTOM_BAND,
                                              sn.ARRIVAL_ODOM_RESIDUAL,
                                              sn.ARRIVAL_GROUND_DISTANCE)


def test_r3_projection_flag_is_rejected_outside_v230_r3(tmp_path):
    cal = _calibration(tmp_path)
    for mode in (gate.GATE_MODE_V1, gate.GATE_MODE_V230_FWD24):
        os.environ[gate.GATE_MODE_ENV] = mode
        os.environ[gate.ARRIVAL_ENV] = 'odom_projection'
        queue = gate.gate_queue_fields(601, calibration=cal)
        queue['sim_budget_s'] = queue['nav_sim_budget_s']
        with pytest.raises(ValueError, match='NAV_ARRIVAL_REQUIRES_V230_R2'):
            gate.validate_gate_queue(queue)
    os.environ[gate.GATE_MODE_ENV] = gate.GATE_MODE_V230_R2
    os.environ[gate.ARRIVAL_ENV] = 'odom_projection'
    queue = gate.gate_queue_fields(601, calibration=cal)
    queue['sim_budget_s'] = queue['nav_sim_budget_s']
    with pytest.raises(ValueError, match='NAV_ARRIVAL_REQUIRES_V230_R3'):
        gate.validate_gate_queue(queue)


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


@pytest.fixture(autouse=True)
def _clear_env():
    keys = (gate.GATE_MODE_ENV, gate.ARRIVAL_ENV, gate.ARRIVAL_ODOM_M_ENV,
            gate.ARRIVAL_GROUND_M_ENV)
    for key in keys:
        os.environ.pop(key, None)
    yield
    for key in keys:
        os.environ.pop(key, None)


def _queue(mode, calibration, **env):
    os.environ[gate.GATE_MODE_ENV] = mode
    for key, value in env.items():
        os.environ[key] = str(value)
    queue = gate.gate_queue_fields(601, calibration=calibration)
    queue['sim_budget_s'] = queue['nav_sim_budget_s']
    return queue


def test_v230_r3_queue_binds_the_projection_and_the_frozen_markers(tmp_path):
    cal = _calibration(tmp_path)
    queue = _queue(gate.GATE_MODE_V230_R3, cal, **{gate.ARRIVAL_ENV: 'odom_projection'})
    gate.validate_gate_queue(queue)
    assert queue['nav_gate_mode'] == 'v230_r3'
    assert queue['nav_arrival_mode'] == 'odom_projection'
    assert queue['nav_arrival_odom_projection_m'] == 0.52
    assert queue['nav_arrival_projection_path_cap_m'] == 1.0
    # the C block and the band/forward condition are the r2 ones, unchanged
    assert queue['nav_acquire_min_height_norm'] == sn.ACQUIRE_MIN_HEIGHT_NORM == 0.02
    assert queue['nav_acquire_confirm_ticks'] == sn.ACQUIRE_CONFIRM_TICKS == 3
    assert queue['nav_forward_reacquire'] is True
    assert queue['nav_zone_profile'] == 'gpu_calib_v230'
    assert queue['nav_forward_cap_m'] == 2.4
    assert queue['nav_bearing_convention'] == 'positive_left'


def test_v230_r3_requires_the_projection_flag_and_frozen_marker_values(tmp_path):
    cal = _calibration(tmp_path)
    queue = _queue(gate.GATE_MODE_V230_R3, cal)   # no arrival flag -> bottom_band
    with pytest.raises(ValueError, match='NAV_ARRIVAL_REQUIRES_V230_R3'):
        gate.validate_gate_queue(queue)
    queue = _queue(gate.GATE_MODE_V230_R3, cal, **{gate.ARRIVAL_ENV: 'odom_projection'})
    with pytest.raises(ValueError, match='NAV_ARRIVAL_ODOM_PROJECTION_MISMATCH'):
        gate.validate_gate_queue(dict(queue, nav_arrival_odom_projection_m=0.51))
    with pytest.raises(ValueError, match='NAV_ARRIVAL_PROJECTION_PATH_CAP_MISMATCH'):
        gate.validate_gate_queue(dict(queue, nav_arrival_projection_path_cap_m=1.04))


def test_v230_r2_queue_has_no_projection_markers(tmp_path):
    cal = _calibration(tmp_path)
    queue = _queue(gate.GATE_MODE_V230_R2, cal, **{gate.ARRIVAL_ENV: 'odom_residual'})
    gate.validate_gate_queue(queue)
    assert not any('projection' in key for key in queue)
    assert queue['nav_arrival_odom_residual_m'] == 0.52


def test_factory_builds_the_projection_claim_only_for_v230_r3(tmp_path):
    cal = _calibration(tmp_path)
    gate._ADMITTED = cal
    _queue(gate.GATE_MODE_V230_R3, cal, **{gate.ARRIVAL_ENV: 'odom_projection'})
    nav = gate.navigation_factory('r1', None)
    assert nav.arrival_mode == sn.ARRIVAL_ODOM_PROJECTION
    assert nav.arrival_projection_m == 0.52
    assert nav.arrival_projection_path_cap_m == 1.0
    assert (nav.acquire_min_height_norm, nav.acquire_confirm_ticks, nav.forward_reacquire) == \
        (0.02, 3, True)
    # r2 + the projection flag must fail closed, and r3 without the flag too
    os.environ[gate.GATE_MODE_ENV] = gate.GATE_MODE_V230_R2
    os.environ[gate.ARRIVAL_ENV] = 'odom_projection'
    with pytest.raises(ValueError, match='NAV_ARRIVAL_REQUIRES_V230_R3'):
        gate.navigation_factory('r1', None)
    os.environ[gate.GATE_MODE_ENV] = gate.GATE_MODE_V230_R3
    os.environ.pop(gate.ARRIVAL_ENV)
    with pytest.raises(ValueError, match='NAV_ARRIVAL_REQUIRES_V230_R3'):
        gate.navigation_factory('r1', None)


def test_r3_adapter_rejects_a_non_forward_acquisition_for_the_projection():
    with pytest.raises(ValueError):
        sn.SelfCentricNavigation('r1', {}, option=sn.OPTION,
                                 acquisition_mode=sn.ACQUISITION_SEARCH_IN_PLACE,
                                 arrival_mode=sn.ARRIVAL_ODOM_PROJECTION)
    with pytest.raises(ValueError):
        sn.SelfCentricNavigation('r1', {}, option=sn.OPTION,
                                 acquisition_mode=sn.ACQUISITION_FORWARD_THEN_SEARCH,
                                 forward_cap_m=2.4,
                                 arrival_mode=sn.ARRIVAL_ODOM_PROJECTION,
                                 arrival_projection_path_cap_m=0.0)


def test_projection_flag_binds_the_arrival_env_and_is_exclusive():
    from scripts import run_e2e_warp as runner
    parser = runner.build_parser()
    flagged = parser.parse_args(['--output', '/tmp/out', '--arrival-odom-projection'])
    runner.apply_arrival_args(flagged)
    assert os.environ[gate.ARRIVAL_ENV] == 'odom_projection'
    assert gate.ARRIVAL_ODOM_M_ENV not in os.environ       # no numeric override
    assert gate.ARRIVAL_GROUND_M_ENV not in os.environ
    ambiguous = parser.parse_args(['--output', '/tmp/out', '--arrival-odom-projection',
                                   '--arrival-odom-residual'])
    with pytest.raises(ValueError, match='NAV_ARRIVAL_METHOD_AMBIGUOUS'):
        runner.apply_arrival_args(ambiguous)
    plain = parser.parse_args(['--output', '/tmp/out'])
    runner.apply_arrival_args(plain)
    assert gate.ARRIVAL_ENV not in os.environ              # default stays off
    assert gate.ARRIVAL_ODOM_M_ENV not in os.environ
