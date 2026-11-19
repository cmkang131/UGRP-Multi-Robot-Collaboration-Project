"""Offline tests of the phase-2 switches (stub LLM, no network, no paid call): --talk free (say entries, say time, reading queue, streak, chance), --leader-binding
(assign lines, hold, lock, release, record), --leader-seed (election tie), --scene-file / --scene-id (rule sentence), N robots (--zones, --max-input-bytes,
--leader r1..rN, protocol plan examples), --map-doors. The default-off identity against the frozen planner is tools/identity_check.py.

Run from the link folder:  python3 -B -m unittest brain.tests.test_free_talk -v
"""
import contextlib
import io
import json
import re
import sys
import tempfile
import unittest
import zlib
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))
sys.dont_write_bytecode = True

import brain_server  # noqa: E402
from brain import FREE_RULE, MESSAGE_RULE, RULES_GOAL, TeamBrain  # noqa: E402
from brain import protocol as P  # noqa: E402
from brain.talk import (BIND_LEADER, CHANCE_FREE, FREE_ANSWER, FREE_RULE as TALK_RULE, HOLD_S, SILENT_TEXT, parse_assign, read_say, read_say_beside_action, read_time, say_time)  # noqa: E402
from brain.tests.test_brain_v2 import GOAL, progress_of  # noqa: E402
from brain.tests.test_protocol import DEST, DOOR, R3, pick_options  # noqa: E402

REPORT = [{"key": "continue", "text": "continue my task"}]
O3 = [{"box": "red", "count": 1, "zone": "sign11"}, {"box": "blue", "count": 1, "zone": "sign12"}, {"box": "red", "count": 1, "zone": "sign13"}]
_TEMP = []


def tearDownModule():
    for tmp in _TEMP:
        tmp.cleanup()


def listing_of(prompt):
    block = re.search(r"Available actions:\n(.*)\nAnswer:", prompt, re.S)[1].splitlines()
    return [(line.split(". ", 1)[0], line.split(". ", 1)[1]) for line in block]


class FreeStub:
    """Scripted model for free talk. say[rid] = list of (target, words): the next time the robot is offered that say entry it chooses it and writes the words.
    Everything else: the first listed body action (or what `choose(rid, entries)` returns as a label)."""

    def __init__(self, say=None, choose=None, raw=None):
        self.say = {rid: list(v) for rid, v in (say or {}).items()}
        self.choose, self.raw = choose, raw
        self.prompts, self.records = [], []

    def call(self, prompt, response_format=None):
        self.prompts.append(prompt)
        if self.raw is not None:
            return {"raw_output": self.raw(prompt) if callable(self.raw) else self.raw}
        robot = progress_of(prompt)["robot"]
        if "Return {\"reasoning\":\"text\"}." in prompt and not prompt.endswith("also \"say\":\"your words\"."):
            return {"raw_output": '{"reasoning":"stub"}'}
        entries = listing_of(prompt)
        queue = self.say.get(robot)
        if queue:
            target, words = queue[0]
            for label, text in entries:
                if text.startswith("say to %s:" % target):
                    queue.pop(0)
                    return {"raw_output": json.dumps({"reasoning": "r", "action": label, "say": words})}
        if self.choose:
            return {"raw_output": json.dumps({"reasoning": "r", "action": self.choose(robot, entries)})}
        body = [label for label, text in entries if not text.startswith("say to ")]
        return {"raw_output": json.dumps({"reasoning": "r", "action": body[0]})}

    def prompts_of(self, rid):
        return [p for p in self.prompts if progress_of(p)["robot"] == rid]


def make_free(team="T1", robots=R3, stub=None, orders=None, leader=None, **kw):
    tmp = tempfile.TemporaryDirectory()
    _TEMP.append(tmp)
    stub = stub or FreeStub()
    kw.setdefault("merge_calls", True)
    kw.setdefault("parser_fix", True)
    brain = TeamBrain(team, list(robots), GOAL, client=stub, log_dir=Path(tmp.name), leader=leader, talk="free", **kw)
    for rid in robots:
        brain.tell(rid, {"orders": (orders or {}).get(rid, []), "progress": "I am in the box room."})
    return brain, stub


def pick_for(rid, colours=("blue", "red", "red")):
    return [{"key": "box:%d" % i, "text": "go grasp target object <%s box> in the box room, %.1f m away, straight ahead of me (my label %s-box%d)" % (c, 1.0 + i, rid, i)}
            for i, c in enumerate(colours)] + [{"key": "wait", "text": "wait here for now"}, {"key": "finish", "text": "finish: there is nothing useful for me to do"}]


class Helpers(unittest.TestCase):
    def test_times_are_the_documented_values(self):
        self.assertAlmostEqual(say_time(257), 1.45 + 0.0036 * 257)
        self.assertAlmostEqual(read_time(257), 0.7 + 0.0018 * 257)
        self.assertGreater(say_time(153), 2.0 - 1e-3)              # about 153 chars: where the runner's 2 s floor stops mattering
        self.assertAlmostEqual(say_time(10, 2.0, 0.0), 2.0)

    def test_parse_assign(self):
        self.assertEqual(parse_assign("assign r2: blue -> sign12; assign r3: Red => sign11"), [("r2", "blue", "sign12"), ("r3", "Red", "sign11")])
        self.assertEqual(parse_assign("assign r2: <blue box> -> <sign12 zone>"), [("r2", "blue", "sign12")])
        self.assertEqual(parse_assign("Assign R4:  red to sign14"), [("r4", "red", "sign14")])
        self.assertEqual(parse_assign("please assign someone"), [])

    def test_read_say_shapes(self):
        menu = {"go grasp <blue box>": {"skill": "executor", "key": "box:0"}, "wait here for now": {"skill": "executor", "key": "wait"},
                "say to r2: <text>": {"skill": "say", "target": "r2", "to": ["r2"]}, "say to r3: <text>": {"skill": "say", "target": "r3", "to": ["r3"]},
                "say to everyone: <text>": {"skill": "say", "target": "everyone", "to": ["r2", "r3"]}}
        label = lambda i: "ABCDEFGH"[i]
        rs = lambda result, text: read_say(menu, result, text, label)
        self.assertEqual(rs({}, "say to r2: take the blue box")["body"], "take the blue box")
        self.assertEqual(rs({}, "say to r2: take the blue box")["entry"], "say to r2: <text>")
        self.assertEqual(rs({"say": "hi"}, "D")["body"], "hi")                       # a bare label of a say entry plus the say field
        self.assertEqual(rs({"say": "hi"}, "D")["target"], "r3")
        self.assertEqual(rs({}, "E: all of you wait here for now")["target"], "everyone")  # label with words after it; words may contain another option's text
        self.assertEqual(rs({}, "E: all of you wait here for now")["body"], "all of you wait here for now")
        self.assertEqual(rs({"say": "hello"}, "say to everyone: <text>")["body"], "hello")  # the placeholder is not words, the field is
        self.assertEqual(rs({}, "say to everyone: <text>")["body"], "")
        self.assertIsNone(rs({}, "say to r5: x")["entry"])                            # not a robot of the menu
        self.assertEqual(rs({}, "Say To ALL: hello")["target"], "everyone")
        self.assertEqual(rs({}, "(D) hello there")["body"], "hello there")
        self.assertIsNone(rs({"say": "x"}, "B"))                                      # a body option is not a say
        self.assertIsNone(rs({}, "wait here for now"))

    def test_protocol_texts_for_the_default_team_are_the_old_constants(self):
        old = ('one JSON object with one entry for every robot of the team, e.g. {"r1": {"box": "red", "zone": "sign11"}, "r2": {"box": "blue", "zone": "sign12"}, '
               '"r3": "stay"}; an entry is {"box": colour, "zone": zone} (the robot carries one box of that colour to that zone) or "stay" (the robot does '
               'nothing and its run ends)')
        self.assertEqual(P.PLAN_FORMAT, old)
        self.assertEqual(P.plan_format(("r1", "r2", "r3"), P.ZONES), old)
        self.assertEqual(P.protocol_texts(R3), (P.PLAN_FORMAT, P.PEER_RULE, P.HUB_PROPOSE, P.HUB_REVISE))
        self.assertEqual(P.protocol_texts(R3, P.ZONES), (P.PLAN_FORMAT, P.peer_rule(P.ACTIONS, P.PLAN_FORMAT), P.HUB_PROPOSE, P.HUB_REVISE))      # explicit default zones: the same text
        self.assertEqual(P.ACTIONS, "An action is: carry one box of a colour (red or blue) to a zone (sign11, sign12, sign13), or stay (do nothing).")
        self.assertEqual(P.default_zones(2), P.ZONES)
        self.assertEqual(P.default_zones(3), P.ZONES)

    def test_protocol_texts_for_nine_robots(self):
        robots = tuple("r%d" % i for i in range(1, 10))
        zones = P.default_zones(9)
        self.assertEqual(zones, tuple("sign%d" % n for n in range(11, 20)))
        self.assertEqual(P.protocol_texts(robots)[0], P.PLAN_FORMAT)               # without zones every team size keeps the old wording
        fmt, peer, propose, revise = P.protocol_texts(robots, zones)
        self.assertEqual(len(re.findall(r'"r\d": ', fmt)), 9)
        self.assertIn('"r9": "stay"', fmt)
        self.assertIn('"r8": {"box": "blue", "zone": "sign18"}', fmt)
        self.assertIn("sign19", propose)
        self.assertIn("sign19", peer)
        self.assertTrue(revise.endswith(fmt + ")."))
        self.assertIsNone(P.parse_plan(json.dumps({"r1": {"box": "red", "zone": "sign14"}, "r2": "stay", "r3": "stay"}), R3)[0])     # default zones: unchanged refusal
        plan = {r: ({"box": "red", "zone": "sign1%d" % (i + 1)} if i % 2 else "stay") for i, r in enumerate(robots)}
        self.assertIsNotNone(P.parse_plan(json.dumps(plan), robots, zones)[0])


