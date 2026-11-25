"""Native scene and stationary camera controls for the R1 acceptance check."""
import math

import mujoco

from harness import overhead_v1 as overhead
from harness.approach_survey_v1 import FAR_POSTURE
from rooms3.maps import ROBOTS
from rooms3.runtime import calibration_file
from scripts.handover_world import World
from sim import masterpi_camera_review_v3 as camera
from sim.camera_robot_port import CameraRobotPort
from sim.masterpi_dynamics_v2 import load_fitted_hardware
from sim.multi_masterpi_production import MultiMasterPiProductionV2


class CameraRig:
    # Reuse the frozen camera paths, including JPEG quality, fisheye remap and ceiling decoder.
    robot = World.robot
    positions = World.positions
    actual_xy = World.actual_xy
    actual_pose = World.actual_pose

    def __init__(self, bundle, scene, stack):
        self.model = mujoco.MjModel.from_xml_path(str(bundle / "scene.xml"))
        self.data = mujoco.MjData(self.model)
        robots = [self.model.body(i).name for i in range(self.model.nbody)
                  if (self.model.body(i).name or "").endswith("__robot")]
        if self.model.neq or set(robots) != {r + "__robot" for r in ROBOTS}:
            raise ValueError("expected three complete robot trees and zero equality constraints")
        self.seed, self.dynamics = scene["source"]["seed"], {}
        calibration = calibration_file()
        if not calibration.is_file():
            raise FileNotFoundError(calibration)
        self.calibration_parameters, self.calibration_status = load_fitted_hardware(calibration)
        self.physical_params = {"servo6_center_pwm": 1500., **self.calibration_parameters}
        self.width, self.height = 640, 480
        self.observer_width, self.observer_height = overhead.WIDTH, overhead.HEIGHT
        self.renderer = mujoco.Renderer(self.model, self.height, self.width)
        stack.callback(self.renderer.close)
        self.observer_renderer = mujoco.Renderer(self.model, self.observer_height, self.observer_width)
        stack.callback(self.observer_renderer.close)
        self.controllers = {rid: MultiMasterPiProductionV2._bind_controller(self, rid, i)
                            for i, rid in enumerate(ROBOTS)}
        self.pwm = {rid: dict(FAR_POSTURE) for rid in ROBOTS}
        for controller in self.controllers.values():
            self.model.cam_pos[controller.robot_cam_cid] = camera.POSITION_M
            self.model.cam_quat[controller.robot_cam_cid] = camera.QUAT_WXYZ
            controller.set_servo_pulses(FAR_POSTURE, forward_only=True)
        self.ports = {rid: CameraRobotPort(self, rid) for rid in ROBOTS}
        self.reader = overhead.OverheadReader()
        self.ticks = round(.1 / self.model.opt.timestep)
        if not math.isclose(self.ticks * self.model.opt.timestep, .1, abs_tol=1e-9):
            raise ValueError("physics timestep must divide the 10 Hz control tick")

    def wrist(self, rid):
        return World.frame(self, rid)

    def tick(self, rows):
        for rid, row in rows.items():
            if any(row["wheels"]):
                raise ValueError("FIX4 camera check must stop before approach driving")
            for servo, pulse in row["pwm"].items():
                servo = int(servo)
                if self.pwm[rid][servo] != pulse:
                    action = ({"kind": "look", "pan_pulse": pulse} if servo == 6 else
                              {"kind": "arm", "servo_id": servo, "pulse": pulse})
                    self.ports[rid].apply(action, float(self.data.time))
                    self.pwm[rid][servo] = pulse
        for _ in range(self.ticks):
            for port in self.ports.values():
                port.tick(float(self.data.time))
            mujoco.mj_step(self.model, self.data)
        mujoco.mj_forward(self.model, self.data)
