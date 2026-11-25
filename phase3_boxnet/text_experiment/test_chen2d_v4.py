"""Offline checks for the neutral site, hidden e2 identity and speaking-order records."""
import ast
import contextlib
import io
import json
import subprocess
import sys
import tempfile
import unittest
from collections import Counter
from dataclasses import replace
from pathlib import Path
from regression_inputs import REGRESSION
from types import SimpleNamespace
from unittest.mock import patch

import fake_model
from enrol_maps import SIZE_NAMES, seed_selection
from env1_create import action_from_response, state_update_func, state_update_func_local_agent, with_action_syntactic_check_func
from episode import run_episode
from limits import Invocation
from map_events import agent_at, boxes, cell_key, event_path, reference_trajectory
from run_chen2d import FRAMEWORKS
from storage import ROOT, digest, read_json, write_json
from summarize import compare
from test_chen2d import calls, fixture_spec
from test_chen2d_v2 import enrolled_spec


def plan(*moves):
    return json.dumps({agent_at(square): f"move({box}, {target})" for square, box, target in moves})


def cli(*args):
    return subprocess.run([sys.executable, "-B", *map(str, args)], cwd=ROOT, text=True, capture_output=True)


def archived_bytes(path, version, code_stamp):
    """Represent new audit fields in the archived schema; preserve every old field and its order."""
    if path.name == "episode.json":
        row = read_json(path)
        assert row.pop("dropoff_rule") == "off"
        for field in ("change_respected", "dropoff_misuse", "dropoff_misuse_before", "dropoff_misuse_after"):
            row.pop(field)
        assert row["speech"] == "authors" and row["relay_calls"] == 0
        for field in list(row):
            if field.startswith(("relay_", "first_plan_maker_")) or field in (
                    "speech", "wording", "stratum", "member_position", "temperature", "retry_temperature"):
                del row[field]
        row["code_version"] = code_stamp
        if version == 3:
            for field in ("dropoff", "told_order_positions", "first_post_event_speakers",
                          "first_told_speaker_positions", "first_told_agent_spoke"):
                row.pop(field)
        for iteration in row["iterations"]:
            for field in list(iteration):
                if field.startswith("plan_maker") or (version == 3 and field in ("central_plan_agents", "told_in_central_plan")):
                    del iteration[field]
    elif path.parent.name == "calls":
        row = read_json(path)
        for attempt in row["attempts"]:
            assert attempt.pop("temperature") == 0.0
    else:
        return path.read_bytes()
    return (json.dumps(row, ensure_ascii=False, indent=2) + "\n").encode()


