"""Offline parity against Chen BoxNet2, physical route certificates and protocol regressions."""
import ast
from collections import Counter
import copy
import csv
import json
from pathlib import Path
import random
import re
import shutil
import subprocess
import sys
import tempfile
from types import SimpleNamespace
import unittest
from unittest.mock import patch

import numpy as np
import boxnet2 as env
from boxnet2_maps import saved_corner_env
from boxnet2_planning import coordinated_plan, independent_result, min_corner_handovers
from episode import Spec, run_episode
from fake_model import CutReply
from limits import Invocation
from map_events import agent_at, boxes, cell_key, event_path
from map_sets import colour_counts, parse_map_set
from matched_protocol import build_prompt, group_partition
from plan_parse import CORNER_MOVES, PlanParser, cut_reply_prefix
from storage import ROOT, code_version, digest, read_json, source_hashes, source_path, write_json
from test_chen2d import calls

SOURCE = ROOT / "fixtures" / "upstream"  # Chen's BoxNet2 files at the same upstream commit as the BoxNet1 copies
REVIEW = ROOT / "review/chen2d-22/continuation"  # not part of the public copy; see the skip below
A, B, C, D = (agent_at(p) for p in env.cells(2, 2))


def upstream_functions():
    # Compile only pure definitions. Chen's module-level driver deletes and recreates directories.
    tree = ast.parse((SOURCE / "env2_create.py").read_text())
    names = {"corner_position", "judge_move_box2pos_box2target_func", "state_update_func",
             "action_from_response", "env_create"}
    tree.body = [n for n in tree.body if isinstance(n, ast.FunctionDef) and n.name in names]
    scope = dict(np=np, copy=copy, re=re, print=lambda *_: None)
    exec(compile(tree, "Chen/env2_create.py", "exec"), scope)
    return scope


def board(rows=2, cols=2, *, items=None):
    state, _ = env.create_board(rows, cols, {}, random.Random(0))
    for pos, contents in (items or {}).items():
        state[cell_key(tuple(map(float, pos)))] = contents.copy()
    return state


def move(colour, dest):
    return env.move_text("box_" + colour, tuple(map(float, dest)))


class SourceParity(unittest.TestCase):
    def test_random_doable_order_fail_state_and_feedback_match_upstream(self):
        ref = upstream_functions()
        cases = collisions = shared = 0
        for rows in (1, 2, 3):
            for seed in range(32):
                rng = random.Random(seed)
                initial, _ = env.create_board(rows, 3, colour_counts(rows * 3), rng)
                ref_lines = ref["state_update_func"](rows, 3, initial).splitlines()
                expected = {line.split(":")[0]: [a.replace("position(", "position[").replace("))", "])")
                                                 for a in ast.literal_eval(line.split("I can do ")[1])]
                            for line in ref_lines}
                self.assertEqual(env.available_actions(rows, 3, initial), expected)
                for _ in range(6):
                    names = list(expected)
                    rng.shuffle(names)
                    joint = {r: rng.choice(expected[r]) for r in names if expected[r] and rng.randrange(4)}
                    feedback, after, hit = ref["action_from_response"](initial, joint)
                    result = env.execute(initial, joint, "fail")
                    self.assertEqual((result.feedback, result.state, result.failed), (feedback, after, hit))
                    if not hit:
                        self.assertEqual(env.execute(initial, joint).state, after)
                    else:
                        self.assertFalse(env.execute(initial, joint).failed)
                    cases += 1
                    collisions += hit
                    shared += bool(feedback)
        self.assertEqual(cases, 576)
        self.assertGreater(collisions, 100)
        self.assertGreater(shared, 20)

    def test_seeded_placement_source_draw_order_and_redraw_inventory(self):
        source = upstream_functions()
        redraw_cases = 0
        for rows in (1, 2, 3):
            for seed in range(16):
                counts = colour_counts(rows * 3)
                rng = random.Random(seed)
                stream = iter(counts.values())
                source["random"] = SimpleNamespace(
                    randint=lambda lo, hi: next(stream) if lo is None else rng.randint(lo, hi), shuffle=rng.shuffle)
                chen = source["env_create"](rows, 3, None, None, list(counts))
                actual, redraws = env.create_board(rows, 3, counts, random.Random(seed))
                if not redraws:
                    self.assertEqual(actual, chen)
                else:
                    self.assertLess(boxes(chen).total(), rows * 3)
                    redraw_cases += 1
                self.assertEqual(boxes(actual), Counter(counts))
                self.assertEqual(boxes(actual), Counter(v[7:] for items in actual.values()
                                                        for v in items if v.startswith("target_")))
        self.assertEqual(redraw_cases, 10)
        with self.assertRaisesRegex(ValueError, "18 boxes exceed 16"):
            env.create_board(3, 3, colour_counts(18), random.Random(0))
        self.assertEqual(boxes(env.create_board(2, 3, colour_counts(12), random.Random(0))[0]).total(), 12)


