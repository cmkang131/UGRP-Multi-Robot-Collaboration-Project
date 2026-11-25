"""Stationary recovery on constructed camera observations. No physics or trained actor."""
from contextlib import ExitStack
import json
from pathlib import Path
import sys
import tempfile
from types import SimpleNamespace
import unittest
from unittest.mock import Mock, patch

import numpy as np
from PIL import Image

from test_gate import score, synthetic
from test_policy import ToyWorld, layout, Policy, Recorder, StopTrial
from harness import overhead_v1 as overhead
from harness.handover_policy import MagnifiedMarkers, PAN_ON_RECHECK, POSE_RECHECKS
from scripts.run_grasp_act_student import CARRY_FAR_POSTURE


class CameraWorld(ToyWorld):
    def __init__(self, trial, record, readings):
        super().__init__(trial, record)
        self.readings = iter(readings)
        self.read_times = []
        self.zoom = Mock()
        self.cameras = ["top"] if trial["wall"] == "north-south" else ["top", "top_1"]

    def positions(self):
        native, magnified = next(self.readings)
        self.read_times.append(self.record.now)
        self.zoom.read.return_value = magnified
        self.last_ceiling_frames = {name: np.full((8, 9, 3), len(self.read_times) + i, np.uint8)
                                    for i, name in enumerate(self.cameras)}
        return native


