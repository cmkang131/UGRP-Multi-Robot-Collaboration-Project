"""Offline OWN reply, repair, publication and saved-episode regression tests."""
import csv
import io
import json
import sys
import unittest
from collections import Counter
from concurrent.futures import ThreadPoolExecutor
from contextlib import redirect_stdout
from unittest.mock import patch

import run_chen2d
from horizon import OWN_MAX_REPAIRS
from episode import run_episode
from failure_causes import classify
from limits import CALL_LIMIT, Invocation
from output_demand import selected_sequence
from plan_parse import OWN_FORMS, PlanParser
from planning_metrics import ENV_STEP_LIMIT, print_planning_table, repair_feedback
from prompt_env1 import OWN_DIALOGUE
from storage import read_json
from test_chen2d import calls
from test_chen2d_v4 import cli
from test_chen2d_v5 import local_references
from test_chen2d_v9 import pipe_rows
from test_chen2d_v11 import A, B, C, D, BAD, GREEN, GREEN_TO_D, RED, TO_B, TWO, HorizonFixtures


PURPLE_AGENT = "Agent[0.5, 3.5]"
PURPLE_MOVE = "move(box_purple, square[0.5, 2.5])"
SECTION = "Planning outcomes and physical calls"


def purple_round(out):
    """Drive the ordinary runner on the enrolled 4×4 map with fixed fake replies."""
    replies = [json.dumps([[PURPLE_MOVE]]), json.dumps({C: [GREEN]}), '```json\n[null]\n```',
               'null', '[null]', '[]', '[null, null]', 'unreadable'] + ['unreadable'] * OWN_MAX_REPAIRS
    argv = ["run_chen2d.py", "--model", "fake", "--sizes", "4x4", "--frameworks", "OWN", "--conditions",
            "static", "--dropoff", "event", "--envs", "0", "--max-env-steps", "1", "--out", str(out)]
    # Stay in-process so the worker sees the scripted replies on every Python start method.
    with (patch.object(sys, "argv", argv), patch.object(run_chen2d, "ProcessPoolExecutor", ThreadPoolExecutor),
          patch("fake_model.reply", side_effect=replies)):
        run_chen2d.main()


