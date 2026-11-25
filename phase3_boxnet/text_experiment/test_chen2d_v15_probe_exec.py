"""Durability and aggregation regressions for the reading-probe runner only."""
import json
import tempfile
import unittest
from argparse import Namespace
from pathlib import Path
from regression_inputs import REGRESSION
from unittest.mock import patch

from probe_reading import run, summarize
from LLM import MODEL
from limits import OUTPUT_LIMIT
from test_chen2d_v3 import scripted_transport
from test_chen2d_v5 import local_references


HERE = Path(__file__).resolve().parent
SOURCE = REGRESSION / "offline-wrong" / "episodes" / "2x2_CMAS_change_env0"


def args_for(out, *, arms=("none",), calls=1, cost="1", jobs=1, model="fake", max_output_tokens=8192):
    return Namespace(episodes=str(SOURCE), out=str(out.relative_to(HERE)), per_episode=1,
        callers=("leader",), arms=arms, horizon=1, protocol="authors", strip_style=False,
        model=model, fake_script="correct", reasoning="default", max_output_tokens=max_output_tokens,
        max_calls=calls, max_cost_usd=cost, shuffle=None, jobs=jobs)


class ReadingProbeExecutionTests(unittest.TestCase):
    def test_resume_reuses_finished_cell_without_new_result(self):
        with tempfile.TemporaryDirectory(dir=HERE) as raw:
            out = Path(raw) / "out"
            args = args_for(out)
            self.assertEqual(len(run(args)), 1)
            self.assertEqual(run(args), [])
            rows = [json.loads(line) for line in (out / "results.jsonl").read_text().splitlines()]
            self.assertEqual(len(rows), 1)
            self.assertTrue(rows[0]["finished"])
            self.assertTrue((out / "cells" / rows[0]["cell_id"] / "calls" / "00001.json").exists())

    def test_guard_refusal_stays_unasked_then_fresh_guard_can_resume(self):
        with tempfile.TemporaryDirectory(dir=HERE) as raw:
            out = Path(raw) / "out"
            refused = args_for(out, calls=0)
            self.assertEqual(run(refused), [])
            self.assertFalse((out / "results.jsonl").exists())
            # Max calls and jobs are invocation limits, not frozen protocol.
            resumed = args_for(out, calls=1, jobs=2)
            self.assertEqual(len(run(resumed)), 1)
            self.assertEqual(len(list((out / "invocations").glob("*.json"))), 2)

    def test_cost_guard_is_unasked_and_can_resume_under_new_budget(self):
        with tempfile.TemporaryDirectory(dir=HERE) as raw:
            out = Path(raw) / "out"
            self.assertEqual(run(args_for(out, cost="0")), [])
            self.assertFalse((out / "results.jsonl").exists())
            self.assertEqual(len(run(args_for(out, cost="1"))), 1)

    def test_runner_rejects_duplicate_cells_and_unknown_runtime_choices(self):
        with tempfile.TemporaryDirectory(dir=HERE) as raw:
            out = Path(raw) / "out"
            duplicate = args_for(out)
            duplicate.callers = ("leader", "leader")
            with self.assertRaisesRegex(ValueError, "Duplicate"):
                run(duplicate)
            unknown = args_for(out)
            unknown.model = "not-a-model"
            with self.assertRaisesRegex(ValueError, "Unknown probe model"):
                run(unknown)

    def test_one_real_truncated_partial_is_saved_once_with_usage(self):
        with tempfile.TemporaryDirectory(dir=HERE) as raw, local_references(), scripted_transport(["truncated"]) as (sent, _):
            out = Path(raw) / "out"
            rows = run(args_for(out, model=MODEL, max_output_tokens=64))
            self.assertEqual(len(sent), 1)  # max_attempts=1: never pay a retry
            row, = rows
            self.assertEqual((row["stop_label"], row["cut_off"], row["reply"]), (OUTPUT_LIMIT, True, "partial {"))
            self.assertEqual((row["prompt_tokens"], row["generated_tokens"], row["reasoning_tokens"]), (10, 64, 63))
            cell = json.loads((out / "cells" / row["cell_id"] / "result.json").read_text())
            self.assertEqual(cell["attempts"][0]["raw_output"], "partial {")
            summary = summarize(out.relative_to(HERE))
            self.assertEqual(summary["cells"]["legacy/leader/none"]["cut_offs"]["count"], 1)
            # A legacy/provider record without a body, finish evidence or
            # reasoning meter is unknown, never silently counted as no cut-off.
            cell.update(reply=None, cut_off=None, reasoning_tokens=None)
            cell["attempts"][0].pop("raw_output", None)
            cell["attempts"][0].pop("reasoning_tokens", None)
            cell["attempts"][0].pop("cut_off", None)
            (out / "cells" / row["cell_id"] / "result.json").write_text(json.dumps(cell), encoding="utf-8")
            unknown = summarize(out.relative_to(HERE))["cells"]["legacy/leader/none"]
            self.assertEqual((unknown["cut_offs"]["count"], unknown["unknown_cut_offs"]["count"]), (0, 1))

    def test_crash_after_durable_call_replays_without_transport(self):
        with tempfile.TemporaryDirectory(dir=HERE) as raw:
            out = Path(raw) / "out"
            args = args_for(out, model=MODEL, max_output_tokens=64)
            with local_references(), scripted_transport(["ok"]) as (sent, _), patch("probe_reading._write_cell_result", side_effect=RuntimeError("crash")):
                with self.assertRaisesRegex(RuntimeError, "crash"):
                    run(args)
                self.assertEqual(len(sent), 1)
            with local_references(), scripted_transport([]) as (sent, _):
                self.assertEqual(len(run(args)), 1)
                self.assertEqual(sent, [])

    def test_jobs_checkpoint_and_summary_exclude_nonplans_from_pairs(self):
        with tempfile.TemporaryDirectory(dir=HERE) as raw:
            out = Path(raw) / "out"
            self.assertEqual(len(run(args_for(out, arms=("none", "last1"), calls=2, jobs=2))), 2)
            rows = [json.loads(line) for line in (out / "results.jsonl").read_text().splitlines()]
            self.assertEqual(len(json.loads((out / "checkpoint.json").read_text())["completed"]), 2)
            changed = next(row for row in rows if row["arm"] == "last1")
            changed["plan_produced"] = False
            (out / "cells" / changed["cell_id"] / "result.json").write_text(json.dumps(changed), encoding="utf-8")
            (out / "results.jsonl").write_text("".join(json.dumps(row) + "\n" for row in rows), encoding="utf-8")
            pair = summarize(out.relative_to(HERE))["paired"]["legacy/leader/none__last1"]
            self.assertEqual(pair["readable_both"], 0)
            self.assertEqual(pair["missing_or_nonplan"]["nonplan_b"]["count"], 1)

    def test_mixed_map_sets_never_pool_summary_cells_or_pairs(self):
        with tempfile.TemporaryDirectory(dir=HERE) as raw:
            out = Path(raw) / "out"
            run(args_for(out, arms=("none", "last1"), calls=2))
            planned = json.loads((out / "planned-cells.json").read_text())
            rows = [json.loads(line) for line in (out / "results.jsonl").read_text().splitlines()]
            changed = next(row for row in rows if row["arm"] == "last1")
            changed["map_set"] = "scaled:1"
            next(item for item in planned if item["cell_id"] == changed["cell_id"])["map_set"] = "scaled:1"
            (out / "cells" / changed["cell_id"] / "result.json").write_text(json.dumps(changed), encoding="utf-8")
            (out / "planned-cells.json").write_text(json.dumps(planned), encoding="utf-8")
            report = summarize(out.relative_to(HERE))
            self.assertEqual(report["cells"]["legacy/leader/none"]["states_asked"], 1)
            self.assertEqual(report["cells"]["scaled:1/leader/last1"]["states_asked"], 1)
            self.assertEqual(report["paired"]["legacy/leader/none__last1"]["expected_states"], 1)
            self.assertEqual(report["paired"]["scaled:1/leader/none__last1"]["expected_states"], 1)


if __name__ == "__main__":
    unittest.main()
