"""Offline end-to-end, reference-parity and scripted transport tests."""
import contextlib
import csv
import io
import json
import random
import subprocess
import sys
import tempfile
import types
import unittest
import warnings
from collections import Counter
from decimal import Decimal
from pathlib import Path
from unittest.mock import patch

import fake_model
from LLM import CallSession, MAX_OUTPUT_TOKENS, MODEL, load_real_api, wire_prompt
from env1_create import action_from_response, saved_env, with_action_syntactic_check_func
from episode import Spec, run_episode
from map_events import boxes, cell_key, event_path, map_assignment
from plan_parse import PlanParser
from limits import CALL_CEILING, CALL_LIMIT, CLIENT_LIMIT, COST_LIMIT, Invocation, StopEpisode
from prompt_env1 import history_tokens
from run_chen2d import FRAMEWORKS
from storage import ROOT, digest, read_json, write_json

SOURCE = ROOT / "fixtures" / "upstream"


def calls(folder):
    return [read_json(p) for p in sorted((folder / "calls").glob("[0-9]*.json"))]


def reference_episode(work, state, framework):
    """Use read-only upstream functions. Omit only the two destructive module-level drivers."""
    trace = []
    def gpt(messages, _model):
        answer = fake_model.reply(messages, "correct")
        trace.append((messages, answer))
        return answer, 18

    upstream_llm = types.ModuleType("LLM")
    upstream_llm.GPT_response = gpt
    prompt, env = types.ModuleType("prompt_env1"), types.ModuleType("env1_create")
    prompt.enc = types.SimpleNamespace(encode=lambda s: range(history_tokens(s)))
    prompt.GPT_response = gpt
    # Only tiktoken initialization is substituted in the reference prompts.
    src = (SOURCE / "prompt_env1.py").read_text()
    exec(src[src.index("input_prompt_token_limit"):], prompt.__dict__)
    modules = {"prompt_env1": prompt, "env1_create": env, "LLM": upstream_llm}
    dest = work / "env_pg_state_2_2/pg_state0"
    dest.mkdir(parents=True, exist_ok=True)
    write_json(dest / "pg_state0.json", state)
    with patch.dict(sys.modules, modules), warnings.catch_warnings(), contextlib.redirect_stdout(io.StringIO()):
        warnings.simplefilter("ignore", DeprecationWarning)
        exec((SOURCE / "env1_create.py").read_text().split("\nCode_dir_path = ")[0], env.__dict__)
        driver = {}
        exec((SOURCE / "env1-box-arrange.py").read_text().split("\nCode_dir_path = ")[0], driver)
        result = driver["run_exp"](str(work), 2, 2, 0, 30, "_w_only_state_action_history", framework, "fake")
        random.seed(0)
        generated = env.env_create(2, 2, 1, 3)
    return trace, result, generated


def fixture_spec(path, state, condition, rows=2, cols=2, dropoff="event", **options):
    write_json(path, state)
    sha = digest(path.read_bytes())
    sidecar = event_path(path)
    write_json(sidecar, map_assignment(state, 0, sha, rows, cols, action_from_response))
    return Spec(rows, cols, "CMAS", condition, 0, path, sha, digest(sidecar.read_bytes()), dropoff=dropoff, **options)


