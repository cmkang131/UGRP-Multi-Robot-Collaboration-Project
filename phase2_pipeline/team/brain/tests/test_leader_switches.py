"""Offline tests of the leader-study switches (stub LLM, no network, no paid call):
message budgets (--max-messages, --leader-max-messages, --robot-max-messages), --leader-policy (label), --leader-authority, --idle-option.
Every switch is off by default and then changes no prompt and no record key (the default-identity tests below; the byte-level proof against the
frozen tree is tools/identity_check.py).

Run from the link folder:  python3 -B -m unittest brain.tests.test_leader_switches -v
"""
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

import brain_server  # noqa: E402
from brain import (IDLE_OPTION_TEXT, LEADER_AUTHORITY_LEADER, LEADER_AUTHORITY_MEMBER, MAX_MESSAGES,  # noqa: E402
                   MESSAGE_RULE, TeamBrain)
from brain.tests.test_brain_v2 import GOAL, OPTIONS, Stub, choice_prompts, message_prompts, progress_of  # noqa: E402

ROBOTS3 = ("r1", "r2", "r3")
PICK3 = [{"key": "box:0", "text": "go grasp target object <blue box> in the box room, 0.8 m away, straight ahead of me (my label r1-box0)"},
         {"key": "wait", "text": "wait here for now"},
         {"key": "finish", "text": "finish: there is nothing useful for me to do"}]
_TEMP = []


def tearDownModule():
    for tmp in _TEMP:
        tmp.cleanup()


def make(team, robots=ROBOTS3, stub=None, leader=None, goal=GOAL, **kw):
    tmp = tempfile.TemporaryDirectory()
    _TEMP.append(tmp)
    stub = stub or Stub()
    return TeamBrain(team, list(robots), goal, client=stub, log_dir=Path(tmp.name), leader=leader, **kw), stub


def cap_in_prompt(prompt):
    return int(re.search(r"You can send at most (\d+) messages in your whole run", prompt)[1])


def left_in_prompt(prompt):
    found = re.search(r"Messages left: (\d+)", prompt)
    return int(found[1]) if found else None


class Defaults(unittest.TestCase):
    def test_default_caps_are_the_main_experiment_cap(self):
        b, stub = make("T2")
        self.assertEqual((b.max_messages, b.message_caps, b._cap("r2")), (MAX_MESSAGES, {}, 8))
        for rid in ROBOTS3:
            b.decide(rid, 12.0, "pick", PICK3)
        self.assertTrue(stub.prompts)
        self.assertEqual({cap_in_prompt(p) for p in stub.prompts if "You can send at most" in p}, {8})
        for key in ("max_messages_by_robot", "conditions"):
            self.assertNotIn(key, b.record())
        self.assertEqual(b.record()["max_messages_per_robot"], 8)

    def test_default_text_has_no_study_sentence(self):
        for team in ("T0", "T1", "T2"):
            b, stub = make(team)
            for rid in ROBOTS3:
                b.decide(rid, 12.0, "pick", PICK3)
            text = "\n".join(stub.prompts)
            self.assertNotIn("You are the leader", text)
            self.assertNotIn("The leader decides which robot takes which box", text)
            self.assertNotIn("a robot that stays still never causes an error", text)
            self.assertIn("finish: there is nothing useful for me to do", text)

    def test_server_defaults(self):
        a = brain_server.parse_args(["--team", "T2", "--robots", "r1,r2,r3", "--port", "1", "--log-dir", "/x"])
        self.assertEqual((a.max_messages, a.leader_max_messages, a.robot_caps, a.leader_policy, a.leader_authority, a.idle_option),
                         (None, None, None, None, False, False))
        self.assertEqual(brain_server.GOAL, GOAL)                      # the default goal text is the one the main experiment used


