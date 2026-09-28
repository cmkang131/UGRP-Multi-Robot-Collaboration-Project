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
    # distances from the transducer FACE (84 mm): near end face 41 mm, far end 641 mm
    assert math.isclose(near['near_face_from_sensor_m'], .041) and math.isclose(near['far_end_from_sensor_m'], .641)
    # 54 mm + 41 mm * tan 15 + 30 mm * sin 2 + 5 mm; + 24 mm grip offset + 10 mm load sag
    assert near['bar_bottom_min_m'] == pytest.approx(.054 + .041 * math.tan(math.radians(15)) + .03 * math.sin(
        math.radians(2)) + .005)
    assert near['tool_z_min_m'] == pytest.approx(.1050, abs=1e-4)
    assert uc.required_heights('whole_beam')['tool_z_min_m'] == pytest.approx(.2857, abs=1e-4)
    assert uc.required_heights('whole_beam', half_angle_deg=7.5)['tool_z_min_m'] == pytest.approx(.1983, abs=1e-4)
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


def _report(t, r, status=None):
    return RangeReport(t_meas=t, age_s=0., valid=r is not None, range_m=float('nan') if r is None else r,
                       sigma_m=DEFAULT_SPEC.sigma_m(r or 0.), status=status or ('ok' if r is not None else 'no_echo'))


def _feed(mon, values, t0=0.):
    state = None
    for i, v in enumerate(values):
        state = mon.update(_report(t0 + .06 * i, v))
    return state


def test_above_cone_monitor_states():
    mon = uc.CarrySonarMonitor('above_cone', expected_baseline_m=.69)
    _feed(mon, [.694, .690, .70, .695, .693])
    assert mon.baseline_m == pytest.approx(.694)
    assert _feed(mon, [.69, .70, .695], 1.) == uc.FORMATION_OK
    assert _feed(mon, [.05, .05], 2.) == uc.FORMATION_OK              # 2 of 5 stop verdicts: not yet
    assert _feed(mon, [.05], 2.12) == uc.LOAD_IN_CONE                 # 3 of the last 5
    assert _feed(mon, [.40, .40, .41], 3.) == uc.INTRUSION
    assert _feed(mon, [None, 1.3, None], 4.) == uc.BEYOND_BASELINE
    assert mon.update(_report(4.12, .69)) == uc.BEYOND_BASELINE        # duplicate time ignored
    assert mon.state(now=4.5) == uc.STALE                             # no fresh reading -> stop, not the old verdict


def test_monitor_mixed_verdicts_stop_or_relook_and_bad_baselines_fail():
    mon = uc.CarrySonarMonitor('above_cone', expected_baseline_m=.69)
    _feed(mon, [.69] * 5)
    # a swinging load alternates stop verdicts: 3 of 5 stops -> stop (most frequent)
    assert _feed(mon, [.05, .40, .69, .05, .40], 1.) in uc.STOP_STATES
    mon2 = uc.CarrySonarMonitor('load_in_cone')
    _feed(mon2, [.048] * 5)
    assert _feed(mon2, [.020, .048, .020, .048, .020], 1.) == uc.RELOOK       # neither 3 stops nor 3 OKs
    # baseline at the own load's end face in above_cone mode: rejected (would hide a slip forever)
    bad = uc.CarrySonarMonitor('above_cone', expected_baseline_m=.69)
    assert _feed(bad, [.048] * 5) == uc.CALIBRATION_FAILED and uc.CALIBRATION_FAILED in uc.STOP_STATES
    far = uc.CarrySonarMonitor('above_cone', expected_baseline_m=.69)
    assert _feed(far, [1.2] * 5) == uc.CALIBRATION_FAILED                      # outside the formation window
    spread = uc.CarrySonarMonitor('above_cone')
    assert _feed(spread, [.60, .69, .80, .65, .75]) == uc.CALIBRATION_FAILED   # readings disagree
    silent = uc.CarrySonarMonitor('above_cone', calib_timeout_s=.3)
    assert _feed(silent, [None] * 8) == uc.CALIBRATION_FAILED                  # never calibrates -> stop
    blind = uc.CarrySonarMonitor('above_cone')
    _feed(blind, [.69] * 5)
    for i in range(3):
        state = blind.update(_report(1. + .06 * i, None, 'blind'))
    assert state == uc.BLIND_ZONE


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
    assert m2['sonar']['sees_own_load'] and m2['sonar']['first_echo_m'] == pytest.approx(.041, abs=.002)
    assert not rec['sonar']['sees_own_load'] and rec['sonar']['echo_geom'].startswith('r2__')
    assert not rec['sonar']['echo_is_own_arm']                  # own arm/jaws also outside the cone (included in rays)
    for row in (m2, rec):
        assert row['sim_joint_ranges_ok']
        assert row['sim_grip_site_m']['z'] == pytest.approx(row['fk_tool_z_m'], abs=.002)
        assert min(c['min_distance_m'] for c in row['bar_clearance'].values()) > .02
        assert row['tip_over_r1']['tip_accel_forward_mps2'] > 2. and row['tip_over_r1']['static_forward_restoring_ratio'] > 2.
        assert row['wrist_camera_proxy']['iou_vs_grasp_view'] > .7
    infeasible = an.evaluate_height(model, data, beam, .199, grasp_mask=grasp_mask)
    assert infeasible['ik_feasible'] is False