class FreeMenu(unittest.TestCase):
    def test_every_decision_lists_the_say_entries_after_the_body_options(self):
        b, stub = make_free("T1")
        b.decide("r1", 12.0, "pick", pick_options("r1"))
        b.decide("r2", 13.0, "destination", DEST)
        b.decide("r3", 14.0, "door", DOOR)
        b.decide("r1", 15.0, "report", REPORT)
        self.assertEqual(len(stub.prompts), 4)
        for prompt, me in zip(stub.prompts, ("r1", "r2", "r3", "r1")):
            texts = [t for _, t in listing_of(prompt)]
            others = [r for r in R3 if r != me]
            self.assertEqual(texts[-3:], ["say to %s: <text>" % others[0], "say to %s: <text>" % others[1], "say to everyone: <text>"])
            self.assertFalse(any(t.startswith("say") for t in texts[:-3]))
            self.assertIn("Answer: Return an action or option label", prompt)

    def test_no_budget_and_no_draft_step(self):
        b, stub = make_free("T2", leader="r1")
        for rid in R3:
            b.decide(rid, 12.0, "pick", pick_options(rid))
        text = "\n".join(stub.prompts)
        self.assertNotIn("generate a short message", text)
        self.assertNotIn("Messages left", text)
        self.assertNotIn("You can send at most", text)
        self.assertNotIn("not sent yet", text)
        self.assertIn(FREE_RULE, text)
        self.assertNotIn(MESSAGE_RULE % 8, text)
        rec = b.record()
        self.assertNotIn("max_messages_per_robot", rec)
        self.assertEqual(rec["conditions"]["talk"]["mode"], "free")
        self.assertEqual(rec["messages_by_robot"], {"r1": 0, "r2": 0, "r3": 0})

    def test_free_talk_has_no_old_routes(self):
        for kw in (dict(protocol="peer-roco"), dict(pre_exchange=True), dict(option_order="reverse"), dict(max_messages=4), dict(leader_max_messages=3),
                   dict(robot_max_messages={"r2": 3}), dict(route_note=True)):
            with self.assertRaises(ValueError, msg=str(kw)):
                make_free("T2", **kw)
        with self.assertRaises(ValueError):
            make_free("T0")
        with self.assertRaises(ValueError):
            make_free("T1", leader_bind=True)                      # binding needs a leader
        with self.assertRaises(ValueError):
            TeamBrain("T2", list(R3), GOAL, client=FreeStub(), log_dir=Path(tempfile.mkdtemp()), leader_bind=True)       # and free talk
        with self.assertRaises(ValueError):
            make_free("T2", leader_seed=3)                         # a seed only breaks the ties of the election
        with self.assertRaises(ValueError):
            make_free("T2", say_streak_max=0)

    def test_t2_members_talk_to_each_other_directly(self):
        b, stub = make_free("T2", leader="r1", stub=FreeStub(say={"r2": [("r3", "I hold the blue order")]}))
        b.decide("r2", 12.0, "pick", pick_options("r2"))
        msg = b._messages[-1]
        self.assertEqual((msg["from"], msg["to"], msg["tgt"]), ("r2", ["r3"], "r3"))          # not routed through the leader
        b.decide("r1", 30.0, "pick", pick_options("r1"))
        self.assertNotIn("I hold the blue order", stub.prompts_of("r1")[-1])                     # the leader did not hear it

    def test_free_organization_sentence_for_t2_and_none_for_t1(self):
        b, stub = make_free("T2", leader="r2", leader_authority=True)
        b.decide("r1", 12.0, "pick", pick_options("r1"))
        b.decide("r2", 12.0, "pick", pick_options("r2"))
        member, leader = stub.prompts_of("r1")[0], stub.prompts_of("r2")[0]
        self.assertIn("Agent 2 is the leader to coordinate the task.", member)
        self.assertIn("The leader decides which robot takes which box to which zone.", member)
        self.assertIn("You are the leader: decide which box each robot takes", leader)
        self.assertIn('"assign r1: red -> sign11"', leader)              # the example names another robot than the leader
        self.assertNotIn("Your messages are delivered to the leader only", member + leader)
        self.assertNotIn("table assignments", member + leader)         # the original authority sentence speaks of message facts; a say has none
        t1, s1 = make_free("T1")
        t1.decide("r1", 12.0, "pick", pick_options("r1"))
        self.assertIn("Organization instructions: \n", s1.prompts[0])


class SayMechanics(unittest.TestCase):
    WORDS = "I know all three orders: blue to sign12, red to sign11 and red to sign13."

    def test_a_say_takes_the_decision_and_costs_say_time(self):
        b, stub = make_free("T1", stub=FreeStub(say={"r1": [("everyone", self.WORDS)]}))
        out = b.decide("r1", 12.0, "pick", pick_options("r1"))
        t_say = say_time(len(self.WORDS))
        self.assertEqual(out["option"], "wait")                       # the body does not act: the runner's `wait` branch
        self.assertAlmostEqual(out["wait_s"], t_say)
        self.assertNotIn("sent_with_action", out)                      # so the runner reads `turn_used` and waits max(2, wait_s)
        self.assertEqual(len(out["sent"]), 1)
        m = out["sent"][0]
        self.assertEqual((m["from"], m["to"], m["tgt"], m["via"], m["chars"]), ("r1", ["r2", "r3"], "everyone", "say", len(self.WORDS)))
        self.assertAlmostEqual(m["say_s"], t_say, places=3)
        self.assertAlmostEqual(m["deliver_at"], 12.0 + t_say + 2.0)    # delivered 2 s after the speech ends
        self.assertAlmostEqual(m["read_s"], read_time(len(self.WORDS)), places=3)
        self.assertEqual(json.loads(m["text"])["message"], self.WORDS)
        self.assertEqual(b._decisions["r1"][-1]["say_s"], out["say_s"])

    def test_report_point_says_use_the_continue_key(self):
        b, _ = make_free("T1", stub=FreeStub(say={"r1": [("r2", "my box is down")]}))
        out = b.decide("r1", 100.0, "report", REPORT)
        self.assertEqual((out["option"], len(out["sent"])), ("continue", 1))
        self.assertGreater(out["wait_s"], 1.0)                         # the runner does not read it at a report: a runner-side item

    def test_directed_and_broadcast_recipients(self):
        b, _ = make_free("T1", stub=FreeStub(say={"r1": [("r3", "only for you")], "r2": [("everyone", "for all")]}))
        b.decide("r1", 12.0, "pick", pick_options("r1"))
        b.decide("r2", 12.0, "pick", pick_options("r2"))
        self.assertEqual([m["to"] for m in b._messages], [["r3"], ["r1", "r3"]])

    def test_the_message_is_shown_to_the_receiver_when_it_is_readable_not_when_it_arrives(self):
        b, stub = make_free("T1", stub=FreeStub(say={"r1": [("r2", self.WORDS)]}))
        out = b.decide("r1", 12.0, "pick", pick_options("r1"))
        arrive = out["sent"][0]["deliver_at"]
        ready = arrive + read_time(len(self.WORDS))
        self.assertEqual(b.readable_count("r2", arrive + 0.01), 0)       # it has arrived but is not read yet
        self.assertEqual(b.readable_count("r2", ready + 0.01), 1)
        b.decide("r2", arrive + 0.5, "pick", pick_options("r2"))
        self.assertNotIn(self.WORDS, stub.prompts_of("r2")[-1])
        b.decide("r2", ready + 0.5, "pick", pick_options("r2"))
        last = stub.prompts_of("r2")[-1]
        self.assertIn(self.WORDS, last)
        self.assertIn('"to":"me"', last)

    def test_the_reading_queue_is_serial_per_receiver(self):
        long = "x" * 600
        b, _ = make_free("T1", stub=FreeStub(say={"r1": [("r3", long)], "r2": [("r3", long)]}))
        a = b.decide("r1", 12.0, "pick", pick_options("r1"))["sent"][0]
        c = b.decide("r2", 12.0, "pick", pick_options("r2"))["sent"][0]
        self.assertEqual(a["deliver_at"], c["deliver_at"])               # the same instant
        ready = sorted(b._readable("r3").values())
        r = read_time(600)
        self.assertAlmostEqual(ready[0], a["deliver_at"] + r)
        self.assertAlmostEqual(ready[1], a["deliver_at"] + 2 * r)        # the second is read after the first

    def test_no_second_say_in_a_row_without_a_new_message(self):
        b, stub = make_free("T1", stub=FreeStub(say={"r1": [("everyone", "first"), ("everyone", "second")]}))
        b.decide("r1", 12.0, "pick", pick_options("r1"))
        b.decide("r1", 15.0, "pick", pick_options("r1"))
        self.assertFalse(any(t.startswith("say to") for _, t in listing_of(stub.prompts_of("r1")[1])))     # just spoke, nothing new: no say entry
        self.assertEqual(len(b._messages), 1)
        # a teammate answers: after it is readable the say entries return
        b._post("r2", 20.0, json.dumps({"message": "ok", "facts": []}), via="say", to=["r1"])
        b._messages[-1].update(chars=2, say_s=1.5, read_s=0.7, tgt="r1")
        b.decide("r1", 30.0, "pick", pick_options("r1"))
        self.assertTrue(any(t.startswith("say to") for _, t in listing_of(stub.prompts_of("r1")[2])))
        self.assertEqual(len(b._messages), 3)                             # r1's first, r2's reply, and the second say of r1 (chosen at that decision)
        self.assertEqual(json.loads(b._messages[-1]["text"])["message"], "second")

    def test_a_non_say_action_clears_the_streak(self):
        b, stub = make_free("T1", stub=FreeStub(say={"r1": [("everyone", "a")]}))
        b.decide("r1", 12.0, "pick", pick_options("r1"))
        b.decide("r1", 15.0, "pick", pick_options("r1"))                  # acts (first body option)
        self.assertFalse(any(t.startswith("say to") for _, t in listing_of(stub.prompts_of("r1")[1])))
        self.assertEqual(b._states["r1"]["say_streak"], 0)

    def test_say_chosen_without_words_is_a_wait_and_counted(self):
        stub = FreeStub(raw=lambda p: json.dumps({"reasoning": "r", "action": [l for l, t in listing_of(p) if t.startswith("say to everyone")][0]}))
        b, _ = make_free("T1", stub=stub)
        out = b.decide("r1", 12.0, "pick", pick_options("r1"))
        self.assertEqual((out["option"], out["sent"], out["say_failed"]), ("wait", [], True))
        self.assertEqual(b.record()["talk"]["events"], {"say_without_text": 1})
        self.assertEqual(b._messages, [])

    def test_two_step_answer_with_the_words_after_the_label(self):
        # reasoning call, then the final answer: "<label>: words" (no JSON), without --merge-calls
        def raw(prompt):
            if prompt.endswith("So the answer is option"):
                label = [l for l, t in listing_of(prompt) if t.startswith("say to r3")][0]
                return "%s: please take the red box to sign13" % label
            return '{"reasoning":"stub"}'
        b, stub = make_free("T1", stub=FreeStub(raw=raw), merge_calls=False)
        out = b.decide("r1", 12.0, "pick", pick_options("r1"))
        self.assertEqual(len(stub.prompts), 2)                                # reasoning + choice, as in the main experiment
        self.assertIn("So the answer is option", stub.prompts[1])
        self.assertEqual(json.loads(out["sent"][0]["text"])["message"], "please take the red box to sign13")
        self.assertEqual(out["sent"][0]["to"], ["r3"])

    def test_the_random_fallback_never_picks_a_say_entry(self):
        import random
        random.seed(1)
        stub = FreeStub(raw="no idea what to do")
        b, _ = make_free("T1", stub=stub, parser_fix=False)
        for i in range(30):
            out = b.decide("r1", 12.0 + i, "pick", pick_options("r1"))
            self.assertEqual(out["sent"], [])
            self.assertIn(out["option"], ("box:0", "box:1", "box:2", "wait", "finish"))

    def test_an_unreadable_answer_is_asked_again_once_and_a_say_in_the_new_answer_counts(self):
        answers = ['{"reasoning":"r","action":"zzz"}', None]
        def raw(prompt):
            if "could not be matched" in prompt:
                return json.dumps({"action": [l for l, t in listing_of(prompt) if t.startswith("say to everyone")][0], "say": "hello all"})
            return answers[0]
        b, stub = make_free("T1", stub=FreeStub(raw=raw))
        out = b.decide("r1", 12.0, "pick", pick_options("r1"))
        self.assertEqual(len(stub.prompts), 2)
        self.assertEqual(json.loads(out["sent"][0]["text"])["message"], "hello all")
        self.assertEqual([e["event"] for e in b._planner.plan_events], ["parse_retry"])

    def test_words_next_to_a_body_action_are_not_sent_when_no_say_entry_is_offered(self):
        # right after its own say a robot is not offered a say entry (SAY_STREAK_MAX): words written next to a body option are then dropped and counted as before
        stub = FreeStub(say={"r2": [("r1", "first words")]}, raw=lambda p: json.dumps({"reasoning": "r", "action": "B", "say": "I am taking the red box to sign12."})
                        if not listing_of(p)[-1][1].startswith("say to") else None)
        b, _ = make_free("T1", stub=stub)
        b._speak("r2", 11.0, {"target": "r1", "to": ["r1"]}, "first words")                  # r2 has just spoken, nothing new has reached it
        out = b.decide("r2", 12.0, "pick", pick_options("r2"))
        self.assertEqual((out["option"], out["sent"], len(b._messages)), ("box:1", [], 1))
        self.assertEqual(b.record()["talk"]["events"], {"words_beside_an_action_not_sent": 1})
        self.assertNotIn("say_with_action", out)

    def test_long_words_are_cut(self):
        b, _ = make_free("T1", stub=FreeStub(say={"r1": [("everyone", "y" * 900)]}))
        m = b.decide("r1", 12.0, "pick", pick_options("r1"))["sent"][0]
        self.assertEqual(m["chars"], 600)
        self.assertEqual(b.record()["talk"]["events"], {"say_cut_at_600_chars": 1})

    def test_no_message_budget_many_says(self):
        stub = FreeStub(say={"r1": [("everyone", "m%d" % i) for i in range(20)]})
        b, _ = make_free("T1", stub=stub)
        for i in range(20):
            b._post("r2", 10.0 * i + 1, json.dumps({"message": "k", "facts": []}), via="say", to=["r1"])         # a teammate message between two says
            b._messages[-1].update(chars=1, say_s=1.5, read_s=0.7, tgt="r1")
            b.decide("r1", 10.0 * i + 5, "pick", pick_options("r1"))
        self.assertEqual(sum(1 for m in b._messages if m["from"] == "r1"), 20)
        self.assertGreater(20, 8)

    def test_chance_offers_a_reply_or_silence(self):
        b, stub = make_free("T1", stub=FreeStub(say={"r1": [("r2", "start")], "r2": [("r1", "reply at a chance")]}))
        sent = b.decide("r1", 12.0, "pick", pick_options("r1"))["sent"][0]
        t = sent["deliver_at"] + read_time(5) + 1.0
        out = b.chance("r2", t)
        self.assertTrue(out["asked"] and len(out["sent"]) == 1)
        prompt = stub.prompts_of("r2")[-1]
        entries = listing_of(prompt)
        self.assertEqual(entries[0][1], SILENT_TEXT)                      # silence first: the body entry keeps the first label
        self.assertIn(CHANCE_FREE, prompt)
        self.assertEqual(out["sent"][0]["via"], "chance")                 # a reply at a chance does not open a chance for its receiver
        self.assertEqual(b._chances["r2"][0]["sent"][0]["chars"], len("reply at a chance"))

    def test_chance_silence_sends_nothing_and_a_robot_that_just_spoke_gets_no_chance(self):
        b, stub = make_free("T1", stub=FreeStub(say={"r1": [("r2", "a")]}))
        b.decide("r1", 12.0, "pick", pick_options("r1"))
        out = b.chance("r1", 14.0)                                        # just spoke, nothing new
        self.assertEqual((out["asked"], out["sent"]), (False, []))
        out = b.chance("r2", 40.0)                                        # the stub answers the first label (silence)
        self.assertEqual((out["asked"], out["sent"], out["final"]), (True, [], False))

    def test_poll_is_quiet_while_the_robot_speaks(self):
        b, _ = make_free("T1", stub=FreeStub(say={"r1": [("everyone", self.WORDS)]}))
        out = b.decide("r1", 12.0, "pick", pick_options("r1"))
        end = 12.0 + out["say_s"]
        self.assertIs(b.hold_poll("r1", 12.5), False)
        self.assertIs(b.hold_poll("r1", end - 0.01), False)
        self.assertIsNone(b.hold_poll("r1", end + 0.01))
        self.assertIsNone(b.hold_poll("r2", 12.5))
        plain = TeamBrain("T1", list(R3), GOAL, client=FreeStub(), log_dir=Path(tempfile.mkdtemp()))
        self.assertIsNone(plain.hold_poll("r1", 12.0))                    # a run without free talk: the usual poll

    def test_window_shows_every_message_that_arrived_while_the_robot_waited(self):
        robots = tuple("r%d" % i for i in range(1, 10))
        say = {r: [("r1", "report of %s" % r)] for r in robots[1:]}
        b, stub = make_free("T1", robots=robots, stub=FreeStub(say=say))
        for r in robots[1:]:
            b.decide(r, 12.0, "pick", pick_options(r))
        b.decide("r1", 60.0, "pick", pick_options("r1"))
        last = stub.prompts_of("r1")[-1]
        for r in robots[1:]:
            self.assertIn("report of %s" % r, last)                       # 8 messages, not only the usual window of 5


