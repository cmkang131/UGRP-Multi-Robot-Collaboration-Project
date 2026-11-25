"""Offline cut-answer and task-20 compatibility regressions."""
import csv
import hashlib
import io
import json
import sys
import tempfile
import unittest
from collections import Counter
from contextlib import redirect_stdout
from dataclasses import replace
from datetime import datetime, timezone
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

import run_chen2d
import summarize
from LLM import MODEL, load_real_api
from episode import run_episode
from fake_model import CutReply
from failure_causes import classify
from limits import CALL_LIMIT, OUTPUT_LIMIT, Invocation
from output_demand import measure_episode
from plan_parse import cut_reply_prefix, read_own_reply
from planning_metrics import MATCHED_ROUND_CAP
from storage import ROOT, code_version, read_json
from test_chen2d import calls
from test_chen2d_v3 import scripted_transport
from test_chen2d_v4 import cli
from test_chen2d_v5 import local_references
from test_chen2d_v11 import A, B, C, D, BAD, ONE, PATH, RED, TO_B, HorizonFixtures
from test_chen2d_v17_retry import http_response
from test_chen2d_v19 import completion
from test_chen2d_v20 import peer_lists, table_rows


def discard_fingerprint(out, policy, script, *flags):
    """Exercise both CLI entry points at fixed times and with a fixed invocation ID."""
    args = ["run_chen2d.py", "--model", "fake", "--protocol", "matched", "--map-set", "scaled:2",
            "--sizes", "2x2", "--frameworks", "CMAS,GROUP,OWN", "--group-size", "2", "--conditions", "static",
            "--envs", "0", "--horizon", "3", "--max-planning-rounds", "2", "--failed-writer", policy,
            "--fake-script", script, "--out", str(out), *flags]
    stamp = SimpleNamespace(now=lambda tz: datetime(2026, 11, 24, tzinfo=timezone.utc))
    with (patch.object(sys, "argv", args), patch("run_chen2d.datetime", stamp),
          patch("run_chen2d.uuid.uuid4", return_value=SimpleNamespace(hex="fixed")),
          patch("LLM.monotonic", return_value=0.0), patch("episode.time", SimpleNamespace(monotonic=lambda: 0.0)),
          redirect_stdout(io.StringIO())):
        run_chen2d.main()
    data = {}
    for by in ([], ["--by", "planning"]):
        with (patch.object(sys, "argv", ["summarize.py", *by, str(out)]), redirect_stdout(io.StringIO()) as table):
            summarize.main()
        data["summary-" + "".join(by)] = table.getvalue().encode()
    for path in out.rglob("*"):
        if path.is_file() and (path.relative_to(out).parts[0] in ("episodes", "invocations")
                               or path.name in ("episodes.csv", "assignments.json")):
            data[path.relative_to(out).as_posix()] = path.read_bytes()
    digest = hashlib.sha256()
    revision = code_version().encode()
    for name, raw in sorted(data.items()):
        digest.update(name.encode() + b"\0" + raw.replace(revision, b"<source-version>") + b"\0")
    return digest.hexdigest()


class DiscardCompatibilityTests(unittest.TestCase):
    def test_explicit_discard_matches_task20_prompts_records_and_summaries(self):
        # Captured with the unmodified task-20 CLI, bc8ca8b14f1e.
        expected = {
            ("drop", "correct"): "b7fc2beecf9ced5f8795f6d7143ad9bd6fcb9fa376d07b107f8793bccc9b7633",
            ("drop", "invalid"): "2829578a19b136c68e63fb0e60efab10a81b4e8bdb96e93e6ad2f7caba0fc00e",
            ("drop", "non-json"): "557c749232a47cca2a768c1fd929b2fec3498c410e0350216ffab33557f94c8b",
            ("fail", "correct"): "60a1d0d058e0c8784cdf983495c1438054f47703f730ae2d6618461e0ba2826c",
            ("fail", "invalid"): "e2aaece79b95673c6b504bbfa2545683ec6a351614d771af01f73576df636fca",
            ("fail", "non-json"): "fed409fa811ba5dcf0db188f864167ab88f32ac536ad827a432a05181e37b61d",
            ("idle", "correct"): "1a632b84399364fb2f0031831a5dbdb6b46e9a8ec56036b8e8681656cd3da610",
            ("idle", "invalid"): "22802c039a2b40090b2b97b0e8812155ed31c79f11be8aaa0f84cce6900f8b17",
            ("idle", "non-json"): "8fc1ec7e190e305aac04bb1968e630ce025747919efc7d7e5283047d0d9a684a",
        }
        with tempfile.TemporaryDirectory(dir=ROOT) as scratch:
            for (policy, script), fingerprint in expected.items():
                with self.subTest(policy=policy, script=script):
                    out = Path(scratch) / (policy + "-" + script)
                    self.assertEqual(discard_fingerprint(out, policy, script, "--cut-answer", "discard"), fingerprint)


