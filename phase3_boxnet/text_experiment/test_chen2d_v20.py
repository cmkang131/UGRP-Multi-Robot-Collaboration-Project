from regression_inputs import REGRESSION
"""Offline regressions for writer-local failures, stalled rounds and delivery-normalized cost."""
import csv
import io
import json
from contextlib import redirect_stdout
from dataclasses import replace
from unittest.mock import patch

import cost
import fake_model
from LLM import MODEL, load_real_api
from episode import run_episode
from limits import CALL_LIMIT, MODEL_SERVICE, OUTPUT_LIMIT, UNUSABLE_REPLY, Invocation
from planning_metrics import MATCHED_CALL_CAP, MATCHED_ENV_CAP, MATCHED_ROUND_CAP, matched_cell_metrics, print_matched_table
from prompt_env1 import OWN_DIALOGUE
from storage import ROOT, read_json
from summarize import read_episode_rows
from test_chen2d import calls, fixture_spec
from test_chen2d_v3 import BOARD, scripted_transport
from test_chen2d_v4 import cli
from test_chen2d_v5 import local_references
from test_chen2d_v11 import A, B, C, D, BAD, ONE, PATH, RED, HorizonFixtures
from test_chen2d_v17_retry import http_response
from test_chen2d_v19 import TWO_WRITERS, completion


def peer_lists(call):
    slot = call["messages"][1]["content"].split(OWN_DIALOGUE, 1)[1]
    return json.JSONDecoder().raw_decode(slot)[0]


def table_rows(table, header):
    lines = table.splitlines()
    start = next(i for i, line in enumerate(lines) if line.startswith(header))
    return list(csv.DictReader((line.replace(" | ", "|") for line in lines[start:]), delimiter="|"))


