"""Offline checks for the public dropoff rule, v5 replay and delivery outcomes."""
import csv
import json
import shutil
import sys
import tempfile
import unittest
from dataclasses import replace
from pathlib import Path
from regression_inputs import REGRESSION
from types import SimpleNamespace
from unittest.mock import patch

import fake_model
from episode import Spec, run_episode
from limits import Invocation
from map_events import boxes, event_path
from run_chen2d import FRAMEWORKS
from storage import ROOT, read_json, write_json
from summarize import episode_csv
from test_chen2d import calls, fixture_spec
from test_chen2d_v2 import enrolled_spec, fixed_dialogue
from test_chen2d_v4 import cli, plan
from test_chen2d_v5 import local_references


RULE = ("The dropoff is only for boxes whose order has been changed to the dropoff. "
        "Putting any other box into the dropoff counts as a wrong delivery, and a wrong delivery cannot be undone.")
GOALS = {
    "central": "Your task is to instruct each agent to match all boxes to their color-coded targets.",
    "DMAS": "All the agents coordinate with others together to come out a plan and achieve the goal: match each box with its color-coded target.",
    "HMAS-1": "one extra planner first proposes an initial plan to coordinates all agents to achieve the goal: match each box with its color-coded target.",
    "HMAS-2": "A central planner coordinates all agents to achieve the goal: match each box with its color-coded target.",
}
OUTCOMES = ("change_respected", "dropoff_misuse", "dropoff_misuse_before", "dropoff_misuse_after")
V5_SMOKE = REGRESSION / "chen2d-5/smoke"