class MessageBudgets(unittest.TestCase):
    def test_shared_cap_is_shown_and_enforced(self):
        for cap in (4, 8, 16):
            b, stub = make("T1", max_messages=cap)
            b.decide("r1", 12.0, "pick", PICK3)
            self.assertEqual({cap_in_prompt(p) for p in stub.prompts}, {cap})
            self.assertEqual({left_in_prompt(p) for p in message_prompts(stub, "r1")}, {cap})
            self.assertEqual(b.record()["max_messages_per_robot"], cap)
            self.assertNotIn("max_messages_by_robot", b.record())      # uniform cap: the old key says it all

    def test_cap_stops_drafts_and_chances_at_that_number(self):
        b, stub = make("T1", robots=("r1", "r2"), stub=Stub(send={"r1": 99}), max_messages=2)
        for i in range(5):
            b.decide("r1", 12.0 + 3 * i, "destination", [{"key": "wait", "text": "wait here"}])
        self.assertEqual(b._sent_by("r1"), 2)                           # the third decision made no draft call
        chance = b.chance("r1", 100.0)
        self.assertEqual((chance["asked"], chance["final"]), (False, True))

    def test_leader_alone_gets_its_own_cap_and_the_record_says_so(self):
        b, stub = make("T2", leader="r3", max_messages=8, leader_max_messages=16)
        for rid in ROBOTS3:
            b.decide(rid, 12.0, "pick", PICK3)
        caps = {rid: {cap_in_prompt(p) for p in stub.prompts if progress_of(p)["robot"] == rid and "You can send" in p} for rid in ROBOTS3}
        self.assertEqual(caps, {"r1": {8}, "r2": {8}, "r3": {16}})
        left = {left_in_prompt(p) for p in message_prompts(stub, "r3")}
        self.assertEqual(left, {16})
        rec = b.record()
        self.assertEqual(rec["max_messages_per_robot"], 8)               # the shared value, as before
        self.assertEqual(rec["max_messages_by_robot"], {"r1": 8, "r2": 8, "r3": 16})
        self.assertEqual(rec["leader"], "r3")

    def test_leader_cap_is_enforced_for_the_leader_only(self):
        b, stub = make("T2", robots=("r1", "r2"), stub=Stub(send={"r1": 99, "r2": 99}), leader="r1", max_messages=1, leader_max_messages=3)
        for i in range(6):
            b.decide("r1", 12.0 + 3 * i, "destination", [{"key": "wait", "text": "wait here"}])
            b.decide("r2", 12.0 + 3 * i, "destination", [{"key": "wait", "text": "wait here"}])
        self.assertEqual((b._sent_by("r1"), b._sent_by("r2")), (3, 1))
        self.assertTrue(b.chance("r1", 200.0)["final"] and b.chance("r2", 200.0)["final"])

    def test_single_robot_caps(self):
        b, stub = make("T1", max_messages=8, robot_max_messages={"r2": 4, "r3": 6})
        self.assertEqual([b._cap(r) for r in ROBOTS3], [8, 4, 6])
        self.assertEqual(b.record()["max_messages_by_robot"], {"r1": 8, "r2": 4, "r3": 6})

    def test_bad_budget_arguments_are_refused(self):
        bad = [("T0", dict(max_messages=4)), ("T0", dict(leader_max_messages=4)), ("T1", dict(leader_max_messages=4)),
               ("T1", dict(max_messages=0)), ("T1", dict(max_messages=2.5)), ("T1", dict(max_messages=True)),
               ("T2", dict(robot_max_messages={"r9": 4})), ("T2", dict(leader_max_messages=4, robot_max_messages={"r1": 4})),
               ("T2", dict(leader_max_messages=0))]
        for team, kw in bad:
            with self.assertRaises(ValueError, msg="%s %s" % (team, kw)):
                make(team, **kw)

    def test_server_arguments(self):
        base = ["--team", "T2", "--robots", "r1,r2,r3", "--port", "1", "--log-dir", "/x"]
        a = brain_server.parse_args(base + ["--leader", "r3", "--max-messages", "8", "--leader-max-messages", "16", "--leader-policy", "least"])
        self.assertEqual((a.leader, a.max_messages, a.leader_max_messages, a.leader_policy), ("r3", 8, 16, "least"))
        a = brain_server.parse_args(base + ["--robot-max-messages", "r2=4,r3=6"])
        self.assertEqual(a.robot_caps, {"r2": 4, "r3": 6})
        for bad in (["--team", "T0", "--robots", "r1,r2,r3", "--max-messages", "4"],
                    ["--team", "T1", "--robots", "r1,r2,r3", "--leader-max-messages", "4"],
                    ["--team", "T2", "--robots", "r1,r2,r3", "--robot-max-messages", "r9=4"],
                    ["--team", "T2", "--robots", "r1,r2,r3", "--robot-max-messages", "r2:4"],
                    ["--team", "T2", "--robots", "r1,r2,r3", "--leader-max-messages", "4", "--robot-max-messages", "r1=4"],
                    ["--team", "T1", "--robots", "r1,r2,r3", "--leader-authority"],
                    ["--team", "T0", "--robots", "r1,r2,r3", "--robot-max-messages", "r2=4"]):
            with self.assertRaises(SystemExit, msg=bad), mock.patch("sys.stderr"):
                brain_server.parse_args(bad + ["--port", "1", "--log-dir", "/x"])

    def test_main_passes_every_switch_to_the_brain(self):
        built = {}

        def make_brain(*a, **k):
            built["args"], built["kw"] = a, k
            return TeamBrain(*a, **{**k, "client": Stub()})

        with tempfile.TemporaryDirectory() as tmp, mock.patch.object(brain_server, "RealLLM", lambda *a, **k: Stub()), \
                mock.patch.object(brain_server, "TeamBrain", make_brain), mock.patch.object(brain_server, "HTTPServer"), \
                mock.patch.object(sys, "argv", ["brain_server.py", "--team", "T2", "--robots", "r1,r2,r3", "--leader", "r2", "--port", "1",
                                                "--log-dir", str(Path(tmp) / "log"), "--max-messages", "4", "--leader-max-messages", "8",
                                                "--leader-policy", "most", "--leader-authority", "--idle-option"]):
            brain_server.main()
        kw = built["kw"]
        self.assertEqual((kw["max_messages"], kw["leader_max_messages"], kw["leader_policy"], kw["leader_authority"], kw["idle_option"], kw["leader"]),
                         (4, 8, "most", True, True, "r2"))
        self.assertEqual(built["args"][2], brain_server.GOAL_IDLE)


