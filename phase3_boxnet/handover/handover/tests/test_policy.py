"""Run the phase sequence and real command decoders on toy observations, without physics."""
from contextlib import ExitStack
import json
import math
from pathlib import Path
import sys
import tempfile
from types import SimpleNamespace
import unittest
from unittest.mock import Mock, patch

BASE = Path(__file__).resolve().parents[2]
sys.path[:0] = [str(BASE), str(BASE/"exec")]
from handover import layout
from handover.records import Recorder, StopTrial
from harness import grasp_act_contract as contract
from harness.grasp_act_rollout import GraspTransitionRule, OwnHistory
from harness.handover_policy import Policy


class ToyWorld:
    def __init__(self, trial, record):
        self.trial, self.record = trial, record
        self.coords = {r: list(v) for r,v in trial["starts"].items()}
        self.pwm = {r: dict(GraspTransitionRule.END_PWM) for r in self.coords}
        self.carried_by, self.box_xy = None, [0.,0.]
        self.commands = []

    def frame(self, rid=None):
        return b"synthetic RGB fixture"

    def actual_xy(self,rid):
        return self.coords[rid][:2]

    def actual_pose(self, rid):
        return list(self.coords[rid])

    def positions(self):
        return self.coords

    def control(self, rid, row):
        self.commands.append((rid,contract.command(row)))
        self.pwm[rid]=dict(row["pwm"])
        self.record.now = round(self.record.now + .1, 8)

    def witness(self):
        rid=self.carried_by
        held=rid is not None and self.pwm[rid]["1"] <= 1550
        return {"body":layout.BODY,"body_id":7,"x":self.box_xy[0],"y":self.box_xy[1],"yaw":0.,"tilt_deg":0.,
                "z":.04 if held else .016,"clearance_m":.024 if held else 0.,
                "speed_m_s":0.,"sim_s":self.record.now,
                "finger_n":{r: [1.,1.] if held and r==rid else [0.,0.] for r in self.coords}}


