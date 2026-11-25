from regression_inputs import REGRESSION
"""Folder-local GROUP planning, probe, accounting and compatibility checks."""
import csv
import io
import json
import shutil
import subprocess
import sys
import unittest
from dataclasses import replace
from contextlib import redirect_stdout
from types import SimpleNamespace
from unittest.mock import patch

from LLM import MODEL, wire_prompt
from episode import Spec, run_episode
from limits import OUTPUT_LIMIT, Invocation
from matched_protocol import GROUP_WRITER, JOINT_FORMAT, JOINT_WRITER, OWN_FORMAT, block_shapes, group_partition
from planning_metrics import CUTOFF_SPLITS, MATCHED_CALL_CAP, MATCHED_ENV_CAP, MATCHED_ROUND_CAP
from probe_reading import ARMS, SavedState, build_prompt, judge_reply, run as run_probe, summarize
from prompt_env1 import OWN_DIALOGUE
from storage import ROOT, digest, json_text, read_json, source_hashes, write_json
from test_chen2d import calls, fixture_spec
from test_chen2d_v3 import scripted_transport
from test_chen2d_v4 import cli
from test_chen2d_v5 import local_references
from test_chen2d_v11 import HorizonFixtures
from test_chen2d_v15_probe_exec import args_for


def crossing_board(reverse=False):
    board = {f"{i + .5}_{j + .5}": [] for i in range(2) for j in range(4)}
    box, target = ("0.5_2.5", "0.5_1.5") if reverse else ("0.5_1.5", "0.5_2.5")
    board[box], board[target] = ["box_red"], ["target_red"]
    return board


def peers(call):
    text = call["messages"][1]["content"].split(OWN_DIALOGUE, 1)[1]
    return json.JSONDecoder().raw_decode(text)[0]


def matched_replay_bytes(test, path, raw):
    """Verify the newer provenance fields before comparing every v15 byte."""
    old_shape = ("Use a joint object mapping each acting Agent[row, col] to its action string, with {} for an idle step. "
                 "Use one action string or the JSON literal null for an individual entry. ")

    def restore_prompt(prompt):
        if JOINT_WRITER in prompt:
            prompt = prompt.replace(JOINT_WRITER + "\n" + OWN_DIALOGUE + "{}", JOINT_WRITER)
            shape = JOINT_FORMAT
        else:
            shape = OWN_FORMAT
        test.assertEqual(prompt.count(shape + "\n"), 1)
        return prompt.replace(shape + "\n", old_shape)

    if path.parent.name == "prompt":
        return restore_prompt(raw.decode()).encode()
    if path.parent.name == "calls":
        call = json.loads(raw)
        test.assertEqual(call.pop("plan_note"), "none")
        for attempt in call["attempts"]:
            test.assertEqual(attempt.pop("visible_reply_chars"), len(attempt["raw_output"]))
            test.assertIsNone(attempt.pop("cutoff_reply_class"))
        call["messages"][1]["content"] = restore_prompt(call["messages"][1]["content"])
        test.assertEqual(call.pop("reply_shape"), "list" if call["role"] == "own" else "joint_list")
        test.assertTrue(call.pop("reply_shape_accepted"))
        test.assertIsNone(call.pop("reply_refusal_reason"))
        test.assertIsNone(call.pop("reply_refusal_detail"))
        test.assertEqual((call.pop("reply_attempt_count"), call.pop("transport_attempt_count")), (1, 0))
        test.assertEqual((call.pop("reply_attempt_limit"), call.pop("transport_attempt_limit")), (3, 3))
        return json_text(call).encode()
    if path.name == "episode.json":
        row = json.loads(raw)
        test.assertEqual((row.pop("plan_note"), row.pop("failed_writer")), ("none", "drop"))
        for field in CUTOFF_SPLITS:
            test.assertEqual(row.pop(field), 0)
        raw = json_text(row).encode()
        test.assertIn(b'"list_parser_version": 17', raw)
        return raw.replace(b'"list_parser_version": 17', b'"list_parser_version": 14')
    if path.name == "assignments.json":
        assignments = json.loads(raw)
        for row in assignments.values():
            test.assertEqual((row.pop("plan_note"), row.pop("failed_writer")), ("none", "drop"))
        return json_text(assignments).encode()
    if path.name == "episodes.csv":
        reader = csv.DictReader(io.StringIO(raw.decode()))
        extra = {"plan_note", "failed_writer", *CUTOFF_SPLITS}
        stream = io.StringIO(newline="")
        writer = csv.DictWriter(stream, fieldnames=[k for k in reader.fieldnames if k not in extra])
        writer.writeheader()
        for row in reader:
            test.assertEqual((row.pop("plan_note"), row.pop("failed_writer")), ("none", "drop"))
            for field in CUTOFF_SPLITS:
                test.assertEqual(row.pop(field), "0")
            writer.writerow(row)
        return stream.getvalue().encode()
    return raw