class OwnReplyTests(HorizonFixtures):
    def one_round(self, reply, horizon, tag, *, mode="lenient", repair=False):
        idle = [None] * horizon
        replies = [reply, json.dumps([GREEN_TO_D, *idle[1:]])]
        if horizon > 1:
            replies += [json.dumps(idle)] * 2
        if repair:
            replies.append(json.dumps([RED, *idle[1:]]))
        spec = self.spec(TWO, "OWN", horizon, max_env_steps=1, parse_mode=mode)
        return self.play(spec, replies, tag)

    def test_forms_lengths_and_strict_refusals_through_the_fake_model(self):
        pair = [RED, None]
        flat = json.dumps(pair)
        cases = (
            ("flat", flat, pair, "list", False, False),
            ("one", json.dumps([RED]), [RED], "list", False, False),
            ("fence", "```json\n" + flat + "\n```", pair, "fenced", False, False),
            ("prose", 'Use {"unknown":[null]} then [17] then ' + flat + " or [null, null].", pair, "fenced", False, False),
            ("execute", '[null] EXECUTE [null] EXECUTE\n' + flat, pair, "fenced", False, False),
            ("singleton-entries", json.dumps([[RED], [None]]), pair, "nested", False, False),
            ("outer-list", json.dumps([pair]), pair, "nested", False, False),
            ("self", json.dumps({A: pair}), pair, "self_dict", False, False),
            ("self-nested", json.dumps({"Agent[0.50,0.5]": [[RED], [None]]}), pair, "self_dict", False, False),
            ("self-prose", "I propose " + json.dumps({A: [pair]}), pair, "self_dict", False, False),
            ("quoted-action", json.dumps(RED), [RED], "string", False, False),
            ("bare-action", RED, [RED], "string", False, False),
            ("bare-null", "null", [None], "string", False, False),
            ("prose-scalar", "EXECUTE " + json.dumps(RED) + " then [null]", [RED], "string", False, False),
            ("padded", json.dumps([RED]), [RED, None, None], "list", True, False),
            ("empty", "[]", [None, None], "list", True, False),
            ("cut", json.dumps([RED, None, RED, RED]), pair, "list", False, True),
            ("nested-padded", json.dumps([[RED]]), pair, "nested", True, False),
            ("self-cut", json.dumps({A: [[RED], [None], [RED]]}), pair, "self_dict", False, True),
            ("fenced-padded", "reply: [" + json.dumps(RED) + "]", pair, "fenced", True, False),
        )
        for name, raw, expected, form, padded, cut in cases:
            for mode in ("lenient", "strict"):
                with self.subTest(case=name, mode=mode):
                    rescue = form != "list" or padded or cut
                    refused = mode == "strict" and rescue
                    row, trace, folder = self.one_round(raw, len(expected), name + mode, mode=mode, repair=refused)
                    first = trace[0]
                    self.assertEqual(first["response"], raw)
                    self.assertEqual((first["own_reply_form"], first["own_reply_padded"], first["own_reply_cut"]),
                                     (None, False, False) if refused else (form, padded, cut))
                    self.assertEqual((row["lenient_rescues"], row["own_robots_dropped"]), (int(rescue and not refused), 0))
                    checks = row["round_log"][0]["checks"]
                    self.assertEqual(checks[0]["status"], "parse failure" if refused else "valid")
                    self.assertEqual([c["speaker"] for c in checks if c["repair"]], [A] if refused else [])
                    accepted = [RED, *([None] * (len(expected) - 1))] if refused else expected
                    dialogue = read_json(folder / "dialogue_history/dialogue_history0.txt")
                    self.assertEqual(dialogue[A], accepted)
                    plan = {B: GREEN_TO_D} if accepted[0] is None else {A: accepted[0], B: GREEN_TO_D}
                    self.assertEqual(row["iterations"][0]["issued_plan"], plan)

    def test_foreign_or_malformed_values_do_not_supply_an_inner_action(self):
        rejected = (
            (1, json.dumps({B: [RED]})), (1, "reply: " + json.dumps({B: [[RED]]})),
            (1, json.dumps({"Agent[0.50000000000000001, 0.5]": [RED]})),
            (1, json.dumps({A: [RED], B: [None]})), (1, json.dumps({A: RED})),
            (1, json.dumps([{A: RED}])), (1, json.dumps([RED, {B: [RED]}])),
            (1, '{"' + A + '":[null],"' + A + '":[' + json.dumps(RED) + ']}'),
            (1, 'before [null] EXECUTE [invalid, [null]]'), (1, "nullified"),
            (2, json.dumps(RED)), (2, RED), (2, json.dumps([[RED, None], [RED]])),
            (2, json.dumps([[[RED, None]]])),
        )
        for index, (horizon, raw) in enumerate(rejected):
            with self.subTest(raw=raw):
                row, trace, _ = self.one_round(raw, horizon, str(index), repair=True)
                self.assertEqual(row["round_log"][0]["checks"][0]["status"], "parse failure")
                self.assertIsNone(trace[0]["own_reply_form"])
                self.assertEqual(row["iterations"][0]["action_calls"][A], trace[-1]["number"])

    def test_exact_parse_and_feasibility_feedback_include_the_speakers_format(self):
        doable = ["move(box_red, square[1.5, 0.5])", TO_B, RED]
        example = json.dumps([doable[0], None])
        peers = "{}"
        instruction = (f" Output only a list like {example} with 2 entries, each one action string for yourself or null."
                       + "\n" + OWN_DIALOGUE + peers)
        for tag, raw, reason in (
                ("syntax", "not JSON", "Your reply could not be read as a JSON list of 2 entries."),
                ("infeasible", json.dumps([BAD, None]), f"Your first entry {json.dumps(BAD)} is not in your doable "
                 f"action list {json.dumps(doable)}. Choose from that list or use null.")):
            row, trace, _ = self.one_round(raw, 2, tag, repair=True)
            self.assertEqual(trace[-1]["messages"][-2]["content"], raw)
            self.assertEqual(trace[-1]["messages"][-1]["content"], reason + instruction)
            self.assertEqual(repair_feedback(trace[-1]), reason + instruction)
            self.assertEqual(classify(row, trace)["repair_calls"], 1)

    def test_dropped_robot_contributes_no_suffix_and_can_act_next_round(self):
        idle = [None] * 3
        bad = [BAD, GREEN_TO_D, None]
        replies = [[RED, None, None], bad, idle, idle] + [bad] * OWN_MAX_REPAIRS
        replies += [idle, [GREEN_TO_D, None, None], idle, [None, GREEN, None]]
        for mode in ("lenient", "strict"):
            row, trace, folder = self.play(self.spec(TWO, "OWN", 3, parse_mode=mode), list(map(json.dumps, replies)), mode)
            first, second = row["round_log"]
            self.assertEqual((row["strict_success"], row["steps"], row["planning_rounds"], row["api_calls"]),
                             (True, 3, 2, 10))
            self.assertEqual((first["own_robots_dropped"], second["own_robots_dropped"], row["own_robots_dropped"]),
                             (1, 0, 1))
            self.assertEqual(first["proposed_plans"], [{A: RED}, {}, {}])
            self.assertIsNone(read_json(folder / "dialogue_history/dialogue_history0.txt")[B])
            self.assertEqual([it["action_calls"] for it in row["iterations"]], [{A: 1}, {B: 8}, {D: 10}])
            self.assertEqual([c["speaker"] for c in trace], [A, B, C, D] + [B] * OWN_MAX_REPAIRS + [A, B, C, D])
            self.assertEqual((row["own_reply_form_counts"], row["discarded_steps"]), ({"list": 10}, 0))

    def test_last_authorized_repair_can_rescue_a_robot(self):
        replies = [json.dumps([RED])] + ["?"] * OWN_MAX_REPAIRS + [json.dumps([[GREEN_TO_D]]), json.dumps([GREEN])]
        row, trace, _ = self.play(self.spec(TWO, "OWN", 1), replies)
        first = row["round_log"][0]
        self.assertEqual((len(first["checks"]), first["checks"][-1]["status"], trace[3]["own_reply_form"]),
                         (4, "valid", "nested"))
        self.assertEqual((row["strict_success"], row["api_calls"], row["own_robots_dropped"]), (True, 5, 0))
        self.assertEqual(row["iterations"][0]["action_calls"], {A: 1, B: 4})

    def test_same_robot_dropped_in_two_rounds_counts_twice(self):
        idle = "[null, null]"
        replies = []
        for first in (idle, json.dumps([RED, None])):
            replies.extend([first, "bad", idle, idle] + ["bad"] * OWN_MAX_REPAIRS)
        row, _, _ = self.play(self.spec(TWO, "OWN", 2, max_env_steps=1), replies)
        self.assertEqual([(b["first_step"], b["own_robots_dropped"], b["effective_steps"]) for b in row["round_log"]],
                         [(1, 1, 0), (1, 1, 1)])
        self.assertEqual((row["own_robots_dropped"], row["empty_steps_skipped"], row["api_calls"]), (2, 2, 12))

    def test_interrupted_repairs_do_not_drop_early_or_double_count_on_resume(self):
        spec = self.spec(TWO, "OWN", 1)
        replies = [json.dumps({A: [RED]})] + ["unreadable"] * (1 + OWN_MAX_REPAIRS)
        replies += [json.dumps([GREEN_TO_D]), json.dumps([GREEN])]
        path = self.work / "episodes" / spec.name / "episode.json"
        first = Invocation(self.work, self.work / "first.json")
        first.create(3, 5, "fake")
        with patch("fake_model.reply", side_effect=replies[:3]):
            run_episode(spec, self.work, first.path, "fake", "correct", 300)
        partial = read_json(path)
        self.assertEqual((partial["success_failure"], partial["steps"], partial["own_reply_form_counts"],
                          partial["own_robots_dropped"]), (CALL_LIMIT, 0, {"self_dict": 1}, 0))
        second = Invocation(self.work, self.work / "second.json")
        second.create(None, 5, "fake")
        with patch("fake_model.reply", side_effect=replies[3:]):
            run_episode(spec, self.work, second.path, "fake", "correct", 300)
        row = read_json(path)
        self.assertEqual((row["strict_success"], row["own_reply_form_counts"], row["own_robots_dropped"],
                          row["api_calls"]), (True, {"self_dict": 1, "list": 2}, 1, 6))
        self.assertEqual([b["own_robots_dropped"] for b in row["round_log"]], [1, 0, 0])
        self.assertEqual([read_json(b.path)["calls"] for b in (first, second)], [3, 3])

    def test_reported_purple_move_executes_and_both_reports_reconcile(self):
        out = self.work / "purple"
        with redirect_stdout(io.StringIO()):
            purple_round(out)
        folder = out / "episodes/4x4_OWN_static_env0"
        row, trace = read_json(folder / "episode.json"), calls(folder)
        self.assertEqual(trace[0]["response"], '[["move(box_purple, square[0.5, 2.5])"]]')
        self.assertEqual((trace[0]["speaker"], row["iterations"][0]["issued_plan"]), (PURPLE_AGENT, {PURPLE_AGENT: PURPLE_MOVE, C: GREEN}))
        self.assertIn("box_purple", row["final_state"]["0.5_2.5"])
        self.assertEqual((row["success_failure"], row["steps"], row["api_calls"], row["own_robots_dropped"]), (ENV_STEP_LIMIT, 1, 10, 1))
        expected = {"list": 3, "nested": 1, "self_dict": 1, "string": 1, "fenced": 1}
        self.assertEqual(Counter(c["own_reply_form"] for c in trace if c["own_reply_form"]), expected)
        self.assertEqual(row["own_reply_form_counts"], expected)
        demand = cli("output_demand.py", out)
        summary = cli("summarize.py", out)
        planning = cli("summarize.py", "--by", "planning", out)
        for process in (demand, summary, planning):
            self.assertEqual(process.returncode, 0, process.stderr)
        table, = pipe_rows(demand.stderr, SECTION)
        self.assertEqual(pipe_rows(planning.stdout, SECTION), [table])
        _, header, values = summary.stdout.splitlines()
        default = dict(zip(header.split(" | "), values.split(" | "), strict=True))
        for report in (table, default):
            self.assertEqual({form: int(report["own_reply_form_" + form]) for form in OWN_FORMS}, expected)
            self.assertEqual(report["own_robots_dropped"], "1")
        measured = list(csv.DictReader(io.StringIO(demand.stdout)))
        self.assertEqual([r["own_reply_form"] for r in measured], [c["own_reply_form"] or "" for c in trace])
        self.assertEqual([r["call_number"] for r in measured if r["own_reply_padded"] == "True"], ["6"])
        self.assertEqual([r["call_number"] for r in measured if r["own_reply_cut"] == "True"], ["7"])
        self.assertEqual([r["plan_agents"] for r in measured[:2]], ["1", "1"])
        with (out / "episodes.csv").open() as source:
            exported, = csv.DictReader(source)
        self.assertEqual((json.loads(exported["own_reply_form_counts"]), exported["own_robots_dropped"]), (expected, "1"))

    def test_legacy_own_measurements_use_the_original_accepted_list(self):
        # Task 12 skipped the short draft list and accepted the full list in prose.
        archived = dict(role="own", speaker=A, response="Draft [] then " + json.dumps([RED, None]))
        self.assertEqual(selected_sequence(archived, PlanParser(), 2)[0], 1)
        table = io.StringIO()
        print_planning_table([dict(framework="OWN", horizon=2, api_calls=1, finished=True,
                                   strict_success=False, success_failure="Syntactic Error")], table)
        row, = pipe_rows(table.getvalue(), SECTION)
        self.assertTrue(all(row["own_reply_form_" + f] == "NA" for f in OWN_FORMS))
        self.assertEqual(row["own_robots_dropped"], "NA")


if __name__ == "__main__":
    suites = sys.argv[1:] or ["test_chen2d", *(f"test_chen2d_v{n}" for n in range(2, 14))]
    with local_references():
        print("Folder-local reference code and scripted model transports. Network connections disabled.", flush=True)
        result = unittest.TextTestRunner(verbosity=2).run(unittest.defaultTestLoader.loadTestsFromNames(suites))
    sys.exit(not result.wasSuccessful())