class CollisionRules(unittest.TestCase):
    def test_two_arrivals_and_unrelated_delivery(self):
        s = board(items={(0, 0): ["box_red"], (0, 2): ["box_blue"], (2, 0): ["box_green"],
                         (1.5, .5): ["target_green"]})
        plans = {A: move("red", (0, 1)), B: move("blue", (0, 1)), C: "move(box_green, target_green)"}
        before = copy.deepcopy(s)
        for order in (plans, dict(reversed(plans.items()))):
            trial = env.execute(s, order, "skip", step=7)
            self.assertEqual(trial.robots, [C])
            self.assertEqual(boxes(trial.state), Counter(red=1, blue=1))
            self.assertEqual(trial.state["0.0_0.0"], ["box_red"])
            self.assertEqual(trial.state["0.0_2.0"], ["box_blue"])
            for e in trial.collisions:
                self.assertEqual((e["event"], e["step"], e["corner"]), ("collision", 7, (0., 1.)))
                self.assertEqual({m["robot"] for m in e["moves"]}, {A, B})
            self.assertEqual(len(trial.collisions), 2)
            self.assertTrue(env.execute(s, order, "fail").failed)
        self.assertEqual(s, before)

    def test_vacancy_swap_chain_and_stationary_occupant(self):
        s = board(items={(0, 0): ["box_red"], (0, 1): ["box_blue"], (1, 2): ["box_green"]})
        ab = {A: move("red", (0, 1)), B: move("blue", (1, 1))}
        self.assertEqual(env.execute(s, ab).collisions, [])
        self.assertEqual(env.execute(s, dict(reversed(ab.items()))).state, env.execute(s, ab).state)
        chain = env.execute(s, {**ab, D: move("green", (1, 1))}, step=3)
        self.assertEqual(chain.state, s)
        self.assertEqual([(e["robot"], e["pass_number"]) for e in chain.collisions], [(B, 1), (D, 1), (A, 2)])
        self.assertEqual(chain.collisions[-1]["cancelled_departures"][0]["robot"], B)
        blocked = env.execute(s, {A: move("red", (0, 1))})
        self.assertEqual(blocked.collisions[0]["initial_occupants"], ["box_blue"])
        s = board(items={(0, 1): ["box_red"], (1, 1): ["box_blue"]})
        swap = env.execute(s, {A: move("red", (1, 1)), B: move("blue", (0, 1))})
        self.assertEqual((swap.state["0.0_1.0"], swap.state["1.0_1.0"], swap.collisions),
                         (["box_blue"], ["box_red"], []))

    def test_rollback_keeps_the_identity_of_a_surviving_same_colour_move(self):
        s = board(items={(0, 1): ["box_red"], (0, 2): ["box_red"], (1, 0): ["box_blue"]})
        # B sees red at (0,2) after A vacates (0,1). A is then rolled back.
        plan = {A: move("red", (1, 0)), B: move("red", (1, 2))}
        result = env.execute(s, plan)
        self.assertEqual((result.robots, result.state["0.0_1.0"], result.state["0.0_2.0"]),
                         ([B], ["box_red"], []))
        self.assertEqual(result.applied[0][0], (0., 2.))