class IdleWriterTests(HorizonFixtures):
    def matched(self, fw="CMAS", board=BOARD, horizon=1, **options):
        return self.spec(board, fw, horizon, protocol="matched", failed_writer="idle",
                         group_size=2 if fw == "GROUP" else None, **options)

    def nine_robots(self, fw, rounds):
        board = {f"{r+.5}_{c+.5}": ["box_red", "target_red"] * 2 for r in range(3) for c in range(3)}
        base = fixture_spec(self.work / "nine.json", board, "static", rows=3, cols=3, protocol="matched",
                            map_set="scaled:2", boxes_per_robot=2.0, box_count=18)
        return replace(base, framework=fw, group_size=3 if fw == "GROUP" else None, failed_writer="idle",
                       horizon=2, max_planning_rounds=rounds)

    def scripted(self, spec, replies, tag, *, invocation="first", max_calls=None):
        out = self.work / tag
        out.mkdir(exist_ok=True)
        budget = Invocation(out, out / (invocation + ".json"))
        budget.create(max_calls, 3, MODEL)
        with local_references(), scripted_transport([]) as (sent, _):
            with patch.object(load_real_api().http.client.HTTPSConnection, "getresponse", side_effect=replies):
                run_episode(spec, out, budget.path, MODEL, "correct", 100, 8192)
        self.assertEqual(len(sent), len(replies))
        self.assertEqual(read_json(budget.path)["calls"], len(sent))
        folder = out / "episodes" / spec.name
        return read_json(folder / "episode.json"), calls(folder)

    def test_blocked_own_and_row_keep_peers_moving_for_the_whole_horizon(self):
        answer = fake_model.reply
        for fw, script, cause, scope, writers in (
                ("OWN", "invalid", "not-doable actions", [A], 9),
                ("GROUP", "non-json", "unusable replies after repairs", [A, B, "Agent[0.5, 2.5]"], 3)):
            with self.subTest(fw=fw):
                marker = (f"choosing only the action of {A}." if fw == "OWN" else f'choosing actions only for ["{A}",')
                def selective(messages, _):
                    return answer(messages, script if marker in messages[1]["content"] else "correct")
                row, trace, _ = self.play(self.nine_robots(fw, 1), selective, fw)
                batch, = row["round_log"]
                event, = batch["writer_blocked"]
                self.assertEqual((row["success_failure"], row["steps"], row["correct_deliveries"], row["box_count"]),
                                 (MATCHED_ROUND_CAP, 2, 18 - 2 * len(scope), 18))
                self.assertEqual(event, dict(event="writer_blocked", planning_round=1, framework=fw, speaker=A,
                    robots=scope, required=True, cause=cause, end_label="Syntactic Error", call=writers + 2,
                    calls=[1, writers + 1, writers + 2], attempts=3, last_call_attempts=1, last_cutoff_class=None,
                    prompt_tokens=33, generated_tokens=21))
                self.assertEqual(peer_lists(trace[1]), {robot: [] for robot in scope})
                self.assertIn("[] means", trace[1]["messages"][1]["content"])
                self.assertEqual(row["first_blocked_cause"], cause)
                self.assertEqual((row["robot_rounds_blocked_by_cause"], row["writer_calls_blocked_by_cause"]),
                                 ({cause: len(scope)}, {cause: 1}))
                self.assertEqual((row["stalled_rounds"], row["rounds_with_blocked_writer"]), (0, 1))
                for step in row["iterations"]:
                    self.assertTrue(set(scope).isdisjoint(step["issued_plan"]))
                self.assertEqual(batch["executed_writer_calls"], list(range(2, writers + 1)))
                self.assertEqual((row["executed_prompt_tokens"], row["executed_generated_tokens"]),
                                 (11 * (writers - 1), 7 * (writers - 1)))
                self.assertEqual((row["blocked_prompt_tokens"], row["blocked_generated_tokens"],
                                  row["other_prompt_tokens"], row["other_generated_tokens"]), (33, 21, 0, 0))

    def test_blocked_leader_recovers_from_same_board_and_counts_nine_robot_rounds(self):
        spec = self.nine_robots("CMAS", 4)
        actions = {f"Agent[{r+.5}, {c+.5}]": RED for r in range(3) for c in range(3)}
        row, trace = self.scripted(spec, [completion("", "length"), completion(" ", "length"),
                                         completion(" [", "length"), completion(json.dumps([actions] * 2))], "leader")
        first, second = row["round_log"]
        event, = first["writer_blocked"]
        self.assertEqual(trace[0]["messages"], trace[1]["messages"])
        self.assertEqual((first["stalled"], first["empty_steps_skipped"], second["stalled"]), (True, 2, False))
        self.assertEqual((event["attempts"], event["last_cutoff_class"], event["prompt_tokens"], event["generated_tokens"]),
                         (3, "partial", 36, 24576))
        self.assertEqual((row["robot_rounds_blocked_by_cause"], row["writer_calls_blocked_by_cause"]),
                         ({"output limit": 9}, {"output limit": 1}))
        self.assertEqual((row["success_failure"], row["correct_deliveries"], row["steps"], row["stalled_rounds"]),
                         ("success", 18, 2, 1))
        self.assertEqual((row["blocked_generated_tokens"], row["executed_generated_tokens"]), (24576, 8192))
        self.assertEqual(row["tokens_per_delivered_box"], 4 * (12 + 8192) / 18)
        self.assertEqual((row["first_blocked_round"], row["first_blocked_cause"]), (1, "output limit"))
        self.assertFalse(row["cut_calls"][0]["terminal"])

    def test_client_cutoff_idles_only_one_writer_and_counts_retries(self):
        spec = self.matched("OWN", board=TWO_WRITERS, max_planning_rounds=1)
        row, trace = self.scripted(spec, [completion("", "length")] * 3 + [
            completion("[null]"), completion('["move(box_blue, target_blue)"]'), completion("[null]")], "own-cut")
        self.assertEqual(peer_lists(trace[1]), {A: []})
        self.assertEqual((row["steps"], row["correct_deliveries"], row["stalled_rounds"]), (1, 1, 0))
        self.assertEqual((row["api_calls"], row["cutoff_attempts_empty"], row["writer_calls_blocked_by_cause"]),
                         (6, 3, {"output limit": 1}))
        self.assertEqual((row["blocked_prompt_tokens"], row["executed_prompt_tokens"], row["other_prompt_tokens"]),
                         (36, 12, 24))

    def test_stall_limit_uses_last_required_cause_in_call_order(self):
        spec = self.matched("GROUP", board=TWO_WRITERS, max_stalled_rounds=2)
        cut = completion("  ", "length")
        bad_body = http_response(200, b"{")
        row, trace = self.scripted(spec, [cut] * 6 + [bad_body] * 3 + [completion("[", "length")] * 3, "two-stalls")
        self.assertEqual((row["success_failure"], row["steps"], len(trace), row["api_calls"]), (OUTPUT_LIMIT, 0, 4, 12))
        self.assertEqual((row["stalled_rounds"], row["rounds_with_blocked_writer"], row["first_blocked_round"]), (2, 2, 1))
        self.assertEqual(row["writer_calls_blocked_by_cause"], {"output limit": 3, "unusable replies after client retries": 1})
        self.assertEqual((row["rounds_all_attempts_cutoff_empty"], row["rounds_all_attempts_cutoff_partial"]), (1, 1))
        self.assertEqual(row["round_log"][-1]["stall_call"], 4)
        self.assertTrue(row["cut_calls"][-1]["terminal"])
        self.assertIsNone(row["tokens_per_delivered_box"])
        self.assertIsNone(row["blocked_prompt_tokens"])  # unmetered bad bodies propagate
        self.assertEqual(row["executed_prompt_tokens"], 0)

    def test_consecutive_stalls_keep_first_cause_and_end_on_a_different_last_cause(self):
        spec = self.matched(max_stalled_rounds=2)
        replies = [completion("[", "length"), *[http_response(503)] * 3, *[http_response(200, b"{")] * 3]
        row, _ = self.scripted(spec, replies, "different-causes")
        first, last = row["round_log"]
        self.assertEqual((row["stalled_rounds"], row["first_blocked_cause"], row["success_failure"]),
                         (2, "output limit", UNUSABLE_REPLY))
        event, = first["writer_blocked"]
        self.assertEqual((event["attempts"], event["last_cutoff_class"]), (4, "partial"))
        self.assertEqual(last["stall_cause"], "unusable replies after client retries")

    def test_optional_cutoff_counts_without_causing_a_stall_or_overwriting_its_cause(self):
        spec = self.matched("GROUP", max_stalled_rounds=1)
        cut = completion("chunk", "length")
        delivery = completion(json.dumps([{A: "move(box_blue, target_blue)"}]))
        row, _ = self.scripted(spec, [delivery, *[cut] * 3], "optional")
        event, = row["round_log"][0]["writer_blocked"]
        self.assertFalse(event["required"])
        self.assertEqual((row["strict_success"], row["stalled_rounds"], row["rounds_with_blocked_writer"]), (True, 0, 1))
        row, _ = self.scripted(spec, [completion(" ", "length")] * 3 + [cut] * 3, "optional-last")
        self.assertEqual(row["success_failure"], OUTPUT_LIMIT)
        self.assertEqual((row["round_log"][0]["stall_call"], row["round_log"][0]["all_cutoff_last_class"]), (1, "empty"))
        self.assertEqual([c["terminal"] for c in row["cut_calls"]], [True, False])
        row, _ = self.scripted(spec, [completion("[{}]"), *[cut] * 3], "optional-after-wait")
        self.assertEqual((row["success_failure"], row["round_log"][0]["stall_cause"]), ("no actions proposed",) * 2)

    def test_repair_after_a_later_speakers_block_receives_the_empty_peer_lists(self):
        spec = self.matched("GROUP")
        delivery = completion(json.dumps([{A: "move(box_blue, target_blue)"}]))
        row, trace = self.scripted(spec, [completion("?"), *[completion("", "length")] * 3, delivery], "repair-view")
        self.assertTrue(row["strict_success"])
        self.assertEqual(trace[-1]["messages"][1], trace[0]["messages"][1])
        repair = trace[-1]["messages"][-1]["content"]
        self.assertEqual(json.JSONDecoder().raw_decode(repair.split(OWN_DIALOGUE)[1])[0], {C: [], D: []})

    def test_last_repair_client_failure_counts_only_its_writer_chain(self):
        spec = self.matched("OWN", board=TWO_WRITERS, max_planning_rounds=1)
        bad = http_response(200, b"{")
        row, trace = self.scripted(spec, [completion("?"), completion("[null]"),
            completion('["move(box_blue, target_blue)"]'), completion("[null]"),
            completion("?"), completion("partial", "length"), bad, bad], "repair-client")
        event, = row["round_log"][0]["writer_blocked"]
        self.assertEqual((event["cause"], event["end_label"], event["call"], event["calls"]),
                         ("unusable replies after client retries", UNUSABLE_REPLY, 6, [1, 5, 6]))
        self.assertEqual((event["attempts"], event["last_call_attempts"], event["last_cutoff_class"]), (5, 3, None))
        self.assertEqual((row["steps"], row["correct_deliveries"], len(trace)), (1, 1, 6))
        self.assertEqual(row["round_log"][0]["executed_writer_calls"], [3])

    def test_valid_action_resets_streak_and_rejected_future_step_can_stall(self):
        spec = self.matched(board=ONE, max_stalled_rounds=2)
        row, _, _ = self.play(spec, ["[{}]", json.dumps([PATH[0]]), "[{}]", "?", "?", "?"], "reset")
        self.assertEqual((row["steps"], row["planning_rounds"], row["stalled_rounds"], row["success_failure"]),
                         (1, 4, 3, "Syntactic Error"))
        self.assertEqual([b["stalled"] for b in row["round_log"]], [True, False, True, True])
        self.assertEqual(row["first_blocked_cause"], "no actions proposed")
        spec = self.matched(board=ONE, horizon=2, max_stalled_rounds=1)
        row, _, _ = self.play(spec, [json.dumps([{}, {A: BAD}])], "rejected")
        self.assertEqual((row["success_failure"], row["first_blocked_cause"], row["rounds_with_blocked_writer"]),
                         ("Syntactic Error", "not-doable actions", 0))
        self.assertEqual((row["stalled_rounds"], row["executed_prompt_tokens"], row["other_prompt_tokens"]), (1, 0, 11))

    def test_all_waits_use_default_three_and_all_failed_first_steps_have_the_existing_label(self):
        row, _, _ = self.play(self.matched(), ["[{}]"] * 3, "waits")
        self.assertEqual((row["success_failure"], row["max_stalled_rounds"], row["stalled_rounds"],
                          row["other_prompt_tokens"]), ("no actions proposed", 3, 3, 33))
        row, _, _ = self.play(self.matched(max_stalled_rounds=1), [json.dumps([{A: BAD}])] * 3, "invalid")
        self.assertEqual((row["success_failure"], row["first_blocked_cause"], row["stalled_rounds"]),
                         ("Syntactic Error", "not-doable actions", 1))
        row, _ = self.scripted(self.matched(max_stalled_rounds=1), [http_response(200, b"{")] * 3, "client-end")
        self.assertEqual((row["success_failure"], row["stalled_rounds"]), (UNUSABLE_REPLY, 1))

    def test_service_and_hard_ceilings_stop_without_inventing_stalled_rounds(self):
        for optional in (False, True):
            spec = self.matched("GROUP", max_stalled_rounds=1)
            prefix = [completion("[{}]")] if optional else []
            row, _ = self.scripted(spec, prefix + [http_response(503)] * 3, f"service-{optional}")
            self.assertEqual((row["success_failure"], row["first_blocked_cause"], row["stalled_rounds"]),
                             (MODEL_SERVICE, "model service", 0))
            self.assertEqual(row["writer_calls_blocked_by_cause"], {})
        row, _, _ = self.play(self.matched("OWN"), ["[null]"], "mid-sweep", ceiling=1)
        self.assertEqual((row["success_failure"], row["stalled_rounds"], row["round_log"][0]["stalled"]),
                         (MATCHED_CALL_CAP, 0, None))
        row, _, _ = self.play(self.matched(board=ONE, max_env_steps=1), [json.dumps([PATH[0]])], "env")
        self.assertEqual((row["success_failure"], row["stalled_rounds"]), (MATCHED_ENV_CAP, 0))
        row, _, _ = self.play(self.matched(max_planning_rounds=1), ["[{}]"], "round")
        self.assertEqual((row["success_failure"], row["stalled_rounds"]), (MATCHED_ROUND_CAP, 1))

    def test_repaired_executed_list_and_resume_count_each_attempt_once(self):
        spec = self.matched(max_stalled_rounds=3)
        cut = completion("", "length")
        first, _ = self.scripted(spec, [cut] * 4, "resume", max_calls=4)
        self.assertEqual((first["success_failure"], first["stalled_rounds"], first["blocked_prompt_tokens"],
                          first["other_prompt_tokens"]), (CALL_LIMIT, 1, 36, 12))
        row, trace = self.scripted(spec, [completion("?"), completion(json.dumps([{A: "move(box_blue, target_blue)"}]))],
                                   "resume", invocation="next")
        self.assertEqual((row["success_failure"], row["api_calls"], len(trace)), ("success", 6, 3))
        self.assertEqual((row["blocked_prompt_tokens"], row["executed_prompt_tokens"], row["other_prompt_tokens"]),
                         (36, 12, 24))
        self.assertEqual(row["round_log"][-1]["executed_writer_calls"], [3])

    def test_drop_and_fail_keep_prior_labels_and_records(self):
        for policy in ("drop", "fail"):
            spec = replace(self.matched("OWN", board=TWO_WRITERS), failed_writer=policy, max_stalled_rounds=None)
            row, trace = self.scripted(spec, [completion("", "length")] * 3, policy)
            self.assertEqual((row["success_failure"], row["steps"], len(trace)), (OUTPUT_LIMIT, 0, 1))
            self.assertNotIn("writer_blocked", row["round_log"][0])
            self.assertNotIn("max_stalled_rounds", row)
            self.assertNotIn("blocked_prompt_tokens", row)

    def test_weighted_delivery_denominator_and_archive_unknowns_in_both_reports(self):
        spec = self.matched(board=TWO_WRITERS, max_planning_rounds=1)
        partial, _, _ = self.play(spec, [json.dumps([{A: RED}])], "partial")
        full, _, _ = self.play(spec, ["?", json.dumps([{A: RED, C: "move(box_blue, target_blue)"}])], "full")
        empty, _, _ = self.play(spec, ["[{}]"], "zero")
        rows = [partial, full, empty]
        table = io.StringIO()
        print_matched_table(rows, table)
        cell, = table_rows(table.getvalue(), "model |")
        keys = list(cell)
        self.assertEqual(keys[keys.index("max_stalled_rounds") + 1:][:2], ["correct_deliveries", "box_count"])
        self.assertEqual((cell["correct_deliveries"], cell["box_count"], cell["total_tokens"],
                          float(cell["tokens_per_delivered_box"])), ("3", "6", "72", 24))
        self.assertEqual(float(cell["executed_prompt_tokens"]), 22)
        names = {str(i): dict(row, env_seed=i) for i, row in enumerate(rows)}
        with redirect_stdout(io.StringIO()) as output:
            cost.report(self.work, names, names, 0, 10)
        lookup = table_rows(output.getvalue(), "size | framework")[0]
        self.assertEqual([float(lookup[k]) for k in ("delivered boxes", "total boxes", "total tokens",
                                                     "tokens per delivered box")], [3, 6, 72, 24])
        zero = matched_cell_metrics([empty])
        self.assertEqual((zero["tokens_per_delivered_box"], zero["total_tokens"], zero["correct_deliveries"]), (None, 18, 0))
        archive = read_episode_rows(REGRESSION / "chen2d-19/pilot-fake")
        old = matched_cell_metrics(archive)
        self.assertEqual(old["correct_deliveries"], old["box_count"])
        self.assertIsNone(old["robot_rounds_blocked_by_cause"])
        self.assertIsNone(old["blocked_prompt_tokens"])

    def test_cli_saves_caps_groups_them_and_rejects_mixed_resume(self):
        common = ("run_chen2d.py", "--model", "fake", "--fake-script", "non-json", "--protocol", "matched",
                  "--failed-writer", "idle", "--frameworks", "CMAS", "--conditions", "static", "--envs", "0")
        outs = []
        for k in (1, 3):
            out = self.work / str(k)
            flags = ("--max-stalled-rounds", str(k)) if k == 1 else ()
            run = cli(*common, *flags, "--out", out)
            self.assertEqual(run.returncode, 0, run.stderr)
            outs.append(out)
            self.assertEqual(read_json(out / "run.json")["max_stalled_rounds"], k)
            with (out / "episodes.csv").open() as handle:
                row, = csv.DictReader(handle)
            self.assertEqual(int(row["stalled_rounds"]), k)
            self.assertEqual(row["tokens_per_delivered_box"], "NA")
            self.assertEqual(json.loads(row["writer_calls_blocked_by_cause"]), {"unusable replies after repairs": k})
        summary = cli("summarize.py", "--by", "planning", *outs)
        self.assertEqual(summary.returncode, 0, summary.stderr)
        _, table = summary.stdout.split("Matched protocol, delivered boxes and writer failures\n")
        cells = table_rows(table, "model |")
        self.assertEqual({r["max_stalled_rounds"] for r in cells}, {"1", "3"})
        self.assertTrue(all(r["tokens_per_delivered_box"] == "NA" for r in cells))
        cost_table = cli("cost.py", outs[0])
        self.assertEqual(cost_table.returncode, 0, cost_table.stderr)
        cell = table_rows(cost_table.stdout, "size | framework")[0]
        self.assertEqual([cell[k] for k in ("delivered boxes", "total tokens", "tokens per delivered box")], ["0", "54", "NA"])
        refused = cli(*common, "--max-stalled-rounds", 2, "--out", outs[0])
        self.assertIn("Run settings", refused.stderr)
        for flags in (("--max-stalled-rounds", 0), ("--protocol", "legacy"),
                      ("--failed-writer", "drop", "--max-stalled-rounds", 2)):
            result = cli(*common, *flags, "--out", self.work / "invalid-option")
            self.assertNotEqual(result.returncode, 0)
            self.assertFalse((self.work / "invalid-option/run.json").exists())
