"""Offline tests of the message rules of 2026-11-15 (stub LLM, no network, no paid call):
  * the answer to the choice question is {"action": label, "send": true|false}: the action and a message together, no turn used,
    no 'send a message' list line, no ban on a message right after a message;
  * the cap of 8 messages per robot: draft step, send question and chances are all skipped (no call) at the cap;
  * TeamBrain.chance (message chance between decisions) and its endpoint /chance of brain_server.py;
  * second message change (2026-11-15): the robot is told its cap and what a message is for (one sentence in the task text), sees
    its own "Messages left: N" in the draft step, the send question and the chance, the chance says "silence unless something is
    new", and one robot sends at most one message per simulated instant (destination + door question on the same tick);
  * reply chance (2026-11-15, last change): a message written at a chance between decisions is recorded with via="chance" and a message
    written at a decision point has no `via`; brain_server.py /poll with chance=true counts only decision-point messages (a reply
    written at a chance does not open a chance), while the plain /poll still counts every message (re-decision trigger unchanged);
  * T0 is untouched.

Run from the project folder:  python3 -B -m unittest brain.tests.test_messaging -v
"""
import hashlib
import json
import re
import sys
import tempfile
import threading
import unittest
import urllib.request
from pathlib import Path
from unittest import mock

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))
sys.dont_write_bytecode = True

import brain_server  # noqa: E402
from brain import CHANCE_NOTE, MAX_MESSAGES, MESSAGE_RULE, TeamBrain  # noqa: E402
from brain.planning import FINAL, FINAL_SEND, SEND_EXTRA, _send_answer, _send_flag  # noqa: E402
from brain.tests.test_brain_v2 import DRAFT_LINE, GOAL, OPTIONS, Stub, message_prompts, progress_of  # noqa: E402

_TEMP = []
DEST = [{"key": "zone:sign11", "text": "transport the box I am holding to the <sign11 zone>"},
        {"key": "wait", "text": "wait here, holding the box"}]
DOOR = [{"key": "go", "text": "carry the box through the door now (one robot at a time fits)"},
        {"key": "wait", "text": "wait here before going to the door"}]
REPORT = [{"key": "continue", "text": "finish my run"}]
POINTS = {"pick": OPTIONS, "destination": DEST, "door": DOOR, "report": REPORT}


def tearDownModule():
    for tmp in _TEMP:
        tmp.cleanup()


def make(team, robots=("r1", "r2"), stub=None, leader=None, **kw):
    tmp = tempfile.TemporaryDirectory()
    _TEMP.append(tmp)
    stub = stub or Stub()
    return TeamBrain(team, list(robots), GOAL, client=stub, log_dir=Path(tmp.name), leader=leader, **kw), stub


def choice_prompts(stub, robot=None):
    return [p for p in stub.prompts if p.endswith("So the answer is option")
            and (robot is None or progress_of(p)["robot"] == robot)]


def listing(prompt):
    block = re.search(r"Available actions:\n(.*)\nAnswer:", prompt, re.S)[1].splitlines()
    return [tuple(line.split(". ", 1)) for line in block]


class Raw(Stub):
    """Stub whose choice answer is exactly `answer` (a string) whenever a draft is shown."""

    def __init__(self, answer, **kw):
        super().__init__(**kw)
        self.answer = answer

    def call(self, prompt, response_format=None):
        if prompt.endswith("So the answer is option") and DRAFT_LINE in prompt:
            self.prompts.append(prompt)
            return {"raw_output": self.answer}
        return super().call(prompt, response_format)


