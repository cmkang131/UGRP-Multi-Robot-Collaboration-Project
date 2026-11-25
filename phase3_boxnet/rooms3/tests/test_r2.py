"""Deterministic board, step barrier and motor-stage checks. The placements below are fixtures."""
import copy
import json
import sys
import unittest
from types import SimpleNamespace

from handover.records import StopTrial
from rooms3 import board, steps
from rooms3.maps import ROBOTS, ROOT

sys.path.insert(0, str(ROOT / "exec"))


def scene(seed):
    return json.loads((ROOT / f"rooms3/scenes/seed-{seed}/map.json").read_bytes())


def witness(x, y, **extra):
    return dict({"x": x, "y": y, "tilt_deg": 0., "speed_m_s": 0., "clearance_m": 0.,
                 "finger_n": {r: [0., 0.] for r in ROBOTS}}, **extra)


class Fixture:
    """Independently supplied camera tracks, with stage endpoints scripted in referee coordinates."""
    identity_radius = .25

    def __init__(self, seed=0):
        self.scene = scene(seed)
        self.positions = {b["id"]: witness(*b["start"][:2]) for b in self.scene["boxes"]}
        self.views = {}
        for rid in ROBOTS:
            b = next(b for b in self.scene["boxes"] if b["room"] == rid)
            self.views[rid] = {"pose": [0, 0, 0], "sign_ids": [self.scene["rooms"][rid]["sign"]],
                               "entries": [self.track(b["colour"], *b["start"][:2])]}
        self.endpoints, self.calls, self.recovered = {}, [], []

    @staticmethod
    def track(colour, x, y):
        return {"kind": {"red": "red", "blue": "cyan"}[colour], "x": x, "y": y}

    def observe(self):
        return board.camera_board(self.scene, self.views), copy.deepcopy(self.views)

    def referee(self):
        return board.referee_board(self.scene, self.positions), copy.deepcopy(self.positions)

    def move(self, rid, track, dest):
        self.calls.append((rid, track, dest))
        body, point, failure = self.endpoints[rid]
        self.positions[body] = witness(*point, tilt_deg=67)
        if failure:
            raise StopTrial(failure, "fixture")
        return body

    def recover(self, rid):
        self.recovered.append(rid)


