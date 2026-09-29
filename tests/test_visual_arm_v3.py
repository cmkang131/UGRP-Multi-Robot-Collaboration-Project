"""새 FK/IK·카메라와 mj_forward의 수치 비교; v2 수학은 import로 재사용."""
import math

import numpy as np
import pytest

mujoco = pytest.importorskip('mujoco')

from harness import visual_arm as v2, visual_arm_v3 as v3
from harness.zone_own_guards import OwnPose
from harness.zone_own_guards_v3 import SweepGuardV3, body_spheres
from harness.zone_robot_model_runtime import for_scene, require_v3_consumers
from scripts.audit_masterpi_v3_static import compile_start, set_static_pwm
from sim.zone_masterpi_v3_scene import MAP_IDS


@pytest.fixture(autouse=True)
def no_step(monkeypatch):
    monkeypatch.setattr(mujoco, 'mj_step', lambda *a, **k: pytest.fail('mj_step 금지'))


@pytest.mark.parametrize('pan', [1300, 1500, 1700])
def test_fk_camera_match_forward(pan):
    _, m, d, _ = compile_start(MAP_IDS[0])
    pwm = {1: 1500, 3: 1000, 4: 2200, 5: 1400, 6: pan}
    set_static_pwm(m, d, 'r1', pwm)
    mujoco.mj_forward(m, d)
    base = d.body('r1__robot')
    rotation = base.xmat.reshape(3, 3)
    # Controller coordinates use floor z; the simulated robot origin is axle z.
    offset = base.xpos - np.array([0., 0., .0325])
    expected = rotation.T @ (d.site('r1__grip_site').xpos - offset)
    np.testing.assert_allclose(v3.forward_grip(pwm), expected, atol=1e-8)
    cid = m.camera('r1__robot_cam').id
    origin, axes = v3.camera_extrinsics(pwm)
    np.testing.assert_allclose(origin, rotation.T @ (d.cam_xpos[cid] - offset), atol=1e-8)
    cv_axes = d.cam_xmat[cid].reshape(3, 3) @ np.diag([1., -1., -1.])
    np.testing.assert_allclose(np.array(axes).T, rotation.T @ cv_axes, atol=1e-8)


@pytest.mark.parametrize('yaw', [-10., 0., 10.])
@pytest.mark.parametrize('radius', [.145, .155, .16])
def test_ik_targets_physical_pad_in_arm_axis_frame(radius, yaw):
    angle = math.radians(yaw)
    target = (.0482 + radius*math.cos(angle), radius*math.sin(angle), .024)
    pose = v3.solve_grip_site_ik(target)
    assert np.linalg.norm(np.array(v3.forward_grip(pose)) - target) < .0005
    assert abs(v2.forward_grip(pose)[0] - target[0]) > .02


def test_bad_targets_fail_closed():
    for target in ((.10, 0., .024), (float('nan'), 0., .024), (.2, .2, .024), (.2032, 0., 3.),
                   (.2282, 0., .024)):
        with pytest.raises(ValueError):
            v3.solve_grip_site_ik(target)


def test_guard_mount_does_not_rotate_with_pan():
    from harness.zone_own_guards import body_spheres as old_spheres
    for pan in (1000, 1500, 2000):
        pwm = {1: 2000, 3: 740, 4: 2320, 5: 1320, 6: pan}
        a = np.asarray(body_spheres(pwm, loaded=True))
        b = np.asarray(old_spheres(pwm, loaded=True))
        np.testing.assert_allclose(a[:, :3] - b[:, :3], np.tile(v3.MOUNT_XYZ_M, (len(a), 1)), atol=1e-10)


def test_guard_checks_intermediate_sweep_and_margin():
    static = {'obstacles': [{'id': 'front_wall', 'center_m': [.27, 0.],
                            'half_extents_m': [.01, 1.], 'height_m': .4}]}
    guard = SweepGuardV3(static)
    current = {1: 2000, 3: 740, 4: 2320, 5: 1320, 6: 1300}
    target = {**v3.solve_grip_ik(.2032, 0., .024), 1: 2000, 6: 1700}
    own = OwnPose(0., 0., 0., .005, .01)
    samples = list(guard.transition_samples(current, target))
    assert samples[0] == current and samples[-1] == target and len(samples) > 2
    assert any(guard.arm_clearance(p, own, loaded=False)[0] < 0 for p in samples)
    assert not guard.transition_clear(current, target, own, loaded=False)
    diag = guard.transition_diagnostic(current, target, own, loaded=False)
    assert diag['limiting']['wall_id'] == 'front_wall'
    assert diag['limiting']['clearance_mm'] < 0


def test_runtime_is_scene_selected_and_v2_consumers_refused():
    scene, _, _, _ = compile_start(MAP_IDS[0])
    runtime = for_scene(scene)
    assert runtime.arm is v3 and isinstance(runtime.guard, SweepGuardV3)
    with pytest.raises(ValueError, match='v3 skill'):
        require_v3_consumers({'skill_module': 'harness.wrist_zone_skill_v9'}, None)
    pwm = {1: 2000, 3: 740, 4: 2320, 5: 1320, 6: 1500}
    assert not runtime.guard.transition_clear(pwm, {6: 1700}, None, loaded=False)
    assert runtime.guard.plan(pwm, pwm, [1300, 1700], None, loaded=False)['pans'] == []
