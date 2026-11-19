"""Offline tests of the second experiment's switches (stub LLM, no network, no paid call): --protocol peer-roco / hub-hmas2, --leader-election,
--msg-delay-s, --msg-loss, --fail-robot, --parser-fix, --merge-calls, --options-v2, --route-note. The default-off identity against the frozen
planner is tools/identity_check.py.

Run from the link folder:  python3 -B -m unittest brain.tests.test_protocol -v
"""
import json
import random
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
from brain import FINISH_V2, ROUTE_NOTE_LEADER, ROUTE_NOTE_MEMBER, WAIT_SUFFIX, TeamBrain  # noqa: E402
from brain.protocol import PEER_LAST, is_agree, nearest_option, parse_plan  # noqa: E402
from brain.tests.test_brain_v2 import GOAL, progress_of  # noqa: E402

R3 = ("r1", "r2", "r3")
PLAN = {"r1": {"box": "blue", "zone": "sign11"}, "r2": {"box": "red", "zone": "sign12"}, "r3": "stay"}
PLAN2 = {"r1": {"box": "blue", "zone": "sign13"}, "r2": {"box": "red", "zone": "sign12"}, "r3": {"box": "red", "zone": "sign11"}}


def pick_options(rid):
    return [{"key": "box:0", "text": "go grasp target object <blue box> in the box room, 1.2 m away, 10° left of me (my label %s-box0)" % rid},
            {"key": "box:1", "text": "go grasp target object <red box> in the box room, 0.8 m away, straight ahead of me (my label %s-box1)" % rid},
            {"key": "box:2", "text": "go grasp target object <red box> in the box room, 2.0 m away, 30° right of me (my label %s-box2)" % rid},
            {"key": "wait", "text": "wait here for now"}, {"key": "finish", "text": "finish: there is nothing useful for me to do"}]


DEST = [{"key": "zone:sign11", "text": "transport the box I am holding to the <sign11 zone>"},
        {"key": "zone:sign12", "text": "transport the box I am holding to the <sign12 zone>"},
        {"key": "zone:sign13", "text": "transport the box I am holding to the <sign13 zone>"},
        {"key": "wait", "text": "wait here, holding the box"}, {"key": "put_down", "text": "put the box I am holding down here and finish"}]
DOOR = [{"key": "go", "text": "carry the box through the door now (one robot at a time fits)"}, {"key": "wait", "text": "wait here before going to the door"}]


class Stub:
    """Scripted model. peer: every speaker says PROCEED until `execute_after` utterances were made, then EXECUTE + plan (unless never_execute);
    hub: the proposal is `plan`, member objections per `objectors` for the first `object_rounds` reviews, the revision is `plan2`;
    anything else (a plain choice) answers the first listed label."""

    def __init__(self, plan=PLAN, plan2=PLAN2, execute_after=3, never_execute=False, objectors=(), object_rounds=1, garbage_plan=0, choice=None):
        self.plan, self.plan2, self.execute_after, self.never_execute = plan, plan2, execute_after, never_execute
        self.objectors, self.object_rounds, self.garbage_plan, self.choice = set(objectors), object_rounds, garbage_plan, choice
        self.prompts, self.reviews, self.records = [], 0, []

    def call(self, prompt, response_format=None):
        self.prompts.append(prompt)
        robot = progress_of(prompt)["robot"]
        if "generate a short message" in prompt:
            return {"raw_output": json.dumps({"message": "hello from %s" % robot, "facts": []})}
        if "speak in our team dialogue" in prompt:
            lines = len(re.findall(r"^r\d: ", prompt.split("Team dialogue this round")[1].split("You are robot")[0], re.M))
            if self.never_execute:
                return {"raw_output": "I see boxes. PROCEED"}
            if lines + 1 >= self.execute_after:
                if self.garbage_plan:
                    self.garbage_plan -= 1
                    return {"raw_output": "EXECUTE it is decided"}
                return {"raw_output": "OK. EXECUTE " + json.dumps(self.plan)}
            return {"raw_output": "I have a blue box. PROCEED"}
        if "propose the plan for the whole team" in prompt:
            return {"raw_output": json.dumps(self.plan)}
        if "review the leader's plan" in prompt:
            self.reviews += 1
            if robot in self.objectors and self.reviews <= self.object_rounds * 2:
                return {"raw_output": "No: I hold the order for blue -> sign13."}
            return {"raw_output": "I Agree"}
        if "revise the plan for the whole team" in prompt:
            return {"raw_output": "Revised: " + json.dumps(self.plan2)}
        if prompt.endswith("So the answer is option") or '"action":"option label"' in prompt or "Answer with only the option label" in prompt:
            return {"raw_output": self.choice if self.choice is not None else json.dumps({"action": "A"})}
        return {"raw_output": '{"reasoning":"stub"}'}


