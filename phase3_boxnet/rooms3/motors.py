"""Three-room bindings for the frozen hand-over grasp, drive and release stages."""
import copy
import io
import json
import math

import mujoco
import numpy as np
from PIL import Image

from handover import criteria, layout
from handover.records import StopTrial
from harness import grasp_act_contract as contract, robot_tags_v1 as tags
from harness.approach_survey_v1 import SurveyApproach
from harness.approach_survey_v1_parts import approach_core, ground_projection
from harness.handover_policy import MagnifiedMarkers, Policy
from rooms3 import board
from rooms3.camera_rig import CameraRig
from rooms3.check_camera import absolute
from rooms3.maps import ROBOTS
from rooms3.steps import release_held
from scripts.handover_world import World
from sim.masterpi_drive_friction_v7 import DriveParameters


class Record:
    def __init__(self, world, out, stack):
        self.world, self.out, self.seq = world, out, 0
        self.events = stack.enter_context((out / "events.jsonl").open("x", buffering=1))
        self.controls = stack.enter_context((out / "controls.jsonl").open("x", buffering=1))

    @property
    def now(self):
        return float(self.world.data.time)

    def event(self, name, **fields):
        row = dict(seq=self.seq, sim_s=self.now, event=name, **fields)
        self.seq += 1
        self.events.write(json.dumps(row, allow_nan=False) + "\n")
        return row

    def observe(self, name, *, jpg=None, **fields):
        if jpg is not None:
            fields["frame"] = f"{self.seq:04d}-{name}.jpg"
            (self.out / fields["frame"]).write_bytes(jpg)
        return self.event(name, **fields)


class MotionWorld(CameraRig):
    wheels = World.wheels

    def __init__(self, bundle, scene, out, stack):
        super().__init__(bundle, scene, stack)
        self.scene, self.record = scene, Record(self, out, stack)
        self.drive, self.dt = DriveParameters(), self.model.opt.timestep
        self.wheel_state = {r: np.zeros(4, dtype=int) for r in ROBOTS}
        self.wheel_cmd = {r: (0.,) * 4 for r in ROBOTS}
        self.pwm = {r: {str(k): v for k, v in self.pwm[r].items()} for r in ROBOTS}
        self.fingers = {self.model.geom(r + "__" + side + "_finger").id: (r, i)
                        for r in ROBOTS for i, side in enumerate(("left", "right"))}
        self.cargo = {b["id"]: (self.model.body(b["id"]).id, self.model.geom(b["id"] + "_geom").id)
                      for b in scene["boxes"]}
        self.base_xy = {r: self.data.qpos[c.base_qadr:c.base_qadr + 2] for r, c in self.controllers.items()}
        self.min_margin = {r: math.inf for r in ROBOTS}
        self.substeps = self.loose_ticks = 0
        self.carrying = self.grasping = self.tracked = None
        self.check_rooms()

    def frame(self, rid=None):
        if rid:
            return World.frame(self, rid)
        self.observer_renderer.update_scene(self.data, camera="rooms3_overview")
        stream = io.BytesIO()
        Image.fromarray(self.observer_renderer.render()).save(stream, format="JPEG", quality=86)
        return stream.getvalue()

    def stop(self):
        for rid in ROBOTS:
            self.wheels(rid, (0.,) * 4)

    def check_rooms(self):
        for rid, (x, y) in self.base_xy.items():
            margin = float(layout.margin(self.scene["rooms"][rid]["bounds"], x, y))
            if not math.isfinite(margin) or margin <= 0:
                self.stop()
                self.record.event("room_limit", robot=rid, xy=[float(x), float(y)], substep=self.substeps)
                raise StopTrial("room_limit", "chassis centre reached its room boundary")
            self.min_margin[rid] = min(self.min_margin[rid], margin)

    def control(self, rid, row):
        self.tick({rid: row})

    def tick(self, rows):
        now = self.record.now
        self.record.controls.write(json.dumps({"sim_s": now, "rows": rows}, allow_nan=False) + "\n")
        for rid in ROBOTS:
            if rid not in rows:
                self.wheels(rid, (0.,) * 4)
                continue
            row = rows[rid]
            for servo, pulse in row["pwm"].items():
                if self.pwm[rid][servo] != pulse:
                    act = ({"kind": "look", "pan_pulse": pulse} if servo == "6" else
                           {"kind": "arm", "servo_id": int(servo), "pulse": pulse})
                    self.ports[rid].apply(act, now)
            self.pwm[rid] = dict(row["pwm"])
            wheels = row["wheels"]
            if any(wheels):
                x, y = self.base_xy[rid]
                rot = self.data.xmat[self.controllers[rid].robot_bid].reshape(3, 3)
                dx, dy = rot[:2, :2] @ [sum(wheels) / 4, (-wheels[0]+wheels[1]+wheels[2]-wheels[3]) / 4]
                bounds = self.scene["rooms"][rid]["bounds"]
                margin = layout.margin(bounds, x, y)
                if margin < .08 and layout.margin(bounds, x + .12*dx, y + .12*dy) < margin - 1e-8:
                    self.stop()
                    raise StopTrial("room_guard", "outward drive inside the 8 cm guard band")
        for i in range(self.ticks):
            for port in self.ports.values():
                port.tick(float(self.data.time))
            for rid, row in rows.items():
                command = tuple(w if i*self.dt < d-1e-10 else 0. for w, d in zip(row["wheels"], row["duration_s"]))
                self.wheels(rid, command)
            mujoco.mj_step(self.model, self.data)
            self.substeps += 1
            self.check_rooms()
        mujoco.mj_forward(self.model, self.data)
        if self.carrying:
            p = self.witness()
            loose = p["clearance_m"] < .006 and max(p["finger_n"][self.carrying]) < .05
            self.loose_ticks = self.loose_ticks + 1 if loose else 0
            if self.loose_ticks >= 3:
                self.record.event("carry_loss", robot=self.carrying, witness=p)
                raise StopTrial("carry_loss", "box on floor without finger contact for three ticks")

    def measure(self, name):
        body, geom = self.cargo[name]
        rotation = self.data.xmat[body].reshape(3, 3)
        x, y, z = self.data.xpos[body]
        velocity, force = np.zeros(6), np.zeros(6)
        mujoco.mj_objectVelocity(self.model, self.data, mujoco.mjtObj.mjOBJ_BODY, body, velocity, 0)
        forces = {r: [0., 0.] for r in ROBOTS}
        for i, contact in enumerate(self.data.contact):
            a, b = contact.geom1, contact.geom2
            finger = self.fingers.get(b if a == geom else a if b == geom else -1)
            if finger is not None:
                mujoco.mj_contactForce(self.model, self.data, i, force)
                forces[finger[0]][finger[1]] += abs(float(force[0]))
        return {"body": name, "body_id": body, "sim_s": self.record.now, "x": float(x), "y": float(y), "z": float(z),
                "clearance_m": float(z - abs(rotation[2]) @ self.model.geom_size[geom]),
                "tilt_deg": math.degrees(math.acos(np.clip(rotation[2, 2], -1, 1))),
                "yaw": math.atan2(rotation[1, 0], rotation[0, 0]),
                "speed_m_s": float(np.linalg.norm(velocity[3:])), "finger_n": forces}

    def witness(self):
        if self.tracked:
            return self.measure(self.tracked)
        # Lock identity by actual bilateral lift for the whole witness window. No mapped start is consulted.
        p = max((self.measure(name) for name in self.cargo), key=lambda p: min(p["finger_n"][self.grasping]))
        if criteria.held(p, self.grasping):
            self.tracked = p["body"]
        return p


