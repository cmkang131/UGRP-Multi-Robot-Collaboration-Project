"""Offline tests of the planner-side experiment conditions (stub LLM, no network, no paid call):
--option-order reverse and --pre-exchange (brain_server.py arguments, TeamBrain keyword arguments).

Run from the project folder:  python3 -B -m unittest brain.tests.test_conditions -v
"""
import hashlib
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
from brain import TeamBrain  # noqa: E402
from brain.tests.test_brain_v2 import DRAFT_LINE, GOAL, OPTIONS, Stub, message_prompts, progress_of  # noqa: E402

ORDERS = {"orders": [{"box": "blue", "count": 1, "zone": "sign11"}]}
DEST = [{"key": "zone:sign11", "text": "transport the box I am holding to the <sign11 zone>"},
        {"key": "zone:sign12", "text": "transport the box I am holding to the <sign12 zone>"},
        {"key": "zone:sign13", "text": "transport the box I am holding to the <sign13 zone>"},
        {"key": "wait", "text": "wait here, holding the box"}]
DOOR = [{"key": "go", "text": "carry the box through the door now (one robot at a time fits)"},
        {"key": "wait", "text": "wait here before going to the door"}]
REPORT = [{"key": "continue", "text": "continue my task"}]
POINTS = {"pick": OPTIONS, "destination": DEST, "door": DOOR, "report": REPORT}
_TEMP = []


def tearDownModule():
    for tmp in _TEMP:
        tmp.cleanup()


def make(team, robots=("r1", "r2"), stub=None, leader=None, **conditions):
    tmp = tempfile.TemporaryDirectory()
    _TEMP.append(tmp)
    stub = stub or Stub()
    brain = TeamBrain(team, list(robots), GOAL, client=stub, log_dir=Path(tmp.name), leader=leader, **conditions)
    for rid in robots:
        brain.tell(rid, ORDERS)
    return brain, stub


def listing(prompt):
    """[(label, text)] of the 'Available actions' block."""
    block = re.search(r"Available actions:\n(.*)\nAnswer:", prompt, re.S)[1].splitlines()
    return [tuple(line.split(". ", 1)) for line in block]


def choice_prompts(stub):
    return [p for p in stub.prompts if p.endswith("So the answer is option")]


def sha(text):
    return hashlib.sha256(text.encode()).hexdigest()


class TextChoosing(Stub):
    """Stub that picks the listed action containing `want` (so a changed order shows in which key comes back)."""

    def __init__(self, want, **kw):
        super().__init__(**kw)
        self.want = want

    def call(self, prompt, response_format=None):
        if prompt.endswith("So the answer is option"):
            self.prompts.append(prompt)
            label = next(l for l, t in listing(prompt) if self.want in t)
            return {"raw_output": json.dumps({"action": label})}
        return super().call(prompt, response_format)


class OptionOrder(unittest.TestCase):
    def test_default_is_forward_and_unchanged(self):
        brain, stub = make("T1")
        self.assertEqual(brain.option_order, "forward")
        brain.decide("r1", 12.0, "pick", OPTIONS)
        texts = [t for _, t in listing(choice_prompts(stub)[0])]
        self.assertEqual(texts, [o["text"] for o in OPTIONS])          # no 'send a message' line: the draft is shown apart
        self.assertIn(DRAFT_LINE, choice_prompts(stub)[0])
        self.assertNotIn("conditions", brain.record())

    def test_reverse_lists_the_whole_shown_list_backwards_with_letters_in_shown_order(self):
        for team in ("T0", "T1", "T2"):
            for point, options in POINTS.items():
                with self.subTest(team=team, point=point):
                    forward, f_stub = make(team)
                    reverse, r_stub = make(team, option_order="reverse")
                    forward.decide("r1", 12.0, point, options)
                    reverse.decide("r1", 12.0, point, options)
                    f_lists = [listing(p) for p in choice_prompts(f_stub)]
                    r_lists = [listing(p) for p in choice_prompts(r_stub)]
                    if point == "report" and team == "T0":
                        self.assertEqual((f_lists, r_lists), ([], []))      # T0 report: no choice step at all
                        continue
                    self.assertEqual(len(f_lists), 1)
                    self.assertEqual(len(r_lists), 1)
                    self.assertEqual([t for _, t in r_lists[0]], [t for _, t in reversed(f_lists[0])])
                    n = len(r_lists[0])
                    self.assertEqual([l for l, _ in r_lists[0]], [chr(65 + i) for i in range(n)])
                    # everything outside the listing is the same
                    cut = lambda p: re.sub(r"Available actions:\n.*\nAnswer:", "", p, flags=re.S)
                    self.assertEqual(cut(choice_prompts(f_stub)[0]), cut(choice_prompts(r_stub)[0]))

    def test_the_chosen_key_follows_the_text_not_the_position(self):
        for order in ("forward", "reverse"):
            brain, _ = make("T1", stub=TextChoosing("<sign12 zone>"), option_order=order)
            answer = brain.decide("r1", 30.0, "destination", DEST)
            self.assertEqual(answer["option"], "zone:sign12")

    def test_record_and_validation(self):
        brain, _ = make("T1", option_order="reverse")
        brain.decide("r1", 12.0, "pick", OPTIONS)
        self.assertEqual(brain.record()["conditions"], {"option_order": "reverse"})
        with self.assertRaises(ValueError):
            make("T1", option_order="shuffled")


