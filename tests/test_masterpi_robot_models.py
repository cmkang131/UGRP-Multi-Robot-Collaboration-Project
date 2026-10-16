"""Robot model as part of the scene version (PR #249). mj_forward only."""
from __future__ import annotations

import numpy as np
import pytest

mujoco = pytest.importorskip("mujoco")

from sim.masterpi_geometry_v3 import PHYSICAL_V3  # noqa: E402
from sim.masterpi_robot_models import (  # noqa: E402
    LEGACY_SCENE_ROBOT_MODEL,
    station_grasp_convention,
    v3_robot_xml_transform,
)
from sim.multi_masterpi_production import build_multi_robot_xml  # noqa: E402


def test_legacy_scenes_keep_v2_station_convention():
    v2 = station_grasp_convention(LEGACY_SCENE_ROBOT_MODEL)
    assert LEGACY_SCENE_ROBOT_MODEL == "masterpi_v2"
    assert v2["station_radius_m"] == v2["arm_radius_m"] == 0.155 and v2["arm_mount_x_m"] == 0.0


def test_v3_station_keeps_arm_radius_in_calibrated_range():
    v3 = station_grasp_convention("masterpi_v3")
    assert v3["arm_radius_m"] == 0.155
    assert v3["station_radius_m"] == pytest.approx(0.155 + PHYSICAL_V3.yaw_axis_x_m)
    with pytest.raises(ValueError):
        station_grasp_convention("masterpi_v9")


def test_v3_transform_swaps_every_robot_and_keeps_scene_bindings():
    base = build_multi_robot_xml(None, navigation_camera=True)
    xml = v3_robot_xml_transform({"wheelbase_m": .120, "track_m": .131})(base)
    v2m = mujoco.MjModel.from_xml_string(base)
    v3m = mujoco.MjModel.from_xml_string(xml)
    assert v3m.nu == v2m.nu and v3m.neq == v2m.neq and v3m.njnt == v2m.njnt
    d = mujoco.MjData(v3m)
    mujoco.mj_forward(v3m, d)
    for rid in ("r1", "r2", "r3"):
        robot = d.body(f"{rid}__robot")
        rel = robot.xmat.reshape(3, 3).T @ (d.body(f"{rid}__arm_base").xpos - robot.xpos)
        assert np.allclose(rel[:2], (PHYSICAL_V3.yaw_axis_x_m, 0), atol=1e-9)
        wheel = robot.xmat.reshape(3, 3).T @ (d.body(f"{rid}__wheel_fl_body").xpos - robot.xpos)
        assert np.allclose(wheel[:2], (PHYSICAL_V3.wheelbase_m / 2, PHYSICAL_V3.track_m / 2), atol=1e-9)
        assert v3m.camera(f"{rid}__nav_cam").id >= 0 and v3m.geom(f"{rid}__peer_visibility_band").id >= 0
        assert int(v3m.geom(f"{rid}__arm_box_collision").conaffinity[0]) & 2
    # robot poses are unchanged
    d2 = mujoco.MjData(v2m)
    mujoco.mj_forward(v2m, d2)
    for rid in ("r1", "r2", "r3"):
        assert np.allclose(d2.body(f"{rid}__robot").xpos, d.body(f"{rid}__robot").xpos)


def test_calibrated_wheel_geometry_wins():
    base = build_multi_robot_xml(None)
    xml = v3_robot_xml_transform({"wheelbase_m": .120, "track_m": .131}, calibrated_keys=("track_m",))(base)
    m = mujoco.MjModel.from_xml_string(xml)
    d = mujoco.MjData(m)
    mujoco.mj_forward(m, d)
    robot = d.body("r1__robot")
    wheel = robot.xmat.reshape(3, 3).T @ (d.body("r1__wheel_fl_body").xpos - robot.xpos)
    assert np.allclose(wheel[:2], (PHYSICAL_V3.wheelbase_m / 2, .131 / 2), atol=1e-9)
