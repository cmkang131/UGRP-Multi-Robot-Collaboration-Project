"""Folder-local transport, frozen-episode and output-demand regression tests."""
import contextlib
import csv
import io
import json
import shutil
import sys
import tempfile
import unittest
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from regression_inputs import REGRESSION
from types import SimpleNamespace
from unittest.mock import patch

import run_chen2d
from LLM import MODEL, QWEN, SMALL_QWEN, load_real_api
from episode import Spec, run_episode
from limits import CALL_CEILING, Invocation
from output_demand import selected_plan
from plan_parse import PlanParser
from prompt_env1 import history_tokens
from storage import ROOT, code_version, digest, json_text, read_json, source_hashes, write_json
from summarize import episode_csv
from test_chen2d import calls
from test_chen2d_v3 import scripted_transport
from test_chen2d_v4 import cli
from test_chen2d_v5 import PINNED_CLIENT_SHA256, local_references
from test_chen2d_v9 import FEEDBACK, call, iteration, pipe_rows, snapshot


V9 = REGRESSION / "chen2d-9/context-runs/w3000-off"
FROZEN = "bdd193eaa2c6"
NAME = "2x2_DMAS_static_env0"
AGENT = "Agent[0.5, 0.5]"
PLAN = {AGENT: "move(box_blue, target_blue)", "Agent[1.5, 1.5]": "move(box_red, target_red)"}
TEXT = json.dumps(PLAN)


def csv_rows(path):
    with path.open(newline="") as stream:
        return list(csv.DictReader(stream))


def turn(number, step, role, reply, meters):
    c = call(number, step, reply, role=role, kinds=[kind for kind, _, _ in meters])
    c.update(speaker=AGENT, round=1)
    for attempt, (kind, generated, reasoning) in zip(c["attempts"], meters, strict=True):
        attempt.update(completion_tokens=generated, reasoning_tokens=reasoning, provider="script",
                       raw_output=TEXT if kind == "truncated" else reply)
    for field in ("completion_tokens", "reasoning_tokens"):
        values = [a[field] for a in c["attempts"]]
        c[field] = None if None in values else sum(values)
    return c


class FolderTest(unittest.TestCase):
    def setUp(self):
        tmp = tempfile.TemporaryDirectory(dir=ROOT, prefix=".chen10-test-")
        self.addCleanup(tmp.cleanup)
        self.work = Path(tmp.name)