_TEMP = []


def tearDownModule():
    for tmp in _TEMP:
        tmp.cleanup()


def make(team, stub=None, robots=R3, leader=None, orders=None, **kw):
    tmp = tempfile.TemporaryDirectory()
    _TEMP.append(tmp)
    stub = stub or Stub()
    brain = TeamBrain(team, list(robots), GOAL, client=stub, log_dir=Path(tmp.name), leader=leader, **kw)
    for rid in robots:
        brain.tell(rid, {"orders": (orders or {}).get(rid, []), "progress": "I am in the box room."})
    return brain, stub


def first_round(brain, t=12.0, robots=R3):
    """The three robots ask their first pick decision at the same simulated second, in number order (what the bridge does)."""
    return {rid: brain.decide(rid, t, "pick", pick_options(rid)) for rid in robots}


class Helpers(unittest.TestCase):
    def test_parse_plan(self):
        plan, err = parse_plan("fine. EXECUTE " + json.dumps(PLAN), R3)
        self.assertEqual((plan["r1"], plan["r3"], err), ({"box": "blue", "zone": "sign11"}, None, None))
        self.assertIsNone(parse_plan('{"r1": "stay"}', R3)[0])
        self.assertIsNone(parse_plan("EXECUTE nothing", R3)[0])
        self.assertIsNone(parse_plan(json.dumps({**PLAN, "r2": {"box": "green", "zone": "sign12"}}), R3)[0])
        self.assertEqual(parse_plan('EXECUTE {"r1":"stay","r2":"stay"} then EXECUTE ' + json.dumps(PLAN), R3)[0]["r2"], {"box": "red", "zone": "sign12"})

    def test_agree_and_nearest_option(self):
        self.assertTrue(all(is_agree(t) for t in ("I Agree", " i agree. ", '"I Agree"', "I Agree.\n\nI see three boxes", "I Agree, but the zone is wrong")))
        self.assertFalse(any(is_agree(t) for t in ("No: the zone is wrong", "I do not agree", "I disagree with the plan", "I can't agree")))
        self.assertEqual(nearest_option(pick_options("r1"), "red"), "box:1")        # 0.8 m beats 2.0 m
        self.assertEqual(nearest_option(pick_options("r1"), "blue"), "box:0")
        self.assertIsNone(nearest_option(pick_options("r1")[:1], "red"))


