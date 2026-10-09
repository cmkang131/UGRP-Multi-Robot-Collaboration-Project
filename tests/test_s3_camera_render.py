"""Actual shared render-call path; deterministic renderer double, no SIM steps."""
from types import SimpleNamespace, MethodType
import threading

import numpy as np
import pytest

from sim import masterpi_camera_review_v3 as v3
from sim.s3_camera_binding import attach, camera_pose


def model_world():
    import mujoco
    from sim.masterpi_dynamics_v2 import MasterPiDynamicsV2
    from sim.multi_masterpi_production import MultiMasterPiProductionV2
    xml = '<mujoco><worldbody>' + ''.join(
        f'<body name="{rid}" pos="{i} 0 .2"><camera name="{rid}__robot_cam"/></body>'
        for i, rid in enumerate(('r1', 'r2', 'r3'))) + '</worldbody></mujoco>'
    model = mujoco.MjModel.from_xml_string(xml)
    data = mujoco.MjData(model)
    world = SimpleNamespace(model=model, data=data, controllers={},
        physics_lock=threading.RLock(), render_lock=threading.RLock(),
        _render_thread_id=threading.get_ident())
    snapshots = []

    class Renderer:
        def update_scene(self, data, *, camera, scene_option):
            rid = camera.split('__')[0]
            snapshots.append((rid, camera_pose(world, world.controllers[rid])))

        def render(self):
            return np.full((2, 2, 3), len(snapshots), dtype=np.uint8)

    world.renderer = Renderer()
    world._render_rgb_direct = MethodType(MultiMasterPiProductionV2._render_rgb_direct, world)
    for i, rid in enumerate(('r1', 'r2', 'r3')):
        robot = MasterPiDynamicsV2.__new__(MasterPiDynamicsV2)
        robot.model, robot.data, robot.robot_cam_cid = model, data, i
        robot.width, robot.height, robot.renderer = 640, 480, None
        robot._n = lambda name, rid=rid: rid+'__'+name
        robot._robot_sensor_scene_option = None
        robot._robot_fisheye_map = None
        robot._configure_measured_robot_camera()
        world.controllers[rid] = robot
    mujoco.mj_forward(model, data)
    return world, snapshots


def test_first_render_camera_pose_equals_s2_and_remains_bound():
    from sim.s2_realism_camera_binding import bind_camera
    s2, s2_at_render = model_world()
    s3, s3_at_render = model_world()
    assert not np.allclose(s3.model.cam_pos[0], v3.POSITION_M)
    for controller in s2.controllers.values():
        bind_camera(controller)
    recorded = []
    attach(s3, camera_binding='v3_persistent_v1', audit=lambda rid, row: recorded.append((rid, row)))
    for repeat in range(2):
        for rid in s3.controllers:
            # Simulate the constructor/reset refresh followed by a first render.
            s2.controllers[rid]._configure_measured_robot_camera()
            s3.controllers[rid]._configure_measured_robot_camera()
            expected_rgb = s2._render_rgb_direct(s2.controllers[rid], 'robot_cam')
            rgb = s3._render_rgb_direct(s3.controllers[rid], 'robot_cam')
            assert np.array_equal(rgb, expected_rgb)
            name, row = recorded[-1]
            assert name == rid and row['render_index'] == repeat
            assert row['local_position_m'] == pytest.approx(v3.POSITION_M, abs=1e-14)
            assert row['local_quat_wxyz'] == pytest.approx(v3.QUAT_WXYZ, abs=1e-14)
            assert {k: v for k, v in row.items() if k not in ('robot_id', 'render_index')} == s2_at_render[-1][1]
            assert s2_at_render[-1] == s3_at_render[-1]
    assert len(recorded) == 6
    assert recorded[0][1]['world_position_m'] != recorded[1][1]['world_position_m']


def test_physical_host_refuses_diagnostic_extrinsic_before_construction(tmp_path):
    from sim.zone_s3_no_prior import PhysicsBackend
    with pytest.raises(ValueError, match='offline diagnostic only'):
        PhysicsBackend({'controller_config': {'options': {
            'recorded_camera_mount': 'legacy_centered_replay_v1'}}}, tmp_path, seed=14201)