class PolicyChecks(unittest.TestCase):
    def setUp(self):
        self.stack=ExitStack()
        self.addCleanup(self.stack.close)
        tmp=self.stack.enter_context(tempfile.TemporaryDirectory())
        self.t=layout.trials()[1]
        self.record=Recorder(Path(tmp),self.t,self.stack)
        self.world=ToyWorld(self.t,self.record)
        row={"t":0., "wheels":[0.]*4,"duration_s":[0.]*4,"pwm":dict(GraspTransitionRule.END_PWM)}
        actor=SimpleNamespace(predict=lambda obs,images: [contract.encode_action(row)]*contract.CHUNK)
        self.p=Policy(self.world,actor)

    def events(self):
        return [json.loads(s) for s in (self.record.out/"events.jsonl").read_text().splitlines()]

    def observations(self):
        return [json.loads(s) for s in (self.record.out/"observations.jsonl").read_text().splitlines()]

    def test_mark_only_receiver_exception_uses_own_observation(self):
        class Survey:
            def __init__(self,contract,select,**kw):
                self.select=select
                self.survey=SimpleNamespace(_tracks=[], evidence={})
                self.entries=[]
                self.arrived=self.box_not_seen=False
                self.reason=self.align_reason=None
            def step(self,jpg,now):
                self.survey._tracks=[{"kind":"red","points":[(.8,0.)]}]
                self.index=self.select([{"kind":"red","x":.8,"y":0.}])
                self.arrived=True
                return None
            def approach_seconds(self): return 0.
            def alignment_trace(self): return []
        with patch("harness.handover_policy.SurveyApproach",Survey):
            for rid,role,origin in (("r1","donor",[-.8,0,0]),("r2","receiver",[.8,0,math.pi])):
                self.world.coords[rid]=origin
                if role=="donor":
                    with self.assertRaises(StopTrial): self.p.approach(rid,role,1)
                else:
                    history=self.p.approach(rid,role,1)
                    self.assertIsInstance(history,OwnHistory)
        seen=[e for e in self.events() if e["event"]=="receiver_seen"]
        self.assertEqual(len(seen),1)
        self.assertAlmostEqual(math.hypot(*seen[0]["observed_xy"]),0.)

    def test_failed_station_hold_preserves_forces_tilt_and_chassis_before_opening(self):
        for role in layout.ROLES:
            rid = self.t[role]
            self.world.carried_by = rid
            for mode, height, forces in [("strict", .07, [4., 4.]), ("ignore", .0119, [4., 4.]),
                                        ("ignore", .07, [.49, 4.]), ("ignore", .07, [4., .49])]:
                with self.subTest(role=role, mode=mode, height=height, forces=forces):
                    policy = self.p if mode == "strict" else Policy(self.world, None, station_tilt=mode)
                    pose = dict(self.world.witness(), tilt_deg=16., clearance_m=height)
                    pose["finger_n"][rid] = forces
                    with patch.object(self.world, "witness", return_value=pose), self.assertRaises(StopTrial):
                        policy.release(role)
                    event = self.observations()[-1]
                    self.assertEqual((event["observation"], event["pose"], event["chassis_pose"]),
                                     ("station_hold_failed", pose, self.world.coords[rid]))
                    self.assertEqual(self.events(), [])
                    self.assertEqual(self.world.commands, [])

    def test_tilted_station_grip_replays_and_judges_the_landing(self):
        policy = Policy(self.world, None, station_tilt="ignore")
        for role, stage, target in (("donor", "release", [0., 0.]), ("receiver", "set_down", [2.36, 0.])):
            rid = self.t[role]
            outside = "missed the mark" if role == "donor" else "outside the receiver sign area"
            for xy, tilt, reason in ((target, 0., None), (target, 11., "settled on the floor"), ([1., 0.], 0., outside)):
                with self.subTest(role=role, landing=xy, tilt=tilt):
                    self.world.carried_by, self.world.box_xy = rid, xy
                    self.world.pwm[rid] = dict(GraspTransitionRule.END_PWM)
                    start, witness = self.record.now, self.world.witness

                    def measured():
                        pose = witness()
                        if self.record.now == start:
                            pose.update(tilt_deg=16., clearance_m=layout.LIFT_FLOOR)
                            pose["finger_n"][rid] = [layout.FINGER_N] * 2
                        else:
                            pose["tilt_deg"] = tilt
                        return pose

                    with patch.object(self.world, "witness", side_effect=measured):
                        if reason is None:
                            policy.release(role)
                        else:
                            with self.assertRaisesRegex(StopTrial, reason) as stopped:
                                policy.release(role)
                            self.assertEqual(stopped.exception.stage, stage)
                    observation = self.observations()[-1]
                    opened, detached, landed = self.events()[-3:]
                    self.assertEqual([e["event"] for e in (opened, detached, landed)],
                                     [stage + "_start", stage + "_open", stage])
                    self.assertEqual((observation["observation"], observation["stage"], observation["robot"],
                                      observation["next_event_seq"], observation["pose"]),
                                     ("held_tilted", stage, rid, opened["seq"], opened["pose"]))
                    self.assertEqual((observation["pose"]["tilt_deg"], landed["rows"], len(landed["rest"])),
                                     (16., 87, 10))

    def test_sign_misses_retain_each_frame_and_raw_read_can_locate_target(self):
        rid, target = self.t["receiver"], self.t["receiver_sign"]
        reader = Mock()
        other = {"sign": target - 1, "corners_px": [[0, 0]] * 4}
        tag = {"sign": target, "corners_px": [[1, 1], [4, 1], [4, 4], [1, 4]]}
        reader.read.return_value = [other]
        reader.read_signs_raw.side_effect = [[other], [tag]]
        proj = SimpleNamespace(K=None, D=None, camera_extrinsics=None)
        with (patch.dict(sys.modules, {"harness.approach_survey_v1_parts.ground_projection": proj}),
              patch("harness.handover_policy.tags.TagReader", return_value=reader),
              patch("harness.handover_policy.tags.sign_on_floor", return_value={"x": 2., "y": 0., "normal": [-1., 0.]}) as locate,
              patch.object(self.p, "station"), patch.object(self.p, "drive"),
              patch.object(self.world, "frame", side_effect=lambda r: str(self.record.now).encode())):
            self.p.find_sign(rid)
        miss, = self.observations()
        seen, = self.events()
        self.assertEqual(miss["decoded"], {"rectified": [other], "raw": [other]})
        self.assertEqual((miss["observation"], miss["pwm"]["6"], seen["method"], seen["pwm"]["6"]),
                         ("sign_scan_miss", 1500, "raw", 1350))
        self.assertEqual(locate.call_args.args[0], tag)
        self.assertEqual(reader.read.call_args_list, reader.read_signs_raw.call_args_list)
        for event in (miss, seen):
            self.assertEqual((self.record.out / event["frame"]).read_bytes(), str(event["sim_s"]).encode())

    def test_seven_unlocalized_sign_views_still_fail(self):
        rid, target = self.t["receiver"], self.t["receiver_sign"]
        reader = Mock()
        reader.read.return_value = [{"sign": target, "corners_px": [[1, 2]] * 4}]
        proj = SimpleNamespace(K=None, D=None, camera_extrinsics=None)
        with (patch.dict(sys.modules, {"harness.approach_survey_v1_parts.ground_projection": proj}),
              patch("harness.handover_policy.tags.TagReader", return_value=reader),
              patch("harness.handover_policy.tags.sign_on_floor", return_value=None),
              patch.object(self.p, "station"), patch.object(self.p, "drive") as drive,
              self.assertRaises(StopTrial) as caught):
            self.p.find_sign(rid)
        self.assertEqual(caught.exception.stage, "sign_seen")
        self.assertEqual(self.events(), [])
        self.assertEqual([e["pwm"]["6"] for e in self.observations()], [1500, 1350, 1650, 1150, 1850, 950, 2050])
        reader.read_signs_raw.assert_not_called()
        drive.assert_not_called()

    def test_native_chunk_decoder_and_release_table_link_to_witnesses(self):
        rid=self.t["receiver"]
        self.world.carried_by=rid
        history=OwnHistory(rid,"constructed",self.p.row(rid))
        with patch.object(self.p,"approach",return_value=history):
            self.assertTrue(self.p.grasp("receiver",1))
        self.world.box_xy=[2.36,0]
        self.p.release("receiver")
        events=self.events()
        self.assertEqual([e["event"] for e in events],["attempt_start","grasp_attempt","set_down_start","set_down_open","set_down"])
        self.assertEqual(events[-1]["rows"],87)
        self.assertEqual(len(events[-1]["rest"]),10)
        self.assertGreaterEqual(events[-2]["sim_s"]-events[-3]["sim_s"],4.)
        self.assertAlmostEqual(events[-1]["sim_s"]-events[-3]["sim_s"],9.7)

    def test_each_robot_gets_only_one_retry_and_rescans(self):
        for role in layout.ROLES:
            rid=self.t[role]
            with patch.object(self.p,"grasp",return_value=False) as grasp, patch.object(self.p,"drive"):
                with self.assertRaises(StopTrial): self.p.pick(role)
                self.assertEqual([call.args for call in grasp.call_args_list],[(role,1),(role,2)])
            self.assertEqual(self.world.commands[-1][0],rid)

    def test_receiver_never_acts_when_donor_clear_fails(self):
        with patch.object(self.p,"pick") as pick, patch.object(self.p,"station"), patch.object(self.p,"release"):
            with self.assertRaises(StopTrial) as result: self.p.run()
        self.assertEqual(result.exception.stage,"donor_clear")
        self.assertEqual([call.args for call in pick.call_args_list],[("donor",)])
        self.assertEqual({rid for rid,_ in self.world.commands},{self.t["donor"]})