class PartitionTests(unittest.TestCase):
    def test_every_size_exact_cover_order_shapes_and_rejections(self):
        shapes = {
            (2, 2): "1x1 1x2 2x2",
            (2, 4): "1x1 1x2 2x2 2x4",
            (4, 4): "1x1 1x2 2x2 2x4 4x4",
            (4, 8): "1x1 1x2 2x2 2x4 4x4 4x8",
            (2, 8): "1x1 1x2 2x2 2x4 2x8",
            (4, 6): "1x1 1x2 1x3 2x2 2x3 4x3 4x6",
            (6, 6): "1x1 1x2 1x3 2x2 2x3 3x3 2x6 3x6 6x6",
            (8, 8): "1x1 1x2 2x2 2x4 4x4 4x8 8x8",
        }
        for (rows, cols), rectangles in shapes.items():
            expected = [tuple(map(int, shape.split("x"))) for shape in rectangles.split()]
            sizes = {h * w for h, w in expected}
            self.assertEqual(block_shapes(rows, cols), {h * w: (h, w) for h, w in expected})
            for g in set(range(rows * cols + 2)) - sizes:
                with self.assertRaisesRegex(ValueError, f"Valid sizes: {', '.join(map(str, sorted(sizes)))}$"):
                    group_partition(rows, cols, g)
            for h, w in expected:
                part = group_partition(rows, cols, h * w)
                self.assertEqual(len(part.blocks), rows * cols // (h * w))
                members = []
                for n, block in enumerate(part.blocks):
                    top, left = divmod(n, cols // w)
                    expected_block = tuple(f"Agent[{top*h+i+.5}, {left*w+j+.5}]" for i in range(h) for j in range(w))
                    self.assertEqual(block, expected_block)
                    members.extend(block)
                self.assertEqual(len(set(members)), rows * cols)


class GroupTests(HorizonFixtures):
    def group(self, board=None, **options):
        board = crossing_board() if board is None else board
        base = fixture_spec(self.work / "board.json", board, options.pop("condition", "static"), rows=2, cols=4)
        return replace(base, **dict(dict(framework="GROUP", group_size=4, protocol="matched", horizon=5), **options))

    def scripted(self, spec, tag, script="correct", ceiling=300):
        out = self.work / tag
        out.mkdir()
        budget = Invocation(out, out / "script.json")
        budget.create(None, 2, "fake")
        run_episode(spec, out, budget.path, "fake", script, ceiling)
        folder = out / "episodes" / spec.name
        return read_json(folder / "episode.json"), calls(folder), folder

    def test_wire_equivalences_at_h1_and_h5_including_history_relays_and_repairs(self):
        for fw, size in (("CMAS", 8), ("OWN", 1)):
            for h, position, script in ((1, "after", "correct"), (5, "before", "repair"), (1, "before", "invalid")):
                with self.subTest(fw=fw, horizon=h, script=script):
                    group = self.group(horizon=h, group_size=size, condition="e1", tell="member", speech="choice",
                                       event_step_override=0, state_position=position, max_planning_rounds=3)
                    ref = replace(group, framework=fw, group_size=None)
                    a, ac, _ = self.scripted(ref, f"{fw}-{h}-{script}", script)
                    b, bc, _ = self.scripted(group, f"g{size}-{h}-{script}", script)
                    self.assertEqual([(wire_prompt(c["messages"]).encode(), c["response"], c["role"], c["speaker"]) for c in ac],
                                     [(wire_prompt(c["messages"]).encode(), c["response"], c["role"], c["speaker"]) for c in bc])
                    for key in ("final_state", "steps", "success_failure", "first_blocked_cause",
                                "repair_calls", "robots_dropped", "api_calls", "prompt_tokens", "completion_tokens"):
                        self.assertEqual(a[key], b[key], key)
                    self.assertEqual(a["round_log"], [{k: v for k, v in batch.items() if k not in ("callers_per_round", "callers_reached")}
                                                      for batch in b["round_log"]])
                    self.assertEqual([i.get("issued_plan") for i in a["iterations"]], [i.get("issued_plan") for i in b["iterations"]])
                    self.assertTrue(bc)
                    for c in bc:
                        self.assertEqual(c["robots_assigned"], 0 if c["role"] == "relay" else size)
                        self.assertEqual(c["callers_per_round"], 8 // size)
                        self.assertEqual(c["framework"], "GROUP")

    def test_scripted_handover_across_border_both_speaking_directions(self):
        for reverse in (False, True):
            spec = self.group(crossing_board(reverse))
            r, trace, _ = self.scripted(spec, f"handover-{reverse}")
            self.assertTrue(r["strict_success"])
            self.assertEqual((r["steps"], r["planning_rounds"]), (2, 2 if reverse else 1))
            first, second = trace[:2]
            self.assertEqual(peers(first), {})
            self.assertEqual(peers(second), {first["speaker"]: json.loads(first["response"])})
            self.assertEqual([c["assigned_robots_with_doable_actions"] for c in trace[:2]],
                             [0, 1] if reverse else [1, 0])
            src, dst = ("Agent[0.5, 2.5]", "Agent[0.5, 1.5]") if reverse else ("Agent[0.5, 1.5]", "Agent[0.5, 2.5]")
            executed = [it for it in r["iterations"] if it["executed"]]
            self.assertEqual([it["issued_plan"] for it in executed],
                             [{src: "move(box_red, square" + dst[5:] + ")"}, {dst: "move(box_red, target_red)"}])
            self.assertEqual([list(it["action_calls"].values())[0] for it in executed], [2, 3] if reverse else [1, 2])

    def test_repair_sweeps_hide_entire_invalid_block_and_credit_last_checked_author(self):
        spec = self.group()
        src, dst = "Agent[0.5, 1.5]", "Agent[0.5, 2.5]"
        transfer = "move(box_red, square[0.5, 2.5])"
        failed_first = [{src: transfer, "Agent[1.5, 0.5]": "move(box_x, target_x)"}]
        # Both writers initially fail. A repairs on its second try, B on its first.
        replies = [json.dumps(failed_first), "no plan", json.dumps([{}, {dst: transfer}]),
                   json.dumps([{}, {dst: "move(box_red, target_red)"}]), json.dumps({src: transfer})]
        r, trace, _ = self.play(spec, replies, "sweeps")
        self.assertTrue(r["strict_success"])
        batch, = r["round_log"]
        self.assertEqual([c["status"] for c in batch["checks"]], ["invalid", "parse failure", "parse failure", "valid", "valid"])
        self.assertEqual(peers(trace[1]), {trace[0]["speaker"]: None})
        self.assertEqual(trace[3]["messages"][1], trace[1]["messages"][1])
        self.assertEqual((batch["repair_calls_by_writer"], batch["repair_calls"], batch["repair_attempts"]),
                         ({trace[0]["speaker"]: 2, trace[1]["speaker"]: 1}, 3, 3))
        self.assertEqual([it["action_calls"] for it in r["iterations"]], [{src: 5}, {dst: 4}])
        self.assertEqual([c["assigned_robots_with_doable_actions"] for c in trace], [1, 0, 1, 0, 1])

    def test_exhausted_block_is_null_and_contributes_nothing_to_surviving_block(self):
        board = crossing_board()
        board["0.5_2.5"] += ["box_blue", "target_blue"]
        spec = self.group(board, horizon=1, max_planning_rounds=1)
        right = {"Agent[0.5, 2.5]": "move(box_blue, target_blue)"}
        invalid = json.dumps([{"Agent[0.5, 1.5]": "move(box_red, target_red)"}])
        for reply, cause in ((invalid, "not-doable actions"), ("no list", "unusable replies after repairs")):
            r, trace, folder = self.play(spec, [reply, json.dumps([right]), reply, reply], cause + "-partial")
            self.assertEqual(r["round_log"][0]["proposed_plans"], [right])
            self.assertEqual(r["round_log"][0]["dropped_robots"], list(spec.partition.blocks[0]))
            self.assertEqual(r["robots_dropped"], 4)
            self.assertIsNone(peers(trace[1])[trace[0]["speaker"]])
            self.assertIsNone(json.loads((folder / "dialogue_history/dialogue_history0.txt").read_text())[trace[0]["speaker"]])
            empty, _, _ = self.play(spec, [reply, "[{}]", reply, reply], cause + "-empty")
            self.assertEqual((empty["first_blocked_round"], empty["first_blocked_cause"], empty["success_failure"]),
                             (1, cause, MATCHED_ROUND_CAP))

    def test_joint_leniency_short_lists_late_failure_and_scope_in_strict_mode(self):
        spec = self.group(max_planning_rounds=1)
        src = "Agent[0.50,1.5]"
        first = {src: "move(box_red, square[0.5, 2.5])"}
        future = {src: "move(box_red, target_red)"}
        numbered = json.dumps({"step 2": future, "step 1": first})
        r, trace, _ = self.play(spec, [numbered, "[{}]"], "numbered")
        batch, = r["round_log"]
        self.assertEqual((trace[0]["lenient_rescue"], peers(trace[1])[trace[0]["speaker"]]), (True, [first, future]))
        self.assertEqual((batch["invalid_position"], batch["rejected_calls"], batch["proposed_plans"]),
                         (2, {src: 1}, [first, future, {}, {}, {}]))
        self.assertEqual(r["iterations"][0]["action_calls"], {src: 1})
        # A foreign key anywhere in the list invalidates the submission even if step 1 passes.
        foreign = json.dumps([first, {"Agent[1.5, 3.5]": "move(box_red, target_red)"}] + [{}] * 3)
        idle, permitted = json.dumps([{}] * 5), json.dumps([first] + [{}] * 4)
        r, trace, _ = self.play(replace(spec, parse_mode="strict"), [foreign, idle, numbered, permitted], "strict")
        self.assertEqual([c["status"] for c in r["round_log"][0]["checks"]], ["parse failure", "valid", "parse failure", "valid"])
        self.assertIsNone(peers(trace[1])[trace[0]["speaker"]])

    def test_retry_cutoffs_and_ceilings_use_matched_records(self):
        spec = self.group(max_planning_rounds=1)
        for cap, label, expected_calls in ((0, MATCHED_CALL_CAP, 0), (1, MATCHED_CALL_CAP, 1)):
            r, _, _ = self.scripted(spec, str(cap), ceiling=cap)
            self.assertEqual((r["success_failure"], r["api_calls"], r["first_blocked_cause"]), (label, expected_calls, "ceiling"))
            if cap:
                self.assertEqual((r["round_log"][0]["callers_per_round"], r["round_log"][0]["callers_reached"]), (2, 1))
        r, _, _ = self.scripted(replace(spec, max_env_steps=1), "env-cap")
        self.assertEqual((r["success_failure"], r["steps"]), (MATCHED_ENV_CAP, 1))
        for tag, kinds, count in (("recovered", ["idle", "truncated", "idle"], "rounds_cutoff_recovered"),
                                  ("exhausted", ["idle"] + ["truncated"] * 3, "rounds_all_attempts_cutoff")):
            out = self.work / tag
            out.mkdir()
            budget = Invocation(out, out / "script.json")
            budget.create(None, 3, MODEL)
            with local_references(), scripted_transport(kinds) as (sent, _):
                run_episode(spec, out, budget.path, MODEL, "correct", 100, 64)
            folder = out / "episodes" / spec.name
            r = read_json(folder / "episode.json")
            self.assertEqual((r[count], r["api_calls"], len(sent)), (1, len(kinds), len(kinds)))
            call = calls(folder)[1]
            self.assertEqual([a["finish_reason"] for a in call["attempts"]],
                             ["length", "stop"] if tag == "recovered" else ["length"] * 3)
            self.assertTrue(all(type(a["reasoning_tokens"]) is int for a in call["attempts"]))
            self.assertEqual(r["cut_calls"][0]["role"], "group_leader")
            if tag == "exhausted":
                self.assertEqual((r["success_failure"], r["first_blocked_cause"]), (OUTPUT_LIMIT, "output limit"))

    def test_v15_matched_episode_trees_with_recorded_clocks_and_versioned_writer_changes(self):
        snapshot = REGRESSION / "chen2d-15/matched-scaled"
        config = read_json(snapshot / "run.json")
        for fw in ("CMAS", "OWN"):
            old = snapshot / "episodes" / f"2x2_{fw}_static_env0"
            row, trace = read_json(old / "episode.json"), calls(old)
            spec = Spec(2, 2, fw, "static", 0, snapshot / "maps/2x2/env0.json", row["env_sha256"], row["event_sha256"],
                        protocol="matched", horizon=5, state_position="after", dropoff="event",
                        map_set="scaled:2", boxes_per_robot=2., box_count=8, reasoning_setting="default")
            out = self.work / fw
            out.mkdir()
            write_json(out / "run.json", config)
            budget = Invocation(out, out / (trace[0]["invocation"] + ".json"))
            budget.create(None, 1, "fake")
            times = [v for it in row["iterations"] if it["calls"] for v in (0., it["planning_seconds"])]
            with (patch("LLM.monotonic", side_effect=[v for c in trace for v in (0., c["elapsed_seconds"])]),
                  patch("episode.time", SimpleNamespace(monotonic=iter(times).__next__)),
                  patch("episode.code_version", return_value=config["code_version"])):
                run_episode(spec, out, budget.path, "fake", "correct", 300)
            new = out / "episodes" / spec.name
            def tree(base):
                return {p.relative_to(base): p.read_bytes() for p in base.rglob("*") if p.is_file()}
            self.assertEqual({p: matched_replay_bytes(self, p, raw) for p, raw in tree(new).items()}, tree(old))


class GroupWorkflowTests(HorizonFixtures):
    def test_default_h1_files_for_all_five_native_and_both_matched_writers_against_v15(self):
        archive = REGRESSION / "chen2d-15/matched-scaled"
        hashes = read_json(archive / "run.json")["source_sha256"]
        # The published v15 client bridge has a relocatable planner path.
        hashes["LLM.py"] = "12c6a358f3d5a552d0214487470f7657fdcfa77d0514248767fd309b5bbe281a"
        files = {}
        driver = """from types import SimpleNamespace
from unittest.mock import patch
import run_chen2d
with (patch('episode.time', SimpleNamespace(monotonic=lambda: 0.0)),
      patch('LLM.monotonic', return_value=0.0),
      patch('run_chen2d.uuid.uuid4', return_value=SimpleNamespace(hex='replay'))):
    run_chen2d.main()
"""
        for label, source, manifest in (("v15", archive / "source", hashes), ("current", ROOT, source_hashes())):
            tree = self.work / label
            tree.mkdir()
            for name, sha in manifest.items():
                self.assertEqual(digest((source / name).read_bytes()), sha)
                shutil.copyfile(source / name, tree / name)
            # Keep option defaults, with one designated map/condition and offline transport.
            # Omission of --frameworks exercises the actual native and matched defaults.
            for run, opts in (("native", []), ("own", ["--frameworks", "OWN"]), ("matched", ["--protocol", "matched"])):
                subprocess.run([sys.executable, "-B", "-c", driver, "--model", "fake", "--conditions", "static",
                                "--envs", "0", "--out", run, *opts], cwd=tree, capture_output=True, check=True)
                out = tree / run
                stamp = read_json(out / "run.json")["code_version"].encode()
                names = [p for p in (out / "episodes").rglob("*") if p.is_file()]
                names += [out / "episodes.csv", out / "assignments.json"]
                files[label, run] = {}
                for name in names:
                    raw = name.read_bytes()
                    if name.name in ("episode.json", "episodes.csv"):
                        raw = raw.replace(stamp, b"<source version>")
                    files[label, run][name.relative_to(out)] = raw
                self.assertEqual(len(list((out / "episodes").iterdir())), {"native": 4, "own": 1, "matched": 2}[run])
        for run in ("native", "own", "matched"):
            self.assertEqual(files["current", run].keys(), files["v15", run].keys())
            for name, raw in files["v15", run].items():
                actual = files["current", run][name]
                if run == "matched":
                    actual = matched_replay_bytes(self, name, actual)
                self.assertEqual(actual, raw, (run, name))

    def test_runner_resume_partition_manifest_and_token_tables_across_sizes(self):
        base = ("--model", "fake", "--protocol", "matched", "--sizes", "4x4", "--envs", "0",
                "--conditions", "static", "--horizon", "5", "--map-set", "scaled:1", "--max-env-steps", "5")
        outputs, totals = [], {}
        for g in (4, 8):
            out = self.work / f"g{g}"
            outputs.append(out)
            command = ("run_chen2d.py", *base, "--frameworks", "GROUP" if g == 4 else "GROUP,CMAS",
                       "--group-size", g, "--out", out)
            short = cli(*command, "--max-calls", 1)
            self.assertEqual(short.returncode, 0, short.stderr)
            folder = next((out / "episodes").glob("*GROUP*"))
            first = folder / "calls/00001.json"
            original = first.read_bytes()
            self.assertFalse(read_json(folder / "episode.json")["finished"])
            completed = cli(*command)
            self.assertEqual(completed.returncode, 0, completed.stderr)
            again = cli(*command)
            self.assertEqual(again.returncode, 0, again.stderr)
            self.assertIn("made 0 calls", again.stdout)
            self.assertEqual(first.read_bytes(), original)
            config = read_json(out / "run.json")
            part = group_partition(4, 4, g)
            self.assertEqual(config["group_partitions"]["4x4"], part.record())
            row = read_json(folder / "episode.json")
            manifest = read_json(out / "assignments.json")[row["episode_id"]]
            self.assertEqual((manifest["framework"], manifest["group_size"], manifest["callers_per_round"]), ("GROUP", g, 16 // g))
            with (out / "episodes.csv").open() as handle:
                line, = (r for r in csv.DictReader(handle) if r["framework"] == "GROUP")
            self.assertEqual((line["group_size"], int(line["callers_per_round"])), (str(g), 16 // g))
            attempts = [a for c in calls(folder) for a in c["attempts"]]
            totals[str(g)] = tuple(sum(a[k] for a in attempts) for k in ("api_calls", "prompt_tokens", "completion_tokens"))
            cost = cli("cost.py", out, "--bootstrap", 10)
            self.assertEqual(cost.returncode, 0, cost.stderr)
            self.assertIn(f"GROUP | {g} | authors", cost.stdout)
            changed = cli(*command, "--group-size", 8 if g == 4 else 4)
            self.assertNotEqual(changed.returncode, 0)
        for options in ((), ("--by", "planning")):
            result = cli("summarize.py", *options, *outputs)
            self.assertEqual(result.returncode, 0, result.stderr)
            heading, *lines = result.stdout.split("Matched protocol, all physical attempts per strict completion\n")[1].splitlines()
            rows = [dict(zip(heading.split(" | "), line.split(" | "), strict=True)) for line in lines]
            observed = {r["group_size"]: tuple(int(r[k]) for k in ("total_calls", "total_prompt_tokens", "total_generated_tokens"))
                        for r in rows if r["framework"] == "GROUP"}
            self.assertEqual(observed, totals)
            self.assertEqual(len(rows), 3)
        demand = cli("output_demand.py", *outputs, "--calls-csv", self.work / "calls.csv")
        self.assertEqual(demand.returncode, 0, demand.stderr)
        with (self.work / "calls.csv").open() as handle:
            demand_rows = list(csv.DictReader(handle))
        for g, (_, _, generated) in totals.items():
            group = [r for r in demand_rows if r["framework"] == "GROUP" and r["group_size"] == g]
            self.assertEqual(sum(int(r["generated_tokens"]) for r in group), generated)
            self.assertTrue(all(r["robots_assigned"] == g and r["map_set"] == "scaled:1" for r in group))

    def test_extended_grids_and_invalid_tiling_through_the_public_entrypoint(self):
        import run_chen2d
        out = self.work / "extended"
        argv = ["run_chen2d.py", "--model", "fake", "--protocol", "matched", "--frameworks", "GROUP", "--group-size", "4",
                "--sizes", "2x8,4x6,6x6,8x8", "--map-set", "scaled:0.5", "--conditions", "static", "--envs", "0",
                "--max-planning-rounds", "1", "--out", str(out)]
        # Exercise map creation in a temporary registry inside this folder.
        with patch("sys.argv", argv), patch("map_sets.ROOT", self.work), redirect_stdout(io.StringIO()):
            run_chen2d.main()
        cfg = read_json(out / "run.json")
        for path in (out / "episodes").glob("*/episode.json"):
            ep = read_json(path)
            r, c = map(int, ep["size"].split("x"))
            self.assertEqual(ep["callers_per_round"], r*c // 4)
            self.assertEqual([a["assigned_robots"] for a in calls(path.parent)], cfg["group_partitions"][ep["size"]]["blocks"])
        self.assertEqual(len(list((out / "episodes").iterdir())), 4)
        for overrides, message in ((("--protocol", "legacy", "--sizes", "2x2"), "requires --protocol matched"),
                                   (("--sizes", "4x6", "--group-size", 8), "Valid sizes: 1, 2, 3, 4, 6, 12, 24"),
                                   (("--frameworks", "CMAS"), "--group-size requires GROUP")):
            p = cli(*argv, *overrides)
            self.assertNotEqual(p.returncode, 0)
            self.assertIn(message, p.stderr)

    def test_active_probe_block_fixed_across_arms_and_peer_judge(self):
        root = self.work
        grid = {f"{i+.5}_{j+.5}": [] for i in range(4) for j in range(4)}
        grid["2.5_3.5"] = ["box_blue", "target_blue"]
        grid["3.5_0.5"] = ["box_red", "target_red"]
        last_robot, left, right = "Agent[3.5, 0.5]", "Agent[2.5, 0.5]", "Agent[2.5, 2.5]"
        move = "move(box_red, target_red)"
        saved = SavedState(root, "example", "same-board", 2, 4, 4, (grid, grid), ("{}",),
                           {last_robot: move}, {"L": right})
        for arm in ARMS:
            first, meta = build_prompt(saved, "group_first", arm, 5, protocol="matched", group_size=4)
            last, late = build_prompt(saved, "group_last", arm, 5, protocol="matched", group_size=4)
            self.assertEqual((meta["robot"], late["robot"], meta["robots_assigned"],
                              meta["assigned_robots_with_doable_actions"], meta["robots_with_doable_actions"]), (right, right, 4, 1, 2))
            self.assertIn(GROUP_WRITER.format(robots=json.dumps(late["assigned_robots"])), last)
            expected = {b[0]: [{last_robot: move} if b[0] == left else {}, {}, {}, {}, {}]
                        for b in group_partition(4, 4, 4).blocks[:-1]}
            self.assertEqual(late["peer_lists"], expected)
            self.assertEqual(first, last.replace(OWN_DIALOGUE + json.dumps(expected), OWN_DIALOGUE + "{}"))
            result = judge_reply(saved, "group_last", json.dumps([{right: move}]), 5, late)
            self.assertEqual((result["proposed_actions"], result["not_doable_actions"], result["conflict_earlier_box"]), (1, 1, 1))
            foreign = judge_reply(saved, "group_last", json.dumps([{last_robot: move}]), 5, late)
            self.assertFalse(foreign["plan_produced"])
            for g, group, baseline in ((1, "group_last", "own_last"), (1, "group_first", "own_first"),
                                       (16, "group_last", "leader"), (16, "group_first", "leader")):
                self.assertEqual(build_prompt(saved, group, arm, 5, protocol="matched", group_size=g)[0],
                                 build_prompt(saved, baseline, arm, 5, protocol="matched")[0])

    def test_probe_fake_calls_guards_resume_and_summary(self):
        out = self.work / "probe"
        args = args_for(out, arms=ARMS, calls=1)
        args.episodes = str(REGRESSION / "chen2d-15/matched-scaled/episodes/4x8_CMAS_static_env0")
        args.callers, args.group_size, args.protocol, args.horizon = ("group_first", "group_last"), 8, "matched", 5
        self.assertEqual(len(run_probe(args)), 1)
        args.max_calls = 7
        self.assertEqual(len(run_probe(args)), 7)
        self.assertEqual(run_probe(args), [])
        summary = summarize(out)
        self.assertEqual((summary["rows"], summary["group_size"], len(summary["cells"]), len(summary["paired"])), (8, 8, 8, 12))
        for cell in (out / "cells").glob("*/result.json"):
            row = read_json(cell)
            trace = read_json(cell.parent / "calls/00001.json")
            self.assertEqual((row["map_set"], row["caller_doable_actions"] > 0, row["plan_produced"], row["not_doable_actions"]),
                             ("scaled:2", True, True, 0))
            self.assertEqual((trace["role"], trace["robots_assigned"], trace["assigned_robots_with_doable_actions"]),
                             ("group", 8, row["assigned_robots_with_doable_actions"]))
        args.group_size = 4
        with self.assertRaisesRegex(ValueError, "configuration differs"):
            run_probe(args)
