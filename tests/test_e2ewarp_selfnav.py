import ast
import json
import pathlib
import types

import pytest

from harness import e2ewarp_selfnav as sn
from harness.grasp_act_contract import SERVOS, command as issued_command

ROOT = pathlib.Path(__file__).resolve().parents[1]


def frame(sim_s=0.0, jpeg=b'jpg', robot_id='r1'):
    return types.SimpleNamespace(robot_id=robot_id, world_id=0, tick=int(sim_s * 10), sim_s=sim_s, jpeg=jpeg, issued=())


def odometry(forward_m_per_pct_s=0.01, yaw_deg_per_pct_s=0.5):
    return sn.OwnCommandOdometry(forward_m_per_pct_s=forward_m_per_pct_s,
                                 yaw_deg_per_pct_s=yaw_deg_per_pct_s)


def constant_detector(detections):
    return lambda fr: detections


def zone_detection(range_m=2.0, bearing_deg=0.0, bottom_norm=0.3, **patch):
    """Detection with measured range plus plausible-patch geometry."""
    det = {'kind': 'zone_B', 'range_m': range_m, 'bearing_deg': bearing_deg, 'bottom_norm': bottom_norm}
    det.update(patch_geometry(**patch))
    return [det]


def patch_geometry(**overrides):
    """Largest-component geometry of a plausible zone patch (frame fractions)."""
    value = dict(width_norm=0.60, height_norm=0.20, area_norm=0.10, solidity=0.85,
                 spans_center_x=True, touches_top=False)
    value.update(overrides)
    return value


def appearance_detection(bottom_norm=0.3, bearing_deg=0.0, **patch):
    """Appearance-only detection: no range_m, so only the bottom band can arrive."""
    det = {'kind': 'zone_B', 'bearing_deg': bearing_deg, 'bottom_norm': bottom_norm}
    det.update(patch_geometry(**patch))
    return [det]


def test_default_off_fails_closed():
    nav = sn.navigation_factory('r1', {'orders': [{'id': 'o'}]})
    rep = nav.observe(frame(1.0))
    assert rep['map_correction_active'] is False
    assert rep['destination_arrived'] is False
    assert rep['ready'] is False and rep['drive_reason'] == 'option_off'
    assert nav.accept_release_fix({'relocalized': True, 'memory_registered': True}) is False
    cmd = nav.command(1.0)
    assert cmd['wheels'] == [0.0, 0.0, 0.0, 0.0] and cmd['duration_s'] == [0.0, 0.0, 0.0, 0.0]
    assert set(cmd) == {'t', 'wheels', 'duration_s', 'pwm'} and set(cmd['pwm']) == {str(i) for i in SERVOS}
    assert all(isinstance(v, int) and 500 <= v <= 2500 for v in cmd['pwm'].values())


def test_default_off_holds_wheels_even_with_controller_inputs():
    nav = sn.navigation_factory('r1', {}, detector=constant_detector(zone_detection()),
                                odometry=odometry())
    rep = nav.observe(frame(0.0))
    assert rep['ready'] is False and rep['destination_arrived'] is False
    assert rep['drive_reason'] == 'option_off'
    cmd = nav.command(0.0)
    assert cmd['wheels'] == [0.0] * 4 and cmd['duration_s'] == [0.0] * 4


def test_ready_requires_active_option_detector_and_odometry():
    det, od = constant_detector(zone_detection()), odometry()
    assert sn.navigation_factory('r1', {}, detector=det, odometry=od).ready is False
    assert sn.navigation_factory('r1', {}, option=sn.OPTION, detector=det).ready is False
    assert sn.navigation_factory('r1', {}, option=sn.OPTION, odometry=od).ready is False
    nav = sn.navigation_factory('r1', {}, option=sn.OPTION, detector=det, odometry=od)
    assert nav.ready is True and nav.observe(frame(0.0))['ready'] is True


def test_no_static_map_geometry_allowed():
    with pytest.raises(ValueError, match='static map input is forbidden'):
        sn.navigation_factory('r1', {'orders': [], 'walls': [], 'zones': {}})
    assert sn.order_sheet({'orders': [], 'mission': {'destination_zone': 'B'}})['mission']['destination_zone'] == 'B'


def test_memory_updates_and_decays():
    dets = [{'kind': 'zone_B', 'range_m': 1.2, 'bearing_deg': 5.0}]
    nav = sn.navigation_factory('r1', {}, option=sn.OPTION, detector=lambda fr: dets)
    rep = nav.observe(frame(0.0))
    assert rep['evidence_revision'] == 1 and rep['self_centric_memory'][0]['kind'] == 'zone_B'
    rep = nav.observe(frame(2.0))
    assert rep['self_centric_memory'][0]['uncertainty_m'] > 0.5  # decayed before re-observation


def test_arrival_and_handoff_are_own_memory_evidence():
    dets = [{'kind': 'zone_B', 'range_m': 0.2, 'bearing_deg': 0.0}]
    nav = sn.navigation_factory('r2', {}, option=sn.OPTION, detector=lambda fr: dets)
    rep = nav.observe(frame(3.0, robot_id='r2'))
    assert rep['destination_arrived'] is True and rep['robot_id'] == 'r2'


def test_abi_and_channel_isolation():
    nav = sn.navigation_factory('r1', {'orders': [{'id': 'o1'}, {'id': 'o2'}]}, option=sn.OPTION)
    assert {c['id'] for c in nav.task_candidates(['o1'])} == {'o2'}
    nav.start({'skill': 'carry_page'}, phase='carry')
    assert nav.phase == 'carry'
    nav.on_messages([{'from': 'r2', 'text': 'ready'}])
    assert nav._messages[-1]['from'] == 'r2'
    assert nav.confirm_act(frame(), 'grasp') is False
    assert nav.accept_release_fix({'relocalized': True, 'memory_registered': True, 'truth_inputs': 0, 'held_world_reads': 0}) is True


