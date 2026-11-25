from regression_inputs import REGRESSION
"""Offline three-structure comparisons, prompt byte checks and accounting."""
import io
import json
import runpy
import sys
import unittest
from collections import Counter
from dataclasses import replace
from types import SimpleNamespace
from unittest.mock import patch

from LLM import MODEL, load_real_api
from episode import HISTORY_METHODS, run_episode
from failure_causes import classify, print_tables
from limits import CALL_LIMIT, OUTPUT_LIMIT, Invocation
from output_demand import measure_episode, unit_totals
from planning_metrics import ENV_STEP_LIMIT, ITERATION_LIMIT, comparison_metrics, cutoff_records
from prompt_env1 import LEADER_SEQUENCE, input_prompt_local_agent_DMAS_dialogue_func
from storage import ROOT, read_json
from test_chen2d import calls
from test_chen2d_v3 import scripted_transport
from test_chen2d_v4 import cli
from test_chen2d_v5 import local_references
from test_chen2d_v9 import FEEDBACK, call, iteration, outcome, pipe_rows
from test_chen2d_v11 import A, B, C, D, BAD, ONE, PATH, TO_D, HorizonFixtures


def dmas(plans):
    return ["PROCEED"] * 3 + ["EXECUTE\n" + json.dumps(plans)]


def own(plans, horizon=3):
    return [json.dumps([p.get(robot) for p in plans] + [None] * (horizon - len(plans)))
            for robot in (A, B, C, D)]


def submissions(fw, plans):
    if fw == "DMAS":
        return dmas(plans)
    if fw == "OWN":
        return own(plans)
    return [json.dumps(plans)]


