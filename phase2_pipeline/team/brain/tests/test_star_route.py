"""Offline tests of the star route (--leader-route star, PREREG-PHASE2.md 8): in a free-talk T2 run ALL communication goes through the leader. A member's only say
entry is "say to <leader>"; words it addresses to another member or to everyone are delivered to the leader only and counted; the leader keeps every entry. Stub model,
no network, no paid call. With the switch off nothing changes (tools/identity_check.py proves the talk-off identity, the hash compare of tools/smoke_bridge.py cases the P arm).

Run from the link folder:  python3 -B -m unittest brain.tests.test_star_route -v
"""
import contextlib
import io
import json
import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))
sys.dont_write_bytecode = True

import brain_server  # noqa: E402
from brain import TeamBrain  # noqa: E402
from brain.talk import (FREE_FINAL, FREE_RULE, FREE_RULE_STAR_MEMBER, RELAY_NOTE, SILENT_TEXT, STAR_LEADER, STAR_MEMBER, STAR_MEMBER_DOWN,  # noqa: E402
                        read_say_beside_action, read_time)
from brain.tests.test_brain_v2 import progress_of  # noqa: E402
from brain.tests.test_free_talk import O3, FreeStub, listing_of, make_free  # noqa: E402
from brain.tests.test_protocol import R3, pick_options  # noqa: E402

R9 = tuple("r%d" % i for i in range(1, 10))


def star(robots=R3, leader="r1", route="star", **kw):
    """A free T2 brain; the leader r1 knows every order unless `orders` says otherwise."""
    kw = dict(dict(leader_authority=True, leader_route=route), **kw)
    kw.setdefault("orders", {leader: O3})
    return make_free("T2", robots=robots, leader=leader, **kw)


def entries_of(prompt):
    return [t for _, t in listing_of(prompt) if t.startswith("say to ")]


class Menu(unittest.TestCase):
    def test_a_member_is_offered_the_leader_only_and_the_leader_everybody(self):
        b, stub = star()
        b.decide("r2", 12.0, "pick", pick_options("r2"))
        b.decide("r1", 12.0, "pick", pick_options("r1"))
        self.assertEqual(entries_of(stub.prompts_of("r2")[0]), ["say to r1: <text>"])
        self.assertEqual(entries_of(stub.prompts_of("r1")[0]), ["say to r2: <text>", "say to r3: <text>", "say to everyone: <text>"])

    def test_nine_robots_and_a_leader_that_is_not_r1(self):
        b, stub = star(R9, leader="r4")
        for rid in ("r1", "r4", "r9"):
            b.decide(rid, 12.0, "pick", pick_options(rid))
        self.assertEqual(entries_of(stub.prompts_of("r1")[0]), ["say to r4: <text>"])
        self.assertEqual(entries_of(stub.prompts_of("r9")[0]), ["say to r4: <text>"])
        self.assertEqual(len(entries_of(stub.prompts_of("r4")[0])), 9)                  # eight teammates and everyone

    def test_the_chance_menu_of_a_member_is_silence_and_the_leader(self):
        b, stub = star(stub=FreeStub(say={"r1": [("r2", "start")]}))
        sent = b.decide("r1", 12.0, "pick", pick_options("r1"))["sent"][0]
        b.chance("r2", sent["deliver_at"] + read_time(5) + 1.0)
        listing = [t for _, t in listing_of(stub.prompts_of("r2")[-1])]
        self.assertEqual(listing, [SILENT_TEXT, "say to r1: <text>"])

    def test_without_the_switch_every_robot_is_offered_every_teammate(self):
        b, stub = star(route=None, leader_bind=True)
        b.decide("r2", 12.0, "pick", pick_options("r2"))
        self.assertEqual(entries_of(stub.prompts_of("r2")[0]), ["say to r1: <text>", "say to r3: <text>", "say to everyone: <text>"])


