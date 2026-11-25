"""Folder-local fake replays for relay timing, display, scoring and matched map assignments."""
import csv
import json
import random
import sys
import tempfile
import unittest
from collections import Counter
from dataclasses import replace
from pathlib import Path
from regression_inputs import REGRESSION
from types import SimpleNamespace
from unittest.mock import patch

import LLM
import audit_news
import fake_model
from analysis_runs import read_run
from env1_create import action_from_response, env_create
from episode import Spec, run_episode
from limits import Invocation
from map_events import CAUSE_SLOTS, agent_at, boxes, cell_key, event_path, reference_trajectory
from relay import HEADER, RELAY_DISPLAYS, RELAY_TIMINGS, STATE_HEADERS
from storage import ROOT, code_version, digest, read_json, write_json
from test_chen2d import calls, fixture_spec
from test_chen2d_v4 import cli
from test_chen2d_v5 import local_references
from test_chen2d_v7 import pipe_table

REVIEW = REGRESSION / "chen2d-8"
FIRST, SENDER, THIRD, LAST = [agent_at((r + .5, c + .5)) for r in range(2) for c in range(2)]
BOARD = {"0.5_0.5": ["box_blue", "target_blue"], "0.5_1.5": ["box_red", "target_red"],
         "1.5_0.5": ["box_blue", "target_blue"], "1.5_1.5": ["box_red", "target_red"]}
EMPTY = "EXECUTE\n{}"
INVALID = '{"Agent[0.5, 0.5]":"move(box_missing, target_missing)"}'


def block_in(call):
    marker = STATE_HEADERS["central" if call["role"] == "central" else "local"]
    return HEADER in call["messages"][1]["content"].partition(marker)[0]


