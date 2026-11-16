"""CPU-only synthetic aggregation probes against unmodified repository code."""
from __future__ import annotations

import json
from pathlib import Path
import re
import sys
import tempfile

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))

from scripts.evaluate_gemini_cohort import run_cohort
from scripts.render_visual_team_report import render
from scripts.carry_failure_metrics import aggregate, schedule


def result_json(path, data):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data), encoding="utf-8")


def crash_denominator():
    with tempfile.TemporaryDirectory() as folder:
        root = Path(folder)
        runs = [{"path": f"team-{seed}-none", "seed": seed, "communication": "none"}
                for seed in (41, 42, 43)]
        result_json(root / "cohort-manifest.json", {"runs": runs})

        def execute(run):
            if run["seed"] == 41:
                result_json(root / run["path"] / "result.json", {
                    "seed": 41, "active_robots": ["r1", "r2", "r3"],
                    "communication": "none", "success": True,
                    "outcomes": {"r1": {"success": True, "reason": "OK"}}
                })
                return 0
            return 2  # A real subprocess can exit before producing result/trace.

        state = run_cohort(root, runs, jobs=1, execute=execute)
        summary = render(root, root / "report.html")
        by_name = {row["name"]: row for group in summary["groups"].values() for row in group}
        return {
            "scheduler_attempted": len(state["attempted"]),
            "scheduler_blocking_reason": state["blocking_reason"],
            "report_attempted": summary["communication_modes"]["none"]["attempted_runs"],
            "crash_lifecycle": by_name["team-42-none"]["lifecycle"],
            "crash_report_attempted": by_name["team-42-none"]["attempted"],
            "not_started_lifecycle": by_name["team-43-none"]["lifecycle"],
            "rendered_mode_row": re.search(r"<tr><td>none</td>.*?</tr>",
                                           (root / "report.html").read_text()).group(0),
            "expected": {"attempted": 2, "successful": 1, "operational_failed": 1,
                         "not_started": 1, "all_attempt_success": "1/2"},
        }


def malformed_result():
    with tempfile.TemporaryDirectory() as folder:
        root = Path(folder)
        runs = [{"path": "team-41-none"}, {"path": "team-42-none"}]

        def execute(run):
            p = root / run["path"]
            p.mkdir()
            (p / "result.json").write_text('{"success":')
            return 0

        try:
            state = run_cohort(root, runs, jobs=1, execute=execute)
            status = {"returned_state": state["status"]}
        except Exception as error:
            status = {"raised": type(error).__name__, "message": str(error)}
        return {**status, "cohort_status_written": (root / "cohort-status.json").exists(),
                "expected": "Retain attempted row as invalid result and stop remaining scheduling."}


def row_identity():
    jobs = schedule({"test": [{"id": "open"}]}, ["teacher", "act"])
    failure = {"whole_success": False, "robot_result_available": False,
               "failure_kind": "missing_or_invalid_result", "carry_entered": None,
               "act_carry_entered": None, "beam_success": None}
    rows = [{**job, "condition": "act", "outcome": failure} for job in jobs]
    try:
        summary = aggregate(jobs, rows)
    except ValueError as error:
        return {"rejected": True, "error": str(error),
                "expected": "Reject a result whose condition conflicts with the scheduled trial_id."}
    return {"complete": summary["complete"],
            "conditions": {k: {f: v[f] for f in ("planned", "attempted", "pending", "failures")}
                           for k, v in summary["conditions"].items()},
            "expected": "Reject a result whose condition conflicts with the scheduled trial_id."}


if __name__ == "__main__":
    print(json.dumps({"crash_denominator": crash_denominator(),
                      "malformed_result": malformed_result(),
                      "row_identity": row_identity()}, indent=2))
