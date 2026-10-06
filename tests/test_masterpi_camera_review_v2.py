"""Pure optical/profile/command contract tests; no simulation or rendering."""
import xml.etree.ElementTree as ET
import cv2
import numpy as np
import pytest
from sim import masterpi_camera_review_v2 as v2
from scripts.review_masterpi_camera_v2 import metrics, plan, targets, JOINT_NAMES


def test_sdk_rectification_projects_original_brown_rays_to_output_pixels():
    k = v2.rectified_matrix()
    ideal = np.array([[-.10, -.02, 1.], [.12, .18, 1.], [0., 0., 1.]])
    raw, _ = cv2.projectPoints(ideal, np.zeros(3), np.zeros(3), np.array(v2.K), np.array(v2.BROWN_D))
    pixels = cv2.undistortPoints(raw, np.array(v2.K), np.array(v2.BROWN_D), P=k).reshape(-1, 2)
    expected = (ideal @ k.T)[:, :2]
    np.testing.assert_allclose(pixels, expected, atol=.001)
    np.testing.assert_allclose(v2.pixel_intrinsic(), [k[0, 0], k[1, 1], 320-k[0, 2], 240-k[1, 2]])


def test_new_profile_does_not_edit_physics_or_original_intrinsic_xml():
    pytest.importorskip("mujoco")
    from sim.masterpi_model_v3 import build_v3_xml
    before = ET.fromstring(build_v3_xml())
    after = ET.fromstring(v2.transform_xml(ET.tostring(before, encoding='unicode'), profile_id=v2.PROFILE_ID))
    for a, b in zip(before.iter(), after.iter()):
        if a.get('name') != 'robot_cam' and not a.get('name', '').startswith('v3_camera_'):
            assert a.attrib == b.attrib
    assert v2.record()['runtime_admitted'] is False
    assert v2.record()['setdown_relook_candidate']['implemented'] is False
    with pytest.raises(ValueError):
        v2.transform_xml('<mujoco/>', profile_id='default')


def test_official_lift_is_horizontal_and_distinct_from_high():
    from harness.visual_arm_v3 import tool_pose
    from harness.zone_pair_highpose import HIGH
    assert tool_pose(v2.OFFICIAL_LIFT_PWM).pitch_deg == pytest.approx(0)
    assert tool_pose(HIGH).pitch_deg == pytest.approx(-40.05)
    assert v2.OFFICIAL_LIFT_PWM == {k: v + {3: 54, 4: 53, 5: 89, 6: 64}[k]
                                    for k, v in v2.OFFICIAL_LIFT_NOMINAL.items()}


def test_diagnostic_targets_and_actuator_names_exist_and_fit_ranges():
    pytest.importorskip("mujoco")
    from sim.masterpi_model_v3 import build_v3_xml
    root = ET.fromstring(build_v3_xml())
    joints = {x.get('name'): x for x in root.iter('joint') if x.get('name')}
    actuators = {x.get('name') for x in root.find('actuator')}
    for _, pose, duration, hold in plan():
        assert 0 < duration <= 1.5 and hold <= 2.8
        for key, value in targets(pose).items():
            joint = 'left_gripper_close' if key == 'gripper' else JOINT_NAMES[key]
            lo, hi = map(float, joints[joint].get('range').split())
            assert lo <= value <= hi
            name = {'yaw': 'servo_arm_yaw', 'gripper': 'servo_gripper_left'}.get(key, 'servo_'+key)
            assert name in actuators


def test_stock_output_denominator_does_not_reuse_fisheye_black_border():
    valid = v2.valid_mask()
    assert valid.shape == (480, 640) and valid.mean() > .99
    rgb = np.full((480, 640, 3), [0, 255, 255], dtype=np.uint8)
    rgb[~valid] = 0
    measured = metrics(rgb, valid)
    assert measured['valid_fraction'] == 1
    assert measured['full_fraction'] == pytest.approx(valid.mean())
