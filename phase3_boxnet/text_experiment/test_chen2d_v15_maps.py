"""Offline P0 coverage for isolated scaled Chen map registries."""
import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

import map_sets
from env1_create import action_from_response
from map_events import boxes, reference_trajectory
from map_sets import (boxes_for_team, colour_counts, parse_map_set, saved_map_env,
                      saved_scaled_env, scaled_env_create)
from enrol_maps import speech_event
from analysis_runs import paired_maps
from scaled_map_measurements import measurements
from storage import ROOT


class ScaledMapTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory(dir=ROOT, prefix=".chen15-maps-")
        self.root = Path(self.tmp.name)

    def tearDown(self):
        self.tmp.cleanup()

    def test_parser_rounding_and_balanced_colours(self):
        self.assertEqual(parse_map_set().map_set, "legacy")
        selected = parse_map_set("scaled:1.00")
        self.assertEqual((selected.map_set, selected.registry_name), ("scaled:1", "envs-scaled/r1"))
        self.assertEqual(boxes_for_team(2, 2, "0.5"), 2)
        self.assertEqual(boxes_for_team(2, 2, "0.625"), 2)  # Python round: 2.5 ties to even.
        self.assertEqual(boxes_for_team(1, 1, "0.5"), 1)
        self.assertEqual(colour_counts(8), {"blue": 2, "red": 2, "green": 2, "purple": 1, "orange": 1})
        for value in ("scaled:0", "scaled:-1", "scaled:NaN", "main"):
            with self.assertRaises(ValueError):
                parse_map_set(value)

    def test_determinism_and_legacy_byte_identity(self):
        one = scaled_env_create(4, 8, parse_map_set("scaled:2").boxes_per_robot, rng=__import__("random").Random(7))
        two = scaled_env_create(4, 8, parse_map_set("scaled:2").boxes_per_robot, rng=__import__("random").Random(7))
        self.assertEqual(one, two)
        legacy = Path(__file__).resolve().parent / "envs/2x2/env0.json"
        before = legacy.read_bytes()
        path, _, metadata = saved_map_env(2, 2, 0, "legacy")
        self.assertEqual((path, path.read_bytes(), metadata["map_set"]), (legacy, before, "legacy"))

    def test_registry_is_separate_and_every_scaled_map_is_script_solvable(self):
        with patch.object(map_sets, "ROOT", self.root):
            selected = parse_map_set("scaled:2")
            path, _, metadata = saved_scaled_env(4, 8, 11, selected)
            self.assertEqual(path.relative_to(self.root).parts[:2], ("envs-scaled", "r2"))
            state = json.loads(path.read_text())
            self.assertEqual(boxes(state).total(), 64)
            final = state
            for final, _ in reference_trajectory(state, action_from_response):
                pass
            self.assertEqual(boxes(final).total(), 0)
            self.assertEqual(metadata, {"map_set": "scaled:2", "boxes_per_robot": 2.0, "box_count": 64})
            self.assertFalse((self.root / "envs").exists())
            with self.assertRaises(ValueError):
                path.write_text("{}")
                saved_scaled_env(4, 8, 11, selected)

    def test_one_box_rate_enrols_events_and_cli_readback_without_legacy_relabel(self):
        with patch.object(map_sets, "ROOT", self.root):
            selected = parse_map_set("scaled:0.125")  # round(.5) is zero, then the required minimum is one.
            path, _, metadata = saved_scaled_env(2, 2, 0, selected)
            self.assertEqual(metadata["box_count"], 1)
            event = json.loads(path.with_suffix(".event.json").read_text())
            self.assertEqual((event["map_set"], event["box_count"]), ("scaled:0.125", 1))
            companion = speech_event(path, 2, 2, 0)
            self.assertEqual(json.loads(companion.read_text())["map_set"], "scaled:0.125")
            # Loading the same selector is a registry readback, not regeneration.
            again, _, readback = saved_map_env(2, 2, 0, "scaled:0.125")
            self.assertEqual((again, readback["box_count"]), (path, 1))

    def test_measurement_grid_is_288_horizon_rows_and_has_headroom(self):
        with patch.object(map_sets, "ROOT", self.root):
            rows = measurements(("0.5", "1", "2"), ("2x2", "2x4", "4x4", "4x8"), range(12))
        self.assertEqual(len(rows), 288)
        self.assertEqual({row["horizon"] for row in rows}, {1, 5})
        self.assertTrue(all(row["box_count"] == boxes_for_team(row["rows"], row["cols"], row["boxes_per_robot"])
                            for row in rows))
        self.assertTrue(all(row["within_legacy_step_limit"] and row["within_max_env_steps_30"] for row in rows))

    def test_auxiliary_pairing_never_pools_legacy_and_scaled_maps(self):
        assigned = {}
        observed = {}
        for map_set, sha in (("legacy", "legacy-hash"), ("scaled:1", "scaled-hash")):
            for framework in ("CMAS", "OWN"):
                name = f"{map_set}-{framework}"
                assigned[name] = dict(map_set=map_set, size="2x2", condition="static", tell=None,
                                      env_seed=0, framework=framework, speech="authors", env_sha256=sha,
                                      event_sha256=sha + "-event")
                observed[name] = dict(finished=True, strict_success=True)
        groups = paired_maps(assigned, observed, "framework", ("CMAS", "OWN"))
        self.assertEqual(len(groups), 2)
        self.assertEqual({group[0][3] for group in groups}, {"legacy", "scaled:1"})


if __name__ == "__main__":
    unittest.main()