class ReasoningTests(FolderTest):
    def test_both_small_qwen_constructor_and_wire_settings_and_provider_on_each_attempt(self):
        with local_references():
            api = load_real_api()
            self.assertEqual(digest(Path(api.__file__).read_bytes()), PINNED_CLIENT_SHA256)
            # Supply the runner's provenance read from the same pinned source as the in-memory client.
            init = api.RealLLM.__init__
            for setting in ("default", "off"):
                out = self.work / setting
                args = ["run_chen2d.py", "--model", SMALL_QWEN, "--out", str(out), "--conditions", "static",
                        "--frameworks", "CMAS", "--envs", "0", "--dropoff", "event", "--max-output-tokens", "96",
                        "--retry-temperature", "0.7", "--episode-call-ceiling", "3"]
                if setting == "off":
                    args += ["--reasoning", "off"]
                constructor = []
                def capture(client, *pos, **kw):
                    constructor.append(kw["reasoning"])
                    init(client, *pos, **kw)
                with self.subTest(setting=setting), scripted_transport(["truncated", "ok", "ok"]) as (sent, _):
                    connection = api.http.client.HTTPSConnection
                    getresponse = connection.getresponse
                    def response(conn):
                        packet = json.loads(getresponse(conn).read(-1))
                        packet["provider"] = "Zulu" if len(sent) == 1 else "Alpha"
                        if sent[-1][0]["reasoning"].get("enabled") is False:
                            packet["usage"]["completion_tokens_details"]["reasoning_tokens"] = 0
                        return SimpleNamespace(status=200, read=lambda _: json.dumps(packet).encode())
                    route = ("offline.invalid", 443, "/fixture", SMALL_QWEN, "test-fixture-credential")
                    with (patch.object(api, "_load_route", return_value=route), patch.object(connection, "getresponse", response),
                          patch.object(api.RealLLM, "__init__", capture), patch.object(sys, "argv", args),
                          patch.object(run_chen2d, "ProcessPoolExecutor", ThreadPoolExecutor),
                          patch.object(run_chen2d, "BRAIN", Path(api.__file__).parent), contextlib.redirect_stdout(io.StringIO())):
                        run_chen2d.main()
                    self.assertEqual(constructor, [None if setting == "default" else {"enabled": False}])
                    expected = {"effort": "low"} if setting == "default" else {"enabled": False}
                    self.assertEqual([(b["model"], b["reasoning"], b["max_tokens"]) for b, _ in sent],
                                     [(SMALL_QWEN, expected, 96)] * 3)
                    self.assertEqual([b["temperature"] for b, _ in sent], [0., .7, 0.])
                    folder = next((out / "episodes").iterdir())
                    physical = [a for c in calls(folder) for a in c["attempts"]]
                    logged = [json.loads(s) for s in (folder / "client-calls.jsonl").read_text().splitlines()]
                    self.assertEqual([a["provider"] for a in physical], ["Zulu", "Alpha", "Alpha"])
                    self.assertEqual([a["provider"] for a in physical], [r["provider"] for r in logged if r["event"] == "finish"])
                    row = read_json(folder / "episode.json")
                    self.assertEqual((row["reasoning_setting"], read_json(out / "run.json")["reasoning_setting"]), (setting, setting))
                    self.assertEqual(row["reasoning_tokens"] == 0, setting == "off")
                    csv_row, = csv_rows(out / "episodes.csv")
                    self.assertEqual((csv_row["providers"], csv_row["reasoning_setting"]), ("Alpha+Zulu", setting))

    def test_off_refused_before_client_construction_for_glm_and_large_qwen(self):
        for model, message in ((MODEL, "requires reasoning"), (QWEN, "no reasoning parameter")):
            out = self.work / "refused"
            args = ["run_chen2d.py", "--model", model, "--reasoning", "off", "--out", str(out)]
            with (self.subTest(model=model), patch.object(sys, "argv", args),
                  patch.object(run_chen2d, "load_real_api", side_effect=AssertionError("client loaded")),
                  contextlib.redirect_stderr(io.StringIO()) as error, self.assertRaises(SystemExit)):
                run_chen2d.main()
            self.assertIn(message, error.getvalue())
            self.assertFalse(out.exists())

    def test_frozen_v9_bytes_and_default_v10_metadata(self):
        archive = V9 / "episodes" / NAME
        old = read_json(archive / "episode.json")
        self.assertEqual(old["code_version"], FROZEN)
        self.assertEqual(digest((archive / "episode.json").read_bytes()), "b22222f1136dea7fd115d22d4be29fc7c44c5618ad449896ea95b2e0edbd9239")
        trace = calls(archive)
        spec = Spec(2, 2, "DMAS", "static", 0, V9 / "maps/2x2/env0.json", old["env_sha256"], old["event_sha256"],
                    dropoff="event")
        for legacy in (True, False):
            out = self.work / ("v9" if legacy else "v10")
            out.mkdir()
            config = read_json(V9 / "run.json")
            if not legacy:
                config.update(code_version=code_version(), source_sha256=source_hashes(), reasoning_setting="default")
            write_json(out / "run.json", config)
            budget = Invocation(out, out / (trace[0]["invocation"] + ".json"))
            budget.create(None, 2, "fake")
            clocks = [n for c in trace for n in (0., c["elapsed_seconds"])]
            steps = [n for it in old["iterations"] for n in (0., it["planning_seconds"])]
            stamp = patch("episode.code_version", return_value=FROZEN) if legacy else contextlib.nullcontext()
            with (patch("LLM.monotonic", side_effect=clocks), stamp,
                  patch("episode.time", SimpleNamespace(monotonic=iter(steps).__next__))):
                run_episode(spec, out, budget.path, "fake", "correct", 300, config["max_output_tokens"], 0., .7)
            new = out / "episodes" / NAME
            files = {p.relative_to(archive) for p in archive.rglob("*") if p.is_file()}
            self.assertEqual(len(files), 59)
            self.assertEqual({p.relative_to(new) for p in new.rglob("*") if p.is_file()}, files)
            for file in files:
                raw = (new / file).read_bytes()
                if not legacy and (file.name == "episode.json" or file.parent.name == "calls"):
                    obj = json.loads(raw)
                    self.assertEqual(obj.pop("reasoning_setting"), "default")
                    if file.name == "episode.json":
                        self.assertEqual(obj.pop("providers"), "")
                        self.assertEqual(obj["code_version"], code_version())
                        obj["code_version"] = FROZEN
                    else:
                        for a in obj["attempts"]:
                            self.assertIsNone(a.pop("provider"))
                    raw = json_text(obj).encode()
                self.assertEqual(raw, (archive / file).read_bytes(), (legacy, file))

    def test_grouping_refusal_and_resume_across_analysis_tools(self):
        a, b = self.work / "default", self.work / "off"
        base = ("run_chen2d.py", "--model", "fake", "--conditions", "static", "--frameworks", "CMAS",
                "--envs", "0", "--fake-script", "non-json")
        for out, options in ((a, ()), (b, ("--reasoning", "off"))):
            run = cli(*base, "--out", out, *options)
            self.assertEqual(run.returncode, 0, run.stderr)
            row, = csv_rows(out / "episodes.csv")
            self.assertEqual((row["reasoning_setting"], row["providers"]), (out.name, ""))
        self.assertIn("different reasoning_setting", cli("summarize.py", a, b).stderr)
        self.assertNotEqual(cli(*base, "--out", a, "--reasoning", "off").returncode, 0)
        failure = cli("failure_causes.py", a, b)
        self.assertEqual(failure.returncode, 0, failure.stderr)
        for section in ("failure causes", "who is ahead"):
            self.assertEqual([r["reasoning_setting"] for r in pipe_rows(failure.stderr, section)], ["default", "off"])
        demand = cli("output_demand.py", a, b)
        self.assertEqual(demand.returncode, 0, demand.stderr)
        for section in ("Planning calls", "Generation per environment step"):
            self.assertEqual([r["reasoning_setting"] for r in pipe_rows(demand.stderr, section)], ["default", "off"])
        path = next(b.glob("episodes/*/episode.json"))
        write_json(path, dict(read_json(path), reasoning_setting="default"))
        for tool in (("summarize.py",), ("failure_causes.py",), ("output_demand.py",), ("cost.py",),
                     ("paired.py", "--a", "authors", "--b", "choice"), ("audit_news.py",),
                     ("free_messages.py",), ("rescues.py",)):
            result = cli(*tool, b)
            self.assertNotEqual(result.returncode, 0, tool)
            self.assertIn("reasoning_setting", result.stderr)


