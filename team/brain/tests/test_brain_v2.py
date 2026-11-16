"""Offline tests for the planner-side fixes of 2026-11-15 (stub LLM, no network, no paid call).

Run from the project folder:  python3 -B -m unittest discover -s brain/tests -p test_brain_v2.py -v
"""
import contextlib
import io
import json
import re
import sys
import tempfile
import unittest
from pathlib import Path
from unittest import mock

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))
sys.dont_write_bytecode = True

import brain  # noqa: E402
from brain import MAX_MESSAGES, MESSAGE_RULE  # noqa: E402
import brain_server  # noqa: E402
from brain import TeamBrain  # noqa: E402
from brain.llm import RealLLM  # noqa: E402

GOAL = brain_server.GOAL
RULE_1 = "Orders are for the whole team; a count is the team total, not per robot."
RULE_2 = ("Moving a box that no order asks for counts as an error; "
          "if there is nothing useful for you to do, you may finish.")
FACTS = [{"table": "orders", "id": "o1", "value": {"box": "blue", "zone": "sign12"}, "seen": 0},
         {"table": "bogus", "id": "x", "value": {"a": 1}},
         {"table": "boxes", "id": "b1"},
         {"table": "boxes", "id": 7, "value": {}}]
OPTIONS = [{"key": "box:0", "text": "go grasp target object <blue box> (my label a)"},
           {"key": "wait", "text": "wait here for now"}]


def progress_of(prompt):
    return json.loads(re.search(r"^Progress: (\{.*\})$", prompt, re.M)[1])


def dialogue_of(prompt):
    """The JSON list line of the Dialogue block."""
    block = re.search(r"Dialogue history:\n(.*?)\n(?:Previous actions|Available actions|Note):", prompt, re.S)[1]
    return json.loads(block.strip().splitlines()[-1])


DRAFT_LINE = "Message I can send to my friends together with my action (not sent yet): "


class Stub:
    """Deterministic offline model. A robot in `send` answers send:true whenever a draft message is shown (at most
    send[rid] times); every choice is the first listed action. Robots in `fail` raise."""

    def __init__(self, send=None, fail=(), facts=FACTS):
        self.send, self.fail, self.facts = dict(send or {}), set(fail), facts
        self.prompts, self.sent, self.texts = [], {}, {}
        self.records = []

    def call(self, prompt, response_format=None):
        self.prompts.append(prompt)
        robot = progress_of(prompt)["robot"]
        if robot in self.fail:
            raise RuntimeError("stub failure")
        if "generate a short message" in prompt:
            n = self.texts[robot] = self.texts.get(robot, 0) + 1
            return {"raw_output": json.dumps({"message": "%s msg %d" % (robot, n), "facts": self.facts})}
        if prompt.endswith("So the answer is option"):
            listing = re.search(r"Available actions:\n(.*)\nAnswer:", prompt, re.S)[1].splitlines()
            labels = [(l.split(". ", 1)[0], l.split(". ", 1)[1]) for l in listing]
            answer = {"action": labels[0][0]}
            if DRAFT_LINE in prompt:                        # a draft is shown: the answer says whether to send it along
                wants = self.sent.get(robot, 0) < self.send.get(robot, 0)
                self.sent[robot] = self.sent.get(robot, 0) + wants
                answer["send"] = wants
            return {"raw_output": json.dumps(answer)}
        return {"raw_output": '{"reasoning":"stub"}'}


_TEMP = []


def tearDownModule():
    for tmp in _TEMP:
        tmp.cleanup()


def make(team, robots=("r1", "r2"), stub=None, leader=None, goal=GOAL):
    tmp = tempfile.TemporaryDirectory()
    _TEMP.append(tmp)
    stub = stub or Stub()
    return TeamBrain(team, list(robots), goal, client=stub, log_dir=Path(tmp.name), leader=leader), stub


def choice_prompts(stub, robot):
    return [p for p in stub.prompts if "choose the best available action" in p and progress_of(p)["robot"] == robot]


def message_prompts(stub, robot):
    return [p for p in stub.prompts if "generate a short message" in p and progress_of(p)["robot"] == robot]


