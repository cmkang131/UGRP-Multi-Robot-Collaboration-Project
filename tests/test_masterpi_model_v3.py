"""MasterPi physical model v3: geometry set, frames, colliders, v2 isolation.

No physics stepping: every check compiles models and at most calls mj_forward.
"""
from __future__ import annotations

import math
from types import SimpleNamespace

import numpy as np
import pytest

mujoco = pytest.importorskip("mujoco")

from sim import masterpi_geometry_v3 as G  # noqa: E402
from sim.masterpi_dynamics_v2 import MasterPiDynamicsV2, build_v2_xml  # noqa: E402
from sim.masterpi_geometry_v3 import PHYSICAL_V3  # noqa: E402
from sim.masterpi_model_v3 import (  # noqa: E402
    CAMERA_HARDWARE_GROUP,
    SONAR_MOUNT_V3,
    SONAR_SITE,
    build_v2_appearance_xml,
    build_v3_xml,
)

LEGACY_SOURCE_CLASSES = {"official", "public_measured", "photo_estimate", "controller", "real_fit"}


@pytest.fixture(scope="module")
def models():
    return (mujoco.MjModel.from_xml_string(build_v2_xml()),
            mujoco.MjModel.from_xml_string(build_v2_appearance_xml()),
            mujoco.MjModel.from_xml_string(build_v3_xml()))


def _forward(model, joints=None):
    data = mujoco.MjData(model)
    for name, value in (joints or {}).items():
        data.qpos[model.jnt_qposadr[model.joint(name).id]] = value
    mujoco.mj_forward(model, data)
    return data


def _visual_only(model, i):
    return int(model.geom_contype[i]) == 0 and int(model.geom_conaffinity[i]) == 0


def _physical(model):
    return {model.geom(i).name: i for i in range(model.ngeom) if not _visual_only(model, i)}


def test_v2_builder_output_is_unchanged_by_importing_v3():
    before = build_v2_xml()
    build_v3_xml()
    build_v2_appearance_xml()
    assert build_v2_xml() == before


def test_v2_appearance_keeps_v2_physics_bit_identical(models):
    v2, app, _ = models
    assert set(_physical(v2)) == set(_physical(app))
    for f in ("body_pos", "body_quat", "body_mass", "body_inertia", "body_ipos", "jnt_range",
              "dof_damping", "actuator_gainprm", "actuator_forcerange", "cam_pos", "cam_quat", "site_pos"):
        assert np.array_equal(getattr(v2, f), getattr(app, f)), f
    for name in _physical(v2):
        a, b = v2.geom(name), app.geom(name)
        for attr in ("type", "size", "pos", "quat", "friction", "contype", "conaffinity", "condim"):
            assert np.array_equal(getattr(a, attr), getattr(b, attr)), (name, attr)


def test_v3_frames_follow_the_physical_geometry(models):
    _, _, v3 = models
    d = _forward(v3)
    g, r = PHYSICAL_V3, PHYSICAL_V3.wheel_radius_m
    floor = lambda body: d.body(body).xpos + np.array([0, 0, 0])  # robot freejoint puts axle at z=r
    assert np.allclose(d.body("robot").xpos, (0, 0, r))
    assert np.allclose(floor("arm_base"), (g.yaw_axis_x_m, 0, g.yaw_joint_z_floor_m), atol=1e-9)
    assert np.allclose(floor("shoulder_link"), (g.yaw_axis_x_m, 0, g.shoulder_axis_z_floor_m), atol=1e-9)
    assert np.allclose(floor("elbow_link")[0] - floor("shoulder_link")[0], g.upper_arm_m)
    assert np.allclose(floor("wrist_link")[0] - floor("elbow_link")[0], g.forearm_m)
    grip = d.site("grip_site").xpos
    assert grip[0] - floor("wrist_link")[0] == pytest.approx(g.pad_center_from_wrist_m)
    assert g.pad_center_from_wrist_m == pytest.approx(0.08685)
    for side in ("left", "right"):
        finger = v3.geom(f"{side}_finger")
        assert finger.size[0] == pytest.approx(g.finger_pad_length_m / 2)
        assert finger.pos[0] == pytest.approx(g.pad_center_from_wrist_m)
    for w, (sx, sy) in {"fl": (1, 1), "fr": (1, -1), "rl": (-1, 1), "rr": (-1, -1)}.items():
        assert np.allclose(d.body(f"wheel_{w}_body").xpos[:2], (sx * g.wheelbase_m / 2, sy * g.track_m / 2))
        assert v3.geom(f"wheel_{w}").size[1] == pytest.approx(g.wheel_width_m / 2)