class SendWithAction(unittest.TestCase):
    def test_action_and_message_together_without_using_the_turn(self):
        for team in ("T1", "T2"):
            with self.subTest(team=team):
                b, stub = make(team, stub=Stub(send={"r1": 1}))
                out = b.decide("r1", 12.0, "pick", OPTIONS)
                self.assertEqual(out["option"], "box:0")                       # the first listed action, not 'wait'
                self.assertEqual(len(out["sent"]), 1)
                self.assertEqual(out["sent"][0]["deliver_at"], 14.0)
                self.assertEqual(out["sent"][0]["to"], ["r2"])
                self.assertTrue(out["sent_with_action"])
                self.assertEqual((out["draft"], out["send"], out["calls"]), (True, True, 3))   # draft + reasoning + choice
                self.assertEqual(out["wait_s"], 0.0)                           # an action, not a wait
                self.assertEqual(b.record()["decisions"]["r1"][0]["sent"][0]["text"], out["sent"][0]["text"])

    def test_every_decision_point_can_send_with_its_action(self):
        for team in ("T1", "T2"):
            for point, options in POINTS.items():
                with self.subTest(team=team, point=point):
                    b, stub = make(team, stub=Stub(send={"r1": 1}))
                    out = b.decide("r1", 12.0, point, options)
                    self.assertEqual(out["option"], options[0]["key"])
                    self.assertEqual((len(out["sent"]), out["sent_with_action"], out["send"], out["send_source"]), (1, True, True, "json"))
                    self.assertEqual(out["calls"], 3)

    def test_the_tail_of_the_choice_prompt_asks_for_send_only_when_a_draft_is_shown(self):
        b, stub = make("T1")
        b.decide("r1", 12.0, "pick", OPTIONS)
        self.assertTrue(choice_prompts(stub)[0].endswith("\n" + FINAL_SEND))
        self.assertTrue(FINAL_SEND.endswith("So the answer is option"))
        self.assertIn("send:true or send:false", FINAL_SEND)

        class Silent(Stub):
            def call(self, prompt, response_format=None):
                if "generate a short message" in prompt:
                    self.prompts.append(prompt)
                    return {"raw_output": json.dumps({"message": ""})}
                return super().call(prompt, response_format)
        for team, stub_ in (("T1", Silent()), ("T0", Stub())):
            b, stub = make(team, stub=stub_)
            b.decide("r1", 12.0, "pick", OPTIONS)
            self.assertTrue(choice_prompts(stub)[0].endswith("\n" + FINAL), team)
            self.assertNotIn("send:true", choice_prompts(stub)[0])

    def test_a_bare_label_or_prose_answer_is_read_from_its_text(self):
        # earlier real runs: 274 of 324 choice answers were bare labels; the model may say it in words instead of JSON
        cases = [("B, send:true", True, "text"), ("B (send: false)", False, "text"), ("A. send", True, "text"),
                 ("B, do not send", False, "text"), ("B - not sending it", False, "text"), ("A, no send", False, "text"),
                 ("I pick B and send the message", True, "text"), ("B, sending is false", False, "text"),
                 ("B", None, None), ("A.", None, None), ("go grasp target object", None, None), ("", None, None)]
        for answer, expected, source in cases:
            with self.subTest(answer=answer):
                self.assertEqual(_send_answer({"action": answer}), (expected, source))
        self.assertEqual(_send_answer({"action": "B", "send": True}), (True, "json"))          # the field comes first
        self.assertEqual(_send_answer({"action": "B, send:true", "send": False}), (False, "json"))
        self.assertEqual(_send_answer({"action": "B, send:true", "send": "maybe"}), (True, "text"))
        for raw, expected in (("B, send:true", True), ("B", None), ("B, do not send", False)):
            with self.subTest(raw=raw):
                b, _ = make("T1", stub=Raw(raw))
                out = b.decide("r1", 12.0, "pick", OPTIONS)
                self.assertEqual((out["option"], out["send"], bool(out["sent"])), ("wait", expected, expected is True))   # B = 'wait here for now' in OPTIONS

    def test_prompt_shows_the_draft_apart_from_the_list_and_asks_for_send(self):
        b, stub = make("T1", stub=Stub(send={"r1": 1}))
        b.decide("r1", 12.0, "pick", OPTIONS)
        prompt = choice_prompts(stub)[0]
        self.assertEqual([t for _, t in listing(prompt)], [o["text"] for o in OPTIONS])    # no 'send a message' line in the list
        self.assertNotIn("send a message:", prompt)
        draft = re.search(r"^" + re.escape(DRAFT_LINE) + r"(\{.*\})$", prompt, re.M)
        self.assertIsNotNone(draft)
        self.assertEqual(json.loads(draft[1])["message"], "r1 msg 1")                      # the candidate the message step wrote
        self.assertLess(prompt.index(DRAFT_LINE), prompt.index("Available actions:"))
        self.assertIn("Answer: " + SEND_EXTRA, prompt)
        self.assertTrue(all(SEND_EXTRA in p for p in stub.prompts if "choose the best available action" in p))   # the reasoning call too

    def test_without_a_draft_the_prompt_has_neither_the_draft_line_nor_the_send_question(self):
        class Silent(Stub):
            def call(self, prompt, response_format=None):
                if "generate a short message" in prompt:
                    self.prompts.append(prompt)
                    return {"raw_output": json.dumps({"message": ""})}
                return super().call(prompt, response_format)

        b, stub = make("T1", stub=Silent(send={"r1": 9}))
        out = b.decide("r1", 12.0, "pick", OPTIONS)
        self.assertEqual((out["sent"], out["calls"]), ([], 3))
        self.assertNotIn("draft", out)
        for prompt in stub.prompts:
            self.assertNotIn(DRAFT_LINE, prompt)
            self.assertNotIn('"send"', prompt)
        self.assertIn('Return an action or option label, optionally as {"action":"text"}.', choice_prompts(stub)[0])

    def test_a_draft_that_is_not_sent_is_recorded_as_a_draft_with_send_false(self):
        b, stub = make("T1")                                                 # the stub answers send:false
        out = b.decide("r1", 12.0, "pick", OPTIONS)
        self.assertEqual((out["draft"], out["send"], out["sent"], out["calls"]), (True, False, [], 3))
        self.assertNotIn("sent_with_action", out)
        self.assertEqual(b.record()["messages"], [])

    def test_an_answer_without_true_or_false_is_not_sent_and_recorded_as_missing(self):
        for answer in ('{"action":"A"}', '{"action":"A","send":"maybe"}', "A", '{"action":"A","send":null}', '{"action":"A","send":1}'):
            with self.subTest(answer=answer):
                b, _ = make("T1", stub=Raw(answer))
                out = b.decide("r1", 12.0, "pick", OPTIONS)
                self.assertEqual((out["option"], out["sent"], out["send"], out["send_source"]), ("box:0", [], None, None))
        for answer, expected in (('{"action":"A","send":true}', True), ('{"action":"A","send":"yes"}', True),
                                 ('{"action":"A","send":"false"}', False), ('{"action":"A","send":false}', False)):
            with self.subTest(answer=answer):
                b, _ = make("T1", stub=Raw(answer))
                out = b.decide("r1", 12.0, "pick", OPTIONS)
                self.assertEqual((out["send"], bool(out["sent"])), (expected, expected))
        self.assertEqual([_send_flag(v) for v in (True, False, "True", " no ", "x", None, 1, 0)],
                         [True, False, True, False, None, None, None, None])

    def test_wait_and_send_together(self):
        b, _ = make("T1", stub=Raw('{"action":"B","send":true}'))
        out = b.decide("r1", 12.0, "pick", OPTIONS)                           # B = 'wait here for now'
        self.assertEqual(out["option"], "wait")
        self.assertEqual((out["wait_s"], len(out["sent"]), out["sent_with_action"]), (2.0, 1, True))

    def test_messages_in_a_row_are_allowed(self):
        b, stub = make("T1", stub=Stub(send={"r1": 3}))
        outs = [b.decide("r1", 12.0 + k, "pick", OPTIONS) for k in range(3)]
        self.assertEqual([len(o["sent"]) for o in outs], [1, 1, 1])
        self.assertEqual([o["calls"] for o in outs], [3, 3, 3])                # every decision drafts: nothing is skipped after a send
        self.assertEqual(len(message_prompts(stub, "r1")), 3)
        actions = json.loads(re.search(r"^Previous actions: (\[.*\])$", message_prompts(stub, "r1")[-1], re.M)[1])
        self.assertEqual(actions, [OPTIONS[0]["text"], "send a message"] * 2)   # nothing is skipped or ruled out after a send

    def test_previous_actions_show_the_action_then_the_message(self):
        b, stub = make("T1", stub=Stub(send={"r1": 1}))
        b.decide("r1", 12.0, "pick", OPTIONS)
        b.decide("r1", 14.0, "pick", OPTIONS)
        actions = re.search(r"^Previous actions: (\[.*\])$", choice_prompts(stub)[-1], re.M)[1]
        self.assertEqual(json.loads(actions), [OPTIONS[0]["text"], "send a message"])