class CutAnswerTests(HorizonFixtures):
    def matched(self, framework="CMAS", board=ONE, **options):
        return self.spec(board, framework, 3, protocol="matched", cut_answer="prefix", max_planning_rounds=1,
                         reasoning_setting="default",
                         group_size=2 if framework == "GROUP" else None, **options)

    def transport(self, spec, replies, tag):
        out = self.work / tag
        out.mkdir()
        budget = Invocation(out, out / "script.json")
        budget.create(None, 5, MODEL)
        with local_references(), scripted_transport([]) as (sent, waits):
            connection = load_real_api().http.client.HTTPSConnection
            with patch.object(connection, "getresponse", side_effect=replies):
                run_episode(spec, out, budget.path, MODEL, "correct", 100)
        self.assertEqual((len(sent), read_json(budget.path)["calls"]), (len(replies), len(replies)))
        folder = out / "episodes" / spec.name
        return read_json(folder / "episode.json"), calls(folder), waits

    def test_joint_cut_inside_third_step_executes_only_two_without_retry(self):
        text = ('Draft for Agent[0.5, 0.5].\n```json\n' + json.dumps(PATH[:2])[:-1]
                + ', {"' + D + '":"' + RED + '","' + A + '":"move(')
        row, (call,), waits = self.transport(self.matched(), [completion(text, "length")], "cut")
        batch, = row["round_log"]
        attempt, = call["attempts"]
        self.assertEqual((attempt["raw_output"], attempt["visible_reply_chars"], attempt["cutoff_reply_class"]),
                         (text, len(text), "partial"))
        self.assertEqual((attempt["cut_off"], attempt["cut_answer_salvaged"], attempt["salvaged_steps"]), (True, True, 2))
        self.assertEqual((call["status"], call["cut_answer_salvaged"], call["response_from_attempt"],
                          call["attempt_id"], call["reply_attempt_count"], waits), ("ok", True, 1, attempt["attempt_id"], 1, []))
        self.assertEqual((batch["proposed_plans"], batch["plans_executed"], batch["empty_steps_skipped"],
                          batch["stop_reason"]), (PATH[:2], 2, 0, "all executed"))
        self.assertEqual([it["issued_plan"] for it in row["iterations"]], PATH[:2])
        event, = batch["writer_cut_prefix"]
        self.assertEqual(event, dict(event="writer_cut_prefix", planning_round=1, framework="CMAS",
                                     speaker=call["speaker"], robots=[A, B, C, D], salvaged_steps=2, horizon=3,
                                     call=1, attempt=1))
        self.assertEqual((row["success_failure"], row["truncated_attempts"], row["cut_calls"][0]["attempts"],
                          row["rounds_cutoff_recovered"], row["cutoff_attempts_partial"]), (MATCHED_ROUND_CAP, 1, 1, 1, 1))
        self.assertEqual((row["cutoff_attempts_partial_salvaged"], row["cut_prefix_robot_steps_kept"],
                          row["cut_prefix_robot_steps_not_written"]), (1, 8, 4))
        demand, _ = measure_episode(self.work / "cut", row, Counter())
        self.assertTrue(demand[0]["attempts"][0]["cut"] and demand[0]["plan_extracted"])
        self.assertNotEqual(classify(row, [call])["cause"], "output_limit")

    def test_empty_fence_and_first_unclosed_step_retry_even_with_complete_robot_pair(self):
        raw = '{"' + A + '":"' + TO_B + '", "' + B + '":"'
        for i, text in enumerate(("  \n", "```js", "[" + raw, raw)):
            with self.subTest(text=text):
                row, (call,), waits = self.transport(self.matched(), [completion(text, "length"),
                                                    completion(json.dumps(PATH))], str(i))
                self.assertEqual((len(waits), call["attempt_kinds"], row["correct_deliveries"]),
                                 (1, ["truncated", "ok"], 1))
                self.assertNotIn("cut_answer_salvaged", call)
                self.assertEqual((row["cutoff_attempts_empty"], row["cutoff_attempts_partial_zero_steps"],
                                  row["round_log"][0]["writer_cut_prefix"]), (int(i == 0), int(i != 0), []))

    def test_group_peer_receives_only_closed_steps_and_supplies_third_step(self):
        raw = json.dumps(PATH[:2])[:-1] + ', {"' + A + '":"incomplete'
        row, trace, _ = self.play(self.matched("GROUP"), [CutReply(raw), json.dumps([{}, {}, PATH[2]])])
        self.assertEqual(peer_lists(trace[1]), {A: PATH[:2]})
        batch, = row["round_log"]
        event, = batch["writer_cut_prefix"]
        self.assertEqual((event["group_size"], event["robots"], row["cut_prefix_robot_steps_kept"],
                          row["cut_prefix_robot_steps_not_written"]), (2, [A, B], 4, 2))
        self.assertEqual((batch["proposed_plans"], row["correct_deliveries"], row["api_calls"]), (PATH, 1, 2))
        self.assertEqual(row["iterations"][-1]["action_calls"], {D: 2})

    def test_own_exposes_two_written_entries_and_merges_normal_wait_tail(self):
        raw = '["' + TO_B + '", null, "' + RED
        replies = [CutReply(raw), json.dumps([None, PATH[1][B], None]), "[null]", json.dumps([None, None, RED])]
        row, trace, _ = self.play(self.matched("OWN"), replies)
        self.assertEqual((trace[0]["own_reply_padded"], peer_lists(trace[1])), (True, {A: [TO_B, None]}))
        self.assertEqual((row["api_calls"], row["cut_prefix_robot_steps_kept"], row["cut_prefix_robot_steps_not_written"]),
                         (4, 2, 1))
        self.assertEqual((row["round_log"][0]["proposed_plans"], row["correct_deliveries"]), (PATH, 1))

    def test_partial_first_action_gets_normal_repair_and_a_repair_can_be_salvaged(self):
        spec = self.matched(failed_writer="idle")
        rejected = json.dumps([{A: BAD}])
        row, trace, _ = self.play(spec, [CutReply(rejected[:-1] + ', {"broken'), CutReply(json.dumps(PATH))])
        batch, = row["round_log"]
        self.assertEqual((trace[1]["messages"][-2]["content"], [c["status"] for c in batch["checks"]]),
                         (rejected, ["invalid", "valid"]))
        self.assertIn("Doable actions now:", trace[1]["messages"][-1]["content"])
        self.assertEqual((row["api_calls"], row["repair_calls"], row["retried_calls"],
                          row["correct_deliveries"], batch["writer_blocked"]), (2, 1, 0, 1, []))
        self.assertEqual([(e["call"], e["salvaged_steps"]) for e in batch["writer_cut_prefix"]], [(1, 1), (2, 3)])
        self.assertEqual((row["cutoff_attempts_partial_salvaged"], row["cut_prefix_robot_steps_kept"],
                          row["cut_prefix_robot_steps_not_written"]), (2, 16, 8))
        self.assertEqual(batch["executed_writer_calls"], [2])

    def test_only_zero_step_writer_idles_after_ordinary_exhaustion(self):
        raw = '[{"' + A + '":"' + TO_B + '"'
        board = dict(ONE)
        board["1.5_0.5"] = ["box_blue", "target_blue"]
        action = {C: "move(box_blue, target_blue)"}
        row, trace, _ = self.play(self.matched("GROUP", board, failed_writer="idle"),
            [CutReply(""), CutReply(" "), CutReply(raw), CutReply(json.dumps([action])[:-1] + ",{")])
        batch, = row["round_log"]
        self.assertEqual((len(trace), row["api_calls"], row["correct_deliveries"], batch["stalled"]), (2, 4, 1, False))
        self.assertEqual(peer_lists(trace[1]), {A: [], B: []})
        self.assertEqual((batch["writer_blocked"][0]["robots"], batch["writer_cut_prefix"][0]["robots"]), ([A, B], [C, D]))
        self.assertEqual((row["cutoff_attempts_empty"], row["cutoff_attempts_partial_zero_steps"],
                          row["cutoff_attempts_partial_salvaged"], row["truncated_attempts"]), (2, 1, 1, 4))
        for policy in ("drop", "fail"):
            row, _, _ = self.play(self.matched(failed_writer=policy), [CutReply(raw)] * 3, policy)
            self.assertEqual(row["success_failure"], OUTPUT_LIMIT)

    def test_reader_respects_own_entry_boundaries_wrappers_scope_and_ambiguity(self):
        def read(text, own=True, h=3):
            return cut_reply_prefix(text, h, own=own, speaker=A, agent_positions={(0.5, 0.5)})

        for text in ('["wait", null', '[["wait"],[null],["unclosed',
                     '{"' + A + '":["wait",{}', '[["wait",null,', "['wait', None, '",
                     '[{"' + A + '":"wait"},{}, {"' + A + '":"wait"'):
            with self.subTest(text=text):
                short, k = read(text)
                self.assertEqual(k, 2)
                self.assertEqual(read_own_reply(short, 3, A, "lenient", matched_shapes=True)[0].entries, [None] * 3)
        for text, own in (('[["wait"', True), ('[{"' + A + '":"wait"', True), ("[nul", True),
                          ('[nullified', True), ("[", False), ('[{"plans":[{}]', False),
                          ('{"' + B + '":[{},', True), ('{"' + A + '":[{},', False),
                          ('[{"' + B + '":"move"},', False), ('[{"' + A + '":"move"}] [{}', False)):
            with self.subTest(text=text):
                self.assertIsNone(read(text, own))
        joint = [{A: 'quoted "brace }, ]" and backslash \\'}, {}]
        for text in ('{"plans":' + json.dumps(joint)[:-1] + ",{", json.dumps({"step 1": joint[0], "step 2": {}})[:-1]):
            self.assertEqual(read(text, False)[1], 2)
        self.assertEqual(read(json.dumps({A: TO_B}), False)[1], 1)
        self.assertEqual(read("null", True)[1], 1)

    def test_strict_short_reply_uses_the_same_length_repair(self):
        row, trace, _ = self.play(self.matched(parse_mode="strict"), [CutReply("[{},{}"), json.dumps(PATH)])
        self.assertEqual((trace[0]["reply_refusal_reason"], trace[0]["salvaged_steps"], row["repair_calls"]),
                         ("wrong_length", 2, 1))
        self.assertEqual(row["correct_deliveries"], 1)

    def test_every_cut_position_in_lists_and_wrappers(self):
        for own, entries in ((False, [{A: 'move(escaped " }, ])'}, {}, {A: RED}]), (True, [TO_B, None, {A: "wait"}])):
            wrapper = A if own else "steps"
            for prologue in ("", "Explained for Agent[0.5, 0.5].\n```json\n"):
                for opener, closer in (("[", "]"), ("{" + json.dumps(wrapper) + ": [", "]}")):
                    items = [json.dumps(entry) for entry in entries]
                    intro = prologue + opener
                    full = intro + ", ".join(items) + closer
                    ends = [len(intro + ", ".join(items[:n])) for n in (1, 2, 3)]
                    for cut in range(len(full) + 1):
                        prefix = cut_reply_prefix(full[:cut], 3, own=own, speaker=A, agent_positions={(.5, .5)})
                        self.assertEqual(prefix[1] if prefix else 0, sum(end <= cut for end in ends), full[:cut])

    def test_final_reply_attempt_salvages_after_transport_and_two_zero_step_cuts(self):
        raw = json.dumps(PATH[:2])[:-1] + ', {"unfinished'
        row, (call,), _ = self.transport(self.matched(), [http_response(429), completion("", "length"),
                                            completion('[{"', "length"), completion(raw, "length")], "last-reply")
        self.assertEqual((call["attempt_count"], call["reply_attempt_count"], call["transport_attempt_count"]), (4, 3, 1))
        self.assertEqual((call["response_from_attempt"], call["salvaged_steps"], row["steps"]), (4, 2, 2))
        self.assertEqual((row["truncated_attempts"], row["cutoff_attempts_empty"],
                          row["cutoff_attempts_partial_zero_steps"], row["cutoff_attempts_partial_salvaged"]), (3, 1, 1, 1))
        self.assertEqual(row["round_log"][0]["writer_cut_prefix"][0]["attempt"], 4)

    def test_native_length_on_an_otherwise_successful_return_and_discard_retry(self):
        raw = json.dumps(PATH[:2])[:-1]
        body = dict(choices=[dict(message=dict(content=raw), finish_reason="stop", native_finish_reason="max_tokens")],
                    usage=dict(prompt_tokens=12, completion_tokens=8192, cost=.0001))
        row, (call,), _ = self.transport(self.matched(), [http_response(200, json.dumps(body).encode())], "native")
        self.assertEqual((row["steps"], call["attempts"][0]["cut_off"], call["salvaged_steps"]), (2, True, 2))
        spec = replace(self.matched(), cut_answer="discard")
        row, (call,), _ = self.transport(spec, [completion(raw, "length"), completion(json.dumps(PATH))], "discard")
        self.assertEqual((call["attempt_kinds"], row["steps"]), (["truncated", "ok"], 3))
        self.assertNotIn("writer_cut_prefix", row["round_log"][0])
        self.assertNotIn("cut_answer", call)

    def test_resuming_an_interrupted_writer_does_not_duplicate_the_prefix(self):
        spec = self.matched("GROUP")
        out = self.work / "resume"
        out.mkdir()
        for invocation, cap, replies in (("first", 1, [CutReply(json.dumps(PATH[:2])[:-1])]),
                                        ("second", 1, [json.dumps([{}, {}, PATH[2]])])):
            budget = Invocation(out, out / (invocation + ".json"))
            budget.create(cap, 3, "fake")
            with patch("fake_model.reply", side_effect=replies):
                run_episode(spec, out, budget.path, "fake", "correct", 20)
            row = read_json(out / "episodes" / spec.name / "episode.json")
            self.assertEqual((len(row["round_log"][0]["writer_cut_prefix"]), row["cut_prefix_robot_steps_kept"]), (1, 4))
            self.assertEqual(row["success_failure"], CALL_LIMIT if invocation == "first" else "success")
        self.assertEqual((row["api_calls"], row["correct_deliveries"]), (2, 1))

    def test_cli_groups_prefix_policy_and_robot_steps_in_both_tables(self):
        common = ("run_chen2d.py", "--model", "fake", "--fake-script", "cut:[{},", "--protocol", "matched",
                  "--frameworks", "CMAS,GROUP,OWN", "--group-size", 2, "--horizon", 3, "--conditions", "static",
                  "--envs", "0", "--max-planning-rounds", 1, "--failed-writer", "idle")
        for setting in ("prefix", "discard"):
            out = self.work / setting
            run = cli(*common, "--cut-answer", setting, "--out", out)
            self.assertEqual(run.returncode, 0, run.stderr)
            with (out / "episodes.csv").open() as f:
                rows = list(csv.DictReader(f))
            self.assertEqual(len(rows), 3)
            self.assertEqual("cutoff_attempts_partial_salvaged" in rows[0], setting == "prefix")
        summary = cli("summarize.py", "--by", "planning", self.work / "prefix", self.work / "discard")
        self.assertEqual(summary.returncode, 0, summary.stderr)
        tables = summary.stdout.split("Matched protocol, delivered boxes and writer failures\n")
        self.assertEqual(len(tables), 2)
        for table in tables:
            cells = table_rows(table, "model |")
            self.assertEqual(len(cells), 6)
            for cell in cells:
                keys = list(cell)
                start = keys.index("cut_answer") + 1
                self.assertEqual(keys[start:start + 2], ["correct_deliveries", "box_count"])
                if cell["cut_answer"] == "prefix":
                    writers = {"CMAS": 1, "GROUP": 2, "OWN": 4}[cell["framework"]]
                    self.assertEqual((cell["cutoff_attempts_partial_salvaged"], cell["cut_prefix_robot_steps_kept"],
                                      cell["cut_prefix_robot_steps_not_written"]), (str(writers), "4", "8"))
        self.assertNotEqual(cli(*common, "--cut-answer", "discard", "--out", self.work / "prefix").returncode, 0)
        self.assertNotEqual(cli(*common, "--protocol", "legacy", "--cut-answer", "prefix", "--out", self.work / "bad").returncode, 0)
