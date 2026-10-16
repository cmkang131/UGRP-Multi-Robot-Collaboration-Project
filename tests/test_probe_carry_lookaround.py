"""Offline checks for the carry look-around probe (no physics)."""
import json
from pathlib import Path
from scripts.probe_carry_lookaround import delta, verdict, region_points, LIMITS, YAW_EFFORT

ROLES = {'r1': 'teal', 'r2': 'blue'}


def sample(grip1=(0., 0., 0.), force=(2., 2.), shift=0., pitch=0.):
    row = {'beam_pitch_deg': pitch, 'beam_roll_deg': 0., 'beam_yaw_deg': 10., 'beam_min_z': .02}
    row['r1'] = {'finger_n': list(force), 'grip_in_beam_m': list(grip1), 'base_xy': [0., 0.], 'base_yaw_deg': 0.}
    row['r2'] = {'finger_n': [2., 2.], 'grip_in_beam_m': [0., 0., 0.], 'base_xy': [shift, 0.], 'base_yaw_deg': 0.}
    return row


def test_quiet_hold_passes():
    base = sample()
    s = sample(); s['delta'] = delta(s, base, ROLES)
    worst, reasons = verdict([s], ROLES, 'r1')
    assert reasons == [] and worst['r1']['slip_axis_mm'] == 0.


def test_each_failure_reason_is_reported():
    base = sample()
    rows = []
    for k in range(4):
        s = sample(grip1=(.006, .004, 0.), force=(.3, 2.), shift=.02, pitch=6.); s['t'] = .05*k
        s['delta'] = delta(s, base, ROLES); rows.append(s)
    _, reasons = verdict(rows, ROLES, 'r1')
    assert {'tilt', 'r1:grip_force', 'r1:slip_axis', 'r1:slip_perp', 'r2:partner_dragged'} <= set(reasons)


def test_single_force_dropout_is_not_grip_loss():
    base = sample(); rows = []
    for k, f in enumerate((2., .1, 2., .1, .1, .1, 2.)):
        s = sample(force=(f, 2.)); s['t'] = .05*k; s['delta'] = delta(s, base, ROLES); rows.append(s)
    worst, reasons = verdict(rows[:3], ROLES, 'r1')
    assert reasons == [] and worst['r1']['dropout_samples'] == 1
    worst, reasons = verdict(rows, ROLES, 'r1')
    assert 'r1:grip_force' in reasons and worst['r1']['longest_low_force_s'] >= .15


def test_actor_own_motion_is_not_partner_drag():
    base = sample(); s = sample(); s['r1']['base_xy'] = [.05, 0.]
    s['delta'] = delta(s, base, ROLES)
    assert verdict([s], ROLES, 'r1')[1] == []


def test_region_points_inside_region_and_wheel_band():
    pts = region_points({'center_m': [4.6, .4], 'half_extents_m': [.3, .7]})
    assert len(pts) == 9 and all(4.3 < x < 4.9 and -.3 < y < 1.1 for x, y, _ in pts)
    assert .31 <= YAW_EFFORT + 1/12 <= .40 and LIMITS['finger_min_n'] == .5


def test_workflow_registered():
    rows = json.loads(Path('configs/simulation_workflows.json').read_text())['workflows']
    row = next(r for r in rows if r['id'] == 'grasp-act-lookaround-probe')
    assert row['runner'] == 'scripts.probe_carry_lookaround' and Path(row['entry']).is_file()


def _pulses_ok(duty):
    from sim.grasp_act_release_teacher import check_wheels
    from scripts.probe_carry_lookaround import MIN_PULSE_S
    for d in duty.values():
        check_wheels(d['levels'], d['durations'])
        assert all(x == 0. or x >= MIN_PULSE_S-1e-9 for x in d['durations'])


