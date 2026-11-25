"""Offline history, failure attribution and frozen protocol regression tests."""
import csv
import io
import json
import re
import shutil
import sys
import tarfile
import tempfile
import unittest
from collections import Counter
from pathlib import Path
from regression_inputs import REGRESSION
from types import SimpleNamespace
from unittest.mock import patch

from episode import HISTORY_DEFAULTS, Spec, run_episode
from failure_causes import CAUSES, classify, move_cycle, recorded_calls
from limits import CALL_CEILING, CALL_LIMIT, MODEL_SERVICE, OUTPUT_LIMIT, Invocation
from run_chen2d import FRAMEWORKS
from storage import ROOT, code_version, digest, read_json, write_json
from test_chen2d import calls
from test_chen2d_v4 import cli
from test_chen2d_v5 import local_references

REVIEW = REGRESSION / "chen2d-9"
FROZEN = "a1831dd303c2"
AGENT = "Agent[0.5, 0.5]"
OTHER = "Agent[0.5, 1.5]"
BAD = "move(box_red, target_red)"
GOOD = "move(box_blue, target_blue)"
PLAN = json.dumps({AGENT: BAD, OTHER: GOOD})
FEEDBACK = "Your assigned task for 0.5_0.5 is not in the doable action list; Please replan for all the agents again with the same ouput format:"
FORMAT = "Your assigned plan is not in the correct json format as before. If your answer is empty dict, please check whether you miss to move box into the same colored target like move(box_blue, target_blue)"
STATE = re.compile(r"^\s*State(\d+):", re.M)
DIALOGUE = re.compile(r"^\s*Dialogue(\d+):", re.M)


def snapshot(directory):
    return {p.relative_to(directory): (p.stat().st_mtime_ns, digest(p.read_bytes()))
            for p in directory.rglob("*") if p.is_file()}


def call(number, step=1, reply="{}", *, role="central", feedback="", rejected=None,
         kinds=("ok",), prompt=100, completion=7, reasoning=2):
    messages = [dict(role="system", content="system"), dict(role="user", content="task")]
    if feedback:
        messages += [dict(role="assistant", content=rejected or PLAN), dict(role="user", content=feedback)]
    attempts = [dict(kind=k, api_calls=1, prompt_tokens=prompt, completion_tokens=completion,
                     reasoning_tokens=reasoning) for k in kinds]
    return dict(number=number, step=step, role=role, response=reply, messages=messages, attempts=attempts,
                status="ok" if reply is not None else "error", api_calls=len(attempts),
                prompt_tokens=prompt * len(attempts) if prompt is not None else None,
                completion_tokens=completion * len(attempts) if completion is not None else None,
                reasoning_tokens=reasoning * len(attempts) if reasoning is not None else None)


def iteration(step, *moves, executed=True):
    return dict(step=step, executed=executed, applied_actions=list(moves))


def outcome(label="Syntactic Error", *iterations, boxes=1, wrong=0, strict=False):
    return dict(parse="lenient", finished=True, strict_success=strict, success_failure=label,
                boxes_left=boxes, wrong_deliveries=wrong, iterations=list(iterations) or [iteration(1)])


def pipe_rows(text, section):
    body = text.split(section + "\n", 1)[1].partition("\n\n")[0].strip().splitlines()
    return [dict(zip(body[0].split(" | "), line.split(" | "), strict=True)) for line in body[1:]]


class FolderTests(unittest.TestCase):
    def setUp(self):
        temp = tempfile.TemporaryDirectory(dir=ROOT, prefix=".chen9-test-")
        self.addCleanup(temp.cleanup)
        self.work = Path(temp.name)

    def v8(self):
        fixture = REVIEW / "v8-static.tar.gz"
        self.assertEqual(digest(fixture.read_bytes()), "c37836f75bc3924d7d6e001545a9b3f8e05b972d83e9b5bb2102e5048e3ca697")
        with tarfile.open(fixture) as archive:
            archive.extractall(self.work, filter="data")
        return self.work / "v8-static"

    def run_cli(self, name, frameworks, *extra):
        out = self.work / name
        result = cli("run_chen2d.py", "--model", "fake", "--sizes", "2x2", "--envs", "0",
                     "--conditions", "static", "--dropoff", "event", "--frameworks", frameworks, "--out", out, *extra)
        self.assertEqual(result.returncode, 0, result.stderr)
        return out


