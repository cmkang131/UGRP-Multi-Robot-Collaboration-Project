"""Offline protocol regressions for the CHEN2D-2 revision."""
import ast
import contextlib
import io
import json
import multiprocessing
import os
import re
import subprocess
import sys
import tempfile
import threading
import types
import unittest
from collections import Counter
from concurrent.futures import ProcessPoolExecutor, ThreadPoolExecutor
from dataclasses import replace
from decimal import Decimal
from pathlib import Path
from regression_inputs import REGRESSION
from unittest.mock import patch

import fake_model
from LLM import CallSession, MODEL, load_real_api
from env1_create import (SIZES, action_from_response, saved_env, state_update_func,
                         state_update_func_local_agent, with_action_syntactic_check_func)
from episode import Episode, Spec, run_episode
from limits import CALL_LIMIT, CLIENT_LIMIT, Invocation, StopEpisode
from map_events import (agent_at, boxes, cell_key, coordinates, distance, event_path, map_assignment,
                        reference_plan, step_limit)
from plan_parse import PlanParser
from run_chen2d import FRAMEWORKS
from storage import ROOT, digest, read_json, version_from_hashes, write_json
from test_chen2d import calls, fixture_spec

# Raw response strings from the frozen v1 smoke, retained verbatim (including whitespace).
# glm-smoke-DMAS / 00011.json
DMAS_11 = 'EXECUTE\n{"Agent[1.5, 0.5]":"move(box_red, square[1.5, 1.5])", "Agent[1.5, 1.5]":"move(box_green, dropoff_green)", "Agent[0.5, 0.5]":"move(box_blue, target_blue)"}'
# glm-smoke-DMAS / 00012.json
DMAS_12 = 'EXECUTE\n{"Agent[1.5, 1.5]":"move(box_green, dropoff_green)", "Agent[1.5, 0.5]":"move(box_red, square[1.5, 1.5])"}'
DMAS_STATE = {'0.5_0.5': ['target_green'], '0.5_1.5': ['target_green'], '1.5_0.5': ['box_red', 'target_green', 'target_orange'], '1.5_1.5': ['target_red', 'target_purple', 'box_orange', 'dropoff_green', 'box_green', 'box_purple']}

# glm-smoke-HMAS-2 / 00017.json
HMAS2_17 = '{"Agent[0.5, 0.5]":"move(box_purple, square[1.5, 0.5])","Agent[0.5, 1.5]":"move(box_green, square[0.5, 0.5])","Agent[1.5, 0.5]":"move(box_red, square[1.5, 1.5])"}We need answer plan. Need reason. Current boxes: purple at .5,.5 target purple? where target_purple at 1.5,1.5. green at .5,1.5 target_green at .5,.5. reds at 1.5,.5 targets red at .5,1.5 and 1.5,1.5. orange none? no boxes orange, targets remain irrelevant.\n\nActions possible limited. Need move toward targets. Agent .5,.5 can move purple to neighbor .5,1.5 or 1.5,.5. target purple at 1.5,1.5, so either then next. Agent .5,1.5 can move green to .5,.5 where target_green, so deliver. Agent1.5,.5 move red to 1.5,1.5 target red or .5,.5. Better red to 1.5,1.5 target red. But if purple also to 1.5,.5? conflict? squares can contain many, ok. Agent .5,1.5 moving green to .5,.5. Agent .5,.5 moving purple to .5,1.5 maybe swap. ok. Agent1.5,.5 red to target red. Agent1.5,1.5 no action.\n\nNeed avoid dead loop. Plan:\n.5,.5 move purple square .5,1.5\n.5,1.5 move green square .5,.5 (will be at target next step? Actually moving box to square containing target_green counts? In previous they used move(box_green,target_green) only if same square. Here can move to neighboring square or same-color target. Since target_green in .5,.5, from .5,1.5 can it move(box_green,target_green)? Possible actions only square .5,.5, not target. So no, must move to square then next deliver.\n1.5,.5 move red square1.5,1.5 (target there, next deliver? possible action next move(box_red,target_red) if same square)\nCould also move red to .5,.5 no target. So yes.\n\nFinal JSON{"Agent[0.5, 0.5]":"move(box_purple, square[0.5, 1.5])","Agent[0.5, 1.5]":"move(box_green, square[0.5, 0.5])","Agent[1.5, 0.5]":"move(box_red, square[1.5, 1.5])"}'
HMAS2_STATE = {'0.5_0.5': ['target_green', 'box_purple'], '0.5_1.5': ['target_red', 'box_green', 'dropoff_orange'], '1.5_0.5': ['box_red', 'box_red', 'target_orange', 'target_orange'], '1.5_1.5': ['target_red', 'target_purple', 'target_orange']}


HISTORY = "_w_all_dialogue_history"
REPAIR = ("Your assigned plan is not in the correct json format as before. If your answer is empty dict, "
          "please check whether you miss to move box into the same colored target like move(box_blue, target_blue)"
          "Please replan for all the agents again with the same ouput format:")