class MovePolicy(Policy):
    def __init__(self, world, actor, rid, track):
        self.w, self.rec, self.actor = world, world.record, actor
        self.scene, self.track = world.scene, track
        self.kind = {"red": "red", "blue": "cyan"}[track["colour"]]
        self.stage, self.zoom_reader, self.seen = "pick", None, False
        room = self.scene["rooms"][rid]
        self.trial = {"trial": self.rec.seq, "donor": rid, "receiver_sign": room["sign"], "starts": {}}

    def box_survey(self, origin, role):
        def select(entries):
            matches = [(math.dist(absolute(origin, e["x"], e["y"]), self.track["xy"]), i)
                       for i, e in enumerate(entries) if e["kind"] == self.kind
                       and board.location(self.scene, *absolute(origin, e["x"], e["y"]))[0] == self.trial["donor"]]
            if matches:
                distance, i = min(matches)
                if distance <= approach_core.POS_GATE_M:
                    return i
            return None
        return SurveyApproach(contract, select, survey_fast=True, align_fast=True, approach_visual=True)

    def grasp(self, role, attempt):
        self.w.grasping, self.w.tracked = self.trial[role], None
        return super().grasp(role, attempt)

    def drive(self, rid, target, face=None, reverse=False):
        # Same measured heading, pulse sizes and budgets as Policy.drive, in this room's coordinate frame.
        if layout.margin(self.scene["rooms"][rid]["bounds"], *target) < .10:
            raise StopTrial(self.stage, "navigation target outside home driving area")
        for _ in range(230):
            x, y, heading = self.pose(rid)
            distance = math.dist((x, y), target)
            arrived = distance <= .027
            if arrived and face is None:
                return
            desired = face if arrived else math.atan2(target[1]-y, target[0]-x) + (math.pi if reverse else 0)
            error = math.remainder(desired - heading, 2*math.pi)
            if abs(error) > (.065 if arrived else .13):
                speed = math.copysign(.35, error)
                wheels = (-speed, speed, -speed, speed)
                count, duration = max(1, min(4, round(abs(error)/.0885))), .065 if abs(error) < .11 else .1
            elif arrived:
                return
            else:
                wheels = (-.35 if reverse else .35,) * 4
                count, duration = max(1, min(4, int(distance/.014))), .1
            for _ in range(count):
                self.w.control(rid, self.row(rid, wheels, duration))
        raise StopTrial(self.stage, "station not reached within the navigation budget")

    def station(self, rid, u, v, degrees=None, *, reverse=False):
        # The inherited find_sign starts with a survey station. The final release stand comes from wrist RGB.
        if self.stage != "sign_seen":
            raise ValueError("unexpected sign survey station")
        home = self.scene["rooms"][rid]["start"]
        self.drive(rid, home[:2], home[2], reverse)

    def prepare_pick(self, rid):
        if self.track["pad"]:
            pad = self.scene["pads"][self.track["pad"]]
            x, y = pad["xy"]
            inward = math.copysign(1, self.scene["rooms"][rid]["start"][0] - x)
            self.drive(rid, [x + inward*layout.SCAN_STAND, y], math.pi if inward > 0 else 0.)
        self.trial["starts"][rid] = self.pose(rid)


