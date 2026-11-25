"""Offline horizon, own-action, accounting and exact v10 replay checks."""
import csv
import io
import json
import sys
import tempfile
import unittest
from dataclasses import replace
from pathlib import Path
from regression_inputs import REGRESSION
from types import SimpleNamespace
from unittest.mock import patch

from LLM import MODEL, load_real_api
from episode import Spec, run_episode
from failure_causes import classify
from limits import CALL_CEILING, CALL_LIMIT, OUTPUT_LIMIT, Invocation
from plan_parse import PlanParser
from planning_metrics import ENV_STEP_LIMIT
from prompt_env1 import LEADER_SEQUENCE, LEADER_STEP, OWN_DIALOGUE, history_tokens
from storage import ROOT, digest, read_json, write_json
from test_chen2d import calls, fixture_spec
from test_chen2d_v3 import scripted_transport
from test_chen2d_v4 import cli
from test_chen2d_v5 import local_references
from test_chen2d_v9 import pipe_rows


A, B, C, D = "Agent[0.5, 0.5]", "Agent[0.5, 1.5]", "Agent[1.5, 0.5]", "Agent[1.5, 1.5]"
TO_B, TO_D, RED = "move(box_red, square[0.5, 1.5])", "move(box_red, square[1.5, 1.5])", "move(box_red, target_red)"
GREEN_TO_D, GREEN = "move(box_green, square[1.5, 1.5])", "move(box_green, target_green)"
BAD = "move(box_missing, target_missing)"
PATH = [{A: TO_B}, {B: TO_D}, {D: RED}]
ONE = {"0.5_0.5": ["box_red"], "0.5_1.5": [], "1.5_0.5": [], "1.5_1.5": ["target_red"]}
TWO = {"0.5_0.5": ["box_red", "target_red"], "0.5_1.5": ["box_green"], "1.5_0.5": [], "1.5_1.5": ["target_green"]}
V10 = REGRESSION / "chen2d-10/fake-static"


class HorizonFixtures(unittest.TestCase):
    def setUp(self):
        tmp = tempfile.TemporaryDirectory(dir=ROOT, prefix=".chen11-test-")
        self.addCleanup(tmp.cleanup)
        self.work = Path(tmp.name)

    def spec(self, board, framework="CMAS", horizon=3, **options):
        base = fixture_spec(self.work / "board.json", board, "static")
        return replace(base, framework=framework, horizon=horizon, **options)

    def play(self, spec, replies, tag="play", ceiling=300):
        out = self.work / tag
        out.mkdir()
        budget = Invocation(out, out / "script.json")
        budget.create(None, 5, "fake")
        with patch("fake_model.reply", side_effect=replies):
            run_episode(spec, out, budget.path, "fake", "correct", ceiling)
        folder = out / "episodes" / spec.name
        return read_json(folder / "episode.json"), calls(folder), folder