class BoardAndSteps(unittest.TestCase):
    def test_opposite_directions_are_two_places_and_receiver_owns_a_settled_box(self):
        f = Fixture(3)
        moves = {"r1": {"colour": "blue", "to": "r2"}, "r2": {"colour": "red", "to": "r1"}}
        for r, b in (("r1", "box_01"), ("r2", "box_02")):
            f.endpoints[r] = (b, f.scene["pads"][f"{r}_{moves[r]['to']}"]["xy"], None)
        result = steps.run_step(f.scene, moves, f)
        for rid, dest in (("r1", "r2"), ("r2", "r1")):
            row = result["actions"][rid]
            self.assertEqual(row["status"], "moved")
            self.assertEqual(row["measured_landing"]["room"], dest)
            self.assertEqual(result["after"]["referee"]["pads"][f"{rid}_{dest}"], 1)
        self.assertEqual(result["actions"]["r3"]["status"], "idle")

    def test_box_arriving_this_tick_is_only_selectable_next_tick(self):
        f = Fixture()
        pad = f.scene["pads"]["r1_r2"]["xy"]
        f.endpoints["r1"] = ("box_01", pad, None)
        moves = {"r1": {"colour": "red", "to": "r2"}, "r2": {"colour": "red", "to": "target"}}
        first = steps.run_step(f.scene, moves, f)
        self.assertEqual(first["actions"]["r2"]["reason"], "box_not_observed")
        self.assertEqual(len(f.calls), 1)
        f.views["r1"]["entries"].clear()
        f.views["r2"]["entries"].append(f.track("red", *pad))
        f.endpoints["r2"] = ("box_01", [0, -1], None)
        second = steps.run_step(f.scene, {"r2": moves["r2"]}, f)
        self.assertEqual(second["actions"]["r2"]["track"]["pad"], "r1_r2")
        self.assertEqual(second["actions"]["r2"]["status"], "moved")
        self.assertEqual(second["after"]["referee"]["delivered"], 1)

    def test_occupied_pad_blocked_from_perception_or_referee_and_capacity_is_parameterized(self):
        f = Fixture()
        pad = f.scene["pads"]["r1_r2"]
        f.positions["box_03"] = witness(*pad["xy"])
        action = {"r1": {"colour": "red", "to": "r2"}}
        for visible in (False, True):
            if visible:
                f.views["r2"]["entries"].append(f.track("red", *pad["xy"]))
            row = steps.run_step(f.scene, action, f)["actions"]["r1"]
            self.assertEqual((row["status"], row["reason"]), ("not_doable", "occupied_pad"))
        self.assertEqual(f.calls, [])
        pad["capacity"] = 2
        f.endpoints["r1"] = ("box_01", [pad["xy"][0], pad["xy"][1] + .05], None)
        result = steps.run_step(f.scene, action, f)
        self.assertEqual(result["after"]["referee"]["pads"]["r1_r2"], 2)

    def test_carry_failure_rebuilds_from_drop_and_other_robots_still_act(self):
        f = Fixture()
        f.endpoints = {"r1": ("box_01", [-1.4, -.8], "carry_loss"), "r2": ("box_02", [.0, -1], None)}
        result = steps.run_step(f.scene, {"r1": {"colour": "red", "to": "r2"},
                                         "r2": {"colour": "blue", "to": "target"}}, f)
        self.assertEqual([c[0] for c in f.calls], ["r1", "r2"])
        self.assertEqual(f.recovered, ["r1"])
        failed = result["actions"]["r1"]
        self.assertEqual((failed["status"], failed["reason"]), ("executed_failed", "carry_loss"))
        self.assertEqual(failed["measured_landing"]["xy"], [-1.4, -.8])
        self.assertFalse(failed["landed_as_requested"])
        self.assertEqual(result["after"]["referee"]["delivered"], 1)
        self.assertEqual(result["after"]["differences"]["delivered_truth_perceived"], [1, 0])

    def test_missed_mark_and_wrong_identified_body_are_not_success(self):
        for endpoint, reason in ((("box_01", [-1.18, -.275], None), "missed_landing"),
                                 (("box_03", [-1.325, -.275], None), "grasp_identity"),
                                 (("box_01", [-2.65, -.21], "grasp_failed"), "grasp_failed")):
            f = Fixture()
            f.endpoints["r1"] = endpoint
            row = steps.run_step(f.scene, {"r1": {"colour": "red", "to": "r2"}}, f)["actions"]["r1"]
            self.assertEqual((row["status"], row["reason"]), ("executed_failed", reason))

    def test_incidental_pad_obstruction_between_actions_vetoes_later_motor_stage(self):
        f = Fixture(3)
        f.endpoints["r1"] = ("box_01", f.scene["pads"]["r2_r1"]["xy"], "carry_loss")
        moves = {"r1": {"colour": "blue", "to": "r2"}, "r2": {"colour": "red", "to": "r1"}}
        result = steps.run_step(f.scene, moves, f)
        self.assertEqual(result["actions"]["r2"]["reason"], "occupied_pad")
        self.assertEqual([v[0] for v in f.calls], ["r1"])

    def test_camera_uses_visible_owned_tracks_decoded_signs_and_no_referee_substitution(self):
        f = Fixture(3)
        f.views["r1"]["entries"].append(f.track("red", *f.scene["boxes"][1]["start"][:2]))
        f.views["r2"]["pose"] = None
        f.views["r3"]["sign_ids"] = [11]
        got = steps.snapshot(f.scene, f)
        self.assertEqual([b["id"] for b in got["perceived"]["boxes"]], ["r1-track-0", "r3-track-0"])
        self.assertIsNone(got["perceived"]["remaining_targets"]["r3"])
        self.assertEqual(got["differences"]["unpaired_bodies"], ["box_02"])
        self.assertEqual(steps.resolve(f.scene, got["perceived"], "r3", {"colour": "red", "to": "target"})[1],
                         "target_not_observed")
        self.assertEqual(steps.resolve(f.scene, got["perceived"], "r1", {"colour": "blue", "to": "r3"})[1],
                         "not_a_neighbour")
        f.positions["box_01"] = witness(-2.4, -.4)
        self.assertEqual(f.observe()[0], got["perceived"])

    def test_airborne_contact_and_out_of_bounds_are_never_scored_as_transfers(self):
        f = Fixture()
        p = f.positions["box_01"] = witness(*f.scene["pads"]["r1_r2"]["xy"], clearance_m=.05, tilt_deg=70)
        p["finger_n"]["r1"] = [1., 1.]
        b = f.referee()[0]["boxes"][0]
        self.assertEqual((b["on_floor"], b["room"], b["pad"]), (False, "r1", None))
        f.positions["box_01"] = witness(20., 0.)
        self.assertIsNone(f.referee()[0]["boxes"][0]["room"])

    def test_target_colour_and_multiplicity_count_only_settled_eligible_bodies(self):
        f = Fixture(3)
        for i, b in enumerate(f.scene["boxes"]):
            f.positions[b["id"]] = witness(-2.7 + .1*i, -1., tilt_deg=88)
        got = f.referee()[0]
        self.assertEqual(got["delivered"], 1)  # one red target on this sign
        self.assertFalse(got["boxes"][0]["delivered"])  # blue
        self.assertEqual(got["remaining_targets"]["r1"], [])
        f.positions["box_02"]["speed_m_s"] = .05
        f.positions["box_03"]["clearance_m"] = .02
        self.assertEqual(f.referee()[0]["delivered"], 0)

    def test_room_limit_aborts_the_round_before_any_more_integration(self):
        f = Fixture()
        f.endpoints["r1"] = ("box_01", [-2, 0], "room_limit")
        with self.assertRaises(StopTrial):
            steps.run_step(f.scene, {"r1": {"colour": "red", "to": "r2"},
                                     "r2": {"colour": "blue", "to": "target"}}, f)
        self.assertEqual([v[0] for v in f.calls], ["r1"])
        self.assertFalse(f.recovered)