def test_rotate_center_equal_rates_and_pivot():
    import pytest
    from scripts.probe_carry_lookaround import rotation_plan, GRIP_X_M, BEAM_GRIP_HALF_M
    plan = rotation_plan('rotate_center', 'r1', 'r2')
    d = plan['duty']; _pulses_ok(d)
    assert d['r1']['body_levels'][2] == pytest.approx(d['r2']['body_levels'][2]) and d['r1']['body_levels'][2] > 0
    for rid in d:
        assert d[rid]['realized_pivot_x_m'] == pytest.approx(GRIP_X_M+BEAM_GRIP_HALF_M, abs=.002)
        assert d[rid]['body_levels'][0] == pytest.approx(0.)
    assert 13 < plan['commanded_step_deg'] < 17
    mirrored = rotation_plan('rotate_center', 'r1', 'r2', sign=-1.)['duty']['r1']
    assert mirrored['levels'] == [-x for x in d['r1']['levels']]


def test_pivot_end_zeroes_short_pulses_and_records_shifted_pivot():
    import pytest
    from scripts.probe_carry_lookaround import rotation_plan
    plan = rotation_plan('pivot_end', 'r1', 'r2')
    d = plan['duty']; _pulses_ok(d)
    assert d['r1']['zeroed_wheels'] == [0, 1] and d['r2']['zeroed_wheels'] == []
    assert d['r1']['body_levels'][2] == pytest.approx(d['r2']['body_levels'][2], rel=1e-3)
    assert d['r1']['realized_pivot_x_m'] == pytest.approx(.2286, abs=.002)     # intended 0.203
    assert d['r2']['realized_pivot_x_m'] == pytest.approx(.743, abs=.003)


def test_pair_duty_rejects_zero_motion():
    import pytest
    from scripts.probe_carry_lookaround import pair_duty
    with pytest.raises(ValueError):
        pair_duty({'r1': (0., 0., 0., 0.)})


def test_carry_plan_moves_formation_together():
    import pytest
    from sim.visible_belief import wheel_to_body
    from scripts.probe_carry_lookaround import carry_plan
    ax = carry_plan('axial', .2, 1., 'r1', 'r2'); _pulses_ok(ax['duty'])
    f1, f2 = (wheel_to_body(ax['duty'][r]['levels'])[0] for r in ('r1', 'r2'))
    assert f1 > 0 > f2 and ax['commanded_m'] == pytest.approx(.2, abs=.02)
    lat = carry_plan('lateral', -.15, .5, 'r1', 'r2'); _pulses_ok(lat['duty'])
    l1, l2 = (wheel_to_body(lat['duty'][r]['levels'])[1] for r in ('r1', 'r2'))
    assert l1 < 0 < l2                       # facing each other: actor right = partner left
    with pytest.raises(ValueError):
        carry_plan('axial', .2, .2, 'r1', 'r2')   # 0.03 s pulse below the minimum


def test_swept_space_includes_footprint():
    import pytest
    from scripts.probe_carry_lookaround import swept_space, ROBOT_RADIUS_M
    s = swept_space([{'bases': [[1., 0.], [-1., 0.]], 'ends': [[.3, 0.], [-.3, 0.]]}], [0., 0.])
    assert s['swept_radius_m'] == pytest.approx(1.+ROBOT_RADIUS_M)
    assert s['bbox_size_m'][0] == pytest.approx(2.+2*ROBOT_RADIUS_M)


def test_band_pixels_finds_own_band_colour_only():
    import numpy as np
    from scripts.probe_carry_lookaround import band_pixels
    img = np.zeros((240, 320, 3), np.uint8); img[:] = (170, 100, 50)          # brown floor
    img[:, 140:180] = (160, 230, 40)                                           # lime beam body
    img[200:230, 140:180] = (5, 242, 153)                                      # teal band (0.02, 0.95, 0.60)
    teal = band_pixels(img, 'teal')
    assert teal['area_px'] == 30*40 and teal['centroid'] == [159.5, 214.5] and teal['bottom_v'] == 229
    assert band_pixels(img, 'blue')['area_px'] == 0


def test_carry_probe_plan_seeds_and_clearance():
    import math
    from scripts.make_carry_probe_plan import prepare, CLEAR_RADIUS_M
    from harness.grasp_act_seed_splits import split_of, registry
    plan = prepare(count=3)
    reg = registry()
    for e in plan['episodes']:
        assert split_of(e['seed'], reg) == 'carry_probe'
        assert e['min_wall_distance_m'] >= CLEAR_RADIUS_M
        b = e['beam_pose']; r1 = e['spawns']['r1']
        assert math.dist(b[:2], r1[:2]) == pytest_approx(.473)