class Election(unittest.TestCase):
    def test_tie_goes_to_the_seeded_choice(self):
        orders = {r: O3 for r in R3}
        for seed in range(12):
            b, _ = make_free("T2", orders=orders, leader_election=True, leader_seed=seed)
            self.assertEqual(b._elect(R3)[0], sorted(R3)[seed % 3], seed)

    def test_a_strict_maximum_wins_whatever_the_seed(self):
        orders = {"r1": O3[:1], "r2": O3, "r3": O3[:2]}
        for seed in (0, 1, 2, 7):
            b, _ = make_free("T2", orders=orders, leader_election=True, leader_seed=seed)
            self.assertEqual(b._elect(R3), ("r2", {"r1": 1, "r2": 3, "r3": 2}))

    def test_without_a_seed_the_lowest_number_wins_as_before(self):
        b, _ = make_free("T2", orders={r: O3 for r in R3}, leader_election=True)
        self.assertEqual(b._elect(R3)[0], "r1")

    def test_the_first_decision_of_a_free_run_elects_once(self):
        orders = {"r1": O3[:1], "r2": [], "r3": O3}
        b, stub = make_free("T2", orders=orders, leader="r1", leader_election=True, leader_seed=1, leader_authority=True)
        self.assertEqual(b.leader, "r1")
        b.decide("r2", 12.0, "pick", pick_options("r2"))
        self.assertEqual(b.leader, "r3")
        self.assertIn("Agent 3 is the leader to coordinate the task.", stub.prompts[0])
        self.assertIn("Agent 1 means robot r1, Agent 2 means robot r2, Agent 3 means robot r3.", stub.prompts[0])
        rec = b.record()
        self.assertEqual((rec["leader"], rec["elected_leader"]), ("r3", "r3"))
        self.assertEqual(rec["election"]["counts"], {"r1": 1, "r2": 0, "r3": 3})
        self.assertEqual(rec["election"]["seed"], 1)
        b.tell("r2", {"orders": O3 + O3})                                # told later: no new election
        b.decide("r1", 20.0, "pick", pick_options("r1"))
        self.assertEqual(b.leader, "r3")

    def test_election_in_a_run_without_free_talk_is_still_not_done(self):
        b = TeamBrain("T2", list(R3), GOAL, client=FreeStub(), log_dir=Path(tempfile.mkdtemp()), leader="r1", leader_election=True)
        b.tell("r3", {"orders": O3})
        b.decide("r1", 12.0, "pick", pick_options("r1"))
        self.assertEqual(b.leader, "r1")                                  # v38 behaviour: no protocol, no election

    def test_protocol_election_uses_the_seed_too(self):
        from brain.tests.test_protocol import Stub as PStub
        orders = {r: O3 for r in R3}
        b = TeamBrain("T2", list(R3), GOAL, client=PStub(), log_dir=Path(tempfile.mkdtemp()), protocol="hub-hmas2", leader_election=True, leader_seed=2)
        for r in R3:
            b.tell(r, {"orders": O3})
        self.assertEqual(b._elect(R3)[0], "r3")

    def test_scene_elections_match_the_document(self):
        """The 15 existing scenes (L3M01-09, S3M01-06), repetition 1: the planner's election (counts of (colour, zone, count)) gives what tools/make_phase2.py
        elect() gives (counts of order ids), and the totals of the document: INFO r1/r2/r3 3/3/3, ORD r2 2, r3 4, r1 0."""
        sys.path.insert(0, str(ROOT.parent / "tools"))
        try:
            import make_phase2
        except Exception as error:              # tools/ or the data it reads (v38 cells, scene files of other folders) are not beside this copy of link/
            self.skipTest("tools/make_phase2.py cannot be imported here: %s" % type(error).__name__)
        wins = {"INFO": {"r1": 0, "r2": 0, "r3": 0}, "ORD": {"r1": 0, "r2": 0, "r3": 0}}
        checked = 0
        for kind, path, ids in (("INFO", make_phase2.SRC["L3"], ["L3M%02d" % i for i in range(1, 10)]),
                                ("ORD", make_phase2.SRC["S3"], ["S3M%02d" % i for i in range(1, 7)])):
            if not Path(path).exists():
                self.skipTest("scene file not on this host: %s" % path)
            scenes = {s["id"]: s for s in json.load(open(path))["scenes"]}
            for sid in ids:
                scene = scenes[sid]
                orders = {o["id"]: {"box": o["colour"], "count": o["count"], "zone": "sign%d" % o["sign"]} for o in scene["orders"]}
                told = {r: [orders[o] for o in scene["knows"][r]] for r in scene["knows"]}
                seed = make_phase2.elect_seed(sid, 1)
                b, _ = make_free("T2", orders=told, leader_election=True, leader_seed=seed)
                leader, counts = b._elect(R3)
                want, want_counts, _ = make_phase2.elect(scene, seed)
                self.assertEqual((leader, counts), (want, want_counts), sid)
                wins[kind][leader] += 1
                checked += 1
        self.assertEqual(checked, 15)
        self.assertEqual(wins, {"INFO": {"r1": 3, "r2": 3, "r3": 3}, "ORD": {"r1": 0, "r2": 2, "r3": 4}})
        self.assertEqual(make_phase2.elect_seed("L3M01", 1), zlib.crc32(b"elect|L3M01|1") % 2 ** 31)