class HorizonTests(HorizonFixtures):
    def test_archived_cmas_and_dmas_horizon_one_all_episode_files_byte_for_byte(self):
        config = read_json(V10 / "run.json")
        stamp = "482329689b8a"
        self.assertEqual(config["code_version"], stamp)
        for fw, count, sha in (
                ("CMAS", 41, "4724c44686f876085e92b6c5cd9b760b52ffccf51c10b5a7831af774b3e1fec7"),
                ("DMAS", 59, "39ade1b17dafecac4022770c92b94b41bc9e4fbe4b110d9cdf7622f7fb5e9df5")):
            archive = V10 / "episodes" / f"2x2_{fw}_static_env0"
            result = archive / "episode.json"
            self.assertEqual(digest(result.read_bytes()), sha)
            row, trace = read_json(result), calls(archive)
            spec = Spec(2, 2, fw, "static", 0, V10 / "maps/2x2/env0.json", row["env_sha256"], row["event_sha256"],
                        dropoff="event", horizon=1)
            out = self.work / fw
            out.mkdir()
            write_json(out / "run.json", config)
            budget = Invocation(out, out / (trace[0]["invocation"] + ".json"))
            budget.create(None, 2, "fake")
            step_clock = [v for it in row["iterations"] for v in (0., it["planning_seconds"])]
            with (patch("LLM.monotonic", side_effect=[v for c in trace for v in (0., c["elapsed_seconds"])]),
                  patch("episode.time", SimpleNamespace(monotonic=iter(step_clock).__next__)),
                  patch("episode.code_version", return_value=stamp)):
                run_episode(spec, out, budget.path, "fake", "correct", 300, 8192, 0., .7)
            new = out / "episodes" / spec.name
            names = {p.relative_to(archive) for p in archive.rglob("*") if p.is_file()}
            self.assertEqual(len(names), count)
            self.assertEqual({p.relative_to(new) for p in new.rglob("*") if p.is_file()}, names)
            for name in names:
                self.assertEqual((new / name).read_bytes(), (archive / name).read_bytes(), (fw, name))

    def test_three_state_dependent_plans_one_leader_call_and_exact_prompt_edit(self):
        spec = self.spec(ONE)
        row, trace, folder = self.play(spec, [json.dumps(PATH)])
        base, single, _ = self.play(replace(spec, horizon=1), list(map(json.dumps, PATH)), "one")
        self.assertEqual(single[0]["messages"][1]["content"].replace(LEADER_STEP, LEADER_SEQUENCE.format(h=3)),
                         trace[0]["messages"][1]["content"])
        self.assertEqual((row["strict_success"], row["steps"], row["planning_rounds"], row["authors_env_action_times"],
                          row["api_calls"], row["tokens"]), (True, 3, 1, 1, 1, 18))
        self.assertEqual((base["final_state"], base["correct_deliveries"]), (row["final_state"], 1))
        batch, = row["round_log"]
        self.assertEqual((batch["proposed_plans"], batch["plans_proposed"], batch["plans_executed"],
                          batch["stop_reason"]), (PATH, 3, 3, "complete"))
        self.assertEqual([it["calls"] for it in row["iterations"]], [1, 0, 0])
        self.assertEqual([it["issued_plan"] for it in row["iterations"]], PATH)
        self.assertEqual(sorted(p.name for p in (folder / "pg_state").glob("*.json")),
                         [f"pg_state{i}.json" for i in range(1, 5)])

    def test_later_invalid_joint_plan_is_atomic_discards_tail_and_replans_with_history(self):
        spec = self.spec(ONE, cmas_history="on", history_window=20000)
        first = [PATH[0], {B: TO_D, A: BAD}, {}]
        row, trace, _ = self.play(spec, [json.dumps(first), json.dumps(PATH[1:])])
        log, end = row["round_log"]
        self.assertEqual((log["stop_reason"], log["invalid_position"], log["plans_executed"], log["plans_proposed"]),
                         ("invalid", 2, 1, 3))
        self.assertEqual((end["first_step"], row["planning_rounds"], row["steps"], row["api_calls"]), (2, 2, 3, 2))
        self.assertEqual([it["issued_plan"] for it in row["iterations"]], PATH)
        self.assertEqual([len(c["messages"]) for c in trace], [2, 2])
        self.assertIn("Action1: " + json.dumps(PATH[0]), trace[1]["messages"][1]["content"])
        self.assertNotIn("Action2:", trace[1]["messages"][1]["content"])
        result = classify(row, trace)
        self.assertEqual((result["planning_iterations"], result["steps_executed"], result["first_plan_invalid_iterations"]),
                         (2, 3, 0))

    def test_leader_lenient_wrapper_strict_bare_list_and_first_plan_repair(self):
        wrapper = json.dumps({"plans": PATH})
        invalid = json.dumps([{A: BAD}, *PATH[1:]])
        for tag, mode, replies, first_status in (
                ("lenient", "lenient", ["draft {} EXECUTE draft {} EXECUTE\n```json\n" + wrapper + "\n```"], "valid"),
                ("strict", "strict", [wrapper, json.dumps(PATH)], "parse failure"),
                ("bad-first", "lenient", [invalid, json.dumps(PATH)], "invalid")):
            row, trace, _ = self.play(self.spec(ONE, parse_mode=mode), replies, tag)
            self.assertEqual((row["steps"], row["planning_rounds"], row["api_calls"], row["lenient_rescues"]),
                             (3, 1, len(replies), int(tag == "lenient")))
            self.assertEqual(row["round_log"][0]["checks"][0]["status"], first_status)
            if len(trace) == 2:
                self.assertIn("whole list", trace[1]["messages"][-1]["content"])
                self.assertEqual(trace[1]["messages"][-2]["content"], replies[0])
        row, trace, _ = self.play(self.spec(ONE, parse_mode="strict"), [wrapper] * 7, "exhausted")
        self.assertEqual((row["success_failure"], row["steps"], len(trace), row["round_log"][0]["stop_reason"]),
                         ("Syntactic Error", 0, 7, "parse failure"))
        self.assertEqual(PlanParser().sequence(json.dumps(PATH[0]), 3), PATH[:1])
        self.assertEqual(PlanParser().sequence("Agent[0.5, 0.5] can start. " + wrapper, 3), PATH)
        for malformed in (json.dumps(PATH * 2), '[{}, "bad"]', '[{"plans":[{}]}', 'draft {} EXECUTE nothing'):
            self.assertIsNone(PlanParser().sequence(malformed, 3))

    def test_checker_handles_coordinate_spacing_but_rejects_ignored_and_off_board_actions(self):
        spec = self.spec(ONE)
        spelling = {"Agent[0.5,0.5]": "move(box_red, square[0.5,1.5])"}
        for i, invalid in enumerate(({A: "nonsense"}, {A: "move(box_red, square[0.5, -0.5])"},
                                      {D: "move(target_red, square[0.5, 1.5])"},
                                      {A: TO_B, "Agent[0.5,0.5]": TO_B})):
            valid = [spelling, *PATH[1:]]
            row, trace, _ = self.play(spec, [json.dumps([invalid]), json.dumps(valid)], str(i))
            self.assertEqual((row["steps"], row["api_calls"], row["strict_success"]), (3, 2, True))
            self.assertIn("not in the doable action list", trace[1]["messages"][-1]["content"])
        row, _, _ = self.play(spec, [json.dumps([*PATH[:2], {D: "move(box_red, square[1.5, 2.5])"}]),
                                     json.dumps(PATH[2:])], "off-board")
        self.assertEqual(row["round_log"][0]["invalid_position"], 3)

    def test_event_fires_between_planned_steps_and_retains_the_original_producer(self):
        spec = replace(self.spec(ONE), condition="e1", event_step_override=1)
        row, trace, _ = self.play(spec, [json.dumps(PATH)])
        self.assertEqual((row["event_step"], row["steps"], row["planning_rounds"], row["api_calls"]), (1, 3, 1, 1))
        self.assertEqual((row["boxes_left"], row["wrong_deliveries"], row["strict_success"]), (0, 1, False))
        self.assertFalse(trace[0]["told"])
        self.assertFalse(row["first_plan_maker_had_news"])
        self.assertEqual([it["plan_maker_call"] for it in row["iterations"][1:]], [1, 1])

    def test_empty_step_and_completion_marker_use_live_board_and_limit_counts_rounds(self):
        spec = self.spec(ONE)
        replies = [[{}, *PATH[:2]], [PATH[2], {}, {D: BAD}]]
        with patch("episode.step_limit", return_value=2):
            row, trace, _ = self.play(spec, list(map(json.dumps, replies)))
        self.assertEqual([it["issued_plan"] for it in row["iterations"]], PATH)
        self.assertEqual((row["steps"], row["planning_rounds"], len(trace), row["strict_success"], row["success_failure"]),
                         (3, 2, 2, True, "failure over query time limit"))
        self.assertEqual([b["empty_steps_skipped"] for b in row["round_log"]], [1, 0])
        self.assertEqual([b["stop_reason"] for b in row["round_log"]], ["all executed", "complete"])

    def test_own_merges_idle_robots_nulls_and_attributes_calls_and_history(self):
        spec = self.spec(TWO, "OWN", history_method="dialogue", history_window=20000)
        a, b, d = [RED, None, None], [GREEN_TO_D, None, None], [GREEN, None, None]
        idle = [None] * 3
        row, trace, folder = self.play(spec, list(map(json.dumps, (a, b, idle, idle, idle, idle, idle, d))))
        self.assertEqual([(c["speaker"], c["role"], c["planning_round"], c["step"]) for c in trace],
                         [(s, "own", n, n) for n in (1, 2) for s in (A, B, C, D)])
        for c in trace:
            prompt = c["messages"][1]["content"]
            self.assertIn("The current state and possible actions of yourself are:", prompt)
            self.assertIn("The current states and possible actions of all other agents are:", prompt)
            self.assertNotIn("[Action Output Instruction]", prompt)
            self.assertNotIn("output PROCEED", prompt)
        self.assertIn(OWN_DIALOGUE + "{}", trace[0]["messages"][1]["content"])
        self.assertIn(OWN_DIALOGUE + json.dumps({A: a}), trace[1]["messages"][1]["content"])
        self.assertIn("Dialogue1: " + json.dumps({A: a, B: b, C: idle, D: idle}), trace[4]["messages"][1]["content"])
        self.assertEqual([it["issued_plan"] for it in row["iterations"]], [{A: RED, B: GREEN_TO_D}, {D: GREEN}])
        self.assertEqual([it["action_calls"] for it in row["iterations"]], [{A: 1, B: 2}, {D: 8}])
        self.assertEqual([it["calls"] for it in row["iterations"]], [4, 4])
        self.assertEqual((row["steps"], row["planning_rounds"], row["api_calls"], row["prompt_tokens"],
                          row["completion_tokens"], row["reasoning_tokens"], row["cost_usd"]), (2, 2, 8, 88, 56, 16, .008))
        ledger = read_json(folder.parents[1] / "script.json")
        self.assertEqual((ledger["calls"], ledger["reservations"]), (8, {}))

    def test_own_rejects_agent_named_entries_and_repairs_only_the_offender(self):
        for index, (bad, status) in enumerate((([BAD], "invalid"), ([{A: RED}], "parse failure"),
                                                ([A + ": " + RED], "parse failure"))):
            spec = self.spec(TWO, "OWN", 1, history_window=0)
            # B's malformed proposal must never cause an action for A.
            replies = [[RED], bad, [GREEN_TO_D], [GREEN]]
            row, trace, _ = self.play(spec, list(map(json.dumps, replies)), str(index))
            self.assertEqual([c["speaker"] for c in trace], [A, B, B, D])
            self.assertEqual(row["iterations"][0]["action_calls"], {A: 1, B: 3})
            self.assertEqual(row["round_log"][0]["checks"][1]["status"], status)
            self.assertEqual((row["strict_success"], row["planning_rounds"], row["steps"]), (True, 2, 2))
            repair = trace[2]["messages"][-1]["content"]
            self.assertIn("Output only a list like", repair)
            self.assertIn("not in your doable action list" if status == "invalid" else "could not be read as a JSON list", repair)
            self.assertNotIn("State1:", trace[3]["messages"][1]["content"])
            cause = classify(row, trace)
            self.assertEqual((cause["repair_calls"], cause["first_plan_invalid_iterations"], cause["first_invalid_call"]), (1, 1, 2))

    def test_own_later_invalid_merged_step_drops_suffix_without_repair(self):
        idle = [None] * 3
        proposed = ([RED, RED, None], [GREEN_TO_D, None, GREEN], idle, idle, idle, idle, idle, [GREEN, None, None])
        row, trace, _ = self.play(self.spec(TWO, "OWN"), list(map(json.dumps, proposed)))
        self.assertEqual([(c["speaker"], len(c["messages"])) for c in trace], [(s, 2) for s in (A, B, C, D)] * 2)
        one, two = row["round_log"]
        self.assertEqual((one["invalid_position"], one["plans_executed"], one["stop_reason"]), (2, 1, "invalid"))
        self.assertEqual((two["first_step"], row["steps"], row["planning_rounds"], row["api_calls"]), (2, 2, 2, 8))
        self.assertEqual([it["issued_plan"] for it in row["iterations"]], [{A: RED, B: GREEN_TO_D}, {D: GREEN}])

    def test_own_first_step_repairs_both_robots_twice(self):
        row, trace, _ = self.play(self.spec(TWO, "OWN", 1, max_env_steps=1), [json.dumps([BAD])] * 6)
        self.assertEqual([c["speaker"] for c in trace], [A, B] * 3)
        batch, = row["round_log"]
        self.assertEqual((row["success_failure"], row["steps"], row["api_calls"], batch["proposed_plans"],
                          batch["own_robots_dropped"], len(batch["checks"])), (ENV_STEP_LIMIT, 1, 6, [{}], 2, 6))

    def test_one_own_robot_cut_off_after_usual_three_attempts(self):
        spec = self.spec(TWO, "OWN", 1)
        budget = Invocation(self.work, self.work / "transport.json")
        budget.create(None, 5, MODEL)
        with local_references(), scripted_transport(["ok"] + ["truncated"] * 3) as (sent, waits):
            conn = load_real_api().http.client.HTTPSConnection
            original = conn.getresponse
            def response(connection):
                packet = json.loads(original(connection).read(-1))
                if len(sent) == 1:
                    packet["choices"][0]["message"]["content"] = json.dumps([RED])
                return SimpleNamespace(status=200, read=lambda _: json.dumps(packet).encode())
            with patch.object(conn, "getresponse", response):
                run_episode(spec, self.work, budget.path, MODEL, "correct", 300, 96, 0., .7)
        folder = self.work / "episodes" / spec.name
        row, trace = read_json(folder / "episode.json"), calls(folder)
        self.assertEqual([c["speaker"] for c in trace], [A, B])
        self.assertEqual([b["temperature"] for b, _ in sent], [0., 0., .7, .7])
        self.assertEqual([b["max_tokens"] for b, _ in sent], [96] * 4)
        self.assertEqual((len(waits), row["success_failure"], row["steps"], row["planning_rounds"], row["api_calls"],
                          row["retried_calls"], row["truncated_attempts"], row["completion_tokens"]),
                         (2, OUTPUT_LIMIT, 0, 1, 4, 1, 3, 291))
        self.assertEqual((row["round_log"][0]["stop_reason"], row["finished"]), ("output limit", True))

    def test_own_partial_round_resumes_without_double_charging_or_partial_execution(self):
        spec = self.spec(TWO, "OWN", 1)
        first = Invocation(self.work, self.work / "first.json")
        first.create(1, 5, "fake")
        run_episode(spec, self.work, first.path, "fake", "correct", 300)
        path = self.work / "episodes" / spec.name / "episode.json"
        row = read_json(path)
        self.assertEqual((row["success_failure"], row["steps"], row["api_calls"], row["planning_rounds"]), (CALL_LIMIT, 0, 1, 1))
        second = Invocation(self.work, self.work / "second.json")
        second.create(None, 5, "fake")
        run_episode(spec, self.work, second.path, "fake", "correct", 300)
        row = read_json(path)
        self.assertEqual((row["strict_success"], row["api_calls"], row["planning_rounds"], row["steps"]), (True, 3, 2, 2))
        self.assertEqual((read_json(first.path)["calls"], read_json(second.path)["calls"]), (1, 2))
        capped, _, _ = self.play(spec, [json.dumps([RED])], "ceiling", ceiling=1)
        self.assertEqual((capped["success_failure"], capped["steps"], capped["api_calls"]), (CALL_CEILING, 0, 1))

    def test_cli_tools_separate_horizons_and_count_once_per_planning_round(self):
        outs = [self.work / "h1", self.work / "h3"]
        options = ("--model", "fake", "--frameworks", "CMAS,OWN", "--dropoff", "event", "--conditions", "static", "--envs", "0")
        def checked(*args):
            result = cli(*args)
            self.assertEqual(result.returncode, 0, result.stderr)
            return result
        for h, out in zip((1, 3), outs, strict=True):
            checked("run_chen2d.py", "--out", out, "--horizon", h, *options)
            rows = list(csv.DictReader((out / "episodes.csv").read_text().splitlines()))
            self.assertEqual({r["horizon"] for r in rows}, {str(h)})
            for r in rows:
                self.assertEqual(int(r["planning_rounds"]), len(read_json(out / "episodes" / r["episode_id"] / "episode.json")["round_log"]))
        summary = checked("summarize.py", *outs).stdout.splitlines()
        self.assertEqual(len(summary), 6)
        causes = list(csv.DictReader(io.StringIO(checked("failure_causes.py", *outs).stdout)))
        self.assertEqual({(r["framework"], r["horizon"], r["cause"]) for r in causes},
                         {(fw, h, "completed") for fw in ("CMAS", "OWN") for h in ("1", "3")})
        demand = checked("output_demand.py", *outs)
        rows = list(csv.DictReader(io.StringIO(demand.stdout)))
        for row in rows:
            out = outs[0] if row["horizon"] == "1" else outs[1]
            call = read_json(out / "episodes" / row["episode_id"] / "calls" / f"{int(row['call_number']):05d}.json")
            self.assertEqual(row["plan_extracted"], "True")
            self.assertEqual(int(row["plan_tokens"]), history_tokens(json.dumps(json.loads(call["response"]))))
        table = pipe_rows(demand.stderr, "Generation per planning round")
        cmas, = [r for r in table if r["framework"] == "CMAS" and r["horizon"] == "3"]
        self.assertEqual((cmas["planning_rounds"], cmas["executed_steps"], cmas["attempts"]), ("3", "9", "3"))
        self.assertIn("CMAS / OWN ratio", checked("cost.py", outs[1], "--bootstrap", 20).stdout)
        self.assertNotEqual(cli("run_chen2d.py", "--out", outs[0], "--horizon", 3, *options).returncode, 0)
        for fw, h in (("HMAS-1", 2), ("HMAS-2", 2), ("CMAS", 0)):
            self.assertNotEqual(cli("run_chen2d.py", "--out", self.work / "refused", *options,
                                    "--frameworks", fw, "--horizon", h).returncode, 0)
        manifest = outs[1] / "assignments.json"
        assigned = read_json(manifest)
        next(iter(assigned.values()))["horizon"] = 1
        write_json(manifest, assigned)
        for tool in ("cost.py", "paired.py"):
            extra = ("--noninferiority",) if tool == "paired.py" else ()
            self.assertIn("Mixed horizon", cli(tool, outs[1], *extra).stderr)


if __name__ == "__main__":
    suites = sys.argv[1:] or ["test_chen2d", *(f"test_chen2d_v{n}" for n in range(2, 12))]
    with local_references():
        print("Folder-local reference code and scripted transports. Network connections disabled.", flush=True)
        result = unittest.TextTestRunner(verbosity=2).run(unittest.defaultTestLoader.loadTestsFromNames(suites))
    sys.exit(not result.wasSuccessful())
