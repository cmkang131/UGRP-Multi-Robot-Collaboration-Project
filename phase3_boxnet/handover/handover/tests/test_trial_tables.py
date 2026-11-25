import csv
import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest
from unittest.mock import patch

from handover import layout, run_trial, score


class TrialTables(unittest.TestCase):
    def test_swap_changes_only_colour_in_all_twelve_source_rows(self):
        swapped = layout.TABLE.with_name("trials-swapped.csv")
        with layout.TABLE.open(newline="") as original, swapped.open(newline="") as other:
            source, paired = csv.DictReader(original), csv.DictReader(other)
            self.assertEqual(source.fieldnames, paired.fieldnames)
            rows = list(source)
            self.assertEqual([int(r["trial"]) for r in rows], list(range(1, 13)))
            self.assertEqual(list(paired), [dict(r, colour={"red": "blue", "blue": "red"}[r["colour"]])
                                            for r in rows])
        # The byte comparison also covers quoting, whitespace, ordering and line endings.
        expected = layout.TABLE.read_bytes().replace(b",red,", b",SWAP,").replace(b",blue,", b",red,")
        self.assertEqual(expected.replace(b",SWAP,", b",blue,"), swapped.read_bytes())

    def test_driver_loads_selected_table_and_preserves_default_definition(self):
        for table, args, colour in (("trials.csv", [], "red"),
                                    ("trials-swapped.csv", ["--trial-table", "trials-swapped.csv"], "blue")):
            with patch.object(run_trial, "run", return_value=0) as run:
                self.assertEqual(run_trial.main(["--trial", "1", "--out", "new", *args]), 0)
            trial, path, budget = run.call_args.args
            self.assertEqual(run.call_args.kwargs, {"station_tilt": "strict"})
            self.assertEqual((trial, path, budget), (layout.trials(table)[1], Path("new"), 1080))
            self.assertEqual(trial["colour"], colour)
            if args:
                self.assertEqual(trial["trial_table"], table)
            else:
                self.assertNotIn("trial_table", trial)

    def test_mixed_tables_cannot_make_a_gate(self):
        rows = [dict(trial=k, status="SUCCESS", evaluated=True) for k in range(1, 13)]
        rows[-1]["trial_table"] = "trials-swapped.csv"
        self.assertEqual(score.aggregate(rows), (0, "INVALID (mixed trial tables)"))

    def test_archived_scores_match_the_frozen_fix5_cli_byte_for_byte(self):
        root = run_trial.BASE
        runs = Path("cloudrun/runs")
        old = runs / "handover-fix5-swap-yimHXMgy/build/context/handover/score.py"
        if not (root / old).is_file():
            self.skipTest("requires the archived FIX5 scorer and trial records")
        for cohort, count in (("handover-20261125a", 1), ("handover-fix3-20261125c", 12),
                              ("handover-fix4-Zc6HAKV9", 12), ("handover-fix5-swap-yimHXMgy", 12)):
            with self.subTest(cohort=cohort):
                paths = sorted(p.relative_to(root) for p in (root / runs / cohort / "trials").glob("trial-*"))
                self.assertEqual(len(paths), count)
                previous, current = (subprocess.run([sys.executable, "-B", cli, *paths], cwd=root, capture_output=True)
                                     for cli in (old, Path("handover/score.py")))
                self.assertIn(b" evaluated ", previous.stdout)
                self.assertEqual((current.returncode, current.stdout, current.stderr),
                                 (previous.returncode, previous.stdout, previous.stderr))

    def test_real_driver_records_the_swapped_row_before_runtime_setup(self):
        with tempfile.TemporaryDirectory() as tmp:
            out = Path(tmp) / "trial-01"
            env = dict(os.environ, HANDOVER_ACT_MODEL=str(Path(tmp) / "absent-model"),
                       HANDOVER_SCENE_ROOT=str(Path(tmp) / "absent-scene"))
            p = subprocess.run([sys.executable, "-B", run_trial.__file__, "--trial", "1", "--out", str(out),
                                "--trial-table", "trials-swapped.csv", "--station-tilt", "ignore"],
                               env=env, capture_output=True)
            self.assertEqual(p.returncode, 2)
            self.assertEqual(json.loads((out / "trial.json").read_bytes()), layout.trials("trials-swapped.csv")[1])
            run = json.loads((out / "run.json").read_bytes())
            self.assertEqual(run["station_tilt"], "ignore")
            self.assertEqual((run["status"], run["stage"]), ("error", "setup"))
            self.assertIn("missing local runtime inputs", run["reason"])