class MapMeasurements(unittest.TestCase):
    @unittest.skipUnless(REVIEW.is_dir(), "review/chen2d-22/continuation is not part of the public copy")
    def test_all_hashes_controls_routes_and_attained_minimum(self):
        witnesses = read_json(REVIEW / "reference-plans.json")
        with (REVIEW / "map-results.csv").open() as f:
            data = list(csv.DictReader(f))
        self.assertEqual(len(data), 48)
        self.assertEqual(len(witnesses), 48)
        for row in data:
            n, m = map(int, row["size"].split("x"))
            seed = int(row["seed"])
            path, sha, _ = saved_corner_env(n, m, seed, parse_map_set("scaled:1"))
            initial = read_json(path)
            self.assertEqual(sha, row["boxnet2_sha256"])
            self.assertEqual(read_json(event_path(path))["placement_redraws"], int(row["placement_redraws"]))
            saved = witnesses[sha]
            plan, final = coordinated_plan(n, m, initial)
            self.assertFalse(boxes(final))
            self.assertEqual((plan, len(plan)), (saved["coordinated_plan"], int(row["coordinated_steps"])))
            self.assertLessEqual(len(plan), 40)
            self.assertEqual(min_corner_handovers(initial), int(row["min_corner_handovers"]))
            state = initial
            owners = {}
            changes = 0
            for joint in saved["min_handover_witness"]:
                self.assertEqual(env.check_plan(joint, env.available_actions(n, m, state)), ("", {}))
                result = env.execute(state, joint, "fail")
                self.assertFalse(result.failed or result.feedback)
                (src, box, dest), = result.applied
                robot, = joint
                previous = owners.pop(src, robot)
                changes += previous != robot
                if isinstance(dest, tuple):
                    owners[dest] = robot
                state = result.state
            self.assertFalse(owners or boxes(state))
            self.assertEqual(changes, int(row["min_corner_handovers"]))
            self.assertEqual(independent_result(n, m, initial), (bool(int(row["independent_complete"])),
                             int(row["independent_steps"]), int(row["cancelled_moves"])))

    def test_diagonal_shared_corner_and_repeated_colour_assignment(self):
        s = board(3, 3, items={(0, 0): ["box_red"], (3, 3): ["box_red"],
                               (2.5, 2.5): ["target_red"], (1.5, 1.5): ["target_red"]})
        self.assertEqual(min_corner_handovers(s), 1)
        s["2.5_2.5"].append(s["1.5_1.5"].pop())
        self.assertEqual(min_corner_handovers(s), 2)