class Binding(unittest.TestCase):
    def leader_run(self, say=None, orders=None, **kw):
        stub = FreeStub(say=say or {"r1": [("everyone", "assign r2: blue -> sign12; assign r3: red -> sign11")]})
        b, stub = make_free("T2", stub=stub, orders=orders or {"r1": O3}, leader="r1", leader_bind=True, **kw)
        return b, stub

    def say_assignments(self, b, now=12.0):
        out = b.decide("r1", now, "pick", pick_options("r1"))
        return out["sent"][0], out

    def test_leader_is_never_bound_and_sees_the_binding_sentences(self):
        b, stub = self.leader_run()
        b.decide("r1", 12.0, "pick", pick_options("r1"))
        prompt = stub.prompts_of("r1")[0]
        self.assertIn(BIND_LEADER % 75, prompt)
        self.assertIn("Organization instructions: Agent 1 is the leader", prompt)
        self.assertNotIn("Leader's assignment for me", prompt)
        self.assertEqual(b.leader_authority, True)                         # binding switches the authority sentences on

    def test_a_member_without_an_assignment_may_only_wait_or_speak_until_the_hold_ends(self):
        b, stub = self.leader_run(say={})
        out = b.decide("r2", 12.0, "pick", pick_options("r2"))
        entries = [t for _, t in listing_of(stub.prompts_of("r2")[0])]
        self.assertEqual(entries[0], "wait here for now")
        self.assertEqual([t for t in entries if not t.startswith("say to")], ["wait here for now"])       # no grasp, no finish
        self.assertIn("Leader's assignment for me: none yet. Until 87 s I can only wait or speak.", stub.prompts_of("r2")[0])
        self.assertEqual(out["bind"]["state"], "held")
        self.assertEqual(b._wake_at["r2"], 87.0)
        self.assertIsNone(b.hold_poll("r2", 80.0))                          # a new message wakes it as usual
        self.assertIs(b.hold_poll("r2", 87.0), True)                         # and the hold's end wakes it
        b.decide("r2", 60.0, "pick", pick_options("r2"))
        self.assertEqual([t for _, t in listing_of(stub.prompts_of("r2")[1]) if not t.startswith("say to")], ["wait here for now"])
        out = b.decide("r2", 88.0, "pick", pick_options("r2"))              # the hold is over: everything opens
        entries = [t for _, t in listing_of(stub.prompts_of("r2")[2])]
        self.assertTrue(any("go grasp" in t for t in entries) and any(t.startswith("finish") for t in entries))
        self.assertNotIn("bind", out)
        self.assertEqual(b.record()["binding"]["unlocked_by_timeout"], 1)

    def test_the_hold_starts_at_the_first_pick_decision_of_the_member(self):
        b, stub = self.leader_run(say={}, hold_s=30.0)
        b.decide("r3", 20.0, "pick", pick_options("r3"))
        self.assertEqual(b._wake_at["r3"], 50.0)
        b.decide("r3", 49.0, "pick", pick_options("r3"))
        self.assertEqual([t for _, t in listing_of(stub.prompts_of("r3")[-1]) if not t.startswith("say to")], ["wait here for now"])
        b.decide("r3", 51.0, "pick", pick_options("r3"))
        self.assertTrue(any("go grasp" in t for _, t in listing_of(stub.prompts_of("r3")[-1])))

    def test_an_assignment_binds_pick_and_destination_once_it_is_readable(self):
        b, stub = self.leader_run()
        msg, _ = self.say_assignments(b)
        self.assertEqual([a["valid"] for a in msg["assign"]], [True, True])
        ready = msg["deliver_at"] + read_time(len(json.loads(msg["text"])["message"]))
        b.decide("r2", ready - 0.2, "pick", pick_options("r2"))              # not readable yet: still held
        self.assertEqual([t for _, t in listing_of(stub.prompts_of("r2")[-1]) if not t.startswith("say to")], ["wait here for now"])
        out = b.decide("r2", ready + 0.2, "pick", pick_options("r2"))
        entries = [t for _, t in listing_of(stub.prompts_of("r2")[-1])]
        body = [t for t in entries if not t.startswith("say to")]
        self.assertEqual(len(body), 2)                                          # the one blue box and wait
        self.assertIn("<blue box>", body[0])
        self.assertEqual(body[1], "wait here for now")
        self.assertIn("Leader's assignment for me: carry a <blue box> to the <sign12 zone>.", stub.prompts_of("r2")[-1])
        self.assertEqual(out["bind"], dict(state="bound", box="blue", zone="sign12"))
        self.assertIn('"table":"assignments"', stub.prompts_of("r2")[-1])        # the existing reported-facts table carries it
        # destination: only the assigned zone (and wait); put_down is taken out
        b.decide("r2", ready + 30.0, "destination", DEST)
        dest = [t for t in [t for _, t in listing_of(stub.prompts_of("r2")[-1])] if not t.startswith("say to")]
        self.assertEqual(dest, ["transport the box I am holding to the <sign12 zone>", "wait here, holding the box"])
        # the other member got her own assignment
        b.decide("r3", ready + 31.0, "pick", pick_for("r3", colours=("red", "blue", "red")))
        self.assertTrue(all("<red box>" in t for t in [t for _, t in listing_of(stub.prompts_of("r3")[-1]) if t.startswith("go grasp")]))
        # door: free
        b.decide("r2", ready + 40.0, "door", DOOR)
        self.assertEqual(len([t for _, t in listing_of(stub.prompts_of("r2")[-1]) if not t.startswith("say to")]), 2)

    def test_an_assignment_to_one_member_does_not_bind_another(self):
        b, stub = self.leader_run(say={"r1": [("r2", "assign r2: blue -> sign12")]})
        msg, _ = self.say_assignments(b)
        t = msg["deliver_at"] + read_time(msg["chars"]) + 5
        b.decide("r3", t, "pick", pick_options("r3"))
        self.assertEqual([x for _, x in listing_of(stub.prompts_of("r3")[-1]) if not x.startswith("say to")], ["wait here for now"])     # r3 has none
        self.assertEqual(b._assignment("r2", t)["box"], "blue")
        self.assertIsNone(b._assignment("r3", t))

    def test_a_line_for_a_member_in_a_message_that_does_not_reach_it_does_not_bind_it(self):
        b, _ = self.leader_run(say={"r1": [("r3", "assign r2: blue -> sign12")]})
        msg, _ = self.say_assignments(b)
        self.assertIsNone(b._assignment("r2", msg["deliver_at"] + 50))
        self.assertTrue(msg["assign"][0]["valid"])                               # a valid line, but nobody binds from it

    def test_invalid_lines_are_counted_and_bind_nobody(self):
        text = "assign r2: green -> sign12; assign r3: red -> sign99; assign r1: red -> sign11; assign r7: red -> sign11; assign r2: blue -> sign12"
        b, _ = self.leader_run(say={"r1": [("everyone", text)]})
        self.say_assignments(b)
        rec = b.record()["binding"]
        self.assertEqual((rec["assign_lines"], rec["assign_valid"], rec["assign_invalid"]), (5, 1, 4))
        self.assertAlmostEqual(rec["valid_rate"], 0.2)
        reasons = [a.get("reason") for a in rec["assignments"]]
        self.assertEqual(reasons, ["colour is not red or blue", "zone is not one of the team's", "the leader itself", "not a robot of the team", None])

    def test_only_the_leader_can_assign(self):
        b, _ = self.leader_run(say={"r2": [("everyone", "assign r3: red -> sign11")]})
        b.decide("r2", 12.0, "pick", pick_options("r2"))
        self.assertNotIn("assign", b._messages[0])
        self.assertEqual(b.record()["binding"]["assign_lines"], 0)

    def test_a_later_assignment_replaces_an_earlier_one(self):
        b, _ = self.leader_run(say={"r1": [("everyone", "assign r2: blue -> sign12"), ("everyone", "assign r2: red -> sign13")]})
        m1, _ = self.say_assignments(b, 12.0)
        b._post("r3", 20.0, json.dumps({"message": "k", "facts": []}), via="say", to=["r1"])
        b._messages[-1].update(chars=1, say_s=1.5, read_s=0.7, tgt="r1")
        out = b.decide("r1", 30.0, "pick", pick_options("r1"))
        m2 = out["sent"][0]
        t = m2["deliver_at"] + 5
        self.assertEqual({k: v for k, v in b._assignment("r2", t).items() if k in ("box", "zone")}, {"box": "red", "zone": "sign13"})

    def test_a_failed_grasp_lifts_the_binding_and_a_missing_colour_does_too(self):
        b, stub = self.leader_run()
        msg, _ = self.say_assignments(b)
        t = msg["deliver_at"] + 5
        # r3 is told to take a red box but the list has none: the binding cannot be met and is lifted (counted)
        b.decide("r3", t, "pick", pick_for("r3", colours=("blue", "blue")))
        b.decide("r2", t, "pick", pick_options("r2"))
        b.tell("r2", {"progress": "I lost the <blue box>: my gripper is empty.", "milestone": "grasp_failed"})
        b.decide("r2", t + 20, "pick", pick_options("r2"))
        entries = [x for _, x in listing_of(stub.prompts_of("r2")[-1])]
        self.assertTrue(any(x.startswith("finish") for x in entries) and len([x for x in entries if x.startswith("go grasp")]) == 3)
        rec = b.record()["binding"]
        self.assertEqual((rec["unlocked_by_grasp_failed"], rec["unlocked_infeasible"]), (1, 1))
        self.assertEqual(rec["members"]["r3"]["infeasible"], 1)

    def test_the_binding_record(self):
        b, _ = self.leader_run()
        msg, _ = self.say_assignments(b)
        ready = msg["deliver_at"] + read_time(msg["chars"])
        b.decide("r2", 12.0, "pick", pick_options("r2"))
        b.decide("r2", ready + 1, "pick", pick_options("r2"))
        b.decide("r2", ready + 40, "destination", DEST)
        rec = b.record()
        bind = rec["binding"]
        self.assertEqual(rec["conditions"]["leader_bind"], {"hold_s": 75.0})
        self.assertEqual((bind["leader"], bind["assign_lines"], bind["assign_valid"], bind["assign_invalid"], bind["valid_rate"]), ("r1", 2, 2, 0, 1.0))
        r2 = bind["members"]["r2"]
        self.assertAlmostEqual(r2["first_arrival_s"], msg["deliver_at"])
        self.assertAlmostEqual(r2["first_readable_s"], ready)
        self.assertEqual((r2["decisions"], r2["held_decisions"], r2["bound_decisions"]), (3, 1, 2))
        self.assertEqual(r2["assignment"], {"box": "blue", "zone": "sign12"})
        self.assertEqual(bind["members_assigned"], 1)
        self.assertEqual((bind["unlocked_by_timeout"], bind["unlocked_by_grasp_failed"], bind["unlocked_infeasible"]), (0, 0, 0))
        json.dumps(rec)                                                    # serialisable

    def test_authority_without_binding_only_carries_the_facts(self):
        stub = FreeStub(say={"r1": [("everyone", "assign r2: blue -> sign12")]})
        b, stub = make_free("T2", stub=stub, orders={"r1": O3}, leader="r1", leader_authority=True)
        msg = b.decide("r1", 12.0, "pick", pick_options("r1"))["sent"][0]
        self.assertTrue(msg["assign"][0]["valid"])
        self.assertNotIn("Until the leader assigns you a box colour", "".join(stub.prompts))      # the binding sentences belong to --leader-binding
        t = msg["deliver_at"] + 5
        b.decide("r2", t, "pick", pick_options("r2"))
        entries = [x for _, x in listing_of(stub.prompts_of("r2")[-1]) if not x.startswith("say to")]
        self.assertEqual(len(entries), 5)                                                         # nothing is filtered
        self.assertIn('"table":"assignments"', stub.prompts_of("r2")[-1])
        self.assertNotIn("binding", b.record())

    def test_hold_s_default_is_the_documented_75_seconds(self):
        self.assertEqual(HOLD_S, 75.0)