class Recovery(unittest.TestCase):
    def policy(self, trial, readings):
        stack = self.enterContext(ExitStack())
        folder = Path(stack.enter_context(tempfile.TemporaryDirectory()))
        record = Recorder(folder, trial, stack)
        world = CameraWorld(trial, record, readings)
        policy = Policy(world, None)
        policy.zoom_reader = world.zoom
        return policy, world

    def events(self, world):
        return [json.loads(line) for line in (world.record.out / "events.jsonl").read_text().splitlines()]

    def test_clean_reads_and_distinct_short_losses_on_both_robots_and_both_walls(self):
        for trial in list(layout.trials().values())[:4]:
            for role, stage, station in (("donor", "donor_clear", layout.PARK),
                                         ("receiver", "receiver_seen", (layout.SCAN_STAND, 0))):
                with self.subTest(direction=trial["direction"], role=role):
                    rid = trial[role]
                    target = layout.xy(trial["direction"], *station)
                    pose = [*target, layout.yaw(trial["direction"], 90)]
                    here = {rid: pose}
                    other = {r: p for r, p in trial["starts"].items() if r != rid}
                    policy, world = self.policy(trial, [(here, {}), (other, other), (other, other),
                                                        (here, {}), (other, other), (other, here)])
                    policy.stage = stage
                    # Each arrival must use this read's pose. The referee and stored chassis are unavailable.
                    with patch.object(world, "actual_xy", side_effect=AssertionError("referee navigation")):
                        for _ in range(3):
                            policy.drive(rid, target, pose[2])
                    events = self.events(world)
                    self.assertEqual([e["event"] for e in events], ["overhead_lost", "overhead_recovered"] * 2)
                    self.assertEqual(world.read_times, [0., 0., .1, .2, .2, .3])
                    self.assertTrue(all(r == rid and row["wheels"] == [0.] * 4 for r, row in world.commands))
                    self.assertEqual([e["missed_frames"] for e in events[1::2]], [2, 1])
                    self.assertEqual([e["method"] for e in events[1::2]], ["native", "magnified"])
                    for lost, end in zip(events[::2], events[1::2]):
                        self.assertEqual((end["robot"], end["stage"], end["chassis_pose"]), (rid, stage, pose))
                        self.assertEqual((end["start_sim_s"], end["lost_seq"]), (lost["sim_s"], lost["seq"]))
                        self.assertAlmostEqual(end["duration_s"], end["sim_s"] - lost["sim_s"])
                    for e, number in zip(events, (2, 4, 5, 6)):
                        self.assertEqual(list(e["ceiling_frames"]), world.cameras)
                        for i, filename in enumerate(e["ceiling_frames"].values()):
                            with Image.open(world.record.out / filename) as frame:
                                self.assertEqual(frame.format, "PNG")
                                self.assertEqual(frame.getpixel((0, 0)), (number + i,) * 3)

    def test_final_recheck_can_recover_with_gripper_and_lowered_arm_held(self):
        trial = layout.trials()[2]
        rid = trial["receiver"]
        fresh = {rid: [*layout.xy(trial["direction"], .48, 0), layout.yaw(trial["direction"], 0)]}
        policy, world = self.policy(trial, [({}, {})] * POSE_RECHECKS + [({}, fresh)])
        policy.stage = "sign_seen"
        hold = dict(world.pwm[rid])
        self.assertEqual(policy.pose(rid), fresh[rid])
        self.assertEqual(len(world.commands), POSE_RECHECKS)
        for r, row in world.commands:
            self.assertEqual((r, row["wheels"], row["pwm"]), (rid, [0.] * 4, hold))
        end = self.events(world)[-1]
        self.assertEqual((end["event"], end["missed_frames"]), ("overhead_recovered", POSE_RECHECKS))
        self.assertAlmostEqual(end["duration_s"], POSE_RECHECKS * .1)

    def test_persistent_other_id_stops_navigation_at_the_active_stage(self):
        trial = layout.trials()[3]
        for stage, role in (("donor_clear", "donor"), ("receiver_pick", "receiver"),
                            ("sign_seen", "receiver"), ("set_down", "receiver")):
            with self.subTest(stage=stage):
                rid = trial[role]
                other = {r: p for r, p in trial["starts"].items() if r != rid}
                policy, world = self.policy(trial, [(other, other)] * (POSE_RECHECKS + 1))
                policy.stage = stage
                grip = 2000 if stage == "donor_clear" else 1500
                world.pwm[rid] = {"1": grip, **CARRY_FAR_POSTURE}
                with self.assertRaises(StopTrial) as caught:
                    policy.drive(rid, trial["starts"][rid][:2])
                self.assertEqual(caught.exception.stage, stage)
                self.assertEqual(len(world.read_times), POSE_RECHECKS + 1)
                self.assertEqual(len(world.commands), POSE_RECHECKS + 5)
                for i, (robot, row) in enumerate(world.commands, 1):
                    pan = 1500 if i < PAN_ON_RECHECK else 1850
                    self.assertEqual((robot, row["wheels"], row["duration_s"]), (rid, [0.] * 4, [0.] * 4))
                    self.assertEqual(row["pwm"], {"1": grip, **CARRY_FAR_POSTURE, "6": pan})
                lost, end = self.events(world)
                self.assertEqual((end["event"], end["lost_seq"], end["stage"]), ("overhead_timeout", lost["seq"], stage))
                self.assertEqual((end["missed_frames"], end["pan_pwm"]), (POSE_RECHECKS + 1, 1850))
                self.assertEqual(end["reason"], str(caught.exception))
                self.assertAlmostEqual(end["duration_s"], 1.7)

    def test_sign_is_measured_again_after_overhead_recovery(self):
        trial = layout.trials()[1]
        rid = trial["receiver"]
        fresh = {rid: [.48, 0., 0.]}
        policy, world = self.policy(trial, [({}, {})] * PAN_ON_RECHECK + [(fresh, {})])
        tag = {"sign": trial["receiver_sign"], "corners_px": [[1, 1], [3, 1], [3, 3], [1, 3]]}
        reader = Mock()
        reader.read.return_value = [tag]
        projection = SimpleNamespace(K=None, D=None, camera_extrinsics=None)
        def project(_tag, pwm, *_):
            return {"x": 2.0 if pwm[6] == 1850 else 1.0, "y": 0., "normal": [-1., 0.]}
        with (patch.dict(sys.modules, {"harness.approach_survey_v1_parts.ground_projection": projection}),
              patch("harness.handover_policy.tags.TagReader", return_value=reader),
              patch("harness.handover_policy.tags.sign_on_floor", side_effect=project),
              patch.object(policy, "station"), patch.object(policy, "drive") as drive,
              patch.object(world, "frame", side_effect=lambda r: str(world.record.now).encode())):
            policy.find_sign(rid)
        _, recovered, sign = self.events(world)
        self.assertEqual(recovered["sim_s"], sign["sim_s"])
        self.assertEqual((world.record.out / sign["frame"]).read_bytes(), str(sign["sim_s"]).encode())
        self.assertEqual(sign["measured_xy"], [2.48, 0.])
        self.assertAlmostEqual(drive.call_args.args[1][0], 2.48 - .59)

    def test_recorded_intervals_score_without_advancing_the_gate(self):
        trial, events, rows, run = synthetic()
        clear = next(e for e in events if e["event"] == "donor_clear")
        index, rid = clear["seq"], trial["donor"]
        policy, world = self.policy(trial, [({}, {}), ({rid: [-.85, 0., 0.]}, {})])
        policy.stage = "donor_clear"
        world.record.now, world.record.seq = 13.8, index
        policy.pose(rid)
        events[index:index] = self.events(world)
        for seq, event in enumerate(events):
            event["seq"] = seq
        def result():
            return score.score(trial, events, rows, run, lambda _: True)
        self.assertEqual(result()["status"], "SUCCESS")
        clear["xy"] = [-.85, 0.]
        self.assertEqual(result()["stage"], "donor_clear")
        events[index + 1]["lost_seq"] -= 1
        self.assertEqual(result()["stage"], "records")

    def test_recorded_timeout_scores_as_an_evaluated_stage_failure(self):
        trial, events, rows, run = synthetic()
        index = next(e["seq"] for e in events if e["event"] == "donor_clear")
        policy, world = self.policy(trial, [({}, {})] * (POSE_RECHECKS + 1))
        policy.stage = "donor_clear"
        world.record.now, world.record.seq = 13.8, index
        with self.assertRaises(StopTrial) as caught:
            policy.pose(trial["donor"])
        world.record.event("failure", stage=caught.exception.stage, reason=str(caught.exception))
        end = world.record.now
        run.update(status="failed", stage="donor_clear", sim_s=end, last_step=round(end / run["dt"]))
        result = score.score(trial, events[:index] + self.events(world), [r for r in rows if r["sim_s"] <= end],
                             run, lambda _: True)
        self.assertEqual((result["status"], result["stage"], result["evaluated"]), ("FAIL", "donor_clear", True))
        self.assertEqual(result["reason"], str(caught.exception))