class WriterIntegration(unittest.TestCase):
    def setUp(self):
        temp = tempfile.TemporaryDirectory(dir=ROOT)
        self.addCleanup(temp.cleanup)
        self.folder = Path(temp.name)

    def play(self, state, replies, framework="CMAS", policy="skip", tag="run"):
        out = self.folder / tag
        out.mkdir()
        path = out / "board.json"
        write_json(path, state)
        sha = digest(path.read_bytes())
        meta = read_json(ROOT / "envs-boxnet2/r1/2x3/env0.event.json")
        write_json(event_path(path), dict(meta, env_sha256=sha, box_count=boxes(state).total()))
        spec = Spec(2, 2, framework, "static", 0, path, sha, digest(event_path(path).read_bytes()),
                    env="boxnet2", collision=policy, dropoff="event", protocol="matched", map_set="scaled:1",
                    boxes_per_robot=1., box_count=boxes(state).total(), horizon=5, plan_note="continue",
                    failed_writer="idle", cut_answer="prefix", max_planning_rounds=1)
        budget = Invocation(out, out / "script.json")
        budget.create(None, 5, "fake")
        with patch("fake_model.reply", side_effect=replies):
            run_episode(spec, out, budget.path, "fake", "correct", 50)
        folder = out / "episodes" / spec.name
        return read_json(folder / "episode.json"), calls(folder), folder

    def test_skip_and_fail_commit_and_record_the_correct_step(self):
        s = board(items={(0, 0): ["box_red"], (0, 2): ["box_blue"], (2, 0): ["box_green"],
                         (1.5, .5): ["target_green"], (.5, .5): ["target_red"], (.5, 1.5): ["target_blue"]})
        joint = {A: move("red", (0, 1)), B: move("blue", (0, 1)), C: "move(box_green, target_green)"}
        deliver = {A: "move(box_red, target_red)", B: "move(box_blue, target_blue)"}
        answer = json.dumps([joint, deliver])
        success, _, folder = self.play(s, [answer])
        self.assertEqual((success["success_failure"], success["steps"], success["correct_deliveries"],
                          success["collision_cancelled_moves"]), ("success", 2, 3, 2))
        self.assertEqual(success["iterations"][0]["issued_plan"], joint)
        self.assertEqual(read_json(folder / "response/response1.json"), {C: joint[C]})
        fail, _, folder = self.play(s, [answer], policy="fail", tag="fail")
        self.assertEqual((fail["success_failure"], fail["steps"], fail["correct_deliveries"],
                          fail["iterations"][0]["executed"]), ("collision", 0, 0, False))
        self.assertEqual(len(fail["iterations"][0]["collisions"]), 2)
        self.assertEqual(list((folder / "pg_state").glob("*")), [folder / "pg_state/pg_state1.json"])

    def test_partial_own_writer_applies_corner_move_next_to_blocked_writer(self):
        s = board(items={(0, 0): ["box_red"], (0, 2): ["box_blue"], (1.5, 1.5): ["target_red", "target_blue"]})
        action = move("red", (1, 1))
        cut = CutReply(json.dumps([action])[:-1] + ', "move(')
        broken = CutReply('["move(')
        row, trace, _ = self.play(s, [cut, broken, broken, broken, "[null]", "[null]"], framework="OWN")
        self.assertEqual((row["steps"], row["round_log"][0]["writer_cut_prefix"][0]["salvaged_steps"],
                          row["round_log"][0]["writer_blocked"][0]["robots"]), (1, 1, [B]))
        self.assertEqual(row["iterations"][0]["issued_plan"], {A: action})
        self.assertIn(json.dumps({A: [action], B: []}), trace[2]["messages"][1]["content"])
        self.assertIsNone(row["tokens_per_delivered_box"])

    def test_all_three_prompts_and_strict_and_prefix_grammars(self):
        s = read_json(ROOT / "envs-boxnet2/r1/3x3/env0.json")
        source = ast.parse((SOURCE / "prompt_env2.py").read_text())
        warning, = [ast.literal_eval(node.value) for node in source.body if isinstance(node, ast.Assign)
                    and any(isinstance(t, ast.Name) and t.id == "collision_avoidance_prompt" for t in node.targets)]
        self.assertEqual(env.COLLISION_RULE, warning)
        texts = []
        common = dict(horizon=5, history_method="authors", history_window=3000, state_position="after",
                      env="boxnet2", plan_note="continue", failed_writer="idle")
        for scope in ({}, {"block": group_partition(3, 3, 3).blocks[0]}, {"robot": (0, 0)}):
            prompt = build_prompt(3, 3, s, [], [s], **common, **scope)
            self.assertEqual(prompt.count(env.COLLISION_RULE), 1)
            self.assertIn("Earlier robots' lists in this planning round: {}", prompt)
            self.assertIn("after they are executed, another planning round continues", prompt)
            texts.append(prompt.split("Write a", 1)[0].split("Write an", 1)[0])
        self.assertEqual(texts, [texts[0]] * 3)
        action = move("blue", (0, 1))
        for own, step in ((True, action), (False, {A: action})):
            reply = json.dumps([step])
            options = dict(own=own, speaker=A, agent_positions={(.5, .5)})
            self.assertEqual(PlanParser("strict", syntax=CORNER_MOVES).sequence(reply, 1, matched_shape=True,
                             **options), [step])
            self.assertIsNone(PlanParser("strict").sequence(reply, 1, matched_shape=True, **options))
            self.assertEqual(cut_reply_prefix(reply[:-1]+",", 5, syntax=CORNER_MOVES, **options), (reply, 1))

    def test_runner_defaults_restart_and_separate_collision_policies(self):
        out = self.folder / "pilot"
        cmd = [sys.executable, "-B", "run_chen2d.py", "--env", "boxnet2", "--model", "fake",
               "--sizes", "1x3", "--frameworks", "CMAS", "--envs", "0", "--out", str(out)]
        subprocess.run([*cmd, "--max-calls", "1"], cwd=ROOT, check=True, capture_output=True)
        config = read_json(out / "run.json")
        self.assertEqual([config[k] for k in ("env", "collision", "map_set", "horizon", "plan_note",
                                              "failed_writer", "cut_answer")],
                         ["boxnet2", "skip", "scaled:1", 5, "continue", "idle", "prefix"])
        subprocess.run(cmd, cwd=ROOT, check=True, capture_output=True)
        row = read_json(next((out / "episodes").glob("*/episode.json")))
        self.assertEqual((row["correct_deliveries"], row["box_count"]), (3, 3))
        mixed = subprocess.run([*cmd, "--collision", "fail"], cwd=ROOT, capture_output=True)
        self.assertNotEqual(mixed.returncode, 0)
        self.assertIn(b"Run settings or protocol source changed", mixed.stderr)

    def test_parameterized_registry_recovers_partial_registration_and_detects_tampering(self):
        selected = parse_map_set("scaled:0.5")
        with patch("boxnet2_maps.ROOT", self.folder):
            path, sha, fields = saved_corner_env(1, 3, 7, selected)
            self.assertEqual(fields["box_count"], 2)
            self.assertEqual(boxes(read_json(path)).total(), 2)
            manifest = path.parent / "manifest.json"
            original = manifest.read_bytes()
            manifest.unlink()
            self.assertEqual(saved_corner_env(1, 3, 7, selected)[1], sha)
            self.assertEqual(manifest.read_bytes(), original)
            path.write_text("{}")
            with self.assertRaisesRegex(ValueError, "Modified BoxNet2 input"):
                saved_corner_env(1, 3, 7, selected)


