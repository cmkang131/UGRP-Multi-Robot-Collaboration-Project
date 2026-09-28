"""Carry height vs the own ultrasonic cone, and the carry-time sonar rule (#221, #246, PR #248).

Pure geometry/IK tests plus one kinematics-only MuJoCo check (no physics step:
``mj_step*`` fail for this module).
"""
from __future__ import annotations

import importlib.util
import math
from dataclasses import replace

import pytest

from harness import ultrasonic_carry as uc
from harness.range_provider import RangeReport
from harness.ultrasonic_model import DEFAULT_SPEC

HAS_MUJOCO = importlib.util.find_spec('mujoco') is not None


@pytest.fixture(scope='module', autouse=True)
def no_physics_step():
    if not HAS_MUJOCO:
        yield
        return
    import mujoco
    saved = {n: getattr(mujoco, n) for n in ('mj_step', 'mj_step1', 'mj_step2')}

    def forbidden(*a, **k):
        raise AssertionError('this suite forbids MuJoCo physics stepping')

    for n in saved:
        setattr(mujoco, n, forbidden)
    try:
        yield
    finally:
        for n, fn in saved.items():
            setattr(mujoco, n, fn)


def test_required_heights_at_the_nominal_mount():
    near = uc.required_heights('near_face')
    assert math.isclose(near['near_face_from_sensor_m'], .047) and math.isclose(near['far_end_from_sensor_m'], .647)
    # 54 mm + 47 mm * tan 15 + 30 mm * sin 2 + 5 mm; + 24 mm grip offset + 10 mm load sag
    assert near['bar_bottom_min_m'] == pytest.approx(.054 + .047 * math.tan(math.radians(15)) + .03 * math.sin(
        math.radians(2)) + .005)
    assert near['tool_z_min_m'] == pytest.approx(.1066, abs=1e-4)
    assert uc.required_heights('whole_beam')['tool_z_min_m'] == pytest.approx(.2873, abs=1e-4)
    assert uc.required_heights('whole_beam', half_angle_deg=7.5)['tool_z_min_m'] == pytest.approx(.1991, abs=1e-4)
    with pytest.raises(ValueError):
        uc.required_heights('below')


def test_requirement_moves_with_the_mount_and_cone():
    base = uc.required_heights('near_face')['tool_z_min_m']
    higher = uc.required_heights('near_face', replace(DEFAULT_SPEC, mount_z_floor_m=.064))['tool_z_min_m']
    further = uc.required_heights('near_face', replace(DEFAULT_SPEC, mount_x_m=.088))['tool_z_min_m']
    tilted = uc.required_heights('near_face', margins=uc.CarryMargins(mount_pitch_up_deg=5.))['tool_z_min_m']
    assert higher == pytest.approx(base + .010) and further < base < tilted


def test_whole_beam_clearance_is_out_of_reach_and_near_face_is_reachable():
    calibrated = uc.max_tool_z()
    assert calibrated == {'tool_z_m': .161, 'pitch_deg': -40}
    anypitch = uc.max_tool_z(pitch_range_deg=(-90, 0))
    assert uc.required_heights('whole_beam')['tool_z_min_m'] > anypitch['tool_z_m']            # 15 deg: never
    assert uc.required_heights('whole_beam', half_angle_deg=7.5)['tool_z_min_m'] > calibrated['tool_z_m']
    assert uc.recommended_carry_tool_z() == .110
    high = replace(DEFAULT_SPEC, mount_z_floor_m=.064, mount_x_m=.068)
    assert uc.recommended_carry_tool_z(high) == .120
    with pytest.raises(ValueError):
        uc.recommended_carry_tool_z(replace(DEFAULT_SPEC, mount_z_floor_m=.12))