class DialogueAndMemory(unittest.TestCase):
    def test_t0_never_shows_dialogue(self):
        b, stub = make("T0", stub=Stub(send={"r1": 9, "r2": 9}))
        b.tell("r2", {"progress": "SECRET-FOR-R2"})
        for now, rid in ((1.0, "r1"), (2.0, "r2"), (30.0, "r1"), (31.0, "r2")):
            b.decide(rid, now, "pick", OPTIONS)
        self.assertEqual(b._messages, [])
        self.assertTrue(stub.prompts)
        for prompt in stub.prompts:
            for word in ("ialogue", "delivered reports", "Agent 1", "stale", "generate a short message"):
                self.assertNotIn(word, prompt)
            self.assertIn("My friends and I", prompt)           # CoELA's own wording stays (prompt_nocom.csv)
        self.assertFalse(any("SECRET-FOR-R2" in p for p in choice_prompts(stub, "r1")))
        self.assertTrue(all(d["sent"] == [] for rid in b.robots for d in b._decisions[rid]))

    def test_t1_t2_deliver_after_exactly_two_seconds(self):
        for team in ("T1", "T2"):
            with self.subTest(team=team):
                b, stub = make(team, stub=Stub(send={"r1": 1}))
                out = b.decide("r1", 12.0, "pick", OPTIONS)
                self.assertEqual(len(out["sent"]), 1)
                self.assertEqual(out["sent"][0]["deliver_at"], 14.0)
                b.decide("r2", 13.99, "pick", OPTIONS)
                self.assertTrue(all("r1 msg 1" not in p for p in stub.prompts[-3:]))
                n = len(stub.prompts)
                b.decide("r2", 14.0, "pick", OPTIONS)
                last = choice_prompts(stub, "r2")[-1]
                self.assertEqual([m["text"] for m in dialogue_of(last)], ["r1 msg 1"])
                self.assertEqual(dialogue_of(last)[0]["from"], "r1")
                self.assertEqual(dialogue_of(last)[0]["time"], 12.0)
                self.assertGreater(len(stub.prompts), n)

    def test_dialogue_is_message_body_only(self):
        b, stub = make("T1", stub=Stub(send={"r1": 1}))
        b.decide("r1", 1.0, "pick", OPTIONS)
        b.decide("r2", 5.0, "pick", OPTIONS)
        last = choice_prompts(stub, "r2")[-1]
        entry = dialogue_of(last)[0]
        self.assertEqual(sorted(entry), ["from", "text", "time"])
        self.assertEqual(entry["text"], "r1 msg 1")
        block = re.search(r"Dialogue history:\n(.*?)\nPrevious actions", last, re.S)[1]
        self.assertNotIn('\\"', block)
        self.assertNotIn("facts", block)
        # the sender's own entry is plain text too
        own = dialogue_of(choice_prompts(stub, "r1")[-1]) if len(choice_prompts(stub, "r1")) > 1 else []
        self.assertTrue(all(not m["text"].startswith("{") for m in own))

    def test_received_facts_are_stored_with_provenance_apart_from_own_facts(self):
        b, stub = make("T1", stub=Stub(send={"r1": 1}))
        own = {"orders": [{"box": "blue", "count": 1, "zone": "sign11"}], "progress": "I am in the box room."}
        b.tell("r2", own)
        b.tell("r1", {"progress": "r1 own fact"})
        b.decide("r1", 40.55, "pick", OPTIONS)
        b.decide("r2", 50.0, "pick", OPTIONS)
        progress = progress_of(choice_prompts(stub, "r2")[-1])
        self.assertEqual(progress["own_facts"], [own])                         # own entries intact
        self.assertEqual(progress["reported_facts"], [
            {"table": "orders", "id": "o1", "value": {"box": "blue", "zone": "sign12"},
             "provenance": "reported by r1 at 40.5 s"}])                       # seen:0 of the model is ignored
        sender = progress_of(choice_prompts(stub, "r1")[-1])
        self.assertNotIn("reported_facts", sender)                             # nothing received yet
        self.assertEqual(sender["own_facts"], [{"progress": "r1 own fact"}])

    def test_no_reported_facts_key_without_delivery_and_in_t0(self):
        b, stub = make("T1", stub=Stub(send={"r1": 1}))
        b.decide("r1", 1.0, "pick", OPTIONS)
        b.decide("r2", 2.0, "pick", OPTIONS)                                   # not delivered yet (3.0)
        self.assertTrue(all("reported_facts" not in p for p in stub.prompts))
        b0, stub0 = make("T0", stub=Stub(send={"r1": 9}))
        b0.decide("r1", 1.0, "pick", OPTIONS)
        b0.decide("r2", 99.0, "pick", OPTIONS)
        self.assertTrue(all("reported_facts" not in p for p in stub0.prompts))

    def test_later_report_replaces_earlier_and_senders_stay_apart(self):
        stub = Stub(send={"r1": 2, "r3": 1}, facts=[{"table": "boxes", "id": "blue1", "value": {"room": "box room"}}])
        b, _ = make("T1", robots=("r1", "r2", "r3"), stub=stub)
        b.decide("r1", 1.0, "pick", OPTIONS)
        b.decide("r1", 2.0, "pick", OPTIONS)                                   # second message of r1 (no ban after a message)
        b.decide("r3", 2.5, "pick", OPTIONS)
        b.decide("r2", 10.0, "pick", OPTIONS)
        rows = progress_of(choice_prompts(stub, "r2")[-1])["reported_facts"]
        self.assertEqual([(r["id"], r["provenance"]) for r in rows],
                         [("blue1", "reported by r1 at 2.0 s"), ("blue1", "reported by r3 at 2.5 s")])

    def test_window_keeps_five_received_plus_own_last(self):
        stub = Stub(send={"r1": 7, "r2": 2})
        b, _ = make("T1", stub=stub)
        for t in range(1, 15):                                                 # r1 sends at 1,3,...,13 (7 messages)
            b.decide("r1", float(t), "pick", OPTIONS)
            if t <= 4:
                b.decide("r2", t + 0.5, "pick", OPTIONS)                       # r2 sends at 1.5 and 3.5
        b.decide("r2", 30.0, "pick", OPTIONS)
        b.decide("r1", 31.0, "pick", OPTIONS)
        last = dialogue_of(choice_prompts(stub, "r2")[-1])
        self.assertEqual([m["text"] for m in last if m["from"] == "r1"], ["r1 msg %d" % k for k in range(3, 8)])
        self.assertEqual([m["text"] for m in last if m["from"] == "r2"], ["r2 msg 2"])
        self.assertEqual([m["time"] for m in last], sorted(m["time"] for m in last))
        self.assertEqual(len(last), 6)
        mine = dialogue_of(choice_prompts(stub, "r1")[-1])
        self.assertEqual([m["text"] for m in mine if m["from"] == "r2"], ["r2 msg 1", "r2 msg 2"])
        self.assertEqual([m["text"] for m in mine if m["from"] == "r1"], ["r1 msg 7"])


