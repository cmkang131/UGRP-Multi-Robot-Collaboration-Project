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


def test_missing_odometry_or_destination_fails_closed():
    nav = sn.navigation_factory('r1', {}, option=sn.OPTION,
                                detector=constant_detector(zone_detection()))
    rep = nav.observe(frame(0.0))
    assert rep['ready'] is False and rep['drive_reason'] == 'no_odometry'
    cmd = nav.command(0.0)
    assert cmd['wheels'] == [0.0] * 4 and cmd['duration_s'] == [0.0] * 4

    nav = sn.navigation_factory('r1', {}, option=sn.OPTION, detector=constant_detector([]),
                                odometry=odometry())
    rep = nav.observe(frame(0.0))
    assert rep['ready'] is True and rep['drive_reason'] == 'no_destination'
    cmd = nav.command(0.0)
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