def test_two_robot_only():
    with pytest.raises(ValueError):
        sn.navigation_factory('r3', {})


def test_no_simulator_or_gt_imports_or_access():
    src = (ROOT / 'harness/e2ewarp_selfnav.py').read_text()
    tree = ast.parse(src)
    imports = set()
    names = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            imports.update(a.name.split('.')[0] for a in node.names)
        elif isinstance(node, ast.ImportFrom) and node.module:
            imports.add(node.module.split('.')[0])
        elif isinstance(node, ast.Name):
            names.add(node.id)
        elif isinstance(node, ast.Attribute):
            names.add(node.attr)
    forbidden = {'mujoco', 'mujoco_warp', 'warp', 'sim', 'torch'}
    assert not (imports & forbidden)
    # No ground-truth/evaluator/top-camera accessors in executable code.
    for token in ('ground_truth', 'gt_pose', 'evaluator', 'top_camera', 'truth'):
        assert token not in names


def test_contract_scenario_is_two_robot_without_static_map():
    scenario = json.loads((ROOT / 'configs/e2ewarp/contract_v1_two_robot_scenario.json').read_text())
    assert scenario['robots'] == ['r1', 'r2']
    assert scenario['static_map_input'] is False
    assert scenario['mission']['robots_required'] == 2
    assert scenario['physics']['backend'] == 'mjwarp_batch_v1' and scenario['physics']['noslip_iterations'] == 0
    assert scenario['language_conditions'] == ['no_comm', 'peer_en', 'leader_en', 'structured']


def test_gpu_calib_zone_detector_accepts_zone_and_rejects_bright_floor():
    import numpy as np
    det = sn.GpuCalibZoneDetector()
    assert sn.GPU_CALIB_V1['hue_cv'] == (110.0, 114.0)
    assert 'opencv' in sn.GPU_CALIB_V1['units']
    img = np.zeros((48, 64, 3), dtype=np.uint8)  # black
    # Measured zone-B median in OpenCV units: H 112, S ~202, V ~85.
    # RGB (18, 36, 85) -> OpenCV H 112, S 201, V 85 (degrees 224, NOT 112).
    img[20:, 20:44] = (18, 36, 85)
    out = det(img)
    assert len(out) == 1 and out[0]['kind'] == 'zone_B'
    assert out[0]['bottom_norm'] >= 0.98 and out[0]['pixels'] >= 600
    assert out[0]['hue_units'] == 'opencv_h_0_180_sv_0_255'
    assert out[0]['solidity'] == 1.0 and out[0]['spans_center_x'] is True
    # Bright pickup-room floor (OpenCV H 120, V~135) must be rejected by the
    # V ceiling, and a bright green block (degrees 112, OpenCV 56) by hue.
    bright_floor = np.zeros((48, 64, 3), dtype=np.uint8)
    bright_floor[:, :] = (0, 0, 135)
    assert det(bright_floor) == []
    green_degrees112 = np.zeros((48, 64, 3), dtype=np.uint8)
    green_degrees112[10:, 10:40] = (8, 60, 0)  # RGB hue 112 DEGREES = OpenCV 56
    assert det(green_degrees112) == []


def test_gpu_calib_zone_detector_classifies_by_largest_component():
    import numpy as np
    det = sn.GpuCalibZoneDetector()
    img = np.zeros((80, 80, 3), dtype=np.uint8)
    img[5:25, 5:25] = (18, 36, 85)     # 400 px
    img[50:70, 50:70] = (18, 36, 85)   # 400 px, disconnected
    mask = np.zeros((80, 80), dtype=bool)
    mask[5:25, 5:25] = True
    mask[50:70, 50:70] = True
    comp = sn.largest_component(mask)
    assert int(mask.sum()) == 800 and comp['area'] == 400  # total >= 600, largest < 600
    assert det(img) == []  # the old mask.sum() classification would have fired


def test_gpu_calib_detector_floor_only_frame_produces_zero_detections():
    import numpy as np
    from PIL import Image
    path = ROOT / 'experiments/2026-10-18-nav-gate-1/raw/r1-tick5.jpg'
    assert path.is_file()
    det = sn.GpuCalibZoneDetector()
    assert det(path.read_bytes()) == []
    # Regression evidence: the total mask alone is >= min_pixels on this real
    # floor frame, but the largest component is far below it.  This is exactly
    # the fail-open path the component rule replaces (measured 1583 vs 381 px).
    rgb = np.asarray(Image.open(path).convert('RGB'))
    h_deg, s, v = sn.rgb_to_hsv(rgb)
    h_cv = sn.hue_degrees_to_opencv(h_deg)
    mask = ((h_cv >= 110) & (h_cv <= 114) & (s >= 100) & (v >= 30) & (v <= 110))
    assert int(mask.sum()) >= sn.GPU_CALIB_V1['min_pixels']
    assert sn.largest_component(mask)['area'] < sn.GPU_CALIB_V1['min_pixels']


def test_gpu_calib_detector_rejects_measured_floor_colour_fill():
    import numpy as np
    # Measured pickup-overlay floor median: OpenCV H 108, S 212, V 90.
    # RGB (15, 45, 90) -> OpenCV H 108, S 212, V 90.
    img = np.zeros((48, 64, 3), dtype=np.uint8)
    img[:, :] = (15, 45, 90)
    assert sn.GpuCalibZoneDetector()(img) == []