class TaskRulesAndWording(unittest.TestCase):
    def test_task_rules_in_every_structure_and_module(self):
        for team in ("T0", "T1", "T2"):
            with self.subTest(team=team):
                b, stub = make(team, stub=Stub(send={"r1": 1}))
                b.decide("r1", 1.0, "pick", OPTIONS)
                b.decide("r2", 9.0, "destination", OPTIONS)
                for prompt in stub.prompts:
                    goal_line = re.search(r"^Goal: (.*)$", prompt, re.M)[1]
                    # a talking structure's task text ends with the message sentence (test_messaging pins its wording); T0 is bare
                    self.assertEqual(goal_line, GOAL if team == "T0" else GOAL + " " + MESSAGE_RULE % MAX_MESSAGES)
                    self.assertIn(RULE_1, goal_line)
                    self.assertIn(RULE_2, goal_line)
        self.assertTrue(GOAL.startswith("Transport each box to the zone named in its order."))

    def test_wording(self):
        for team in ("T0", "T1", "T2"):
            b, stub = make(team, stub=Stub(send={"r1": 1}))
            b.decide("r1", 1.0, "pick", OPTIONS)
            for prompt in stub.prompts:
                self.assertNotIn("stale", prompt)
                self.assertIn("Only local observations", prompt)
                if team == "T0":
                    self.assertIn("Given our shared goal, my progress, and previous actions", prompt)
                else:
                    self.assertIn("Given our shared goal, dialogue history, my progress, and previous actions", prompt)
                    self.assertIn("Dialogue history:", prompt)

    def test_only_intended_lines_differ_from_the_frozen_planner(self):
        old_pkg = ROOT / "brain_2066649"
        if not old_pkg.is_dir():
            self.skipTest("frozen reference brain_2066649 is not beside this folder")
        import brain_2066649
        # T1/T2: the message rule changed on purpose (2026-11-15 user decision: a message goes with the action,
        # no separate send option). Those intended T1/T2 line changes are checked against the brain-v2 baseline by
        # an offline comparison script of the development work (T0 byte-identical, T1/T2 5 kinds of lines).
        for team in ("T0",):
            with self.subTest(team=team):
                rendered = []
                for cls in (brain_2066649.TeamBrain, TeamBrain):
                    stub = Stub(send={"r1": 1})
                    tmp = tempfile.TemporaryDirectory()
                    _TEMP.append(tmp)
                    b = cls(team, ["r1", "r2"], GOAL, client=stub, log_dir=Path(tmp.name))
                    b.tell("r1", {"orders": [{"box": "blue", "count": 1, "zone": "sign11"}]})
                    b.decide("r1", 12.0, "pick", OPTIONS)
                    rendered.append(stub.prompts)
                old, new = rendered
                self.assertEqual(len(old), len(new))
                for before, after in zip(old, new):
                    expect = before.replace("known; reported facts may be stale.", "known.")
                    if team == "T0":
                        expect = (expect.replace("dialogue history, ", "").replace(" and delivered reports", "")
                                  .replace(" Agent 1 means robot r1.", ""))
                    self.assertEqual(after, expect)