class NativeBackend:
    identity_radius = approach_core.POS_GATE_M

    def __init__(self, world):
        self.w, self.scene, self.actor = world, world.scene, None
        self.signs = tags.TagReader(ground_projection.K, ground_projection.D)
        self.zoom = copy.copy(world.reader)
        self.zoom.detector = MagnifiedMarkers(world.reader.detector)
        self.policy = None

    def referee(self):
        witnesses = {name: self.w.measure(name) for name in self.w.cargo}
        return board.referee_board(self.scene, witnesses), witnesses

    def observe(self):
        poses = self.w.positions()
        if set(poses) != set(ROBOTS):
            for rid, pose in self.zoom.read(self.w.last_ceiling_frames).items():
                poses.setdefault(rid, pose)
        views = {r: {"pose": poses.get(r), "entries": [], "sign_ids": [], "evidence": {}} for r in ROBOTS}
        surveys = {r: SurveyApproach(contract, lambda entries: None, survey_fast=True) for r in ROBOTS}
        for _ in range(100):
            rows = {}
            for rid, survey in surveys.items():
                if survey.arrived:
                    continue
                jpg = self.w.frame(rid) if survey.needs_frame() else b""
                view = views[rid]
                if jpg and not view["sign_ids"]:
                    wanted = self.scene["rooms"][rid]["sign"]
                    for reader in (self.signs.read, self.signs.read_signs_raw):
                        if any(tag.get("sign") == wanted for tag in reader(jpg)):
                            frame = f"{self.w.record.seq:04d}-{rid}-board-sign.jpg"
                            (self.w.record.out / frame).write_bytes(jpg)
                            view.update(sign_ids=[wanted], sign_frame=frame)
                            break
                rows[rid] = survey.step(jpg, self.w.record.now)
            if not rows:
                break
            self.w.tick(rows)
        for rid, survey in surveys.items():
            if survey.entries is None:
                raise RuntimeError("board survey did not finish")
            views[rid].update(entries=survey.entries, evidence=dict(survey.survey.evidence))
        self.w.record.event("board_survey", views=views)
        return board.camera_board(self.scene, views), views

    def prepare(self, rid, track):
        self.policy = MovePolicy(self.w, self.actor, rid, track)
        self.policy.prepare_pick(rid)
        return self.policy

    def move(self, rid, track, dest):
        if self.actor is None:
            raise RuntimeError("native moves require the frozen hand-over actor")
        p = self.prepare(rid, track)
        try:
            p.pick("donor")
        except StopTrial as exc:
            if exc.stage == "donor_pick":
                raise StopTrial("grasp_failed", str(exc)) from exc
            raise
        body = self.w.tracked
        self.w.loose_ticks = 0
        self.w.record.event("carry_start", robot=rid, body=body, destination=dest)
        p.stage = "carry"
        if dest == "target":
            p.find_sign(rid)
        else:
            pad = self.scene["pads"][f"{rid}_{dest}"]
            x, y = pad["xy"]
            outward = math.copysign(1, x - self.scene["rooms"][rid]["start"][0])
            face = 0. if outward > 0 else math.pi
            p.drive(rid, [x - outward*.70, y], face)
            p.drive(rid, [x - outward*layout.RELEASE_STAND, y], face)
        release_held(p, rid)
        self.w.tracked = self.w.grasping = None
        # Back away and restore the home survey heading for the next measured board.
        home = self.scene["rooms"][rid]["start"]
        try:
            p.drive(rid, home[:2], home[2], reverse=True)
        except StopTrial as exc:
            if exc.stage == "room_limit":
                raise
            self.w.stop()
            self.w.record.event("return_home_failed", robot=rid, reason=str(exc))
        return body

    def recover(self, rid):
        self.w.stop()
        self.w.carrying = None
        # Open in place after a failure. Let gravity and contacts determine the next board.
        self.policy.idle(rid, 12, {**self.w.pwm[rid], "1": 2000})
        self.w.record.event("recovery_open", robot=rid, body=self.w.tracked)
        self.w.tracked = self.w.grasping = None