class Cap(unittest.TestCase):
    def test_eight_messages_then_no_draft_no_send_question_no_call(self):
        b, stub = make("T1", stub=Stub(send={"r1": 99}))
        calls = [b.decide("r1", 12.0 + k, "pick", OPTIONS)["calls"] for k in range(8)]
        self.assertEqual(calls, [3] * 8)
        self.assertEqual(b._sent_by("r1"), 8)
        before = len(stub.prompts)
        out = b.decide("r1", 30.0, "pick", OPTIONS)
        self.assertEqual((out["sent"], out["calls"], out.get("draft")), ([], 2, None))    # reasoning + choice only: no draft call
        new = stub.prompts[before:]
        self.assertEqual(len(new), 2)
        self.assertFalse(any("generate a short message" in p for p in new))
        self.assertFalse(any(DRAFT_LINE in p for p in new))
        self.assertTrue(all(SEND_EXTRA not in p for p in new))
        self.assertEqual(len(message_prompts(stub, "r1")), 8)                  # exactly 8 draft calls in the whole run
        self.assertEqual(len(b.record()["messages"]), 8)
        self.assertEqual(b.record()["max_messages_per_robot"], 8)
        self.assertEqual(b.record()["messages_by_robot"], {"r1": 8, "r2": 0})

    def test_the_cap_is_per_robot(self):
        b, stub = make("T1", stub=Stub(send={"r1": 99, "r2": 99}))
        for k in range(8):
            b.decide("r1", 12.0 + k, "pick", OPTIONS)
        out = b.decide("r2", 30.0, "pick", OPTIONS)
        self.assertEqual((len(out["sent"]), out["calls"]), (1, 3))             # r2 still has its own 8

    def test_pre_exchange_message_counts_and_chances_count_too(self):
        b, stub = make("T1", pre_exchange=True)
        b.max_messages = 1
        first = b.decide("r1", 12.0, "pick", OPTIONS)
        self.assertEqual(len(first["sent"]), 1)                                 # the forced message is the one allowed
        out = b.decide("r1", 14.0, "pick", OPTIONS)
        self.assertEqual((out["calls"], out.get("draft")), (2, None))           # no draft after the cap
        self.assertEqual(b.chance("r1", 20.0), dict(sent=[], calls=0, asked=False, final=True))

    def test_the_cap_ends_the_chances_and_makes_no_call(self):
        b, stub = make("T1")
        b.max_messages = 2
        for k, now in enumerate((20.0, 35.0)):
            out = b.chance("r1", now)
            self.assertEqual((len(out["sent"]), out["calls"], out["asked"]), (1, 1, True))
        self.assertTrue(out["final"])                                           # the second message reached the cap
        n = len(stub.prompts)
        self.assertEqual(b.chance("r1", 50.0), dict(sent=[], calls=0, asked=False, final=True))
        self.assertEqual(len(stub.prompts), n)                                  # no call at all
        self.assertEqual(b.chance("r2", 50.0)["asked"], True)                   # the other robot still has its chances

    def test_a_sent_message_and_a_chance_message_count_together(self):
        b, stub = make("T1", stub=Stub(send={"r1": 99}))
        b.max_messages = 3
        b.decide("r1", 12.0, "pick", OPTIONS)
        b.chance("r1", 30.0)
        out = b.decide("r1", 31.0, "pick", OPTIONS)
        self.assertEqual(len(out["sent"]), 1)
        self.assertEqual(b._sent_by("r1"), 3)
        self.assertEqual(b.decide("r1", 32.0, "pick", OPTIONS)["calls"], 2)