class FairPlanningTests(HorizonFixtures):
    def test_dmas_four_speakers_one_final_reply_three_steps(self):
        spec = self.spec(ONE, "DMAS", parse_mode="strict", history_method="none")
        row, trace, folder = self.play(spec, dmas(PATH))
        self.assertEqual([c["speaker"] for c in trace], [A, B, C, D])
        self.assertEqual([c["role"] for c in trace], ["dialogue"] * 4)
        batch, = row["round_log"]
        self.assertEqual((batch["final_speaker"], batch["final_call"], batch["plans_proposed"],
                          batch["effective_steps"], batch["stop_reason"]), (D, 4, 3, 3, "complete"))
        self.assertEqual([it["issued_plan"] for it in row["iterations"]], PATH)
        self.assertEqual([it["calls"] for it in row["iterations"]], [4, 0, 0])
        self.assertTrue(row["strict_success"])
        for i, c in enumerate(trace):
            prompt = c["messages"][1]["content"]
            self.assertIn(LEADER_SEQUENCE.format(h=3), prompt)
            self.assertIn("Propose your own actions for the next 3 steps at the current round.", prompt)
            self.assertIn("If everyone has made proposals and got approved,", prompt)
            self.assertNotIn("Example#1", prompt)
            for earlier in trace[:i]:
                self.assertIn(f"[{earlier['speaker']}: PROCEED]", prompt)
        self.assertIn(trace[-1]["response"], (folder / "dialogue_history/dialogue_history0.txt").read_text())

    def test_dmas_keeps_row_break_and_four_discussion_sweeps(self):
        # The earlier row can submit a different plan. Only the last submission is executed.
        row, trace, _ = self.play(self.spec(ONE, "DMAS"), ["PROCEED"] * 12 +
                                  ["EXECUTE\n[{}]", "EXECUTE\n" + json.dumps(PATH)])
        self.assertEqual([c["speaker"] for c in trace[-2:]], [A, C])
        self.assertEqual([c["round"] for c in trace], [1]*4 + [2]*4 + [3]*4 + [4]*2)
        self.assertEqual((row["round_log"][0]["final_speaker"], row["effective_steps"]), (C, 3))
        self.assertIn('[Agent[0.5, 0.5]: EXECUTE\n[{}]]', trace[-1]["messages"][1]["content"])
        with patch("episode.step_limit", return_value=1):
            row, trace, _ = self.play(self.spec(ONE, "DMAS"), ["PROCEED"] * 16, "no-agreement")
        self.assertEqual((row["steps"], row["plans_proposed"], len(trace), row["success_failure"],
                          row["round_log"][0]["stop_reason"]), (0, 0, 16, ITERATION_LIMIT, "no agreement"))

    def test_invalid_second_dmas_plan_discards_remainder_without_repair(self):
        first = [PATH[0], {A: BAD, B: TO_D}, {}]
        row, trace, _ = self.play(self.spec(ONE, "DMAS"), dmas(first) + dmas(PATH[1:]))
        self.assertEqual([len(c["messages"]) for c in trace], [2]*8)
        b, end = row["round_log"]
        self.assertEqual((b["invalid_position"], b["effective_steps"], b["discarded_steps"], b["empty_steps_skipped"],
                          b["rejected_calls"], end["first_step"]), (2, 1, 2, 0, {A: 4}, 2))
        self.assertEqual([it["issued_plan"] for it in row["iterations"]], PATH)
        self.assertEqual((row["plans_proposed"], row["steps"], row["discarded_steps"]), (5, 3, 2))

    def test_parse_or_bad_first_plan_repairs_only_the_final_writer(self):
        for tag, bad in (("parse", '{"plans":[]}'), ("invalid", json.dumps([{A: BAD}]))):
            # B submits and the following row only discusses. The repair must still go to B.
            replies = ["PROCEED", "EXECUTE\n" + bad, "PROCEED", "PROCEED", json.dumps(PATH)]
            row, trace, _ = self.play(self.spec(ONE, "DMAS", parse_mode="strict"), replies, tag)
            self.assertEqual([c["speaker"] for c in trace], [A, B, C, D, B])
            self.assertEqual(trace[-1]["messages"][1], trace[1]["messages"][1])
            self.assertEqual(trace[-1]["messages"][-2]["content"], replies[1])
            self.assertIn("whole list for all the agents", trace[-1]["messages"][-1]["content"])
            self.assertEqual([c["repair"] for c in row["round_log"][0]["checks"]], [False, True])
            self.assertEqual((row["round_log"][0]["final_call"], row["steps"], row["api_calls"]), (5, 3, 5))

    def test_idle_receivers_act_in_same_own_round_and_null_robot_still_speaks(self):
        row, trace, _ = self.play(self.spec(ONE, "OWN"), own(PATH))
        self.assertEqual([c["speaker"] for c in trace], [A, B, C, D])
        self.assertIn("can observe [], can do []", trace[1]["messages"][1]["content"])
        self.assertEqual(json.loads(trace[1]["response"]), [None, TO_D, None])
        self.assertEqual(json.loads(trace[2]["response"]), [None] * 3)
        self.assertEqual([it["action_calls"] for it in row["iterations"]], [{A: 1}, {B: 2}, {D: 4}])
        self.assertEqual((row["planning_rounds"], row["effective_steps"], row["api_calls"]), (1, 3, 4))

    def test_empty_rounds_never_advance_state_history_or_event_clock(self):
        for fw in ("CMAS", "DMAS", "OWN"):
            spec = self.spec(ONE, fw, history_window=100000, cmas_history="on")
            row, trace, folder = self.play(spec, submissions(fw, [{}, {}, {}]) + submissions(fw, [{}, PATH[0], {}])
                                          + submissions(fw, [PATH[1], {}, PATH[2]]), fw)
            batches = row["round_log"]
            self.assertEqual([b["first_step"] for b in batches], [1, 1, 2])
            self.assertEqual([b["stop_reason"] for b in batches], ["all empty", "empty tail", "complete"])
            self.assertEqual([b["empty_steps_skipped"] for b in batches], [3, 2, 1])
            self.assertEqual([b["effective_steps"] for b in batches], [0, 1, 2])
            self.assertEqual((row["steps"], row["effective_steps"], row["plans_proposed"], row["empty_steps_skipped"]),
                             (3, 3, 9, 6))
            self.assertEqual([it["step"] for it in row["iterations"] if it["executed"]], [1, 2, 3])
            self.assertEqual(len(list((folder / "pg_state").glob("*.json"))), 4)
            for c in trace:
                prompt = c["messages"][1]["content"]
                self.assertEqual("State1:" in prompt, c["planning_round"] == 3)
                self.assertNotIn("Action2:", prompt)
            self.assertEqual(classify(row, trace)["iterations_with_proposal"], 3)
            _, segments = measure_episode(folder.parents[1], dict(row, reasoning_setting="default"), Counter())
            units = unit_totals(segments, "step")
            self.assertEqual((len(units), sum(s["executed"] for s in units)), (3, 3))
            self.assertEqual(len(unit_totals(segments, "planning_round")), 3)
            self.assertEqual(sum(s["attempt_count"] for s in units), len(trace))

    def test_no_past_history_in_all_frameworks_and_shared_physical_cap(self):
        for fw in ("CMAS", "DMAS", "OWN"):
            spec = self.spec(ONE, fw, history_window=100000, history_method="none", cmas_history="on", max_env_steps=2)
            row, trace, _ = self.play(spec, submissions(fw, [PATH[0], {}, {}]) + submissions(fw, PATH[1:]), fw)
            self.assertEqual([b["effective_steps"] for b in row["round_log"]], [1, 1])
            self.assertEqual((row["success_failure"], row["steps"], row["discarded_steps"], row["stop_reason"]),
                             (ENV_STEP_LIMIT, 2, 0, "environment step limit"))
            for c in trace:
                self.assertNotRegex(c["messages"][1]["content"], r"(?m)^\s*(?:State|Action|Dialogue)\d+:")
            self.assertEqual({c["planning_round"] for c in trace}, {1, 2})
            exact, _, _ = self.play(replace(spec, max_env_steps=3), submissions(fw, PATH), fw + "-exact")
            self.assertTrue(exact["strict_success"])
            zero, trace, _ = self.play(replace(spec, max_env_steps=0), [], fw + "-zero")
            self.assertEqual((zero["success_failure"], zero["steps"], trace), (ENV_STEP_LIMIT, 0, []))

    def test_retry_and_repair_denominator_and_discard_accounting(self):
        spec = self.spec(ONE, "DMAS", horizon=4)
        replies = dmas([{A: BAD}]) + [None, json.dumps([{}, PATH[0], {A: BAD}, {}])] + dmas([PATH[1], {}, PATH[2]])
        budget = Invocation(self.work, self.work / "meter.json")
        budget.create(None, 5, MODEL)
        with local_references(), scripted_transport(["truncated" if s is None else "ok" for s in replies]) as (sent, waits):
            connection = load_real_api().http.client.HTTPSConnection
            original = connection.getresponse
            def getresponse(conn):
                packet = json.loads(original(conn).read(-1))
                reply = replies[len(sent) - 1]
                if reply is not None:
                    packet["choices"][0]["message"]["content"] = reply
                return SimpleNamespace(status=200, read=lambda _: json.dumps(packet).encode())
            with patch.object(connection, "getresponse", getresponse):
                run_episode(spec, self.work, budget.path, MODEL, "correct", 300, 128, 0., .7)
        folder = self.work / "episodes" / spec.name
        row, trace = read_json(folder / "episode.json"), calls(folder)
        stats = comparison_metrics([row])
        self.assertEqual((len(waits), len(trace), len(sent), read_json(budget.path)["calls"]), (1, 9, 10, 10))
        self.assertEqual([b["effective_steps"] for b in row["round_log"]], [1, 2])
        self.assertEqual((stats["plans_proposed"], stats["effective_steps"], stats["empty_steps_skipped"],
                          stats["discarded_steps"], stats["median_effective_steps_per_planning_round"],
                          stats["effective_steps_per_model_call"]), (7, 3, 2, 2, 1.5, .3))
        self.assertEqual(row["cut_calls"], [dict(call=5, planning_round=1, speaker=D, role="repair_call", attempts=1, terminal=False)])
        self.assertEqual((stats["cut_repair_call"], stats["ended_by_output_limit"]), (1, 0))

    def test_cut_attribution_including_discussion_and_terminal_speaker(self):
        for fw, role, expected in (("CMAS", "central", "leader"), ("DMAS", "dialogue", "final_dmas_speaker"),
                                   ("OWN", "own", "individual_robot")):
            last = dict(call(1, reply=None, role=role, kinds=["truncated"]*3), speaker=B)
            row = dict(framework=fw, horizon=3, success_failure=OUTPUT_LIMIT)
            self.assertEqual(cutoff_records(row, [last]), [dict(call=1, planning_round=1, speaker=B,
                                                               role=expected, attempts=3, terminal=True)])
        trace = [call(1, role="dialogue", reply="PROCEED", kinds=["truncated", "ok"]),
                 call(2, role="dialogue", reply="EXECUTE [{}]", kinds=["truncated", "ok"]),
                 call(3, role="dialogue", reply=None, feedback=FEEDBACK, kinds=["truncated"]*3)]
        row = dict(framework="DMAS", horizon=3, success_failure=OUTPUT_LIMIT,
                   round_log=[dict(planning_round=1, final_submission_call=2, final_call=3)])
        self.assertEqual([(r["role"], r["attempts"]) for r in cutoff_records(row, trace)],
                         [("dialogue_turn", 1), ("final_dmas_speaker", 1), ("repair_call", 3)])

    def test_terminal_dmas_truncation_counts_attempts_and_publishes_no_partial_plan(self):
        spec = self.spec(ONE, "DMAS")
        budget = Invocation(self.work, self.work / "cut.json")
        budget.create(None, 5, MODEL)
        with local_references(), scripted_transport(["truncated"]*3):
            run_episode(spec, self.work, budget.path, MODEL, "correct", 300, 128, 0., .7)
        row = read_json(self.work / "episodes" / spec.name / "episode.json")
        counts = comparison_metrics([row])
        self.assertEqual((row["steps"], row["cut_calls"][0]["speaker"], row["round_log"][0]["stop_reason"]),
                         (0, A, "output limit"))
        self.assertEqual((counts["ended_by_output_limit"], counts["cut_final_dmas_speaker"],
                          counts["output_limit_final_dmas_speaker"], counts["model_calls"]), (1, 3, 1, 3))

    def test_state_order_is_the_exact_two_sentence_move_for_both_prompts(self):
        archived = runpy.run_path(str(REGRESSION / "chen2d-11/fake-h5-8192/source/prompt_env1.py"))
        original = archived["input_prompt_local_agent_DMAS_dialogue_func"]
        past_state, current = {"old": ["box_red"]}, {"now": ["target_red"]}
        for method in ("authors", "dialogue", "none"):
            for fw in ("DMAS", "OWN"):
                past = HISTORY_METHODS[method]
                args = ("SELF\n", "OTHERS\n", "CURRENT PEERS", ["MOVE"], [past_state, current], ["OLD PEERS"], past)
                options = dict(own_horizon=3 if fw == "OWN" else None, history_window=100000, announcement="NOTICE\n")
                before = input_prompt_local_agent_DMAS_dialogue_func(*args, **options)
                # Task 14 adds the OWN output example after the full state/history context.
                self.assertEqual(before.partition("[Own Action Output Instruction]")[0],
                                 original(*args, **options).partition("[Own Action Output Instruction]")[0])
                pad = "  " if method == "none" else "    "
                state = ("The current state and possible actions of yourself are: {SELF\n}.\n" + pad +
                         "The current states and possible actions of all other agents are: {OTHERS\n}.")
                history = "The previous state and action pairs at each step are:\n"
                if method != "none":
                    history += pad + "State1: {'old': ['box_red']}\n"
                    if method == "dialogue":
                        history += "Dialogue1: OLD PEERS\n"
                    history += "Action1: MOVE\n\n"
                head, separator, tail = before.partition("NOTICE\n" + state + "\n" + pad + history)
                self.assertTrue(separator)
                self.assertTrue(tail.startswith("\n" + pad + "Please learn from previous steps."))
                expected = head + history + "\n" + pad + "NOTICE\n" + state + tail
                self.assertEqual(input_prompt_local_agent_DMAS_dialogue_func(*args, state_position="after", **options), expected)

    def test_cli_records_and_groups_order_and_limits_in_both_tables(self):
        outs = []
        def checked(*args):
            p = cli(*args)
            self.assertEqual(p.returncode, 0, p.stderr)
            return p
        options = ("--frameworks", "CMAS,DMAS,OWN", "--model", "fake", "--horizon", 1, "--envs", 0,
                   "--conditions", "static", "--dropoff", "event", "--max-env-steps", 2,
                   "--cmas-history", "on", "--history-window", 100000)
        for name, flag, limit in (("default", [], 2048), ("before", ["--state-position", "before"], 8192),
                                  ("after", ["--state-position", "after"], 8192)):
            out = self.work / name
            outs.append(out)
            checked("run_chen2d.py", "--out", out, *options, "--max-output-tokens", limit, *flag)
            setting = flag[-1] if flag else "before"
            self.assertEqual(read_json(out / "run.json")["state_position"], setting)
            for item in read_json(out / "assignments.json").values():
                row = read_json(out / "episodes" / item["episode_id"] / "episode.json")
                for record in (item, row):
                    self.assertEqual((record["state_position"], record["state_position_effective"], record["max_env_steps"]),
                                     (setting, "ignored" if item["framework"] == "CMAS" else setting, 2))
                self.assertEqual((row["steps"], row["success_failure"]), (2, ENV_STEP_LIMIT))
        for fw in ("CMAS", "DMAS", "OWN"):
            defaults, before, after = [calls(out / "episodes" / f"2x2_{fw}_static_env0") for out in outs]
            prompts = lambda cs: [c["messages"] for c in cs]
            self.assertEqual(prompts(defaults), prompts(before))
            self.assertEqual(prompts(before) == prompts(after), fw == "CMAS")
        outcome_table = "Planning outcomes and physical calls"
        summary = pipe_rows(checked("summarize.py", "--by", "planning", *outs).stdout, outcome_table)
        demand = pipe_rows(checked("output_demand.py", *outs).stderr, outcome_table)
        self.assertEqual(summary, demand)
        self.assertEqual(len(summary), 9)
        self.assertTrue(all(r["episodes"] == r["ended_by_env_step_limit"] == "1" for r in demand))
        causes = pipe_rows(checked("failure_causes.py", *outs).stderr, "failure causes")
        self.assertEqual({(r["framework"], r["state_position"], r["max_output_tokens"]) for r in causes},
                         {(r["framework"], r["state_position"], r["max_output_tokens"]) for r in demand})
        self.assertNotEqual(cli("run_chen2d.py", "--out", outs[-1], *options, "--state-position", "before").returncode, 0)
        self.assertNotEqual(cli("run_chen2d.py", "--out", self.work/"invalid", *options, "--frameworks", "CMAS",
                                "--state-position", "before").returncode, 0)
        self.assertNotEqual(cli("run_chen2d.py", "--out", self.work/"invalid-cap", *options, "--max-env-steps", -1).returncode, 0)

    def test_ended_by_iteration_limit_with_and_without_executed_move_cycle(self):
        forward = ([.5, .5], "box_red", [.5, 1.5])
        back = ([.5, 1.5], "box_red", [.5, .5])
        subjects = [outcome(ITERATION_LIMIT, *(iteration(i, move) for i, move in enumerate([forward, back]*2, 1))),
                    outcome(ITERATION_LIMIT), outcome("Syntactic Error"), outcome(ITERATION_LIMIT, boxes=0, strict=True)]
        values = []
        for subject in subjects:
            r = classify(subject, [])
            values.append(dict(r, model="fake", reasoning_setting="default", max_output_tokens=8192, history_method="authors",
                               cmas_history="off", history_window=100000, size="2x2", framework="DMAS", condition="static",
                               horizon=1, state_position="after", max_env_steps="default"))
        stream = io.StringIO()
        print_tables(values, [], stream)
        result, = pipe_rows(stream.getvalue(), "failure causes")
        self.assertEqual([result[k] for k in ("completed_episodes", "ended_by_syntactic_error", "ended_by_iteration_limit",
                                              "iteration_limit_with_move_cycle", "iteration_limit_without_move_cycle")],
                         ["1", "1", "2", "1", "1"])

    def test_resume_after_empty_round_replays_exact_calls_and_contiguous_steps(self):
        spec = self.spec(ONE, "DMAS")
        first = Invocation(self.work, self.work / "partial.json")
        first.create(5, 5, "fake")
        replies = dmas([{}]*3) + dmas(PATH)
        with patch("fake_model.reply", side_effect=replies[:5]):
            run_episode(spec, self.work, first.path, "fake", "correct", 300)
        path = self.work / "episodes" / spec.name / "episode.json"
        self.assertEqual((read_json(path)["steps"], read_json(path)["success_failure"]), (0, CALL_LIMIT))
        second = Invocation(self.work, self.work / "resume.json")
        second.create(None, 5, "fake")
        with patch("fake_model.reply", side_effect=replies[5:]):
            run_episode(spec, self.work, second.path, "fake", "correct", 300)
        row = read_json(path)
        self.assertEqual((row["steps"], row["planning_rounds"], row["api_calls"], row["empty_steps_skipped"]), (3, 2, 8, 3))
        self.assertEqual((read_json(first.path)["calls"], read_json(second.path)["calls"]), (5, 3))


if __name__ == "__main__":
    suites = sys.argv[1:] or ["test_chen2d", *(f"test_chen2d_v{n}" for n in range(2, 13))]
    with local_references():
        print("Folder-local reference code and scripted model transports. Network connections disabled.", flush=True)
        result = unittest.TextTestRunner(verbosity=2).run(unittest.defaultTestLoader.loadTestsFromNames(suites))
    sys.exit(not result.wasSuccessful())