class Peer(unittest.TestCase):
    def test_hold_then_round_in_the_last_callers_decide(self):
        b, stub = make("T1", protocol="peer-roco")
        out = {}
        out["r1"] = b.decide("r1", 12.0, "pick", pick_options("r1"))
        out["r2"] = b.decide("r2", 12.0, "pick", pick_options("r2"))
        self.assertEqual((out["r1"]["option"], out["r1"]["calls"], out["r2"]["option"], len(stub.prompts)), ("wait", 0, "wait", 0))    # held, no call
        out["r3"] = b.decide("r3", 12.0, "pick", pick_options("r3"))
        self.assertEqual(len(stub.prompts), 3)                        # r1, r2, r3 speak once each; EXECUTE comes from the third (all have spoken)
        self.assertEqual(out["r3"]["option"], "finish")               # PLAN gives r3 "stay"

    def test_peer_round_plan_is_read_by_every_robot(self):
        b, stub = make("T1", protocol="peer-roco", stub=Stub(plan=PLAN2))
        first_round_out = first_round(b)
        self.assertEqual(first_round_out["r3"]["option"], "box:1")     # r3: red box -> nearest red (0.8 m)
        self.assertEqual([m["via"] for m in b._messages], ["protocol"] * 3)
        self.assertEqual(b._messages[0]["to"], ["r2", "r3"])            # a peer utterance goes to everyone else
        self.assertEqual(b.decide("r1", 13.0, "pick", pick_options("r1"))["option"], "wait")      # plan reaches r1 at 14.0 (delay 2 s)
        self.assertEqual(b.decide("r1", 14.0, "pick", pick_options("r1"))["option"], "box:0")
        self.assertEqual(b.decide("r2", 14.0, "pick", pick_options("r2"))["option"], "box:1")
        dest = b.decide("r1", 60.0, "destination", DEST)
        self.assertEqual((dest["option"], dest["calls"]), ("zone:sign13", 0))        # no model call: the plan decides
        rec = b.record()
        self.assertEqual(rec["conditions"]["protocol"]["mode"], "peer-roco")
        rnd = rec["conditions"]["protocol"]["rounds"][0]
        self.assertEqual((rnd["reason"], rnd["calls"], rnd["status"], rnd["participants"]), ("first_pick", 3, "plan", list(R3)))
        self.assertEqual(rnd["delivery"], {"r1": 14.0, "r2": 14.0, "r3": 12.0})

    def test_stay_entry_finishes(self):
        b, _ = make("T1", protocol="peer-roco")
        out = first_round(b)
        self.assertEqual(out["r3"]["option"], "finish")                # PLAN gives r3 "stay"

    def test_execute_is_refused_before_everyone_has_spoken(self):
        b, stub = make("T1", protocol="peer-roco", stub=Stub(execute_after=1))      # r1 says EXECUTE at once, which only counts after all spoke
        first_round(b)
        self.assertEqual(len(stub.prompts), 3)
        rnd = b.record()["conditions"]["protocol"]["rounds"][0]
        self.assertEqual(rnd["calls"], 3)
        self.assertEqual([u["speaker"] for u in rnd["utterances"]], list(R3))

    def test_call_limit_forced_execute_sentence_and_empty_plan(self):
        b, stub = make("T1", protocol="peer-roco", stub=Stub(never_execute=True))
        first_round(b)
        self.assertEqual(len(stub.prompts), 12 + 2)                    # cap 10 is checked at the start of a cycle: 4 cycles = 12 calls; then r3 chooses alone (2 calls)
        talk = [p for p in stub.prompts if "speak in our team dialogue" in p]
        self.assertEqual([PEER_LAST in p for p in talk].count(True), 1)  # only the call with index 9 carries the sentence
        self.assertIn(PEER_LAST, talk[9])
        self.assertEqual(b.record()["conditions"]["protocol"]["rounds"][0]["status"], "empty")

    def test_unreadable_plan_is_asked_again_then_accepted(self):
        b, stub = make("T1", protocol="peer-roco", stub=Stub(garbage_plan=1))
        first_round(b)
        rnd = b.record()["conditions"]["protocol"]["rounds"][0]
        self.assertEqual((rnd["syntax_errors"], rnd["status"]), (1, "plan"))
        self.assertTrue(any("could not be used" in p for p in stub.prompts))

    def test_second_pick_after_a_lost_grasp_opens_a_new_round(self):
        b, stub = make("T1", protocol="peer-roco", stub=Stub(plan=PLAN2))
        first_round(b)
        b.decide("r1", 14.0, "pick", pick_options("r1")); b.decide("r2", 14.0, "pick", pick_options("r2"))
        before = len(stub.prompts)
        b.decide("r1", 90.0, "pick", pick_options("r1"))                # r1 lost its box and asks for a pick again
        self.assertEqual(len(b.record()["conditions"]["protocol"]["rounds"]), 2)
        self.assertEqual(b.record()["conditions"]["protocol"]["rounds"][1]["reason"], "regrasp")
        self.assertGreater(len(stub.prompts) - before, 2)

    def test_a_robot_that_never_asks_does_not_block_after_hold_s(self):
        b, stub = make("T1", protocol="peer-roco", stub=Stub(plan={"r1": {"box": "blue", "zone": "sign11"}, "r2": "stay", "r3": "stay"}))
        self.assertEqual(b.decide("r1", 12.0, "pick", pick_options("r1"))["option"], "wait")
        self.assertEqual(b.decide("r2", 13.0, "pick", pick_options("r2"))["option"], "wait")
        out = b.decide("r1", 32.0, "pick", pick_options("r1"))        # r3 never asked: after HOLD_S the round opens without it
        self.assertEqual(out["option"], "box:0")
        self.assertEqual(b.record()["conditions"]["protocol"]["rounds"][0]["participants"], ["r1", "r2"])

    def test_chance_is_final_and_no_budget_text(self):
        b, stub = make("T1", protocol="peer-roco")
        first_round(b)
        self.assertTrue(b.chance("r1", 20.0)["final"])
        self.assertNotIn("at most", " ".join(stub.prompts))
        self.assertNotIn("Messages left", " ".join(stub.prompts))