class Chance(unittest.TestCase):
    def test_one_draft_step_with_the_normal_message_prompt(self):
        b, stub = make("T1")
        b.decide("r1", 12.0, "pick", OPTIONS)
        base = message_prompts(stub, "r1")[0]
        out = b.chance("r1", 27.0)
        self.assertEqual((out["asked"], out["calls"], out["final"], len(out["sent"])), (True, 1, False, 1))
        self.assertEqual(out["sent"][0]["time"], 27.0)
        self.assertEqual(out["sent"][0]["deliver_at"], 29.0)
        self.assertEqual(out["sent"][0]["to"], ["r2"])
        prompt = message_prompts(stub, "r1")[-1]
        self.assertEqual(progress_of(prompt)["point"], "moving")
        # the same prompt as a decision's message step, apart from where the robot is in the run (point, time, previous actions,
        # messages left) and the one closing sentence of a chance (a reply only if there is something to answer or something new to say)
        norm = lambda p: re.sub(r'"point":"[a-z]+"|"time":[0-9.]+|^Previous actions: .*$|^Messages left: .*$', "", p, flags=re.M)
        self.assertEqual(norm(prompt), norm(base) + " " + CHANCE_NOTE)
        self.assertTrue(prompt.endswith("Use an empty message for silence. " + CHANCE_NOTE))
        self.assertEqual(stub.prompts[-1], prompt)                              # one call, no reasoning or choice step
        self.assertEqual(json.loads(b._messages[-1]["text"])["message"], "r1 msg 2")

    def test_an_empty_draft_is_silence_and_the_robot_is_asked_again_next_time(self):
        class Silent(Stub):
            def call(self, prompt, response_format=None):
                if "generate a short message" in prompt:
                    self.prompts.append(prompt)
                    return {"raw_output": json.dumps({"message": ""})}
                return super().call(prompt, response_format)

        b, stub = make("T1", stub=Silent())
        out = b.chance("r1", 15.0)
        self.assertEqual((out["sent"], out["calls"], out["asked"], out["final"]), ([], 1, True, False))
        self.assertEqual(b.record()["messages"], [])
        self.assertEqual(b.chance("r1", 30.0)["calls"], 1)
        self.assertEqual(len(b.record()["chances"]["r1"]), 2)                    # silent asks are recorded (they cost a call)

    def test_a_message_from_a_chance_reaches_the_other_robot_after_two_seconds(self):
        b, stub = make("T1")
        b.chance("r1", 20.0)
        b.decide("r2", 21.99, "pick", OPTIONS)
        self.assertNotIn("r1 msg 1", choice_prompts(stub, "r2")[-1])
        b.decide("r2", 22.0, "pick", OPTIONS)
        self.assertIn("r1 msg 1", choice_prompts(stub, "r2")[-1])

    def test_t2_routing_for_chances_and_for_messages_sent_with_actions(self):
        robots = ("r1", "r2", "r3")
        b, _ = make("T2", robots=robots)
        out = {rid: b.chance(rid, 20.0 + i)["sent"][0]["to"] for i, rid in enumerate(robots)}
        self.assertEqual(out, {"r1": ["r2", "r3"], "r2": ["r1"], "r3": ["r1"]})
        b, _ = make("T2", robots=robots, stub=Stub(send={r: 1 for r in robots}))
        sent = {rid: b.decide(rid, 1.0 + i, "pick", OPTIONS)["sent"][0]["to"] for i, rid in enumerate(robots)}
        self.assertEqual(sent, {"r1": ["r2", "r3"], "r2": ["r1"], "r3": ["r1"]})
        b, _ = make("T2", robots=robots, leader="r2")
        out = {rid: b.chance(rid, 20.0 + i)["sent"][0]["to"] for i, rid in enumerate(robots)}
        self.assertEqual(out, {"r1": ["r2"], "r2": ["r1", "r3"], "r3": ["r2"]})
        b, stub = make("T2", robots=robots)
        b.chance("r1", 20.0)
        b.decide("r3", 30.0, "destination", OPTIONS)
        self.assertIn("r1 msg 1", choice_prompts(stub, "r3")[-1])

    def test_t0_and_t3_are_not_asked_and_nothing_is_touched(self):
        b, stub = make("T0")
        record = b.record()
        self.assertEqual(b.chance("r1", 20.0), dict(sent=[], calls=0, asked=False, final=True))
        self.assertEqual(stub.prompts, [])
        self.assertEqual(b._now, -1.0)                                           # not even the clock of the planner moved
        self.assertEqual(b.record(), record)
        for key in ("max_messages_per_robot", "messages_by_robot", "chances"):
            self.assertNotIn(key, record)
        b, stub = make("T3")
        self.assertTrue(b.chance("r1", 20.0)["final"])
        self.assertEqual(stub.prompts, [])

    def test_a_halted_robot_gets_no_chance_and_a_failed_chance_does_not_halt(self):
        b, stub = make("T1", stub=Stub(fail=("r2",)))
        out = b.chance("r2", 20.0)
        self.assertEqual((out["asked"], out["final"], out["reason"], out["sent"]), (True, True, "RuntimeError", []))
        self.assertIsNone(b._halts["r2"])                                        # an optional step never halts the robot
        self.assertEqual(b.record()["chances"]["r2"][0]["reason"], "RuntimeError")
        n = len(stub.prompts)
        b.decide("r2", 21.0, "pick", OPTIONS)                                    # its next decision fails and halts it, as before
        self.assertEqual(b._halts["r2"], "RuntimeError")
        self.assertEqual(b.chance("r2", 40.0), dict(sent=[], calls=0, asked=False, final=True))
        self.assertGreater(n, 0)

    def test_the_call_cap_ends_chances_without_halting(self):
        b, stub = make("T1")
        b.max_calls = 2
        self.assertEqual(b.chance("r1", 20.0)["calls"], 1)
        self.assertEqual(b.chance("r1", 40.0)["calls"], 1)
        out = b.chance("r1", 60.0)
        self.assertEqual((out["calls"], out["final"], out["reason"]), (0, True, "Robot call cap reached"))
        self.assertIsNone(b._halts["r1"])
        self.assertEqual(b.record()["calls_by_robot"]["r1"], 2)

    def test_times_must_not_go_back(self):
        b, _ = make("T1")
        b.decide("r1", 30.0, "pick", OPTIONS)
        with self.assertRaises(ValueError):
            b.chance("r1", 29.0)
        b.chance("r1", 45.0)
        with self.assertRaises(ValueError):
            b.decide("r2", 44.0, "pick", OPTIONS)                                # a chance moves the planner's clock like a decision

    def test_the_cap_and_the_record_keys_exist_only_for_talking_structures(self):
        for team in ("T1", "T2"):
            b, _ = make(team)
            self.assertEqual(b.record()["max_messages_per_robot"], 8)
        self.assertNotIn("chances", make("T1")[0].record())                      # only when a chance was asked

    def test_chance_does_not_change_what_decide_does_with_the_same_time(self):
        a, _ = make("T1")
        c, _ = make("T1")
        c.chance("r1", 10.0)
        self.assertEqual(a.decide("r1", 12.0, "pick", OPTIONS)["calls"], c.decide("r1", 12.0, "pick", OPTIONS)["calls"])


def goal_line(prompt):
    return re.search(r"^Goal: (.*)$", prompt, re.M)[1]


def left(prompt):
    """The N of the 'Messages left: N' line of a prompt (None when the prompt has no such line)."""
    found = re.findall(r"^Messages left: (\d+)$", prompt, re.M)
    assert len(found) <= 1, "one line at most"
    return int(found[0]) if found else None


def drafts(stub, robot):
    return [p for p in stub.prompts if "generate a short message" in p and progress_of(p)["robot"] == robot]


