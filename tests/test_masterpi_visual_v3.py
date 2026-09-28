"""MasterPi visual v3: appearance/physics separation, sonar mount, provenance.

No physics stepping: every check compiles models and at most calls mj_forward.
"""
from __future__ import annotations

import copy
import math
import xml.etree.ElementTree as ET

import numpy as np
import pytest

mujoco = pytest.importorskip("mujoco")

from sim import masterpi_geometry_v3 as G  # noqa: E402
from sim.masterpi_dynamics_v2 import build_v2_xml  # noqa: E402
from sim.masterpi_visual_v3 import (  # noqa: E402
    PROFILE_APPEARANCE_ONLY,
    PROFILE_DRAWING_LAYOUT,
    SONAR_MOUNT_V3,
    SONAR_SITE,
    build_v3_xml,
)

ALLOWED_SOURCE_CLASSES = {"official", "public_measured", "photo_estimate", "controller", "real_fit"}


@pytest.fixture(scope="module")
def models():
    v2 = mujoco.MjModel.from_xml_string(build_v2_xml())
    app = mujoco.MjModel.from_xml_string(build_v3_xml(profile=PROFILE_APPEARANCE_ONLY))
    draw = mujoco.MjModel.from_xml_string(build_v3_xml(profile=PROFILE_DRAWING_LAYOUT))
    return v2, app, draw


def _name(model, obj, i):
    return mujoco.mj_id2name(model, obj, i) or ""


def _visual_only(model, i):
    return int(model.geom_contype[i]) == 0 and int(model.geom_conaffinity[i]) == 0


def _physical_geoms(model):
    out = {}
    for i in range(model.ngeom):
        if _visual_only(model, i):
            continue
        out[_name(model, mujoco.mjtObj.mjOBJ_GEOM, i)] = i
    return out


GEOM_FIELDS = ("geom_type", "geom_size", "geom_pos", "geom_quat", "geom_friction", "geom_contype",
               "geom_conaffinity", "geom_condim", "geom_priority", "geom_solref", "geom_solimp",
               "geom_margin", "geom_gap", "geom_bodyid")
BODY_FIELDS = ("body_pos", "body_quat", "body_mass", "body_inertia", "body_ipos", "body_iquat",
               "body_parentid", "body_jntnum")
JOINT_FIELDS = ("jnt_type", "jnt_axis", "jnt_pos", "jnt_range", "jnt_bodyid", "dof_damping",
                "dof_armature", "dof_frictionloss")
ACT_FIELDS = ("actuator_gainprm", "actuator_biasprm", "actuator_ctrlrange", "actuator_forcerange",
              "actuator_trnid")
CAM_FIELDS = ("cam_pos", "cam_quat", "cam_fovy", "cam_intrinsic", "cam_sensorsize", "cam_resolution",
              "cam_bodyid")


def _same(a, b, field):
    np.testing.assert_array_equal(getattr(a, field), getattr(b, field), err_msg=field)


def test_v2_builder_output_is_not_mutated():
    before = build_v2_xml()
    build_v3_xml(profile=PROFILE_APPEARANCE_ONLY)
    build_v3_xml(profile=PROFILE_DRAWING_LAYOUT)
    assert build_v2_xml() == before


def test_profile_must_be_explicit():
    with pytest.raises(TypeError):
        build_v3_xml()  # type: ignore[call-arg]
    with pytest.raises(ValueError):
        build_v3_xml(profile="v3")


def test_appearance_only_keeps_v2_physics_exactly(models):
    v2, app, _ = models
    for count in ("nbody", "njnt", "nq", "nv", "nu", "ncam", "neq", "ntendon"):
        assert getattr(v2, count) == getattr(app, count), count
    for field in BODY_FIELDS + JOINT_FIELDS + ACT_FIELDS + CAM_FIELDS:
        _same(v2, app, field)
    for i in range(v2.nbody):
        assert _name(v2, mujoco.mjtObj.mjOBJ_BODY, i) == _name(app, mujoco.mjtObj.mjOBJ_BODY, i)
    np.testing.assert_array_equal(v2.opt.gravity, app.opt.gravity)
    assert v2.opt.timestep == app.opt.timestep
    p2, pa = _physical_geoms(v2), _physical_geoms(app)
    assert set(p2) == set(pa)
    for name, i in p2.items():
        j = pa[name]
        for field in GEOM_FIELDS:
            np.testing.assert_array_equal(getattr(v2, field)[i], getattr(app, field)[j], err_msg=f"{name}.{field}")
    # every v2 site survives unchanged; v3 only adds its sonar site
    for i in range(v2.nsite):
        name = _name(v2, mujoco.mjtObj.mjOBJ_SITE, i)
        j = app.site(name).id
        np.testing.assert_array_equal(v2.site_pos[i], app.site_pos[j])
        np.testing.assert_array_equal(v2.site_bodyid[i], app.site_bodyid[j])
    assert app.nsite == v2.nsite + 1