class Hub(unittest.TestCase):
    def test_proposal_review_revision_and_latest_plan(self):
        b, stub = make("T2", protocol="hub-hmas2", stub=Stub(objectors=("r2",), object_rounds=1))
        first_round(b)
        rnd = b.record()["conditions"]["protocol"]["rounds"][0]
        # proposal 1 + reviews r2, r3 + revision 1 + reviews r2, r3 (all agree) = 6 calls
        self.assertEqual((rnd["calls"], rnd["review_rounds"], rnd["status"]), (6, 2, "plan"))
        self.assertEqual(json.loads(rnd["plan"]), {"r1": {"box": "blue", "zone": "sign13"}, "r2": {"box": "red", "zone": "sign12"},
                                                    "r3": {"box": "red", "zone": "sign11"}})
        review_prompts = [p for p in stub.prompts if "review the leader's plan" in p]
        self.assertTrue(all("No: I hold the order" not in p for p in review_prompts if progress_of(p)["robot"] == "r3"))   # r3 never sees r2's objection
        revise = [p for p in stub.prompts if "revise the plan for the whole team" in p]
        self.assertEqual(len(revise), 1)
        self.assertIn("r2: No: I hold the order", revise[0])
        routes = [(m["from"], m["to"]) for m in b._messages]
        self.assertIn(("r2", ["r1"]), routes)                         # a member's review goes to the leader only
        self.assertIn(("r1", ["r2", "r3"]), routes)                   # the leader's plan goes to everyone

    def test_limit_of_three_review_rounds_then_latest_plan_runs(self):
        b, stub = make("T2", protocol="hub-hmas2", stub=Stub(objectors=("r2", "r3"), object_rounds=9))
        first_round(b)
        rnd = b.record()["conditions"]["protocol"]["rounds"][0]
        self.assertEqual((rnd["calls"], rnd["review_rounds"], rnd["status"]), (1 + 3 * (2 + 1), 3, "plan"))
        self.assertEqual(json.loads(rnd["plan"])["r1"]["zone"], "sign13")     # the latest (revised) plan

    def test_cmas_has_no_review(self):
        b, stub = make("T2", protocol="hub-hmas2", hub_rounds=0)
        first_round(b)
        rnd = b.record()["conditions"]["protocol"]["rounds"][0]
        self.assertEqual((rnd["calls"], rnd["review_rounds"]), (1, 0))

    def test_leader_other_than_r1_and_election(self):
        orders = {"r2": [{"box": "red", "count": 1, "zone": "sign12"}, {"box": "blue", "count": 1, "zone": "sign13"}], "r3": [{"box": "red", "count": 1, "zone": "sign12"}]}
        b, stub = make("T2", protocol="hub-hmas2", leader="r3", orders=orders)
        first_round(b)
        self.assertEqual(b.record()["conditions"]["protocol"]["rounds"][0]["leader"], "r3")
        b, stub = make("T2", protocol="hub-hmas2", leader="r1", orders=orders, leader_election=True)
        first_round(b)
        rnd = b.record()["conditions"]["protocol"]["rounds"][0]
        self.assertEqual((rnd["leader"], rnd["election"]["counts"]), ("r2", {"r1": 0, "r2": 2, "r3": 1}))
        self.assertTrue(any("Agent 1 means robot r1, Agent 2 means robot r2" in p for p in stub.prompts))
        b, _ = make("T2", protocol="hub-hmas2", leader_election=True)                    # nobody knows anything: tie, lowest number
        first_round(b)
        self.assertEqual(b.record()["conditions"]["protocol"]["rounds"][0]["leader"], "r1")