def drafted_choices(stub, robot):
    return [p for p in choice_prompts(stub, robot) if DRAFT_LINE in p]


class TaskSentenceAndAllowance(unittest.TestCase):
    """The robot is told its cap and what a message is for; every message prompt shows its own remaining count."""

    RULE = ("You can send at most 8 messages in your whole run. Send a message only when it tells your teammates something they "
            "need and do not already know; repeated or unnecessary messages lower the team's score.")

    def test_the_task_text_ends_with_the_message_sentence_in_every_prompt_of_t1_and_t2(self):
        self.assertEqual(MESSAGE_RULE % MAX_MESSAGES, self.RULE)                  # the wording the user asked for, pinned
        for team in ("T1", "T2"):
            b, stub = make(team, stub=Stub(send={"r1": 5}))
            b.decide("r1", 12.0, "pick", OPTIONS)
            b.decide("r2", 12.0, "pick", OPTIONS)
            b.chance("r1", 27.0)
            self.assertEqual(len(stub.prompts), 7)                                      # r1: draft, reasoning, choice; r2: the same; r1 chance
            for prompt in stub.prompts:
                self.assertEqual(goal_line(prompt), GOAL + " " + self.RULE, team)

    def test_the_number_comes_from_the_cap(self):
        b, stub = make("T1")
        b.max_messages = 3                                                          # what test code and runs may set per brain
        b.decide("r1", 12.0, "pick", OPTIONS)
        self.assertTrue(all("at most 3 messages in your whole run" in goal_line(p) for p in stub.prompts))
        with mock.patch("brain.MAX_MESSAGES", 5):                                   # the module constant is the default cap
            b, stub = make("T2")
        b.decide("r1", 12.0, "pick", OPTIONS)
        self.assertTrue(all("at most 5 messages in your whole run" in goal_line(p) for p in stub.prompts))
        self.assertTrue(all(left(p) in (5, None) for p in stub.prompts))

    def test_t0_gets_neither_the_sentence_nor_a_count(self):
        b, stub = make("T0")
        b.decide("r1", 12.0, "pick", OPTIONS)
        b.chance("r1", 27.0)                                                        # T0 cannot talk: nothing is asked
        self.assertTrue(stub.prompts)
        for prompt in stub.prompts:
            self.assertEqual(goal_line(prompt), GOAL)
            self.assertNotIn("Messages left", prompt)
            self.assertNotIn("messages in your whole run", prompt)

    def test_the_count_is_in_the_draft_step_the_reasoning_and_choice_prompts_and_the_chance(self):
        b, stub = make("T1", stub=Stub(send={"r1": 99}))
        b.decide("r1", 12.0, "pick", OPTIONS)
        b.decide("r1", 14.0, "pick", OPTIONS)
        b.chance("r1", 29.0)
        step = [(p, left(p)) for p in stub.prompts if progress_of(p)["robot"] == "r1"]
        self.assertTrue(all(n is not None for _, n in step))                        # draft, reasoning, choice (a draft is shown) and chance
        # decision 1: three calls with 8, decision 2: three calls with 7, the chance: one call with 6
        self.assertEqual([n for _, n in step], [8, 8, 8, 7, 7, 7, 6])
        self.assertEqual(len(drafted_choices(stub, "r1")), 2)
        draft_prompt = drafts(stub, "r1")[0]
        self.assertLess(draft_prompt.index("Messages left: 8"), draft_prompt.index("Note: The generated message"))
        choice = drafted_choices(stub, "r1")[0]
        lines = choice.split("\n")
        i = next(k for k, l in enumerate(lines) if l.startswith(DRAFT_LINE))
        self.assertEqual((lines[i + 1], lines[i + 2]), ("Messages left: 8", "Available actions:"))   # right under the draft it is about

    def test_a_choice_without_a_draft_shows_no_count(self):
        class Silent(Stub):
            def call(self, prompt, response_format=None):
                if "generate a short message" in prompt:
                    self.prompts.append(prompt)
                    return {"raw_output": json.dumps({"message": ""})}
                return super().call(prompt, response_format)
        b, stub = make("T1", stub=Silent())
        b.decide("r1", 12.0, "pick", OPTIONS)
        self.assertEqual([left(p) for p in stub.prompts], [8, None, None])          # the draft step only; reasoning and choice have no send question

    def test_the_count_is_the_robots_own_and_counts_every_kind_of_message(self):
        b, stub = make("T1", stub=Stub(send={"r1": 99, "r2": 99}), pre_exchange=True)
        b.decide("r1", 1.0, "pick", OPTIONS)                                        # the forced pre-exchange message of r1 (count 1)
        b.decide("r2", 1.0, "pick", OPTIONS)                                        # r2's own forced message; r1's count must not move
        b.decide("r1", 20.0, "pick", OPTIONS)                                       # decision-time message (count 2)
        b.chance("r1", 40.0)                                                        # chance message (count 3)
        b.decide("r2", 41.0, "pick", OPTIONS)
        self.assertEqual([left(p) for p in drafts(stub, "r1")], [8, 7, 6])
        self.assertEqual([left(p) for p in drafts(stub, "r2")], [8, 7])
        self.assertEqual([left(p) for p in drafted_choices(stub, "r1")], [7])       # the same N as the draft step of the same decision
        self.assertEqual(b._sent_by("r1"), 3)

    def test_one_left_then_none_the_last_message_is_announced_as_one(self):
        b, stub = make("T1", stub=Stub(send={"r1": 99}))
        for k in range(8):
            b.decide("r1", 12.0 + k, "pick", OPTIONS)
        self.assertEqual([left(p) for p in drafts(stub, "r1")], [8, 7, 6, 5, 4, 3, 2, 1])
        self.assertEqual(len(drafts(stub, "r1")), 8)
        before = len(stub.prompts)
        b.decide("r1", 30.0, "pick", OPTIONS)                                       # at the cap nothing is drafted or asked: no prompt shows 0
        self.assertNotIn(0, [left(p) for p in stub.prompts[before:] if left(p) is not None])

    def test_every_plain_way_of_saying_nothing_is_silence_and_ends_nothing(self):
        # The new sentences ask the model for an empty message more often. RealLLM.call passes a completion whose content is the
        # empty string "" (it raises only when content is not a string at all, e.g. null: a pre-existing path, see docs/planning_messages.md).
        for raw in ("", "   \n", '""', '{"message": ""}', '{"message":"","facts":[]}'):
            class Quiet(Stub):
                def call(self, prompt, response_format=None, raw=raw):
                    if "generate a short message" in prompt:
                        self.prompts.append(prompt)
                        return {"raw_output": raw}
                    return super().call(prompt, response_format)
            with self.subTest(raw=raw):
                b, stub = make("T1", stub=Quiet())
                chance = b.chance("r1", 27.0)
                self.assertEqual((chance["sent"], chance["asked"], chance["final"], chance["calls"]), ([], True, False, 1))
                out = b.decide("r1", 28.0, "pick", OPTIONS)
                self.assertEqual((out["sent"], out.get("halted"), out["calls"]), ([], None, 3))      # draft, reasoning, choice
                self.assertEqual(b.record()["messages"], [])

    def test_the_chance_sentence_is_only_in_chance_prompts(self):
        b, stub = make("T2", stub=Stub(send={"r1": 1}))                              # T2: r1 is the leader, r2 sends to r1
        b.decide("r2", 12.0, "pick", OPTIONS)
        b.chance("r2", 27.0)
        moving = [p for p in stub.prompts if progress_of(p)["point"] == "moving"]
        self.assertEqual(len(moving), 1)
        self.assertTrue(moving[0].endswith(CHANCE_NOTE))
        self.assertIn("something new", CHANCE_NOTE)
        self.assertIn("has just arrived", CHANCE_NOTE)                           # a chance is offered because a message reached the robot
        self.assertIn("reply", CHANCE_NOTE)
        self.assertIn('return an empty message ("")', CHANCE_NOTE)
        others = [p for p in stub.prompts if progress_of(p)["point"] != "moving"]
        self.assertTrue(others)
        self.assertTrue(all(CHANCE_NOTE not in p for p in others))
        self.assertTrue(all(p.count(CHANCE_NOTE) <= 1 for p in stub.prompts))