def enrolled_spec(framework="CMAS", condition="e1", seed=0, dropoff="event", **options):
    path, sha = saved_env(2, 2, seed)
    return Spec(2, 2, framework, condition, seed, path, sha, digest(event_path(path).read_bytes()), dropoff=dropoff, **options)


def fixed_dialogue(messages, _script):
    """Exercise syntax, dialogue, review and revision with identical replies for every recipient policy."""
    prompt = messages[1]["content"]
    local = re.search(r"of yourself are: \{Agent\[([\d.]+), ([\d.]+)\]", prompt)
    if "Please evaluate the given plan." in prompt:
        return "Please reconsider this plan."
    if local and len(messages) == 2 and local[2] == "0.5":
        return "PROCEED"
    bad = '{"Agent[0.5, 0.5]":"move(box_missing, target_missing)"}'
    if len(messages) == 2:
        return ("EXECUTE\n" if local else "") + bad
    if "This is the feedback from local agents." in messages[-1]["content"]:
        return bad
    return fake_model.plan_from_text(prompt, obey=False)


def activity_snapshot(r):
    return [(it["step"], it["issued_plan"]) for it in r["iterations"] if it["executed"]]


class RevisionTests(unittest.TestCase):
    def setUp(self):
        temp = tempfile.TemporaryDirectory(dir=ROOT, prefix=".chen-v2-test-")
        self.addCleanup(temp.cleanup)
        self.work = Path(temp.name)

    def play(self, spec, tag="run", replies=None, ceiling=300):
        out = self.work / tag
        out.mkdir(exist_ok=True)
        budget = Invocation(out, out / "budget.json")
        budget.create(None, 10, "fake")
        scripted = patch.object(fake_model, "reply", side_effect=replies) if replies is not None else contextlib.nullcontext()
        with scripted:
            run_episode(spec, out, budget.path, "fake", "correct", ceiling)
        folder = out / "episodes" / spec.name
        return read_json(folder / "episode.json"), calls(folder)

    def cli(self, out, *args):
        return subprocess.run([sys.executable, "-B", "run_chen2d.py", "--model", "fake", "--out",
                               str(out), "--frameworks", "CMAS", "--envs", "0", "--dropoff", "event", *args],
                              cwd=ROOT, capture_output=True, text=True)

    def summary(self, *outs):
        return subprocess.run([sys.executable, "-B", "summarize.py", *map(str, outs)],
                              cwd=ROOT, capture_output=True, text=True)

    def test_enrollment_reference_joint_actions_and_bounds(self):
        fallback = distant = False
        for rows, cols in SIZES:
            for seed in range(3):
                path, sha = saved_env(rows, cols, seed, self.work / "envs")
                sidecar = event_path(path)
                state, a = read_json(path), read_json(sidecar)
                self.assertEqual((read_json(event_path(saved_env(rows, cols, seed)[0])), a["env_sha256"]), (a, sha))
                self.assertNotEqual(a["L"], a["M"])
                self.assertIn(a["A"], boxes(state))
                self.assertNotIn("target_" + a["A"], state[cell_key(a["D"])])
                targets = [coordinates(k) for k, v in state.items() if "target_" + a["A2"] in v]
                minimum = lambda d: min(distance(d, t) for t in targets)
                best = max(minimum(coordinates(k)) for k in state)
                self.assertGreaterEqual(minimum(a["D2"]), min(2, best))
                fallback |= best < 2
                distant |= best >= 2
                steps = 0
                with patch("env1_create.GPT_response", side_effect=AssertionError("reference needed a repair")):
                    while boxes(state):
                        plan = reference_plan(state)
                        doable = state_update_func(rows, cols, state).splitlines()
                        for agent, action in plan.items():
                            listing = next(line for line in doable if line.startswith(agent + ":"))
                            self.assertIn(action, ast.literal_eval(listing.split("I can do ", 1)[1]))
                        checked, repairs = with_action_syntactic_check_func(
                            state, json.dumps(plan), [], [], "fake", HISTORY, "CMAS", parser=PlanParser("strict"))
                        self.assertEqual((json.loads(checked), repairs), (plan, []))
                        feedback, state = action_from_response(state, plan)
                        self.assertFalse(feedback)
                        steps += 1
                self.assertEqual((steps, a["event_step"]), (a["S"], min(step_limit(rows, cols)//2, max(2, (steps+1)//2))))
        self.assertTrue(distant and fallback)
        for n, expected in ((1, 0), (2, 1), (40, 15)):
            state = {"0.5_0.5": ["box_red", "target_red"] * n, "0.5_1.5": [], "1.5_0.5": [], "1.5_1.5": []}
            assignment = map_assignment(state, 0, "fixture", 2, 2, action_from_response)
            self.assertEqual((assignment["S"], assignment["event_step"]), (n, expected))
        sidecar = event_path(path)
        original = sidecar.read_bytes()
        sidecar.write_text("{}")
        with self.assertRaisesRegex(ValueError, "modified enrolled event"):
            saved_env(rows, cols, seed, self.work / "envs")
        self.assertNotEqual(sidecar.read_bytes(), original)
        sidecar.unlink()
        with self.assertRaisesRegex(ValueError, "Missing or modified enrolled event"):
            saved_env(rows, cols, seed, self.work / "envs")

    def test_e1_distribution_independent_of_the_trajectory_and_delivery_actions(self):
        state = {"0.5_0.5": ["box_red", "target_red"], "0.5_1.5": [],
                 "1.5_0.5": [], "1.5_1.5": ["box_red", "target_red"]}
        spec = fixture_spec(self.work / "map.json", state, "e1", event_step_override=1)
        r, _ = self.play(spec, "nothing")  # both red boxes delivered on step one
        waiting, _ = self.play(spec, "waiting", replies=["{}", '{"Agent[0.5, 0.5]":"move(box_red, target_red)"}'],
                               ceiling=2)
        self.assertEqual((r["A"], r["D"], r["S"], r["L"], r["M"]),
                         (waiting["A"], waiting["D"], waiting["S"], waiting["L"], waiting["M"]))
        self.assertEqual((r["box_A_left_at_event"], waiting["box_A_left_at_event"]), (0, 2))
        self.assertTrue(r["event_fired"] and r["event_nothing_to_change"])
        spec = replace(spec, event_step_override=2)
        def idle_then_wrong(messages, _):
            if not any("Change of orders" in m["content"] for m in messages):
                return "{}"
            return fake_model.plan_from_text(messages[1]["content"], obey=False)
        wrong, _ = self.play(spec, "wrong", replies=idle_then_wrong)
        self.assertEqual((wrong["first_plan_after_event_wrong"], wrong["wrong_deliveries"],
                          wrong["strict_success"], wrong["success"]), (True, 2, False, True))
        self.assertIsNone(wrong["steps_to_last_dropoff"])
        def idle_then_obey(messages, script):
            if not any("Change of orders" in m["content"] for m in messages):
                return "{}"
            return fake_model.plan_from_text(messages[1]["content"], obey=True)
        correct, records = self.play(spec, "correct", replies=idle_then_obey)
        self.assertTrue(correct["strict_success"] and correct["first_plan_respected_change"])
        self.assertGreater(correct["steps_to_last_dropoff"], 0)
        expected = (f"Change of orders (announced after step 2): the order for boxes of colour red has changed. "
                    f"They are no longer wanted in target_red. They are now wanted in the drop-off at square{r['D']}. "
                    "A box_red that is put into target_red from now on counts as a wrong delivery.")
        self.assertEqual(correct["event"]["announcement"], expected)
        for c in records:
            text = c["messages"][1]["content"]
            self.assertEqual(text.count(expected), int(c["step"] > 2))
            for line in (l for l in text.splitlines() if "I can do " in l):
                items = ast.literal_eval(fake_model.OBSERVATION.search(line)[3])
                self.assertEqual("move(box_red, dropoff_red)" in line, "box_red" in items and "dropoff_red" in items)

    def test_e2_first_delivery_only_visible_return_and_latency(self):
        state = {"0.5_0.5": ["box_blue", "target_blue"], "0.5_1.5": ["box_blue", "target_blue"],
                 "1.5_0.5": [], "1.5_1.5": []}
        spec = fixture_spec(self.work / "map.json", state, "e2", event_step_override=19)
        # Reverse row order to distinguish execution order from grid order. Both deliveries succeed.
        first = '{"Agent[0.5, 1.5]":"move(box_blue, target_blue)","Agent[0.5, 0.5]":"move(box_blue, target_blue)"}'
        scripted = iter(["{}", "{}", first])
        def delayed(messages, _):
            return next(scripted, None) or fake_model.plan_from_text(messages[1]["content"], obey=True)
        r, records = self.play(spec, replies=delayed)
        e = r["event"]
        self.assertEqual((r["trigger_step"], e["X"], r["first_plan_returned_towards_D2"]), (3, [0.5, 1.5], True))
        self.assertEqual(e["announcement"], "Change of orders (announced after step 3): the box of colour blue "
                         "that was just delivered was not accepted. It is back in square[0.5, 1.5] as "
                         f"box_blue_returned and is now wanted in the drop-off at square{r['D2']}.")
        self.assertEqual(e["state_before"]["0.5_1.5"], [])
        self.assertEqual(e["state_after"]["0.5_1.5"], ["box_blue_returned"])
        self.assertEqual(e["state_after"]["0.5_0.5"], [])
        self.assertEqual(read_json(self.work / "run/episodes" / spec.name / "pg_state/pg_state4.json"), e["state_after"])
        self.assertEqual(r["correct_deliveries"], 2)
        self.assertEqual(r["steps_to_returned_dropoff"], distance(e["X"], e["D"]) + 1)
        self.assertTrue(r["strict_success"] and r["success"])
        self.assertEqual(r["final_state"][cell_key(e["D"])], ["dropoff_blue"])
        self.assertTrue(all(("box_blue_returned" in c["messages"][1]["content"]) == (c["step"] > 3) for c in records))
        stalled, _ = self.play(spec, "stalled", replies=[first] + ["{}"] * 30)
        self.assertEqual((stalled["correct_deliveries"], stalled["boxes_left"], stalled["strict_success"],
                          stalled["steps_to_returned_dropoff"], stalled["first_plan_returned_towards_D2"]),
                         (1, 1, False, None, False))

    def test_e2_only_the_returned_box_can_use_the_site(self):
        state = {"0.5_0.5": ["target_blue", "box_blue", "dropoff_blue", "box_blue_returned"],
                 "0.5_1.5": ["box_blue_returned"], "1.5_0.5": [], "1.5_1.5": []}
        good = "move(box_blue_returned, dropoff_blue)"
        bad = "move(box_blue, dropoff_blue)"
        central = state_update_func(2, 2, state, returned_only=True).splitlines()
        for i, line in enumerate(central):
            self.assertEqual(good in line, i == 0)
            self.assertNotIn(bad, line)
        self.assertIn("move(box_blue, target_blue)", central[0])
        for row in range(2):
            for col in range(2):
                own, others = state_update_func_local_agent(2, 2, row, col, state, returned_only=True)
                self.assertEqual(good in own, row == col == 0)
                self.assertEqual(good in others, (row, col) != (0, 0))
                self.assertNotIn(bad, own + others)
        action = lambda text: {"Agent[0.5, 0.5]": text}
        with patch("env1_create.GPT_response", return_value=(json.dumps(action(good)), 18)):
            fixed, tokens = with_action_syntactic_check_func(state, json.dumps(action(bad)), ["prompt"], [], "fake",
                                                            HISTORY, "CMAS", returned_only=True)
        self.assertEqual((json.loads(fixed), tokens), (action(good), [18]))
        feedback, after = action_from_response(state, action(good), returned_only=True)
        self.assertFalse(feedback)
        self.assertEqual(after["0.5_0.5"], ["target_blue", "box_blue", "dropoff_blue"])
        feedback, unchanged = action_from_response(after, action(bad), returned_only=True)
        self.assertTrue(feedback)
        self.assertEqual(unchanged, after)
        self.assertNotIn(bad, state_update_func(2, 2, after, returned_only=True))
        self.assertNotIn("box_blue", action_from_response(after, action("move(box_blue, target_blue)"),
                                                        returned_only=True)[1]["0.5_0.5"])

    def test_private_notices_at_every_call_and_broadcast_byte_parity(self):
        for kind in ("e1", "e2"):
            for fw in FRAMEWORKS:
                with self.subTest(kind=kind, framework=fw):
                    base = enrolled_spec(fw, kind, event_step_override=1)
                    def broadcast(ep, robot, role):
                        ep.session.speaker, ep.session.role, ep.session.told = robot, role, bool(ep.event)
                        if not ep.event:
                            return ""
                        e = ep.event
                        a, k, d = e["A"], e["step"], e["D"]
                        if kind == "e1":
                            words = (f"the order for boxes of colour {a} has changed. They are no longer wanted in "
                                     f"target_{a}. They are now wanted in the drop-off at square{d}. A box_{a} that "
                                     f"is put into target_{a} from now on counts as a wrong delivery.")
                        else:
                            words = (f"the box of colour {a} that was just delivered was not accepted. It is back in "
                                     f"square{e['X']} as box_{a}_returned and is now wanted in the drop-off at square{d}.")
                        return f"Change of orders (announced after step {k}): {words}\n"
                    with patch.object(Episode, "address", broadcast):
                        reference, full = self.play(base, "broadcast", fixed_dialogue, 40)
                    self.assertTrue(reference["event_fired"])
                    notice = reference["event"]["announcement"]
                    board = reference["map_assignment"]
                    seen_roles = set()
                    for tell in ("all", "leader", "member"):
                        r, log = self.play(replace(base, tell=tell), tell, fixed_dialogue, 40)
                        self.assertEqual(r["map_assignment"], board)
                        self.assertEqual(activity_snapshot(reference), activity_snapshot(r))
                        if tell == "all":
                            self.assertEqual([c["messages"] for c in log], [c["messages"] for c in full])
                        expected_turns = Counter()
                        for c, ref in zip(log, full, strict=True):
                            first_prompt = c["messages"][1]["content"]
                            local = re.search(r"of yourself are: \{(Agent\[[^\]]+\])", first_prompt)
                            leader = board["L2"] if kind == "e2" else board["L"]
                            member = agent_at(r["event"]["X"]) if kind == "e2" else agent_at(board["D"])
                            self.assertEqual((r["L"], r["M"]), (leader, member))
                            actor = local[1] if local else leader
                            self.assertEqual(c["speaker"], actor)
                            expected_role = ("review" if fw == "HMAS-2" else "dialogue") if local else "central"
                            self.assertEqual(c["role"], expected_role)
                            post = c["step"] > r["event_step"]
                            told = post and (tell == "all" or (tell == "leader" and actor == leader)
                                             or (tell == "member" and bool(local) and actor == member))
                            self.assertEqual(c["told"], told)
                            self.assertEqual(sum(m["content"].count(notice) for m in c["messages"]), int(told))
                            if told:
                                heading = "The current state and possible actions of yourself" if local else "Hence, the current state"
                                self.assertIn(notice + "\n" + heading, first_prompt)
                                expected_turns[actor] += 1
                            if post:
                                seen_roles.add((expected_role, len(c["messages"]) > 2))
                            # Robot telemetry and reviewer selection are public and identical on this fixed transcript.
                            self.assertEqual(fake_model.OBSERVATION.findall(first_prompt),
                                             fake_model.OBSERVATION.findall(ref["messages"][1]["content"]))
                        self.assertEqual(Counter(r["told_turns_after_event"]), expected_turns)
                        if tell == "member" and fw == "CMAS":
                            self.assertEqual(r["told_turns_after_event"], {member: 0})
                            self.assertFalse(r["first_told_agent_mentioned_change"])
                    if fw != "DMAS":
                        self.assertIn(("central", True), seen_roles)
                    if fw in ("HMAS-1", "DMAS"):
                        self.assertIn(("dialogue", True), seen_roles)
                    if fw == "HMAS-2":
                        self.assertIn(("review", False), seen_roles)

    def test_member_review_reaches_only_current_revision_and_matches_scoring(self):
        state = {k: ["box_red"] * 2 for k in ("0.5_0.5", "0.5_1.5", "1.5_0.5", "1.5_1.5")}
        state["0.5_0.5"].extend(["target_red"] * 8)
        spec = replace(fixture_spec(self.work / "map.json", state, "e1", event_step_override=1, tell="member"),
                       framework="HMAS-2")
        a = read_json(event_path(spec.env_path))
        m = a["M"]
        here = tuple(map(float, re.findall(r"\d+\.5", m)))
        dest = a["D"]
        place = "dropoff_red"
        if distance(here, dest):
            hop = min(p for p in map(coordinates, state) if distance(here, p) == 1 and distance(p, dest) < distance(here, dest))
            place = f"square{list(hop)}"
        single = json.dumps({m: f"move(box_red, {place})"})
        initial = True
        def reviews(messages, _):
            nonlocal initial
            if initial:
                initial = False
                return "{}"
            if "Please evaluate the given plan." in messages[1]["content"]:
                return "Use the drop-off per order receipt 817."
            return single
        r, log = self.play(spec, replies=reviews, ceiling=8)
        self.assertEqual([c["speaker"] for c in log if c["role"] == "review"], [m, m])
        self.assertEqual(r["told_turns_after_event"], {m: 2})
        self.assertTrue(r["first_told_agent_mentioned_change"] and r["first_plan_respected_change"])
        self.assertEqual((r["later_mention_iterations"], r["later_mention_iterations_respected"]), (1, 1))
        for c in log:
            prompt = c["messages"]
            if c["role"] == "central":
                self.assertNotIn(r["event"]["announcement"], str(prompt))
                self.assertEqual("receipt 817" in str(prompt), len(prompt) > 2)
        self.assertEqual([it["mentioning_agents"] for it in r["iterations"][1:]], [[m], [m], []])

    def test_exact_v1_replies_in_checker_and_extraction(self):
        for mode in ("strict", "lenient"):
            budget = Invocation(self.work, self.work / f"budget-{mode}.json")
            budget.create(None, 1, "fake")
            folder = self.work / mode
            folder.mkdir()
            messages = [{"role": "system", "content": "You are a helpful assistant."}, {"role": "user", "content": "plan"}]
            with CallSession(folder, budget, "fake", "correct", 20) as session, patch.object(
                    fake_model, "reply", side_effect=[DMAS_11, DMAS_12, HMAS2_17]):
                parser = PlanParser(mode, session.mark_rescue)
                first = parser.extract(session.call(messages)[0])
                def check_dmas():
                    return with_action_syntactic_check_func(DMAS_STATE, first, ["plan"], [], "fake", HISTORY,
                                                            "DMAS", parser=parser)
                if mode == "strict":
                    with self.assertRaisesRegex(re.error, "wrong json format"):
                        check_dmas()
                else:
                    selected, repairs = check_dmas()
                    self.assertEqual(repairs, [18])
                    self.assertEqual(json.loads(selected), {"Agent[1.5, 1.5]":"move(box_green, dropoff_green)",
                                                            "Agent[1.5, 0.5]":"move(box_red, square[1.5, 1.5])"})
                value = parser.extract(session.call(messages)[0])
                if mode == "strict":
                    with self.assertRaisesRegex(re.error, "wrong json format"):
                        with_action_syntactic_check_func(HMAS2_STATE, value, ["plan"], [], "fake", HISTORY, "HMAS-2", parser=parser)
                else:
                    plan, repairs = with_action_syntactic_check_func(HMAS2_STATE, value, ["plan"], [], "fake", HISTORY,
                                                                    "HMAS-2", parser=parser)
                    self.assertEqual(repairs, [])
                    self.assertEqual(json.loads(plan), {"Agent[0.5, 0.5]":"move(box_purple, square[1.5, 0.5])",
                        "Agent[0.5, 1.5]":"move(box_green, square[0.5, 0.5])","Agent[1.5, 0.5]":"move(box_red, square[1.5, 1.5])"})
                self.assertEqual([r["lenient_rescue"] for r in calls(folder)], [False, mode == "lenient", mode == "lenient"])

    def test_last_execute_multiple_objects_nested_braces_and_no_json_feedback(self):
        p = PlanParser()
        self.assertEqual(p.extract('notes with {bad} then {"k": "}"}'), '{"k": "}"}')
        self.assertEqual(p.extract('{"old": 0} EXECUTE {"middle": 0} EXECUTE \n{"first":1} {"second":2}'), '{"first": 1}')
        self.assertEqual(p.extract('EXECUTE [{bad}, {"ok":1}] even more {bad}'), '{"ok": 1}')
        self.assertIsNone(p.extract('EXECUTE {bad}'))
        self.assertIsNone(p.extract('{"old": 0} EXECUTE no plan'))
        state = {"0.5_0.5": ["box_blue", "target_blue"], "0.5_1.5": [], "1.5_0.5": [], "1.5_1.5": []}
        spec = fixture_spec(self.work / "map.json", state, "static")
        invalid = '{"Agent[0.5, 0.5]":"move(box_missing, target_missing)"}'
        final = 'EXECUTE\n{"Agent[0.5, 0.5]":"move(box_blue, target_blue)"} trailing'
        r, log = self.play(spec, replies=[invalid, "still thinking", final])
        self.assertEqual((r["lenient_rescues"], r["api_calls"], r["strict_success"]), (2, 3, True))
        self.assertEqual(log[2]["messages"][-1]["content"], REPAIR)
        self.assertEqual([c["lenient_rescue"] for c in log], [False, True, True])
        failed, calls6 = self.play(spec, "six", replies=[invalid] + ["no JSON"]*6)
        self.assertEqual((failed["success_failure"], failed["api_calls"]), ("Syntactic Error", 7))
        self.assertTrue(all(c["messages"][-1]["content"] == REPAIR for c in calls6[2:]))
        first_bad, _ = self.play(spec, "no-first", replies=["{bad}"])
        self.assertEqual((first_bad["success_failure"], first_bad["steps"]), ("Hallucination of wrong plan", 0))
        # A braced central revision is passed whole by the strict checker.
        hmas = replace(spec, framework="HMAS-2")
        good = final.split("\n")[1].removesuffix(" trailing")
        for mode in ("lenient", "strict"):
            rm, lc = self.play(replace(hmas, parse_mode=mode), mode, replies=[good, "Please revise.", good + " trailing"])
            self.assertEqual(rm["success_failure"], "success" if mode == "lenient" else "Hallucination of wrong plan")
            self.assertEqual(lc[-1]["lenient_rescue"], mode == "lenient")

    def test_unfired_and_no_change_stay_in_denominators(self):
        from summarize import compare
        rows = []
        for kind in ("e1", "e2"):
            spec = enrolled_spec(condition=kind)
            if kind == "e1":
                spec = replace(spec, event_step_override=read_json(event_path(spec.env_path))["S"])
            finished, _ = self.play(spec, "complete")
            early, _ = self.play(spec, "early", replies=["no plan"])
            self.assertTrue(early["event_not_fired"] and early["finished"])
            self.assertFalse(early["event_fired"])
            self.assertIsNone(early["trigger_step"])
            self.assertIsNone(early["first_plan_after_event_towards_dropoff"])
            self.assertTrue(finished["event_fired"])
            self.assertEqual(finished["event_nothing_to_change"], kind == "e1")
            rows.extend((finished, early))
        buf = io.StringIO()
        with contextlib.redirect_stdout(buf):
            compare(rows, Counter())
        head, *lines = buf.getvalue().splitlines()
        groups = [dict(zip(head.split(" | "), line.split(" | "), strict=True)) for line in lines]
        for g in groups:
            self.assertEqual([g[k] for k in ("recorded", "event fired", "not fired", "success", "strict success")],
                             ["2", "1", "1", "50.0% (1/2)", "50.0% (1/2)"])
            self.assertEqual(g["nothing to change"], "1" if g["condition"] == "e1" else "0")
            self.assertIn("(0/2)", g["first-plan wrong"])
            self.assertIn("(0/2)" if g["condition"] == "e1" else "(1/2)", g["first-plan towards"])
            self.assertIn("NA]", g["first-plan towards"])
            self.assertIn("/2)", g["first told mention"])
            if g["condition"] == "e2":
                self.assertIn("(1/2)", g["mean steps to returned drop-off"])

    def test_cli_variants_and_version_refusal(self):
        out = self.work / "all-tells"
        proc = self.cli(out, "--conditions", "static,e1,e2", "--tell", "all,leader,member", "--jobs", "3")
        self.assertEqual(proc.returncode, 0, proc.stderr)
        rows = [read_json(p) for p in out.glob("episodes/*/episode.json")]
        self.assertEqual(Counter(r["condition"] for r in rows), {"static": 1, "e1": 3, "e2": 3})
        self.assertTrue(all(r["parse"] == "lenient" for r in rows))
        config = read_json(out / "run.json")
        self.assertEqual(config["code_version"], version_from_hashes(config["source_sha256"]))
        self.assertEqual({r["code_version"] for r in rows}, {config["code_version"]})
        good = self.summary(out)
        self.assertEqual(good.returncode, 0, good.stderr)
        self.assertIn("static | - | 1", good.stdout)
        self.assertIn("e1 | member | 1", good.stdout)
        self.assertIn("episodes with rescue", good.stdout)
        self.assertNotEqual(self.cli(out, "--event", "e1", "--parse", "strict").returncode, 0)
        csv_before = (out / "episodes.csv").read_bytes()
        rowfile = next(out.glob("episodes/*/episode.json"))
        row = read_json(rowfile)
        row.pop("code_version")
        write_json(rowfile, row)
        refused = self.summary(out)
        self.assertNotEqual(refused.returncode, 0)
        self.assertIn("code version", refused.stderr)
        self.assertEqual(csv_before, (out / "episodes.csv").read_bytes())
        old = REGRESSION / "offline-batch1"
        self.assertNotEqual(self.summary(old, out).returncode, 0)
        other = self.work / "other"
        other.mkdir()
        config["source_sha256"]["episode.py"] = "f" * 64
        config["code_version"] = version_from_hashes(config["source_sha256"])
        write_json(other / "run.json", config)
        self.assertIn("Refusing to mix code versions", self.summary(out, other).stderr)
        alias = self.work / "alias"
        self.assertEqual(self.cli(alias, "--event", "e2", "--event-step", "22").returncode, 0)
        r = read_json(next(alias.glob("episodes/*/episode.json")))
        self.assertEqual((r["condition"], r["trigger_step"]),
                         ("e2", r["map_assignment"]["reference_first_delivery_steps"][r["A2"]]))

    def test_tight_shared_cost_waits_for_settlement(self):
        budget = Invocation(self.work, self.work / "budget.json")
        budget.create(2, Decimal("0.010"), MODEL)
        budget.reserve("one", Decimal("0.008"))
        waiting, release = threading.Event(), threading.Event()
        def wait_for_first(_delay):
            waiting.set()
            if not release.wait(timeout=4):
                raise TimeoutError("First reservation did not settle")
        with patch("limits.sleep", side_effect=wait_for_first), ThreadPoolExecutor(1) as pool:
            second = pool.submit(budget.reserve, "two", Decimal("0.008"))
            try:
                self.assertTrue(waiting.wait(timeout=4))
                self.assertEqual(read_json(budget.path)["reservations"], {"one": "0.008"})
                budget.settle("one", 1, Decimal("0.001"), Decimal("0.001"))
            finally:
                release.set()
            second.result(timeout=4)
        budget.settle("two", 1, Decimal("0.003"), Decimal("0.003"))
        info = read_json(budget.path)
        self.assertEqual((info["reservations"], Decimal(info["guard_cost_usd"]), info["calls"]), ({}, Decimal("0.004"), 2))

    def test_client_episode_dollar_cap_does_not_stop_other_episodes(self):
        api = load_real_api()
        budget = Invocation(self.work, self.work / "budget.json")
        budget.create(10, 3, MODEL)
        folder = self.work / "used"
        folder.mkdir()
        route = ("offline.invalid", 443, "/script", MODEL, "fixture-credential")
        with patch.object(api, "_load_route", return_value=route), patch.object(api, "check_spend_guard", return_value={}), patch.object(
                api.http.client, "HTTPSConnection", side_effect=AssertionError("exhausted ledger reached transport")):
            with CallSession(folder, budget, MODEL, "correct", 10) as session:
                session.client._reserve("used-by-script", 1.5)
                session.client._settle({"attempt_id": "used-by-script", "cost_usd": 1.5, "status": "ok"})
                with self.assertRaises(StopEpisode) as refused:
                    session.call([{"role": "user", "content": "plan"}])
                self.assertEqual(refused.exception.label, CLIENT_LIMIT)
                self.assertFalse(refused.exception.interrupted)
        info = read_json(budget.path)
        self.assertEqual((info["calls"], info["reservations"], info["stop_label"]), (0, {}, None))
        budget.reserve("other-episode", Decimal("0.01"))
        budget.settle("other-episode", 1, Decimal("0.001"), Decimal("0.001"))

    def test_resume_an_interrupted_lenient_repair_keeps_original_usage(self):
        state = {"0.5_0.5": ["box_blue", "target_blue"], "0.5_1.5": [], "1.5_0.5": [], "1.5_1.5": []}
        spec = fixture_spec(self.work / "board.json", state, "static")
        first = Invocation(self.work, self.work / "first.json")
        first.create(2, 1, "fake")
        invalid = '{"Agent[0.5, 0.5]":"move(box_missing, target_missing)"}'
        with patch.object(fake_model, "reply", side_effect=[invalid, "no JSON"]):
            self.assertEqual(run_episode(spec, self.work, first.path, "fake", "correct", 15), CALL_LIMIT)
        directory = self.work / "episodes" / spec.name
        prefix = {p: p.read_bytes() for p in (directory / "calls").glob("*.json")}
        second = Invocation(self.work, self.work / "second.json")
        second.create(1, 1, "fake")
        with patch.object(fake_model, "reply", side_effect=['EXECUTE\n{"Agent[0.5, 0.5]":"move(box_blue, target_blue)"}']):
            self.assertEqual(run_episode(spec, self.work, second.path, "fake", "correct", 15), "success")
        self.assertTrue(all(p.read_bytes() == data for p, data in prefix.items()))
        row = read_json(directory / "episode.json")
        self.assertEqual((row["lenient_rescues"], row["api_calls"]), (2, 3))
        self.assertEqual([read_json(b.path)["calls"] for b in (first, second)], [2, 1])
        self.assertTrue(all(read_json(b.path)["reservations"] == {} for b in (first, second)))

    def test_two_episode_processes_inside_scripted_transport_at_once(self):
        api = load_real_api()
        ctx = multiprocessing.get_context("fork")
        gate = ctx.Barrier(2)
        budget = Invocation(self.work, self.work / "budget.json")
        budget.create(2, Decimal("0.1"), MODEL)
        specs = [enrolled_spec(condition="static", seed=i) for i in range(2)]
        class OverlappingConnection:
            def __init__(self, *args, **kwargs):
                pass

            def request(inner, method, path, body, headers):
                gate.wait(timeout=8)
                reserved = read_json(budget.path)["reservations"]
                events = [json.loads(p.read_text().splitlines()[-1])["event"]
                          for p in self.work.glob("episodes/*/campaign-calls.jsonl")]
                write_json(self.work / f"transport-{os.getpid()}.json",
                           {"outstanding": sorted(reserved), "client_events": sorted(events)})
                gate.wait(timeout=8)

            def getresponse(self):
                payload = {"choices": [{"message": {"content": "{}"}, "finish_reason": "stop"}],
                           "usage": {"prompt_tokens": 10, "completion_tokens": 2, "cost": 0.000001}}
                return types.SimpleNamespace(status=200, read=lambda n: json.dumps(payload).encode())

            def close(self):
                pass

        route = ("offline.invalid", 443, "/script", MODEL, "offline-fixture-credential")
        with patch.object(api, "check_spend_guard", return_value={}), patch.object(api, "_load_route", return_value=route), patch.object(
                api.http.client, "HTTPSConnection", OverlappingConnection), ProcessPoolExecutor(2, mp_context=ctx) as pool:
            futures = [pool.submit(run_episode, s, self.work, budget.path, MODEL, "correct", 10) for s in specs]
            self.assertEqual([f.result(timeout=20) for f in futures], [CALL_LIMIT, CALL_LIMIT])
        observed = [read_json(p) for p in self.work.glob("transport-*.json")]
        self.assertEqual(len(observed), 2)
        self.assertTrue(all(len(x["outstanding"]) == 2 and x["client_events"] == ["reserve", "reserve"]
                            for x in observed))
        info = read_json(budget.path)
        self.assertEqual((info["calls"], Decimal(info["reported_cost_usd"]), info["reservations"]), (2, Decimal("0.000002"), {}))
        self.assertFalse((self.work / "campaign-calls.jsonl").exists())
        for s in specs:
            folder = self.work / "episodes" / s.name
            ledger = [json.loads(line) for line in (folder / "campaign-calls.jsonl").read_text().splitlines()]
            self.assertEqual([e["event"] for e in ledger], ["reserve", "settle"])
            self.assertEqual(ledger[0]["budget_usd"], 1.5)
            self.assertEqual(read_json(folder / "episode.json")["api_calls"], 1)


if __name__ == "__main__":
    unittest.main()