def test_lift_ik_matches_m2_and_the_recommended_pose():
    m2 = uc.lift_ik(uc.M2_LIFT_TOOL_Z_M)
    assert m2['pitch_deg'] == pytest.approx(-64.08, abs=.01) and m2['tool_z_m'] == pytest.approx(.095, abs=.001)
    rec = uc.lift_ik(.110)
    assert rec['tool_z_m'] == pytest.approx(.110, abs=.001)
    assert m2['pitch_change_from_grasp_deg'] == pytest.approx(8.01, abs=.01)     # bar turns in the jaws at M2 too
    assert 11 < rec['pitch_change_from_grasp_deg'] < 13
    assert uc.expected_bar_bottom(.095) == pytest.approx(.061)       # recorded M2 bar underside 0.0602-0.061


def _report(t, r):
    return RangeReport(t_meas=t, age_s=0., valid=r is not None, range_m=float('nan') if r is None else r,
                       sigma_m=DEFAULT_SPEC.sigma_m(r or 0.))


def _feed(mon, values, t0=0.):
    state = None
    for i, v in enumerate(values):
        state = mon.update(_report(t0 + .06 * i, v))
    return state


def test_above_cone_monitor_states():
    mon = uc.CarrySonarMonitor('above_cone')
    assert _feed(mon, [.694, .690, .70, .695, .693]) == uc.CALIBRATING or mon.baseline_m == pytest.approx(.694)
    assert mon.baseline_m == pytest.approx(.694)
    assert _feed(mon, [.69, .70, .695], 1.) == uc.FORMATION_OK
    assert _feed(mon, [.05, .05], 2.) == uc.UNKNOWN                  # debounce: 2 < k
    assert _feed(mon, [.05], 2.12) == uc.LOAD_IN_CONE
    assert _feed(mon, [.40, .40, .41], 3.) == uc.INTRUSION
    assert _feed(mon, [None, 1.3, None], 4.) == uc.BEYOND_BASELINE
    assert mon.update(_report(4.12, .69)) == uc.BEYOND_BASELINE        # stale/duplicate time ignored


def test_load_in_cone_monitor_detects_a_jump_longer():
    mon = uc.CarrySonarMonitor('load_in_cone')
    _feed(mon, [.048, .047, .049, .048, .047])
    assert mon.baseline_m == pytest.approx(.048)
    assert _feed(mon, [.048, .047, .048], 1.) == uc.LOAD_PRESENT
    assert _feed(mon, [.69, .70, .69], 2.) == uc.LOAD_LOST
    with pytest.raises(ValueError):
        uc.CarrySonarMonitor('sideways')


def test_kinematic_scene_confirms_load_seen_at_m2_height_and_partner_seen_at_recommended():
    if not HAS_MUJOCO:
        pytest.skip('mujoco is not installed')
    from scripts import analyze_ultrasonic_carry_height as an
    model, data, beam, _ = an.build_scene()
    grasp_mask, _ = an.camera_bar_mask(uc.grasp_pose(), 0.)
    m2 = an.evaluate_height(model, data, beam, uc.M2_LIFT_TOOL_Z_M, grasp_mask=grasp_mask)
    rec = an.evaluate_height(model, data, beam, uc.recommended_carry_tool_z(), grasp_mask=grasp_mask)
    assert m2['sonar']['sees_own_load'] and m2['sonar']['first_echo_m'] == pytest.approx(.047, abs=.002)
    assert not rec['sonar']['sees_own_load'] and rec['sonar']['echo_geom'].startswith('r2__')
    assert rec['sonar']['with_own_arm_echo_geom'].startswith('r2__')        # own arm/jaws also outside the cone
    for row in (m2, rec):
        assert row['sim_joint_ranges_ok']
        assert row['sim_grip_site_m']['z'] == pytest.approx(row['fk_tool_z_m'], abs=.002)
        assert min(c['min_distance_m'] for c in row['bar_clearance'].values()) > .02
        assert row['tip_over_r1']['tip_accel_forward_mps2'] > 2. and row['tip_over_r1']['static_forward_restoring_ratio'] > 2.
        assert row['wrist_camera_proxy']['iou_vs_grasp_view'] > .7
    infeasible = an.evaluate_height(model, data, beam, .199, grasp_mask=grasp_mask)
    assert infeasible['ik_feasible'] is False