class DetectorCoordinates(unittest.TestCase):
    def test_magnified_quads_keep_native_position_heading_and_tile_calibration(self):
        # Construct the same oblique marker in two overlapping crops of the second ceiling camera.
        height, width = 100, 160
        gray = np.zeros((height, width), dtype=np.uint8)
        quad = np.float32([[[78, 72], [88, 65], [95, 75], [85, 82]]])
        def enlarged(x0, y0):
            return [(quad - (x0, y0) + .5) * 2 - .5], np.int32([[41]]), ()
        empty = ([], None, ())
        decoder = Mock()
        decoder.detectMarkers.side_effect = [empty] * 4 + [empty, empty, enlarged(0, 26), enlarged(56, 26)]
        reader = object.__new__(overhead.OverheadReader)
        reader.right, reader.down, reader.f = np.array([1., 0., 0.]), np.array([0., -1., 0.]), 100.
        cameras = (("top", (0., -1.)), ("top_1", (0., 1.)))
        pictures = {name: gray for name, _ in cameras}
        with (patch.multiple(overhead, WIDTH=width, HEIGHT=height, CAMERAS=cameras, TOP_ID0=40, N_TOP=2),
              patch.dict(sys.modules, {"cv2": SimpleNamespace()})):
            reader.detector = Mock()
            reader.detector.detectMarkers.side_effect = [empty, ([quad], np.int32([[41]]), ())]
            expected = reader.read(pictures)
            reader.detector = MagnifiedMarkers(decoder)
            actual = reader.read(pictures)
        self.assertEqual(set(actual), {"r2"})
        np.testing.assert_allclose(actual["r2"], expected["r2"])
        for call in decoder.detectMarkers.call_args_list:
            self.assertEqual(call.args[0].shape, (148, 208))