class OneMessagePerInstant(unittest.TestCase):
    """Real run CF2-C01-T1-r1: the destination question and the door question of r1 fell on the same tick (38.5 s) and both sent."""

    def test_the_second_question_of_the_same_instant_has_no_draft_and_no_send_question(self):
        b, stub = make("T1", stub=Stub(send={"r1": 99, "r2": 99}))
        first = b.decide("r1", 38.5, "destination", DEST)
        second = b.decide("r1", 38.5, "door", DOOR)
        self.assertEqual((len(first["sent"]), first["calls"], first["draft"]), (1, 3, True))
        self.assertEqual((second["sent"], second["calls"], "draft" in second, "send" in second), ([], 2, False, False))   # reasoning + choice
        self.assertEqual(second["option"], "go")                                    # the action is chosen as always
        self.assertEqual(len(drafts(stub, "r1")), 1)
        self.assertEqual(len(drafted_choices(stub, "r1")), 1)
        self.assertTrue(choice_prompts(stub, "r1")[-1].endswith("\n" + FINAL))     # the plain choice question
        self.assertEqual([m["time"] for m in b.record()["messages"] if m["from"] == "r1"], [38.5])
        third = b.decide("r1", 39.5, "destination", DEST)                           # the next instant drafts again
        self.assertEqual((len(third["sent"]), third["calls"]), (1, 3))

    def test_it_is_per_robot_and_per_instant(self):
        b, stub = make("T1", stub=Stub(send={"r1": 99, "r2": 99}))
        self.assertEqual(len(b.decide("r1", 38.5, "destination", DEST)["sent"]), 1)
        self.assertEqual(len(b.decide("r2", 38.5, "destination", DEST)["sent"]), 1)   # the teammate's message does not count for r2
        self.assertEqual(len(b.decide("r1", 38.6, "door", DOOR)["sent"]), 1)            # 0.1 s later is another instant
        self.assertEqual(b._sent_by("r1"), 2)

    def test_a_draft_that_was_not_sent_does_not_block_the_next_question_of_the_instant(self):
        b, stub = make("T1", stub=Stub(send={}))                                    # drafts, never sends
        self.assertEqual(b.decide("r1", 38.5, "destination", DEST)["sent"], [])
        second = b.decide("r1", 38.5, "door", DOOR)
        self.assertEqual((second["calls"], second["draft"], second["send"]), (3, True, False))

    def test_t2_and_the_pre_exchange_follow_the_same_rule(self):
        b, stub = make("T2", stub=Stub(send={"r1": 99, "r2": 99}))
        b.decide("r2", 38.5, "destination", DEST)
        self.assertEqual(b.decide("r2", 38.5, "door", DOOR)["calls"], 2)
        b, stub = make("T1", stub=Stub(send={"r1": 99}), pre_exchange=True)
        forced = b.decide("r1", 12.0, "pick", OPTIONS)                              # pre-exchange: the forced message holds the decision
        self.assertEqual((len(forced["sent"]), forced["calls"]), (1, 1))
        later = b.decide("r1", 12.0, "pick", OPTIONS)                               # the same instant: the held decision may not draft again
        self.assertEqual(later["sent"], [])

    def test_a_chance_in_the_instant_of_a_message_is_skipped_and_does_not_end_the_chances(self):
        b, stub = make("T1", stub=Stub(send={"r1": 99}))
        b.decide("r1", 27.0, "destination", DEST)                                   # sent at 27.0
        prompts = len(stub.prompts)
        out = b.chance("r1", 27.0)
        self.assertEqual(out, dict(sent=[], calls=0, asked=False, final=False))     # final stays False: the bridge keeps offering chances
        self.assertEqual(len(stub.prompts), prompts)
        self.assertNotIn("chances", b.record())                                     # not asked, nothing recorded
        again = b.chance("r1", 42.0)
        self.assertEqual((again["asked"], again["calls"], len(again["sent"])), (True, 1, 1))
        # and the other way round: a decision in the instant of a chance message has no draft
        b, stub = make("T1", stub=Stub(send={"r1": 99}))
        self.assertEqual(len(b.chance("r1", 27.0)["sent"]), 1)
        out = b.decide("r1", 27.0, "destination", DEST)
        self.assertEqual((out["sent"], out["calls"], "draft" in out), ([], 2, False))

    def test_a_silent_chance_does_not_block_a_decision_of_the_instant(self):
        class Silent(Stub):
            def call(self, prompt, response_format=None):
                if "generate a short message" in prompt:
                    self.prompts.append(prompt)
                    return {"raw_output": json.dumps({"message": ""})}
                return super().call(prompt, response_format)
        b, stub = make("T1", stub=Silent())
        self.assertEqual(b.chance("r1", 27.0)["sent"], [])
        self.assertEqual(b.decide("r1", 27.0, "destination", DEST)["calls"], 3)       # silence is not a message