def pytest_approx(v):
    import pytest
    return pytest.approx(v, abs=1e-6)


def test_door_points_on_both_faces_beside_jambs():
    import pytest
    from scripts.make_setdown_probe_plan import door_points
    door = {'center_m': [2.2, .05], 'half_extents_m': [.025, .25], 'axis': 'x'}
    pts = door_points(door)
    assert len(pts['west']) == len(pts['east']) == 4
    assert all(x == pytest.approx(2.165) for x, _, _ in pts['west']) and all(x == pytest.approx(2.235) for x, _, _ in pts['east'])
    assert sorted({round(y, 3) for _, y, _ in pts['west']}) == [-.23, .33]       # outside the 0.5 m opening


def test_setdown_plan_door_cases_and_clearance():
    import math
    from scripts.make_setdown_probe_plan import prepare, LATERAL_M, HALF_FORMATION_M
    from harness.grasp_act_seed_splits import split_of, registry
    plan = prepare(count=6); reg = registry()
    assert [e['case'] for e in plan['episodes']] == ['door_before', 'door_after']*3
    for e in plan['episodes']:
        assert split_of(e['seed'], reg) == 'carry_probe'
        (dx, dy), (hx, _) = e['door']['center_m'], e['door']['half_extents_m']
        x, y, yaw = e['beam_pose']
        assert abs(y-dy) <= LATERAL_M+1e-9 and abs(math.degrees(yaw)) <= 3.
        edge = x+HALF_FORMATION_M if e['case'] == 'door_before' else x-HALF_FORMATION_M
        gap = (dx-hx)-edge if e['case'] == 'door_before' else edge-(dx+hx)
        assert gap == __import__('pytest').approx(e['door_gap_m']) and gap >= .25


def test_setdown_mode_in_cli():
    import subprocess, sys
    out = subprocess.run([sys.executable, '-m', 'scripts.probe_carry_lookaround', '--help'], capture_output=True, text=True).stdout
    assert 'setdown_look' in out and 'rotate_center' in out


def test_setdown_backoff_constant_matches_teacher():
    from scripts.make_setdown_probe_plan import BACKOFF_M
    from sim.grasp_act_release_teacher import OBSERVE_BACKOFF_M
    assert BACKOFF_M == OBSERVE_BACKOFF_M


def test_pair_odometry_profile_default_unchanged_and_scales_plans():
    import pytest
    from scripts.probe_carry_lookaround import rotation_plan, carry_plan, GRIP_X_M, BEAM_GRIP_HALF_M
    from sim.visible_belief import rates, odometry, AXIAL_M_PER_S_AT_035, LATERAL_M_PER_S_AT_035, YAW_RAD_PER_S_AT_035
    assert rates() == (AXIAL_M_PER_S_AT_035, LATERAL_M_PER_S_AT_035, YAW_RAD_PER_S_AT_035)
    assert odometry([.35]*4, .1) == odometry([.35]*4, .1, 'off')
    ax0, lat0, yaw0 = rates('off'); ax1, lat1, yaw1 = rates('gcp_probe_v1')
    assert ax1 == ax0 and lat1/lat0 == pytest.approx(1.54, abs=.02) and yaw1/yaw0 == pytest.approx(1.68, abs=.02)
    old = rotation_plan('rotate_center', 'r1', 'r2'); new = rotation_plan('rotate_center', 'r1', 'r2', odometry='gcp_probe_v1')
    assert old['periods'] > new['periods']                   # faster yaw -> fewer periods per 15 deg
    assert new['commanded_step_deg'] == pytest.approx(15, abs=4)
    for p in (old, new):
        assert p['duty']['r1']['realized_pivot_x_m'] == pytest.approx(GRIP_X_M+BEAM_GRIP_HALF_M, abs=.02)
    assert carry_plan('lateral', .15, 1., 'r1', 'r2', 'gcp_probe_v1')['periods'] < carry_plan('lateral', .15, 1., 'r1', 'r2')['periods']
    assert carry_plan('axial', .2, 1., 'r1', 'r2', 'gcp_probe_v1')['periods'] == carry_plan('axial', .2, 1., 'r1', 'r2')['periods']