class LeaderSeat(unittest.TestCase):
    def test_leader_seats_are_named_in_every_prompt_and_routing_follows(self):
        for seat in ROBOTS3:
            b, stub = make("T2", leader=seat, stub=Stub(send={r: 1 for r in ROBOTS3}))
            sent = {rid: b.decide(rid, 12.0, "pick", PICK3) for rid in ROBOTS3}
            index = ROBOTS3.index(seat) + 1
            self.assertTrue(all(("Agent %d is the leader to coordinate the task." % index) in p for p in stub.prompts))
            mapping = "Agent 1 means robot r1, Agent 2 means robot r2, Agent 3 means robot r3."
            self.assertEqual(all(mapping in p for p in stub.prompts), seat != "r1")      # the mapping sentence is listed for a leader other than Agent 1
            routes = {m["from"]: m["to"] for m in b._messages}
            self.assertEqual(routes, {seat: [r for r in ROBOTS3 if r != seat], **{r: [seat] for r in ROBOTS3 if r != seat}})
            self.assertEqual(b.record()["leader"], seat)
            self.assertTrue(all(out["sent"] == [] or out["sent"] for out in sent.values()))

    def test_policy_label_changes_nothing_but_the_record(self):
        plain, p_stub = make("T2", leader="r2")
        label, l_stub = make("T2", leader="r2", leader_policy="least")
        for brain_ in (plain, label):
            for rid in ROBOTS3:
                brain_.decide(rid, 12.0, "pick", PICK3)
        self.assertEqual(p_stub.prompts, l_stub.prompts)
        self.assertEqual(label.record()["conditions"], {"leader_policy": "least"})
        self.assertNotIn("conditions", plain.record())