class Scale(unittest.TestCase):
    ROBOTS9 = tuple("r%d" % i for i in range(1, 10))

    def test_nine_robots_get_eight_directed_entries_and_zones_up_to_sign19(self):
        stub = FreeStub(say={"r4": [("everyone", "assign r2: blue -> sign19")]})
        b, stub = make_free("T2", robots=self.ROBOTS9, stub=stub, leader="r4", leader_bind=True, orders={"r4": O3}, leader_authority=True)
        self.assertEqual(b.zones, tuple("sign%d" % n for n in range(11, 20)))
        out = b.decide("r4", 12.0, "pick", pick_options("r4"))
        entries = [t for _, t in listing_of(stub.prompts_of("r4")[0])]
        says = [t for t in entries if t.startswith("say to")]
        self.assertEqual(len(says), 9)
        self.assertEqual(says[-1], "say to everyone: <text>")
        self.assertNotIn("say to r4: <text>", says)
        self.assertTrue(out["sent"][0]["assign"][0]["valid"])                    # sign19 is a zone of a 9-robot team
        self.assertIn('"assign r1: red -> sign11"', stub.prompts_of("r4")[0])
        self.assertIn("Agent 1 means robot r1, Agent 2 means robot r2", stub.prompts_of("r4")[0])

    def test_a_protocol_run_without_zones_keeps_the_old_wording_for_any_team_size(self):
        from brain.tests.test_protocol import Stub as PStub
        old = P.PLAN_FORMAT
        for robots in (("r1", "r2"), R3, tuple("r%d" % i for i in range(1, 6))):
            b = TeamBrain("T2", list(robots), GOAL, client=PStub(), log_dir=Path(tempfile.mkdtemp()), protocol="hub-hmas2")
            self.assertEqual((b._ptexts[0], b.zones), (old, P.ZONES), robots)               # no switch: the example still names r1 r2 r3 and the three zones
            self.assertNotIn("zones", b.record().get("conditions", {}))
        free, _ = make_free("T1", robots=tuple("r%d" % i for i in range(1, 6)))
        self.assertEqual(free.zones, P.default_zones(5))                                    # free talk is a new mode: its default follows N
        self.assertNotIn("zones", free.record().get("conditions", {}))                      # (the default of its mode is not a condition)
        given, _ = make_free("T1", robots=tuple("r%d" % i for i in range(1, 6)), zones=P.default_zones(5))
        self.assertEqual(given.record()["conditions"]["zones"], list(P.default_zones(5)))

    def test_zones_switch_and_the_destination_options_widen_the_zone_set(self):
        b, _ = make_free("T2", leader="r1", leader_bind=True, zones=("sign11", "sign12"), leader_authority=True)
        self.assertEqual(b.zones, ("sign11", "sign12"))
        self.assertEqual(b.record()["conditions"]["zones"], ["sign11", "sign12"])
        b.decide("r2", 12.0, "destination", DEST)                              # the runner offers sign13 too: a zone of the scene
        self.assertIn("sign13", b._zone_set())
        with self.assertRaises(ValueError):
            make_free("T2", zones=("sign11", "nowhere"))

    def test_default_zones_are_not_in_the_record(self):
        b, _ = make_free("T1")
        self.assertNotIn("zones", b.record().get("conditions", {}))

    def test_max_input_bytes_moves_the_planner_bound(self):
        robots = tuple("r%d" % i for i in range(1, 15))
        def run(bound):
            stub = FreeStub(say={r: [("r1", "w" * 600)] for r in robots[1:]})
            b, stub = make_free("T1", robots=robots, stub=stub, max_input_bytes=bound)
            for r in robots[1:]:
                b.decide(r, 12.0, "pick", pick_options(r))
            out = b.decide("r1", 80.0, "pick", pick_options("r1"))
            return b, out, stub
        b, out, stub = run(None)
        self.assertNotIn("halted", out)                                        # thirteen 600-char messages exceed the main experiment's 12000-byte bound: the oldest are not shown
        self.assertLess(len(stub.prompts_of("r1")[-1].encode()) + 1024, 12000)
        self.assertIn("older messages not shown)", stub.prompts_of("r1")[-1])
        self.assertGreater(b.record()["talk"]["events"]["history_messages_dropped"], 0)
        b, out, stub = run(24000)
        self.assertNotIn("halted", out)
        self.assertLess(len(stub.prompts_of("r1")[-1].encode()) + 1024, 24000)
        self.assertNotIn("not shown", stub.prompts_of("r1")[-1])               # everything fits: nothing is cut, no note
        self.assertNotIn("history_trimmed_prompts", b.record()["talk"]["events"])
        self.assertEqual(b.record()["conditions"]["max_input_bytes"], 24000)
        with self.assertRaises(ValueError):
            make_free("T1", max_input_bytes=1000)

    def test_protocol_round_for_five_robots_uses_their_zones_and_an_example_for_each(self):
        from brain.tests.test_protocol import Stub as PStub

        class Five(PStub):
            def call(self, prompt, response_format=None):
                self.prompts.append(prompt)
                if "propose the plan for the whole team" in prompt:
                    return {"raw_output": json.dumps({"r1": {"box": "red", "zone": "sign15"}, "r2": "stay", "r3": "stay", "r4": "stay", "r5": "stay"})}
                if "review the leader's plan" in prompt:
                    return {"raw_output": "I Agree"}
                return {"raw_output": '{"reasoning":"stub"}'}
        robots = tuple("r%d" % i for i in range(1, 6))
        stub = Five()
        b = TeamBrain("T2", list(robots), GOAL, client=stub, log_dir=Path(tempfile.mkdtemp()), protocol="hub-hmas2", leader="r1", zones=P.default_zones(5))
        for r in robots:
            b.tell(r, {"orders": [], "progress": "x"})
        for r in robots:                                                    # the round opens when every robot has asked
            b.decide(r, 12.0, "pick", pick_options(r))
        self.assertTrue(any('"r5": "stay"' in p and "sign15" in p for p in stub.prompts))
        self.assertEqual(b._plan["entries"]["r1"], {"box": "red", "zone": "sign15"})       # sign15 is accepted for a five-robot team (the default zones refuse it)