class RelayExperimentTests(unittest.TestCase):
    def setUp(self):
        temp = tempfile.TemporaryDirectory(dir=ROOT, prefix=".chen8-test-")
        self.addCleanup(temp.cleanup)
        self.work = Path(temp.name)

    def spec(self, framework="DMAS", timing="turn", display="persistent"):
        path = self.work / "board.json"
        spec = fixture_spec(path, BOARD, "e1", dropoff="always", speech="auto", tell="member", event_step_override=1)
        sidecar = event_path(path)
        assignment = dict(read_json(sidecar), A="blue", D=[.5, 1.5], M=SENDER, L=LAST)
        write_json(sidecar, assignment)
        return replace(spec, framework=framework, relay_timing=timing, relay_display=display,
                       event_hash=digest(sidecar.read_bytes()))

    def play(self, spec, tag, responder, ceiling=100):
        out = self.work / tag
        out.mkdir()
        budget = Invocation(out, out / "budget.json")
        budget.create(None, 2, "fake")
        with patch.object(fake_model, "reply", side_effect=lambda m, _: responder(LLM._session.get(), m)):
            run_episode(spec, out, budget.path, "fake", "correct", ceiling)
        folder = out / "episodes" / spec.name
        row = read_json(folder / "episode.json")
        trace = calls(folder)
        self.assertEqual((row["relay_calls"], sum(c["role"] == "relay" for c in trace)), (0, 0))
        audit_news.inspect_episode(folder, row)  # Reopen the producing calls and check the saved attribution.
        return row, trace

    def test_implicit_auto_replays_saved_v7_episode_bytes(self):
        archive = REVIEW / "v7-auto"
        old = next((archive / "episodes").iterdir())
        saved, trace = read_json(old / "episode.json"), calls(old)
        self.assertEqual(saved["code_version"], "5a5ab0e063c9")
        spec = Spec(2, 4, "DMAS", "e1", 200, archive / "maps/2x4/env200.json", saved["env_sha256"],
                    saved["event_sha256"], tell="member", speech="auto")
        budget = Invocation(self.work, self.work / (trace[0]["invocation"] + ".json"))
        budget.create(None, 2, "fake")
        clock = [t for c in trace for t in (0., c["elapsed_seconds"])]
        steps = [t for it in saved["iterations"] for t in (0., it["planning_seconds"])]
        with (patch("LLM.monotonic", side_effect=clock),
              patch("episode.time", SimpleNamespace(monotonic=iter(steps).__next__))):
            run_episode(spec, self.work, budget.path, "fake", "correct", 300, 24000, 0., .7)
        new = self.work / "episodes" / spec.name
        files = {p.relative_to(old) for p in old.rglob("*") if p.is_file()}
        self.assertEqual(files, {p.relative_to(new) for p in new.rglob("*") if p.is_file()})
        for relative in files:
            data = (new / relative).read_bytes()
            if relative.name == "episode.json":
                self.assertEqual(json.loads(data)["code_version"], code_version())
                companion = self.work / "relay" / spec.name / (digest(data) + ".json")
                measurement = read_json(companion)
                self.assertEqual((measurement["relay_timing"], measurement["relay_display"]), ("immediate", "persistent"))
                expected = audit_news.inspect_episode(old, saved)
                self.assertEqual([(r["step"], r["producer_news_source"]) for r in measurement["post_event_producers"]],
                                 [(s.step, s.source) for s in expected])
                data = data.replace(code_version().encode(), saved["code_version"].encode(), 1)
            self.assertEqual(data, (old / relative).read_bytes(), relative)

    def test_turn_and_displays_including_repair_and_late_first_recipient_turn(self):
        for display in RELAY_DISPLAYS:
            for sender_reply in ("PROCEED", EMPTY):
                def respond(s, messages):
                    if len(messages) > 2:
                        return "{}"
                    if s.step == 3:
                        if s.speaker == FIRST:
                            return "PROCEED"
                        if s.speaker == SENDER:
                            return sender_reply
                        return "EXECUTE\n" + INVALID
                    if s.step >= 5 and s.speaker == THIRD:
                        return "PROCEED"
                    if s.step >= 6:
                        return "EXECUTE\n" + fake_model.plan_from_text(messages[1]["content"], False)
                    return EMPTY

                with self.subTest(display=display, reply=sender_reply):
                    spec = self.spec(display=display)
                    row, trace = self.play(spec, display + sender_reply[:3], respond)
                    receipt = row["relay_deliveries"][SENDER]
                    self.assertEqual((receipt["iteration"], receipt["round"], receipt["speaker_position"]), (3, 1, 2))
                    self.assertEqual((row["relay_delivery_iteration"], row["relay_delivery_speaker_position"]), (3, 2))
                    sender_call = trace[receipt["after_call"] - 1]
                    self.assertEqual((sender_call["speaker"], sender_call["response"]), (SENDER, sender_reply))
                    notice = row["event"]["announcement"]
                    self.assertEqual(row["relay_records"][0]["delivered_text"], notice)
                    seen = {}
                    for call in trace:
                        robot = call["speaker"]
                        eligible = call["number"] > receipt["after_call"] and robot != SENDER
                        turn = (call["step"], call["round"])
                        visible = eligible and (display == "persistent" or seen.get(robot, turn) == turn)
                        if eligible:
                            seen.setdefault(robot, turn)
                        self.assertEqual(block_in(call), visible, (display, call["number"]))
                        self.assertEqual((HEADER + f"[{SENDER}, after step 1]: {notice}\n") in
                                         call["messages"][1]["content"], visible)
                    self.assertTrue(any(c["speaker"] == THIRD and len(c["messages"]) > 2 and block_in(c) for c in trace))
                    self.assertEqual(seen, {THIRD: (3, 1), FIRST: (4, 1), LAST: (5, 1)})

    def test_once_expires_between_rounds_of_the_same_iteration(self):
        def respond(s, messages):
            if s.step == 2 and s.round == 1:
                return "PROCEED"
            if s.step > 2:
                return "EXECUTE\n" + fake_model.plan_from_text(messages[1]["content"], False)
            return EMPTY

        row, trace = self.play(self.spec(display="once"), "rounds", respond)
        self.assertEqual(row["relay_delivery_iteration"], 2)
        seen = {(c["speaker"], c["round"]): block_in(c) for c in trace if c["step"] == 2}
        self.assertTrue(seen[THIRD, 1])
        self.assertFalse(seen[THIRD, 2])
        self.assertFalse(seen[FIRST, 1])
        self.assertTrue(seen[FIRST, 2])

    def test_tell_all_consumes_each_senders_notice_independently(self):
        def respond(s, messages):
            if s.step == 2 and s.round == 1:
                return "PROCEED"
            if s.step >= 4:
                return "EXECUTE\n" + fake_model.plan_from_text(messages[1]["content"], False)
            return EMPTY

        row, trace = self.play(replace(self.spec(display="once"), tell="all"), "all-senders", respond)
        senders = (FIRST, SENDER, THIRD, LAST)
        receipts = row["relay_deliveries"]
        self.assertEqual([receipts[r]["speaker_position"] for r in senders], [1, 2, 3, 4])
        seen = set()
        for call in trace:
            text = call["messages"][1]["content"].partition(STATE_HEADERS["local"])[0]
            receiver = call["speaker"]
            for sender in senders:
                eligible = receiver != sender and call["number"] > receipts[sender]["after_call"]
                self.assertEqual(f"[{sender}, after step 1]: " in text, eligible and (sender, receiver) not in seen)
                if eligible:
                    seen.add((sender, receiver))

    def test_physical_wrong_delivery_order_including_same_iteration_and_never(self):
        for release_at, wrong_at, expected in ((3, 2, False), (3, 3, True), (3, 4, True),
                                               (None, 2, False), (None, None, None), (3, None, True)):
            def respond(s, _):
                if s.step == release_at and s.speaker == FIRST:
                    return "PROCEED"
                actions = {}
                if s.step == 1:
                    # An ordinary blue target is correct before the event. A red misuse is the wrong colour.
                    actions = {FIRST: "move(box_blue, target_blue)", SENDER: "move(box_red, dropoff)"}
                if s.step == wrong_at:
                    actions = {THIRD: "move(box_blue, target_blue)"}
                return "EXECUTE\n" + json.dumps(actions)

            with self.subTest(release=release_at, wrong=wrong_at):
                row, trace = self.play(self.spec(), f"order-{release_at}-{wrong_at}", respond, ceiling=15)
                self.assertEqual(row["first_wrong_delivery_step"], wrong_at)
                self.assertIs(row["delivered_before_first_wrong"], expected)
                self.assertEqual(row["relay_delivery_iteration"], release_at or "never")
                self.assertEqual(row["relay_delivery_speaker_position"], 2 if release_at else "never")
                if release_at is None:
                    self.assertEqual(row["relay_deliveries"][SENDER], "never")
                    self.assertFalse(any(block_in(c) for c in trace))
                self.assertEqual(row["wrong_deliveries"], 1 + int(wrong_at is not None))
                last = row["iterations"][-1]
                self.assertFalse(last["executed"])
                self.assertEqual((last["producer_news_source"], last["producer_had_news"]), (None, None))

    def test_producer_uses_direct_then_relay_then_ordinary_dialogue_then_none(self):
        def respond(s, messages):
            if s.step in (2, 4) and s.speaker == FIRST:
                return "PROCEED"
            if s.step in (2, 3) and s.speaker in (THIRD, LAST):
                return "PROCEED"
            if s.step == 4 and s.speaker == SENDER:
                return "PROCEED. Blue now goes to the dropoff."
            if s.step == 5 and s.speaker == THIRD:
                return "EXECUTE\n" + fake_model.plan_from_text(messages[1]["content"], False)
            return EMPTY

        row, trace = self.play(self.spec(display="once"), "sources", respond)
        post = row["iterations"][1:]
        self.assertEqual([it["producer_news_source"] for it in post], ["direct", "relay", "dialogue", "none"])
        self.assertEqual([it["producer_had_news"] for it in post], [True, True, True, False])
        relayed_by_dialogue = trace[post[2]["plan_maker_call"] - 1]
        self.assertFalse(block_in(relayed_by_dialogue))
        self.assertIn("Blue now goes to the dropoff.", relayed_by_dialogue["messages"][1]["content"])

    def test_hmas1_waits_for_selected_dialogue_and_central_planner_reads_once(self):
        def respond(s, m):
            if s.step >= 5:
                plan = fake_model.plan_from_text(m[1]["content"], False)
                return plan if s.role == "central" else "EXECUTE\n" + plan
            if s.role == "central":
                if s.step == 3:
                    return json.dumps({SENDER: "move(box_red, target_red)", THIRD: "move(box_blue, target_blue)"})
                return json.dumps({FIRST: "move(box_blue, target_blue)"})
            return EMPTY

        row, trace = self.play(self.spec("HMAS-1", display="once"), "hmas1", respond)
        self.assertEqual((row["relay_delivery_iteration"], row["relay_delivery_speaker_position"]), (3, 1))
        central = [c for c in trace if c["role"] == "central"]
        self.assertEqual([c["step"] for c in central if block_in(c)], [4])
        self.assertTrue(all(c["number"] > row["relay_deliveries"][SENDER]["after_call"] for c in trace if block_in(c)))

    def test_central_once_retains_initial_prompt_for_repairs_and_revisions(self):
        for fw in ("CMAS", "HMAS-2"):
            def respond(s, messages):
                if s.role == "review":
                    return "Please reconsider." if s.step == 2 else "I Agree"
                if s.step >= 3:
                    return fake_model.plan_from_text(messages[1]["content"], False)
                if s.step == 2:
                    if len(messages) == 2:
                        return INVALID
                    if fw == "HMAS-2" and "feedback from local agents" not in messages[-1]["content"]:
                        return json.dumps({LAST: "move(box_red, target_red)"})
                return "{}"

            row, trace = self.play(self.spec(fw, "immediate", "once"), fw, respond)
            self.assertEqual((row["relay_delivery_iteration"], row["relay_delivery_speaker_position"]), (2, 0))
            self.assertTrue(all(block_in(c) == (c["step"] == 2 and c["role"] == "central") for c in trace))
            count = sum(c["step"] == 2 and c["role"] == "central" and block_in(c) for c in trace)
            self.assertEqual(count, 3 if fw == "HMAS-2" else 2)

    def test_cli_rejects_explicit_defaults_mixed_speech_and_undefined_turn(self):
        out = self.work / "invalid"
        for rule in ("authors", "choice", "free", "auto,choice"):
            for flag, value in (("--relay-display", "persistent"), ("--relay-timing", "immediate")):
                run = cli("run_chen2d.py", "--out", out, "--model", "fake", "--speech", rule, flag, value)
                self.assertNotEqual(run.returncode, 0)
                self.assertIn("--speech auto only", run.stderr)
        for fw in ("CMAS", "HMAS-2", "DMAS,CMAS"):
            run = cli("run_chen2d.py", "--out", out, "--model", "fake", "--speech", "auto",
                      "--frameworks", fw, "--relay-timing", "turn")
            self.assertNotEqual(run.returncode, 0)
            self.assertIn("undefined for", run.stderr)
        self.assertFalse((out / "run.json").exists())

    def test_implicit_and_explicit_defaults_share_assignment_and_analysis(self):
        opts = ("run_chen2d.py", "--model", "fake", "--sizes", "2x4", "--envs", "200", "--frameworks", "DMAS",
                "--conditions", "e1", "--tell", "member", "--speech", "auto")
        controls = ("--relay-timing", "immediate", "--relay-display", "persistent")
        old, new = self.work / "implicit", self.work / "explicit"
        for folder, flags in ((old, ()), (new, controls)):
            run = cli(*opts, "--out", folder, *flags)
            self.assertEqual(run.returncode, 0, run.stderr)
        skipped = cli(*opts, "--out", old, *controls)
        self.assertEqual(skipped.returncode, 0, skipped.stderr)
        self.assertIn("0 calls", skipped.stdout)
        _, a, rows = read_run(old)
        _, b, other = read_run(new)
        self.assertEqual(a, b)
        name, = a
        for k in ("relay_timing", "relay_display", "relay_deliveries", "delivered_before_first_wrong",
                  "first_wrong_delivery_step", "strict_success"):
            self.assertEqual(rows[name][k], other[name][k])
        self.assertEqual([it.get("producer_news_source") for it in rows[name]["iterations"]],
                         [it.get("producer_news_source") for it in other[name]["iterations"]])
        self.assertEqual(cli("audit_news.py", old).stdout, cli("audit_news.py", new).stdout)

    def test_cli_factorial_pairing_partial_denominators_and_resume(self):
        out = self.work / "factorial"
        opts = ("run_chen2d.py", "--model", "fake", "--sizes", "2x4", "--envs", "328,329", "--frameworks", "DMAS",
                "--conditions", "e1", "--tell", "member", "--speech", "auto", "--relay-timing", "turn,immediate",
                "--relay-display", "once,persistent", "--shuffle", "4")
        self.assertEqual(cli(*opts, "--out", out, "--max-calls", 5).returncode, 0)
        check = cli("paired.py", out, "--by", "relay")
        self.assertNotEqual(check.returncode, 0)
        self.assertIn("unrecorded episodes", check.stderr)
        check = cli("paired.py", out, "--by", "relay", "--allow-partial")
        self.assertEqual(check.returncode, 0, check.stderr)
        self.assertIn("WARNING", check.stdout)
        self.assertEqual(cli(*opts, "--out", out).returncode, 0)
        _, assigned, rows = read_run(out)
        self.assertEqual(len(assigned), 8)
        self.assertEqual({(r["relay_timing"], r["relay_display"]) for r in rows.values()},
                         {(t, d) for t in RELAY_TIMINGS for d in RELAY_DISPLAYS})
        summary = cli("summarize.py", out, "--by", "relay")
        self.assertEqual(summary.returncode, 0, summary.stderr)
        self.assertEqual([r["assigned"] for r in pipe_table(summary.stdout, "size |")], ["2"] * 4)
        with (out / "episodes.csv").open() as f:
            self.assertEqual(len([r for r in csv.DictReader(f) if r["relay_delivery_iteration"]]), 8)
        comparison = cli("paired.py", out, "--by", "relay")
        self.assertEqual(comparison.returncode, 0, comparison.stderr)
        self.assertEqual(comparison.stdout.count("Relay cells (relay_timing/relay_display)"), 4)
        for line in comparison.stdout.splitlines():
            if line.startswith("2x4 |"):
                self.assertEqual(line.split(" | ")[4:7], ["2", "2", "0"])
        specific = cli("paired.py", out, "--by", "relay", "--a", "turn/once", "--b", "turn/persistent",
                       "--outcome", "change_respected")
        self.assertEqual(specific.returncode, 0, specific.stderr)
        self.assertEqual(specific.stdout.count("Relay cells (relay_timing/relay_display)"), 1)
        audit = cli("audit_news.py", out)
        self.assertEqual(audit.returncode, 0, audit.stderr)
        first, all_steps = audit.stdout.split("All executed post-event plans:")
        for table, expected in ((first, 8), (all_steps, sum(it["executed"] for row in rows.values()
                                                            for it in row["iterations"] if it["step"] > row["event_step"]))):
            items = pipe_table(table, "framework | speech | relay_timing")
            self.assertEqual(len(items), 12)
            self.assertEqual(sum(int(r["respected " + k]) for r in items for k in ("yes", "no", "NA")), expected)
        fresh = self.work / "fresh"
        self.assertEqual(cli(*opts, "--out", fresh).returncode, 0)
        for name, row in rows.items():
            new = read_json(fresh / "episodes" / name / "episode.json")
            for field in ("relay_deliveries", "first_wrong_delivery_step", "delivered_before_first_wrong", "strict_success"):
                self.assertEqual(row[field], new[field])
            left, right = (calls(folder / "episodes" / name) for folder in (out, fresh))
            for a, b in zip(left, right, strict=True):
                self.assertEqual((a["messages"], a["response"]), (b["messages"], b["response"]))

    def test_cause_maps_are_new_reproducible_and_balanced(self):
        envs = ROOT / "envs"
        old = read_json(REVIEW / "pre-enrolment.json")
        for filename, entries in old.items():
            now = read_json(envs / filename)
            for name, sha in entries.items():
                self.assertEqual(now[name], sha)
                self.assertEqual(digest((envs / name).read_bytes()), sha)
        used = set(old["manifest.json"].values())
        strata = Counter()
        for slot in CAUSE_SLOTS[2, 4]:
            path = envs / "2x4" / f"env{slot}.json"
            event, board = read_json(event_path(path)), read_json(path)
            sha = digest(path.read_bytes())
            self.assertNotIn(sha, used)
            used.add(sha)
            self.assertEqual((event["env_sha256"], event["map_set"], event["slot_seed"]), (sha, "cause", slot))
            self.assertEqual(board, env_create(2, 4, 1, 3, rng=random.Random(event["seed"])))
            self.assertEqual(event["M"], agent_at(event["D"]))
            row, col = map(int, event["D"])
            stratum = "first_column" if col == 0 else "other_columns"
            self.assertEqual((event["member_position"], event["stratum"]), (row * 4 + col + 1, stratum))
            strata[stratum, event["wording"]] += 1
            trajectory = [board] + [s for s, _ in reference_trajectory(board, action_from_response)]
            at_event = trajectory[event["event_step"]]
            self.assertGreater(boxes(at_event)[event["A"]], 0)
            self.assertNotIn("target_" + event["A"], board[cell_key(event["D"])])
            self.assertNotIn("box_" + event["A"], at_event[cell_key(event["D"])])
            self.assertEqual(event["previously_enrolled_seeds"], [slot] if 328 <= slot <= 335 else [])
        self.assertEqual(strata, {(s, w): 6 for s in ("first_column", "other_columns") for w in (1, 2)})
        before = {p: p.stat().st_mtime_ns for p in envs.rglob("*.json")}
        again = cli("enrol_maps.py", "--set", "cause", "--sizes", "2x4", "--envs", "328-351")
        self.assertEqual(again.returncode, 0, again.stderr)
        self.assertEqual(again.stdout, (REVIEW / "enrol-cause.txt").read_text())
        self.assertEqual(before, {p: p.stat().st_mtime_ns for p in envs.rglob("*.json")})


if __name__ == "__main__":
    suites = sys.argv[1:] or ["test_chen2d", *(f"test_chen2d_v{n}" for n in range(2, 9))]
    with local_references():
        print("Folder-local reference hashes verified. Network connections disabled.", flush=True)
        result = unittest.TextTestRunner(verbosity=2).run(unittest.defaultTestLoader.loadTestsFromNames(suites))
    sys.exit(not result.wasSuccessful())
