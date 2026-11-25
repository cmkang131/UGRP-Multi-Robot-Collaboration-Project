"""Offline map, retry, accounting and compatibility regressions for CHEN2D-3."""
import json
import os
import subprocess
import sys
import tempfile
import unittest
from collections import Counter
from contextlib import contextmanager
from dataclasses import replace
from decimal import Decimal
from pathlib import Path
from regression_inputs import REGRESSION
from types import SimpleNamespace
from unittest.mock import patch

import fake_model
from LLM import MAX_OUTPUT_TOKENS, MODEL, CallSession, load_real_api, wire_prompt
from env1_create import action_from_response
from episode import run_episode
from limits import CALL_CEILING, CALL_LIMIT, COST_LIMIT, MODEL_SERVICE, OUTPUT_LIMIT, Invocation, StopEpisode
from map_events import EVENT_FILE_VERSION, agent_at, boxes, cell_key, coordinates, distance, event_path, reference_plan
from storage import ROOT, digest, read_json, write_json
from test_chen2d import calls, fixture_spec

BOARD = {"0.5_0.5": ["box_blue", "target_blue"], "0.5_1.5": [], "1.5_0.5": [], "1.5_1.5": []}
DELIVER = '{"Agent[0.5, 0.5]":"move(box_blue, target_blue)"}'
OUTPUT_TOKENS = 96


@contextmanager
def scripted_transport(kinds):
    """Leave native retries, request formatting, and both ledgers active. Replace the socket and sleep."""
    api = load_real_api()
    sent, waits = [], []

    class Connection:
        def __init__(self, *args, **kwargs):
            pass

        def request(self, method, path, body, headers):
            sent.append((json.loads(body), headers["X-Request-Id"]))

        def getresponse(self):
            n = len(sent)
            kind = kinds(sent[-1][0], n) if callable(kinds) else kinds[n - 1]
            if kind == "network":
                raise ConnectionResetError("scripted connection reset")
            if kind in ("rate_limit", "http_5xx"):
                return SimpleNamespace(status=429 if kind == "rate_limit" else 503,
                                       getheaders=lambda: [], read=lambda limit: b"{}")
            cutoff = kind == "truncated"
            limit = sent[-1][0]["max_tokens"]
            payload = {"choices": [{"message": {"content": "partial {" if cutoff else "{}" if kind == "idle" else DELIVER},
                                    "finish_reason": "length" if cutoff else "stop"}],
                       "usage": {"prompt_tokens": 10 * n, "completion_tokens": limit if cutoff else 3 * n,
                                 "completion_tokens_details": {"reasoning_tokens": limit - 1 if cutoff else n},
                                 "cost": n / 100_000}}
            return SimpleNamespace(status=200, read=lambda size: json.dumps(payload).encode())

        def close(self):
            pass

    route = ("offline.invalid", 443, "/script", MODEL, "test-fixture-credential")
    with (patch.object(api, "_load_route", return_value=route),
          patch.object(api, "check_spend_guard", return_value={}),
          patch.object(api.http.client, "HTTPSConnection", Connection),
          patch.object(api.time, "sleep", side_effect=waits.append)):
        yield sent, waits