# --- solo carry --------------------------------------------------------------------------------

def test_solo_straight_lift_minimums_and_carry_p30_clear_every_kind():
    expect = {'box': (.120, .110), 'can': (.120, .110), 'tile': (.110, .095)}
    for kind, (z15, z75) in expect.items():
        assert uc.recommended_solo_tool_z(kind) == pytest.approx(z15)
        assert uc.recommended_solo_tool_z(kind, half_angle_deg=7.5) == pytest.approx(z75)
        item = uc.SOLO_ITEMS[kind]
        grasp = uc.solo_lift(item, .095)['grasp_pitch_deg']
        hover = uc.solo_posture_margins(item, uc.solo_lift(item, .095)['pulses'], grasp)
        assert not hover['clear']                                   # existing 0.095 hover: item in the cone
        p30 = uc.solo_posture_margins(item, uc.CARRY_P30, grasp, extra_tilts_deg=(uc.CARRY_P30_RECORDED_TILT_DEG,))
        assert p30['clear'] and min(c['margin_m'] for c in p30['cases'].values()) > .05


def test_solo_forward_rule_states():
    from harness import ultrasonic_map as um
    from harness.ultrasonic_map import ExpectedRange
    stop = uc.solo_stop_distance(.092)
    assert stop == pytest.approx(.092 + .19 * .30 + .02)
    exp = ExpectedRange(.50, .008)
    kw = dict(front_extent_from_sensor_m=.092, stop_m=stop, slow_m=uc.solo_stop_distance(.092, reaction_s=1.))
    state = lambda r, t=1.: uc.solo_forward_state(_report(t, r), 1., exp, **kw)
    assert state(.50) == {'state': uc.CLEAR, 'consistency': um.CONSISTENT}
    assert state(.25)['state'] == uc.SLOW and state(.25)['consistency'] == um.SHORTER
    assert state(.15)['state'] == uc.STOP
    assert state(.10)['state'] == uc.STOP_NEAR_FIELD
    assert state(.50, t=.5)['state'] == uc.NO_READING
    inv = lambda status, **extra: uc.solo_forward_state(
        RangeReport(1., 0., False, status=status, **extra), 1., exp, **kw)
    # never 'clear' without a valid echo
    assert inv('no_echo')['state'] == uc.NO_ECHO_AHEAD and inv('no_echo')['consistency'] == um.MISSING_ECHO
    assert inv('no_echo', last_valid_t=.8, last_valid_range_m=.17)['state'] == uc.HOLD      # was stopped at a wall
    assert inv('blind')['state'] == uc.STOP_NEAR_FIELD
    assert inv('sensor_absent')['state'] == uc.NO_READING
    assert {uc.HOLD, uc.STOP_NEAR_FIELD, uc.NO_READING} <= set(uc.SOLO_STOP_STATES)


def test_kinematic_solo_carry_p30_sees_the_wall_not_its_arm_or_item():
    if not HAS_MUJOCO:
        pytest.skip('mujoco is not installed')
    from scripts import analyze_ultrasonic_carry_height as an
    scene, model, data, _ = an.build_solo_scene()
    for kind in ('box', 'tile'):
        item = uc.SOLO_ITEMS[kind]
        g = uc.solo_lift(item, .095)['grasp_pitch_deg']
        p30 = an.evaluate_solo(scene, model, data, kind, 'carry_p30', dict(uc.CARRY_P30), g)
        hover = an.evaluate_solo(scene, model, data, kind, 'hover', uc.solo_lift(item, .095)['pulses'], g)
        for case in p30['cases'].values():
            assert case['matches_map'] and not case['own_arm_geoms_in_cone'] and not case['item_in_cone']
        assert all(c['item_in_cone'] for c in hover['cases'].values())
        assert p30['put_down']['descent_ik_feasible'] and p30['put_down']['transition_to_hover_lowest_item_point_m'] > .05
    assert hover['cases']['level']['matches_map']                  # the 12 mm tile's echo stays under threshold