class ChenTests(unittest.TestCase):
    def setUp(self):
        temp = tempfile.TemporaryDirectory(dir=ROOT, prefix=".chen-test-")
        self.addCleanup(temp.cleanup)
        self.work = Path(temp.name)

    def cli(self, name, *options):
        out = self.work / name
        cmd = [sys.executable, "-B", str(ROOT / "run_chen2d.py"), "--out", str(out),
               "--model", "fake", "--sizes", "2x2", "--frameworks", "CMAS", "--conditions", "e1", "--parse", "strict",
               "--envs", "0", "--dropoff", "event", *options]
        subprocess.run(cmd, cwd=ROOT, capture_output=True, text=True, check=True)
        return out

    def episode(self, out, framework="CMAS", condition="e1", size="2x2", seed=0):
        suffix = condition if condition == "static" else f"{condition}_all"
        directory = out / "episodes" / f"{size}_{framework}_{suffix}_env{seed}"
        return directory, read_json(directory / "episode.json")

    def test_all_frameworks_match_upstream_static_and_event_pairing(self):
        out = self.cli("pair", "--frameworks", ",".join(FRAMEWORKS), "--conditions", "static,e1",
                       "--jobs", "4")
        frozen, sha = saved_env(2, 2, 0)
        seed_state = read_json(frozen)
        events = []
        for framework in FRAMEWORKS:
            with self.subTest(framework=framework):
                static, result = self.episode(out, framework, "static")
                self.assertEqual(result["success_failure"], "success")
                self.assertTrue(result["strict_success"])
                original_trace, original, generated = reference_episode(self.work / "authors", seed_state, framework)
                recorded = calls(static)
                self.assertEqual(generated, seed_state)
                self.assertEqual(original_trace, [(r["messages"], r["response"]) for r in recorded])
                self.assertEqual((original[3], original[4] + 1, sum(original[5])),
                                 (result["success_failure"], result["steps"], result["tokens"]))
                self.assertEqual([json.loads(s) for s in original[1]],
                                 [it["issued_plan"] for it in result["iterations"]])
                self.assertEqual(original[2], [read_json(static / "pg_state" / f"pg_state{n+1}.json")
                                                for n in range(len(original[2]))])
                changed, result2 = self.episode(out, framework)
                log = calls(changed)
                self.assertEqual([r["messages"] for r in recorded if r["step"] == 1],
                                 [r["messages"] for r in log if r["step"] == 1])
                self.assertEqual((result["env_sha256"], result2["env_sha256"]), (sha, sha))
                for folder in (static, changed):
                    self.assertEqual(read_json(folder / "pg_state/pg_state1.json"), seed_state)
                self.assertEqual(result2["success_failure"], "success")
                self.assertTrue(result2["strict_success"])
                self.assertEqual(result2["wrong_deliveries"], 0)
                self.assertEqual(result2["correct_deliveries"], boxes(seed_state).total())
                assignment = read_json(event_path(frozen))
                event = result2["event"]
                events.append(event)
                k = assignment["event_step"]
                self.assertEqual(event["step"], k)
                self.assertEqual(read_json(changed / "pg_state" / f"pg_state{k + 1}.json"), event["state_after"])
                self.assertEqual(event["box_A_left"], boxes(event["state_before"])[assignment["A"]])
                self.assertEqual(result2["event_nothing_to_change"], event["box_A_left"] == 0)
                self.assertEqual((event["A"], event["D"]), (assignment["A"], assignment["D"]))
                d = cell_key(event["D"])
                self.assertNotIn("target_" + event["A"], seed_state[d])
                self.assertIn("dropoff_" + event["A"], result2["final_state"][d])
                self.assertEqual([r["messages"] for r in recorded if r["step"] <= k],
                                 [r["messages"] for r in log if r["step"] <= k])
                for r in log:
                    q = r["messages"][1]["content"]
                    marker = "Hence, the current state" if "You are a central planner" in q else "The current state and possible actions of yourself"
                    self.assertEqual(q.count(event["announcement"]), int(r["step"] > k))
                    if r["step"] > k:
                        self.assertIn(event["announcement"] + "\n" + marker, q)
                post = [r for r in log if r["step"] == k + 1]
                self.assertEqual(result2["post_event_calls"], len(post))
                self.assertEqual(result2["post_event_rounds"], 0 if framework == "CMAS" else 1)
                self.assertGreater(result2["post_event_planning_seconds"], 0)
                drops = [it["step"] for it in result2["iterations"]
                         if any(a[2] == "dropoff_" + event["A"] for a in it["applied_actions"])]
                self.assertEqual(result2["steps_to_last_dropoff"], max(drops) - k if drops else None)
        self.assertTrue(all(e == events[0] for e in events))

    def test_wrong_is_irreversible_and_excluded_from_strict_success(self):
        folder, result = self.episode(self.cli("wrong", "--fake-script", "wrong", "--event-step", "1"))
        colour = result["A"]
        self.assertEqual((result["success"], result["strict_success"], result["boxes_left"]), (True, False, 0))
        wrong_steps = [it for it in result["iterations"] if it.get("plan_wrong")]
        self.assertTrue(wrong_steps)
        self.assertEqual(result["first_plan_after_event_wrong"], wrong_steps[0]["step"] == 2)
        self.assertEqual(result["wrong_deliveries"], result["box_A_left_at_event"])
        self.assertIsNone(result["steps_to_last_dropoff"])
        it = wrong_steps[0]
        before = read_json(folder / "pg_state" / f"pg_state{it['step']}.json")
        after = read_json(folder / "pg_state" / f"pg_state{it['step']+1}.json")
        removed = sum(a[2] == "target_" + colour for a in it["applied_actions"])
        self.assertGreater(removed, 0)
        for item in ("target_" + colour, "box_" + colour):
            count = lambda state: sum(v.count(item) for v in state.values())
            self.assertEqual(count(before) - count(after), removed)
        self.assertEqual(result["correct_deliveries"] + result["wrong_deliveries"],
                         boxes(read_json(folder / "pg_state/pg_state1.json")).total())

    def test_six_syntax_reprompts_and_missing_braces(self):
        folder, result = self.episode(self.cli("syntax", "--fake-script", "invalid"))
        self.assertEqual((result["success_failure"], result["api_calls"], result["steps"]), ("Syntactic Error", 7, 0))
        self.assertEqual([len(r["messages"]) for r in calls(folder)], [2, 4, 6, 8, 10, 12, 14])
        _, result = self.episode(self.cli("nonjson", "--fake-script", "non-json"))
        self.assertEqual((result["success_failure"], result["api_calls"]), ("Hallucination of wrong plan", 1))
        with self.assertRaisesRegex(Exception, "wrong json format"):
            with_action_syntactic_check_func({}, "{bad}", [], [], "fake", "_w_all_dialogue_history", "CMAS", parser=PlanParser("strict"))

    def test_change_reaches_syntax_and_hmas_feedback_reprompts(self):
        for script, framework in (("repair", "DMAS"), ("feedback", "HMAS-2")):
            with self.subTest(script=script):
                folder, r = self.episode(self.cli(script, "--frameworks", framework, "--fake-script", script), framework)
                self.assertTrue(r["strict_success"])
                step = [c for c in calls(folder) if c["step"] == r["event_step"] + 1]
                reviews = [c for c in step if len(c["messages"]) > 2]
                self.assertTrue(reviews)
                self.assertTrue(all(c["messages"][1]["content"].count(r["event"]["announcement"]) == 1
                                    for c in step))
                self.assertEqual(r["post_event_rounds"], 1)
                if script == "feedback":
                    self.assertEqual(len(reviews), 1)
                    self.assertIn("I Agree.", reviews[0]["messages"][-1]["content"])
                    self.assertEqual(step[-1], reviews[0])

    def test_endless_dmas_and_episode_ceiling(self):
        _, cap = self.episode(self.cli("ceiling", "--frameworks", "DMAS", "--fake-script", "endless",
                                        "--event-step", "1", "--episode-call-ceiling", "17"), "DMAS")
        self.assertEqual((cap["success_failure"], cap["api_calls"], cap["call_ceiling"], cap["steps"]),
                         (CALL_CEILING, 17, True, 1))
        self.assertEqual(cap["iterations"][0]["issued_plan"], {})
        self.assertEqual((cap["post_event_calls"], cap["first_plan_after_event_wrong"]), (1, None))
        _, endless = self.episode(self.cli("endless", "--frameworks", "DMAS", "--fake-script", "endless",
                                           "--episode-call-ceiling", "500"), "DMAS")
        self.assertEqual((endless["success_failure"], endless["steps"], endless["api_calls"]),
                         ("failure over query time limit", 30, 480))
        self.assertTrue(all((it["rounds"], it["calls"], it["issued_plan"]) == (4, 16, {})
                            for it in endless["iterations"]))

    def test_global_guards_and_resume_without_rebilling(self):
        for flag, limit, label in (("--max-cost-usd", "0.003", COST_LIMIT), ("--max-calls", "3", CALL_LIMIT)):
            with self.subTest(flag=flag):
                name = flag[2:]
                out = self.cli(name, flag, limit, "--event-step", "1", "--envs", "0,1")
                folder, paused = self.episode(out)
                self.assertEqual((paused["success_failure"], paused["api_calls"], paused["finished"]), (label, 3, False))
                self.assertEqual(len(list((out / "episodes").iterdir())), 1)
                prefix = {p: p.read_bytes() for p in (folder / "calls").glob("[0-9]*.json")}
                self.cli(name, "--event-step", "1", "--envs", "0,1", "--jobs", "2")
                _, done = self.episode(out)
                self.assertTrue(done["strict_success"])
                self.assertTrue(all(p.read_bytes() == data for p, data in prefix.items()))
                self.assertEqual(len(calls(folder)), done["api_calls"])
                self.assertLessEqual(paused["post_event_planning_seconds"], done["post_event_planning_seconds"])
                old = (folder / "episode.json").stat().st_mtime_ns
                self.cli(name, "--event-step", "1", "--envs", "0,1")
                self.assertEqual(old, (folder / "episode.json").stat().st_mtime_ns)
                with (out / "episodes.csv").open() as f:
                    rows = list(csv.DictReader(f))
                self.assertEqual(len(rows), 2)
                inv = [read_json(p) for p in (out / "invocations").glob("*.json")]
                self.assertEqual(sum(int(r["api_calls"]) for r in rows), sum(s["calls"] for s in inv))
                self.assertEqual(min(s["calls"] for s in inv), 0)

    def test_shared_caps_across_processes(self):
        out = self.cli("parallel", "--jobs", "6", "--envs", "0,1,2", "--frameworks", "DMAS,HMAS-2",
                       "--conditions", "static,e1", "--max-calls", "5", "--max-cost-usd", "0.004")
        invocation = read_json(next((out / "invocations").glob("*.json")))
        self.assertEqual(invocation["calls"], 4)
        self.assertEqual(Decimal(invocation["reported_cost_usd"]), Decimal("0.004"))
        episodes = [read_json(p) for p in (out / "episodes").glob("*/episode.json")]
        self.assertEqual(sum(r["api_calls"] for r in episodes), 4)
        empty = self.cli("zero", "--max-calls", "0")
        self.assertFalse(list((empty / "episodes").glob("*/episode.json")))

    def test_all_sizes_and_environment_integrity(self):
        out = self.cli("sizes", "--sizes", "2x2,2x4,4x4,4x8", "--frameworks", "HMAS-1", "--jobs", "4")
        for path in (out / "episodes").glob("*/episode.json"):
            self.assertTrue(read_json(path)["strict_success"])
        self.assertEqual(len(list((out / "episodes").glob("*/episode.json"))), 4)
        env = self.work / "envs"
        path, sha = saved_env(2, 4, 2, env)
        timestamp = path.stat().st_mtime_ns
        self.assertEqual(saved_env(2, 4, 2, env), (path, sha))
        self.assertEqual(timestamp, path.stat().st_mtime_ns)
        for seed in range(3):
            path, _ = saved_env(4, 8, seed, env)
            state = read_json(path)
            cnt = boxes(state)
            self.assertEqual(len(state), 32)
            self.assertEqual(len(cnt), 5)
            self.assertTrue(all(1 <= x <= 3 for x in cnt.values()))
            self.assertEqual(cnt, Counter(i[7:] for v in state.values() for i in v if i.startswith("target_")))
        path.write_text("{}")
        with self.assertRaisesRegex(ValueError, "Missing or modified"):
            saved_env(4, 8, 2, env)
        path.unlink()
        with self.assertRaisesRegex(ValueError, "Missing or modified"):
            saved_env(4, 8, 2, env)

    def test_no_remaining_box_event_and_persistent_dropoff(self):
        state = {"0.5_0.5": ["box_blue", "target_blue"], "0.5_1.5": [], "1.5_0.5": [], "1.5_1.5": []}
        path = self.work / "fixture.json"
        write_json(path, state)
        spec = fixture_spec(path, state, "e1", event_step_override=1)
        budget = Invocation(self.work, self.work / "budget.json")
        budget.create(None, 1, "fake")
        run_episode(spec, self.work, budget.path, "fake", "correct", 300)
        _, r = self.episode(self.work)
        self.assertTrue(r["strict_success"])
        self.assertTrue(r["event_fired"] and r["event_nothing_to_change"])
        self.assertIsNone(r["first_plan_after_event_towards_dropoff"])
        self.assertIsNone(r["steps_to_last_dropoff"])
        e = r["event"]
        d = cell_key(e["D"])
        after = e["state_after"]
        after[d] += ["box_blue", "box_blue"]
        agent = "Agent" + str(e["D"])
        for _ in range(2):
            action = {agent: "move(box_blue, dropoff_blue)"}
            self.assertEqual(with_action_syntactic_check_func(after, json.dumps(action), [], [], "fake",
                                                              "_w_all_dialogue_history", "CMAS")[0], json.dumps(action))
            feedback, after = action_from_response(after, action)
            self.assertEqual(feedback, "")
            self.assertIn("dropoff_blue", after[d])

    def test_history_counter_and_summary_denominators(self):
        self.assertEqual([history_tokens(s) for s in ("", "abcd", "abcde", "한글")], [0, 1, 2, 2])
        out = self.cli("summary", "--conditions", "static,e1", "--fake-script", "wrong", "--event-step", "9")
        text = subprocess.check_output([sys.executable, "-B", "summarize.py", str(out)], cwd=ROOT, text=True)
        self.assertIn("100.0% (1/1)", text)
        self.assertIn("0.0% (0/1)", text)
        self.assertIn("[1 NA]", text)
        out = self.cli("failure", "--fake-script", "non-json")
        text = subprocess.check_output([sys.executable, "-B", "summarize.py", str(out)], cwd=ROOT, text=True)
        self.assertIn("Hallucination of wrong plan (1)", text)

    def test_last_allowed_step_code_label_for_both_limits(self):
        for rows, cols, limit in ((2, 2, 30), (4, 8, 40)):
            with self.subTest(size=(rows, cols)):
                work = self.work / f"{rows}x{cols}"
                work.mkdir()
                path = work / "fixture.json"
                state = {f"{i+.5}_{j+.5}": [] for i in range(rows) for j in range(cols)}
                state["0.5_0.5"] = ["box_blue", "target_blue"]
                write_json(path, state)
                spec = fixture_spec(path, state, "static", rows=rows, cols=cols)
                budget = Invocation(work, work / "budget.json")
                budget.create(None, 1, "fake")
                scripted = ["{}"] * (limit - 1) + ['{"Agent[0.5, 0.5]":"move(box_blue, target_blue)"}']
                with patch.object(fake_model, "reply", side_effect=scripted):
                    run_episode(spec, work, budget.path, "fake", "correct", 300)
                r = read_json(work / "episodes" / spec.name / "episode.json")
                self.assertEqual((r["success_failure"], r["steps"], r["strict_success"]),
                                 ("failure over query time limit", limit, True))

    def test_real_client_bridge_with_scripted_transport_and_ledger(self):
        # Never open a socket or read a credential. Exercise the actual request builder and file ledger.
        api = load_real_api()
        sent = []
        class ScriptedConnection:
            def __init__(self, *args, **kwargs):
                pass

            def request(self, method, path, body, headers):
                sent.append(json.loads(body))

            def getresponse(self):
                payload = {"choices": [{"message": {"content": f"answer {len(sent)}"}, "finish_reason": "stop"}],
                           "usage": {"prompt_tokens": 101, "completion_tokens": 37,
                                     "completion_tokens_details": {"reasoning_tokens": 19}, "cost": 0.000005}}
                return types.SimpleNamespace(status=200, read=lambda _limit: json.dumps(payload).encode())

            def close(self):
                pass

        budget = Invocation(self.work, self.work / "invocation.json")
        budget.create(None, Decimal("2.5"), MODEL)
        messages = [{"role": role, "content": text} for role, text in
                    (("system", "You are a helpful assistant."), ("user", "  plan\n"),
                     ("assistant", " prior "), ("user", "Feedback"))]
        route = ("offline.invalid", 443, "/script", MODEL, "never-a-real-credential")
        with patch.object(api, "check_spend_guard", return_value={}), patch.object(api, "_load_route", return_value=route), patch.object(api.http.client, "HTTPSConnection", ScriptedConnection):
            folder = self.work / "episode-one"
            folder.mkdir()
            with CallSession(folder, budget, MODEL, "correct", 900) as session:
                self.assertEqual(session.ceiling, 600)
                for n in (1, 2):
                    self.assertEqual(session.call(messages), (f"answer {n}", 138))
                self.assertEqual([r["reasoning_tokens"] for r in session.records], [19, 19])
                self.assertEqual(sum(r["cost_usd"] for r in session.records), 0.00001)
            folder = self.work / "episode-two"
            folder.mkdir()
            with CallSession(folder, budget, MODEL, "correct", 300) as session:
                self.assertEqual(session.call(messages), ("answer 3", 138))
                self.assertFalse(session.records[0]["cache_hit"])
            ledger = folder / "campaign-calls.jsonl"
            events = [json.loads(line) for line in ledger.read_text().splitlines()]
            self.assertEqual([e["event"] for e in events], ["reserve", "settle"])
            first = self.work / "episode-one/campaign-calls.jsonl"
            self.assertEqual(len(first.read_text().splitlines()), 4)
            self.assertFalse((self.work / "campaign-calls.jsonl").exists())
            self.assertEqual([e["budget_usd"] for e in events[::2]], [1.5])
            self.assertEqual(read_json(budget.path)["calls"], 3)
            self.assertEqual(Decimal(read_json(budget.path)["reported_cost_usd"]), Decimal("0.000015"))
            for body in sent:
                self.assertEqual(body["messages"], [{"role": "user", "content": wire_prompt(messages)}])
                self.assertEqual(body["model"], MODEL)
                self.assertEqual(body["max_tokens"], MAX_OUTPUT_TOKENS)
                self.assertEqual(body["reasoning"], {"effort": "low"})
                self.assertEqual(body["temperature"], 0)
                self.assertNotIn("response_format", body)
            # The same episode ledger refuses a subsequent request with a pending reservation.
            with ledger.open("a") as log:
                log.write(json.dumps(dict(event="reserve", attempt_id="pending-fixture", budget_usd=1.5,
                                          reserve_usd=0.01, campaign_max_calls=None)) + "\n")
            with CallSession(folder, budget, MODEL, "correct", 300) as session:
                self.assertEqual(session.call(messages), ("answer 3", 138))  # same interrupted episode's prefix
                with self.assertRaises(StopEpisode) as denied:
                    session.call(messages)
            self.assertEqual(denied.exception.label, CLIENT_LIMIT)
            self.assertEqual(len(sent), 3)
            self.assertTrue(denied.exception.interrupted)


    def test_failed_transport_reservation_is_separate_from_usage(self):
        api = load_real_api()
        class BusyConnection:
            def __init__(self, *args, **kwargs):
                pass
            def request(self, method, path, body, headers):
                pass
            def getresponse(self):
                return types.SimpleNamespace(status=503, getheaders=lambda: [], read=lambda n: b"{}")
            def close(self):
                pass

        budget = Invocation(self.work, self.work / "budget.json")
        budget.create(None, 1, MODEL)
        messages = [{"role": "user", "content": "scripted failure"}]
        route = ("offline.invalid", 443, "/script", MODEL, "never-a-real-credential")
        with patch.object(api, "check_spend_guard", return_value={}), patch.object(api, "_load_route", return_value=route), patch.object(api.http.client, "HTTPSConnection", BusyConnection):
            with CallSession(self.work, budget, MODEL, "correct", 300) as session:
                session.client._sleep = lambda _: None
                with self.assertRaises(StopEpisode) as stopped:
                    session.call(messages)
                self.assertEqual(stopped.exception.label, "failure model service")
                self.assertEqual(session.api_calls, 3)
                self.assertIsNone(session.records[0]["cost_usd"])
                self.assertIsNone(session.records[0]["prompt_tokens"])
                self.assertGreater(session.records[0]["guard_cost_usd"], 0)
                self.assertEqual(session.records[0]["detail"], "http_5xx")
        info = read_json(budget.path)
        self.assertEqual(Decimal(info["reported_cost_usd"]), 0)
        self.assertGreater(Decimal(info["guard_cost_usd"]), 0)
        self.assertEqual(len((self.work / "campaign-calls.jsonl").read_text().splitlines()), 6)


if __name__ == "__main__":
    unittest.main()