class PromptRule(unittest.TestCase):
    def test_every_robot_is_told_the_rule(self):
        b, stub = star(leader="r2")
        b.decide("r1", 12.0, "pick", pick_options("r1"))
        b.decide("r2", 12.0, "pick", pick_options("r2"))
        member, leader = stub.prompts_of("r1")[0], stub.prompts_of("r2")[0]
        self.assertIn(STAR_MEMBER % "r2", member)
        self.assertIn("You can only talk to the leader r2; the leader relays.", member)
        self.assertIn("your teammates can only talk to you", leader)
        self.assertIn(STAR_LEADER, leader)
        self.assertNotIn(STAR_LEADER, member)
        self.assertNotIn(STAR_MEMBER % "r2", leader)

    def test_the_goal_sentence_about_speaking_names_the_leader_for_a_member_only(self):
        b, stub = star()
        b.decide("r2", 12.0, "pick", pick_options("r2"))
        b.decide("r1", 12.0, "pick", pick_options("r1"))
        member, leader = stub.prompts_of("r2")[0], stub.prompts_of("r1")[0]
        self.assertIn(FREE_RULE_STAR_MEMBER, member)
        self.assertNotIn(FREE_RULE, member)
        self.assertNotIn("say to everyone", member)
        self.assertIn(FREE_RULE, leader)                                        # the leader may speak to one teammate or to everyone
        self.assertNotIn(FREE_RULE_STAR_MEMBER, leader)
        self.assertIn("Besides acting you may speak", member + leader)             # the anchor the smoke model keys on

    def test_the_rule_is_stated_without_authority_or_binding_too(self):
        b, stub = star(leader_authority=False)
        b.decide("r2", 12.0, "pick", pick_options("r2"))
        b.decide("r1", 12.0, "pick", pick_options("r1"))
        self.assertIn("You can only talk to the leader r1; the leader relays.", stub.prompts_of("r2")[0])
        self.assertIn("your teammates can only talk to you", stub.prompts_of("r1")[0])

    def test_nothing_of_it_is_in_a_run_without_the_switch(self):
        b, stub = star(route=None, leader_bind=True)
        b.decide("r2", 12.0, "pick", pick_options("r2"))
        b.decide("r1", 12.0, "pick", pick_options("r1"))
        for prompt in stub.prompts:
            for text in ("can only talk to", "relays", "STAR", FREE_RULE_STAR_MEMBER):
                self.assertNotIn(text, prompt)
        self.assertIn(FREE_RULE, stub.prompts_of("r2")[0])

    def test_the_two_step_final_line_names_the_leader_for_a_member(self):
        def raw(prompt):
            if prompt.endswith("So the answer is option"):
                return "say to r3: pass this on"
            return '{"reasoning":"stub"}'
        b, stub = star(stub=FreeStub(raw=raw), merge_calls=False)
        out = b.decide("r2", 12.0, "pick", pick_options("r2"))
        final = [p for p in stub.prompts_of("r2") if p.endswith("So the answer is option")][0]
        self.assertIn("(for example: say to r1: your words)", final)
        self.assertNotIn("say to r2: your words", final)
        self.assertEqual((out["sent"][0]["to"], out["sent"][0]["redirected_from"]), (["r1"], "r3"))
        leader_prompts = stub.prompts_of("r1")
        b.decide("r1", 30.0, "pick", pick_options("r1"))
        self.assertIn(FREE_FINAL, stub.prompts_of("r1")[len(leader_prompts):][-1])       # the leader keeps the original line

    def test_the_input_bound_leaves_room_for_a_longer_leader_name(self):
        robots = tuple("r%d" % i for i in range(1, 13))
        b, _ = star(robots, leader="r12")
        self.assertEqual((b._free_suffix_extra("r1"), b._free_suffix_extra("r12")), (1, 0))
        self.assertEqual(len(b._free_final("r1").encode()) - len(FREE_FINAL.encode()), 1)
        p, _ = make_free("T1")
        self.assertEqual((p._free_suffix_extra("r1"), p._free_final("r1"), p._free_rule("r1")), (0, FREE_FINAL, FREE_RULE))