def test_arrival_guard_rejects_bottom_fill_floor_detection():
    # Largest connected component of the real floor frame when the band is
    # widened to 108-116 (the only way the pickup floor becomes one blob):
    # width .848, height .677, area .341, solidity .594, bottom .846.  Force the
    # bottom to the frame edge and it must still not arrive.
    floor_fill = [dict(kind='zone_B', bearing_deg=0.0, bottom_norm=1.0,
                       width_norm=0.8484, height_norm=0.6771, area_norm=0.3415,
                       solidity=0.5945, spans_center_x=True, touches_top=False)]
    nav = sn.navigation_factory('r1', {}, option=sn.OPTION,
                                detector=constant_detector(floor_fill), odometry=odometry())
    rep = nav.observe(frame(0.0))
    assert rep['destination_arrived'] is False
    assert rep['drive_reason'] != 'arrived'
    # A floor fill that also reaches the top of the frame is rejected harder.
    full_fill = [dict(kind='zone_B', bearing_deg=0.0, bottom_norm=1.0,
                      width_norm=0.95, height_norm=0.83, area_norm=0.42,
                      solidity=0.59, spans_center_x=True, touches_top=False)]
    nav = sn.navigation_factory('r1', {}, option=sn.OPTION,
                                detector=constant_detector(full_fill), odometry=odometry())
    assert nav.observe(frame(0.0))['destination_arrived'] is False
    # A 3-px JPEG edge strip (the real floor frame's largest component) is not
    # a patch either, even with a high bottom band.
    strip = [dict(kind='zone_B', bearing_deg=0.0, bottom_norm=0.999,
                  width_norm=0.20, height_norm=0.006, area_norm=0.001,
                  solidity=0.99, spans_center_x=True, touches_top=False)]
    nav = sn.navigation_factory('r1', {}, option=sn.OPTION,
                                detector=constant_detector(strip), odometry=odometry())
    assert nav.observe(frame(0.0))['destination_arrived'] is False


def test_arrival_guard_accepts_a_plausible_zone_patch():
    nav = sn.navigation_factory('r1', {}, option=sn.OPTION,
                                detector=constant_detector(appearance_detection(bottom_norm=0.99)),
                                odometry=odometry())
    rep = nav.observe(frame(0.0))
    assert rep['destination_arrived'] is True and rep['drive_reason'] == 'arrived'


def test_stale_bottom_band_detection_cannot_claim_arrival():
    near = appearance_detection(bottom_norm=0.99)
    calls = {'n': 0}

    def once(frame_or_rgb):
        calls['n'] += 1
        return near if calls['n'] == 1 else []

    nav = sn.navigation_factory('r1', {}, option=sn.OPTION, detector=once, odometry=odometry())
    assert nav.observe(frame(0.0))['destination_arrived'] is True
    rep = nav.observe(frame(10.0))  # no fresh detection; memory retains the old one
    assert rep['destination_arrived'] is False
    assert rep['drive_reason'] != 'arrived'


def test_own_command_odometry_requires_injected_calibration():
    with pytest.raises(TypeError):
        sn.OwnCommandOdometry()  # calibration must be injected; no invented defaults
    od = sn.OwnCommandOdometry(forward_m_per_pct_s=0.001, yaw_deg_per_pct_s=0.01)
    row = dict(t=0.0, wheels=[.4, .4, .4, .4], duration_s=[.15] * 4, pwm={})
    f, y = od.step(row)
    assert f > 0 and abs(y) < 1e-9


def test_own_command_odometry_converts_normalized_duty_to_percent():
    """0.35 (35 %) for 0.1 s integrates as 3.5 pct-s, not as 0.035 pct-s.

    Gate calibration: 0.0040237052 m/pct-s and 1.7277518948 deg/pct-s, measured
    with a 35 % x 0.1 s pulse (experiments/2026-10-18-nav-gate-1/raw/calibration.json).
    One such pulse moved 0.5633 m / 40 = 0.01408 m, so that is the expected step.
    Before the fix the same row returned 0.35 x 0.1 x calibration = 1.41e-4 m
    (100x too small); the yaw step was 100x too small for the same reason.
    """
    forward_m_per_pct_s = 0.0040237052109054995
    yaw_deg_per_pct_s = 1.7277518947686832
    od = sn.OwnCommandOdometry(forward_m_per_pct_s=forward_m_per_pct_s,
                               yaw_deg_per_pct_s=yaw_deg_per_pct_s)
    row = dict(t=0.0, wheels=[.35] * 4, duration_s=[.1] * 4, pwm={})
    forward_m, yaw_deg = od.step(row)
    assert forward_m == pytest.approx(.1 * 35.0 * forward_m_per_pct_s, rel=1e-12)
    assert forward_m == pytest.approx(0.014083, rel=1e-4)  # one calibration pulse
    assert abs(yaw_deg) < 1e-12

    # +turn pattern from the calibration run: [-PCT, PCT, -PCT, PCT].
    row = dict(t=0.0, wheels=[-.35, .35, -.35, .35], duration_s=[.1] * 4, pwm={})
    forward_m, yaw_deg = od.step(row)
    assert forward_m == pytest.approx(0.0, abs=1e-12)
    assert yaw_deg == pytest.approx(.1 * 35.0 * yaw_deg_per_pct_s, rel=1e-12)
    assert yaw_deg == pytest.approx(6.04713, rel=1e-4)  # 20 pulses measured 120.94 deg


def test_odometry_shifts_self_centric_memory_opposite_to_motion():
    od = sn.OwnCommandOdometry(forward_m_per_pct_s=0.001, yaw_deg_per_pct_s=0.01)
    nav = sn.navigation_factory('r1', {}, option=sn.OPTION, odometry=od,
                                detector=lambda fr: [{'kind': 'zone_B', 'bearing_deg': 0.0,
                                                      'range_m': 2.0, 'bottom_norm': 0.3}])
    nav.observe(frame(0.0))
    row = dict(t=0.0, wheels=[.4, .4, .4, .4], duration_s=[.15] * 4, pwm={})
    out = nav.step_odometry(row)
    assert out[0] > 0
    # memory range decreases as the robot moves toward the landmark
    assert nav.memory.items[0].range_m < 2.0


