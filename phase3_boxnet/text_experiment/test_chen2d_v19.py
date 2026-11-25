"""Local writer, metering, archive and first-round pairing regressions."""
import io
import json
import runpy
import shutil
import tempfile
import unittest
from pathlib import Path
from regression_inputs import REGRESSION
from unittest.mock import patch

import fake_model
import probe_reading
from LLM import MODEL, load_real_api
from episode import run_episode
from limits import OUTPUT_LIMIT, Invocation
from matched_protocol import build_prompt
from planning_metrics import CUTOFF_SPLITS, print_matched_table
from storage import ROOT, digest, read_json, write_json
from summarize import episode_csv, read_episode_rows
from test_chen2d import calls
from test_chen2d_v3 import BOARD, scripted_transport
from test_chen2d_v4 import cli
from test_chen2d_v5 import local_references
from test_chen2d_v11 import A, B, C, D, HorizonFixtures
from test_chen2d_v17_retry import http_response


V18 = REGRESSION / "chen2d-18/h5-2x3"
NOTE = ("The job may need more than 5 steps: plan only the next 5 steps; "
        "after they are executed, another planning round continues from the new state.")
SINGULAR = ("The job may need more than 1 step: plan only the next 1 step; "
            "after it is executed, another planning round continues from the new state.")
TWO_WRITERS = {"0.5_0.5": ["box_red", "target_red"], "0.5_1.5": [],
               "1.5_0.5": ["box_blue", "target_blue"], "1.5_1.5": []}


def completion(text, finish="stop"):
    body = dict(choices=[dict(message=dict(content=text), finish_reason=finish)],
                usage=dict(prompt_tokens=12, completion_tokens=8192,
                           completion_tokens_details=dict(reasoning_tokens=8282), cost=.0001))
    return http_response(200, json.dumps(body).encode())


