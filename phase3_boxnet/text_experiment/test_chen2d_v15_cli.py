"""Public runner and report boundaries for the matched and scaled treatments."""
import csv
import json
import tempfile
import unittest
from pathlib import Path

from matched_protocol import build_prompt
from planning_metrics import matched_cell_metrics
from storage import ROOT, read_json
from test_chen2d_v4 import cli


class MatchedCliTests(unittest.TestCase):
    def test_scaled_legacy_and_matched_cells_reconcile_to_physical_calls(self):
        with tempfile.TemporaryDirectory(dir=ROOT) as scratch:
            root = Path(scratch)
            base = ("--model", "fake", "--frameworks", "CMAS,OWN", "--conditions", "static",
                    "--dropoff", "event", "--envs", "0", "--horizon", "5", "--state-position", "after")
            outs = []
            for treatment in ("legacy", "scaled:2"):
                out = root / treatment.replace(":", "-")
                outs.append(out)
                run = cli("run_chen2d.py", *base, "--protocol", "matched", "--map-set", treatment, "--out", out)
                self.assertEqual(run.returncode, 0, run.stderr)
                cfg = read_json(out / "run.json")
                self.assertEqual((cfg["max_env_steps"], cfg["max_planning_rounds"], cfg["effective_episode_call_ceiling"]),
                                 (30, 30, 300))
                with (out / "episodes.csv").open() as stream:
                    records = list(csv.DictReader(stream))
                for r in records:
                    ep = out / "episodes" / r["episode_id"]
                    episode = read_json(ep / "episode.json")
                    attempts = [a for c in (ep / "calls").glob("[0-9]*.json") for a in read_json(c)["attempts"]]
                    self.assertEqual((r["map_set"], r["strict_success"], int(r["rounds_no_cutoff"])),
                                     (treatment, "True", episode["planning_rounds"]))
                    self.assertEqual(len(attempts), episode["api_calls"])
                    self.assertEqual(sum(a["completion_tokens"] for a in attempts), episode["completion_tokens"])
                    self.assertEqual(episode["map_set"], treatment)
                    if treatment == "scaled:2":
                        self.assertEqual((episode["boxes_per_robot"], episode["box_count"]), (2, 8))
            table = cli("summarize.py", "--by", "planning", *outs)
            self.assertEqual(table.returncode, 0, table.stderr)
            matched = table.stdout.split("Matched protocol, all physical attempts per strict completion\n")[1]
            header, *lines = matched.strip().splitlines()
            rows = [dict(zip(header.split(" | "), line.split(" | "), strict=True)) for line in lines]
            self.assertEqual({(r["map_set"], r["framework"]) for r in rows},
                             {(design, f) for design in ("legacy", "scaled:2") for f in ("CMAS", "OWN")})
            self.assertTrue(all(float(r["calls_per_strict_completion"]) == int(r["total_calls"]) for r in rows))

    def test_cost_per_completion_counts_unfinished_and_retry_attempts(self):
        def episode(done, calls, tokens):
            return dict(finished=done, strict_success=done, success_failure="success" if done else "model service",
                        first_blocked_cause=None if done else "model service", api_calls=calls,
                        prompt_tokens=tokens, completion_tokens=tokens // 2, rounds_no_cutoff=0,
                        rounds_cutoff_recovered=1, rounds_all_attempts_cutoff=0, rounds_cutoff_unknown=0)
        a, b = episode(True, 2, 100), episode(False, 3, 50)
        stats = matched_cell_metrics([a, b])
        self.assertEqual((stats["calls_per_strict_completion"], stats["prompt_tokens_per_strict_completion"],
                          stats["generated_tokens_per_strict_completion"]), (5., 150., 75.))
        self.assertEqual(matched_cell_metrics([b])["calls_per_strict_completion"], "no completion")
        self.assertIsNone(matched_cell_metrics([a, dict(b, prompt_tokens=None)])["prompt_tokens_per_strict_completion"])

    def test_matched_reading_window_and_method_select_the_same_history_for_every_reader(self):
        board = {"0.5_0.5": ["box_blue"], "0.5_1.5": ["target_blue"]}
        states = [board] * 6
        responses = [json.dumps({"Agent[0.5, 0.5]": f"source step {i}"}) for i in range(5)]
        for method, w in (("authors", 0), ("none", 10000), ("authors", 75), ("dialogue", 75), ("authors", 10000)):
            histories = set()
            for pos in ("before", "after"):
                for robot in (None, (0, 1)):
                    prompt = build_prompt(1, 2, board, responses, states, horizon=5, history_method=method,
                                          history_window=w, state_position=pos, robot=robot,
                                          earlier={"Agent[0.5, 0.5]": ["x"] * 5})
                    histories.add(tuple(s for s in prompt.splitlines() if s.startswith(("State", "Action"))))
            self.assertEqual(len(histories), 1)
            count = len(histories.pop()) // 2
            if w == 75:
                self.assertTrue(0 < count < 5)
            else:
                self.assertEqual(count, 5 if method == "authors" and w else 0)