class CapsAndHalts(unittest.TestCase):
    def test_per_robot_cap_halts_only_that_robot(self):
        b, stub = make("T1")
        b.max_calls = 3                                                        # one T1 decision = 3 module calls
        first = b.decide("r1", 1.0, "pick", OPTIONS)
        self.assertEqual((first.get("halted"), first["calls"]), (None, 3))
        second = b.decide("r1", 2.0, "pick", OPTIONS)
        self.assertTrue(second["halted"])
        self.assertEqual(second["reason"], "Robot call cap reached")
        other = b.decide("r2", 3.0, "pick", OPTIONS)                           # r2 has its own 3 calls
        self.assertEqual((other.get("halted"), other["calls"]), (None, 3))
        again = b.decide("r1", 4.0, "pick", OPTIONS)
        self.assertTrue(again["halted"])
        self.assertEqual(again["calls"], 0)
        record = b.record()
        self.assertEqual(record["calls_by_robot"], {"r1": 3, "r2": 3})
        self.assertEqual(record["halted_by_robot"], {"r1": "Robot call cap reached", "r2": None})
        self.assertEqual(record["halted"], "Robot call cap reached")
        self.assertEqual(record["max_calls_per_robot"], 3)
        self.assertEqual(json.loads((Path(b.log_dir) / "brain-record.json").read_text())["halted_by_robot"]["r2"], None)

    def test_error_of_one_robot_does_not_halt_the_other(self):
        b, stub = make("T1", stub=Stub(fail={"r1"}))
        bad = b.decide("r1", 1.0, "pick", OPTIONS)
        self.assertEqual((bad["halted"], bad["reason"]), (True, "RuntimeError"))
        for now in (2.0, 3.0, 4.0):
            good = b.decide("r2", now, "pick", OPTIONS)
            self.assertNotIn("halted", good)
            self.assertEqual(good["calls"], 3)
        self.assertTrue(b.decide("r1", 5.0, "pick", OPTIONS)["halted"])
        self.assertEqual(b.record()["halted_by_robot"], {"r1": "RuntimeError", "r2": None})

    def test_real_client_ceiling_is_not_clamped_to_one_robot_cap(self):
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        client = RealLLM(4, Path(tmp.name) / "calls.jsonl", campaign_log_path=Path(tmp.name) / "ledger.jsonl",
                         campaign_max_calls=4)
        stub = Stub()

        def fake_call(prompt, response_format=None):
            client.records.append({"cache_hit": False, "cost_usd": 0.0})
            return stub.call(prompt)

        client.call = fake_call
        with mock.patch.object(brain, "check_spend_guard", lambda: {"skipped": "test"}):
            b = TeamBrain("T1", ["r1", "r2"], GOAL, client=client, log_dir=Path(tmp.name) / "log")
            b.max_calls = 2                                                    # per robot; the client ceiling is 4
            r1 = b.decide("r1", 1.0, "pick", OPTIONS)
            r2 = b.decide("r2", 2.0, "pick", OPTIONS)
        self.assertTrue(r1["halted"] and r2["halted"])                         # both hit their OWN cap of 2
        self.assertEqual((r1["calls"], r2["calls"]), (2, 2))                   # r2 was not blocked by r1's calls
        self.assertEqual(client.max_calls, 4)
        self.assertEqual(b.record()["paid_calls"], 4)
        self.assertEqual(b.record()["calls_by_robot"], {"r1": 2, "r2": 2})

    def test_server_ceiling(self):
        self.assertEqual(brain_server.run_ceiling(150, 2), 300)
        self.assertEqual(brain_server.run_ceiling(150, 3), 300)               # hard episode cap, not raised
        self.assertEqual(brain_server.run_ceiling(10, 3), 30)