class Conditions(unittest.TestCase):
    def test_loss_removes_the_plan_for_the_robot_that_did_not_get_it(self):
        b, stub = make("T1", protocol="peer-roco", stub=Stub(plan=PLAN2, execute_after=1), msg_loss=0.999, msg_seed=3)
        out = first_round(b)
        self.assertEqual(out["r3"]["option"], "box:1")                  # the last speaker holds its own plan
        later = b.decide("r1", 14.0, "pick", pick_options("r1"))        # r1 never received the EXECUTE message: it decides alone (stub: label A = box:0)
        self.assertEqual(later["option"], "box:0")
        self.assertTrue(all(m.get("lost") for m in b._messages))

    def test_delay_postpones_the_plan(self):
        b, _ = make("T1", protocol="peer-roco", stub=Stub(plan=PLAN2), msg_delay_s=6.0)
        first_round(b)
        self.assertEqual(b.decide("r1", 14.0, "pick", pick_options("r1"))["option"], "wait")
        self.assertEqual(b.decide("r1", 18.0, "pick", pick_options("r1"))["option"], "box:0")
        self.assertEqual(b._messages[0]["deliver_at"], 18.0)

    def test_loss_is_deterministic_per_seed(self):
        def lost(seed):
            b, _ = make("T1", protocol="peer-roco", msg_loss=0.5, msg_seed=seed)
            first_round(b)
            return [m.get("lost") for m in b._messages]
        self.assertEqual(lost(5), lost(5))
        self.assertTrue(any(lost(s) != lost(5) for s in range(6, 12)))

    def test_failed_robot_is_halted_does_not_speak_and_is_not_waited_for(self):
        b, stub = make("T1", protocol="peer-roco", stub=Stub(plan=PLAN2), fail_robot="r2", fail_at_s=5.0)
        out = {rid: b.decide(rid, 12.0, "pick", pick_options(rid)) for rid in R3}
        self.assertTrue(out["r2"]["halted"] and out["r2"]["reason"] == "robot_failed")
        self.assertEqual(b.record()["conditions"]["protocol"]["rounds"][0]["participants"], ["r1", "r3"])
        self.assertTrue(all(m["from"] != "r2" and "r2" not in m["to"] for m in b._messages))
        self.assertEqual(b.record()["conditions"]["fail"], {"robot": "r2", "at_s": 5.0})

    def test_failure_also_applies_to_the_v38_style_flow(self):
        b, stub = make("T2", stub=Stub(), fail_robot="r1", fail_at_s=30.0)
        self.assertFalse(b.decide("r1", 12.0, "pick", pick_options("r1")).get("halted"))
        late = b.decide("r1", 40.0, "pick", pick_options("r1"))
        self.assertTrue(late["halted"] and late["reason"] == "robot_failed")
        self.assertTrue(b.chance("r1", 41.0)["final"])

    def test_delay_and_loss_in_the_v38_style_flow(self):
        b, _ = make("T1", stub=Stub(), msg_delay_s=5.0)
        b._post("r1", 10.0, "{}")
        self.assertEqual(b._messages[0]["deliver_at"], 15.0)
        b, _ = make("T1", stub=Stub(), msg_loss=0.999, msg_seed=1)
        b._post("r1", 10.0, "{}")
        self.assertEqual((b._messages[0]["to"], sorted(b._messages[0]["lost"])), ([], ["r2", "r3"]))

    def test_bad_arguments(self):
        for team, kw in [("T0", dict(protocol="peer-roco")), ("T2", dict(protocol="peer-roco")), ("T1", dict(protocol="hub-hmas2")),
                         ("T1", dict(protocol="peer-roco", max_messages=4)), ("T1", dict(leader_election=True)), ("T0", dict(msg_loss=0.1)),
                         ("T1", dict(msg_loss=1.0)), ("T1", dict(fail_robot="r2")), ("T1", dict(fail_robot="r9", fail_at_s=1.0)),
                         ("T2", dict(protocol="hub-hmas2", hub_rounds=-1)), ("T1", dict(protocol="peer-roco", peer_max_calls=2)), ("T1", dict(protocol="x"))]:
            with self.assertRaises(ValueError, msg=(team, kw)):
                make(team, **kw)