class LeaderAuthority(unittest.TestCase):
    def prompts(self, **kw):
        b, stub = make("T2", leader="r2", **kw)
        for rid in ROBOTS3:
            b.decide(rid, 12.0, "pick", PICK3)
        return b, stub

    def test_leader_and_members_get_their_own_sentence_and_nothing_else_changes(self):
        _, plain = self.prompts()
        b, auth = self.prompts(leader_authority=True)
        self.assertEqual(len(plain.prompts), len(auth.prompts))
        lead_sentence = "Agent 2 is the leader to coordinate the task."
        for p, q in zip(plain.prompts, auth.prompts):
            rid = progress_of(p)["robot"]
            extra = LEADER_AUTHORITY_LEADER if rid == "r2" else LEADER_AUTHORITY_MEMBER
            self.assertEqual(q.replace(lead_sentence + " " + extra, lead_sentence), p)    # removing the two sentences gives the plain prompt
        self.assertEqual(b.record()["conditions"], {"leader_authority": True})

    def test_no_information_is_added(self):
        # the sentences only name the table and the format; they mention no box, no zone, no order and no robot's knowledge
        for text in (LEADER_AUTHORITY_LEADER, LEADER_AUTHORITY_MEMBER):
            self.assertNotRegex(text, r"sign\d|red|blue|\bo[123]\b")
        self.assertIn("using only what you know and what your friends have told you", LEADER_AUTHORITY_LEADER)

    def test_only_t2_can_use_it(self):
        for team in ("T0", "T1"):
            with self.assertRaises(ValueError):
                make(team, leader_authority=True)


class IdleOption(unittest.TestCase):
    def test_finish_text_is_replaced_at_pick_only_and_its_key_is_kept(self):
        b, stub = make("T1", idle_option=True)
        out = b.decide("r1", 12.0, "pick", PICK3)
        prompt = [p for p in stub.prompts if p.endswith("So the answer is option")][-1]
        self.assertIn(IDLE_OPTION_TEXT, prompt)
        self.assertNotIn("finish: there is nothing useful for me to do", prompt)
        recorded = b.record()["decisions"]["r1"][-1]["options"]
        self.assertEqual([o["key"] for o in recorded], ["box:0", "wait", "finish"])      # keys, order and the other texts as sent
        self.assertEqual(recorded[1]["text"], "wait here for now")
        self.assertEqual(out["option"], "box:0")
        other = [{"key": "zone:sign11", "text": "transport the box I am holding to the <sign11 zone>"},
                 {"key": "wait", "text": "wait here, holding the box"}, {"key": "finish", "text": "finish elsewhere"}]
        b.decide("r1", 20.0, "destination", other)
        self.assertEqual(b.record()["decisions"]["r1"][-1]["options"][2]["text"], "finish elsewhere")
        self.assertEqual(b.record()["conditions"], {"idle_option": True})

    def test_goal_variant_differs_from_the_main_goal_in_the_last_sentences_only(self):
        self.assertTrue(brain_server.GOAL_IDLE.startswith(brain_server.GOAL[:brain_server.GOAL.index("Moving a box")]))
        self.assertNotEqual(brain_server.GOAL_IDLE, brain_server.GOAL)
        self.assertIn("a robot that stays still never causes an error", brain_server.GOAL_IDLE)
        self.assertNotIn("do not stop just because you cannot do your own order", brain_server.GOAL_IDLE)

    def test_works_for_every_structure(self):
        for team in ("T0", "T1", "T2"):
            b, stub = make(team, idle_option=True, goal=brain_server.GOAL_IDLE)
            b.decide("r1", 12.0, "pick", PICK3)
            self.assertTrue(any(IDLE_OPTION_TEXT in p for p in stub.prompts))


if __name__ == "__main__":
    unittest.main()