class LeaderAndRouting(unittest.TestCase):
    def parse(self, *argv):
        base = ["--team", "T2", "--port", "1", "--log-dir", "/nonexistent"]
        return brain_server.parse_args(base + list(argv))

    def test_leader_option(self):
        self.assertEqual(self.parse().leader, "r1")
        self.assertEqual(self.parse("--leader", "r2").leader, "r2")
        self.assertEqual(self.parse("--leader", "r3", "--robots", "r1,r2,r3").leader, "r3")
        for bad in (["--leader", "r4"], ["--leader", "r3"]):                  # r3 is not in the default roster
            with self.subTest(bad=bad), contextlib.redirect_stderr(io.StringIO()), self.assertRaises(SystemExit):
                self.parse(*bad)

    def test_leader_sentence_and_agent_mapping(self):
        b, stub = make("T2", leader="r2", stub=Stub())
        b.decide("r1", 1.0, "pick", OPTIONS)
        for prompt in stub.prompts:
            self.assertIn("Agent 2 is the leader to coordinate the task.", prompt)
            self.assertIn("Agent 1 means robot r1, Agent 2 means robot r2.", prompt)
        b, stub = make("T2", stub=Stub())                                      # default leader: text unchanged
        b.decide("r1", 1.0, "pick", OPTIONS)
        for prompt in stub.prompts:
            self.assertIn("Agent 1 is the leader to coordinate the task.", prompt)
            self.assertIn("known. Agent 1 means robot r1.\n", prompt)
        b, stub = make("T1", leader="r2", stub=Stub())                         # no leader sentence outside T2
        b.decide("r1", 1.0, "pick", OPTIONS)
        self.assertTrue(all("is the leader" not in p and "Agent 1 means robot r1." in p for p in stub.prompts))

    def send_all(self, team, robots, leader=None):
        stub = Stub(send={r: 1 for r in robots})
        b, _ = make(team, robots=robots, stub=stub, leader=leader)
        for i, rid in enumerate(robots):
            b.decide(rid, 1.0 + i, "pick", OPTIONS)
        return b, stub, {m["from"]: m["to"] for m in b._messages}

    def test_three_robot_t2_is_hierarchical(self):
        robots = ("r1", "r2", "r3")
        _, _, routes = self.send_all("T2", robots)
        self.assertEqual(routes, {"r1": ["r2", "r3"], "r2": ["r1"], "r3": ["r1"]})
        _, _, routes = self.send_all("T2", robots, leader="r2")
        self.assertEqual(routes, {"r1": ["r2"], "r2": ["r1", "r3"], "r3": ["r2"]})

    def test_three_robot_t2_non_leaders_do_not_hear_each_other(self):
        b, stub, _ = self.send_all("T2", ("r1", "r2", "r3"))
        b.decide("r3", 50.0, "destination", OPTIONS)
        texts = [m["text"] for m in dialogue_of(choice_prompts(stub, "r3")[-1])]
        self.assertIn("r1 msg 1", texts)
        self.assertNotIn("r2 msg 1", texts)
        b.decide("r1", 51.0, "destination", OPTIONS)
        texts = [m["text"] for m in dialogue_of(choice_prompts(stub, "r1")[-1])]
        self.assertTrue({"r2 msg 1", "r3 msg 1"} <= set(texts))

    def test_t1_three_robots_and_two_robot_t2_routing_unchanged(self):
        _, _, routes = self.send_all("T1", ("r1", "r2", "r3"))
        self.assertEqual(routes, {"r1": ["r2", "r3"], "r2": ["r1", "r3"], "r3": ["r1", "r2"]})
        _, _, routes = self.send_all("T2", ("r1", "r2"))
        self.assertEqual(routes, {"r1": ["r2"], "r2": ["r1"]})
        _, _, routes = self.send_all("T2", ("r1", "r2"), leader="r2")
        self.assertEqual(routes, {"r1": ["r2"], "r2": ["r1"]})


if __name__ == "__main__":
    unittest.main()