class DropoffRuleTests(unittest.TestCase):
    def setUp(self):
        tmp = tempfile.TemporaryDirectory(dir=ROOT, prefix=".chen6-test-")
        self.addCleanup(tmp.cleanup)
        self.work = Path(tmp.name)

    def play(self, spec, tag, prefix=(), responder=None, max_calls=None):
        out = self.work / tag
        out.mkdir()
        budget = Invocation(out, out / "test.json")
        budget.create(max_calls, 2, "fake")
        scripted, ordinary = iter(prefix), fake_model.reply

        def reply(messages, script):
            action = next(scripted, None)
            return action if action is not None else ordinary(messages, script)

        with patch.object(fake_model, "reply", side_effect=responder or reply):
            run_episode(spec, out, budget.path, "fake", "correct", 300)
        folder = out / "episodes" / spec.name
        return read_json(folder / "episode.json"), calls(folder)

    def check_rule(self, call, framework):
        messages = call["messages"]
        self.assertEqual(sum(m["content"].count(RULE) for m in messages), int(call["role"] != "relay"))
        if call["role"] != "relay":
            goal = GOALS["central" if call["role"] == "central" else framework]
            self.assertIn(goal + " " + RULE, messages[1]["content"])

    def test_every_task_prompt_and_private_colour_against_static(self):
        for fw in FRAMEWORKS:
            with self.subTest(framework=fw):
                base = enrolled_spec(fw, "static", dropoff="always", event_step_override=1)
                _, control = self.play(base, fw + "-static", responder=fixed_dialogue)
                _, off = self.play(replace(base, dropoff_rule="off"), fw + "-off", responder=fixed_dialogue)
                for c, old in zip(control, off, strict=True):
                    self.check_rule(c, fw)
                    for msg, previous in zip(c["messages"], old["messages"], strict=True):
                        self.assertEqual(msg["content"].replace(" " + RULE, ""), previous["content"])
                post_roles = set()
                for tell in ("all", "member", "leader"):
                    row, records = self.play(replace(base, condition="e1", tell=tell), fw + tell, responder=fixed_dialogue)
                    self.assertEqual(row["event_step"], 1)
                    self.assertGreater(row["box_A_left_at_event"], 0)
                    notice = row["event"]["announcement"] + "\n"
                    for c, static in zip(records, control, strict=True):
                        self.check_rule(c, fw)
                        self.assertEqual((c["step"], c["role"], c["speaker"]), (static["step"], static["role"], static["speaker"]))
                        if c["step"] > 1:
                            post_roles.add((c["role"], c["told"]))
                        # The ordinary map already names the colours. Compare the whole conversation to
                        # static on the identical trajectory, including repairs and HMAS-2 revisions.
                        for i, (msg, baseline) in enumerate(zip(c["messages"], static["messages"], strict=True)):
                            expected = baseline["content"]
                            if c["told"] and i == 1:
                                marker = "Hence, the current state is" if c["role"] == "central" else "The current state and possible actions of yourself are:"
                                expected = expected.replace(marker, notice + marker, 1)
                            self.assertEqual(msg["content"], expected)
                roles = {"CMAS": ["central"], "DMAS": ["dialogue"], "HMAS-1": ["central", "dialogue"],
                         "HMAS-2": ["central", "review"]}[fw]
                self.assertEqual(post_roles, {(role, told) for role in roles for told in (False, True)})

    def test_forwarded_news_and_relay_only_prompts(self):
        for fw in FRAMEWORKS:
            for speech in ("auto", "choice", "free"):
                with self.subTest(framework=fw, speech=speech):
                    spec = enrolled_spec(fw, "e1", tell="member", speech=speech, dropoff="always", event_step_override=1)
                    row, trace = self.play(spec, fw + speech)
                    self.assertEqual(row["relay_calls"], int(speech != "auto"))
                    for call in trace:
                        self.check_rule(call, fw)
                    self.assertTrue(any("Messages received from robots:" in c["messages"][1]["content"] for c in trace))

    def test_off_replays_every_file_of_the_sixteen_v5_smoke_episodes(self):
        config = read_json(V5_SMOKE / "run.json")
        archived = sorted((V5_SMOKE / "episodes").iterdir())
        self.assertEqual(len(archived), 16)
        for old in archived:
            with self.subTest(episode=old.name):
                saved, trace = read_json(old / "episode.json"), calls(old)
                path = V5_SMOKE / "maps" / saved["size"] / f"env{saved['env_seed']}.json"
                spec = Spec(2, 4, saved["framework"], saved["condition"], saved["env_seed"], path,
                            saved["env_sha256"], saved["event_sha256"], tell=saved["tell"], speech=saved["speech"],
                            dropoff_rule="off")
                call_clock = [t for c in trace for t in (0., c["elapsed_seconds"])]
                step_clock = [t for it in saved["iterations"] for t in (0., it["planning_seconds"])]
                budget = Invocation(self.work, self.work / (trace[0]["invocation"] + ".json"))
                if not budget.path.exists():
                    budget.create(None, 2, "fake")
                with (patch("LLM.monotonic", side_effect=call_clock),
                      patch("episode.time", SimpleNamespace(monotonic=iter(step_clock).__next__))):
                    run_episode(spec, self.work, budget.path, "fake", "correct", 300,
                                temperature=config["temperature"], retry_temperature=config["retry_temperature"])
                new = self.work / "episodes" / spec.name
                files = {p.relative_to(old) for p in old.rglob("*") if p.is_file()}
                self.assertEqual(files, {p.relative_to(new) for p in new.rglob("*") if p.is_file()})
                for file in files:
                    actual = (new / file).read_bytes()
                    if file.name == "episode.json":
                        row = json.loads(actual)
                        self.assertEqual(row.pop("dropoff_rule"), "off")
                        for field in OUTCOMES:
                            row.pop(field)
                        row["code_version"] = saved["code_version"]
                        actual = (json.dumps(row, ensure_ascii=False, indent=2) + "\n").encode()
                    self.assertEqual(actual, (old / file).read_bytes(), str(file))

    def test_cli_off_matches_frozen_v5_hierarchical_prompts_and_actions(self):
        frozen, fresh = self.work / "v5", self.work / "v6"
        shutil.copytree(V5_SMOKE / "source", frozen)
        options = ("--model", "fake", "--sizes", "2x2", "--envs", "0", "--frameworks", "HMAS-1,HMAS-2",
                   "--conditions", "static,e1,e2", "--tell", "member", "--speech", "choice,free")
        archived = cli(frozen / "run_chen2d.py", "--out", "run", *options)
        self.assertEqual(archived.returncode, 0, archived.stderr)
        # The portable archived runner has a new digest for its relocated planner path.
        expected = dict(read_json(V5_SMOKE / "run.json")["source_sha256"])
        expected['LLM.py'] = '5115847cee9de2ce430465a4c8cc551c482195cf141961a240efbd2fc85f9a5d'
        self.assertEqual(read_json(frozen / "run/run.json")["source_sha256"], expected)
        replay = cli("run_chen2d.py", "--out", fresh, "--dropoff-rule", "off", *options)
        self.assertEqual(replay.returncode, 0, replay.stderr)
        old_dirs = sorted((frozen / "run/episodes").iterdir())
        new_dirs = sorted((fresh / "episodes").iterdir())
        self.assertEqual(len(old_dirs), 12)
        for old, new in zip(old_dirs, new_dirs, strict=True):
            self.assertEqual(old.name, new.name)
            for a, b in zip(calls(old), calls(new), strict=True):
                for field in ("step", "round", "speaker", "role", "told", "messages", "response"):
                    self.assertEqual(a[field], b[field], (old.name, field))
            files = {p.relative_to(old) for p in old.rglob("*") if p.is_file()}
            self.assertEqual(files, {p.relative_to(new) for p in new.rglob("*") if p.is_file()})
            for file in files:
                if file.name != "episode.json" and file.parent.name != "calls":
                    self.assertEqual((old / file).read_bytes(), (new / file).read_bytes(), (old.name, file))

    def check_outcome(self, row, change, before, after):
        self.assertEqual(tuple(row[k] for k in OUTCOMES), (change, before + after, before, after))

    def test_e1_counts_affected_boxes_at_the_boundary_and_applied_deliveries(self):
        board = {f"{i+.5}_{j+.5}": ["box_blue", "target_blue", "box_red", "target_red"] * 2
                 for i in range(2) for j in range(2)}
        spec = fixture_spec(self.work / "board.json", board, "e1", dropoff="always", event_step_override=1)
        event = read_json(event_path(spec.env_path))
        d, colour = event["D"], event["A"]
        other = "red" if colour == "blue" else "blue"
        early = plan((d, "box_" + colour, "dropoff"))
        misuse = plan((d, "box_" + other, "dropoff"))
        old_target = plan((d, "box_" + colour, "target_" + colour))
        row, _ = self.play(spec, "honoured", [early, misuse])
        self.assertEqual(row["box_A_left_at_event"], boxes(board)[colour] - 1)
        self.assertEqual((row["wrong_deliveries"], row["strict_success"], row["boxes_left"]), (2, False, 0))
        self.check_outcome(row, 1, 1, 1)
        wrong, _ = self.play(spec, "old-target", [early, old_target])
        self.assertEqual((wrong["wrong_deliveries"], wrong["boxes_left"]), (2, 0))
        self.check_outcome(wrong, 0, 1, 0)
        leftover, _ = self.play(spec, "left-over", [early] + ["{}"] * 30)
        self.assertTrue(leftover["finished"])
        self.assertFalse(leftover["strict_success"])
        self.assertGreater(boxes(leftover["final_state"])[colour], 0)
        self.check_outcome(leftover, 0, 1, 0)
        static, _ = self.play(replace(spec, condition="static"), "static", [early, misuse])
        self.check_outcome(static, None, 2, 0)

    def test_empty_event_unfired_event_and_initial_state_event(self):
        board = {"0.5_0.5": ["box_blue", "target_blue"], "0.5_1.5": [], "1.5_0.5": [], "1.5_1.5": []}
        spec = fixture_spec(self.work / "one.json", board, "e1", dropoff="always")
        for trigger, expected_step, expected in ((1, 1, None), (2, None, None), (None, 0, 1)):
            row, _ = self.play(replace(spec, event_step_override=trigger), str(trigger))
            self.assertEqual(row["event_step"], expected_step)
            self.check_outcome(row, expected, 0, 0)
        row, _ = self.play(replace(spec, condition="e2"), "unfired-e2", ["No plan."])
        self.assertFalse(row["event_fired"])
        self.check_outcome(row, None, 0, 0)

    def test_e2_only_the_returned_identity_and_whole_trigger_step(self):
        x, via, d = (.5, .5), (.5, 1.5), (1.5, 1.5)
        b = "box_blue"
        board = {"0.5_0.5": [b, b] + ["target_blue"] * 4, "0.5_1.5": [b], "1.5_0.5": [], "1.5_1.5": [b]}
        spec = fixture_spec(self.work / "four-blue.json", board, "e2", dropoff="always")
        first = [plan((x, b, "target_blue"), (d, b, "dropoff")), plan((via, b, "square[1.5, 1.5]")),
                 plan((d, b, "dropoff"), (x, b, "target_blue"))]
        send_returned = [plan((x, b, "square[0.5, 1.5]")), plan((via, b, "square[1.5, 1.5]")), plan((d, b, "dropoff"))]
        for name, tail, score in (("accepted", send_returned, 1), ("old-target", [plan((x, b, "target_blue"))], 0)):
            row, trace = self.play(spec, name, first + tail)
            self.assertEqual((row["event_step"], row["event"]["returned_box_id"], row["strict_success"], row["boxes_left"]),
                             (1, 0, False, 0))
            self.check_outcome(row, score, 1, 1)
            for c in trace:
                self.check_rule(c, "CMAS")
        leftover, _ = self.play(spec, "leftover-e2", first, max_calls=3)
        self.assertEqual(boxes(leftover["final_state"])["blue"], 1)
        self.check_outcome(leftover, 0, 1, 1)

    def run_cli(self, out, *options):
        return cli("run_chen2d.py", "--model", "fake", "--out", out, "--frameworks", "CMAS",
                   "--conditions", "e1", "--tell", "member", "--envs", "0", *options)

    def test_cli_effective_switch_resume_and_summary_guards(self):
        on, off, event = (self.work / name for name in ("on", "off", "event"))
        for out, rule, options in ((on, "on", ()), (off, "off", ("--dropoff-rule", "off")),
                                   (event, "off", ("--dropoff", "event", "--dropoff-rule", "on"))):
            result = self.run_cli(out, "--sizes", "2x4", "--envs", "100", *options)
            self.assertEqual(result.returncode, 0, result.stderr)
            name, item = next(iter(read_json(out / "assignments.json").items()))
            folder = out / "episodes" / name
            self.assertEqual([read_json(out / "run.json")["dropoff_rule"], item["dropoff_rule"],
                              read_json(folder / "episode.json")["dropoff_rule"]], [rule] * 3)
            self.assertEqual(RULE in calls(folder)[0]["messages"][1]["content"], rule == "on")
            self.assertIn("dropoff_rule " + rule, cli("summarize.py", out).stdout)
            if out == off:
                self.assertEqual([c["messages"] for c in calls(folder)],
                                 [c["messages"] for c in calls(V5_SMOKE / "episodes" / name)])
        self.assertIn("different dropoff_rule", cli("summarize.py", on, off).stderr)
        self.assertNotEqual(self.run_cli(on, "--dropoff-rule", "off").returncode, 0)
        path = next(on.glob("episodes/*/episode.json"))
        csv_bytes = (on / "episodes.csv").read_bytes()
        row = read_json(path)
        for opposite in (dict(row, dropoff_rule="off"), {k: v for k, v in row.items() if k != "dropoff_rule"}):
            write_json(path, opposite)
            self.assertIn("dropoff_rule", cli("summarize.py", on).stderr)
            self.assertEqual((on / "episodes.csv").read_bytes(), csv_bytes)

    def test_csv_summary_and_paired_outcome_denominators(self):
        out = self.work / "pairs"
        result = self.run_cli(out, "--envs", "0-2", "--frameworks", "CMAS,DMAS", "--speech", "authors,choice")
        self.assertEqual(result.returncode, 0, result.stderr)
        for path in out.glob("episodes/*/episode.json"):
            row = read_json(path)
            choice = row["speech"] == "choice"
            partial = row["framework"] == "CMAS" and choice
            seed = row["env_seed"]
            if partial and seed == 2:
                path.unlink()  # assigned, never recorded in this constructed comparison
                continue
            score = int(choice == (row["framework"] == "CMAS")) if seed == 0 else 1
            row.update(strict_success=False, finished=not (partial and seed == 0),
                       change_respected=None if partial and seed == 1 else score,
                       dropoff_misuse=1, dropoff_misuse_before=int(seed == 0), dropoff_misuse_after=int(seed != 0))
            write_json(path, row)
        summary = cli("summarize.py", out)
        self.assertEqual(summary.returncode, 0, summary.stderr)
        _, header, *lines = summary.stdout.splitlines()
        groups = [dict(zip(header.split(" | "), line.split(" | "), strict=True)) for line in lines]
        group = next(g for g in groups if g["framework"] == "CMAS" and g["speech"] == "choice")
        self.assertEqual([group[k] for k in ("assigned", "recorded", "strict success", "change respected",
                         "dropoff misuse", "dropoff misuse before", "dropoff misuse after")],
                         ["3", "2", "0.0% (0/3)", "100.0% (1/1) [2 NA]", "2", "1", "1"])
        with (out / "episodes.csv").open() as handle:
            indexed = {r["episode_id"]: r for r in csv.DictReader(handle)}
        self.assertEqual([indexed["2x2_CMAS_e1_member_env1_choice"][k] for k in OUTCOMES], ["NA", "1", "0", "1"])
        pair = ("paired.py", out, "--a", "authors", "--b", "choice")
        strict = cli(*pair)
        change = cli(*pair, "--outcome", "change_respected")
        self.assertEqual(strict.returncode, 0, strict.stderr)
        self.assertEqual(change.returncode, 0, change.stderr)
        self.assertEqual(strict.stdout, cli(*pair, "--outcome", "strict").stdout)
        self.assertIn("ties dropped=3   n used=0", strict.stdout)
        self.assertIn("CMAS | 0 | 0 | 1 | 1 | 1 | 0 | 1 | 0", change.stdout)
        for seed in (1, 2):
            self.assertIn(f"CMAS | {seed} | 1 | NA | NA", change.stdout)
        self.assertIn("positive=1   negative=0   ties dropped=0   n used=1", change.stdout)

    def test_archived_csv_derives_outcomes_without_editing_episode(self):
        old = V5_SMOKE / "episodes/2x4_CMAS_e1_member_env100_choice"
        local = self.work / "episodes" / old.name
        local.mkdir(parents=True)
        shutil.copyfile(V5_SMOKE / "run.json", self.work / "run.json")
        shutil.copyfile(old / "episode.json", local / "episode.json")
        row, = episode_csv(self.work)
        self.assertEqual(row["dropoff_rule"], "off")
        self.check_outcome(row, 1, 0, 0)
        self.assertEqual((local / "episode.json").read_bytes(), (old / "episode.json").read_bytes())


if __name__ == "__main__":
    suites = ["test_chen2d", *(f"test_chen2d_v{i}" for i in range(2, 7))]
    with local_references():
        print("Folder-local reference hashes verified. Network connections disabled.", flush=True)
        result = unittest.TextTestRunner(verbosity=2).run(unittest.defaultTestLoader.loadTestsFromNames(suites))
    sys.exit(not result.wasSuccessful())