class Redirect(unittest.TestCase):
    def member_says(self, answer, rid="r2", robots=R3, leader="r1", **kw):
        raw = answer if callable(answer) else json.dumps(answer)
        b, stub = star(robots, leader, stub=FreeStub(raw=raw), **kw)
        return b, stub, b.decide(rid, 12.0, "pick", pick_options(rid))

    def assert_to_leader_only(self, b, out, redirected_from, label=""):
        self.assertNotIn("halted", out, label)
        self.assertEqual(len(out["sent"]), 1, label)
        m = out["sent"][0]
        self.assertEqual((m["to"], m["tgt"], out["option"]), (["r1"], "r1", "wait"), label)
        self.assertEqual(m.get("redirected_from"), redirected_from, label)
        events = b.record()["talk"]["events"]
        self.assertEqual(events.get("member_redirected_to_leader"), 1 if redirected_from else None, label)
        self.assertEqual(b.record()["star"]["member_messages_to_non_leader"], 0, label)
        self.assertEqual([r for r, why in b._halts.items() if why], [], label)

    def test_every_shape_that_addresses_someone_else_goes_to_the_leader_and_is_counted(self):
        words = "take the red box to sign13"
        shapes = [
            ("say to a member", {"action": "say to r3: " + words}, "r3"),
            ("say to everyone", {"action": "say to everyone: " + words}, "everyone"),
            ("say to a member, words in the say field", {"action": "say to r3: <text>", "say": words}, "r3"),
            ("body label, to field member", {"action": "B", "say": words, "to": "r3"}, "r3"),
            ("body label, to field everyone", {"action": "B", "say": words, "to": "everyone"}, "everyone"),
            ("body label, to field all", {"action": "B", "say": words, "to": "all"}, "everyone"),
            ("body label, to list of every other robot", {"action": "B", "say": words, "to": ["r1", "r3"]}, "everyone"),
            ("body label, leading address", {"action": "B", "say": "r3, " + words}, "r3"),
            ("body label, leading address with a colon", {"action": "B", "say": "R3: " + words}, "r3"),
            ("body label, to field beats the leading address", {"action": "B", "say": "r1, " + words, "to": "r3"}, "r3"),
        ]
        for name, answer, source in shapes:
            b, stub, out = self.member_says(answer)
            self.assert_to_leader_only(b, out, source, name)
            self.assertTrue(json.loads(out["sent"][0]["text"])["message"].endswith(words), name)           # the words themselves are unchanged
            self.assertEqual(b.record()["star"]["redirected_by_addressee"], {source: 1}, name)
            if "say_with_action" in out:
                self.assertEqual(out["say_with_action"]["key"], "box:1", name)                  # the body label of that answer was not done

    def test_a_list_naming_several_members_is_counted_with_its_names(self):
        b, stub, out = self.member_says({"action": "B", "say": "all of you wait", "to": ["r3", "r4"]}, robots=R9)
        self.assert_to_leader_only(b, out, "r3,r4")

    def test_words_that_address_nobody_else_go_to_the_leader_without_a_count(self):
        answers = [("no addressee beside a body label", {"action": "B", "say": "I take the red box"}),
                   ("to field names the leader", {"action": "B", "say": "I take the red box", "to": "r1"}),
                   ("leading address of the leader", {"action": "B", "say": "r1, I take the red box"}),
                   ("say to the leader", {"action": "say to r1: I take the red box"}),
                   ("a say label of the leader's entry with the words in the field", {"action": "F", "say": "I take the red box"}),
                   ("a say label of the leader's entry, words start with a teammate's name", {"action": "F", "say": "r3, I take the red box"})]
        for name, answer in answers:
            b, stub, out = self.member_says(answer)
            self.assert_to_leader_only(b, out, None, name)
            self.assertNotIn("member_redirected_to_leader", b.record()["talk"]["events"], name)
            self.assertEqual(b.record()["star"]["redirected"], 0, name)

    def test_a_speech_to_nobody_is_not_redirected(self):
        for name, answer in (("itself", {"action": "say to r2: hello"}), ("a robot that is not in the team", {"action": "say to r7: hello"}),
                             ("no words", {"action": "say to r3: <text>"}), ("no words, everyone", {"action": "say to everyone: <text>"})):
            b, stub, out = self.member_says(answer)
            self.assertEqual((out["sent"], out["option"]), ([], "wait"), name)
            self.assertNotIn("halted", out, name)
            self.assertEqual(b.record()["talk"]["events"], {"say_to_nobody": 1}, name)
            self.assertEqual(b._messages, [], name)

    def test_an_unreadable_answer_that_is_asked_again_is_redirected_too(self):
        def raw(prompt):
            if "could not be matched" in prompt:
                return json.dumps({"action": "B", "say": "r3, retry words"})
            return '{"reasoning":"r","action":"zzz"}'
        b, stub, out = self.member_says(raw)
        self.assertEqual(len(stub.prompts), 2)
        self.assert_to_leader_only(b, out, "r3")

    def test_the_chance_path_redirects(self):
        def raw(prompt):
            robot = progress_of(prompt)["robot"]
            if robot == "r1":
                return json.dumps({"action": [l for l, t in listing_of(prompt) if t.startswith("say to r2")][0], "say": "start"})
            return json.dumps({"action": "A", "say": "r3, got it", "to": "r3"})            # the silence label with words, addressed to another member
        b, stub = star(stub=FreeStub(raw=raw))
        sent = b.decide("r1", 12.0, "pick", pick_options("r1"))["sent"][0]
        out = b.chance("r2", sent["deliver_at"] + read_time(5) + 1.0)
        self.assertTrue(out["asked"] and len(out["sent"]) == 1)
        m = out["sent"][0]
        self.assertEqual((m["via"], m["to"], m["tgt"], m["redirected_from"]), ("chance", ["r1"], "r1", "r3"))
        self.assertEqual(b.record()["talk"]["events"]["member_redirected_to_leader"], 1)
        self.assertFalse(out["final"])

    def test_a_member_cannot_assign_and_a_redirect_does_not_widen(self):
        b, stub, out = self.member_says({"action": "B", "say": "r3, assign r2: blue -> sign12"})
        self.assertEqual(out["sent"][0]["to"], ["r1"])
        self.assertNotIn("assign", out["sent"][0])
        self.assertNotIn("say_widened_for_assignments", b.record()["talk"]["events"])

    def test_read_say_beside_action_with_a_roster_returns_a_target_without_entry(self):
        menu = {"go grasp <blue box>": {"skill": "executor", "key": "box:0"}, "wait here for now": {"skill": "executor", "key": "wait"},
                "say to r1: <text>": {"skill": "say", "target": "r1", "to": ["r1"]}}
        label = lambda i: "ABC"[i]
        kw = dict(roster=["r1", "r3"], default="r1")
        got = read_say_beside_action(menu, {"say": "hi", "to": "r3"}, "A", label, **kw)
        self.assertEqual((got["target"], got["entry"]), ("r3", None))
        got = read_say_beside_action(menu, {"say": "hi"}, "A", label, **kw)
        self.assertEqual((got["target"], got["entry"]), ("r1", "say to r1: <text>"))
        got = read_say_beside_action(menu, {"say": "hi", "to": ["r1", "r3"]}, "A", label, **kw)
        self.assertEqual((got["target"], got["entry"]), ("everyone", None))
        self.assertEqual(read_say_beside_action(menu, {"say": "r3, hi"}, "A", label, **kw)["target"], "r3")
        self.assertEqual(read_say_beside_action(menu, {"say": "r2, hi"}, "A", label, **kw)["target"], "r1")             # not a robot of the roster: the default
        self.assertEqual(read_say_beside_action(menu, {"say": "hi", "to": "r2"}, "A", label, **kw)["target"], "r1")