def test_appearance_only_forward_kinematics_match_v2(models):
    v2, app, _ = models
    d2, da = mujoco.MjData(v2), mujoco.MjData(app)
    for m, d in ((v2, d2), (app, da)):
        for joint, value in (("arm_yaw", .3), ("shoulder", 1.1), ("elbow", -.7), ("wrist_pitch", -.4)):
            d.qpos[m.jnt_qposadr[m.joint(joint).id]] = value
        mujoco.mj_forward(m, d)
    np.testing.assert_allclose(d2.xpos, da.xpos, atol=0, rtol=0)
    np.testing.assert_allclose(d2.cam_xpos, da.cam_xpos, atol=0, rtol=0)
    np.testing.assert_allclose(d2.cam_xmat, da.cam_xmat, atol=0, rtol=0)


def test_all_added_geoms_are_massless_visuals(models):
    v2, app, _ = models
    v2_names = {_name(v2, mujoco.mjtObj.mjOBJ_GEOM, i) for i in range(v2.ngeom)}
    robot_root = app.body("robot").id
    added = 0
    for i in range(app.ngeom):
        name = _name(app, mujoco.mjtObj.mjOBJ_GEOM, i)
        if name in v2_names:
            continue
        added += 1
        assert name.startswith("v3_"), name
        assert _visual_only(app, i), name
        assert app.body_rootid[app.geom_bodyid[i]] == robot_root, name
    assert added > 200
    # colliding proxies are hidden; v2 visual-only geoms are gone from the robot
    for i in range(app.ngeom):
        if app.body_rootid[app.geom_bodyid[i]] != robot_root:
            continue
        name = _name(app, mujoco.mjtObj.mjOBJ_GEOM, i)
        if not name.startswith("v3_"):
            assert not _visual_only(app, i), name
            assert app.geom_rgba[i][3] == 0.0, name


def test_sonar_mount_matches_drawing_values(models):
    _, app, draw = models
    for m in (app, draw):
        d = mujoco.MjData(m)
        mujoco.mj_forward(m, d)
        base = d.body("robot").xpos
        p = d.site(SONAR_SITE).xpos
        axis = d.site(SONAR_SITE).xmat.reshape(3, 3)[:, 2]
        assert p[0] - base[0] == pytest.approx(G.SONAR_FACE_X_M, abs=1e-6)
        assert p[1] - base[1] == pytest.approx(0.0, abs=1e-6)
        assert p[2] == pytest.approx(G.SONAR_CENTER_Z_FLOOR_M, abs=1e-6)
        np.testing.assert_allclose(axis, (1, 0, 0), atol=1e-9)
        for side, s in (("left", 1), ("right", -1)):
            g = d.geom(f"v3_sonar_can_{side}")
            assert g.xpos[1] - base[1] == pytest.approx(s * G.SONAR_TRANSDUCER_SPACING_M / 2, abs=1e-6)
            assert g.xpos[2] == pytest.approx(G.SONAR_CENTER_Z_FLOOR_M, abs=1e-6)
    assert SONAR_MOUNT_V3["pos_floor_m"] == (G.SONAR_FACE_X_M, 0.0, G.SONAR_CENTER_Z_FLOOR_M)
    # the correction relative to v2 is material, not rounding
    assert G.SONAR_CENTER_Z_FLOOR_M - G.V2_SONAR_CENTER_Z_FLOOR_M > 0.005


