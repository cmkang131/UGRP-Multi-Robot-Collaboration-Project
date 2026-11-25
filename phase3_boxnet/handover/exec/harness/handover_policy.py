"""Fixed handover script's motor and perception skills. No planner or service client."""
import copy
import math

import numpy as np
from PIL import Image

from harness import grasp_act_contract as contract, robot_tags_v1 as tags
from harness.approach_survey_v1 import SurveyApproach
from harness.grasp_act_policy import ChunkExecutor
from harness.grasp_act_rollout import GraspTransitionRule, OwnHistory
from harness.release_code_v1 import ReleaseCodeV1
from scripts.run_grasp_act_student import CARRY_ARM_ROWS, CARRY_FAR_POSTURE, carry_pwm
from handover import criteria, layout
from handover.records import StopTrial


POSE_RECHECKS = 12
PAN_ON_RECHECK = 8


class MagnifiedMarkers:
    """Run the same ArUco decoder on overlapping 2x crops and return native pixel corners."""

    def __init__(self, detector):
        self.detector = detector

    def detectMarkers(self, gray):
        def halves(size):
            mid = size // 2
            # A nominal top card spans 17 px (24 px corner to corner) in the ceiling image.
            return ((0, min(size, mid + 24)), (max(0, mid - 24), size))

        corners, ids = [], []
        height, width = gray.shape
        for y0, y1 in halves(height):
            for x0, x1 in halves(width):
                crop = Image.fromarray(gray[y0:y1, x0:x1])
                zoom = crop.resize((2 * crop.width, 2 * crop.height), Image.Resampling.BICUBIC)
                quads, numbers, _ = self.detector.detectMarkers(np.asarray(zoom))
                if numbers is not None:
                    # Invert the resize about pixel centres before the calibrated reader sees the corners.
                    corners.extend((q + .5) / 2 - .5 + (x0, y0) for q in quads)
                    ids.extend(numbers.ravel())
        return corners, np.asarray(ids, dtype=np.int32).reshape(-1, 1), ()


def absolute(pose, x, y):
    c, s = math.cos(pose[2]), math.sin(pose[2])
    return [pose[0] + c*x - s*y, pose[1] + s*x + c*y]


