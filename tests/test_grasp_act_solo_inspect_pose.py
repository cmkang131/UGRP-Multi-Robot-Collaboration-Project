"""No world/render: camera-relative geometry must not gain fictitious motion."""
import json

import numpy as np
import pytest

from scripts.probe_solo_lift_inspect_pose import (
    MANIFEST, camera_object_transform, geometry_metrics, joint_grid,
    nominal_transforms, object_in_gripper, payload_bounds,
)

RUNS = json.loads(MANIFEST.read_text())['runs']
INSPECT_CANDIDATE = {1: 1500, 3: 900, 4: 2200, 5: 1800, 6: 1700}


def grasp(run):
    return {int(k): v for k, v in run['commands'][0]['pwm'].items()}


def test_frozen_chain_matches_actual_runner_camera_and_command_fk():
    from sim.masterpi_camera_review_v3 import POSITION_M, QUAT_WXYZ
    from harness.servo_camera_fk import fixed_transform, model, transform_from_commands
    from harness.visual_arm_v3 import tool_pose
    from sim.grasp_act_gaze import camera_extrinsics
    mount = fixed_transform(model()['camera'])
    actual = fixed_transform(dict(translation_m=POSITION_M, quaternion_wxyz=QUAT_WXYZ))
    np.testing.assert_allclose(mount, actual, atol=1e-14)
    for pwm in (INSPECT_CANDIDATE, grasp(RUNS[0])):
        g, c = nominal_transforms(pwm)
        wrist = tool_pose(pwm, tool_length_cm=0.)
        np.testing.assert_allclose(g[:3, 3], [wrist.x_m, wrist.y_m, wrist.z_m], atol=1e-12)
        origin, axes = camera_extrinsics(pwm)
        np.testing.assert_allclose(c[:3, 3], origin, atol=1e-12)
        np.testing.assert_allclose(c[:3, :3], np.asarray(axes).T, atol=1e-12)
        # Analysis must not accidentally qualify the unloaded runtime API.
        assert transform_from_commands(pwm, camera_pose='servo_fk_v1')[0] is None


def test_camera_to_gripper_invariant_over_joint_limited_pwm_grid():
    reference = None
    count = 0
    for pwm in joint_grid():
        g, c = nominal_transforms(pwm)
        relative = np.linalg.inv(c) @ g
        reference = relative if reference is None else reference
        np.testing.assert_allclose(relative, reference, atol=2e-14)
        count += 1
    assert count > 1000


@pytest.mark.parametrize('run', RUNS, ids=lambda run: run['run'])
def test_rigid_held_projection_cannot_be_repaired_by_post_grasp_inspect_pwm(run):
    p = grasp(run)
    before = camera_object_transform(run['kind'], p, p)
    after = camera_object_transform(run['kind'], p, INSPECT_CANDIDATE)
    np.testing.assert_allclose(after, before, atol=2e-14)
    a, b = geometry_metrics(run['kind'], before), geometry_metrics(run['kind'], after)
    assert a == b
    assert a['surface_sample_inside_ratio'] < .90  # whole cargo isn't framed
    if run['kind'] == 'cyan':
        assert a['usable_pixels'] == a['margin_pixels'] == 0
    else:
        assert a['usable_bbox_xyxy'][-1] >= 460  # still clipped at the bottom


def test_re_uprighting_the_cargo_after_moving_wrist_is_a_false_counterexample():
    p = grasp(RUNS[1])
    rigid = camera_object_transform('can', p, INSPECT_CANDIDATE)
    g, c = nominal_transforms(INSPECT_CANDIDATE)
    # Wrong model: assign a NEW grasp frame at the inspect pose. This models
    # object rotation/slip, not a retained rigid grasp or a camera-only servo.
    false = np.linalg.inv(c) @ g @ object_in_gripper('can', INSPECT_CANDIDATE)
    assert np.max(np.abs(rigid-false)) > .2
    assert geometry_metrics('can', rigid) != geometry_metrics('can', false)


def test_cylinder_caps_do_not_count_pixels_outside_the_radial_surface():
    transform = np.eye(4)
    transform[:3, 3] = [1., 0., .2]  # entirely to the right of the camera FOV
    assert geometry_metrics('can', transform)['raw_pixels'] == 0
    transform[:3, 3] = [0., 0., .2]
    row = geometry_metrics('can', transform)
    assert 10000 < row['raw_pixels'] < 20000  # projected circular front cap


@pytest.mark.parametrize('pwm', [
    {**INSPECT_CANDIDATE, 3: 2501},
    {**INSPECT_CANDIDATE, 5: 500},  # PWM-valid but outside shoulder joint limit
    {**INSPECT_CANDIDATE, 2: 1500},  # no independent camera servo
])
def test_invalid_pwm_and_invented_camera_joint_rejected(pwm):
    with pytest.raises(ValueError):
        nominal_transforms(pwm)


@pytest.mark.parametrize('kind', ['cyan', 'can', 'tile'])
def test_payload_only_static_torque_has_margin_to_configured_caps(kind):
    from sim.grasp_act_solo_teacher import cargo
    for row in payload_bounds(kind).values():
        assert row['payload_torque_bound_nm'] == pytest.approx(cargo(kind).mass_kg*9.80665*row['lever_bound_m'])
        assert row['remaining_payload_only_nm'] > .9*row['configured_cap_nm']