class RuleSentence(unittest.TestCase):
    """--scene-file / --scene-id (the rule sentence of the S3 scenes; precedence-link.diff without status-feed and plan-after)."""
    RULE = ("Rule of this task, given to every robot: the <red box> for the <sign13 zone> must be set down at its zone BEFORE the <blue box> for the <sign11 zone> "
            "is set down at its zone. A box set down earlier than that does not count as delivered.")
    ORDERS = {"r1": [{"box": "red", "count": 1, "zone": "sign13"}, {"box": "blue", "count": 1, "zone": "sign11"}], "r2": [], "r3": [{"box": "red", "count": 1, "zone": "sign12"}]}

    def scene_file(self, constraints):
        doc = {"scenes": [{"id": "X1", "orders": [{"id": "o1", "colour": "red", "count": 1, "sign": 13}, {"id": "o2", "colour": "blue", "count": 1, "sign": 11},
                                                  {"id": "o3", "colour": "red", "count": 1, "sign": 12}], "constraints": constraints}]}
        path = Path(tempfile.mkdtemp()) / "scenes.json"
        path.write_text(json.dumps(doc))
        return path

    def test_only_the_holders_see_the_rule(self):
        for holders in (["r1"], list(R3)):
            b, stub = make_free("T1", orders=self.ORDERS, order_rules={r: self.RULE for r in holders})
            for rid in R3:
                b.decide(rid, 12.0, "pick", pick_options(rid))
            for rid in R3:
                self.assertEqual(all(self.RULE in p for p in stub.prompts_of(rid)), rid in holders, rid)
            own = progress_of(stub.prompts_of("r1")[0])["own_facts"][0]
            self.assertEqual(sorted(own), ["order_rule", "orders", "progress"])
            self.assertEqual(b.record()["conditions"]["order_rules"], {"holders": sorted(holders)})

    def test_the_rule_is_not_an_order_for_the_election(self):
        orders = {"r1": self.ORDERS["r1"], "r2": [], "r3": self.ORDERS["r1"] + self.ORDERS["r3"]}
        got = set()
        for rules in ({}, {"r1": self.RULE}, {"r2": self.RULE}):
            b, _ = make_free("T2", orders=orders, leader_election=True, order_rules=rules)
            got.add(str(b._elect(R3)))
        self.assertEqual(got, {str(("r3", {"r1": 2, "r2": 0, "r3": 3}))})

    def test_no_rules_no_change(self):
        a, sa = make_free("T1", orders=self.ORDERS)
        b, sb = make_free("T1", orders=self.ORDERS, order_rules={})
        for brain in (a, b):
            brain.decide("r1", 12.0, "pick", pick_options("r1"))
        self.assertEqual(sa.prompts, sb.prompts)
        self.assertFalse(any("order_rule" in p for p in sb.prompts))
        self.assertNotIn("order_rules", b.record().get("conditions", {}))

    def test_bad_rules(self):
        with self.assertRaises(ValueError):
            make_free("T1", order_rules={"r9": self.RULE})

    def test_scene_rules_from_a_scene_file(self):
        path = self.scene_file([{"id": "k1", "type": "order", "orders": ["o1", "o2"], "known_by": ["r1"]}])
        self.assertEqual(brain_server.scene_rules(path, "X1"), {"r1": self.RULE})
        self.assertEqual(brain_server.scene_rules(self.scene_file([]), "X1"), {})
        with self.assertRaises(ValueError):
            brain_server.scene_rules(self.scene_file([{"id": "k1", "type": "sync", "orders": ["o1", "o2"], "known_by": ["r1"], "window_s": 60}]), "X1")
        with self.assertRaises(ValueError):
            brain_server.scene_rules(path, "nope")
        self.assertTrue(RULES_GOAL.startswith(" ") and "rule" not in brain_server.GOAL)

    # Several rules per scene (phase-2 N=9 scenes: 3 rules, every robot knows every rule): one text per rule, in the scene's order.
    RULE2 = ("Rule of this task, given to every robot: the <blue box> for the <sign11 zone> must be set down at its zone BEFORE the <red box> for the <sign12 zone> "
             "is set down at its zone. A box set down earlier than that does not count as delivered.")
    RULE3 = ("Rule of this task, given to every robot: the <red box> for the <sign12 zone> must be set down at its zone BEFORE the <red box> for the <sign13 zone> "
             "is set down at its zone. A box set down earlier than that does not count as delivered.")

    def test_several_rules_every_robot_reads_every_rule_in_order(self):
        rules = [self.RULE, self.RULE2, self.RULE3]
        b, stub = make_free("T1", orders=self.ORDERS, order_rules={r: rules for r in R3})
        for rid in R3:
            b.decide(rid, 12.0, "pick", pick_options(rid))
        for rid in R3:
            for prompt in stub.prompts_of(rid):
                self.assertEqual([prompt.count(t) for t in rules], [1, 1, 1], rid)
                self.assertEqual(sorted(prompt.index(t) for t in rules), [prompt.index(t) for t in rules])      # the shown order is the given order
            own = progress_of(stub.prompts_of(rid)[0])["own_facts"][0]
            self.assertEqual(sorted(own), ["order_rules", "orders", "progress"])             # next to "orders" (the prompt shows the keys sorted)
            self.assertEqual(own["order_rules"], rules)
            self.assertNotIn("order_rule", own)
        rec = b.record()["conditions"]["order_rules"]
        self.assertEqual(rec, {"holders": sorted(R3), "rules_by_holder": {r: 3 for r in sorted(R3)}})

    def test_one_rule_is_the_same_as_before_whatever_the_shape(self):
        a, sa = make_free("T1", orders=self.ORDERS, order_rules={r: self.RULE for r in R3})
        b, sb = make_free("T1", orders=self.ORDERS, order_rules={r: [self.RULE] for r in R3})
        for brain in (a, b):
            for rid in R3:
                brain.decide(rid, 12.0, "pick", pick_options(rid))
        self.assertEqual(sa.prompts, sb.prompts)
        self.assertEqual(a.record()["conditions"], b.record()["conditions"])
        self.assertEqual(a.record()["conditions"]["order_rules"], {"holders": sorted(R3)})           # no count for a single rule
        own = progress_of(sb.prompts_of("r1")[0])["own_facts"][0]
        self.assertEqual(own["order_rule"], self.RULE)
        self.assertNotIn("order_rules", own)

    def test_several_rules_only_to_their_holders(self):
        b, stub = make_free("T1", orders=self.ORDERS, order_rules={"r1": [self.RULE, self.RULE2], "r2": self.RULE3})
        for rid in R3:
            b.decide(rid, 12.0, "pick", pick_options(rid))
        got = {rid: progress_of(stub.prompts_of(rid)[0])["own_facts"][0] for rid in R3}
        self.assertEqual(got["r1"]["order_rules"], [self.RULE, self.RULE2])
        self.assertEqual(got["r2"]["order_rule"], self.RULE3)
        self.assertFalse(any(k.startswith("order_rule") for k in got["r3"]))
        self.assertFalse(any("Rule of this task" in p for p in stub.prompts_of("r3")))
        self.assertEqual(b.record()["conditions"]["order_rules"], {"holders": ["r1", "r2"], "rules_by_holder": {"r1": 2, "r2": 1}})

    def test_several_rules_are_not_orders_for_the_election(self):
        orders = {"r1": self.ORDERS["r1"], "r2": [], "r3": self.ORDERS["r1"] + self.ORDERS["r3"]}
        got = set()
        for rules in ({}, {r: [self.RULE, self.RULE2, self.RULE3] for r in R3}, {"r2": [self.RULE, self.RULE3]}):
            b, _ = make_free("T2", orders=orders, leader_election=True, order_rules=rules)
            got.add(str(b._elect(R3)))
        self.assertEqual(got, {str(("r3", {"r1": 2, "r2": 0, "r3": 3}))})

    def test_bad_several_rules(self):
        for bad in ([], [""], [self.RULE, ""], [self.RULE, 5], [self.RULE, None], "", 5, [[self.RULE]]):
            with self.assertRaises(ValueError, msg=repr(bad)):
                make_free("T1", order_rules={"r1": bad})
        with self.assertRaises(ValueError):
            make_free("T1", order_rules={"r9": [self.RULE, self.RULE2]})

    def test_scene_rules_with_several_constraints(self):
        k = lambda i, pair, known: {"id": "k%d" % i, "type": "order", "orders": pair, "known_by": known}
        every = ["r1", "r2", "r3"]
        path = self.scene_file([k(1, ["o1", "o2"], every), k(2, ["o2", "o3"], every), k(3, ["o3", "o1"], every)])
        got = brain_server.scene_rules(path, "X1")
        text = lambda p, q: brain_server.rule_text(brain_server.load_scene(path, "X1"), {"orders": [p, q]})
        self.assertEqual(got, {r: [text("o1", "o2"), text("o2", "o3"), text("o3", "o1")] for r in every})   # every robot, every rule, the scene's order
        self.assertEqual(got["r1"][0], self.RULE)
        # a robot told only some of the rules gets those (a rule it is told twice is still one sentence); one rule is the bare string
        path = self.scene_file([k(1, ["o1", "o2"], ["r1", "r1", "r2"]), k(2, ["o2", "o3"], ["r1"])])
        self.assertEqual(brain_server.scene_rules(path, "X1"), {"r1": [text("o1", "o2"), text("o2", "o3")], "r2": text("o1", "o2")})
        # a scene's rules reach the planner in the same shape
        b, stub = make_free("T1", orders=self.ORDERS, order_rules=got)
        b.decide("r2", 12.0, "pick", pick_options("r2"))
        self.assertEqual(progress_of(stub.prompts_of("r2")[0])["own_facts"][0]["order_rules"], got["r2"])

    def test_scene_zones(self):
        self.assertEqual(brain_server.scene_zones(self.scene_file([]), "X1"), ("sign11", "sign12", "sign13"))
        doc = {"scenes": [{"id": "M1", "orders": [{"id": "o1", "colour": "red", "count": 1, "sign": 14}],
                           "arena": {"signs": [{"number": n} for n in (11, 12, 13, 14, 15)]}}]}
        path = Path(tempfile.mkdtemp()) / "map.json"
        path.write_text(json.dumps(doc))
        self.assertEqual(brain_server.scene_zones(path, "M1"), tuple("sign%d" % n for n in range(11, 16)))
        doc = {"scenes": [{"id": "M2", "orders": [{"id": "o1", "colour": "red", "count": 1, "sign": 17}]}]}
        path.write_text(json.dumps(doc))
        self.assertEqual(brain_server.scene_zones(path, "M2"), ("sign11", "sign12", "sign13", "sign17"))