def test_arrival_uses_recorded_bottom_band_evidence():
    det = zone_detection(range_m=1.0, bottom_norm=0.985)
    nav = sn.navigation_factory('r2', {}, option=sn.OPTION, detector=lambda fr: det)
    assert nav.observe(frame(1.0, robot_id='r2'))['destination_arrived'] is True


def test_active_drive_emits_pulses_and_reduces_destination_range_and_bearing():
    nav = sn.navigation_factory('r1', {}, option=sn.OPTION, odometry=odometry(),
                                detector=constant_detector(zone_detection(range_m=2.0, bearing_deg=10.0)))
    rep = nav.observe(frame(0.0))
    assert rep['ready'] is True and rep['destination_arrived'] is False
    assert rep['drive_reason'] == 'driving'
    range0, bearing0 = nav.memory.items[0].range_m, nav.memory.items[0].bearing_deg
    for step in range(6):
        cmd = nav.command(0.1 + 0.1 * step)
        issued_command(cmd)  # own issued-command whitelist (percent x pulse width)
        assert any(w != 0.0 for w in cmd['wheels'])
        assert all(abs(w) <= sn.WHEEL_PCT + 1e-9 for w in cmd['wheels'])
        assert all(0.0 <= dt <= 0.15 for dt in cmd['duration_s'])
        # proportional differential: left and right pulse widths differ
        assert cmd['duration_s'][0] != cmd['duration_s'][1]
        delta = nav.step_odometry(cmd)
        assert delta is not None and delta[0] > 0.0 and delta[1] > 0.0
    assert nav.memory.items[0].range_m < range0
    assert abs(nav.memory.items[0].bearing_deg) < abs(bearing0)


def test_off_axis_destination_rotates_in_place_before_translating():
    nav = sn.navigation_factory('r1', {}, option=sn.OPTION, odometry=odometry(),
                                detector=constant_detector(zone_detection(range_m=2.0, bearing_deg=90.0)))
    nav.observe(frame(0.0))
    cmd = nav.command(0.0)
    assert cmd['wheels'][0] < 0.0 < cmd['wheels'][1]
    assert cmd['wheels'][2] < 0.0 < cmd['wheels'][3]
    assert all(dt > 0.0 for dt in cmd['duration_s'])


def test_arrival_evidence_stops_wheels():
    cases = [
        (zone_detection(range_m=0.2, bearing_deg=0.0, bottom_norm=0.3), sn.ARRIVAL_RANGE_M),
        (zone_detection(range_m=1.0, bearing_deg=0.0, bottom_norm=0.99), sn.ARRIVAL_RANGE_M),
        (zone_detection(range_m=0.4, bearing_deg=0.0, bottom_norm=0.3), 0.5),
    ]
    for dets, threshold in cases:
        nav = sn.navigation_factory('r1', {}, option=sn.OPTION, detector=constant_detector(dets),
                                    odometry=odometry(), arrival_range_m=threshold)
        rep = nav.observe(frame(0.0))
        assert rep['destination_arrived'] is True, dets
        assert rep['drive_reason'] == 'arrived', dets
        cmd = nav.command(0.1)
        assert cmd['wheels'] == [0.0] * 4 and cmd['duration_s'] == [0.0] * 4, dets


def test_missing_odometry_or_detector_fails_closed():
    nav = sn.navigation_factory('r1', {}, option=sn.OPTION,
                                detector=constant_detector(zone_detection()))
    rep = nav.observe(frame(0.0))
    assert rep['ready'] is False and rep['drive_reason'] == 'no_odometry'
    cmd = nav.command(0.0)
    assert cmd['wheels'] == [0.0] * 4 and cmd['duration_s'] == [0.0] * 4

    # No own-RGB detector: nothing could ever be acquired, so SEARCH must not
    # run (this is the pre-search hold, not a search timeout).
    nav = sn.navigation_factory('r1', {}, option=sn.OPTION, odometry=odometry())
    rep = nav.observe(frame(0.0))
    assert rep['ready'] is False and rep['drive_reason'] == 'no_destination'
    cmd = nav.command(0.0)
    assert cmd['wheels'] == [0.0] * 4 and cmd['duration_s'] == [0.0] * 4


def test_search_rotates_in_place_when_no_destination_is_remembered():
    nav = sn.navigation_factory('r1', {}, option=sn.OPTION, detector=constant_detector([]),
                                odometry=odometry())
    rep = nav.observe(frame(0.0))
    assert rep['ready'] is True and rep['destination_arrived'] is False
    assert rep['drive_reason'] == 'searching' and rep['search_steps'] == 0
    cmd = nav.command(0.0)
    issued_command(cmd)  # inside the own issued-command whitelist
    # Symmetric in-place turn: left/right wheels in opposite directions at the
    # calibrated amplitude and the short search pulse (35 % x 75 ms).
    assert cmd['wheels'][0] < 0.0 < cmd['wheels'][1]
    assert cmd['wheels'][0] == cmd['wheels'][2] and cmd['wheels'][1] == cmd['wheels'][3]
    assert all(abs(w) == sn.WHEEL_PCT for w in cmd['wheels'])
    assert all(dt == pytest.approx(sn.SEARCH_PULSE_DUTY * sn.PULSE_S) for dt in cmd['duration_s'])
    # The search pulse is shorter than a drive pulse and leaves an inter-command gap.
    assert sn.SEARCH_PULSE_DUTY * sn.PULSE_S < sn.PULSE_S
    assert rep['search_elapsed_s'] == 0.0
    # Still no destination: keep sweeping, never claim arrival.
    for step in range(1, 4):
        rep = nav.observe(frame(0.1 * step))
        assert rep['destination_arrived'] is False and rep['drive_reason'] == 'searching'
        cmd = nav.command(0.1 * step)
        assert cmd['wheels'] != [0.0] * 4