def test_v3_keeps_dynamics_camera_and_calibration_hooks(models):
    v2, _, v3 = models
    names = lambda m, n, obj: [mujoco.mj_id2name(m, obj, i) for i in range(n)]
    assert names(v2, v2.nu, mujoco.mjtObj.mjOBJ_ACTUATOR) == names(v3, v3.nu, mujoco.mjtObj.mjOBJ_ACTUATOR)
    for f in ("actuator_gainprm", "actuator_biasprm", "actuator_forcerange", "actuator_ctrlrange",
              "jnt_range", "jnt_axis", "dof_damping", "body_mass", "body_inertia", "cam_pos", "cam_quat",
              "cam_intrinsic", "cam_resolution"):
        assert np.array_equal(getattr(v2, f), getattr(v3, f)), f
    assert v3.body("robot").mass == v2.body("robot").mass
    # explicit/calibrated wheel geometry wins over the drawing
    hw = mujoco.MjModel.from_xml_string(build_v3_xml({"track_m": .131, "wheelbase_m": .120}))
    d = _forward(hw)
    assert np.allclose(d.body("wheel_fl_body").xpos[:2], (.060, .0655))


def test_v3_robot_cam_is_rigid_on_the_gripper_and_hardware_is_hidden(models):
    v2, _, v3 = models
    pose = {"arm_yaw": .3, "shoulder": .9, "elbow": -.6, "wrist_pitch": -.8}
    for model in (v2, v3):
        d = _forward(model, pose)
        rel = d.body("gripper").xmat.reshape(3, 3).T @ (d.cam("robot_cam").xpos - d.body("gripper").xpos)
        assert np.allclose(rel, (0.067, 0, 0.0136), atol=1e-9)
    cams = [i for i in range(v3.ngeom) if v3.geom(i).name.startswith("v3_camera_")]
    assert cams and all(int(v3.geom_group[i]) == CAMERA_HARDWARE_GROUP for i in cams)


def test_v3_colliders_and_sonar(models):
    _, _, v3 = models
    phys = _physical(v3)
    for name in ("arm_box_collision", "yaw_servo_collision", "ultrasonic_collision",
                 "base_lower_collision", "rear_cage_collision", "arm_pedestal_collision"):
        assert name in phys
    assert v3.geom("base_lower_collision").size[0] == pytest.approx(G.CHASSIS_LENGTH_M / 2 - .002)
    d = _forward(v3)
    site = d.site(SONAR_SITE)
    assert np.allclose(site.xpos, SONAR_MOUNT_V3["pos_floor_m"], atol=1e-9)
    assert SONAR_MOUNT_V3["pos_floor_m"] == (0.088, 0.0, 0.0617)
    assert np.allclose(site.xmat.reshape(3, 3)[:, 2], (1, 0, 0))
    # every added visual is massless and non-colliding
    for i in range(v3.ngeom):
        if v3.geom(i).name.startswith("v3_"):
            assert _visual_only(v3, i)


def test_v3_has_no_initial_self_or_floor_penetration(models):
    _, _, v3 = models
    d = _forward(v3)
    robot = v3.body("robot").id
    for c in d.contact[:d.ncon]:
        b1, b2 = v3.geom_bodyid[c.geom1], v3.geom_bodyid[c.geom2]
        roots = {int(v3.body_rootid[b1]), int(v3.body_rootid[b2])}
        if roots == {robot}:
            pytest.fail(f"self contact {v3.geom(c.geom1).name} / {v3.geom(c.geom2).name}")
        # wheels may touch the floor; nothing else of the robot may
        names = {v3.geom(c.geom1).name, v3.geom(c.geom2).name}
        if robot in roots and not any(n.startswith("wheel_") for n in names):
            assert c.dist > -1e-4, names