class OrderAndPreExchange(unittest.TestCase):
    def test_reverse_order_reverses_only_the_actions(self):
        f, f_stub = make("T1", stub=Stub(send={"r1": 1}))
        r, r_stub = make("T1", stub=Stub(send={"r1": 1}), option_order="reverse")
        f.decide("r1", 12.0, "pick", OPTIONS)
        r.decide("r1", 12.0, "pick", OPTIONS)
        fl, rl = listing(choice_prompts(f_stub)[0]), listing(choice_prompts(r_stub)[0])
        self.assertEqual([t for _, t in rl], [t for _, t in reversed(fl)])
        cut = lambda p: re.sub(r"Available actions:\n.*\nAnswer:", "", p, flags=re.S)
        self.assertEqual(cut(choice_prompts(f_stub)[0]), cut(choice_prompts(r_stub)[0]))     # the draft line is the same
        self.assertEqual(len(r.record()["messages"]), 1)

    def test_pre_exchange_decision_after_the_forced_message_may_draft_again(self):
        b, stub = make("T1", pre_exchange=True)
        b.decide("r1", 12.0, "pick", OPTIONS)
        b.decide("r2", 12.0, "pick", OPTIONS)
        out = b.decide("r1", 14.0, "pick", OPTIONS)
        self.assertEqual((out["calls"], out["draft"]), (3, True))
        self.assertEqual(out["wait_s"], 0.0)

    def test_forced_message_is_not_marked_as_sent_with_an_action(self):
        b, _ = make("T1", pre_exchange=True)
        out = b.decide("r1", 12.0, "pick", OPTIONS)
        self.assertEqual((out["option"], len(out["sent"])), ("wait", 1))
        self.assertNotIn("sent_with_action", out)                                # the bridge asks again 2 s later, as before


class T0Untouched(unittest.TestCase):
    def test_t0_prompts_have_no_draft_and_no_send_wording_and_make_no_message_call(self):
        b, stub = make("T0", stub=Stub(send={"r1": 9, "r2": 9}))
        for now, rid, point, options in ((1.0, "r1", "pick", OPTIONS), (9.0, "r2", "destination", DEST), (30.0, "r1", "report", [
                {"key": "continue", "text": "continue my task"}])):
            b.decide(rid, now, point, options)
        for prompt in stub.prompts:
            for word in (DRAFT_LINE, '"send"', "send a message", "generate a short message"):
                self.assertNotIn(word, prompt)
        self.assertEqual(b.record()["messages"], [])
        self.assertTrue(all("draft" not in d and "send" not in d for rows in b._decisions.values() for d in rows))


class ChanceReplyMark(unittest.TestCase):
    """A reply written at a chance is marked via="chance" in the record; nothing written at a decision point is."""

    def test_only_the_message_of_a_chance_has_via(self):
        for team in ("T1", "T2"):
            with self.subTest(team=team):
                b, stub = make(team, stub=Stub(send={"r1": 1, "r2": 1}))
                decided = b.decide("r1", 12.0, "pick", OPTIONS)
                self.assertNotIn("via", decided["sent"][0])
                replied = b.chance("r2", 14.0)
                self.assertEqual(replied["sent"][0]["via"], "chance")                # the answer carries it too (bridge log)
                messages = b.record()["messages"]
                self.assertEqual([(m["from"], m.get("via")) for m in messages], [("r1", None), ("r2", "chance")])
                self.assertEqual(b.record()["chances"]["r2"][0]["sent"][0]["via"], "chance")

    def test_the_pre_exchange_message_has_no_via(self):
        b, stub = make("T1", stub=Stub(send={"r1": 1}), pre_exchange=True)
        out = b.decide("r1", 0.0, "pick", OPTIONS)
        sent = [m for m in b.record()["messages"] if m["from"] == "r1"]
        self.assertTrue(sent)
        self.assertTrue(all("via" not in m for m in sent), sent)

    def test_via_is_not_shown_to_any_model(self):
        b, stub = make("T1", stub=Stub(send={"r1": 1, "r2": 1}))
        b.decide("r1", 12.0, "pick", OPTIONS)
        b.chance("r2", 14.0)
        b.decide("r1", 17.0, "destination", DEST)                                  # r1 reads r2's chance reply
        self.assertTrue(stub.prompts)
        self.assertTrue(all("via" not in p and "chance\"" not in p for p in stub.prompts))
        dialogue = [p for p in stub.prompts if progress_of(p)["robot"] == "r1" and progress_of(p)["time"] == 17.0]
        self.assertTrue(dialogue and all("r2 msg 1" in p for p in dialogue))         # r1 does read the reply, without its mark