class DemandTests(FolderTest):
    def constructed(self, tag, subjects, *, limit=100, setting="default"):
        out = self.work / tag
        out.mkdir()
        config = dict(read_json(V9 / "run.json"), model=SMALL_QWEN, reasoning_setting=setting,
                      code_version=code_version(), source_sha256=source_hashes(), max_output_tokens=limit)
        write_json(out / "run.json", config)
        for fw, trace, iterations, changes in subjects:
            name = f"2x2_{fw}_static_env0"
            folder = out / "episodes" / name
            (folder / "calls").mkdir(parents=True)
            row = dict(read_json(V9 / "episodes" / NAME / "episode.json"), episode_id=name, framework=fw,
                       model=SMALL_QWEN, reasoning_setting=setting, code_version=config["code_version"],
                       max_output_tokens=limit, api_calls=sum(c["api_calls"] for c in trace), iterations=iterations)
            row.update(changes)
            write_json(folder / "episode.json", row)
            for c in trace:
                write_json(folder / "calls" / f'{c["number"]:05d}.json', c)
        return out

    def test_calls_attempts_step_sums_quantiles_reviews_and_excluded_relay(self):
        dmas = [turn(1, 1, "dialogue", "PROCEED " + TEXT, [("ok", 10, 4)]),
                turn(2, 1, "dialogue", 'draft {"note":1} EXECUTE ' + TEXT,
                     [("truncated", 100, 80), ("ok", 30, 5)]),
                turn(3, 1, "relay", "SEND", [("truncated", 100, 90), ("ok", 45, 2)]),
                turn(4, 2, "dialogue", "EXECUTE {}", [("ok", 50, 10)])]
        hmas = [turn(1, 1, "central", TEXT, [("ok", 20, None)]),
                turn(2, 1, "review", "I suggest " + TEXT, [("ok", 6, 0)]),
                turn(3, 1, "central", TEXT, [("ok", 12, 1)])]
        run = self.constructed("meters", [("DMAS", dmas, [iteration(1), iteration(2)], {}),
                                          ("HMAS-2", hmas, [iteration(1)], {})])
        before = snapshot(run)
        dest = self.work / "calls.csv"
        result = cli("output_demand.py", run, "--calls-csv", dest)
        self.assertEqual(result.returncode, 0, result.stderr)
        data = csv_rows(dest)
        self.assertEqual(len(data), 6)
        one, retried, empty = [r for r in data if r["framework"] == "DMAS"]
        self.assertEqual([r["call_number"] for r in (one, retried, empty)], ["1", "2", "4"])
        self.assertEqual((one["plan_tokens"], one["plan_agents"], empty["plan_tokens"], empty["plan_agents"]),
                         ("0", "0", "1", "0"))
        self.assertEqual([retried[k] for k in ("generated_tokens", "reasoning_tokens", "visible_tokens", "cut_attempts",
                                               "plan_agents", "plan_tokens", "team_size", "speaker", "max_output_tokens")],
                         ["130", "85", "45", "1", "2", str(history_tokens(TEXT)), "4", AGENT, "100"])
        cut, ok = json.loads(retried["attempts"])
        self.assertEqual([cut[k] for k in ("generated_tokens", "reasoning_tokens", "visible_tokens", "cut", "plan_tokens")],
                         [100, 80, 20, True, 0])
        self.assertEqual((ok["visible_tokens"], ok["cut"], ok["plan_tokens"]), (25, False, history_tokens(TEXT)))
        role = {(r["framework"], r["role"]): r for r in pipe_rows(result.stdout, "Planning calls")}
        local = role["DMAS", "dialogue"]
        self.assertEqual([local[k] for k in ("logical_calls", "attempts", "attempt_cut_share", "extracted_plans")],
                         ["3", "4", "25.00% (1/4)", "2"])
        for field, expected in (("generated_tokens", (30, 46, 50)), ("reasoning_tokens", (5, 9, 10)),
                                ("visible_tokens", (25, 37, 40))):
            for stat, value in zip(("median", "p90", "max"), expected, strict=True):
                self.assertEqual(local[stat + "_" + field], f"{value} [n=3, cut=25.00% (1/4)]")
        self.assertEqual(local["median_agents_per_plan"], "1 [n=2, cut=33.33% (1/3)]")
        self.assertEqual(local["median_agents_per_call"], "0 [n=3, cut=33.33% (1/3)]")
        self.assertEqual(role["HMAS-2", "review"]["extracted_plans"], "0")
        steps = {r["framework"]: r for r in pipe_rows(result.stdout, "Generation per environment step")}
        self.assertEqual(steps["DMAS"]["median_generated_tokens"], "95 [n=2, cut=50.00% (1/2)]")
        self.assertEqual(steps["DMAS"]["p90_generated_tokens"], "131 [n=2, cut=50.00% (1/2)]")
        self.assertEqual(steps["HMAS-2"]["median_generated_tokens"], "38 [n=1, cut=0.00% (0/1)]")
        relay, = pipe_rows(result.stdout, "Excluded relay work")
        self.assertEqual([relay[k] for k in ("relay_calls", "relay_attempts", "relay_attempt_cut_share")],
                         ["1", "2", "50.00% (1/2)"])
        self.assertNotEqual(cli("output_demand.py", run, "--csv", run / "episodes.csv").returncode, 0)
        self.assertNotEqual(cli("output_demand.py", run, run).returncode, 0)
        self.assertEqual(snapshot(run), before)

    def test_partial_retry_unknown_meters_all_cut_and_pooling_limits_by_step(self):
        retry = turn(1, 1, "central", TEXT, [("truncated", 100, None), ("ok", 12, 2)])
        partial = self.constructed("partial", [("CMAS", [retry], [iteration(1, executed=False)],
                                                dict(finished=False, api_calls=1))])
        later = [turn(1, 1, "central", TEXT, [("ok", 40, None)]),
                 turn(2, 2, "central", None, [("network", None, None)])]
        high = self.constructed("high", [("CMAS", later, [iteration(1), iteration(2, executed=False)], {})], limit=200)
        result = cli("output_demand.py", partial, high)
        self.assertEqual(result.returncode, 0, result.stderr)
        prefix, ok, missing = list(csv.DictReader(io.StringIO(result.stdout)))
        self.assertEqual([prefix[k] for k in ("attempt_count", "cut", "generated_tokens", "visible_tokens", "plan_tokens")],
                         ["1", "True", "100", "", "0"])
        self.assertEqual((ok["reasoning_tokens"], ok["visible_tokens"], missing["generated_tokens"]), ("", "", ""))
        low, high = pipe_rows(result.stderr, "Planning calls")
        self.assertEqual(low["median_generated_tokens"], "NA [n=0, cut=100.00% (1/1)]")
        self.assertEqual(high["median_generated_tokens"], "40 [n=1, cut=0.00% (0/2)]")
        step, = pipe_rows(result.stderr, "Generation per environment step")
        self.assertEqual((step["observed_limits"], step["steps"], step["median_generated_tokens"], step["p90_generated_tokens"]),
                         ("100,200", "3", "70 [n=2, cut=33.33% (1/3)]", "94 [n=2, cut=33.33% (1/3)]"))

    def test_strict_and_lenient_extraction_repairs_and_final_ceiling(self):
        one = call(1, reply="prefix " + TEXT + " suffix")
        strict, lenient = PlanParser("strict"), PlanParser("lenient")
        self.assertEqual(selected_plan(one, strict, 0), (2, history_tokens(TEXT)))
        # The strict revision checker consumes the entire string.
        revision = dict(one, messages=[*one["messages"], dict(role="assistant", content=TEXT), dict(role="user", content="revise")])
        self.assertIsNone(selected_plan(revision, strict, 0))
        self.assertEqual(selected_plan(revision, lenient, 0), (2, history_tokens(TEXT)))
        repair = call(2, role="dialogue", feedback=FEEDBACK, reply=TEXT)
        self.assertEqual(selected_plan(repair, strict, 1), (2, history_tokens(TEXT)))
        self.assertIsNone(selected_plan(repair, strict, 6))
        run = self.constructed("ceiling", [("CMAS", [turn(1, 1, "central", TEXT, [("ok", 8, 2)])],
                                            [iteration(1, executed=False)], dict(success_failure=CALL_CEILING, episode_call_ceiling=1))])
        result = cli("output_demand.py", run)
        self.assertEqual(result.returncode, 0, result.stderr)
        row, = csv.DictReader(io.StringIO(result.stdout))
        self.assertEqual((row["generated_tokens"], row["plan_extracted"]), ("8", "False"))

    def test_copied_v3_run_read_only_and_rebuilt_episode_csv_defaults(self):
        old = self.work / "v3"
        shutil.copytree(REGRESSION / "chen2d-3/e2", old)
        before = snapshot(old)
        result = cli("output_demand.py", old)
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(snapshot(old), before)
        rows = list(csv.DictReader(io.StringIO(result.stdout)))
        self.assertEqual(len(rows), 82)
        self.assertEqual({(r["reasoning_setting"], r["size"], r["condition"]) for r in rows}, {("default", "2x2", "e2")})
        self.assertEqual({(r["generated_tokens"], r["reasoning_tokens"], r["visible_tokens"]) for r in rows}, {("7", "2", "5")})
        self.assertEqual({r["role"] for r in rows}, {"central", "review", "dialogue"})
        self.assertTrue(all(json.loads(r["attempts"])[0]["provider"] is None for r in rows))
        episode_csv(old)
        self.assertEqual({(r["reasoning_setting"], r["providers"]) for r in csv_rows(old / "episodes.csv")}, {("default", "")})


if __name__ == "__main__":
    suites = sys.argv[1:] or ["test_chen2d", *(f"test_chen2d_v{n}" for n in range(2, 11))]
    with local_references():
        print("Folder-local references verified. Network connections disabled.", flush=True)
        result = unittest.TextTestRunner(verbosity=2).run(unittest.defaultTestLoader.loadTestsFromNames(suites))
    sys.exit(not result.wasSuccessful())