class LeaderAndPrivacy(unittest.TestCase):
    def test_the_leader_may_speak_to_one_member_or_to_everyone(self):
        b, stub = star(stub=FreeStub(say={"r1": [("r2", "only r2"), ("everyone", "all of you")]}))
        one = b.decide("r1", 12.0, "pick", pick_options("r1"))["sent"][0]
        self.assertEqual((one["to"], one["tgt"]), (["r2"], "r2"))
        b._states["r1"]["say_streak"] = 0                                          # a new message would clear it; keep the test about the target
        both = b.decide("r1", 40.0, "pick", pick_options("r1"))["sent"][0]
        self.assertEqual((both["to"], both["tgt"]), (["r2", "r3"], "everyone"))
        self.assertNotIn("redirected_from", one)
        self.assertNotIn("member_redirected_to_leader", b.record()["talk"]["events"])

    def test_the_assign_widening_rule_still_applies_to_the_leader(self):
        raw = json.dumps({"action": "B", "say": "r2: take the blue box to sign12. assign r3: red -> sign11"})
        b, stub = star(stub=FreeStub(raw=raw), leader_bind=True)
        out = b.decide("r1", 12.0, "pick", pick_options("r1"))
        m = out["sent"][0]
        self.assertEqual((m["to"], m["tgt"]), (["r2", "r3"], "everyone"))
        self.assertEqual(out["say_with_action"]["widened_from"], "r2")
        ready = m["deliver_at"] + read_time(len(json.loads(raw)["say"]))
        self.assertEqual(b._assignment("r3", ready + 0.1)["zone"], "sign11")

    def test_a_member_message_reaches_the_leader_and_no_other_member(self):
        secret = "SECRET-FROM-R2 the red box is at the left wall"
        def raw(prompt):
            robot = progress_of(prompt)["robot"]
            if robot == "r2" and secret not in prompt:
                return json.dumps({"action": "say to everyone: " + secret})
            return json.dumps({"action": [l for l, t in listing_of(prompt) if not t.startswith("say to ")][0]})
        b, stub = star(stub=FreeStub(raw=raw))
        sent = b.decide("r2", 12.0, "pick", pick_options("r2"))["sent"][0]
        self.assertEqual((sent["to"], sent["redirected_from"]), (["r1"], "everyone"))
        late = sent["deliver_at"] + read_time(len(secret)) + 5.0
        b.decide("r3", late, "pick", pick_options("r3"))
        b.decide("r1", late + 1.0, "pick", pick_options("r1"))
        self.assertNotIn(secret, stub.prompts_of("r3")[-1])                          # r3 never hears r2
        self.assertIn(secret, stub.prompts_of("r1")[-1])                             # the leader does
        self.assertEqual(b._states["r1"]["dialogue"][-1]["to"], "me")
        # the leader relays: its own say to r3 is the only way the content reaches r3
        relay = b._speak("r1", late + 2.0, {"target": "r3", "to": ["r3"]}, "r2 says the red box is at the left wall")
        b.decide("r3", relay["deliver_at"] + read_time(40) + 1.0, "pick", pick_options("r3"))
        self.assertIn("r2 says the red box is at the left wall", stub.prompts_of("r3")[-1])
        self.assertNotIn(secret, stub.prompts_of("r3")[-1])

    def test_a_member_does_not_see_what_the_leader_says_to_another_member(self):
        b, stub = star(stub=FreeStub(say={"r1": [("r2", "PRIVATE-TO-R2 take blue")]}))
        sent = b.decide("r1", 12.0, "pick", pick_options("r1"))["sent"][0]
        b.decide("r3", sent["deliver_at"] + 30.0, "pick", pick_options("r3"))
        self.assertNotIn("PRIVATE-TO-R2", stub.prompts_of("r3")[-1])