class BodyLabelWithWords(unittest.TestCase):
    """The real model often answers {"action":"B","say":"..."} (a body option plus words). Speaking is an action that takes the turn: the words are the decision."""
    WORDS = "r2, I take the red box to sign12; please take the blue one."

    def run_pick(self, raw, rid="r1", team="T1", **kw):
        b, stub = make_free(team, stub=FreeStub(raw=raw), **kw)
        return b, stub, b.decide(rid, 12.0, "pick", pick_options(rid))

    def test_a_body_label_with_words_is_a_directed_speech_and_the_body_action_is_not_done(self):
        b, stub, out = self.run_pick(json.dumps({"reasoning": "r", "action": "B", "say": self.WORDS}))
        self.assertEqual(out["option"], "wait")                                  # not box:1: the body does not act
        self.assertEqual(len(out["sent"]), 1)
        m = out["sent"][0]
        self.assertEqual((m["to"], m["tgt"], m["via"]), (["r2"], "r2", "say"))      # "r2," at the start addresses r2
        self.assertEqual(json.loads(m["text"])["message"], self.WORDS)
        self.assertNotIn("sent_with_action", out)                                 # the runner reads turn_used: the speech took the turn
        self.assertAlmostEqual(out["wait_s"], say_time(len(self.WORDS)))
        self.assertEqual(out["say_with_action"], {"action": "B", "key": "box:1"})  # the dropped body label is in the record
        self.assertEqual(b.record()["talk"]["events"], {"say_with_action": 1})
        self.assertEqual(b._decisions["r1"][-1]["say_with_action"], {"action": "B", "key": "box:1"})
        self.assertEqual(b._states["r1"]["actions"], ["say to r2"])               # no body action in the robot's own history
        self.assertEqual(b._states["r1"]["say_streak"], 1)

    def test_target_rules(self):
        def to_of(result, text="hello there", rid="r1", **kw):
            b, stub, out = self.run_pick(json.dumps(dict({"action": "B", "say": text}, **result)), rid=rid, **kw)
            return out["sent"][0]["to"]
        self.assertEqual(to_of({}), ["r2", "r3"])                                  # no addressee: everyone
        self.assertEqual(to_of({"to": "r3"}), ["r3"])                              # an explicit "to" field
        self.assertEqual(to_of({"to": "everyone"}, "r2, hi"), ["r2", "r3"])        # explicit beats the text
        self.assertEqual(to_of({"to": "all"}), ["r2", "r3"])
        self.assertEqual(to_of({"to": ["r2"]}, "hi"), ["r2"])
        self.assertEqual(to_of({"to": ["r2", "r3"]}, "hi"), ["r2", "r3"])          # a list that names every teammate
        self.assertEqual(to_of({"to": "r9"}, "r3: hi"), ["r3"])                    # a "to" that is not a teammate is ignored: the text decides
        self.assertEqual(to_of({}, "r3: take the blue box"), ["r3"])               # "rX:" and "rX," at the start
        self.assertEqual(to_of({}, "R3, take the blue box"), ["r3"])
        self.assertEqual(to_of({}, "r1, I am r1"), ["r2", "r3"])                   # the speaker itself is not a teammate
        self.assertEqual(to_of({}, "r7, nobody"), ["r2", "r3"])                    # not a robot of the team
        self.assertEqual(to_of({}, "I told r2 already"), ["r2", "r3"])             # only a leading address counts

    def test_the_other_shape_a_say_label_with_text_or_say(self):
        for field in ("text", "say", "message"):
            raw = lambda p, field=field: json.dumps({"action": [l for l, t in listing_of(p) if t.startswith("say to r3")][0], field: "go to sign13"})
            b, stub, out = self.run_pick(raw)
            self.assertEqual((out["sent"][0]["to"], json.loads(out["sent"][0]["text"])["message"]), (["r3"], "go to sign13"), field)
            self.assertNotIn("say_with_action", out)                               # that is the normal speech, not a body label with words

    def test_nothing_is_read_as_a_speech_without_real_words(self):
        for extra in ({"say": ""}, {"say": "   "}, {"say": "<text>"}, {"say": "your words"}, {"text": "..."}, {"say": 12}):
            b, stub, out = self.run_pick(json.dumps(dict({"action": "B"}, **extra)))
            self.assertEqual((out["option"], out["sent"]), ("box:1", []), extra)
            self.assertNotIn("say_with_action", b.record().get("talk", {}).get("events", {}))

    def test_an_echo_of_an_option_line_is_not_a_speech(self):
        def raw(prompt):
            return json.dumps({"action": "B", "text": "B. " + [t for l, t in listing_of(prompt) if l == "B"][0]})
        b, stub, out = self.run_pick(raw)
        self.assertEqual((out["option"], out["sent"]), ("box:1", []))
        self.assertEqual(b.record()["talk"]["events"], {"words_beside_an_action_not_sent": 1})

    def test_the_unreadable_answer_retry_applies_the_same_rule(self):
        def raw(prompt):
            if "could not be matched" in prompt:
                return json.dumps({"action": "B", "say": "r3, retry words"})
            return '{"reasoning":"r","action":"zzz"}'
        b, stub, out = self.run_pick(raw)
        self.assertEqual(len(stub.prompts), 2)
        self.assertEqual((out["sent"][0]["to"], out["option"]), (["r3"], "wait"))
        self.assertEqual(b.record()["talk"]["events"], {"say_with_action": 1})

    def test_a_chance_with_the_silence_label_and_words_is_a_reply(self):
        def raw(prompt):
            if "A. %s" % SILENT_TEXT in prompt:                                 # the chance of r2: the first entry is the silence
                return json.dumps({"action": "A", "say": "r1, got it"})
            return json.dumps({"action": [l for l, t in listing_of(prompt) if t.startswith("say to r2")][0], "say": "start"})
        b, _ = make_free("T1", stub=FreeStub(raw=raw))
        sent = b.decide("r1", 12.0, "pick", pick_options("r1"))["sent"][0]
        out = b.chance("r2", sent["deliver_at"] + read_time(5) + 1.0)
        self.assertTrue(out["asked"] and len(out["sent"]) == 1)
        self.assertEqual((out["sent"][0]["via"], out["sent"][0]["to"]), ("chance", ["r1"]))
        self.assertEqual(out["say_with_action"], {"action": "A", "key": "silent"})
        self.assertEqual(b.record()["talk"]["events"]["say_with_action"], 1)

    def test_a_leader_answer_with_a_body_label_and_assign_lines_binds_the_member(self):
        words = "assign r2: blue -> sign12; assign r3: red -> sign11"
        b, stub, out = self.run_pick(json.dumps({"action": "B", "say": words}), team="T2", leader="r1", leader_bind=True, orders={"r1": O3})
        m = out["sent"][0]
        self.assertEqual([(a["to"], a["box"], a["zone"], a["valid"]) for a in m["assign"]], [("r2", "blue", "sign12", True), ("r3", "red", "sign11", True)])
        self.assertEqual(m["to"], ["r2", "r3"])
        ready = m["deliver_at"] + read_time(len(words))
        bound = b.decide("r2", ready + 0.2, "pick", pick_options("r2"))
        self.assertEqual(bound["bind"], dict(state="bound", box="blue", zone="sign12"))        # exactly as for a normal say option
        normal, _ = make_free("T2", stub=FreeStub(say={"r1": [("everyone", words)]}), leader="r1", leader_bind=True, orders={"r1": O3})
        n = normal.decide("r1", 12.0, "pick", pick_options("r1"))["sent"][0]
        self.assertEqual(n["assign"], m["assign"])

    def leader_says(self, say_fields, rid="r1", **kw):
        kw = dict(dict(team="T2", leader="r1", leader_bind=True, orders={"r1": O3}), **kw)
        return self.run_pick(json.dumps(dict({"action": "B"}, **say_fields)), rid=rid, **kw)

    def test_an_assign_line_for_another_teammate_widens_the_speech_to_everyone(self):
        words = "r2: take the blue box to sign12. assign r3: red -> sign11"
        b, stub, out = self.leader_says({"say": words})
        m = out["sent"][0]
        self.assertEqual((m["to"], m["tgt"]), (["r2", "r3"], "everyone"))                 # "r2:" would have addressed r2 only: r3's line would never arrive
        self.assertEqual(out["say_with_action"], {"action": "B", "key": "box:1", "widened_from": "r2"})
        self.assertEqual(b.record()["talk"]["events"], {"say_with_action": 1, "say_widened_for_assignments": 1})
        self.assertEqual(b.record()["talk"]["directed"], 0)
        self.assertEqual(b.record()["talk"]["to_everyone"], 1)
        ready = m["deliver_at"] + read_time(len(words))
        self.assertEqual(b._assignment("r3", ready + 0.1)["zone"], "sign11")             # the line reached the robot it names
        bound = b.decide("r3", ready + 0.2, "pick", pick_options("r3"))
        self.assertEqual(bound["bind"], dict(state="bound", box="red", zone="sign11"))

    def test_an_explicit_to_field_is_widened_the_same_way(self):
        b, stub, out = self.leader_says({"say": "assign r3: red -> sign11", "to": "r2"})
        self.assertEqual((out["sent"][0]["to"], out["sent"][0]["tgt"]), (["r2", "r3"], "everyone"))
        self.assertEqual(out["say_with_action"]["widened_from"], "r2")

    def test_assign_lines_for_the_addressee_only_keep_the_directed_speech(self):
        for words in ("r2, assign r2: blue -> sign12", "r2: please wait. assign r2: blue -> sign12; assign r2: red -> sign13"):
            b, stub, out = self.leader_says({"say": words})
            self.assertEqual((out["sent"][0]["to"], out["sent"][0]["tgt"]), (["r2"], "r2"), words)
            self.assertNotIn("widened_from", out["say_with_action"])
            self.assertNotIn("say_widened_for_assignments", b.record()["talk"]["events"])

    def test_only_valid_lines_of_the_leader_widen_the_speech(self):
        for words in ("r2, assign r3: green -> sign11",              # colour is not red or blue
                      "r2, assign r3: red -> sign99",                # not a zone of the team
                      "r2, assign r1: red -> sign11",                # the leader itself
                      "r2, assign r7: red -> sign11",                # not a robot of the team
                      "r2, I would assign r3 something later"):      # not a line
            b, stub, out = self.leader_says({"say": words})
            self.assertEqual(out["sent"][0]["to"], ["r2"], words)
            self.assertNotIn("say_widened_for_assignments", b.record()["talk"]["events"], words)
        b, stub, out = self.leader_says({"say": "r3, assign r2: blue -> sign12"}, rid="r2", leader_bind=False, leader_authority=True)      # r2 is not the leader: its lines are no assignments
        self.assertEqual(out["sent"][0]["to"], ["r3"])
        b, stub, out = self.run_pick(json.dumps({"action": "B", "say": "r2, assign r3: red -> sign11"}), team="T2", leader="r1")      # no authority, no binding: none either
        self.assertEqual(out["sent"][0]["to"], ["r2"])

    def test_a_say_option_the_model_chose_itself_keeps_its_addressee(self):
        stub = FreeStub(say={"r1": [("r2", "assign r3: red -> sign11")]})
        b, _ = make_free("T2", stub=stub, leader="r1", leader_bind=True, orders={"r1": O3})
        out = b.decide("r1", 12.0, "pick", pick_options("r1"))
        self.assertEqual((out["sent"][0]["to"], out["sent"][0]["tgt"]), (["r2"], "r2"))
        self.assertNotIn("say_with_action", out)
        self.assertNotIn("say_widened_for_assignments", b.record()["talk"]["events"])

    def test_the_chance_path_widens_too(self):
        def raw(prompt):
            if "A. %s" % SILENT_TEXT in prompt:                                  # the chance of the leader
                return json.dumps({"action": "A", "say": "r2, got it. assign r3: red -> sign11"})
            return json.dumps({"action": [l for l, t in listing_of(prompt) if t.startswith("say to r1")][0], "say": "hello leader"})
        b, _ = make_free("T2", stub=FreeStub(raw=raw), leader="r1", leader_bind=True, orders={"r1": O3})
        sent = b.decide("r2", 12.0, "pick", pick_options("r2"))["sent"][0]
        out = b.chance("r1", sent["deliver_at"] + read_time(12) + 1.0)
        self.assertTrue(out["asked"] and len(out["sent"]) == 1)
        self.assertEqual((out["sent"][0]["via"], out["sent"][0]["to"], out["sent"][0]["tgt"]), ("chance", ["r2", "r3"], "everyone"))
        self.assertEqual(out["say_with_action"]["widened_from"], "r2")

    def test_words_are_cut_like_any_speech(self):
        b, stub, out = self.run_pick(json.dumps({"action": "B", "say": "y" * 900}))
        self.assertEqual(out["sent"][0]["chars"], 600)
        self.assertEqual(b.record()["talk"]["events"], {"say_cut_at_600_chars": 1, "say_with_action": 1})

    def test_read_say_beside_action_directly(self):
        menu = {"go grasp <blue box>": {"skill": "executor", "key": "box:0"}, "wait here for now": {"skill": "executor", "key": "wait"},
                "say to r2: <text>": {"skill": "say", "target": "r2", "to": ["r2"]}, "say to everyone: <text>": {"skill": "say", "target": "everyone", "to": ["r2", "r3"]}}
        label = lambda i: "ABCD"[i]
        got = read_say_beside_action(menu, {"say": "r2: hi"}, "B", label)
        self.assertEqual((got["target"], got["entry"], got["body"], got["dropped"]), ("r2", "say to r2: <text>", "r2: hi", {"action": "B", "key": "wait"}))
        got = read_say_beside_action(menu, {"say": "hi"}, "go grasp <blue box>", label)
        self.assertEqual((got["target"], got["dropped"]["key"]), ("everyone", None))      # a long answer text keeps the text, no key
        self.assertIsNone(read_say_beside_action(menu, {}, "A", label))
        self.assertIsNone(read_say_beside_action({k: v for k, v in menu.items() if v["skill"] != "say"}, {"say": "hi"}, "A", label))     # no say entry offered

    def test_the_prompt_says_that_speaking_uses_the_turn_and_shows_the_json_shape(self):
        b, stub, out = self.run_pick(json.dumps({"action": "B"}))
        prompt = stub.prompts[0]
        self.assertIn("Speaking uses your turn instead of a body action", prompt)
        self.assertIn('{"action":"<say option label>","say":"your words"}', prompt)
        self.assertIn('Do not write "say" together with a body action: then only the words are sent and the action is not done.', prompt)
        self.assertIn(TALK_RULE, prompt)
        self.assertIn(FREE_ANSWER, prompt)
        self.assertIn(FREE_RULE, prompt)

    def test_the_smoke_model_anchors_are_unchanged(self):
        b, stub, out = self.run_pick(json.dumps({"action": "B"}))
        self.assertIn("Besides acting you may speak", stub.prompts[0])
        self.assertTrue(stub.prompts[0].endswith('also "say":"your words".'))
        self.assertIn('"action":"option label"', stub.prompts[0])