class TaskThreeTests(unittest.TestCase):
    def setUp(self):
        tmp = tempfile.TemporaryDirectory(dir=ROOT, prefix=".chen-v3-test-")
        self.addCleanup(tmp.cleanup)
        self.work = Path(tmp.name)
        self.spec = fixture_spec(self.work / "board.json", BOARD, "static")

    def invocation(self, tag, max_calls=None, cap=1, name="budget"):
        out = self.work / tag
        out.mkdir(exist_ok=True)
        budget = Invocation(out, out / (name + ".json"))
        budget.create(max_calls, cap, MODEL)
        return budget

    def episode(self, budget, ceiling=300):
        run_episode(self.spec, budget.out, budget.path, MODEL, "correct", ceiling, OUTPUT_TOKENS)
        folder = budget.out / "episodes" / self.spec.name
        row = read_json(folder / "episode.json")
        records = calls(folder)
        ledger = [json.loads(line) for line in (folder / "campaign-calls.jsonl").read_text().splitlines()]
        return row, records, ledger

    def test_all_twelve_maps_replayed_against_frozen_bytes(self):
        root = ROOT / "envs"
        manifest = REGRESSION / "chen2d-4/maps-before.json"
        self.assertEqual(digest(manifest.read_bytes()), "8e0266d961ec8e305d3e14f882d4ca21d59560625c8ca260c0ae974aab402351")
        maps, events = read_json(manifest), read_json(root / "events-manifest.json")
        self.assertEqual(len(maps), 12)
        current = read_json(root / "manifest.json")
        self.assertEqual({name: current[name] for name in maps}, maps)
        for name, sha in maps.items():
            with self.subTest(map=name):
                path = root / name
                sidecar = event_path(path)
                self.assertEqual(digest(path.read_bytes()), sha)
                self.assertEqual(digest(sidecar.read_bytes()), events[str(sidecar.relative_to(root))])
                initial, a = read_json(path), read_json(sidecar)
                self.assertEqual((a["event_file_version"], a["env_sha256"]), (EVENT_FILE_VERSION, sha))
                state, first_delivery = initial, {}
                for step in range(1, a["S"] + 1):
                    applied = []
                    feedback, state = action_from_response(state, reference_plan(state), applied)
                    self.assertFalse(feedback)
                    for _, item, dest in applied:
                        if dest == "target_" + item[4:]:
                            first_delivery.setdefault(item[4:], step)
                    if step == a["event_step"]:
                        remaining = boxes(state)
                        self.assertEqual(a["reference_boxes_at_event"], {c: remaining[c] for c in boxes(initial)})
                        self.assertGreater(remaining[a["A"]], 0)
                        self.assertEqual((max(remaining.values()), remaining[a["A"]]),
                                         (a["reference_box_A_left"], a["reference_box_A_left"]))
                        free = [k for k in initial if "target_" + a["A"] not in initial[k]]
                        preferred = [k for k in free if "box_" + a["A"] not in state[k]]
                        self.assertIn(cell_key(a["D"]), preferred or free)
                self.assertFalse(boxes(state))
                self.assertEqual(a["reference_first_delivery_steps"], first_delivery)
                delayed = {c for c, step in first_delivery.items() if step >= 2}
                self.assertIn(a["A2"], delayed or first_delivery)
                self.assertEqual(a["M"], agent_at(a["D"]))
                self.assertNotEqual(a["L"], a["M"])
                self.assertIsNone(a["M2"])

    def test_lowered_event_fires_before_first_plan_when_only_initial_box_remains(self):
        spec = replace(self.spec, condition="e1")
        budget = self.invocation("zero")
        run_episode(spec, budget.out, budget.path, "fake", "correct", 30)
        folder = budget.out / "episodes" / spec.name
        row = read_json(folder / "episode.json")
        self.assertEqual((row["map_assignment"]["clamped_event_step"], row["event_step"], row["box_A_left_at_event"]),
                         (2, 0, 1))
        self.assertTrue(row["map_assignment"]["event_step_lowered"] and row["strict_success"])
        self.assertTrue(calls(folder)[0]["told"])
        self.assertEqual(read_json(folder / "pg_state/pg_state1.json"), row["event"]["state_after"])

    def test_e2_member_is_actual_rejected_robot_including_leader_collision(self):
        board = {k: ["box_blue", "target_blue"] if k != "0.5_0.5" else [] for k in BOARD}
        spec = replace(fixture_spec(self.work / "e2.json", board, "e2", tell="member"), framework="HMAS-2")
        leader = read_json(event_path(spec.env_path))["L2"]
        self.assertEqual(leader, "Agent[1.5, 1.5]")
        original = fake_model.reply
        for label, actor in (("same", leader), ("different", "Agent[0.5, 1.5]"), ("unfired", None)):
            with self.subTest(actor=actor):
                budget = self.invocation(label)
                # Fix the rejecting square and give that robot an HMAS-2 review on the next iteration.
                if actor:
                    here = next(coordinates(k) for k in board if agent_at(coordinates(k)) == actor)
                    hop = next(coordinates(k) for k in board if distance(coordinates(k), here) == 1)
                    replies = iter([json.dumps({actor: "move(box_blue, target_blue)"}),
                                    json.dumps({actor: f"move(box_blue_returned, square{list(hop)})"})])
                else:
                    replies = iter(["no plan"])
                def choose_first(messages, script):
                    if "Please evaluate the given plan." in messages[1]["content"]:
                        return "I Agree"
                    return next(replies, None) or original(messages, script)
                with patch.object(fake_model, "reply", side_effect=choose_first):
                    run_episode(spec, budget.out, budget.path, "fake", "correct", 100)
                folder = budget.out / "episodes" / spec.name
                row = read_json(folder / "episode.json")
                self.assertEqual((row["L"], row["M"]), (leader, actor))
                self.assertEqual(row["leader_is_member"], None if actor is None else actor == leader)
                if actor is None:
                    self.assertTrue(row["event_not_fired"])
                    self.assertEqual(row["told_turns_after_event"], {})
                else:
                    self.assertEqual(agent_at(row["event"]["X"]), actor)
                    self.assertEqual(row["event"]["M"], actor)
                    for c in calls(folder):
                        expected = c["step"] > row["trigger_step"] and c["role"] == "review" and c["speaker"] == actor
                        self.assertEqual(c["told"], expected)
                        self.assertEqual("Change of orders" in c["messages"][1]["content"], expected)
                    self.assertGreater(row["told_turns_after_event"][actor], 0)

    def test_truncated_then_ok_continues_and_settles_both_attempts(self):
        budget = self.invocation("recovered")
        with scripted_transport(["truncated", "idle", "ok"]) as (sent, waits):
            row, log, ledger = self.episode(budget)
        self.assertEqual((row["success_failure"], row["steps"], row["api_calls"]), ("success", 2, 3))
        self.assertEqual([(c["attempt_count"], c["attempt_kinds"]) for c in log], [(2, ["truncated", "ok"]), (1, ["ok"])])
        self.assertEqual((row["retried_calls"], row["truncated_attempts"]), (1, 1))
        self.assertEqual([i["calls"] for i in row["iterations"]], [2, 1])
        self.assertEqual((row["prompt_tokens"], row["completion_tokens"], row["reasoning_tokens"], row["tokens"]),
                         (60, 111, 100, 171))
        self.assertEqual(log[0]["cost_usd"], 0.00003)
        self.assertEqual(row["cost_usd"], 0.00006)
        info = read_json(budget.path)
        self.assertEqual((info["calls"], Decimal(info["reported_cost_usd"]), Decimal(info["guard_cost_usd"]), info["reservations"]),
                         (3, Decimal("0.00006"), Decimal("0.00006"), {}))
        self.assertEqual(len(waits), 1)
        self.assertEqual(len({request_id for _, request_id in sent}), 3)
        self.assertEqual(sent[0][0], sent[1][0])
        self.assertTrue(all(body["max_tokens"] == OUTPUT_TOKENS for body, _ in sent))
        self.assertEqual([e["event"] for e in ledger], ["reserve", "settle"] * 3)
        attempts = [a for c in log for a in c["attempts"]]
        self.assertEqual([a["attempt_id"] for a in attempts], [e["attempt_id"] for e in ledger[::2]])
        self.assertEqual(attempts[0]["logical_call_id"], attempts[1]["logical_call_id"])
        self.assertFalse(any(a["cache_hit"] for a in attempts))

    def test_three_truncations_get_output_limit_and_all_charges(self):
        from summarize import compare
        from contextlib import redirect_stdout
        from io import StringIO
        budget = self.invocation("exhausted")
        with scripted_transport(["truncated"] * 3) as (sent, waits):
            row, log, ledger = self.episode(budget, ceiling=3)
        self.assertEqual((row["success_failure"], row["detail"], row["steps"], row["api_calls"]), (OUTPUT_LIMIT, "truncated", 0, 3))
        self.assertTrue(row["finished"])
        self.assertEqual((row["retried_calls"], row["truncated_attempts"], row["tokens"]), (1, 3, 348))
        self.assertEqual((len(log), log[0]["attempt_count"], log[0]["attempt_kinds"]), (1, 3, ["truncated"] * 3))
        self.assertEqual((len(sent), len(waits), len(ledger)), (3, 2, 6))
        self.assertEqual((row["cost_usd"], row["known_reported_cost_usd"], row["guard_cost_usd"]), (0.00006,) * 3)
        info = read_json(budget.path)
        self.assertEqual((info["calls"], Decimal(info["guard_cost_usd"]), Decimal(info["reported_cost_usd"])),
                         (3, Decimal("0.00006"), Decimal("0.00006")))
        output = StringIO()
        with redirect_stdout(output):
            compare([row], Counter())
        header, group = [s.split(" | ") for s in output.getvalue().splitlines()]
        summary = dict(zip(header, group, strict=True))
        self.assertEqual([summary[f] for f in ("retried_calls", "truncated_attempts", OUTPUT_LIMIT)], ["1", "3", "1"])

    def test_other_transients_are_retried_and_mixed_usage_keeps_known_costs(self):
        for window, kinds, success in (("0", ["http_5xx", "rate_limit", "ok"], True),
                                       ("1", ["rate_limit", "network", "truncated"], False),
                                       ("1", ["network"] * 3, False)):
            with self.subTest(kinds=kinds), patch.dict(os.environ, {"UGRP_V8_RETRY_WINDOW": window}):
                budget = self.invocation(kinds[0])
                with scripted_transport(kinds) as (sent, waits):
                    row, log, ledger = self.episode(budget)
                self.assertEqual(row["success_failure"], "success" if success else MODEL_SERVICE)
                self.assertEqual((len(sent), len(waits), row["api_calls"], row["retried_calls"]), (3, 2, 3, 1))
                self.assertEqual((log[0]["attempt_kinds"], row["truncated_attempts"]), (kinds, kinds.count("truncated")))
                self.assertIsNone(row["cost_usd"])
                self.assertIsNone(row["prompt_tokens"])
                has_usage = kinds[-1] in ("ok", "truncated")
                self.assertEqual(row["known_prompt_tokens"], 30 if has_usage else 0)
                self.assertEqual(row["known_reported_cost_usd"], 0.00003 if has_usage else 0)
                guard = sum(Decimal(str(e["cost_usd"])) for e in ledger if e["event"] == "settle")
                info = read_json(budget.path)
                self.assertEqual(Decimal(str(row["guard_cost_usd"])), guard)
                self.assertEqual(Decimal(info["guard_cost_usd"]), guard)
                self.assertEqual(Decimal(info["reported_cost_usd"]), Decimal(str(row["known_reported_cost_usd"])))

    def test_attempt_cap_and_invocation_resume_do_not_rebill_or_grant_extra_retries(self):
        for last, outcome in (("ok", "success"), ("truncated", OUTPUT_LIMIT)):
            with self.subTest(last=last):
                first = self.invocation(last, max_calls=1)
                with scripted_transport(["truncated", "truncated", last]) as (sent, _):
                    paused, before, _ = self.episode(first)
                    self.assertEqual((paused["success_failure"], paused["finished"], paused["api_calls"], len(sent)),
                                     (CALL_LIMIT, False, 1, 1))
                    self.assertEqual(before[0]["status"], "interrupted")
                    second = self.invocation(last, name="resume")
                    final, after, _ = self.episode(second)
                self.assertEqual((final["success_failure"], final["api_calls"], final["cost_usd"], len(sent)),
                                 (outcome, 3, 0.00006, 3))
                self.assertEqual(before[0]["attempts"], after[0]["attempts"][:1])
                self.assertEqual([a["invocation"] for a in after[0]["attempts"]], ["budget", "resume", "resume"])
                self.assertEqual([read_json(b.path)["calls"] for b in (first, second)], [1, 2])
                self.assertEqual([Decimal(read_json(b.path)["guard_cost_usd"]) for b in (first, second)],
                                 [Decimal("0.00001"), Decimal("0.00005")])
        limited = self.invocation("episode-cap")
        with scripted_transport(["truncated"]) as (sent, _):
            row, _, _ = self.episode(limited, ceiling=1)
        self.assertEqual((row["success_failure"], row["truncated_attempts"], len(sent)), (CALL_CEILING, 1, 1))

    def test_dollar_guard_can_stop_between_native_attempts(self):
        messages = [{"role": "user", "content": "short request"}]
        api = load_real_api()
        price = api.MODEL_PROFILES.get(MODEL, {}).get("max_price", api.DEFAULT_MAX_PRICE)
        reserve = (Decimal(len(wire_prompt(messages).encode()) + 1024) * Decimal(str(price["prompt"])) +
                   OUTPUT_TOKENS * Decimal(str(price["completion"]))) / 1_000_000
        budget = self.invocation("cost", cap=reserve)
        with scripted_transport(["http_5xx"]) as (sent, _):
            with CallSession(budget.out, budget, MODEL, "correct", 300, OUTPUT_TOKENS) as session:
                with self.assertRaises(StopEpisode) as stopped:
                    session.call(messages)
        self.assertEqual((stopped.exception.label, stopped.exception.interrupted, len(sent)), (COST_LIMIT, True, 1))
        info = read_json(budget.path)
        self.assertEqual((info["calls"], Decimal(info["guard_cost_usd"]), Decimal(info["reported_cost_usd"]), info["reservations"]),
                         (1, reserve, Decimal(0), {}))

    def test_summary_checks_manifest_and_each_episode_version_and_token_limit(self):
        def cli(*args):
            return subprocess.run([sys.executable, "-B", *map(str, args)], cwd=ROOT, capture_output=True, text=True)
        def run(out, *args):
            return cli("run_chen2d.py", "--out", out, "--model", "fake", "--frameworks", "CMAS",
                       "--conditions", "static", "--envs", "0", *args)
        default, other = self.work / "default", self.work / "other"
        rc = run(default)
        self.assertEqual(rc.returncode, 0, rc.stderr)
        rc = run(other, "--max-output-tokens", OUTPUT_TOKENS)
        self.assertEqual(rc.returncode, 0, rc.stderr)
        self.assertNotEqual(run(default, "--max-output-tokens", OUTPUT_TOKENS).returncode, 0)
        self.assertNotEqual(run(self.work / "invalid", "--max-output-tokens", 0).returncode, 0)
        self.assertEqual(read_json(default / "run.json")["max_output_tokens"], MAX_OUTPUT_TOKENS)
        settings = read_json(other / "run.json")
        self.assertEqual((settings["event_file_version"], settings["max_output_tokens"]), (EVENT_FILE_VERSION, OUTPUT_TOKENS))
        self.assertIn("different max_output_tokens", cli("summarize.py", default, other).stderr)
        write_json(other / "run.json", dict(settings, event_file_version=EVENT_FILE_VERSION - 1))
        self.assertIn("different event_file_version", cli("summarize.py", default, other).stderr)
        write_json(other / "run.json", settings)
        path = next(other.glob("episodes/*/episode.json"))
        row = read_json(path)
        csv_before = (other / "episodes.csv").read_bytes()
        for field in ("event_file_version", "max_output_tokens"):
            self.assertEqual(row[field], settings[field])
            write_json(path, dict(row, **{field: row[field] + 1}))
            rc = cli("summarize.py", other)
            self.assertNotEqual(rc.returncode, 0)
            self.assertIn(field, rc.stderr)
            self.assertEqual((other / "episodes.csv").read_bytes(), csv_before)
        row["map_assignment"].pop("event_file_version")
        write_json(path, row)
        self.assertIn("event_file_version in map assignment", cli("summarize.py", other).stderr)


if __name__ == "__main__":
    unittest.main()