def test_search_direction_reverses_every_leg():
    nav = sn.navigation_factory('r1', {}, option=sn.OPTION, detector=constant_detector([]),
                                odometry=odometry())
    first = nav.command(0.0)['wheels'][0]
    for step in range(1, sn.SEARCH_LEG_STEPS):
        cmd = nav.command(0.1 * step)
        assert cmd['wheels'][0] == first
    # Leg boundary: the sweep reverses so the heading cannot wind past one turn.
    cmd = nav.command(0.1 * sn.SEARCH_LEG_STEPS)
    assert cmd['wheels'][0] == -first and cmd['wheels'][1] == first


def test_search_switches_to_driving_the_moment_the_destination_appears():
    detections = {'items': []}
    nav = sn.navigation_factory('r1', {}, option=sn.OPTION,
                                detector=lambda fr: detections['items'], odometry=odometry())
    assert nav.observe(frame(0.0))['drive_reason'] == 'searching'
    assert nav.command(0.0)['wheels'][0] < 0.0
    detections['items'] = zone_detection(range_m=2.0, bearing_deg=0.0)
    rep = nav.observe(frame(0.1))
    assert rep['drive_reason'] == 'driving' and rep['destination_arrived'] is False
    cmd = nav.command(0.1)
    assert cmd['wheels'] == [sn.WHEEL_PCT] * 4  # straight ahead, no residual turn
    assert all(dt == pytest.approx(sn.PULSE_S) for dt in cmd['duration_s'])


def test_search_times_out_to_a_hold_after_the_budget():
    nav = sn.navigation_factory('r1', {}, option=sn.OPTION, detector=constant_detector([]),
                                odometry=odometry())
    last = None
    for step in range(round(sn.SEARCH_BUDGET_S * 10)):
        last = nav.command(step / 10.0)
        assert last['wheels'] != [0.0] * 4
    assert nav._search_elapsed_s(round(sn.SEARCH_BUDGET_S * 10) / 10.0) == pytest.approx(
        sn.SEARCH_BUDGET_S)
    timed_out = nav.command(sn.SEARCH_BUDGET_S)
    assert timed_out['wheels'] == [0.0] * 4 and timed_out['duration_s'] == [0.0] * 4
    rep = nav.observe(frame(sn.SEARCH_BUDGET_S))
    assert rep['drive_reason'] == 'search_timeout'
    assert rep['destination_arrived'] is False
    assert rep['search_steps'] == round(sn.SEARCH_BUDGET_S * 10)
    # The timeout is sticky: further commands hold.
    assert nav.command(sn.SEARCH_BUDGET_S + 0.1)['wheels'] == [0.0] * 4
    assert nav.command(sn.SEARCH_BUDGET_S + 5.0)['wheels'] == [0.0] * 4


def test_search_timeout_does_not_block_a_later_detection():
    detections = {'items': []}
    nav = sn.navigation_factory('r1', {}, option=sn.OPTION,
                                detector=lambda fr: detections['items'], odometry=odometry())
    for step in range(round(sn.SEARCH_BUDGET_S * 10) + 1):
        nav.command(step / 10.0)
    assert nav.command(sn.SEARCH_BUDGET_S)['wheels'] == [0.0] * 4
    detections['items'] = zone_detection(range_m=2.0, bearing_deg=0.0)
    rep = nav.observe(frame(sn.SEARCH_BUDGET_S + 0.1))
    assert rep['drive_reason'] == 'driving'
    assert any(w != 0.0 for w in nav.command(sn.SEARCH_BUDGET_S + 0.1)['wheels'])


def test_search_hard_step_cap_bounds_a_non_monotonic_clock():
    nav = sn.navigation_factory('r1', {}, option=sn.OPTION, detector=constant_detector([]),
                                odometry=odometry())
    for _ in range(sn.SEARCH_MAX_STEPS):
        nav.command(0.0)  # frozen clock: sim time never reaches the budget
    timed_out = nav.command(0.0)
    assert timed_out['wheels'] == [0.0] * 4
    assert nav._drive_plan(0.0)['reason'] == 'search_timeout'


def test_search_sweeps_a_180_deg_zone_into_a_120_deg_camera():
    """Acquisition geometry: a zone behind the robot enters the camera in budget.

    The camera model is a synthetic 120 deg HFOV and the heading is integrated
    from the *issued* pulses with the measured gate yaw rate
    (1.7275 deg per percent-second, experiments/2026-10-18-nav-gate-1).  Both
    are eval-only assumptions of this pure-python test, never controller inputs.
    """
    yaw_deg_per_pct_s = 1.7275488814064257  # measured gate calibration
    zone_bearing_deg = 180.0  # directly behind the spawn heading
    state = {'heading_deg': 0.0}

    def fov_detector(fr):
        bearing = sn.wrap_deg(zone_bearing_deg - state['heading_deg'])
        if abs(bearing) <= 60.0:  # 120 deg camera HFOV
            return zone_detection(range_m=2.0, bearing_deg=bearing)
        return []

    nav = sn.navigation_factory('r1', {}, option=sn.OPTION, detector=fov_detector,
                                odometry=odometry())
    acquired_at = None
    for step in range(round(sn.SEARCH_BUDGET_S * 10)):
        rep = nav.observe(frame(step / 10.0))
        if rep['drive_reason'] == 'driving':
            acquired_at = step / 10.0
            break
        assert rep['drive_reason'] == 'searching'
        cmd = nav.command(step / 10.0)
        assert cmd['wheels'] != [0.0] * 4
        # +turn pulse has wheels[0] < 0; the issued row is normalized (0.35 =
        # 35 %), so convert back to percent-seconds before applying the rate.
        sign = 1.0 if cmd['wheels'][0] < 0.0 else -1.0
        state['heading_deg'] = sn.wrap_deg(
            state['heading_deg'] + sign * 100.0 * abs(cmd['wheels'][0])
            * cmd['duration_s'][0] * yaw_deg_per_pct_s)
    assert acquired_at is not None and 0.0 < acquired_at < sn.SEARCH_BUDGET_S
    assert rep['destination_arrived'] is False
    # The acquired landmark is followed (rotate toward it), not the blind sweep.
    follow = nav.command(acquired_at)
    assert follow['wheels'] != [0.0] * 4
    assert follow['duration_s'] != [0.0] * 4