class ServerEndpoint(unittest.TestCase):
    """brain_server.py really serving on localhost (no model: the stub client): /chance is a planner contact, so it moves `seen`
    (before the reply chance of 2026-11-15 it did not): the same message is answered once and the bridge's poll is false until
    another message arrives."""

    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        made = {}

        class Capture(brain_server.HTTPServer):
            def __init__(self, *a, **k):
                super().__init__(*a, **k)
                made["server"] = self

        argv = ["brain_server.py", "--team", "T1", "--port", "0", "--log-dir", str(Path(self.tmp.name) / "log")]
        stub = Stub(send={"r1": 1})
        self.stub = stub
        patches = [mock.patch.object(brain_server, "RealLLM", lambda *a, **k: stub), mock.patch.object(brain_server, "HTTPServer", Capture),
                   mock.patch.object(sys, "argv", argv)]
        for p in patches:
            p.start()
            self.addCleanup(p.stop)
        self.thread = threading.Thread(target=brain_server.main, daemon=True)
        self.thread.start()
        for _ in range(200):
            if "server" in made:
                break
            threading.Event().wait(0.01)
        self.server = made["server"]
        self.addCleanup(self.server.server_close)
        self.addCleanup(self.server.shutdown)
        self.port = self.server.server_address[1]

    def post(self, path, **body):
        request = urllib.request.Request("http://127.0.0.1:%d%s" % (self.port, path), data=json.dumps(body).encode(),
                                         headers={"Content-Type": "application/json"})
        with urllib.request.urlopen(request, timeout=20) as reply:
            return json.loads(reply.read())

    def test_chance_endpoint_answers_and_counts_as_a_contact_for_the_new_message_signal(self):
        sent = self.post("/decide", rid="r1", now_s=12.0, point="pick", options=OPTIONS)
        self.assertEqual(len(sent["sent"]), 1)
        self.assertFalse(self.post("/poll", rid="r2", now_s=13.0)["new"])        # not delivered yet (14.0)
        self.assertTrue(self.post("/poll", rid="r2", now_s=14.0)["new"])
        out = self.post("/chance", rid="r2", now_s=30.0)                         # r2 drafts between decisions and has read r1's message
        self.assertEqual((out["asked"], out["calls"], len(out["sent"])), (True, 1, 1))
        self.assertFalse(self.post("/poll", rid="r2", now_s=30.0)["new"])        # answered: a chance is a planner contact like a decision
        self.assertFalse(self.post("/poll", rid="r2", now_s=40.0)["new"])        # and stays so until another message arrives
        self.post("/decide", rid="r2", now_s=31.0, point="pick", options=OPTIONS)
        self.assertTrue(self.post("/poll", rid="r1", now_s=33.0)["new"])         # r2's chance message reaches r1 (30 + 2 s)
        self.assertEqual(self.post("/chance", rid="r1", now_s=34.0)["asked"], True)
        self.assertFalse(self.post("/poll", rid="r1", now_s=34.0)["new"])        # r1 answered it: the same message is not offered again
        record = self.post("/record")
        self.assertEqual([m["from"] for m in record["messages"]], ["r1", "r2", "r1"])
        self.assertEqual(sorted(record["chances"]), ["r1", "r2"])

    def test_a_reply_written_at_a_chance_does_not_open_a_chance_but_the_plain_poll_still_sees_it(self):
        sent = self.post("/decide", rid="r1", now_s=12.0, point="pick", options=OPTIONS)          # a message written at a decision point
        self.assertNotIn("via", sent["sent"][0])
        self.assertEqual(self.post("/poll", rid="r2", now_s=13.0, chance=True), {"new": False, "chance": True})   # not delivered yet (14.0)
        self.assertEqual(self.post("/poll", rid="r2", now_s=14.0, chance=True), {"new": True, "chance": True})    # it opens r2's chance
        self.assertEqual(self.post("/poll", rid="r2", now_s=14.0), {"new": True})                                # the flag changes nothing else
        reply = self.post("/chance", rid="r2", now_s=14.0)
        self.assertEqual(reply["sent"][0]["via"], "chance")                                                       # r2's reply, delivered at 16.0
        self.assertEqual(self.post("/poll", rid="r2", now_s=15.0, chance=True), {"new": False, "chance": True})   # r2 has read it
        # r1 receives the reply: it does NOT open r1's chance ...
        self.assertEqual(self.post("/poll", rid="r1", now_s=16.0, chance=True), {"new": False, "chance": True})
        # ... but the plain poll (re-decision trigger, waiting robots) still reacts to it, as before
        self.assertEqual(self.post("/poll", rid="r1", now_s=16.0), {"new": True})
        # a decision of r1 reads it (both marks move) and writes another message at the decision point: that one opens r2's chance again
        self.stub.send["r1"] = 2
        self.assertEqual(len(self.post("/decide", rid="r1", now_s=17.0, point="destination", options=DEST)["sent"]), 1)
        self.assertEqual(self.post("/poll", rid="r1", now_s=17.0), {"new": False})
        self.assertEqual(self.post("/poll", rid="r1", now_s=17.0, chance=True), {"new": False, "chance": True})
        self.assertEqual(self.post("/poll", rid="r2", now_s=19.0, chance=True), {"new": True, "chance": True})
        self.assertEqual(self.post("/chance", rid="r2", now_s=19.0)["sent"][0]["via"], "chance")
        self.assertEqual(self.post("/poll", rid="r2", now_s=19.0, chance=True), {"new": False, "chance": True})
        self.assertEqual(self.post("/poll", rid="r1", now_s=21.0, chance=True), {"new": False, "chance": True})   # the second reply: no chain
        self.assertEqual(self.post("/poll", rid="r1", now_s=21.0), {"new": True})
        record = self.post("/record")
        self.assertEqual([(m["from"], m.get("via")) for m in record["messages"]], [("r1", None), ("r2", "chance"), ("r1", None), ("r2", "chance")])

    def test_old_clients_still_work(self):
        self.assertEqual(self.post("/tell", rid="r1", facts={"progress": "x"}), {})
        self.assertIn("option", self.post("/decide", rid="r1", now_s=1.0, point="pick", options=OPTIONS))


if __name__ == "__main__":
    unittest.main()
