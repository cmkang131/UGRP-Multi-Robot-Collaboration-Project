"""Ordered free-talk assignments, decisions after release and the idle star leader. Scripted responses only."""
import tempfile
import unittest
from pathlib import Path

import brain_server
from brain import TeamBrain
from brain.tests.test_free_talk import FreeStub, listing_of, pick_for
from brain.tests.test_brain_v2 import progress_of
from brain.tests.test_protocol import DEST, DOOR

NEXT = [{"key": "back", "text": "go back to the box room for another box"}, {"key": "finish", "text": "finish my run"}]
MOVES = [{"key": "wait", "text": "keep waiting here"}, {"key": "move:back", "text": "back off a little"},
         {"key": "move:aside", "text": "step aside"}]
RELAY = [{"key": "wait", "text": "stay here and keep relaying for the team"}]


class TripDecisions(unittest.TestCase):
    def brain(self, team="T2", multi=True, **kw):
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        self.stub = FreeStub()
        b = TeamBrain(team, ["r1", "r2", "r3"], brain_server.GOAL, log_dir=Path(tmp.name),
                      client=self.stub, talk="free", merge_calls=True, parser_fix=True, multi_carry=multi, **kw)
        for r in b.robots:
            b.tell(r, {"orders": []})
        return b

    def send(self, b, now, body, target="r2", speaker="r1"):
        self.stub.say[speaker] = [(target, body)]
        answer = b.decide(speaker, now, "door", DOOR)
        self.assertEqual(len(answer["sent"]), 1)
        return answer["sent"][0]

    @staticmethod
    def release(b, trip, box, zone, outcome="at_zone"):
        b.tell("r2", dict(milestone="carry_finished", trip=trip, box=box, zone=zone, outcome=outcome))

    def test_readable_rows_stay_in_line_order_with_identical_jobs_and_duplicate_reports(self):
        b = self.brain(leader_bind=True, leader_route="star", options_v2=True)
        words = "assign r2: red -> sign13\nassign r2: red -> sign13\nassign r2: blue -> sign11"
        self.send(b, 0., words)
        self.assertEqual(b.decide("r2", 1., "pick", pick_for("r2"))["bind"]["state"], "held")
        self.assertEqual(b.decide("r2", 5., "pick", pick_for("r2"))["option"], "box:1")
        self.assertEqual(b.decide("r2", 6., "destination", DEST)["option"], "zone:sign13")
        self.release(b, 1, "red", "sign13")
        self.release(b, 1, "red", "sign13")
        self.stub.say["r2"] = [("r1", "One red delivered")]
        answer = b.decide("r2", 7., "next", NEXT)
        self.assertEqual((answer["option"], answer["sent"][0]["to"]), ("wait", ["r1"]))
        self.assertNotIn("finish my run", [t for _, t in listing_of(self.stub.prompts[-1])])
        self.assertEqual(b.decide("r2", 10., "next", NEXT)["option"], "back")
        b.tell("r2", dict(milestone="trip_started", trip=2))
        self.assertEqual(b.decide("r2", 11., "destination", DEST)["option"], "zone:sign13")
        self.release(b, 2, "red", "sign13")
        self.assertEqual(b.decide("r2", 12., "next", NEXT)["bind"]["box"], "blue")
        self.assertEqual(b.decide("r2", 13., "pick", pick_for("r2"))["option"], "box:0")
        self.assertEqual(b.decide("r2", 14., "destination", DEST)["option"], "zone:sign11")
        self.release(b, 3, "blue", "sign11")
        self.stub.choose = lambda _, entries: next(k for k, text in entries if text == "finish my run")
        self.assertEqual(b.decide("r2", 15., "next", NEXT)["option"], "finish")
        member = b.record()["binding"]["members"]["r2"]
        self.assertEqual([a["trip"] for a in member["fulfilled"]], [1, 2, 3])
        self.assertEqual(member["pending"], [])

    def test_a_later_message_appends_only_valid_lines_addressed_to_the_reader(self):
        b = self.brain(leader_bind=True, leader_route="star")
        self.send(b, 0., "assign r2: blue -> sign12")
        b.decide("r1", 3., "door", DOOR)               # an intervening body turn
        self.send(b, 4., "assign r2: purple -> sign11\nassign r2: red -> sign11\nassign r3: blue -> sign12")
        self.assertEqual(b.decide("r2", 12., "destination", DEST)["option"], "zone:sign12")
        facts = progress_of(self.stub.prompts[-1])["reported_facts"]
        rows = next(f["value"]["assigned_carries"] for f in facts if f["id"] == "r2")
        self.assertEqual([(r["box"], r["zone"]) for r in rows], [("blue", "sign12"), ("red", "sign11")])
        self.assertEqual(b.decide("r3", 12., "pick", pick_for("r3"))["bind"]["state"], "held")
        self.release(b, 1, "blue", "sign12")
        self.assertEqual(b.decide("r2", 13., "destination", DEST)["option"], "zone:sign11")
        self.assertEqual(b.record()["binding"]["assign_invalid"], 1)

    def test_loss_or_an_unrelated_delivery_does_not_consume_the_queue(self):
        b = self.brain(leader_bind=True)
        self.send(b, 0., "assign r2: red -> sign13\nassign r2: blue -> sign12")
        b.decide("r2", 6., "pick", pick_for("r2"))
        b.tell("r2", {"milestone": "grasp_failed"})
        self.assertNotIn("bind", b.decide("r2", 7., "pick", pick_for("r2")))
        self.release(b, 1, "red", "sign13", "put_down")
        self.release(b, 1, "blue", "sign12")
        self.assertEqual(b.decide("r2", 8., "next", NEXT)["bind"]["box"], "red")
        b.tell("r2", {"milestone": "trip_started", "trip": 2})
        self.assertEqual(b.decide("r2", 9., "pick", pick_for("r2"))["option"], "box:1")
        self.assertEqual(b.record()["binding"]["members"]["r2"]["fulfilled"], [])

    def test_empty_list_and_blocked_keep_move_choices_and_the_star_route(self):
        b = self.brain(leader_bind=True, leader_route="star", hold_s=0.)
        self.send(b, 0., "assign r2: blue -> sign12")
        empty = MOVES + [{"key": "finish", "text": "finish my run"}]
        self.stub.choose = lambda _, entries: next(k for k, t in entries if t == "step aside")
        self.assertEqual(b.decide("r2", 7., "pick", empty)["option"], "move:aside")
        self.stub.say["r2"] = [("r1", "The way is blocked")]
        speech = b.decide("r2", 8., "blocked", MOVES)
        self.assertEqual((speech["option"], speech["sent"][0]["to"]), ("wait", ["r1"]))
        self.assertEqual(b.decide("r2", 12., "blocked", MOVES)["option"], "move:aside")

    def test_next_in_peer_run_can_speak_then_finish_after_return(self):
        b = self.brain(team="T1", options_v2=True)
        self.stub.say["r3"] = [("r2", "I can do another trip")]
        spoke = b.decide("r3", 0., "next", NEXT)
        self.assertEqual((spoke["option"], spoke["sent"][0]["to"]), ("wait", ["r2"]))
        self.assertEqual(b.decide("r3", 4., "next", NEXT)["option"], "back")
        self.stub.choose = lambda _, entries: next(k for k, t in entries if t == "finish my run")
        self.assertEqual(b.decide("r3", 20., "next", NEXT)["option"], "finish")

    def test_relay_remains_available_after_the_leaders_final_next(self):
        b = self.brain(leader_route="star")
        self.assertTrue(b.decide("r1", 0., "next", NEXT)["relay"])
        self.stub.choose = lambda _, entries: next(k for k, t in entries if t.startswith("finish"))
        self.assertEqual(b.decide("r1", 20., "next", NEXT)["option"], "finish")
        self.send(b, 21., "At my second box", "r1", "r2")
        self.stub.say["r1"] = [("r2", "Go ahead")]
        result = b.decide("r1", 30., "relay", RELAY)
        self.assertEqual(result["sent"][0]["to"], ["r2"])
        self.assertIn("At my second box", self.stub.prompts[-1])
        self.assertEqual(b.record()["star"]["relay_decisions"], 1)

    def test_single_carry_keeps_the_first_line_of_the_latest_message(self):
        b = self.brain(multi=False, leader_bind=True)
        self.send(b, 0., "assign r2: blue -> sign12")
        b.decide("r1", 3., "door", DOOR)
        self.send(b, 4., "assign r2: red -> sign13\nassign r2: blue -> sign11")
        self.assertEqual(b.decide("r2", 12., "destination", DEST)["option"], "zone:sign13")
        self.assertNotIn("multi_carry", b.record()["conditions"])
        self.assertNotIn("pending", b.record()["binding"]["members"]["r2"])