def test_default_off_never_searches_when_no_destination_is_detected():
    nav = sn.navigation_factory('r1', {}, detector=constant_detector([]), odometry=odometry())
    for step in range(3):
        rep = nav.observe(frame(0.1 * step))
        assert rep['drive_reason'] == 'option_off' and rep['destination_arrived'] is False
        cmd = nav.command(0.1 * step)
        assert cmd['wheels'] == [0.0] * 4 and cmd['duration_s'] == [0.0] * 4


def test_appearance_only_destination_drives_and_bottom_band_stops():
    det = appearance_detection(bottom_norm=0.3)
    nav = sn.navigation_factory('r1', {}, option=sn.OPTION, detector=constant_detector(det),
                                odometry=odometry())
    rep = nav.observe(frame(0.0))
    assert rep['self_centric_memory'][0]['range_measured'] is False
    # A detector default range of 0.0 must not be read as "arrived at 0 m".
    assert rep['destination_arrived'] is False
    assert any(w != 0.0 for w in nav.command(0.0)['wheels'])

    near = appearance_detection(bottom_norm=0.99)
    nav = sn.navigation_factory('r1', {}, option=sn.OPTION, detector=constant_detector(near),
                                odometry=odometry())
    assert nav.observe(frame(1.0))['destination_arrived'] is True
    assert nav.command(1.0)['wheels'] == [0.0] * 4


def test_cross_robot_frame_and_issued_row_are_rejected():
    nav = sn.navigation_factory('r1', {}, option=sn.OPTION, detector=constant_detector([]),
                                odometry=odometry())
    with pytest.raises(ValueError, match='robot_id'):
        nav.observe(frame(0.0, robot_id='r2'))
    with pytest.raises(ValueError, match='robot_id'):
        nav.step_odometry(dict(t=0.0, wheels=[0.0] * 4, duration_s=[0.0] * 4, pwm={}, robot_id='r2'))
    with pytest.raises(ValueError, match='robot_id'):
        nav.observe(types.SimpleNamespace(sim_s=0.0, jpeg=b'jpg'))
    assert nav.observe(frame(0.0, robot_id='r1'))['robot_id'] == 'r1'
    # owned issued rows carry no robot_id and still apply
    assert nav.step_odometry(dict(t=0.0, wheels=[0.0] * 4, duration_s=[0.0] * 4, pwm={})) == (0.0, 0.0)


# ---- approved 2026-10-19 gate mode: gpu_calib_v230 + bounded forward leg ----

def test_gpu_calib_v230_raises_only_the_v_ceiling():
    """The approved band keeps H/S/min-component and raises V 110 -> 230."""
    import numpy as np
    bright = np.zeros((48, 64, 3), dtype=np.uint8)  # black
    # RGB (51, 89, 194) -> OpenCV H 112, S 188, V 194: measured bright zone paint.
    bright[20:, 20:44] = (51, 89, 194)
    assert sn.GpuCalibZoneDetector()(bright) == []  # v1 V<=110 rejects it
    v230 = sn.GpuCalibZoneDetector(profile='gpu_calib_v230')
    out = v230(bright)
    assert len(out) == 1 and out[0]['kind'] == 'zone_B'
    assert out[0]['profile'] == 'gpu_calib_v230' and out[0]['pixels'] >= 600
    assert sn.GPU_CALIB_V230['hue_cv'] == sn.GPU_CALIB_V1['hue_cv']
    assert sn.GPU_CALIB_V230['sat_min'] == sn.GPU_CALIB_V1['sat_min']
    assert sn.GPU_CALIB_V230['val'] == (30.0, 230.0)
    assert sn.GPU_CALIB_V230['min_pixels'] == 600
    with pytest.raises(ValueError, match='unknown own-RGB appearance profile'):
        sn.GpuCalibZoneDetector(profile='gpu_calib_v999')


def test_gpu_calib_v230_keeps_the_600_pixel_component_rule():
    import numpy as np
    img = np.zeros((64, 64, 3), dtype=np.uint8)
    img[20:44, 20:44] = (51, 89, 194)      # 24x24 = 576 px < 600
    assert sn.GpuCalibZoneDetector(profile='gpu_calib_v230')(img) == []
    img[20:45, 20:45] = (51, 89, 194)      # 25x25 = 625 px >= 600
    assert len(sn.GpuCalibZoneDetector(profile='gpu_calib_v230')(img)) == 1


def gate_odometry():
    """Measured gate calibration (experiments/2026-10-18-nav-gate-1/raw)."""
    return sn.OwnCommandOdometry(forward_m_per_pct_s=0.0040237052109054995,
                                 yaw_deg_per_pct_s=1.7277518947686832)


def forward_nav(detector=None, cap=2.4, odometry=None):
    return sn.navigation_factory(
        'r1', {}, option=sn.OPTION,
        detector=detector if detector is not None else constant_detector([]),
        odometry=gate_odometry() if odometry is None else odometry,
        acquisition_mode=sn.ACQUISITION_FORWARD_THEN_SEARCH, forward_cap_m=cap)