class HistoryBound(unittest.TestCase):
    """Free talk only: the message history of a prompt is cut (oldest first) so that the prompt fits the byte bound."""

    def chatter(self, robots, n, bound, chars=600, **kw):
        """n messages of `chars` characters from the teammates to r1 (written straight into the run), then r1's decision."""
        stub = FreeStub()
        b, stub = make_free("T1", robots=robots, stub=stub, max_input_bytes=bound, **kw)
        for i in range(n):
            speaker = robots[1 + i % (len(robots) - 1)]
            text = ("m%02d " % i) + "x" * (chars - 4)
            b._speak(speaker, 5.0 + i, {"target": "r1", "to": ["r1"]}, text)
        return b, stub

    def check_fits(self, stub, bound):
        for prompt in stub.prompts:
            self.assertLessEqual(len(prompt.encode()) + 1024, bound)

    def test_twenty_long_messages_are_cut_to_fit_the_default_bound(self):
        b, stub = self.chatter(R3, 20, None)
        out = b.decide("r1", 400.0, "pick", pick_options("r1"))
        self.assertNotIn("halted", out)                                           # before: PlanningContextError stopped the robot
        prompt = stub.prompts_of("r1")[-1]
        self.check_fits(stub, 12000)
        dropped = b.record()["talk"]["events"]["history_messages_dropped"]
        self.assertGreater(dropped, 5)
        self.assertEqual(b.record()["talk"]["events"]["history_trimmed_prompts"], 1)
        self.assertIn("(%d older messages not shown)" % dropped, prompt)
        self.assertEqual(prompt.count("older messages not shown)"), 1)
        self.assertIn("m19 ", prompt)                                             # the newest is kept
        self.assertNotIn("m00 ", prompt)                                          # the oldest is dropped first
        shown = [i for i in range(20) if "m%02d " % i in prompt]
        self.assertEqual(shown, list(range(20 - len(shown), 20)))                 # a contiguous newest block
        self.assertEqual(20 - len(shown), dropped)                                # the note counts what the bound hid (the usual window of 5 is not counted: all 20 are fresh here)
        self.assertEqual(len(b._messages), 20)                                    # only the display is cut

    def test_nothing_is_cut_and_no_note_when_everything_fits(self):
        b, stub = self.chatter(R3, 3, None, chars=100)
        b.decide("r1", 400.0, "pick", pick_options("r1"))
        self.assertNotIn("not shown", stub.prompts_of("r1")[-1])
        self.assertNotIn("history_trimmed_prompts", b.record()["talk"]["events"])
        self.assertNotIn("history_messages_dropped", b.record()["talk"]["events"])

    def test_nine_robots_with_the_scale_bound_fit_even_with_a_very_long_history(self):
        robots = tuple("r%d" % i for i in range(1, 10))
        b, stub = self.chatter(robots, 60, 24000)                                 # 60 x 600 characters waiting for r1: 36 KB of history, far beyond 24 KB
        out = b.decide("r1", 900.0, "pick", pick_options("r1"))
        self.assertNotIn("halted", out)
        self.check_fits(stub, 24000)
        self.assertGreater(b.record()["talk"]["events"]["history_messages_dropped"], 20)
        self.assertIn("m59 ", stub.prompts_of("r1")[-1])

    def test_the_retry_prompt_fits_too(self):
        # an unreadable answer is asked once more with the label-only sentence appended: the bound must hold for that prompt as well
        answers = []
        def raw(prompt):
            answers.append(prompt)
            return '{"reasoning":"r","action":"zzz"}' if "could not be matched" not in prompt else json.dumps({"action": "A"})
        stub = FreeStub(raw=raw)
        b, stub = make_free("T1", robots=R3, stub=stub, max_input_bytes=6000)
        for i in range(20):
            b._speak("r2", 5.0 + i, {"target": "r1", "to": ["r1"]}, ("m%02d " % i) + "x" * 596)
        out = b.decide("r1", 400.0, "pick", pick_options("r1"))
        self.assertNotIn("halted", out)
        self.assertEqual(len(answers), 2)
        self.assertTrue(any("could not be matched" in p for p in answers))
        self.check_fits(stub, 6000)

    def test_a_cut_assignment_still_binds_the_member(self):
        words = "assign r2: blue -> sign12; assign r3: red -> sign11"
        stub = FreeStub(say={"r1": [("everyone", words)]})
        b, stub = make_free("T2", stub=stub, leader="r1", leader_bind=True, orders={"r1": O3}, max_input_bytes=6000)
        sent = b.decide("r1", 12.0, "pick", pick_options("r1"))["sent"][0]
        for i in range(20):                                                        # r3 chatters to r2 afterwards: the leader's message falls out of the view of r2
            b._speak("r3", 20.0 + i, {"target": "r2", "to": ["r2"]}, ("c%02d " % i) + "x" * 596)
        out = b.decide("r2", 400.0, "pick", pick_options("r2"))
        prompt = stub.prompts_of("r2")[-1]
        self.assertNotIn(words, prompt)                                            # not shown in the dialogue ...
        self.assertIn("older messages not shown)", prompt)
        self.assertEqual(out["bind"], dict(state="bound", box="blue", zone="sign12"))   # ... but the binding reads the stored messages
        self.assertIn('"table":"assignments"', prompt)                              # and the reported fact is in the progress block as before
        self.assertEqual(sent["assign"][0]["valid"], True)

    def test_without_free_talk_the_prompt_is_never_cut(self):
        # a run without --talk free keeps the old rule: a prompt over the bound stops the robot (PlanningContextError), nothing is dropped or noted
        stub = FreeStub()
        b = TeamBrain("T1", list(R3), GOAL, client=stub, log_dir=Path(tempfile.mkdtemp()), max_input_bytes=1100)
        for rid in R3:
            b.tell(rid, {"orders": O3, "progress": "I am in the box room."})
        out = b.decide("r1", 12.0, "pick", pick_options("r1"))
        self.assertEqual((out.get("halted"), out.get("reason")), (True, "PlanningContextError"))
        self.assertEqual(stub.prompts, [])
        self.assertNotIn("hist_skip", b._states["r1"])
        self.assertNotIn("talk", b.record())

    def test_mandatory_context_still_overflows_when_no_message_is_left_to_cut(self):
        stub = FreeStub()
        b, stub = make_free("T1", robots=tuple("r%d" % i for i in range(1, 15)), stub=stub, max_input_bytes=1100)
        out = b.decide("r1", 12.0, "pick", pick_options("r1"))
        self.assertEqual((out.get("halted"), out.get("reason")), (True, "PlanningContextError"))
        self.assertEqual(stub.prompts, [])                                         # not sent: it could not fit even without messages


class BrainServerArgs(unittest.TestCase):
    BASE = ["--team", "T2", "--robots", "r1,r2,r3", "--port", "1", "--log-dir", "/tmp/x"]

    def test_defaults_are_off(self):
        a = brain_server.parse_args(self.BASE)
        self.assertEqual((a.talk, a.no_message_budget, a.leader_bind, a.hold_s, a.leader_seed, a.zones, a.scene_file, a.scene_id, a.max_input_bytes, a.map_doors),
                         (None, False, False, HOLD_S, None, None, None, None, None, False))

    def test_the_manifest_flag_sets_parse(self):
        p = ["--parser-fix", "--merge-calls", "--options-v2", "--talk", "free", "--no-message-budget", "--msg-delay-s", "2", "--say-fix-s", "1.45", "--say-per-char-s", "0.0036",
             "--read-fix-s", "0.7", "--read-per-char-s", "0.0018"]
        le = p + ["--leader-authority", "--leader-election", "--leader-bind", "--hold-s", "75", "--leader-seed", "1139440579"]
        a = brain_server.parse_args(self.BASE + le + ["--scene-file", "/not/there.json", "--scene-id", "S3M01"])
        self.assertEqual((a.talk, a.leader_bind, a.hold_s, a.leader_seed, str(a.scene_file)), ("free", True, 75.0, 1139440579, "/not/there.json"))
        a = brain_server.parse_args(["--team", "T1", "--robots", ",".join("r%d" % i for i in range(1, 10)), "--leader", "r1", "--port", "1", "--log-dir", "/x"] + p +
                                    ["--max-input-bytes", "24000", "--map-doors"])
        self.assertEqual((a.max_input_bytes, a.map_doors), (24000, True))
        self.assertTrue(brain_server.parse_args(self.BASE + ["--talk", "free", "--leader-binding"]).leader_bind)      # the name of the task text
        self.assertEqual(brain_server.parse_args(["--team", "T2", "--robots", ",".join("r%d" % i for i in range(1, 10)), "--leader", "r9", "--port", "1",
                                                 "--log-dir", "/x"]).leader, "r9")

    def test_bad_combinations_are_refused(self):
        for bad in (["--leader-binding"], ["--no-message-budget"], ["--say-fix-s", "2"], ["--talk", "free", "--hold-s", "5"], ["--leader-seed", "3"],
                    ["--talk", "free", "--protocol", "hub-hmas2"], ["--talk", "free", "--max-messages", "4"], ["--talk", "free", "--pre-exchange"],
                    ["--talk", "free", "--route-note"], ["--talk", "free", "--option-order", "reverse"], ["--scene-file", "x.json"], ["--zones", "sign1,bad"],
                    ["--max-input-bytes", "500"], ["--talk", "free", "--say-streak", "0"]):
            with self.assertRaises(SystemExit, msg=str(bad)), contextlib.redirect_stderr(io.StringIO()):
                brain_server.parse_args(self.BASE + bad)
        with self.assertRaises(SystemExit), contextlib.redirect_stderr(io.StringIO()):
            brain_server.parse_args(["--team", "T1", "--robots", "r1,r2,r3", "--port", "1", "--log-dir", "/x", "--talk", "free", "--leader-binding"])
        with self.assertRaises(SystemExit), contextlib.redirect_stderr(io.StringIO()):
            brain_server.parse_args(["--team", "T0", "--robots", "r1,r2,r3", "--port", "1", "--log-dir", "/x", "--talk", "free"])

    def test_large_planner_rows_of_the_manifests_carry_the_scale_bound(self):
        # a 9-robot prompt of free talk reached about 12.4 KB and a 6-robot multi-carry prompt (10 boxes) 9.4 KB in the scripted smoke, more with real talk:
        # every row of more than 3 robots with a planner (--talk free; the scripted-oracle rows have no planner flags) names 24000 and the several-door goal
        import csv
        files = sorted((ROOT.parent / "manifests").glob("phase2-*.csv"))
        if not files:
            self.skipTest("the manifests are not next to this copy of link/")
        rows = []
        for f in files:
            with open(f, newline="") as handle:
                rows += [r for r in csv.DictReader(handle) if len(r["robots"].split(",")) > 3 and "--talk" in r["server_args"]]
        # plan v11 (3 robots only) has no such row; the check stays for any larger-team list that comes back
        self.assertEqual([r["run_id"] for r in rows if "--max-input-bytes 24000" not in r["server_args"] or "--map-doors" not in r["server_args"]], [])

    def test_map_doors_goal(self):
        goal = brain_server.with_several_doors(brain_server.GOAL)
        self.assertIn("There are several doors", goal)
        self.assertNotIn("the door between the box room and the zone room", goal)
        self.assertIn("There are several doors", brain_server.with_several_doors(brain_server.GOAL_IDLE))
        self.assertEqual(brain_server.GOAL, GOAL)                            # the default goal text is untouched


if __name__ == "__main__":
    unittest.main()