class SmallSwitches(unittest.TestCase):
    def pick(self, brain):
        return brain.decide("r1", 12.0, "pick", pick_options("r1"))

    def test_parser_fix_reads_json_followed_by_text_and_a_leading_label(self):
        garbled = '{"action":"C","send":false}  Reasoning: it is closest.'
        b, stub = make("T0", stub=Stub(choice=garbled), parser_fix=True)
        self.assertEqual(self.pick(b)["option"], "box:2")                    # C = third listed
        b, stub = make("T0", stub=Stub(choice='{"action":"B. go grasp target object <red box>"}'), parser_fix=True)
        self.assertEqual(self.pick(b)["option"], "box:1")
        self.assertFalse(any(e["event"] == "random_fallback" for e in b._planner.plan_events))

    def test_default_parser_falls_back_to_random_on_the_same_answer(self):
        garbled = '{"action":"C","send":false}  Reasoning: it is closest.'
        random.seed(1)
        b, _ = make("T0", stub=Stub(choice=garbled))
        self.pick(b)
        self.assertTrue(any(e["event"] == "random_fallback" for e in b._planner.plan_events))

    def test_unreadable_answer_is_asked_once_more_before_a_fallback_is_recorded(self):
        class Twice(Stub):
            def call(self, prompt, response_format=None):
                if "could not be matched" in prompt:
                    self.prompts.append(prompt)
                    return {"raw_output": '{"action":"D"}'}
                return super().call(prompt, response_format)
        b, stub = make("T0", stub=Twice(choice="hmm hard to say"), parser_fix=True)
        self.assertEqual(self.pick(b)["option"], "wait")                       # D = wait, from the second answer
        events = [e["event"] for e in b._planner.plan_events]
        self.assertIn("parse_retry", events)
        self.assertNotIn("random_fallback", events)

    def test_merge_calls_is_one_call_per_choice(self):
        plain, p_stub = make("T0", stub=Stub())
        merged, m_stub = make("T0", stub=Stub(choice='{"reasoning":"x","action":"B"}'), merge_calls=True)
        self.pick(plain)
        self.assertEqual(self.pick(merged)["option"], "box:1")
        self.assertEqual((len(p_stub.prompts), len(m_stub.prompts)), (2, 1))
        self.assertIn('Return {"reasoning":"text","action":"option label"}', m_stub.prompts[0])

    def test_options_v2_and_route_note(self):
        b, stub = make("T1", stub=Stub(), options_v2=True)
        self.pick(b)
        rec = b.record()["decisions"]["r1"][0]["options"]
        self.assertTrue(rec[3]["text"].endswith(WAIT_SUFFIX))
        self.assertEqual(rec[4]["text"], FINISH_V2)
        b, stub = make("T2", stub=Stub(), route_note=True, leader="r2")
        for rid in R3:
            b.decide(rid, 12.0, "pick", pick_options(rid))
        for p in stub.prompts:
            self.assertIn(ROUTE_NOTE_LEADER if progress_of(p)["robot"] == "r2" else ROUTE_NOTE_MEMBER, p)

    def test_server_arguments(self):
        base = ["--team", "T2", "--robots", "r1,r2,r3", "--port", "1", "--log-dir", "/x"]
        a = brain_server.parse_args(base + ["--protocol", "hub-hmas2", "--hub-rounds", "0", "--leader-election", "--msg-loss", "0.2", "--msg-seed", "7",
                                            "--msg-delay-s", "6", "--fail-robot", "r1", "--fail-at-s", "60", "--parser-fix", "--merge-calls",
                                            "--options-v2", "--route-note"])
        self.assertEqual((a.protocol, a.hub_rounds, a.leader_election, a.msg_loss, a.msg_delay_s, a.fail_robot, a.fail_at_s),
                         ("hub-hmas2", 0, True, 0.2, 6.0, "r1", 60.0))
        for bad in (["--team", "T1", "--protocol", "hub-hmas2"], ["--team", "T2", "--protocol", "hub-hmas2", "--max-messages", "8"],
                    ["--team", "T1", "--leader-election"], ["--team", "T1", "--fail-robot", "r2"], ["--team", "T0", "--msg-loss", "0.1"],
                    ["--team", "T1", "--fail-robot", "r9", "--fail-at-s", "5"]):
            with self.assertRaises(SystemExit, msg=bad), mock.patch("sys.stderr"):
                brain_server.parse_args(bad + ["--robots", "r1,r2,r3", "--port", "1", "--log-dir", "/x"])
        d = brain_server.parse_args(base)
        self.assertEqual((d.protocol, d.hub_rounds, d.peer_max_calls, d.leader_election, d.msg_delay_s, d.msg_loss, d.fail_robot, d.parser_fix,
                          d.merge_calls, d.options_v2, d.route_note), (None, 3, 10, False, 2.0, 0.0, None, False, False, False, False))



