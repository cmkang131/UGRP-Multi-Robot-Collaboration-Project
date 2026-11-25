"""Offline board-size, registry and writer regressions for the matched experiment."""
import csv
import json
import random
import tempfile
import unittest
from collections import Counter
from pathlib import Path
from unittest.mock import patch

from board_sizes import SCALED_ONLY_SIZES
from env1_create import action_from_response, saved_env, square_actions, state_update_func, surround_index_func
from fake_model import observed_state
from horizon import check_joint
from map_events import agent_at, boxes, cell_key, reference_trajectory
from map_sets import colour_counts, parse_map_set, saved_scaled_env, scaled_env_create
from storage import ROOT, digest, read_json
from test_chen2d import calls
from test_chen2d_v4 import cli


def csv_rows(path):
    with path.open(newline="") as stream:
        return list(csv.DictReader(stream))


def checked_cli(*args):
    result = cli(*args)
    if result.returncode:
        raise AssertionError(f"{args[0]} failed:\n{result.stderr}\n{result.stdout}")
    return result.stdout


STATIC = ("--model", "fake", "--protocol", "matched", "--map-set", "scaled:1",
          "--conditions", "static", "--envs", "0", "--state-position", "after")
ALL_SIZES = ",".join(SCALED_ONLY_SIZES)
STRUCTURES = ("--frameworks", "CMAS,GROUP,OWN", "--group-size", "3")


class RegistryTests(unittest.TestCase):
    def test_published_registry_file_bytes_match_pre_enrolment(self):
        # Hash lines are sorted by path relative to the original registry. Include
        # the old manifests, sidecars and lock files, as well as the maps.
        originals = {
            "envs": (863, "1fbcd1125c64705bd91d98fe48b9fbe335c2648b1c2802886fdd5531fa9c8039"),
            "envs-scaled/r0.5": (99, "2b9e5a8af1a465d7d8578e8560731262200ca97abdf9a0ea0dbec024219f13e1"),
            "envs-scaled/r1": (99, "bf0feba1c11e71aa340552702e15d1acfe5ad2c8956700f4d14957efcbdc9d5c"),
            "envs-scaled/r2": (99, "eaafdb9770db3c381ea99f4c48e29434f2f6c1011d4634186fcb7a2b5d671788"),
        }
        for name, expected in originals.items():
            root = ROOT / name
            files = sorted(p.relative_to(root) for p in root.rglob("*") if p.is_file())
            if name in ("envs-scaled/r1", "envs-scaled/r2"):
                # The three pilot-only board sizes were enrolled after the frozen registry.
                files = [p for p in files if p.parts[0] not in SCALED_ONLY_SIZES]
            data = "".join(f"{p} {digest((root / p).read_bytes())}\n" for p in files)
            self.assertEqual((len(files), digest(data.encode())), expected, name)
            for manifest in ("manifest.json", "events-manifest.json"):
                for path, sha in read_json(root / manifest).items():
                    self.assertEqual(digest((root / path).read_bytes()), sha, path)
        for size in SCALED_ONLY_SIZES:
            self.assertFalse((ROOT / "envs" / size).exists())

    def test_all_48_maps_regenerate_and_reference_delivers_every_box(self):
        for size in SCALED_ONLY_SIZES:
            rows, cols = map(int, size.split("x"))
            root = ROOT / "envs-scaled/r1" / size
            maps, events = (read_json(root / f) for f in ("manifest.json", "events-manifest.json"))
            for seed in range(16):
                with self.subTest(size=size, seed=seed):
                    path, event_path = root / f"env{seed}.json", root / f"env{seed}.event.json"
                    self.assertEqual(digest(path.read_bytes()), maps[path.name])
                    self.assertEqual(digest(event_path.read_bytes()), events[event_path.name])
                    state, event = read_json(path), read_json(event_path)
                    self.assertEqual(state, scaled_env_create(rows, cols, 1, rng=random.Random(seed)))
                    self.assertEqual(boxes(state), Counter(colour_counts(rows * cols)))
                    self.assertEqual((event["env_sha256"], event["seed"], event["map_set"], event["box_count"]),
                                     (maps[path.name], seed, "scaled:1", rows * cols))
                    self.assertIn(cell_key(event["D"]), state)
                    self.assertIn(cell_key(event["D2"]), state)
                    self.assertNotEqual(event["L"], event["M"])
                    self.assertEqual(event["M"], agent_at(event["D"]))
                    trajectory = list(reference_trajectory(state, action_from_response))
                    self.assertEqual(len(trajectory), event["S"])
                    self.assertFalse(boxes(trajectory[-1][0]))
                    self.assertLessEqual(len(trajectory), 30)

    def test_other_scaled_rate_and_corrupt_size_local_event(self):
        with tempfile.TemporaryDirectory(dir=ROOT) as tmp, patch("map_sets.ROOT", Path(tmp)):
            args = (1, 3, 4, parse_map_set("scaled:3"))
            path, sha, meta = saved_scaled_env(*args)
            self.assertEqual((meta["box_count"], boxes(read_json(path)).total()), (9, 9))
            self.assertEqual(saved_scaled_env(*args)[1], sha)
            path.with_suffix(".event.json").write_text("{}")
            with self.assertRaisesRegex(ValueError, "modified enrolled scaled event"):
                saved_scaled_env(*args)
            with self.assertRaisesRegex(ValueError, "no legacy maps"):
                saved_env(1, 3, 0, Path(tmp) / "legacy")
            self.assertFalse((Path(tmp) / "legacy").exists())

    def test_measurement_cli_accepts_the_three_new_sizes(self):
        with tempfile.TemporaryDirectory(dir=ROOT) as tmp:
            out = Path(tmp) / "measurements.json"
            checked_cli("scaled_map_measurements.py", "--sizes", ALL_SIZES, "--rates", "1", "--envs", "0-1", "--out", out)
            rows = read_json(out)
            self.assertEqual(len(rows), 12)
            self.assertEqual({(r["size"], r["seed"], r["horizon"]) for r in rows},
                             {(s, n, h) for s in SCALED_ONLY_SIZES for n in range(2) for h in (1, 5)})
            self.assertTrue(all(r["scripted_planning_rounds"] == (r["scripted_steps"] + r["horizon"] - 1) // r["horizon"]
                                for r in rows))

    def test_one_row_ends_have_one_neighbour_and_no_vertical_move(self):
        state = {f"0.5_{j + .5}": ["box_blue", "target_blue"] for j in range(3)}
        allowed = {}
        for j, columns in enumerate(((1.5,), (.5, 2.5), (1.5,))):
            neighbours = surround_index_func(1, 3, 0, j)
            self.assertEqual(neighbours, [[.5, col] for col in columns])
            name = agent_at((.5, j + .5))
            allowed[name] = square_actions(state[f"0.5_{j + .5}"], neighbours, False)
            self.assertEqual(allowed[name], [*(f"move(box_blue, square[0.5, {c}])" for c in columns),
                                             "move(box_blue, target_blue)"])
        prompt = state_update_func(1, 3, state)
        self.assertEqual(list(observed_state(prompt)), [(.5, .5), (.5, 1.5), (.5, 2.5)])
        off_board = {"Agent[0.5, 0.5]": "move(box_blue, square[1.5, 0.5])"}
        self.assertEqual(check_joint(state, off_board, allowed, False)[1], off_board)


class RunnerTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        scratch = tempfile.TemporaryDirectory(dir=ROOT, prefix=".chen18-tests-")
        cls.addClassCleanup(scratch.cleanup)
        cls.root = Path(scratch.name)
        for h in (1, 5):
            checked_cli("run_chen2d.py", *STATIC, *STRUCTURES, "--sizes", ALL_SIZES,
                        "--horizon", h, "--out", cls.root / f"h{h}")

    def test_all_structures_finish_and_call_the_recorded_writers_in_order(self):
        for h in (1, 5):
            out = self.root / f"h{h}"
            partitions = read_json(out / "run.json")["group_partitions"]
            assigned = read_json(out / "assignments.json")
            records = csv_rows(out / "episodes.csv")
            self.assertEqual(len(records), 9)
            for row in records:
                size, fw = row["size"], row["framework"]
                rows, cols = map(int, size.split("x"))
                teams = [[agent_at((i + .5, j + .5)) for j in range(cols)] for i in range(rows)]
                robots = [robot for team in teams for robot in team]
                folder = out / "episodes" / row["episode_id"]
                ep = read_json(folder / "episode.json")
                manifest = assigned[row["episode_id"]]
                with self.subTest(horizon=h, size=size, framework=fw):
                    self.assertEqual((ep["size"], manifest["size"], row["map_set"], int(row["box_count"])),
                                     (size, size, "scaled:1", len(robots)))
                    self.assertTrue(ep["finished"] and ep["strict_success"])
                    self.assertEqual((ep["boxes_left"], ep["correct_deliveries"]), (0, len(robots)))
                    self.assertEqual((ep["max_env_steps"], ep["max_planning_rounds"]), (30, 30))
                    self.assertEqual(partitions[size]["blocks"], teams)
                    self.assertEqual(partitions[size]["block_shape"], [1, 3])
                    speakers = [ep["L"]] if fw == "CMAS" or (fw == "GROUP" and rows == 1) else (
                        [team[0] for team in teams] if fw == "GROUP" else robots)
                    if fw == "GROUP":
                        self.assertEqual((int(row["callers_per_round"]), manifest["group_size"]), (rows, 3))
                    for batch in ep["round_log"]:
                        self.assertEqual([c["speaker"] for c in batch["checks"]], speakers)
                    self.assertEqual((ep["api_calls"], ep["repair_calls"]), (len(speakers) * ep["planning_rounds"], 0))

    def test_endpoint_wire_messages_responses_and_merged_plans(self):
        for h in (1, 5):
            base = self.root / f"h{h}" / "episodes"
            for g, sizes, fw in ((1, SCALED_ONLY_SIZES, "OWN"), (3, ("1x3",), "CMAS"), (9, ("3x3",), "CMAS")):
                out = self.root / f"g{g}-h{h}"
                if g != 3:
                    checked_cli("run_chen2d.py", *STATIC, "--horizon", h, "--sizes", ",".join(sizes),
                                "--frameworks", "GROUP", "--group-size", g, "--out", out)
                for size in sizes:
                    with self.subTest(horizon=h, size=size, g=g):
                        a = base / f"{size}_{fw}_static_env0"
                        b = (base if g == 3 else out / "episodes") / f"{size}_GROUP-g{g}_static_env0"
                        def wire(path):
                            return [(c["speaker"], c["role"], c["messages"], c["response"]) for c in calls(path)]
                        self.assertEqual(wire(a), wire(b))
                        left, right = [read_json(p / "episode.json") for p in (a, b)]
                        for field in ("steps", "planning_rounds", "api_calls", "final_state"):
                            self.assertEqual(left[field], right[field])
                        self.assertEqual([r["proposed_plans"] for r in left["round_log"]],
                                         [r["proposed_plans"] for r in right["round_log"]])
                        self.assertEqual([i["issued_plan"] for i in left["iterations"]],
                                         [i["issued_plan"] for i in right["iterations"]])

    def test_two_repairs_per_writer_on_each_size(self):
        out = self.root / "repairs"
        checked_cli("run_chen2d.py", *STATIC, *STRUCTURES, "--sizes", ALL_SIZES, "--horizon", 5,
                    "--fake-script", "invalid", "--max-planning-rounds", 1, "--out", out)
        for path in (out / "episodes").glob("*/episode.json"):
            row = read_json(path)
            rows, cols = map(int, row["size"].split("x"))
            writers = {"CMAS": 1, "GROUP": rows, "OWN": rows * cols}[row["framework"]]
            self.assertEqual((row["api_calls"], row["repair_calls"], row["steps"]), (3 * writers, 2 * writers, 0))
            self.assertEqual(list(row["round_log"][0]["repair_calls_by_writer"].values()), [2] * writers)

    def test_clear_refusals_at_public_entry_points(self):
        for opts, reason in (
            (("--sizes", "2x2,1x3", "--map-set", "legacy"), "1x3 has no legacy maps"),
            (("--sizes", "2x3", "--protocol", "legacy"), "2x3 requires --protocol matched"),
            (("--sizes", "3x3", "--group-size", 2), "Valid sizes: 1, 3, 9"),
            (("--sizes", "3x4"), "Invalid selection"),
            (("--sizes", "1x3", "--conditions", "static,e1"), "supports --conditions static only"),
            (("--sizes", "2x3", "--conditions", "e2"), "supports --conditions static only"),
        ):
            out = self.root / "refused"
            result = cli("run_chen2d.py", *STATIC, *STRUCTURES, *opts, "--out", out)
            self.assertNotEqual(result.returncode, 0)
            self.assertIn(reason, result.stderr)
            self.assertFalse((out / "assignments.json").exists())
        for flags in ((), ("--map-set", "legacy"), ("--set", "legacy")):
            result = cli("enrol_maps.py", "--sizes", ALL_SIZES, "--envs", "0", *flags)
            self.assertNotEqual(result.returncode, 0)
            self.assertIn("--map-set scaled:R", result.stderr)
        for flags in (("--boxes-per-robot", 1), ("--map-set", "scaled:1")):
            self.assertIn("3x3 | 0 | scaled:1 | 1.0 | 9", checked_cli("enrol_maps.py", "--sizes", ALL_SIZES,
                                                                      "--envs", "0", *flags))

    def test_summary_cost_and_probe_filters_reconcile_selected_sizes(self):
        out = self.root / "h5"
        records = csv_rows(out / "episodes.csv")
        expected = {(r["size"], r["framework"]): int(r["api_calls"]) for r in records if r["size"] != "2x3"}
        args = ("--sizes", "1x3,3x3")
        summary = checked_cli("summarize.py", out, "--by", "planning", *args)
        title = "Matched protocol, all physical attempts per strict completion\n"
        table = csv.DictReader(summary.split(title)[1].replace(" | ", "|").splitlines(), delimiter="|")
        self.assertEqual({(r["size"], r["framework"]): int(r["total_calls"]) for r in table}, expected)
        self.assertEqual(csv_rows(out / "episodes.csv"), records)
        costs = checked_cli("cost.py", out, *args, "--bootstrap", 10)
        selected = [line.replace(" | ", "|") for line in costs.splitlines()
                    if line.startswith(("size | framework", "1x3 | ", "3x3 | ")) and " | static | " not in line]
        self.assertEqual({(r["size"], r["framework"]): int(r["calls sum"])
                          for r in csv.DictReader(selected, delimiter="|")}, expected)
        probe = self.root / "probe"
        episodes = ",".join(str(out / "episodes" / f"{size}_CMAS_static_env0") for size in SCALED_ONLY_SIZES)
        flags = ("--model", "fake", "--episodes", episodes, "--protocol", "matched", "--group-size", 3,
                 "--callers", "group_first,group_last", "--arms", "none", "--per-episode", 1, "--out", probe)
        checked_cli("probe_reading.py", *flags, *args, "--max-calls", 1)
        planned = read_json(probe / "planned-cells.json")
        self.assertEqual(Counter(p["size"] for p in planned), {"1x3": 2, "3x3": 2})
        pending = json.loads(checked_cli("probe_reading.py", "--summarize", probe, "--sizes", "3x3"))
        self.assertEqual(pending["rows"], 0)
        self.assertTrue(all(c["states_unasked"] == 1 for c in pending["cells"].values()))
        checked_cli("probe_reading.py", *flags, *args)
        complete = json.loads(checked_cli("probe_reading.py", "--summarize", probe))
        subset = json.loads(checked_cli("probe_reading.py", "--summarize", probe, "--sizes", "3x3"))
        self.assertEqual((complete["rows"], subset["rows"], read_json(probe / "summary.json")["rows"]), (4, 2, 4))
        middle = self.root / "probe-2x3"
        checked_cli("probe_reading.py", *flags, "--out", middle, "--sizes", "2x3")
        middle_rows = [json.loads(line) for line in (middle / "results.jsonl").read_text().splitlines()]
        self.assertEqual([(r["size"], r["robots_assigned"], r["plan_produced"]) for r in middle_rows],
                         [("2x3", 3, True)] * 2)
        result = cli("probe_reading.py", "--model", "fake", "--episodes", episodes, "--sizes", "2x3",
                     "--callers", "leader", "--out", self.root / "unmatched")
        self.assertNotEqual(result.returncode, 0)
        self.assertIn("2x3 requires --protocol matched", result.stderr)

    def test_resume_adds_only_the_requested_new_partitions(self):
        out = self.root / "resume"
        args = ("run_chen2d.py", *STATIC, "--frameworks", "GROUP", "--group-size", 1, "--out", out)
        checked_cli(*args, "--sizes", "2x2")
        old = read_json(out / "run.json")["group_partitions"]
        self.assertFalse(old.keys() & set(SCALED_ONLY_SIZES))
        first = (out / "episodes/2x2_GROUP-g1_static_env0/episode.json").read_bytes()
        for size in ("1x3", "3x3"):
            checked_cli(*args, "--sizes", size)
            current = read_json(out / "run.json")["group_partitions"]
            self.assertEqual(current.keys() - old.keys(), {size})
            self.assertEqual({k: current[k] for k in old}, old)
            old = current
        self.assertEqual((out / "episodes/2x2_GROUP-g1_static_env0/episode.json").read_bytes(), first)


if __name__ == "__main__":
    unittest.main()