class NeutralSiteTests(unittest.TestCase):
    def setUp(self):
        temp = tempfile.TemporaryDirectory(dir=ROOT, prefix=".chen-v4-test-")
        self.addCleanup(temp.cleanup)
        self.work = Path(temp.name)

    def play(self, spec, tag, prefix=(), responder=None):
        out = self.work / tag
        out.mkdir()
        budget = Invocation(out, out / "budget.json")
        budget.create(None, 2, "fake")
        replies, ordinary = iter(prefix), fake_model.reply

        def reply(messages, script):
            scripted = next(replies, None)
            return scripted if scripted is not None else ordinary(messages, script)

        with patch.object(fake_model, "reply", side_effect=responder or reply):
            run_episode(spec, out, budget.path, "fake", "correct", 300)
        folder = out / "episodes" / spec.name
        return folder, read_json(folder / "episode.json"), calls(folder)

    def test_initial_states_and_exact_pre_event_messages_in_every_framework(self):
        for framework in FRAMEWORKS:
            base = enrolled_spec(framework, condition="static", dropoff="always")
            initial = read_json(base.env_path)
            static_dir, static, control = self.play(base, framework + "-static")
            for kind in ("static", "e1", "e2"):
                with self.subTest(framework=framework, condition=kind):
                    if kind == "static":
                        folder, row, records = static_dir, static, control
                    else:
                        folder, row, records = self.play(replace(base, condition=kind), framework + kind)
                    site_key = cell_key(row["D2"] if kind == "e2" else row["D"])
                    expected = {k: items + (["dropoff"] if k == site_key else []) for k, items in initial.items()}
                    self.assertEqual(read_json(folder / "pg_state/pg_state1.json"), expected)
                    for p in (folder / "pg_state").glob("*.json"):
                        s = read_json(p)
                        self.assertEqual(sum(items.count("dropoff") for items in s.values()), 1)
                        self.assertIn("dropoff", s[site_key])
                        self.assertNotRegex(p.read_text(), r"dropoff_|_returned")
                    self.assertTrue(row["strict_success"] and row["success"])
                    if kind == "e1":
                        k, a, d = row["event_step"], row["A"], row["D"]
                        self.assertEqual([r["messages"] for r in control if r["step"] <= k],
                                         [r["messages"] for r in records if r["step"] <= k])
                        self.assertEqual(row["event"]["state_before"], row["event"]["state_after"])
                        self.assertEqual(row["event"]["announcement"], f"Change of orders (announced after step {k}): "
                                         f"the order for boxes of colour {a} has changed. They are no longer wanted in "
                                         f"target_{a}. They are now wanted in the dropoff at square{d}. A box_{a} that "
                                         f"is put into target_{a} from now on counts as a wrong delivery.")
                    for call in records:
                        text = call["messages"][1]["content"]
                        self.assertNotRegex(text, r"dropoff_|_returned|returned_box_id")
                        self.assertEqual("Change of orders" in text, call["told"])

    def test_untold_cmas_input_identical_to_static_through_completion(self):
        # Reuse the map IDs that motivated the change, from the local frozen generator.
        for size, seed in (("2x2", 1), ("4x8", 0)):
            base = enrolled_spec(condition="static", seed=seed, dropoff="always")
            path = ROOT / "envs" / size / f"env{seed}.json"
            rows, cols = map(int, size.split("x"))
            base = replace(base, rows=rows, cols=cols, env_path=path, env_hash=digest(path.read_bytes()),
                           event_hash=digest(event_path(path).read_bytes()))
            _, static, control = self.play(base, size + "-static")
            _, event, private = self.play(replace(base, condition="e1", tell="member"), size + "-private")
            self.assertTrue(event["event_fired"] and event["success"] and static["strict_success"])
            self.assertFalse(event["strict_success"])
            self.assertEqual(event["wrong_deliveries"], event["box_A_left_at_event"])
            self.assertEqual([(r["messages"], r["response"]) for r in private],
                             [(r["messages"], r["response"]) for r in control])
            self.assertEqual(static["final_state"], event["final_state"])
            self.assertFalse(any(r["told"] for r in private))

    def test_neutral_actions_follow_all_author_actions_and_site_cannot_move(self):
        items = ["target_blue", "box_blue", "target_red", "box_red", "box_blue"]
        square = "0.5_0.5"
        board = {square: items + ["dropoff"], "0.5_1.5": ["box_red"], "1.5_0.5": [], "1.5_1.5": []}
        control = dict(board, **{square: items})
        def observations(b):
            central = state_update_func(2, 2, b)
            local, others = state_update_func_local_agent(2, 2, 0, 0, b, returned_only=True)
            _, from_neighbour = state_update_func_local_agent(2, 2, 0, 1, b, returned_only=True)
            return (central.splitlines()[0], local, from_neighbour.splitlines()[0]), others
        before, _ = observations(control)
        after, others = observations(board)
        for old, new in zip(before, after, strict=True):
            def actions(line):
                return ast.literal_eval(line.split("can do ")[1])
            self.assertEqual(actions(new), actions(old) + [f"move({box}, dropoff)" for box in items if box.startswith("box_")])
        self.assertNotIn("dropoff", others)
        for name in ("box_red", "box_blue"):
            good = plan(((.5, .5), name, "dropoff"))
            checked, repairs = with_action_syntactic_check_func(board, good, [], [], "fake", "_w_all_dialogue_history",
                                                                 "CMAS", returned_only=True)
            self.assertEqual((checked, repairs), (good, []))
            feedback, updated = action_from_response(board, json.loads(good), returned_only=True)
            expected = board[square].copy()
            expected.remove(name)
            self.assertEqual((feedback, updated[square]), ("", expected))
        for bad in (plan(((.5, .5), "dropoff", "square[0.5, 1.5]")),
                    plan(((.5, 1.5), "box_red", "dropoff"))):
            feedback, unchanged = action_from_response(board, json.loads(bad))
            self.assertTrue(feedback)
            self.assertEqual(board, unchanged)
            with patch("env1_create.GPT_response", return_value=("{}", 18)):
                _, repairs = with_action_syntactic_check_func(board, bad, ["prompt"], [], "fake",
                                                              "_w_all_dialogue_history", "CMAS")
            self.assertEqual(repairs, [18])

    def test_wrong_deliveries_and_trigger_boundary(self):
        board = {f"{i+.5}_{j+.5}": ["box_blue", "target_blue", "box_red", "target_red"] * 2
                 for i in range(2) for j in range(2)}
        spec = fixture_spec(self.work / "board.json", board, "e1", event_step_override=1, dropoff="always")
        a = read_json(event_path(spec.env_path))
        d, colour = a["D"], a["A"]
        other = "red" if colour == "blue" else "blue"
        route_a = plan((d, "box_" + colour, "dropoff"))
        route_other = plan((d, "box_" + other, "dropoff"))
        other_square = next([i+.5, j+.5] for i in range(2) for j in range(2) if [i+.5, j+.5] != d)
        wrong_target = plan((other_square, "box_" + colour, "target_" + colour))
        _, row, _ = self.play(spec, "changed", [route_a, route_a, route_other, wrong_target])
        self.assertTrue(row["success"] and row["first_plan_respected_change"])
        self.assertEqual((row["wrong_deliveries"], row["strict_success"], row["boxes_left"]), (3, False, 0))
        self.assertEqual(row["correct_deliveries"] + 3, boxes(board).total())
        self.assertEqual([it["plan_wrong"] for it in row["iterations"][1:4]], [False, True, True])
        self.assertIn("dropoff", row["final_state"][cell_key(d)])
        _, static, _ = self.play(replace(spec, condition="static"), "static-wrong", [route_a])
        self.assertEqual((static["success"], static["strict_success"], static["boxes_left"], static["wrong_deliveries"]),
                         (True, False, 0, 1))

    def e2_fixture(self):
        board = {"0.5_0.5": ["box_blue", "box_blue", "target_blue", "target_blue", "target_blue"],
                 "0.5_1.5": ["box_blue"], "1.5_0.5": [], "1.5_1.5": []}
        return fixture_spec(self.work / "blue.json", board, "e2", dropoff="always")

    def test_returned_id_last_when_another_copy_is_present_or_arrives(self):
        spec = self.e2_fixture()
        x, via, d, b = (.5, .5), (.5, 1.5), (1.5, 1.5), "box_blue"
        deliver = plan((x, b, "target_blue"))
        _, r, records = self.play(spec, "collision", [
            deliver, deliver, plan((via, b, "square[0.5, 0.5]"), (x, b, "target_blue")),
            plan((x, b, "square[0.5, 1.5]")), plan((via, b, "square[1.5, 1.5]")), plan((d, b, "dropoff"))])
        self.assertEqual((r["D2"], r["event"]["X"], r["event"]["returned_box_id"]), (list(d), list(x), 0))
        self.assertEqual(r["event"]["announcement"], "Change of orders (announced after step 1): the box of colour blue "
                         "that was just delivered at square[0.5, 0.5] was not accepted. It is back in square[0.5, 0.5] "
                         "and is now wanted in the dropoff at square[1.5, 1.5].")
        self.assertEqual([it["applied_box_ids"] for it in r["iterations"]], [[0], [1], [2, 2], [0], [0], [0]])
        self.assertEqual((r["first_plan_returned_towards_D2"], r["first_plan_after_event_wrong"]), (False, False))
        self.assertEqual((r["strict_success"], r["correct_deliveries"], r["steps_to_returned_dropoff"]), (True, 3, 5))
        self.assertEqual(r["final_state"][cell_key(d)], ["dropoff"])
        for c in records:
            self.assertNotRegex(str(c["messages"]), r"_returned|returned_box_id|applied_box_ids|dropoff_blue")

    def test_returned_target_and_ordinary_same_colour_dropoff_are_both_wrong(self):
        spec = self.e2_fixture()
        x, via, d, b = (.5, .5), (.5, 1.5), (1.5, 1.5), "box_blue"
        deliver = plan((x, b, "target_blue"))
        _, r, _ = self.play(spec, "wrong-ids", [
            deliver, plan((x, b, "square[0.5, 1.5]")), deliver, plan((via, b, "square[1.5, 1.5]")),
            plan((d, b, "dropoff")), plan((via, b, "square[0.5, 0.5]")), deliver])
        self.assertEqual((r["success"], r["strict_success"], r["wrong_deliveries"], r["correct_deliveries"]),
                         (True, False, 2, 1))
        self.assertFalse(r["first_plan_returned_towards_D2"])  # The ordinary box made the first hop.
        self.assertTrue(r["iterations"][2]["plan_wrong"])
        self.assertTrue(r["iterations"][4]["plan_wrong"])
        self.assertIsNone(r["iterations"][3]["plan_towards_dropoff"])
        self.assertIsNone(r["steps_to_returned_dropoff"])

    def test_told_speaking_positions_and_denominators(self):
        rows = []
        for seed, fixed, actual in ((3, 2, None), (4, 3, 2)):
            spec = enrolled_spec("DMAS", seed=seed, tell="member", dropoff="always")
            _, r, log = self.play(spec, f"dmas-{seed}")
            m = r["M"]
            first = [c for c in log if c["step"] == r["event_step"] + 1]
            self.assertEqual(r["first_post_event_speakers"], [c["speaker"] for c in first])
            self.assertEqual(r["first_post_event_speakers"], ["Agent[0.5, 0.5]", "Agent[1.5, 0.5]"])
            self.assertEqual((r["told_order_positions"], r["first_told_speaker_positions"]), ({m: fixed}, {m: actual}))
            self.assertEqual(r["first_told_agent_spoke"], actual is not None)
            rows.append(r)
        output = io.StringIO()
        with contextlib.redirect_stdout(output):
            compare(rows, Counter())
        head, line = output.getvalue().splitlines()
        group = dict(zip(head.split(" | "), line.split(" | "), strict=True))
        self.assertEqual(group["mean fixed order position"], "2.50 (2/2)")
        self.assertEqual(group["mean position among speakers"], "2.00 (1/2)")
        self.assertEqual(group["first iteration told agent spoke"], "50.0% (1/2)")

        for fw in ("CMAS", "HMAS-1"):
            spec = enrolled_spec(fw, seed=3, tell="member", dropoff="always")
            _, r, _ = self.play(spec, fw)
            self.assertEqual(r["told_order_positions"], {r["M"]: 2 if fw == "HMAS-1" else None})
            if fw == "CMAS":
                self.assertFalse(r["first_told_agent_spoke"])
        _, unfired, _ = self.play(replace(spec, event_step_override=100), "no-event")
        self.assertIsNone(unfired["first_post_event_speakers"])
        self.assertIsNone(unfired["first_told_agent_spoke"])

    def test_review_membership_uses_the_proposal_before_revision(self):
        spec = enrolled_spec("HMAS-2", event_step_override=1, tell="member", dropoff="always")
        m = read_json(event_path(spec.env_path))["M"]
        initial = plan(((.5, .5), "box_purple", "target_purple"))
        _, r, records = self.play(spec, "revised", ["{}", initial, "Please reconsider.", "{}"])
        self.assertEqual(r["iterations"][0]["told_in_central_plan"], {m: False})
        first = r["iterations"][1]
        self.assertEqual((first["central_plan_agents"], first["issued_plan"], first["told_in_central_plan"]),
                         ([m], {}, {m: True}))
        self.assertEqual(r["first_post_event_speakers"], [r["L"], m, r["L"]])
        self.assertEqual((r["first_told_speaker_positions"], r["first_told_agent_spoke"]), ({m: 2}, True))
        for c in records:
            self.assertEqual(c["told"], c["step"] > 1 and c["role"] == "review" and c["speaker"] == m)
            self.assertEqual(r["event"]["announcement"] in str(c["messages"]), c["told"])

    def test_e2_member_notice_on_local_turn_only_when_member_is_leader(self):
        for fw in ("CMAS", "HMAS-2"):
            spec = enrolled_spec(fw, condition="e2", tell="member", dropoff="always")
            _, row, trace = self.play(spec, fw)
            self.assertTrue(row["leader_is_member"])
            member, k = row["M"], row["trigger_step"]
            for call in trace:
                told = call["step"] > k and call["role"] == "review" and call["speaker"] == member
                self.assertEqual(call["told"], told)
                for message in call["messages"]:
                    self.assertNotRegex(message["content"], r"dropoff_|_returned|returned_box_id")
                self.assertEqual(row["event"]["announcement"] in call["messages"][1]["content"], told)
            self.assertEqual(row["first_told_agent_spoke"], fw == "HMAS-2")
            if fw == "HMAS-2":
                first = row["first_post_event_speakers"]
                self.assertEqual((first[0], first[-1]), (member, member))
                self.assertEqual(row["first_told_speaker_positions"][member], len(first))
                for it in row["iterations"]:
                    proposal = it["central_plan_agents"]
                    self.assertEqual(it["told_in_central_plan"][member], member in proposal)

    def test_all_enrolled_maps_and_original_sidecars(self):
        root = ROOT / "envs"
        maps, events = read_json(root / "manifest.json"), read_json(root / "events-manifest.json")
        for recorded, current in (("maps-before.json", maps), ("events-before.json", events)):
            original = read_json(REGRESSION / "chen2d-4" / recorded)
            self.assertEqual({name: current[name] for name in original}, original)
        for size in SIZE_NAMES:
            for seed in range(20):
                with self.subTest(size=size, seed=seed):
                    path = root / size / f"env{seed}.json"
                    sidecar = event_path(path)
                    for p, manifest in ((path, maps), (sidecar, events)):
                        self.assertEqual(digest(p.read_bytes()), manifest[str(p.relative_to(root))])
                    initial, a = read_json(path), read_json(sidecar)
                    states = [initial] + [s for s, _ in reference_trajectory(initial, action_from_response)]
                    remaining = boxes(states[a["event_step"]])
                    self.assertEqual((a["S"], a["reference_box_A_left"]), (len(states)-1, remaining[a["A"]]))
                    self.assertGreaterEqual(remaining[a["A"]], 1)
                    self.assertEqual(remaining[a["A"]], max(remaining.values()))
                    self.assertEqual(a["M"], agent_at(a["D"]))
        self.assertEqual(seed_selection("0-2,4,8-9"), [0, 1, 2, 4, 8, 9])
        for bad in ("2-1", "0-2,2", "-1", "1,,3"):
            with self.assertRaises(ValueError):
                seed_selection(bad)

    def test_cli_records_default_refuses_mixed_modes_and_wrong_episode(self):
        always, event = self.work / "default", self.work / "legacy"
        def run(path, *options):
            return cli("run_chen2d.py", "--out", path, "--model", "fake", "--conditions", "static",
                       "--frameworks", "CMAS", "--sizes", "2x2", "--envs", "0-1", *options)
        for path, mode, options in ((always, "always", ()), (event, "event", ("--dropoff", "event"))):
            result = run(path, *options)
            self.assertEqual(result.returncode, 0, result.stderr)
            self.assertEqual(read_json(path / "run.json")["dropoff"], mode)
            self.assertEqual([read_json(p)["dropoff"] for p in path.glob("episodes/*/episode.json")], [mode] * 2)
            self.assertIn("dropoff " + mode, cli("summarize.py", path).stdout)
        self.assertNotEqual(run(always, "--dropoff", "event").returncode, 0)
        self.assertIn("different dropoff", cli("summarize.py", always, event).stderr)
        archived = REGRESSION / "chen2d-3/batch1"
        self.assertIn("different dropoff", cli("summarize.py", always, archived).stderr)
        self.assertIn("Refusing to mix code versions", cli("summarize.py", event, archived).stderr)
        p = next(always.glob("episodes/*/episode.json"))
        csv = (always / "episodes.csv").read_bytes()
        write_json(p, dict(read_json(p), dropoff="event"))
        self.assertIn("dropoff", cli("summarize.py", always).stderr)
        self.assertEqual(csv, (always / "episodes.csv").read_bytes())

    def test_resume_reconstructs_the_hidden_id_from_the_paid_prefix(self):
        spec = enrolled_spec(condition="e2", dropoff="always")
        _, complete, _ = self.play(spec, "whole")
        out = self.work / "resumed"
        out.mkdir()
        first = Invocation(out, out / "first.json")
        first.create(complete["trigger_step"] + 1, 1, "fake")
        run_episode(spec, out, first.path, "fake", "correct", 300)
        path = out / "episodes" / spec.name / "episode.json"
        interrupted = read_json(path)
        self.assertTrue(interrupted["event_fired"])
        self.assertFalse(interrupted["finished"])
        second = Invocation(out, out / "second.json")
        second.create(None, 1, "fake")
        run_episode(spec, out, second.path, "fake", "correct", 300)
        resumed = read_json(path)
        for key in ("event", "strict_success", "correct_deliveries", "wrong_deliveries", "steps_to_returned_dropoff",
                    "first_told_speaker_positions", "final_state", "api_calls"):
            self.assertEqual(resumed[key], complete[key], key)
        self.assertEqual([it["applied_box_ids"] for it in resumed["iterations"]],
                         [it["applied_box_ids"] for it in complete["iterations"]])
        self.assertEqual(complete["api_calls"], read_json(first.path)["calls"] + read_json(second.path)["calls"])

    def test_version_three_episode_bytes(self):
        archive = REGRESSION / "chen2d-3"
        for batch, fw, kind, tell in (("batch1", "CMAS", "static", "all"), ("batch1", "DMAS", "e1", "member"),
                                      ("e2", "HMAS-1", "e2", "all"), ("e2", "HMAS-2", "e2", "all")):
            with self.subTest(framework=fw, condition=kind):
                spec = enrolled_spec(fw, kind, tell=tell, dropoff="event")
                old = archive / batch / "episodes" / spec.name
                saved, trace = read_json(old / "episode.json"), calls(old)
                # Reproduce even the call-file bytes by replaying recorded clocks and invocation ID.
                call_clock = [t for record in trace for t in (0., record["elapsed_seconds"])]
                step_clock = [t for it in saved["iterations"] for t in (0., it["planning_seconds"])]
                out = self.work / fw
                out.mkdir()
                budget = Invocation(out, out / (trace[0]["invocation"] + ".json"))
                budget.create(None, 1, "fake")
                with (patch("LLM.monotonic", side_effect=call_clock),
                      patch("episode.time", SimpleNamespace(monotonic=iter(step_clock).__next__))):
                    run_episode(spec, out, budget.path, "fake", "correct", 300)
                new = out / "episodes" / spec.name
                files = {p.relative_to(old) for p in old.rglob("*") if p.is_file()}
                self.assertEqual(files, {p.relative_to(new) for p in new.rglob("*") if p.is_file()})
                for file in files:
                    self.assertEqual(archived_bytes(new / file, 3, saved["code_version"]),
                                     (old / file).read_bytes(), str(file))


if __name__ == "__main__":
    unittest.main()