def test_forward_acquisition_is_straight_and_stops_exactly_at_2p4_m():
    nav = forward_nav()
    rep = nav.observe(frame(0.0))
    assert rep['drive_reason'] == 'acquiring_forward'
    assert rep['acquisition_mode'] == 'forward_then_search'
    assert rep['forward_cap_m'] == pytest.approx(2.4)
    assert rep['forward_used_m'] == 0.0
    used = 0.0
    step = 0
    while True:
        rep = nav.observe(frame(step / 10.0))
        if rep['drive_reason'] != 'acquiring_forward':
            break
        cmd = nav.command(step / 10.0)
        issued_command(cmd)
        # Straight +x: all four wheels at the calibrated 35 % amplitude.
        assert cmd['wheels'] == [sn.WHEEL_PCT] * 4
        assert all(dt > 0.0 for dt in cmd['duration_s'])
        assert all(dt <= sn.PULSE_S + 1e-12 for dt in cmd['duration_s'])
        used += gate_odometry().step(cmd)[0]
        assert used <= 2.4 + 1e-9
        step += 1
        assert step < 400
    # The cap is reached, then the same bounded in-place SEARCH starts.
    assert rep['drive_reason'] == 'searching'
    assert rep['forward_used_m'] == pytest.approx(2.4, abs=1e-9)
    assert used == pytest.approx(2.4, abs=1e-9)
    assert 165 <= rep['forward_steps'] <= 175          # ~171 x 0.01408 m
    assert 16.0 <= step / 10.0 <= 18.0                 # ~17.1 s of the 60 s budget
    turn = nav.command(step / 10.0)
    assert turn['wheels'][0] < 0.0 < turn['wheels'][1]  # in place, no advance
    assert turn['wheels'][0] == -turn['wheels'][1]
    # Nothing can move forward after the cap, even much later without detection.
    for later in range(1, 5):
        assert nav.command(step / 10.0 + later)['wheels'][0] < 0.0


def test_forward_acquisition_clips_the_final_pulse_to_the_cap():
    nav = forward_nav(cap=0.02)
    nav.observe(frame(0.0))
    first = nav.command(0.0)
    second = nav.command(0.1)
    od = gate_odometry()
    total = od.step(first)[0] + od.step(second)[0]
    assert total == pytest.approx(0.02, abs=1e-12)
    assert nav._forward_used_m == pytest.approx(0.02, abs=1e-12)
    assert nav._drive_plan(0.2)['reason'] == 'searching'
    assert nav.command(0.2)['wheels'][0] < 0.0


def test_forward_acquisition_switches_to_follow_in_the_same_control_step():
    items = {'items': []}
    nav = forward_nav(detector=lambda fr: items['items'])
    for step in range(20):
        nav.observe(frame(step / 10.0))
        nav.command(step / 10.0)
    assert nav._forward_used_m < 2.4
    items['items'] = zone_detection(range_m=2.0, bearing_deg=0.0)
    rep = nav.observe(frame(2.0))
    assert rep['drive_reason'] == 'driving'  # detection acted on immediately
    cmd = nav.command(2.0)
    assert cmd['wheels'] == [sn.WHEEL_PCT] * 4  # no residual turn
    assert all(dt == pytest.approx(sn.PULSE_S) for dt in cmd['duration_s'])
    # Follow pulses are not charged to (or capped by) the acquisition distance.
    assert nav._forward_used_m < 2.4


def test_forward_acquisition_is_default_off_and_fails_closed_on_bad_inputs():
    nav = sn.navigation_factory('r1', {}, option=sn.OPTION,
                                detector=constant_detector([]), odometry=gate_odometry())
    assert nav.acquisition_mode == sn.ACQUISITION_SEARCH_IN_PLACE
    assert nav.forward_cap_m == 0.0
    assert nav.observe(frame(0.0))['drive_reason'] == 'searching'
    assert nav.command(0.0)['wheels'][0] < 0.0
    with pytest.raises(ValueError, match='positive forward cap'):
        sn.navigation_factory('r1', {}, option=sn.OPTION, odometry=gate_odometry(),
                              acquisition_mode=sn.ACQUISITION_FORWARD_THEN_SEARCH)
    with pytest.raises(ValueError, match='forward cap is only valid'):
        sn.navigation_factory('r1', {}, option=sn.OPTION, odometry=gate_odometry(),
                              forward_cap_m=2.4)
    with pytest.raises(ValueError, match='unknown acquisition mode'):
        sn.navigation_factory('r1', {}, option=sn.OPTION, odometry=gate_odometry(),
                              acquisition_mode='blind_run')
    # Without injected odometry the forward leg cannot be integrated: hold.
    nav = sn.navigation_factory('r1', {}, option=sn.OPTION, detector=constant_detector([]),
                                acquisition_mode=sn.ACQUISITION_FORWARD_THEN_SEARCH,
                                forward_cap_m=2.4)
    rep = nav.observe(frame(0.0))
    assert rep['drive_reason'] == 'no_odometry'
    assert nav.command(0.0)['wheels'] == [0.0] * 4


def test_forward_acquisition_is_one_shot_and_never_restarts_after_following():
    items = {'items': []}
    nav = forward_nav(detector=lambda fr: items['items'])
    for step in range(20):
        nav.observe(frame(step / 10.0))
        nav.command(step / 10.0)
    items['items'] = zone_detection(range_m=2.0, bearing_deg=0.0)
    nav.observe(frame(2.0))
    nav.command(2.0)
    used = nav._forward_used_m
    assert nav._destination_seen is True and used < 2.4
    # A later memory loss must not open a second blind forward leg.
    nav.memory.items = []
    assert nav._drive_plan(3.0)['reason'] == 'searching'
    cmd = nav.command(3.0)
    assert cmd['wheels'][0] < 0.0 < cmd['wheels'][1]
    assert nav._forward_used_m == used