def test_drawing_layout_changes_only_declared_structure(models):
    _, app, draw = models
    for field in ("body_mass", "body_inertia", "body_ipos", "body_quat") + JOINT_FIELDS + ACT_FIELDS + CAM_FIELDS:
        _same(app, draw, field)
    moved = np.flatnonzero(np.any(app.body_pos != draw.body_pos, axis=1))
    assert [_name(draw, mujoco.mjtObj.mjOBJ_BODY, i) for i in moved] == ["arm_base"]
    assert draw.body("arm_base").pos[0] == pytest.approx(G.YAW_AXIS_X_M)
    assert draw.body("arm_base").pos[2] == app.body("arm_base").pos[2]
    pa, pd = _physical_geoms(app), _physical_geoms(draw)
    assert set(pd) - set(pa) == {"arm_box_collision"}
    changed = {n for n in pa if any(np.any(getattr(app, f)[pa[n]] != getattr(draw, f)[pd[n]]) for f in ("geom_size", "geom_pos"))}
    assert changed == {"base_lower_collision", "base_top", "front_plate", "rear_cage_collision"}


def test_v3_robot_clones_with_prefixes_like_multi_robot_builder():
    root = ET.fromstring(build_v3_xml(profile=PROFILE_APPEARANCE_ONLY))
    world = root.find("worldbody")
    robot = next(c for c in world if c.tag == "body" and c.get("name") == "robot")
    idx = list(world).index(robot)
    world.remove(robot)
    for k, rid in enumerate(("a", "b")):
        clone = copy.deepcopy(robot)
        for item in clone.iter():
            if item.get("name"):
                item.set("name", f"{rid}__{item.get('name')}")
        clone.set("pos", f"0 {k * .4:.3f} .0325")
        world.insert(idx + k, clone)
    actuator = root.find("actuator")
    for item in list(actuator):
        actuator.remove(item)
    model = mujoco.MjModel.from_xml_string(ET.tostring(root, encoding="unicode"))
    assert model.site("a__" + SONAR_SITE).id != model.site("b__" + SONAR_SITE).id


def test_arm_visuals_follow_joint_frames(models):
    _, _, draw = models
    d = mujoco.MjData(draw)
    d.qpos[draw.jnt_qposadr[draw.joint("shoulder").id]] = math.pi / 2
    mujoco.mj_forward(draw, d)
    # arm straight up: the ID5 servo body is centred on the shoulder link axis
    servo = d.geom("v3_shoulder_servo").xpos
    shoulder = d.body("shoulder_link").xpos
    assert servo[0] == pytest.approx(shoulder[0], abs=1e-6)
    assert servo[2] > shoulder[2]
    # camera lens front sits exactly on the unchanged robot_cam position
    lens = d.geom("v3_camera_lens_glass")
    cam = d.cam("robot_cam")
    assert np.linalg.norm(lens.xpos - cam.xpos) < 0.001


def test_every_source_entry_is_classified():
    assert G.SOURCES
    for name, (value, klass, where) in G.SOURCES.items():
        assert klass in ALLOWED_SOURCE_CLASSES, name
        assert where, name
        assert getattr(G, name) == value, name
    assert len(G.MEASURE_ON_ROBOT) >= 10
    keys = {row[0] for row in G.MEASURE_ON_ROBOT}
    assert {"sonar_center_height_mm", "sonar_face_forward_mm", "yaw_axis_forward_mm", "upper_arm_mm"} <= keys


def test_drawing_scale_helper_reproduces_printed_dimensions():
    # printed 101 mm cover line (y=751 px) and 65 mm wheel line (y=838 px)
    assert G.drawing_side_to_m(880, 751)[1] == pytest.approx(0.101, abs=0.0015)
    assert G.drawing_side_to_m(880, 838)[1] == pytest.approx(0.065, abs=0.0015)
    assert G.drawing_side_to_m(672.5, 846)[0] == pytest.approx(G.SONAR_FACE_X_M, abs=0.0005)


def test_new_modules_are_outside_registered_bundle_sources():
    from harness.rgb_execution_bundle import source_closure

    closure = source_closure()
    assert "sim/masterpi_visual_v3.py" not in closure
    assert "sim/masterpi_geometry_v3.py" not in closure