class ElectionWindow(unittest.TestCase):
    ORDERS = {"r1": O3[:1], "r2": [], "r3": O3}

    def test_the_leader_is_known_before_the_first_entry_is_built(self):
        b, stub = star(leader="r1", orders=self.ORDERS, leader_election=True, leader_seed=1)
        self.assertEqual(b.leader, "r1")                                              # before the first decision the constructor's leader stands
        entries = b._say_entries("r2", 0.0)                                             # a menu asked before any decision: it elects first
        self.assertEqual((b.leader, [text for text, _ in entries]), ("r3", ["say to r3: <text>"]))
        self.assertEqual(len(b._say_entries("r3", 0.0)), 3)                              # the elected leader: r1, r2 and everyone

    def test_the_first_decision_elects_and_members_are_offered_the_elected_leader(self):
        b, stub = star(leader="r1", orders=self.ORDERS, leader_election=True, leader_seed=1)
        b.decide("r1", 12.0, "pick", pick_options("r1"))                               # r1 is no leader any more
        self.assertEqual(entries_of(stub.prompts_of("r1")[0]), ["say to r3: <text>"])
        self.assertIn(STAR_MEMBER % "r3", stub.prompts_of("r1")[0])
        self.assertEqual(b.record()["star"]["leader"], "r3")

    def test_a_chance_before_any_decision_elects_first(self):
        b, stub = star(leader="r1", orders=self.ORDERS, leader_election=True, leader_seed=1)
        out = b.chance("r1", 5.0)
        self.assertTrue(out["asked"])
        self.assertEqual(b.leader, "r3")
        self.assertEqual([t for _, t in listing_of(stub.prompts_of("r1")[0])], [SILENT_TEXT, "say to r3: <text>"])

    def test_without_an_election_the_given_leader_holds_from_the_start(self):
        b, stub = star(leader="r2")
        self.assertEqual([t for t, _ in b._say_entries("r1", 0.0)], ["say to r2: <text>"])


class Record(unittest.TestCase):
    def test_the_star_record(self):
        def raw(prompt):
            robot = progress_of(prompt)["robot"]
            if robot == "r2":
                return json.dumps({"action": "say to everyone: " + "x" * 50})             # redirected
            if robot == "r3":
                return json.dumps({"action": "F", "say": "y" * 30})                       # the leader's entry
            return json.dumps({"action": "B"})
        b, stub = star(stub=FreeStub(raw=raw))
        b.decide("r2", 12.0, "pick", pick_options("r2"))
        b.decide("r3", 12.0, "pick", pick_options("r3"))
        b._speak("r1", 20.0, {"target": "everyone", "to": ["r2", "r3"]}, "z" * 40)
        b._speak("r1", 30.0, {"target": "r2", "to": ["r2"]}, "w" * 20)
        rec = b.record()
        star_rec = rec["star"]
        self.assertEqual(star_rec["leader"], "r1")
        self.assertEqual(star_rec["says_by_recipient"], {"r1": {"r2": 2, "r3": 1}, "r2": {"r1": 1, "r3": 0}, "r3": {"r1": 1, "r2": 0}})
        self.assertEqual(star_rec["says_by_target"], {"r1": {"everyone": 1, "r2": 1}, "r2": {"r1": 1}, "r3": {"r1": 1}})
        self.assertEqual(star_rec["received_by_robot"], {"r1": 2, "r2": 2, "r3": 1})
        self.assertEqual((star_rec["member_messages"], star_rec["member_chars"], star_rec["member_messages_to_non_leader"]), (2, 80, 0))
        self.assertEqual((star_rec["redirected"], star_rec["redirected_by_robot"], star_rec["redirected_by_addressee"]), (1, {"r2": 1, "r3": 0}, {"everyone": 1}))
        inbound, outbound = star_rec["leader_inbound"], star_rec["leader_outbound"]
        self.assertEqual((inbound["messages"], inbound["chars"], inbound["by_sender"]), (2, 80, {"r2": 1, "r3": 1}))
        self.assertAlmostEqual(inbound["read_s"], read_time(50) + read_time(30), places=3)
        self.assertEqual((outbound["messages"], outbound["chars"], outbound["deliveries"], outbound["directed"], outbound["to_everyone"]), (2, 60, 3, 1, 1))
        self.assertEqual(rec["conditions"]["leader_route"], "star")
        self.assertEqual(rec["talk"]["events"], {"member_redirected_to_leader": 1})
        self.assertEqual(rec["talk"]["says"], 4)
        self.assertEqual(rec["messages_by_robot"], {"r1": 2, "r2": 1, "r3": 1})

    def test_no_star_key_without_the_switch(self):
        b, _ = star(route=None, stub=FreeStub(say={"r2": [("r3", "hello")]}))
        b.decide("r2", 12.0, "pick", pick_options("r2"))
        rec = b.record()
        self.assertNotIn("star", rec)
        self.assertNotIn("leader_route", rec["conditions"])
        self.assertEqual((rec["messages"][0]["to"], "redirected_from" in rec["messages"][0]), (["r3"], False))      # members still talk to each other


RELAY_OPTIONS = [{"key": "wait", "text": "stay here and keep relaying for the team"}]