class HistoryTests(FolderTests):
    def test_four_archived_v8_episodes_byte_for_byte(self):
        archive = self.v8()
        self.assertEqual(read_json(archive / "run.json")["code_version"], FROZEN)
        out = self.work / "replay"
        out.mkdir()
        config = read_json(archive / "run.json")
        for fw in FRAMEWORKS:
            with self.subTest(framework=fw):
                old = archive / "episodes" / f"2x2_{fw}_static_env0"
                row, trace = read_json(old / "episode.json"), calls(old)
                spec = Spec(2, 2, fw, "static", 0, archive / "maps/2x2/env0.json", row["env_sha256"],
                            row["event_sha256"], dropoff="event")
                budget = Invocation(out, out / (trace[0]["invocation"] + ".json"))
                budget.create(None, 2, "fake")
                clock = [v for c in trace for v in (0., c["elapsed_seconds"])]
                steps = [v for it in row["iterations"] for v in (0., it["planning_seconds"])]
                with (patch("LLM.monotonic", side_effect=clock),
                      patch("episode.time", SimpleNamespace(monotonic=iter(steps).__next__)),
                      patch("episode.code_version", return_value=FROZEN)):
                    run_episode(spec, out, budget.path, "fake", "correct", 300, config["max_output_tokens"])
                new = out / "episodes" / spec.name
                self.assertEqual({k: sha for k, (_, sha) in snapshot(new).items()},
                                 {k: sha for k, (_, sha) in snapshot(old).items()})
        self.assertNotEqual(code_version(), FROZEN)

    def test_zero_none_dialogue_and_larger_windows_at_every_planner(self):
        framework_list = ",".join(FRAMEWORKS)
        def prompts(name, *opts):
            out = self.run_cli(name, framework_list, *opts)
            result = {}
            for fw in FRAMEWORKS:
                folder = out / "episodes" / f"2x2_{fw}_static_env0"
                for c in calls(folder):
                    if c["step"] == 9:
                        result.setdefault((fw, c["role"]), c["messages"][1]["content"])
            return result

        zero = prompts("zero", "--history-window", "0", "--history-method", "dialogue", "--cmas-history", "on")
        none = prompts("none", "--history-window", "12000", "--history-method", "none", "--cmas-history", "on")
        small = prompts("small", "--history-window", "1000", "--cmas-history", "on")
        large = prompts("large", "--history-window", "12000", "--cmas-history", "on")
        dialogue = prompts("dialogue", "--history-window", "12000", "--history-method", "dialogue", "--cmas-history", "on")
        default = prompts("default")
        self.assertEqual(zero, none)  # Same authors' no-history template, including current-round dialogue.
        self.assertEqual(set(large), {("CMAS", "central"), ("DMAS", "dialogue"), ("HMAS-1", "dialogue"),
                                      ("HMAS-1", "central"), ("HMAS-2", "central"), ("HMAS-2", "review")})
        for key, text in large.items():
            with self.subTest(planner=key):
                self.assertEqual(STATE.findall(zero[key]), [])
                self.assertEqual(STATE.findall(text), list(map(str, range(1, 9))))
                small_steps = STATE.findall(small[key])
                self.assertLess(len(small_steps), 8)
                self.assertEqual(small_steps, list(map(str, range(9 - len(small_steps), 9))))
                self.assertEqual(DIALOGUE.findall(text), [])
                if key[0] == "CMAS":
                    self.assertEqual(STATE.findall(default[key]), [])
                    self.assertEqual(text, dialogue[key])
                else:
                    self.assertEqual(DIALOGUE.findall(dialogue[key]), list(map(str, range(1, 9))))
                    self.assertIn("State8:", default[key])
        self.assertIn("The previous dialogue history is:", none["DMAS", "dialogue"])
        out = self.work / "default"
        self.assertEqual({k: read_json(out / "run.json")[k] for k in HISTORY_DEFAULTS}, HISTORY_DEFAULTS)
        self.assertNotIn("history_window", read_json(out / "episodes/2x2_DMAS_static_env0/episode.json"))
        with (out / "episodes.csv").open() as stream:
            self.assertEqual({r["history_window"] for r in csv.DictReader(stream)}, {"3000"})

    def test_settings_guard_resume_summary_and_single_run_readers(self):
        out = self.run_cli("new", "CMAS", "--history-window", "1000", "--history-method", "dialogue", "--cmas-history", "on")
        other = self.run_cli("old", "CMAS")
        summary = cli("summarize.py", out)
        self.assertEqual(summary.returncode, 0, summary.stderr)
        for setting in ("history_window 1000", "history_method dialogue", "cmas_history on"):
            self.assertIn(setting, summary.stdout)
        self.assertIn("different history settings", cli("summarize.py", out, other).stderr)
        resp = cli("run_chen2d.py", "--model", "fake", "--sizes", "2x2", "--envs", "0", "--frameworks", "CMAS",
                   "--conditions", "static", "--dropoff", "event", "--out", out)
        self.assertNotEqual(resp.returncode, 0)
        self.assertIn("Run settings", resp.stderr)
        bad = cli("run_chen2d.py", "--model", "fake", "--history-window", "-1", "--out", self.work / "bad")
        self.assertNotEqual(bad.returncode, 0)
        p = out / "episodes/2x2_CMAS_static_env0/episode.json"
        row = read_json(p)
        self.assertEqual(row["code_version"], code_version())
        write_json(p, dict(row, history_window=3000))
        for tool in ("summarize.py", "failure_causes.py", "cost.py"):
            self.assertIn("Mixed history settings", cli(tool, out).stderr)


