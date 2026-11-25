"""Offline runner checks for physical ceilings and the number of writers in a round."""
import io
import sys
from concurrent.futures import ThreadPoolExecutor
from contextlib import redirect_stdout
from dataclasses import replace
from pathlib import Path
from unittest.mock import patch

import run_chen2d
from LLM import MODEL, load_real_api
from episode import run_episode
from limits import CALL_LIMIT, Invocation
from planning_metrics import MATCHED_CALL_CAP, MATCHED_ROUND_CAP
from storage import digest, ROOT, read_json
from test_chen2d import calls, fixture_spec
from test_chen2d_v3 import scripted_transport
from test_chen2d_v4 import cli
from test_chen2d_v5 import PINNED_CLIENT_SHA256, local_references
from test_chen2d_v11 import HorizonFixtures


class RoundVolumeTests(HorizonFixtures):
    def test_full_round_with_zero_or_all_repairs_for_each_team_size(self):
        for cols in (4, 8):
            robots = 4 * cols
            board = {f"{i + .5}_{j + .5}": [] for i in range(4) for j in range(cols)}
            board["0.5_0.5"] = ["box_red", "target_red"]
            base = fixture_spec(self.work / f"board{cols}.json", board, "static", rows=4, cols=cols)
            for framework, group, writers in (("CMAS", None, 1), ("GROUP", 4, robots // 4),
                                              ("GROUP", 8, robots // 8), ("OWN", None, robots)):
                spec = replace(base, framework=framework, group_size=group, protocol="matched",
                               horizon=5, max_planning_rounds=1)
                for script, repairs in (("correct", 0), ("non-json", 2)):
                    with self.subTest(robots=robots, framework=framework, group=group, script=script):
                        out = self.work / f"{robots}-{framework}-{group}-{script}"
                        out.mkdir()
                        budget = Invocation(out, out / "script.json")
                        budget.create(None, 1, "fake")
                        run_episode(spec, out, budget.path, "fake", script, 300)
                        directory = out / "episodes" / spec.name
                        batch, = read_json(directory / "episode.json")["round_log"]
                        trace = calls(directory)
                        self.assertEqual(len({c["speaker"] for c in trace}), writers)
                        self.assertEqual(batch["repair_calls"], writers * repairs)
                        self.assertEqual(len(trace), writers * (1 + repairs))
                        self.assertEqual(len(trace), read_json(budget.path)["calls"])
                        self.assertEqual(set(batch["repair_calls_by_writer"].values()), {2} if repairs else set())


class RunnerCeilingTests(HorizonFixtures):
    def test_warning_precedes_dispatch_and_only_the_effective_episode_cap_earns_its_label(self):
        # The archived client and replaced HTTPS connection are the same ones used in the historical suite.
        with local_references():
            api = load_real_api()
            self.assertEqual(digest(Path(api.__file__).read_bytes()), PINNED_CLIENT_SHA256)
            self.assertEqual(api.HARD_EPISODE_CALLS, 600)
            for hard, framework, extra, expected, n in (
                    (600, "CMAS", [], MATCHED_ROUND_CAP, 1),
                    (2, "OWN", [], MATCHED_CALL_CAP, 2),
                    (600, "OWN", ["--max-calls", "1"], CALL_LIMIT, 1)):
                with self.subTest(hard=hard, framework=framework, expected=expected):
                    out = self.work / expected
                    argv = ["run_chen2d.py", "--model", MODEL, "--out", str(out), "--protocol", "matched",
                            "--frameworks", framework, "--conditions", "static", "--envs", "0",
                            "--max-planning-rounds", "1", "--episode-call-ceiling", "900", *extra]
                    console = io.StringIO()
                    with (scripted_transport(["idle"] * 4) as (sent, _), patch.object(sys, "argv", argv),
                          patch.object(run_chen2d, "ProcessPoolExecutor", ThreadPoolExecutor),
                          patch.object(run_chen2d, "BRAIN", Path(api.__file__).parent),
                          patch.object(api, "HARD_EPISODE_CALLS", hard), redirect_stdout(console)):
                        run_chen2d.main()
                    warning = console.getvalue().splitlines()[0]
                    self.assertIn("--episode-call-ceiling 900", warning)
                    self.assertIn(f"hard cap of {hard}", warning)
                    self.assertIn(f"effective episode ceiling is {hard}", warning)
                    cfg = read_json(out / "run.json")
                    row = read_json(next((out / "episodes").iterdir()) / "episode.json")
                    self.assertEqual((cfg["max_reply_attempts_per_call"], cfg["max_transport_errors_per_call"],
                                      cfg["max_attempts_per_call"], cfg["transport_retry_total_s"]), (3, 3, 5, 60))
                    self.assertEqual((cfg["episode_call_ceiling"], cfg["hard_episode_calls"],
                                      cfg["effective_episode_call_ceiling"], row["episode_call_ceiling"]),
                                     (900, hard, hard, hard))
                    self.assertEqual((row["success_failure"], row["call_ceiling"], row["api_calls"], len(sent)),
                                     (expected, expected == MATCHED_CALL_CAP, n, n))

    def test_fake_has_no_real_client_ceiling(self):
        out = self.work / "fake-run"
        proc = cli("run_chen2d.py", "--model", "fake", "--protocol", "matched", "--frameworks", "CMAS",
                   "--conditions", "static", "--envs", "0", "--episode-call-ceiling", "900", "--out", out)
        self.assertEqual(proc.returncode, 0, proc.stderr)
        self.assertNotIn("exceeds", proc.stdout)
        self.assertEqual(read_json(out / "run.json")["effective_episode_call_ceiling"], 900)
        row = read_json(next((out / "episodes").iterdir()) / "episode.json")
        self.assertEqual(row["episode_call_ceiling"], 900)
