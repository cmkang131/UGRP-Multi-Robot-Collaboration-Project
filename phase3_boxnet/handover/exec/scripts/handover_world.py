"""Single-threaded, local physics and cameras for the explicitly selected handover scene."""
from contextlib import ExitStack
import hashlib
import io
import math

import cv2
import mujoco
import numpy as np
from PIL import Image

from harness import overhead_v1 as overhead
from sim.camera_robot_port import CameraRobotPort
from sim.masterpi_drive_friction_v7 import DriveParameters
from sim.masterpi_dynamics_v2 import load_fitted_hardware
from sim.multi_masterpi_production import MultiMasterPiProductionV2
from sim import masterpi_camera_review_v3 as camera
from sim.handover_scene import stock_xml
from handover import criteria, layout
from handover.records import StopTrial


FAR = {"1": 2000, "3": 740, "4": 2320, "5": 1320, "6": 1500}
IDS = ("r1", "r2")


class World:
    def __init__(self, trial, record, stack: ExitStack):
        self.trial, self.record = trial, record
        self.seed = trial["seed"]
        self.drive = DriveParameters()
        hw, self.calibration_status = load_fitted_hardware()
        self.calibration_parameters = hw
        self.physical_params = {"servo6_center_pwm": 1500., **hw}
        self.dynamics = {}
        xml = stock_xml(trial, record.out, hw, self.drive)
        with (record.out / "scene.xml").open("x") as stream:
            stream.write(xml)
        self.model = mujoco.MjModel.from_xml_string(xml)
        if self.model.neq or sorted(self.model.body(i).name for i in range(self.model.nbody)
                if (self.model.body(i).name or "").endswith("__robot")) != ["r1__robot", "r2__robot"]:
            raise ValueError("expected exactly two robot trees and zero equality constraints")
        self.data = mujoco.MjData(self.model)
        self.width, self.height = 640, 480
        self.observer_width, self.observer_height = overhead.WIDTH, overhead.HEIGHT
        self.renderer = mujoco.Renderer(self.model, self.height, self.width)
        stack.callback(self.renderer.close)
        self.observer_renderer = mujoco.Renderer(self.model, self.observer_height, self.observer_width)
        stack.callback(self.observer_renderer.close)
        self.controllers = {r: MultiMasterPiProductionV2._bind_controller(self, r, i) for i, r in enumerate(IDS)}
        self.pwm = {r: dict(FAR) for r in IDS}
        for c in self.controllers.values():
            self.model.cam_pos[c.robot_cam_cid] = camera.POSITION_M
            self.model.cam_quat[c.robot_cam_cid] = camera.QUAT_WXYZ
            c.set_servo_pulses({int(k): v for k, v in FAR.items()}, forward_only=True)
        self.ports = {r: CameraRobotPort(self, r) for r in IDS}
        self.wheel_state = {r: np.zeros(4, dtype=int) for r in IDS}
        self.wheel_cmd = {r: (0.,)*4 for r in IDS}
        self.base = [self.data.qpos[c.base_qadr:c.base_qadr+2] for c in self.controllers.values()]
        self.box = self.model.body(layout.BODY).id
        self.geom = self.model.geom(layout.BODY+"_geom").id
        self.fingers = {self.model.geom(r+"__"+s+"_finger").id: (r, i)
                        for r in IDS for i, s in enumerate(("left", "right"))}
        self.reader = overhead.OverheadReader()
        self.dt = float(self.model.opt.timestep)
        self.carrying, self.loose_ticks = None, 0
        self.last_held = True  # The lift witness is valid when each carry begins.
        self.ticks = round(.1 / self.dt)
        if not math.isclose(self.ticks * self.dt, .1, abs_tol=1e-9):
            raise ValueError("physics timestep must divide the executor's 0.1 s period")
        self.sample()
        with (record.out / "initial-overview.jpg").open("xb") as stream:
            stream.write(self.frame())
        record.event("world_ready", body=layout.BODY, body_id=self.box, dt=self.dt, welds=0,
                     controllers=list(self.controllers), mujoco_version=mujoco.__version__,
                     xml_sha256=hashlib.sha256(xml.encode()).hexdigest(), frame="initial-overview.jpg")

    def robot(self, rid):
        return self.controllers[rid]

    def sample(self):
        a, b = self.base
        self.record.sample(float(self.data.time), float(a[0]), float(a[1]), float(b[0]), float(b[1]))

    def wheels(self, rid, command):
        if command != self.wheel_cmd[rid]:
            effective, state = self.drive.command_step(command, self.wheel_state[rid])
            self.data.ctrl[self.controllers[rid].wheel_act] = self.drive.torque_cap_nm * effective
            self.wheel_state[rid], self.wheel_cmd[rid] = state, command

    def stop(self):
        for r in IDS:
            self.wheels(r, (0.,)*4)

    def control(self, rid, row):
        # The same independent wheel deadlines, PWM slew and 10 Hz control cadence as run_grasp_act_student.
        for other in IDS:
            if other != rid:
                self.wheels(other, (0.,)*4)
        port = self.ports[rid]
        t = float(self.data.time)
        for s, pulse in row["pwm"].items():
            if pulse != self.pwm[rid][s]:
                port.apply({"kind": "look", "pan_pulse": pulse} if s == "6" else
                           {"kind": "arm", "servo_id": int(s), "pulse": pulse}, t)
        self.pwm[rid] = dict(row["pwm"])
        wheels, durations = row["wheels"], row["duration_s"]
        if any(wheels):
            # The referee can stop the experiment. It never adjusts a pose or repairs an attempted grasp.
            c = self.controllers[rid]
            x, y = self.data.qpos[c.base_qadr:c.base_qadr+2]
            rot = self.data.xmat[c.robot_bid].reshape(3, 3)
            forward, left = sum(wheels)/4, (-wheels[0]+wheels[1]+wheels[2]-wheels[3])/4
            dx, dy = rot[:2,:2] @ [forward, left]
            bounds = layout.room(self.trial, rid)
            clearance = layout.margin(bounds, x, y)
            if clearance < .08 and layout.margin(bounds, x+.12*dx, y+.12*dy) < clearance-1e-8:
                self.stop()
                self.record.event("room_guard", robot=rid, xy=[float(x), float(y)], clearance_m=float(clearance))
                raise StopTrial("room_guard", "outward drive inside 8 cm guard band")
        try:
            for i in range(self.ticks):
                for active_port in self.ports.values():
                    active_port.tick(float(self.data.time))
                self.wheels(rid, tuple(w if i*self.dt < d-1e-10 else 0. for w, d in zip(wheels, durations)))
                mujoco.mj_step(self.model, self.data)
                self.sample()
        finally:
            self.record.flush()
        mujoco.mj_forward(self.model, self.data)
        if self.carrying:
            p = self.witness()
            held = criteria.held(p, self.carrying)
            if held != self.last_held:
                self.record.observe("carry_hold_changed", robot=self.carrying, held=held, pose=p,
                                    chassis_pose=self.actual_pose(self.carrying), pwm=dict(self.pwm[self.carrying]))
                self.last_held = held
            loose = p["clearance_m"] < .006 and max(p["finger_n"][self.carrying]) < .05
            self.loose_ticks = self.loose_ticks+1 if loose else 0
            if self.loose_ticks >= 3:
                stage = "release" if self.carrying == self.trial["donor"] else "set_down"
                self.record.event("carry_loss", robot=self.carrying, pose=p, stage=stage)
                raise StopTrial(stage, "box on floor without finger contact for three carry ticks")
        else:
            self.loose_ticks = 0
            self.last_held = True

    def frame(self, rid=None):
        if rid:
            c = self.controllers[rid]
            self.renderer.update_scene(self.data, camera=c.robot_cam_cid, scene_option=c._robot_sensor_scene_option)
            pixels = cv2.remap(self.renderer.render(), *c._robot_fisheye_map, cv2.INTER_LINEAR)
        else:
            self.observer_renderer.update_scene(self.data, camera="handover_overview")
            pixels = self.observer_renderer.render()
        buf = io.BytesIO()
        # Same encoder and wrist/overview qualities as the production world.
        Image.fromarray(pixels).save(buf, format="JPEG", quality=82 if rid else 86)
        return buf.getvalue()

    def positions(self):
        pictures = {}
        for name, _ in overhead.CAMERAS:
            self.observer_renderer.update_scene(self.data, camera=name)
            pictures[name] = self.observer_renderer.render().copy()
        self.last_ceiling_frames = pictures  # The exact inputs to this read, including every tile.
        return self.reader.read(pictures)

    def actual_xy(self, rid):
        c = self.controllers[rid]
        return self.data.qpos[c.base_qadr:c.base_qadr+2].tolist()

    def actual_pose(self, rid):
        """Referee evidence synchronized to the last physics step."""
        rot = self.data.xmat[self.controllers[rid].robot_bid].reshape(3, 3)
        return [*self.actual_xy(rid), math.atan2(rot[1, 0], rot[0, 0])]

    def witness(self):
        rot = self.data.xmat[self.box].reshape(3, 3)
        x, y, z = self.data.xpos[self.box]
        velocity = np.zeros(6)
        mujoco.mj_objectVelocity(self.model, self.data, mujoco.mjtObj.mjOBJ_BODY, self.box, velocity, 0)
        forces = {r: [0., 0.] for r in IDS}
        force = np.zeros(6)
        for i, contact in enumerate(self.data.contact):
            a, b = int(contact.geom1), int(contact.geom2)
            finger = self.fingers.get(b if a == self.geom else a if b == self.geom else -1)
            if finger:
                mujoco.mj_contactForce(self.model, self.data, i, force)
                forces[finger[0]][finger[1]] += abs(float(force[0]))
        return {"body": layout.BODY, "body_id": self.box, "sim_s": float(self.data.time),
                "x": float(x), "y": float(y), "z": float(z),
                "yaw": math.atan2(rot[1,0], rot[0,0]), "tilt_deg": math.degrees(math.acos(np.clip(rot[2,2], -1, 1))),
                "clearance_m": float(z - abs(rot[2]) @ self.model.geom_size[self.geom]),
                "speed_m_s": float(np.linalg.norm(velocity[3:])), "finger_n": forces}