class WriterTests(HorizonFixtures):
    def matched(self, fw, *, board=TWO_WRITERS, **kwargs):
        return self.spec(board, fw, 1, protocol="matched", group_size=2 if fw == "GROUP" else None,
                         max_planning_rounds=1, **kwargs)

    def transport_episode(self, spec, replies, tag):
        out = self.work / tag
        out.mkdir()
        budget = Invocation(out, out / "meter.json")
        budget.create(None, 3, MODEL)
        with local_references(), scripted_transport([]) as (sent, _):
            connection = load_real_api().http.client.HTTPSConnection
            with patch.object(connection, "getresponse", side_effect=replies):
                run_episode(spec, out, budget.path, MODEL, "correct", 99, 8192)
        folder = out / "episodes" / spec.name
        self.assertEqual(len(sent), len(replies))
        return read_json(folder / "episode.json"), calls(folder)

    def test_note_is_the_only_byte_change_from_v18_for_each_role(self):
        archive = V18 / "source/matched_protocol.py"
        self.assertEqual(digest(archive.read_bytes()), read_json(V18 / "run.json")["source_sha256"][archive.name])
        previous = runpy.run_path(str(archive))["build_prompt"]
        board = read_json(V18 / "maps/2x3/env0.json")
        roles = ({}, {"block": (C, D, "Agent[1.5, 2.5]")}, {"robot": (1, 2)})
        for role in roles:
            for h, note in ((1, SINGULAR), (5, NOTE)):
                for position in ("before", "after"):
                    opts = dict(horizon=h, history_method="authors", history_window=1000,
                                state_position=position, earlier={A: [None] * h}, **role)
                    base = previous(2, 3, board, [], [board], **opts)
                    for option in ({}, {"plan_note": "none"}):
                        self.assertEqual(build_prompt(2, 3, board, [], [board], **opts, **option).encode(), base.encode())
                    request = f"Return a JSON list for the next {h} steps in execution order."
                    actual = build_prompt(2, 3, board, [], [board], **opts, plan_note="continue")
                    self.assertEqual(actual, base.replace(request, request + "\n" + note))
                    self.assertEqual(actual.state_offset, base.state_offset)

    def test_all_roles_and_repairs_keep_note_and_last_repair_can_recover(self):
        for fw, writers in (("CMAS", 1), ("GROUP", 2), ("OWN", 4)):
            spec = self.matched(fw, plan_note="continue", failed_writer="fail")
            answer = fake_model.reply
            row, trace, _ = self.play(spec, lambda msgs, _: answer(msgs, "invalid" if len(msgs) < 6 else "correct"), fw)
            self.assertTrue(row["strict_success"])
            self.assertEqual((len(trace), row["repair_calls"]), (3 * writers, 2 * writers))
            self.assertEqual((row["plan_note"], row["failed_writer"]), ("continue", "fail"))
            for call in trace:
                self.assertEqual(call["plan_note"], "continue")
                self.assertEqual(call["messages"][1]["content"].count(SINGULAR), 1)
                self.assertEqual(call["attempts"][0]["visible_reply_chars"], len(call["response"]))

    def test_required_writer_fails_before_execution_with_cmas_label_and_cause(self):
        answer = fake_model.reply
        for script, cause in (("non-json", "unusable replies after repairs"), ("invalid", "not-doable actions")):
            for fw in ("CMAS", "GROUP", "OWN"):
                def selective(messages, _):
                    prompt = messages[1]["content"]
                    chosen = (fw == "CMAS" or f"choosing only the action of {C}." in prompt or
                              f'choosing actions only for ["{C}",' in prompt)
                    return answer(messages, script if chosen else "correct")
                row, trace, _ = self.play(self.matched(fw, failed_writer="fail"), selective, script + fw)
                self.assertEqual((row["success_failure"], row["first_blocked_round"], row["first_blocked_cause"],
                                  row["steps"], row["robots_dropped"]), ("Syntactic Error", 1, cause, 0, 0))
                self.assertEqual(row["round_log"][0]["failed_call"], trace[-1]["number"])
                self.assertEqual(row["repair_calls"], 2)
                if fw != "CMAS":
                    dropped, _, _ = self.play(self.matched(fw), selective, script + fw + "-drop")
                    self.assertEqual((dropped["steps"], dropped["correct_deliveries"]), (1, 1))
                    self.assertGreater(dropped["robots_dropped"], 0)

    def test_idle_only_assignment_can_exhaust_repairs_while_a_teammate_serves(self):
        answer = fake_model.reply
        for fw, target in (("GROUP", f'choosing actions only for ["{C}",'), ("OWN", f"choosing only the action of {B}.")):
            spec = self.matched(fw, board=BOARD, failed_writer="fail")
            row, _, _ = self.play(spec, lambda msgs, _: answer(msgs, "non-json" if target in msgs[1]["content"] else "correct"), fw)
            self.assertEqual((row["strict_success"], row["repair_calls"], row["robots_dropped"]),
                             (True, 2, 2 if fw == "GROUP" else 1))

    def test_raw_lengths_and_last_cut_ignore_reasoning_and_transport(self):
        for fw in ("CMAS", "GROUP", "OWN"):
            spec = self.matched(fw, board=BOARD, failed_writer="fail")
            for last, end_class in ((None, "empty"), (" \t", "empty"), (" 가", "partial")):
                replies = [completion("", "length"), completion(" [", "length"), http_response(503),
                           completion(last, "length")]
                row, trace = self.transport_episode(spec, replies, fw + str(last))
                self.assertEqual((row["success_failure"], row["first_blocked_cause"], row["steps"]),
                                 (OUTPUT_LIMIT, "output limit", 0))
                attempts = trace[0]["attempts"]
                self.assertEqual([a["visible_reply_chars"] for a in attempts], [0, 2, 0, len(last or "")])
                self.assertEqual([a["cutoff_reply_class"] for a in attempts], ["empty", "partial", None, end_class])
                self.assertEqual(attempts[0]["reasoning_tokens"], 8282)
                self.assertEqual(row["cutoff_attempts_empty"], 1 + int(end_class == "empty"))
                self.assertEqual(row["cutoff_attempts_partial"], 1 + int(end_class == "partial"))
                self.assertEqual(row["rounds_all_attempts_cutoff_" + end_class], 1)
                self.assertEqual(row["round_log"][0]["all_cutoff_last_class"], end_class)

    def test_recovered_required_cutoff_and_exhausted_optional_cutoff(self):
        spec = self.matched("GROUP", board=BOARD, failed_writer="fail")
        delivery = json.dumps([{A: "move(box_blue, target_blue)"}])
        replies = [completion("   ", "length"), completion(delivery), *[completion("x", "length")] * 3]
        row, trace = self.transport_episode(spec, replies, "recovered")
        self.assertEqual((row["strict_success"], row["cutoff_attempts_empty"], row["cutoff_attempts_partial"],
                          row["rounds_all_attempts_cutoff"], row["robots_dropped"]), (True, 1, 3, 0, 2))
        self.assertEqual((trace[0]["attempts"][0]["visible_reply_chars"], trace[1]["failure"]), (3, OUTPUT_LIMIT))

    def test_group_required_when_its_speaker_is_idle_and_a_member_can_act(self):
        board = {key: list(items) for key, items in TWO_WRITERS.items()}
        board["1.5_0.5"], board["1.5_1.5"] = [], board["1.5_0.5"]
        spec = self.matched("GROUP", board=board, failed_writer="fail")
        row, trace, _ = self.play(spec, ["[{}]", "?", "?", "?"], "idle-leader")
        self.assertEqual((trace[-1]["speaker"], trace[-1]["assigned_robots_with_doable_actions"]), (C, 1))
        self.assertEqual((row["steps"], row["first_blocked_cause"], row["success_failure"]),
                         (0, "unusable replies after repairs", "Syntactic Error"))