class Policy:
    def __init__(self, world, actor, *, station_tilt="strict"):
        self.w, self.rec, self.trial, self.actor = world, world.record, world.trial, actor
        self.station_tilt = station_tilt
        self.kind = "cyan" if self.trial["colour"] == "blue" else "red"
        self.seen = False
        self.stage = "donor_pick"
        self.zoom_reader = None

    def photo(self, label, jpg=None):
        filename = f"{self.rec.seq:04d}-{label}.jpg"
        with (self.rec.out / filename).open("xb") as stream:
            stream.write(self.w.frame() if jpg is None else jpg)
        return filename

    def row(self, rid, wheels=(0., 0., 0., 0.), duration=.1, pwm=None):
        return {"t": self.rec.now, "wheels": list(wheels), "duration_s": [duration if w else 0. for w in wheels],
                "pwm": dict(self.w.pwm[rid] if pwm is None else pwm)}

    def idle(self, rid, times=1, pwm=None):
        for _ in range(times):
            self.w.control(rid, self.row(rid, pwm=pwm))

    def ceiling_evidence(self, label):
        files = {}
        for camera, rgb in self.w.last_ceiling_frames.items():
            name = f"{self.rec.seq:04d}-{label}-{camera}.png"
            with (self.rec.out / name).open("xb") as stream:
                Image.fromarray(rgb).save(stream, format="PNG", compress_level=1)
            files[camera] = name
        return files

    def pose(self, rid):
        observed = self.w.positions().get(rid)
        if observed is not None:
            return observed

        started = self.rec.now
        lost = self.rec.event("overhead_lost", robot=rid, stage=self.stage, pwm=dict(self.w.pwm[rid]),
                              ceiling_frames=self.ceiling_evidence("lost"))
        if self.zoom_reader is None:
            self.zoom_reader = copy.copy(self.w.reader)
            self.zoom_reader.detector = MagnifiedMarkers(self.w.reader.detector)
        interval = dict(robot=rid, stage=self.stage, lost_seq=lost["seq"], start_sim_s=started)
        for missed in range(1, POSE_RECHECKS + 1):
            pwm = self.w.pwm[rid]
            if missed == PAN_ON_RECHECK and all(pwm[k] == CARRY_FAR_POSTURE[k] for k in ("3", "4", "5")):
                # Only swivel an already raised travel arm. Keep its grip and let the pan settle.
                pan = 1850 if pwm["6"] == 1500 else 1500
                interval["pan_pwm"] = pan
                self.idle(rid, 6, {**pwm, "6": pan})
            else:
                self.idle(rid)
            observed = self.w.positions().get(rid)
            method = "native"
            if observed is None:
                observed = self.zoom_reader.read(self.w.last_ceiling_frames).get(rid)
                method = "magnified"
            if observed is not None:
                self.rec.event("overhead_recovered", **interval, duration_s=self.rec.now - started,
                               missed_frames=missed, method=method, chassis_pose=observed,
                               ceiling_frames=self.ceiling_evidence("recovered"))
                return observed
        reason = f"ceiling camera lost {rid}'s card for {POSE_RECHECKS + 1} observations"
        self.rec.event("overhead_timeout", **interval, duration_s=self.rec.now - started,
                       missed_frames=POSE_RECHECKS + 1, reason=reason,
                       ceiling_frames=self.ceiling_evidence("timeout"))
        raise StopTrial(self.stage, reason)

    def drive(self, rid, target, face=None, reverse=False):
        if layout.margin(layout.room(self.trial, rid), *target) < .10:
            raise StopTrial(self.stage, "measured navigation target is outside the home driving area")
        # Re-measure after no more than four calibrated pulses. The heading and target use metres/radians.
        for _ in range(230):
            x, y, heading = self.pose(rid)
            distance = math.dist((x, y), target)
            arrived = distance <= .027
            if arrived and face is None:
                return
            desired = face if arrived else math.atan2(target[1]-y, target[0]-x) + (math.pi if reverse else 0)
            error = math.remainder(desired-heading, 2*math.pi)
            if abs(error) > (.065 if arrived else .13):
                speed = math.copysign(.35, error)
                wheels = (-speed, speed, -speed, speed)
                count = max(1, min(4, round(abs(error)/.0885)))
                duration = .065 if abs(error) < .11 else .1
            elif arrived:
                return
            else:
                wheels = (-.35 if reverse else .35,)*4
                count = max(1, min(4, int(distance/.014)))
                duration = .1
            for _ in range(count):
                self.w.control(rid, self.row(rid, wheels, duration))
        raise StopTrial(self.stage, "station not reached within the navigation budget")

    def station(self, rid, u, v, degrees=None, *, reverse=False):
        direction = self.trial["direction"]
        self.drive(rid, layout.xy(direction, u, v),
                   None if degrees is None else layout.yaw(direction, degrees), reverse)

    def eligible_box(self, origin, role, entry):
        if entry["kind"] != self.kind:
            return False
        x, y = absolute(origin, entry["x"], entry["y"])
        if role == "receiver":
            return math.hypot(x, y) <= .22
        return layout.uv(self.trial["direction"], x, y)[0] < -.25

    def box_survey(self, origin, role):
        def select(entries):
            return next((i for i, entry in enumerate(entries) if self.eligible_box(origin, role, entry)), None)

        return SurveyApproach(contract, select, survey_fast=True, align_fast=True, approach_visual=True)

    def approach(self, rid, role, attempt):
        origin = self.pose(rid)
        approach = self.box_survey(origin, role)
        history = OwnHistory(rid, f"gate-{self.trial['trial']}-{attempt}", self.row(rid))
        for tick in range(2200):
            jpg = self.w.frame(rid)
            if tick == 0:
                first_frame = jpg
            history.observe(self.rec.now, jpg, skill="grasp", object_kind=self.kind, role="west")
            row = approach.step(jpg, self.rec.now)
            if role == "receiver" and not self.seen:
                # A single accepted floor projection in this RGB frame; selection itself needs two sightings.
                for track in approach.survey._tracks:
                    x, y = track["points"][-1]
                    if self.eligible_box(origin, role, {"kind": track["kind"], "x": x, "y": y}):
                        self.seen = True
                        self.rec.event("receiver_seen", robot=rid, kind=self.kind, observed_xy=absolute(origin, x, y),
                                       frame=self.photo("receiver-first-sees", jpg))
                        self.stage = "receiver_pick"
                        break
            if row is not None:
                self.w.control(rid, row)
                history.issue(row)
            if approach.arrived:
                break
        alignment = next((r for r in reversed(approach.alignment_trace()) if "aggregate" in r), {})
        self.rec.event("approach_end", robot=rid, attempt=attempt, reason=approach.reason,
                       alignment=approach.align_reason, selected=approach.index, entries=approach.entries,
                       survey_counts=dict(approach.survey.evidence), alignment_measurement=alignment.get("aggregate"),
                       alignment_sim_s=alignment.get("t"), face_check=alignment.get("face_check"),
                       first_wrist_frame=self.photo(role+"-first-wrist", first_frame))
        if not approach.arrived or approach.index is None or approach.box_not_seen:
            stage = "receiver_seen" if role == "receiver" and not self.seen else role+"_pick"
            raise StopTrial(stage, "own-camera approach could not hand off a selected box to ACT")
        history.clock = contract.IssuedClock()
        history.clock.skill = ("grasp", self.kind, "west", "none")
        history.clock.started = self.rec.now - approach.approach_seconds()
        return history

    def grasp(self, role, attempt):
        rid = self.trial[role]
        history = self.approach(rid, role, attempt)
        self.rec.event("attempt_start", robot=rid, attempt=attempt)
        actor = ChunkExecutor(self.actor.predict)
        rule = GraspTransitionRule()
        window = []
        for _ in range(900):
            now = self.rec.now
            obs, imgs, _ = history.observe(now, self.w.frame(rid), skill="grasp", object_kind=self.kind, role="west")
            row, _ = actor.step(obs, imgs)
            # As in the executor's rule-based ACT grasp, the learned done bit cannot end the grasp.
            actor.done_requested = False
            self.w.control(rid, row)
            history.issue(row)
            pose = self.w.witness()
            if criteria.held(pose, rid):
                window.append([self.rec.now, pose["clearance_m"], pose["tilt_deg"], *pose["finger_n"][rid]])
            else:
                window = []
            if rule.observe(now, row):
                break
        else:
            self.rec.event("grasp_attempt", robot=rid, attempt=attempt, outcome="miss", reason="ACT timeout")
            return False
        # Hold the issued end posture through the executor's 3.1 s settle window.
        for _ in range(31):
            self.idle(rid)
            pose = self.w.witness()
            if criteria.held(pose, rid):
                window.append([self.rec.now, pose["clearance_m"], pose["tilt_deg"], *pose["finger_n"][rid]])
            else:
                window = []
        success = bool(window) and window[-1][0] - window[0][0] >= layout.LIFT_SECONDS - 1e-7
        self.rec.event("grasp_attempt", robot=rid, attempt=attempt, outcome="lift" if success else "miss",
                       pose=pose, lift_samples=window, frame=self.photo(role+"-grasp"),
                       wrist_frame=self.photo(role+"-grasp-wrist", self.w.frame(rid)))
        return success

    def pick(self, role):
        rid = self.trial[role]
        self.stage = "receiver_seen" if role == "receiver" and not self.seen else role+"_pick"
        for attempt in (1, 2):
            if self.grasp(role, attempt):
                self.w.carrying = rid
                return
            if attempt == 1:
                self.idle(rid, 12, {"1": 2000, "3": 740, "4": 2320, "5": 1320, "6": 1500})
                if role == "receiver":
                    self.station(rid, layout.SCAN_STAND, 0, 180, reverse=True)
                else:
                    start = self.trial["starts"][rid]
                    self.drive(rid, start[:2], start[2], reverse=True)
        raise StopTrial(self.stage, "both grasp attempts failed")

    def release(self, role):
        rid = self.trial[role]
        name = "release" if role == "donor" else "set_down"
        self.stage = name
        carried = self.w.witness()
        held = criteria.held(carried, rid, ignore_tilt=self.station_tilt == "ignore")
        if not held or carried["tilt_deg"] > layout.TILT_TOL:
            self.rec.observe("held_tilted" if held else "station_hold_failed", stage=name, robot=rid, pose=carried,
                             chassis_pose=self.w.actual_pose(rid), pwm=dict(self.w.pwm[rid]))
        if not held:
            raise StopTrial(name, "box was no longer held at the release station")
        self.w.carrying = None
        self.rec.event(name+"_start", robot=rid, pose=carried, chassis=self.w.actual_xy(rid))
        replay = ReleaseCodeV1(contract, self.w.pwm[rid])
        detached = False
        for _ in range(len(replay.rows)):
            row, _ = replay.step(self.rec.now)
            self.w.control(rid, row)
            pose = self.w.witness()
            if not detached and criteria.free(pose):
                if row["pwm"]["1"] <= 1550:
                    raise StopTrial(name, "both fingers lost the box before the gripper opened")
                detached = True
                self.rec.event(name+"_open", robot=rid, pose=pose, frame=self.photo(name+"-open"),
                               wrist_frame=self.photo(name+"-open-wrist", self.w.frame(rid)))
        rest = []
        for _ in range(10):
            self.idle(rid)
            rest.append(self.w.witness())
        pose = rest[-1]
        self.rec.event(name, robot=rid, pose=pose, rest=rest, rows=replay.i,
                       sign_relative=layout.sign_relative(self.trial, pose["x"], pose["y"]),
                       pose_at_sign=layout.pose_at_sign(self.trial, pose),
                       frame=self.photo(name+"-settled"))
        if not detached or not all(criteria.resting(p) for p in rest):
            raise StopTrial(name, "release did not end detached and settled on the floor")
        if role == "donor" and not criteria.at_mark(self.trial, pose):
            raise StopTrial(name, "settled box missed the mark's position or orientation")
        if role == "receiver" and not criteria.at_sign(self.trial, pose):
            raise StopTrial(name, "settled box outside the receiver sign area")

    def find_sign(self, rid):
        from harness.approach_survey_v1_parts import ground_projection as projection
        reader = tags.TagReader(projection.K, projection.D)
        self.stage = "sign_seen"
        self.station(rid, .48, 0, 0, reverse=True)
        hold = dict(self.w.pwm[rid])
        far = carry_pwm(hold, 1.)
        for i in range(1, CARRY_ARM_ROWS+1):
            self.idle(rid, pwm=carry_pwm(hold, i/CARRY_ARM_ROWS))
        self.idle(rid, 5)

        def sighting():
            jpg = self.w.frame(rid)
            target = self.trial["receiver_sign"]
            reads = {"rectified": reader.read(jpg)}
            method = "rectified"
            if not any(t.get("sign") == target for t in reads[method]):
                # Same raw ArUco path as the archived --sign-raw-read executor. Its corners are rectified.
                method = "raw"
                reads[method] = reader.read_signs_raw(jpg)
            for tag in reads[method]:
                if tag.get("sign") != target:
                    continue
                p = tags.sign_on_floor(tag, {int(k): v for k, v in self.w.pwm[rid].items()},
                                       projection.camera_extrinsics, projection.K)
                if p is not None:
                    return jpg, tag, p, method
            self.rec.observe("sign_scan_miss", robot=rid, sign=target, decoded=reads,
                             pwm=dict(self.w.pwm[rid]), chassis_pose=self.w.actual_pose(rid),
                             box_pose=self.w.witness(), jpg=jpg)

        for pan in (1500, 1350, 1650, 1150, 1850, 950, 2050):
            self.idle(rid, 6, {**far, "6": pan})
            at = self.rec.now
            sight = sighting()
            if sight is None:
                continue
            own = self.pose(rid)
            if self.rec.now != at:
                # An overhead recovery can settle the chassis or swivel the arm. Pair same-tick images.
                sight = sighting()
                if sight is None:
                    continue
            jpg, tag, p, method = sight
            measured = absolute(own, p["x"], p["y"])
            nx, ny = p["normal"]
            # Floor target 0.28 m in front of the observed card, plus the replay's 0.31 m box offset.
            stand = absolute(own, p["x"]+.59*nx, p["y"]+.59*ny)
            face = own[2] + math.atan2(-ny, -nx)
            self.rec.event("sign_seen", robot=rid, sign=tag["sign"], corners_px=tag["corners_px"],
                           measured_xy=measured, method=method, pwm=dict(self.w.pwm[rid]),
                           chassis_pose=self.w.actual_pose(rid), frame=self.photo("receiver-sign", jpg))
            self.stage = "set_down"
            self.idle(rid, 6, far)
            self.drive(rid, stand, face)
            for i in reversed(range(CARRY_ARM_ROWS)):
                self.idle(rid, pwm=carry_pwm(hold, i/CARRY_ARM_ROWS))
            self.idle(rid, 5)
            return
        raise StopTrial("sign_seen", "destination card was not localized from the receiver's own RGB")

    def run(self):
        donor, receiver = self.trial["donor"], self.trial["receiver"]
        self.idle(donor, 10)
        self.pick("donor")
        self.stage = "release"
        self.station(donor, -.70, 0, 0)
        self.station(donor, -layout.RELEASE_STAND, 0, 0)
        self.release("donor")
        self.stage = "donor_clear"
        self.station(donor, -.85, 0, 0, reverse=True)
        self.station(donor, *layout.PARK, 90)
        self.idle(donor, 5)
        actual = self.w.actual_xy(donor)
        if not layout.park_clear(self.trial, *actual):
            raise StopTrial("donor_clear", "donor did not park off the receiver's sightline")
        self.rec.event("donor_clear", robot=donor, xy=actual, pose=self.w.witness(), frame=self.photo("donor-clear"))
        self.stage = "receiver_seen"
        self.station(receiver, layout.SCAN_STAND, 0, 180)
        self.rec.event("scan_start", robot=receiver, xy=self.w.actual_xy(receiver))
        self.pick("receiver")
        self.find_sign(receiver)
        self.release("receiver")