A, B = [.5, .5], [.5, 1.5]
FORWARD, BACK = (A, "box_red", B), (B, "box_red", A)


class RulesTests(unittest.TestCase):
    def test_label_precedence_recovered_mixed_and_terminal_truncations(self):
        cuts = [call(1, reply=None, kinds=("truncated", "truncated")), call(2, role="relay")]
        self.assertEqual(classify(outcome(OUTPUT_LIMIT, strict=True, boxes=0), cuts)["cause"], "completed")
        self.assertEqual(classify(outcome(OUTPUT_LIMIT), [])["cause"], "output_limit")
        self.assertEqual(classify(outcome(CALL_CEILING), cuts)["cause"], "output_limit")
        self.assertEqual(classify(outcome(MODEL_SERVICE), [call(1, reply=None, kinds=("http_5xx", "truncated"))])["cause"], "other")
        self.assertEqual(classify(outcome("Hallucination of wrong plan"), [])["cause"], "other")
        self.assertEqual(classify(outcome(MODEL_SERVICE), [call(1, reply=None, kinds=())])["cause"], "other")
        recovered = [call(1, kinds=("truncated", "ok")), call(2, role="relay", reply=None, kinds=("truncated",))]
        row = classify(outcome("success", boxes=0, wrong=1), recovered)
        self.assertEqual((row["cause"], row["cutoff_calls"], row["cutoff_attempts"], row["all_cutoff_calls"]),
                         ("wrong_delivery", 1, 1, 2))

    def test_repair_last_iteration_repeat_after_feedback_and_delivery_only(self):
        repaired = [call(1, reply=PLAN), call(2, feedback=FEEDBACK, reply=json.dumps({OTHER: GOOD}))]
        r = classify(outcome(), repaired)
        self.assertEqual((r["cause"], r["last_iteration_repair"], r["repeated_invalid_action"]), ("context", True, False))
        self.assertEqual(classify(outcome(MODEL_SERVICE), repaired)["cause"], "other")
        self.assertEqual(classify(outcome(CALL_LIMIT), repaired)["cause"], "other")
        earlier = outcome("failure over query time limit", iteration(1), iteration(2))
        self.assertEqual(classify(earlier, repaired + [call(3, 2)])["cause"], "other")
        recurrent = [call(1, reply=PLAN), call(2, feedback=FEEDBACK, reply="EXECUTE\n" + PLAN), call(3, 2)]
        r = classify(earlier, recurrent)
        self.assertEqual((r["cause"], r["last_iteration_repair"], r["repeated_invalid_action"]), ("context", False, True))
        # The action can become legal on a new board; require another rejection there.
        later = repaired + [call(3, 2, reply=PLAN)]
        self.assertFalse(classify(earlier, later)["repeated_invalid_action"])
        self.assertTrue(classify(earlier, [*later, call(4, 2, feedback=FEEDBACK)])["repeated_invalid_action"])
        json_repair = [call(1, reply="EXECUTE\nbad JSON", role="dialogue"),
                       call(2, feedback=FORMAT, rejected="bad JSON", role="dialogue")]
        self.assertEqual(classify(outcome(CALL_CEILING), json_repair)["cause"], "context")
        self.assertEqual(classify(outcome("success", boxes=0, wrong=1), repaired)["cause"], "other")
        self.assertEqual(classify(outcome("success", boxes=0, wrong=2), [])["cause"], "wrong_delivery")
        self.assertEqual(classify(outcome("success", boxes=2, wrong=0), repaired)["cause"], "context")

    def test_executed_period_one_and_two_cycles_and_counterexamples(self):
        shuttle = [iteration(i, move) for i, move in enumerate((FORWARD, BACK, FORWARD, BACK), 1)]
        joint = [iteration(i, FORWARD, BACK) for i in range(1, 5)]
        for pattern in (shuttle, joint):
            r = classify(outcome("failure over query time limit", *pattern, iteration(5)), [])
            self.assertEqual((r["cause"], r["move_cycle"], r["last_iteration_repair"]), ("context", True, False))
        for sample in (shuttle[:3], [*shuttle[:2], iteration(3, executed=False), *shuttle[2:]],
                       [iteration(i, FORWARD) for i in range(1, 5)],
                       [iteration(i, (A, "box_red", "target_red")) for i in range(1, 5)],
                       [iteration(i) for i in range(1, 5)],
                       [dict(it, applied_box_ids=[i]) for i, it in enumerate(shuttle)]):
            self.assertFalse(move_cycle(sample))
        self.assertTrue(move_cycle([dict(it, applied_box_ids=[1]) for it in shuttle]))

    def test_saved_state_checks_a_plan_even_when_ceiling_prevented_feedback(self):
        board = {"0.5_0.5": [], "0.5_1.5": ["box_blue", "target_blue"]}
        early_stop = outcome(CALL_CEILING, iteration(1, executed=False))
        r = classify(early_stop, [call(1, reply=PLAN, prompt=321)], {1: board})
        self.assertEqual((r["first_plan_invalid_share"], r["prompt_tokens_at_first_invalid"], r["repair_calls"]),
                         (1, 321, 0))
        self.assertEqual((r["cause"], r["proposals_with_saved_state"]), ("other", 1))
        trace = [call(1, reply=PLAN), call(2, feedback=FEEDBACK), call(3, 2, reply=PLAN)]
        ended = outcome(CALL_CEILING, iteration(1), iteration(2, executed=False))
        r = classify(ended, trace, {1: board, 2: board})
        self.assertEqual((r["cause"], r["repeated_invalid_action"], r["last_iteration_repair"]), ("context", True, False))
        fixed = dict(board, **{"0.5_0.5": ["box_red", "target_red"]})
        self.assertEqual(classify(ended, trace, {1: board, 2: fixed})["cause"], "other")

    def test_distinct_first_proposals_denominators_and_single_attempt_prompt_lengths(self):
        # Step 1 has a valid central proposal followed by a rejected local proposal.
        # Step 9 starts with a rejected plan. The echoed feedback is historical text.
        trace = [call(1, reply="{}", kinds=("truncated", "ok"), prompt=10), call(2, reply="EXECUTE\n" + PLAN, role="dialogue", prompt=20),
                 call(3, role="dialogue", feedback=FEEDBACK, reply="broken", prompt=30),
                 call(4, role="dialogue", feedback=FORMAT, rejected="broken", prompt=None, reasoning=None),
                 call(5, 2, reply="PROCEED", role="dialogue", prompt=40),
                 call(6, 9, reply=PLAN, prompt=50), call(7, 9, feedback=FEEDBACK, prompt=60),
                 call(8, 9, role="review", prompt=5000, reply="I Agree"), call(9, 9, role="relay", prompt=7000)]
        trace[4]["messages"][1]["content"] += "\n" + FEEDBACK
        r = classify(outcome(CALL_CEILING, *(iteration(i) for i in (1, 2, 9))), trace)
        self.assertEqual((r["cause"], r["repair_calls"], r["repair_iterations"], r["iterations_with_proposal"]),
                         ("context", 3, 2, 2))
        self.assertEqual((r["first_plan_invalid_share"], r["early_invalid"], r["late_invalid"]), (1/3, 0, 1))
        self.assertEqual((r["first_invalid_call"], r["prompt_tokens_at_first_invalid"]), (2, 20))
        self.assertEqual((r["planning_calls"], r["plan_making_calls"], r["mean_prompt_tokens"], r["max_prompt_tokens"]),
                         (8, 7, 35, 60))
        self.assertEqual(r["plan_call_tokens"][0], dict(number=1, step=1, prompt_tokens=10, completion_tokens=14, reasoning_tokens=4))
        self.assertIsNone(r["plan_call_tokens"][3]["reasoning_tokens"])
        self.assertEqual((r["mean_completion_tokens"], r["mean_reasoning_tokens"]), (8, 14/6))
        empty = classify(outcome(MODEL_SERVICE, iteration(1, executed=False)), [])
        self.assertIsNone(empty["mean_prompt_tokens"])
        self.assertIsNone(empty["prompt_tokens_at_first_invalid"])
        self.assertIsNone(empty["cutoff_call_share"])