class Placement(unittest.TestCase):
    def policy(self, *, early=False):
        root = ROOT / "cloudrun/runs/handover-fix6-original-a117mixN/trials/trial-04"
        archived = [json.loads(line) for line in (root / "events.jsonl").read_text().splitlines()]
        start = next(e for e in archived if e["event"] == "release_start")
        rest = next(e["pose"] for e in archived if e["event"] == "release")
        rid, tilted = start["robot"], start["pose"]
        self.assertGreater(tilted["tilt_deg"], 10.)
        p = SimpleNamespace()
        p.events, p.issued = [], []
        p.rec = SimpleNamespace(now=0., event=lambda name, **fields: p.events.append((name, fields)))
        p.photo = lambda name: "fixture"
        p.w = SimpleNamespace(carrying=rid, pwm={rid: {"1": 1450, "3": 740, "4": 2320, "5": 1320, "6": 1500}})
        p.pose = tilted
        p.w.witness = lambda: p.pose
        def control(robot, row):
            p.issued.append(row)
            if early or row["pwm"]["1"] > 1550:
                p.pose = rest
            p.rec.now += .1
        p.w.control = control
        p.idle = lambda robot: setattr(p.rec, "now", p.rec.now + .1)
        return p, rid

    def test_tilted_archived_hold_issues_actual_87_row_release_and_uses_landing(self):
        p, rid = self.policy()
        steps.release_held(p, rid)
        self.assertEqual(len(p.issued), 87)
        self.assertEqual([event for event, _ in p.events], ["station_hold", "detached", "placement"])
        self.assertEqual(len(p.events[-1][1]["rest"]), 10)
        self.assertTrue(board.landed(p.pose))

    def test_insufficient_hold_and_early_detach_remain_distinct(self):
        p, rid = self.policy()
        p.pose = witness(0, 0)
        with self.assertRaises(StopTrial) as lost:
            steps.release_held(p, rid)
        self.assertEqual((lost.exception.stage, len(p.issued)), ("station_hold", 0))
        p, rid = self.policy(early=True)
        with self.assertRaises(StopTrial) as early:
            steps.release_held(p, rid)
        self.assertEqual(early.exception.stage, "early_detach")