def test_controller_mismatch_table_is_explicit():
    rows = {name: (ctrl, phys) for name, ctrl, phys, _ in G.CONTROLLER_VS_PHYSICAL_V3}
    assert rows["shoulder_axis_z_floor_m"] == pytest.approx((0.1255, 0.1277))
    assert rows["tool_point_from_wrist_m"] == pytest.approx((0.100, 0.08685))
    # the physical arm lengths the SDK does match
    assert PHYSICAL_V3.upper_arm_m == G.CONTROLLER_UPPER_ARM_M
    assert PHYSICAL_V3.forearm_m == G.CONTROLLER_FOREARM_M


def test_sim_fk_matches_v3_frames_at_servo_poses(models):
    """PWM -> joint map (unchanged v2 actuator map) drives the v3 physical arm."""
    _, _, v3 = models
    fake = SimpleNamespace(physical_params={"servo6_center_pwm": 1500.0})
    pose = {3: 1000, 4: 1800, 5: 1300, 6: 1600}
    targets = MasterPiDynamicsV2.pulse_to_joint_targets(fake, pose)
    d = _forward(v3, {"arm_yaw": targets["yaw"], "shoulder": targets["shoulder"],
                      "elbow": targets["elbow"], "wrist_pitch": targets["wrist"]})
    g = PHYSICAL_V3
    th5, th4, th3 = targets["shoulder"], -targets["elbow"], targets["wrist"]
    yaw = targets["yaw"]
    radius = (g.upper_arm_m * math.cos(th5) + g.forearm_m * math.cos(th5 - th4)
              + g.pad_center_from_wrist_m * math.cos(th3 + th5 - th4))
    height = (g.shoulder_axis_z_floor_m + g.upper_arm_m * math.sin(th5) + g.forearm_m * math.sin(th5 - th4)
              + g.pad_center_from_wrist_m * math.sin(th3 + th5 - th4))
    expect = (g.yaw_axis_x_m + radius * math.cos(yaw), radius * math.sin(yaw), height)
    assert np.allclose(d.site("grip_site").xpos, expect, atol=1e-9)


def test_physical_geometry_set_is_source_tagged_and_replaceable():
    values = PHYSICAL_V3.values()
    assert set(values) == set(PHYSICAL_V3.sources)
    assert {c for c, _ in PHYSICAL_V3.sources.values()} <= set(G.PHYSICAL_SOURCE_CLASSES)
    measured = PHYSICAL_V3.with_measurements(version="masterpi-physical-ugrp1-test", note="tape", upper_arm_m=.0648)
    assert measured.upper_arm_m == .0648 and measured.sources["upper_arm_m"] == ("real_measured", "tape")
    assert PHYSICAL_V3.upper_arm_m == .065
    with pytest.raises(ValueError):
        PHYSICAL_V3.with_measurements(version=PHYSICAL_V3.version, note="x", upper_arm_m=.06)
    with pytest.raises(ValueError):
        PHYSICAL_V3.with_measurements(version="v", note="x", not_a_field=1.0)
    m = mujoco.MjModel.from_xml_string(build_v3_xml(geometry=measured))
    d = _forward(m)
    assert d.body("elbow_link").xpos[0] - d.body("shoulder_link").xpos[0] == pytest.approx(.0648)


def test_legacy_drawing_sources_classified():
    for name, (value, cls, note) in G.SOURCES.items():
        assert cls in LEGACY_SOURCE_CLASSES, name
        assert note
    assert G.drawing_side_to_m(880.0, 991.5) == (0.0, 0.0)
    assert len(G.MEASURE_ON_ROBOT) >= 15