class LegacyBytes(unittest.TestCase):
    def test_all_default_files_and_summaries_equal_frozen_task21_with_version_included(self):
        # Source snapshot: 6172cbfbac44. The public copy differs only in LLM.py (BOXNET_BRAIN_DIR default), as in upload 1.
        self.assertEqual(code_version(), "79f547d10c06")
        driver = """
from datetime import datetime, timezone
from types import SimpleNamespace
from unittest.mock import patch
import run_chen2d
with (patch('run_chen2d.datetime', SimpleNamespace(now=lambda tz: datetime(2026,11,25,tzinfo=timezone.utc))),
      patch('run_chen2d.uuid.uuid4', return_value=SimpleNamespace(hex='fixed')),
      patch('episode.time', SimpleNamespace(monotonic=lambda: 0.0)),
      patch('LLM.monotonic', return_value=0.0)):
    run_chen2d.main()
"""
        with tempfile.TemporaryDirectory(dir=ROOT) as scratch:
            scratch = Path(scratch)
            legacy = scratch / "original"
            legacy.mkdir()
            for name, sha in source_hashes().items():
                source = source_path(name)
                self.assertEqual(digest(source.read_bytes()), sha)
                shutil.copyfile(source, legacy / name)
            campaigns = [
                ("native", ["--frameworks", "CMAS,HMAS-1,HMAS-2,DMAS,OWN", "--dropoff", "event"]),
                ("matched", ["--protocol", "matched", "--map-set", "scaled:1", "--frameworks", "CMAS,GROUP,OWN",
                             "--group-size", "2", "--horizon", "5", "--failed-writer", "idle", "--cut-answer", "prefix",
                             "--plan-note", "continue", "--fake-script", "cut:[{},"])
            ]
            for name, flags in campaigns:
                outputs, summaries = [], []
                for tree in (legacy, ROOT):
                    out = (legacy if tree == legacy else scratch) / name
                    args = ["--model", "fake", "--conditions", "static", "--sizes", "2x2", "--envs", "0",
                            "--max-env-steps", "2", "--max-calls", "300", "--out", str(out), *flags]
                    subprocess.run([sys.executable, "-B", "-c", driver, *args], cwd=tree, check=True, capture_output=True)
                    recorded = {read_json(p)["framework"] for p in (out / "episodes").glob("*/episode.json")}
                    self.assertEqual(recorded, set(flags[flags.index("--frameworks") + 1].split(",")))
                    outputs.append({p.relative_to(out): digest(p.read_bytes()) for p in out.rglob("*") if p.is_file()})
                    summaries.append([subprocess.check_output([sys.executable, "-B", "summarize.py", *by, str(out)],
                                     cwd=tree) for by in ([], ["--by", "planning"])])
                self.assertEqual(summaries[0], summaries[1])
                self.assertEqual(outputs[0].keys(), outputs[1].keys())
                for file, sha in outputs[0].items():
                    self.assertEqual(sha, outputs[1][file], str(file))
