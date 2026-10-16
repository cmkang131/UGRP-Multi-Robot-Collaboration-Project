"""v110 runtime camera binding: controller mount refresh must retain explicit v3."""
import mujoco
import numpy as np
from sim import s2_realism as v109
from sim import masterpi_camera_review_v3 as camera
from sim.masterpi_drive_friction_v7 import build_world


def bind_camera(controller):
    def apply():
        controller.model.cam_pos[controller.robot_cam_cid] = np.asarray(camera.POSITION_M)
        controller.model.cam_quat[controller.robot_cam_cid] = np.asarray(camera.QUAT_WXYZ)
        mujoco.mj_forward(controller.model, controller.data)
    original = controller._configure_measured_robot_camera

    def configure():
        original()  # preserve the inherited measured K/D and resolution
        apply()

    controller._configure_measured_robot_camera = configure
    controller._sync_real_camera_mount = apply
    apply()


def bound_world(*args, **kwargs):
    world = build_world(*args, **kwargs)
    try:
        with world.physics_lock:
            for controller in world.controllers.values():
                bind_camera(controller)
        return world
    except Exception:
        world.close()
        raise


class PhysicsBackend(v109.PhysicsBackend):
    def __init__(self, *args, **kwargs):
        # Constructor-scoped factory injection in this single-simulation process.
        # Restore immediately, so the archived v109 path still reproduces its refusal.
        original = v109.build_world
        try:
            v109.build_world = bound_world
            super().__init__(*args, **kwargs)
        finally:
            v109.build_world = original