class Relay(unittest.TestCase):
    """The leader stays in the conversation after its own run: its answers carry relay=True and the point "relay" (wait + say entries) is accepted for it."""

    def test_only_the_leader_of_a_star_run_is_marked(self):
        b, _ = star()
        self.assertTrue(b.decide("r1", 12.0, "pick", pick_options("r1"))["relay"])
        self.assertNotIn("relay", b.decide("r2", 12.0, "pick", pick_options("r2")))
        b, _ = star(route=None, leader_bind=True)
        self.assertNotIn("relay", b.decide("r1", 12.0, "pick", pick_options("r1")))
        p, _ = make_free("T1")
        self.assertNotIn("relay", p.decide("r1", 12.0, "pick", pick_options("r1")))

    def test_the_relay_point_is_for_the_star_leader_only(self):
        b, _ = star()
        self.assertEqual(b.decide("r1", 90.0, "relay", RELAY_OPTIONS)["option"], "wait")
        with self.assertRaises(ValueError):
            b.decide("r2", 91.0, "relay", RELAY_OPTIONS)                          # a member
        b, _ = star(route=None, leader_bind=True)
        with self.assertRaisesRegex(ValueError, "Unknown decision point"):
            b.decide("r1", 90.0, "relay", RELAY_OPTIONS)                          # no star route: the point does not exist
        p, _ = make_free("T1")
        with self.assertRaisesRegex(ValueError, "Unknown decision point"):
            p.decide("r1", 90.0, "relay", RELAY_OPTIONS)

    def test_a_relay_decision_after_the_leaders_own_run_shows_the_message_and_may_reply(self):
        def raw(prompt):
            robot = progress_of(prompt)["robot"]
            if robot == "r2" and "REPLY-FOR-R2" not in prompt:
                return json.dumps({"action": [l for l, t in listing_of(prompt) if t.startswith("say to r1")][0], "say": "QUESTION-FROM-R2 which zone?"})
            if robot == "r1" and RELAY_NOTE in prompt:
                return json.dumps({"action": [l for l, t in listing_of(prompt) if t.startswith("say to r2")][0], "say": "REPLY-FOR-R2 sign12"})
            return json.dumps({"action": [l for l, t in listing_of(prompt) if not t.startswith("say to ")][0]})
        b, stub = star(stub=FreeStub(raw=raw))
        b.decide("r1", 12.0, "pick", pick_options("r1"))                              # the leader's last ordinary decision; its run ends later
        asked = b.decide("r2", 100.0, "door", [{"key": "go", "text": "carry the box through the door now"}, {"key": "wait", "text": "wait here"}])
        question = asked["sent"][0]
        t = question["deliver_at"] + read_time(40) + 1.0
        self.assertTrue(b.readable_count("r1", t) > 0)                                 # what /poll answers `new` on
        out = b.decide("r1", t, "relay", RELAY_OPTIONS)
        prompt = stub.prompts_of("r1")[-1]
        self.assertIn("QUESTION-FROM-R2", prompt)
        self.assertIn(RELAY_NOTE, prompt)
        self.assertEqual([x for _, x in listing_of(prompt)], ["stay here and keep relaying for the team", "say to r2: <text>", "say to r3: <text>", "say to everyone: <text>"])
        reply = out["sent"][0]
        self.assertEqual((reply["to"], reply["tgt"], out["relay"], out["option"]), (["r2"], "r2", True, "wait"))
        self.assertEqual(b.record()["star"]["relay_decisions"], 1)
        back = b.decide("r2", reply["deliver_at"] + read_time(25) + 1.0, "door", [{"key": "go", "text": "carry the box through the door now"}, {"key": "wait", "text": "wait here"}])
        self.assertIn("REPLY-FOR-R2", stub.prompts_of("r2")[-1])                       # the reply reached the member

    def test_a_question_that_became_readable_after_the_leaders_reply_began_can_still_be_answered(self):
        # two members ask together; the leader reads them one after the other, answers the first, and the second becomes readable while it speaks
        b, stub = star(stub=FreeStub(say={"r1": [("r2", "answer to r2"), ("r3", "answer to r3")]}))
        first = b._speak("r2", 60.0, {"target": "r1", "to": ["r1"]}, "q" * 200)
        second = b._speak("r3", 60.0, {"target": "r1", "to": ["r1"]}, "q" * 200)
        ready = sorted(b._readable("r1").values())
        t_first = ready[0] + 0.01
        self.assertLess(t_first, ready[1])                                            # only the first is readable yet
        out = b.decide("r1", t_first, "relay", RELAY_OPTIONS)
        self.assertEqual(out["sent"][0]["to"], ["r2"])
        self.assertLess(second["deliver_at"], t_first)                                # the second message had arrived before the leader's reply began
        t_second = ready[1] + 0.01
        self.assertGreater(t_second, t_first)
        again = b.decide("r1", t_second, "relay", RELAY_OPTIONS)
        self.assertEqual(again["sent"][0]["to"], ["r3"])                              # a say entry was offered again: the message became readable after the reply began
        self.assertEqual(b.record()["star"]["relay_decisions"], 2)
        # nothing new: no second say in a row (the old rule)
        self.assertEqual(entries_of(stub.prompts_of("r1")[-1]), ["say to r2: <text>", "say to r3: <text>", "say to everyone: <text>"])
        none = b.decide("r1", t_second + 5.0, "relay", RELAY_OPTIONS)
        self.assertEqual(none["sent"], [])
        self.assertEqual([x for _, x in listing_of(stub.prompts_of("r1")[-1])], ["stay here and keep relaying for the team"])

    def test_no_note_and_no_relay_option_outside_the_relay_point(self):
        b, stub = star()
        b.decide("r1", 12.0, "pick", pick_options("r1"))
        self.assertNotIn(RELAY_NOTE, stub.prompts_of("r1")[0])
        self.assertIn("keep relaying", stub.prompts_of("r1")[0])                       # the leader is told it stays

    def test_the_record_counts_the_relay_decisions(self):
        b, _ = star()
        b.decide("r1", 12.0, "pick", pick_options("r1"))
        for t in (90.0, 95.0):
            b.decide("r1", t, "relay", RELAY_OPTIONS)
        self.assertEqual(b.record()["star"]["relay_decisions"], 2)
        self.assertEqual([d["point"] for d in b._decisions["r1"]], ["pick", "relay", "relay"])