class PeerWordingAndElectedLeader(unittest.TestCase):
    """2026-11-17 smoke fixes: the peer prompt follows the original dialog instruction (EXECUTE when everyone has made proposals and got approved);
    an elected (or replacement) leader is the leader of the run from the election on: prompts, routing and the record's top-level leader."""
    ORIGINAL = ("End your response by either: 1) output PROCEED, if the plans require further discussion; 2) If everyone has made proposals and got "
                "approved, output the final plan as soon as possible, must strictly follow [Action Output Instruction]!")

    def test_peer_prompt_follows_the_original_instruction(self):
        from brain.protocol import PEER_RULE
        b, stub = make("T1", protocol="peer-roco", stub=Stub(plan=PLAN2))
        first_round(b)
        speak = [p for p in stub.prompts if "speak in our team dialogue" in p]
        self.assertEqual(len(speak), 3)
        for p in speak:
            self.assertIn(self.ORIGINAL, p)
            self.assertIn("[Action Output Instruction]\nMust first output 'EXECUTE', then on the new line give the plan as one JSON object", p)
            self.assertIn("Propose exactly one action for yourself at the **current** round.", p)
            self.assertIn("Carefully check and correct them if they made a mistake.", p)
            self.assertNotIn("hand over to the next robot", p)          # the first wording that never led to an EXECUTE
        self.assertIn("Say concisely what you know or see that your friends need", PEER_RULE)     # kept: our partial observations

    def test_execute_still_needs_everyone_to_have_spoken_and_the_last_call_is_forced(self):
        b, stub = make("T1", protocol="peer-roco", stub=Stub(plan=PLAN2, execute_after=1))        # the first speaker already says EXECUTE: not accepted yet
        first_round(b)
        rnd = b.record()["conditions"]["protocol"]["rounds"][0]
        self.assertEqual(rnd["calls"], 3)
        b, stub = make("T1", protocol="peer-roco", stub=Stub(never_execute=True))
        first_round(b)
        last = [p for p in stub.prompts if "speak in our team dialogue" in p][9]      # the call with index peer_max_calls - 1 (RoCo code); the cycle then runs to its end (12 calls)
        self.assertIn("This is the last call: you must end your response by incorporating all previous discussions and output the best plan via EXECUTE.", last)
        self.assertEqual(len([p for p in stub.prompts if "last call" in p]), 1)

    def test_elected_leader_is_the_leader_of_the_run(self):
        orders = {"r2": [{"box": "red", "count": 1, "zone": "sign12"}, {"box": "blue", "count": 1, "zone": "sign13"}], "r3": [{"box": "red", "count": 1, "zone": "sign12"}]}
        b, stub = make("T2", protocol="hub-hmas2", leader="r1", orders=orders, leader_election=True)
        self.assertEqual(b.record()["leader"], "r1")                    # before the first round the --leader value
        first_round(b)
        rec = b.record()
        self.assertEqual((b.leader, rec["leader"], rec["elected_leader"]), ("r2", "r2", "r2"))
        self.assertEqual(rec["conditions"]["protocol"]["rounds"][0]["leader"], "r2")
        round_prompts = [p for p in stub.prompts if "propose the plan" in p or "review the leader's plan" in p]
        self.assertTrue(round_prompts)
        for p in round_prompts:
            self.assertIn("Agent 2 is the leader to coordinate the task.", p)
            self.assertNotIn("Agent 1 is the leader", p)
        self.assertEqual(b._recipients("r3"), ["r2"])                   # T2 routing: a member's later messages go to the elected leader

    def test_no_election_no_elected_leader_key_and_the_leader_stays(self):
        b, _ = make("T2", protocol="hub-hmas2", leader="r3")
        first_round(b)
        rec = b.record()
        self.assertEqual((b.leader, rec["leader"]), ("r3", "r3"))
        self.assertNotIn("elected_leader", rec)

    def test_failed_leader_is_replaced_for_the_run(self):
        b, _ = make("T2", protocol="hub-hmas2", leader="r1", fail_robot="r1", fail_at_s=5.0)
        for rid in ("r2", "r3"):
            b.decide(rid, 12.0, "pick", pick_options(rid))
        rec = b.record()
        self.assertEqual((rec["leader"], rec["conditions"]["protocol"]["rounds"][0]["leader"]), ("r2", "r2"))
        self.assertNotIn("elected_leader", rec)                          # nobody was elected by the switch: the replacement follows the same rule


if __name__ == "__main__":
    unittest.main()