class ArchiveAndProbeTests(unittest.TestCase):
    def setUp(self):
        scratch = tempfile.TemporaryDirectory(dir=ROOT, prefix=".chen19-test-")
        self.addCleanup(scratch.cleanup)
        self.work = Path(scratch.name)

    def test_old_run_summarizes_with_text_missing_text_and_missing_call_files(self):
        # A frozen v18 folder is readable directly. Modify only a local copy for cut cases.
        self.assertTrue(all(r["plan_note"] == "none" for r in read_episode_rows(V18)))
        write_json(self.work / "run.json", read_json(V18 / "run.json"))
        name = "2x3_CMAS_static_env0"
        directory = self.work / "episodes" / name
        (directory / "calls").mkdir(parents=True)
        row = read_json(V18 / "episodes" / name / "episode.json")
        n = row["round_log"][-1]["planning_round"]
        row["round_log"][-1]["cutoff_class"] = "all attempts cut off"
        row.update(rounds_no_cutoff=row["rounds_no_cutoff"] - 1, rounds_all_attempts_cutoff=1,
                   truncated_attempts=3, success_failure=OUTPUT_LIMIT, strict_success=False,
                   cut_calls=[dict(call=1, planning_round=n, attempts=3, terminal=True, role="leader")])
        write_json(directory / "episode.json", row)
        call = dict(number=1, failure=OUTPUT_LIMIT, response=None, attempts=[
            dict(api_calls=1, kind="truncated", cut_off=True, raw_output=" \t"),
            dict(api_calls=1, kind="truncated", cut_off=True),
            dict(api_calls=1, kind="truncated", cut_off=True, raw_output="초안"),
            dict(api_calls=1, kind="http_5xx", cut_off=None)])
        path = directory / "calls/00001.json"
        call["attempts"][1]["attempt_id"] = "archived-reply"
        write_json(path, call)
        for index, (attempt_counts, round_counts) in enumerate((((1, 1, 1), (0, 1, 0)), ((2, 1, 0), (0, 1, 0)),
                                                                ((0, 0, 3), (0, 0, 1)))):
            old, = episode_csv(self.work)
            self.assertEqual(tuple(old[k] for k in CUTOFF_SPLITS), attempt_counts + round_counts)
            table = io.StringIO()
            print_matched_table([old], table)
            _, header, line = table.getvalue().splitlines()
            values = dict(zip(header.split(" | "), line.split(" | "), strict=True))
            self.assertEqual(tuple(int(values[k]) for k in CUTOFF_SPLITS), attempt_counts + round_counts)
            self.assertEqual(read_json(directory / "episode.json"), row)
            if index == 0:
                (directory / "client-calls.jsonl").write_text('{"attempt_id":"archived-reply","raw_output":""}\n')
            elif index == 1:
                path.unlink()
        shutil.copyfile(V18 / "assignments.json", self.work / "assignments.json")
        shutil.copytree(V18 / "invocations", self.work / "invocations")
        checked = cli("summarize.py", "--by", "planning", self.work)
        self.assertEqual(checked.returncode, 0, checked.stderr)
        self.assertIn("rounds_all_attempts_cutoff_unknown", checked.stdout)

    def test_new_settings_persist_and_cannot_be_changed_on_resume(self):
        out = self.work / "pilot"
        common = ("run_chen2d.py", "--model", "fake", "--protocol", "matched", "--frameworks", "CMAS,GROUP,OWN",
                  "--group-size", "2", "--conditions", "static", "--envs", "0", "--max-planning-rounds", "1",
                  "--out", out)
        checked = cli(*common, "--plan-note", "continue", "--failed-writer", "fail")
        self.assertEqual(checked.returncode, 0, checked.stderr)
        cfg = read_json(out / "run.json")
        self.assertEqual((cfg["plan_note"], cfg["failed_writer"]), ("continue", "fail"))
        for folder in (out / "episodes").iterdir():
            self.assertTrue(all(c["plan_note"] == "continue" for c in calls(folder)))
        for change in (("--failed-writer", "fail"), ("--plan-note", "continue")):
            refusal = cli(*common, *change)
            self.assertNotEqual(refusal.returncode, 0)
            self.assertIn("Run settings", refusal.stderr)

    def test_both_probe_entry_points_accept_note_for_saved_states(self):
        source = V18 / "episodes/2x3_CMAS_static_env0"
        for module in ("probe_reading.py", "probe_wording.py"):
            out = self.work / module
            run = cli(module, "--episodes", source, "--out", out, "--callers", "leader", "--per-episode", "1",
                      "--arms", "none", "--protocol", "matched", "--plan-note", "continue", "--horizon", "5")
            self.assertEqual(run.returncode, 0, run.stderr)
            self.assertEqual(read_json(out / "config.json")["plan_note"], "continue")
            call, = (out / "cells").glob("*/calls/00001.json")
            record = read_json(call)
            self.assertEqual(record["plan_note"], "continue")
            self.assertIn(NOTE, record["messages"][1]["content"])

    def first_args(self, *more):
        return probe_reading.parser().parse_args(("--first-round", "--protocol", "matched", "--frameworks",
            "CMAS,GROUP,OWN", "--group-size", "3", "--sizes", "1x3,2x3,3x3", "--map-set", "scaled:2",
            "--envs", "0", "--horizon", "5", "--plan-note", "none,continue", "--out", str(self.work / "probe"), *more))

    def test_every_initial_writer_is_paired_with_identical_inputs_and_resumes_once(self):
        out = self.work / "probe"
        with patch("map_sets.ROOT", self.work):
            first = probe_reading.run(self.first_args("--max-calls", "7"))
            second = probe_reading.run(self.first_args("--jobs", "2"))
            self.assertEqual(probe_reading.run(self.first_args()), [])
        rows = first + second
        self.assertEqual((len(first), len(rows)), (7, 54))
        pairs = {}
        for row in rows:
            key = row["size"], row["framework"], row["writer_index"]
            pairs.setdefault(key, {})[row["plan_note"]] = row
            call, = calls(out / "cells" / row["cell_id"])
            self.assertEqual((call["planning_round"], call["step"], call["attempt_count"], call["plan_note"]),
                             (1, 1, 1, row["plan_note"]))
            self.assertEqual(row["visible_reply_chars"], len(row["reply"]))
        self.assertEqual(len(pairs), 27)
        for (size, fw, index), pair in pairs.items():
            a, b = pair["none"], pair["continue"]
            self.assertEqual(a["messages"][1]["content"], b["prompt"].replace("\n" + NOTE, ""))
            self.assertEqual((a["env_sha256"], a["peer_lists"]), (b["env_sha256"], b["peer_lists"]))
            self.assertEqual(len(a["peer_lists"]), index)
            if fw == "GROUP":
                self.assertEqual(a["physical_caller_role"], "central" if size == "1x3" else "group")
        summary = probe_reading.summarize(out)
        for arm, stats in summary["arms"].items():
            self.assertEqual((stats["attempts"], stats["unasked"], stats["generated_tokens"],
                              stats["reasoning_tokens"]), (27, 0, 189, 54))
            self.assertEqual(stats["visible_reply_chars"], sum(r["visible_reply_chars"] for r in rows if r["arm"] == arm))
            self.assertEqual(stats["usable_replies"], sum(r["usable_reply"] for r in rows if r["arm"] == arm))

    def test_first_round_cut_valid_looking_and_invalid_step_do_not_count_as_usable(self):
        args = self.first_args("--sizes", "1x3", "--frameworks", "CMAS", "--model", MODEL)
        args.group_size = None
        bad_step = json.dumps([{A: "move(box_absent, target_absent)"}] + [{}] * 4)
        replies = [completion("[{}, {}, {}, {}, {}]", "length"), completion(bad_step)]
        with patch("map_sets.ROOT", self.work), local_references(), scripted_transport([]) as (sent, _):
            with patch.object(load_real_api().http.client.HTTPSConnection, "getresponse", side_effect=replies):
                rows = probe_reading.run(args)
        self.assertEqual(len(sent), 2)
        self.assertTrue(all(row["plan_produced"] and not row["usable_reply"] for row in rows))
        arms = probe_reading.summarize(self.work / "probe")["arms"]
        self.assertEqual((arms["none"]["cutoff_attempts_partial"], arms["continue"]["cutoff_attempts_partial"]), (1, 0))
        self.assertEqual((arms["none"]["generated_tokens"], arms["none"]["reasoning_tokens"]), (8192, 8282))