class LeaderDown(unittest.TestCase):
    """A halted leader (call cap, fault, --fail-robot): the members are told, their say entry is `say to everyone`, every such speech is counted."""

    def down_brain(self, how="halts", **kw):
        raw = kw.pop("raw", None)
        b, stub = star(stub=FreeStub(raw=raw) if raw else FreeStub(), **kw)
        if how == "halts":
            b._halts["r1"] = "Robot call cap reached"
        return b, stub

    def test_members_are_told_and_offered_everyone_only(self):
        b, stub = self.down_brain()
        b.decide("r2", 50.0, "pick", pick_options("r2"))
        prompt = stub.prompts_of("r2")[0]
        self.assertIn(STAR_MEMBER_DOWN % "r1", prompt)
        self.assertNotIn(STAR_MEMBER % "r1", prompt)
        self.assertNotIn(FREE_RULE_STAR_MEMBER, prompt)
        self.assertEqual(entries_of(prompt), ["say to everyone: <text>"])

    def test_a_member_speech_goes_to_everyone_but_the_leader_and_is_counted(self):
        raw = json.dumps({"action": "B", "say": "hello team"})
        b, stub = self.down_brain(raw=raw)
        out = b.decide("r2", 50.0, "pick", pick_options("r2"))
        m = out["sent"][0]
        self.assertEqual((m["to"], m["tgt"], m["leader_down"]), (["r3"], "everyone", True))
        self.assertNotIn("redirected_from", m)                                      # nobody else was addressed
        rec = b.record()
        self.assertEqual(rec["talk"]["events"], {"say_with_action": 1, "leader_down_fallback": 1})
        self.assertEqual(rec["star"]["leader_down_fallback"], 1)
        self.assertEqual(rec["star"]["leader_down"], {"reason": "Robot call cap reached", "first_seen_s": 50.0, "leader": "r1"})
        self.assertEqual(rec["star"]["member_messages_to_non_leader"], 0)           # the fallback is not a leak
        self.assertEqual(rec["star"]["leader_inbound"]["messages"], 0)

    def test_an_address_to_one_member_goes_to_everyone_while_the_leader_is_down(self):
        for answer in ({"action": "say to r3: take blue"}, {"action": "B", "say": "r3, take blue"}, {"action": "B", "say": "take blue", "to": "r3"}):
            b, stub = self.down_brain(raw=json.dumps(answer))
            out = b.decide("r2", 50.0, "pick", pick_options("r2"))
            m = out["sent"][0]
            self.assertEqual((m["to"], m["tgt"], m["leader_down"]), (["r3"], "everyone", True), answer)
            self.assertEqual(b.record()["talk"]["events"].get("member_redirected_to_everyone"), 1 if "r3" in m.get("redirected_from", "") else None, answer)
            self.assertNotIn("member_redirected_to_leader", b.record()["talk"]["events"], answer)
            self.assertEqual([r for r, why in b._halts.items() if why and r != "r1"], [], answer)

    def test_the_fault_of_the_leader_counts_too(self):
        b, stub = star(fail_robot="r1", fail_at_s=10.0, stub=FreeStub(raw=json.dumps({"action": "B", "say": "anyone there"})))
        b.decide("r3", 5.0, "pick", pick_options("r3"))                              # before the failure: the leader is the addressee
        self.assertEqual(b._messages[-1]["to"], ["r1"])
        b._states["r3"]["say_streak"] = 0
        out = b.decide("r3", 50.0, "pick", pick_options("r3"))
        self.assertEqual((out["sent"][0]["to"], out["sent"][0]["leader_down"]), (["r2"], True))
        self.assertEqual(b.record()["star"]["leader_down"]["reason"], "robot_failed")
        self.assertEqual(b.record()["star"]["leader_down_fallback"], 1)

    def test_the_call_cap_of_the_leader_counts_before_it_decides_again(self):
        b, stub = star(stub=FreeStub(raw=json.dumps({"action": "B", "say": "hi"})))
        b.max_calls = 1
        b.decide("r1", 12.0, "pick", pick_options("r1"))                              # the leader's only call
        out = b.decide("r2", 50.0, "pick", pick_options("r2"))
        self.assertEqual((out["sent"][0]["to"], out["sent"][0]["leader_down"]), (["r3"], True))

    def test_a_leader_that_is_up_leaves_no_fallback_trace(self):
        b, stub = star(stub=FreeStub(raw=json.dumps({"action": "B", "say": "hi"})))
        b.decide("r2", 50.0, "pick", pick_options("r2"))
        rec = b.record()
        self.assertIsNone(rec["star"]["leader_down"])
        self.assertEqual((rec["star"]["leader_down_fallback"], rec["talk"]["events"]), (0, {"say_with_action": 1}))
        self.assertNotIn("leader_down", b._messages[0])

    def test_the_chance_path_and_the_two_step_line_follow_the_fallback(self):
        def raw(prompt):
            if prompt.endswith("So the answer is option"):
                return "say to everyone: two step words"
            if "A. %s" % SILENT_TEXT in prompt:
                return json.dumps({"action": "A", "say": "chance words"})
            return '{"reasoning":"stub"}'
        b, stub = self.down_brain(raw=raw, merge_calls=False)
        out = b.decide("r2", 50.0, "pick", pick_options("r2"))
        final = [p for p in stub.prompts_of("r2") if p.endswith("So the answer is option")][0]
        self.assertIn("(for example: say to everyone: your words)", final)
        self.assertEqual((out["sent"][0]["to"], out["sent"][0]["leader_down"]), (["r3"], True))
        b.chance("r3", out["sent"][0]["deliver_at"] + read_time(20) + 1.0)
        chance = b._messages[-1]
        self.assertEqual((chance["from"], chance["via"], chance["to"], chance["leader_down"]), ("r3", "chance", ["r2"], True))
        self.assertEqual(b.record()["talk"]["events"]["leader_down_fallback"], 2)

    def test_the_input_bound_counts_the_longer_line(self):
        b, _ = self.down_brain()
        b._states["r2"]["now"] = 50.0
        self.assertEqual(b._free_suffix_extra("r2"), len("say to everyone:") - len("say to r2:"))
        self.assertEqual(b._free_suffix_extra("r1"), 0)