def test_kinematic_side_grasp_pair_sees_ahead_and_door_posts():
    if not HAS_MUJOCO:
        pytest.skip('mujoco is not installed')
    from scripts import analyze_ultrasonic_carry_height as an
    d = an.analyse_side()
    side, straight = d['modes']['side'], d['modes']['straight']
    assert side['sim_joint_ranges_ok'] and max(side['grip_site_error_m'].values()) < .002
    for v in side['sonar_open_floor'].values():
        assert v['matches_map'] and not (v['own_geoms_in_cone'] or v['load_in_cone'] or v['partner_in_cone'])
    for v in straight['sonar_open_floor'].values():
        assert v['echo_geom'].endswith('ultrasonic_bracket') and v['first_echo_m'] == pytest.approx(.688, abs=.003)
    door = side['door_crossing_axial']
    assert door['sonar']['r2_in_door']['r2']['first_echo_m'] == pytest.approx(.166, abs=.003)
    assert door['sonar']['r2_in_door']['r2']['matches_map']
    assert .15 < door['clearance_per_side_0.5m'] < straight['door_crossing_axial']['clearance_per_side_0.5m']
    assert side['wrist_camera_iou_vs_straight'] == pytest.approx(1.)
    assert side['tip_over']['r1']['tip_accel_lateral_mps2'] > straight['tip_over']['r1']['tip_accel_forward_mps2']
    assert d['axial_leg_leader_facing']['best_heading_off_travel_deg'] > 60
    assert d['arm_yaw_axis']['yaw_axis_offset_from_chassis_origin_m'] == [0., 0.]


# --- v2 vs v3 (PR #249 drawing layout) -----------------------------------------------------------

def test_v3_drawing_geometry_raises_the_lifts_and_keeps_carry_p30_clear():
    v3 = uc.GEOMETRY_V3
    spec = v3.spec()
    assert (spec.mount_x_m, spec.mount_z_floor_m) == (.088, .0617)
    assert uc.required_heights('near_face', spec, arm_axis_x_m=v3.arm_axis_x_m)['near_face_from_sensor_m'] == pytest.approx(.0792)
    assert uc.recommended_carry_tool_z(spec, arm_axis_x_m=v3.arm_axis_x_m) == pytest.approx(.125)
    assert uc.required_heights('whole_beam', spec, arm_axis_x_m=v3.arm_axis_x_m)['tool_z_min_m'] > uc.max_tool_z()['tool_z_m']
    for kind, z in (('box', .140), ('can', .140), ('tile', .125)):
        assert uc.recommended_solo_tool_z(kind, spec, arm_axis_x_m=v3.arm_axis_x_m) == pytest.approx(z)
        item = uc.SOLO_ITEMS[kind]
        g = uc.solo_lift(item, .095)['grasp_pitch_deg']
        p30 = uc.solo_posture_margins(item, uc.CARRY_P30, g, spec, arm_axis_x_m=v3.arm_axis_x_m)
        assert p30['clear'] and p30['item_front_beyond_sensor_m'] == pytest.approx(.124, abs=.002)
    assert uc.turn_in_place_grip_shift_m(90., uc.GEOMETRY_V2) == 0.
    assert uc.turn_in_place_grip_shift_m(90., v3) == pytest.approx(.0682, abs=1e-4)


def test_link_length_sensitivity_is_scoped_and_restored():
    from harness import visual_arm as va
    from scripts.analyze_ultrasonic_carry_height import arm_links
    assert not hasattr(uc, 'arm_links')                         # runtime module never mutates the IK
    before = (va.LINK_2_CM, va.GRIPPER_LINK_CM, dict(va.tool_pose.__kwdefaults__), uc.max_tool_z())
    with arm_links(uc.DRAWING_LINK2_CM, None):
        assert uc.max_tool_z()['tool_z_m'] == pytest.approx(.151)
    with arm_links(None, uc.DRAWING_GRIPPER_CM):
        with pytest.raises(ValueError):
            uc.solo_lift(uc.SOLO_ITEMS['tile'], .095)           # 7 mm tile grip below the reachable minimum
    assert (va.LINK_2_CM, va.GRIPPER_LINK_CM, dict(va.tool_pose.__kwdefaults__), uc.max_tool_z()) == before