def test_detector_bearing_convention_matches_the_controller_turn_sign():
    import numpy as np
    img = np.zeros((48, 64, 3), dtype=np.uint8)
    img[12:, 6:26] = (51, 89, 194)   # patch left of image centre
    legacy = sn.GpuCalibZoneDetector(profile='gpu_calib_v230')
    control = sn.GpuCalibZoneDetector(profile='gpu_calib_v230',
                                      bearing_convention=sn.BEARING_POSITIVE_LEFT)
    ldet, cdet = legacy(img), control(img)
    assert len(ldet) == 1 and len(cdet) == 1
    # Image-column convention: left of centre is negative (legacy default).
    assert ldet[0]['bearing_deg'] < 0.0
    # Controller convention: the same left target is positive (turn left).
    assert cdet[0]['bearing_deg'] > 0.0
    assert cdet[0]['bearing_deg'] == pytest.approx(-ldet[0]['bearing_deg'], rel=1e-12)
    assert cdet[0]['bearing_convention'] == sn.BEARING_POSITIVE_LEFT
    assert ldet[0]['bearing_convention'] == sn.BEARING_POSITIVE_RIGHT
    with pytest.raises(ValueError, match='unknown bearing convention'):
        sn.GpuCalibZoneDetector(bearing_convention='mirrored')
    # The corrected convention drives a left target with a left (CCW) turn.
    nav = sn.navigation_factory('r1', {}, option=sn.OPTION, odometry=gate_odometry(),
                                detector=lambda fr: cdet)
    nav.observe(frame(0.0))
    cmd = nav.command(0.0)
    assert cmd['wheels'][0] < 0.0 < cmd['wheels'][1]


# ---- memory decay (2026-10-19 A fix: linear, anchored at last_seen) ----

def test_landmark_decay_is_linear_in_time_since_last_seen():
    """4.0 s -> 8.5 s: 0.5 -> 0.59 m; the old code reached 2.57 m (quadratic)."""
    lm = sn.Landmark('zone_B', 1.0, 0.0, 4.0)
    assert lm.base_uncertainty_m == 0.5
    values = []
    for step in range(1, 46):                      # 4.1 .. 8.5 s, 10 Hz ticks
        lm.decay(4.0 + step / 10.0)
        values.append(lm.uncertainty_m)
    assert values[0] == pytest.approx(0.502)
    assert values[-1] == pytest.approx(0.59)       # 4.5 s x 0.02 m/s = +0.09
    assert all(b >= a for a, b in zip(values, values[1:]))
    # Equal time steps add equal (not growing) increments.
    for a, b in zip(values, values[1:]):
        assert b - a == pytest.approx(0.002, abs=1e-12)


def test_landmark_decay_is_idempotent_at_the_same_instant():
    lm = sn.Landmark('zone_B', 1.0, 0.0, 0.0)
    for _ in range(45):                            # 45 calls at 4.5 s, not 4.5 s total
        lm.decay(4.5)
    assert lm.uncertainty_m == pytest.approx(0.59)


def test_landmark_decay_caps_at_max_uncertainty():
    lm = sn.Landmark('zone_B', 1.0, 0.0, 0.0)
    lm.decay(10.0)
    assert lm.uncertainty_m == pytest.approx(0.7)
    lm.decay(1000.0)
    assert lm.uncertainty_m == 3.0                 # min(max_m=3.0, ...)
    lm.decay(10000.0)
    assert lm.uncertainty_m == 3.0


def test_explicit_initial_uncertainty_becomes_the_decay_base():
    lm = sn.Landmark('zone_B', 1.0, 0.0, 0.0, uncertainty_m=0.3)
    lm.decay(5.0)
    assert lm.base_uncertainty_m == 0.3
    assert lm.uncertainty_m == pytest.approx(0.4)


def test_reobservation_resets_base_and_last_seen_together():
    detections = {'items': [{'kind': 'zone_B', 'range_m': 1.2, 'bearing_deg': 5.0}]}
    nav = sn.navigation_factory('r1', {}, option=sn.OPTION,
                                detector=lambda fr: detections['items'], odometry=odometry())
    nav.observe(frame(0.0))
    first = nav.memory.items[-1]
    detections['items'] = []
    nav.observe(frame(2.0))                        # no fresh detection: the clock ages
    assert first.uncertainty_m == pytest.approx(0.54)
    detections['items'] = [{'kind': 'zone_B', 'range_m': 1.0, 'bearing_deg': 4.0}]
    nav.observe(frame(3.0))                        # re-observation
    fresh = nav.memory.items[-1]
    assert fresh.last_seen_s == 3.0
    assert fresh.base_uncertainty_m == 0.5
    assert fresh.uncertainty_m == 0.5
    fresh.decay(4.0)
    assert fresh.uncertainty_m == pytest.approx(0.52)  # anchored at the new sighting
    # The earlier sighting keeps its own older clock (nothing rewrites it).
    assert first.last_seen_s == 0.0 and first.uncertainty_m == pytest.approx(0.56)


def test_single_detection_survives_past_the_old_nine_second_drop():
    """A target seen once at 4.0 s is still remembered at 45.0 s.

    The quadratic bug crossed the 3.0 m retention threshold at 9.0 s and deleted
    the target (the r2 search_timeout in the 2026-10-19 45 s diagnostic).
    """
    detections = {'items': [{'kind': 'zone_B', 'range_m': 1.0, 'bearing_deg': 20.0}]}
    nav = sn.navigation_factory('r1', {}, option=sn.OPTION,
                                detector=lambda fr: detections['items'], odometry=odometry())
    nav.observe(frame(4.0))
    detections['items'] = []
    for step in range(1, 411):                     # 4.1 .. 45.0 s, no new detection
        nav.observe(frame(4.0 + step / 10.0))
    target = nav.memory.nearest('zone_B')
    assert target is not None                      # old code: dropped at 9.0 s
    assert target.last_seen_s == 4.0
    assert target.uncertainty_m == pytest.approx(0.5 + 0.02 * 41.0)  # 1.32, below 3.0