class Switch(unittest.TestCase):
    def test_the_brain_refuses_the_switch_outside_a_free_t2_run(self):
        with self.assertRaises(ValueError):
            make_free("T1", leader_route="star")
        with self.assertRaises(ValueError):
            make_free("T2", leader_route="ring")
        with self.assertRaises(ValueError):
            import tempfile
            TeamBrain("T2", list(R3), "goal", client=FreeStub(), log_dir=Path(tempfile.mkdtemp()), leader_route="star")          # no free talk

    BASE = ["--team", "T2", "--robots", "r1,r2,r3", "--port", "1", "--log-dir", "/tmp/x"]

    def test_parse_args(self):
        self.assertIsNone(brain_server.parse_args(self.BASE).leader_route)
        a = brain_server.parse_args(self.BASE + ["--talk", "free", "--leader-route", "star"])
        self.assertEqual(a.leader_route, "star")
        a = brain_server.parse_args(self.BASE + ["--talk", "free", "--leader-authority", "--leader-election", "--leader-bind", "--hold-s", "75", "--leader-seed", "3",
                                                  "--leader-route", "star"])
        self.assertEqual((a.leader_route, a.leader_bind, a.leader_seed), ("star", True, 3))
        for bad in (["--leader-route", "star"], ["--leader-route", "ring", "--talk", "free"]):
            with self.assertRaises(SystemExit, msg=str(bad)), contextlib.redirect_stderr(io.StringIO()):
                brain_server.parse_args(self.BASE + bad)
        with self.assertRaises(SystemExit), contextlib.redirect_stderr(io.StringIO()):
            brain_server.parse_args(["--team", "T1", "--robots", "r1,r2,r3", "--port", "1", "--log-dir", "/x", "--talk", "free", "--leader-route", "star"])

    def test_the_leader_rows_of_the_manifests_carry_the_switch_and_the_peer_rows_do_not(self):
        import csv
        files = sorted((ROOT.parent / "manifests").glob("phase2-*.csv"))
        if not files:
            self.skipTest("the manifests are not next to this copy of link/")
        rows = []
        for f in files:
            with open(f, newline="") as handle:
                rows += [r for r in csv.DictReader(handle) if "--talk" in r["server_args"]]
        self.assertGreater(len(rows), 0)
        # L-star rows carry the switch; L-open (T2, arm L-open) and P (T1) rows do not
        self.assertEqual([r["run_id"] for r in rows if r["arm"] == "L-star" and "--leader-route star" not in r["server_args"]], [])
        self.assertEqual([r["run_id"] for r in rows if r["arm"] != "L-star" and "--leader-route" in r["server_args"]], [])
        self.assertEqual({r["arm"] for r in rows if r["team"] == "T2"}, {"L-open", "L-star"})
        self.assertEqual({r["arm"] for r in rows if r["team"] == "T1"}, {"P"})


if __name__ == "__main__":
    unittest.main()