class AnalysisTests(FolderTests):
    def test_read_only_cli_on_copied_v6_v7_v8_runs(self):
        v6 = self.work / "v6"
        v7 = self.work / "v7"
        shutil.copytree(REGRESSION / "chen2d-6/smoke", v6)
        shutil.copytree(REGRESSION / "chen2d-8/v7-auto", v7)
        v8 = self.v8()
        before = [snapshot(p) for p in (v6, v7, v8)]
        result = cli("failure_causes.py", v6, v7, v8)
        self.assertEqual(result.returncode, 0, result.stderr)
        table = list(csv.DictReader(io.StringIO(result.stdout)))
        self.assertEqual(Counter(r["code_version"] for r in table), {"70c073dc2208": 16, "5a5ab0e063c9": 1, FROZEN: 4})
        self.assertEqual({r["cause"] for r in table if r["code_version"] == FROZEN}, {"completed"})
        self.assertEqual(Counter(r["cause"] for r in table if r["code_version"] == "70c073dc2208"), {"completed": 12, "wrong_delivery": 4})
        self.assertEqual({r["cmas_history"] for r in table}, {"off"})
        self.assertIn("who is ahead", result.stderr)
        self.assertNotEqual(cli("failure_causes.py", v6, "--csv", v6 / "episodes.csv").returncode, 0)
        self.assertNotEqual(cli("failure_causes.py", v6, v6).returncode, 0)
        self.assertEqual(before, [snapshot(p) for p in (v6, v7, v8)])

    def test_cli_constructed_runs_all_causes_mixed_settings_and_rank_flips(self):
        archive = self.v8()
        template = read_json(archive / "episodes/2x2_CMAS_static_env0/episode.json")
        def write_run(tag, limit, window, flag, subjects):
            p = self.work / tag
            p.mkdir()
            config = dict(read_json(archive / "run.json"), max_output_tokens=limit, history_window=window,
                          history_method="authors", cmas_history=flag)
            write_json(p / "run.json", config)
            for n, (fw, row, trace) in enumerate(subjects):
                name = f"2x2_{fw}_static_env{n}"
                folder = p / "episodes" / name
                (folder / "calls").mkdir(parents=True)
                full = dict(template, episode_id=name, env_seed=n, framework=fw, max_output_tokens=limit,
                            history_window=window, history_method="authors", cmas_history=flag)
                full.update(row, api_calls=sum(c["api_calls"] for c in trace))
                write_json(folder / "episode.json", full)
                for c in trace:
                    write_json(folder / "calls" / f"{c['number']:05d}.json", c)
            return p

        ok = ("CMAS", outcome("success", boxes=0, strict=True), [call(1, prompt=20)])
        wrong = ("DMAS", outcome("success", boxes=0, wrong=1), [call(1, prompt=100)])
        repairs = [call(1, 9, reply=PLAN, prompt=30), call(2, 9, feedback=FEEDBACK, reply=PLAN, prompt=50)]
        ctx = ("DMAS", outcome(CALL_CEILING, iteration(9, executed=False)), repairs)
        cycle = ("DMAS", outcome("failure over query time limit", *(iteration(i, move) for i, move in
                 enumerate((FORWARD, BACK, FORWARD, BACK), 1))), [])
        cutoff = ("CMAS", outcome(CALL_CEILING), [call(1, reply=None, kinds=("truncated", "truncated"))])
        other = ("CMAS", outcome(MODEL_SERVICE), [])
        a = write_run("low", 1024, 3000, "off", [ok, wrong, ctx, cycle, cutoff, other])
        b = write_run("high", 8192, 3000, "off", [("CMAS", *wrong[1:]), ("DMAS", *ok[1:])])
        c = write_run("long", 8192, 12000, "off", [("DMAS", *ok[1:])])
        d = write_run("leader", 8192, 12000, "on", [ok])
        dest = self.work / "results.csv"
        result = cli("failure_causes.py", a, b, c, d, "--episodes-csv", dest)
        self.assertEqual(result.returncode, 0, result.stderr)
        with dest.open() as f:
            rows = list(csv.DictReader(f))
        self.assertEqual({r["cause"] for r in rows}, set(CAUSES))
        summary = pipe_rows(result.stdout, "failure causes")
        low = next(r for r in summary if r["max_output_tokens"] == "1024" and r["framework"] == "DMAS")
        self.assertEqual([low[k] for k in ("context", "last_iteration_repair", "repeated_invalid_action", "move_cycle")],
                         ["66.67% (2/3)", "33.33% (1/3)", "33.33% (1/3)", "33.33% (1/3)"])
        self.assertEqual((low["first_plan_invalid_late"], low["mean_prompt_late"]), ("100.00% (1/1)", "40.00"))
        ranks = pipe_rows(result.stdout, "who is ahead")
        self.assertEqual([r["ahead"] for r in ranks], ["CMAS", "DMAS", "NA", "tie"])
        self.assertEqual((ranks[-1]["cmas_history"], ranks[-1]["DMAS_cmas_history"]), ("on", "off"))

    def test_published_prefix_during_resume_and_missing_call_detection(self):
        folder = self.work / "episodes/test/calls"
        folder.mkdir(parents=True)
        first = call(1, kinds=("truncated", "ok"))
        write_json(folder / "00001.json", first)
        write_json(folder / "00002.json", call(2))
        row = dict(episode_id="test", finished=False, api_calls=1)
        prefix = recorded_calls(self.work, row)
        self.assertEqual(len(prefix), 1)
        self.assertEqual([a["kind"] for a in prefix[0]["attempts"]], ["truncated"])
        self.assertIsNone(prefix[0]["response"])
        self.assertEqual(prefix[0]["completion_tokens"], 7)
        with self.assertRaisesRegex(ValueError, "disagrees"):
            recorded_calls(self.work, dict(row, finished=True))
        with self.assertRaisesRegex(ValueError, "Missing"):
            recorded_calls(self.work, dict(row, api_calls=4))


if __name__ == "__main__":
    suites = sys.argv[1:] or ["test_chen2d", *(f"test_chen2d_v{n}" for n in range(2, 10))]
    with local_references():
        print("Folder-local reference hashes verified. Network connections disabled.", flush=True)
        result = unittest.TextTestRunner(verbosity=2).run(unittest.defaultTestLoader.loadTestsFromNames(suites))
    sys.exit(not result.wasSuccessful())