class PreExchange(unittest.TestCase):
    def test_t0_is_rejected_everywhere(self):
        with self.assertRaises(ValueError):
            make("T0", pre_exchange=True)
        with self.assertRaises(ValueError):
            make("T3", pre_exchange=True)
        with self.assertRaises(SystemExit):
            with mock.patch("sys.stderr"):
                brain_server.parse_args(["--team", "T0", "--port", "1", "--log-dir", "/x", "--pre-exchange"])

    def test_server_main_builds_the_brain_with_the_conditions_without_starting_a_server(self):
        built = {}

        def make_brain(*a, **k):
            built["brain"] = TeamBrain(*a, **k)
            return built["brain"]

        with tempfile.TemporaryDirectory() as tmp, mock.patch.object(brain_server, "RealLLM", lambda *a, **k: Stub()), \
                mock.patch.object(brain_server, "TeamBrain", make_brain), mock.patch.object(brain_server, "HTTPServer") as server, \
                mock.patch.object(sys, "argv", ["brain_server.py", "--team", "T2", "--robots", "r1,r2,r3", "--port", "1", "--log-dir",
                                                str(Path(tmp) / "log"), "--option-order", "reverse", "--pre-exchange", "--leader", "r2"]):
            brain_server.main()
        server.assert_called_once()
        brain = built["brain"]
        self.assertEqual((brain.team, brain.option_order, brain.pre_exchange, brain.leader), ("T2", "reverse", True, "r2"))
        with tempfile.TemporaryDirectory() as tmp, mock.patch.object(brain_server, "RealLLM", lambda *a, **k: Stub()), \
                mock.patch.object(brain_server, "TeamBrain", make_brain), mock.patch.object(brain_server, "HTTPServer"), \
                mock.patch.object(sys, "argv", ["brain_server.py", "--team", "T1", "--port", "1", "--log-dir", str(Path(tmp) / "log")]):
            brain_server.main()
        self.assertEqual((built["brain"].option_order, built["brain"].pre_exchange), ("forward", False))

    def test_server_arguments(self):
        base = ["--team", "T1", "--port", "1", "--log-dir", "/x"]
        a = brain_server.parse_args(base)
        self.assertEqual((a.option_order, a.pre_exchange), ("forward", False))
        a = brain_server.parse_args(base + ["--option-order", "reverse", "--pre-exchange"])
        self.assertEqual((a.option_order, a.pre_exchange), ("reverse", True))
        with self.assertRaises(SystemExit):
            with mock.patch("sys.stderr"):
                brain_server.parse_args(base + ["--option-order", "sideways"])

    def test_first_pick_writes_one_message_with_the_normal_message_prompt_and_no_choice_step(self):
        plain, p_stub = make("T1")
        plain.decide("r1", 12.0, "pick", OPTIONS)
        brain, stub = make("T1", pre_exchange=True)
        out = brain.decide("r1", 12.0, "pick", OPTIONS)
        self.assertEqual((out["option"], out["calls"], len(out["sent"])), ("wait", 1, 1))
        self.assertEqual(out["wait_s"], 2.0)
        self.assertEqual(out["sent"][0]["deliver_at"], 14.0)
        self.assertEqual(out["sent"][0]["to"], ["r2"])
        self.assertTrue(out["sent"][0]["exchange"])                    # the record marks the forced message
        self.assertFalse(any(m.get("exchange") for m in plain.record()["messages"]))
        self.assertEqual(len(stub.prompts), 1)                       # the message module only: no reasoning, no choice
        self.assertEqual(sha(stub.prompts[0]), sha(message_prompts(p_stub, "r1")[0]))   # same prompt as the normal first message
        self.assertEqual(brain.record()["conditions"], {"pre_exchange": True})

    def test_first_real_decision_waits_for_the_peer_message_and_drafts_again(self):
        # no ban on a message after a message (2026-11-15): the decision after the forced one writes a draft like any decision
        brain, stub = make("T1", pre_exchange=True)
        a1 = brain.decide("r1", 12.0, "pick", OPTIONS)
        a2 = brain.decide("r2", 12.0, "pick", OPTIONS)
        self.assertTrue(a1["sent"] and a2["sent"])
        out = brain.decide("r1", 14.0, "pick", OPTIONS)               # r2's message (deliver 14.0) has arrived
        self.assertEqual(out["calls"], 3)                            # draft + reasoning + choice
        self.assertEqual(out["sent"], [])                            # the stub does not send
        prompt = choice_prompts(stub)[-1]
        self.assertIn(DRAFT_LINE, prompt)
        self.assertIn("r2 msg 1", prompt)                            # the peer's message is in the dialogue
        self.assertIn('"send a message"', prompt)                    # previous actions show the forced message

    def test_a_message_still_in_flight_holds_the_decision(self):
        brain, stub = make("T1", pre_exchange=True)
        brain.decide("r1", 12.0, "pick", OPTIONS)                    # delivered to r2 at 14.0
        brain.decide("r2", 13.0, "pick", OPTIONS)                    # delivered to r1 at 15.0
        held = brain.decide("r1", 14.0, "pick", OPTIONS)
        self.assertEqual((held["option"], held["calls"], held["sent"]), ("wait", 0, []))
        out = brain.decide("r1", 15.0, "pick", OPTIONS)
        self.assertEqual(out["calls"], 3)
        self.assertNotEqual(out["option"], "wait")

    def test_a_robot_that_never_asks_is_not_waited_for(self):
        brain, _ = make("T1", pre_exchange=True)
        brain.decide("r1", 12.0, "pick", OPTIONS)
        out = brain.decide("r1", 14.0, "pick", OPTIONS)               # r2 never decided (nothing graspable)
        self.assertEqual(out["calls"], 3)

    def test_silence_is_allowed_still_waits_for_the_others_and_asks_the_message_module_only_once(self):
        class SilentR1(Stub):
            def call(self, prompt, response_format=None):
                if "generate a short message" in prompt and progress_of(prompt)["robot"] == "r1":
                    self.prompts.append(prompt)
                    return {"raw_output": json.dumps({"message": ""})}
                return super().call(prompt, response_format)

        brain, stub = make("T1", stub=SilentR1(), pre_exchange=True)
        first = brain.decide("r1", 12.0, "pick", OPTIONS)           # r1 is asked first and is silent: it must still hold
        self.assertEqual((first["option"], first["sent"], first["calls"]), ("wait", [], 1))
        self.assertTrue(brain.decide("r2", 12.0, "pick", OPTIONS)["sent"])
        out = brain.decide("r1", 14.0, "pick", OPTIONS)               # r2's message has arrived
        self.assertEqual(out["calls"], 2)                            # reasoning + choice; no second message call
        self.assertEqual(len(message_prompts(stub, "r1")), 1)
        self.assertIn("r2 msg 1", choice_prompts(stub)[-1])
        self.assertFalse(any(t.startswith("send a message") for _, t in listing(choice_prompts(stub)[-1])))

    def test_both_silent_is_released_at_the_next_ask(self):
        class Silent(Stub):
            def call(self, prompt, response_format=None):
                if "generate a short message" in prompt:
                    self.prompts.append(prompt)
                    return {"raw_output": json.dumps({"message": ""})}
                return super().call(prompt, response_format)

        brain, _ = make("T1", stub=Silent(), pre_exchange=True)
        self.assertEqual(brain.decide("r1", 12.0, "pick", OPTIONS)["option"], "wait")
        self.assertEqual(brain.decide("r2", 12.0, "pick", OPTIONS)["option"], "wait")
        self.assertEqual(brain.decide("r1", 14.0, "pick", OPTIONS)["calls"], 2)
        self.assertEqual(brain.record()["messages"], [])

    def test_only_the_first_pick_decision_is_forced(self):
        brain, stub = make("T1", pre_exchange=True)
        brain.decide("r1", 12.0, "pick", OPTIONS)
        brain.decide("r1", 14.0, "pick", OPTIONS)
        out = brain.decide("r1", 40.0, "pick", OPTIONS)              # e.g. a second pick after a lost grasp
        self.assertEqual((out["sent"], out["calls"]), ([], 3))        # normal flow: message candidate offered, then reasoning, choice
        self.assertEqual([m["from"] for m in brain._messages], ["r1"])

    def test_other_points_are_not_forced(self):
        brain, stub = make("T1", pre_exchange=True)
        out = brain.decide("r1", 12.0, "destination", DEST)
        self.assertEqual(out["sent"], [])
        self.assertEqual(out["calls"], 3)                            # message candidate + reasoning + choice, as without the condition

    def test_t2_routing_follows_the_structure(self):
        brain, _ = make("T2", robots=("r1", "r2", "r3"), pre_exchange=True)
        sent = {rid: brain.decide(rid, 12.0, "pick", OPTIONS)["sent"][0] for rid in ("r1", "r2", "r3")}
        self.assertEqual(sent["r1"]["to"], ["r2", "r3"])             # the leader's message goes to everyone
        self.assertEqual(sent["r2"]["to"], ["r1"])                   # a member's goes to the leader only
        self.assertEqual(sent["r3"]["to"], ["r1"])
        # r2 waits only for what is addressed to it: the leader's message, delivered at 14.0 (not r3's)
        self.assertEqual(brain.decide("r2", 14.0, "pick", OPTIONS)["calls"], 3)

    def test_a_halted_robot_does_not_block_the_run(self):
        brain, _ = make("T1", stub=Stub(fail=("r2",)), pre_exchange=True)
        out = brain.decide("r2", 12.0, "pick", OPTIONS)
        self.assertTrue(out.get("halted"))
        self.assertEqual(brain.decide("r1", 12.0, "pick", OPTIONS)["calls"], 1)
        self.assertEqual(brain.decide("r1", 14.0, "pick", OPTIONS)["calls"], 3)


if __name__ == "__main__":
    unittest.main()
