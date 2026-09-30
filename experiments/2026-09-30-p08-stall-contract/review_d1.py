"""Read pinned #293 source from Git; synthetic NumPy counterexamples only.

Run under scripts.run_ci_tests.run_locked, from the assigned worktree.
Print JSON; caller saves it in a new primary outputs directory. Does not fetch,
load raw imagery, tune a threshold, or import the reference into harness.
"""
import ast
import hashlib
import json
import subprocess
import sys
import types

import numpy as np

SHA = "d86cc82eedbe0c6693eaf808c54ce43387723f1d"
BASE = "experiments/2026-09-30-stall-detector-d1/"


def module(name):
    source = subprocess.check_output(["git", "show", f"{SHA}:{BASE}{name}.py"])
    tree = ast.parse(source)
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            assert {alias.name for alias in node.names} <= {"numpy"}
        elif isinstance(node, ast.ImportFrom):
            assert node.module in {"__future__", "dataclasses", "typing"}
    result = types.ModuleType("p08_review_" + name)
    sys.modules[result.__name__] = result
    exec(compile(source, f"git:{SHA}:{BASE}{name}.py", "exec"), result.__dict__)
    return result, hashlib.sha256(source).hexdigest()


def main():
    d1, detector_hash = module("d1_detector")
    evaluation, evaluation_hash = module("d1_evaluation")
    command = d1.CommandInterval(0., 6., "own-c1")
    times = np.arange(0., 6., .1)
    dark = np.full((480, 640), 30, dtype=np.uint8)
    bright = np.full((480, 640), 200, dtype=np.uint8)
    cases = {}
    for name, frames, ts, cmd, expected in (
        ("constant_start_block_proxy", [dark] * len(times), times, command, "INSUFFICIENT_SIGNAL"),
        ("invalid_roi", [bright] * len(times), times, command, "INSUFFICIENT_REFERENCE"),
        ("no_frames", [], [], command, "INSUFFICIENT_REFERENCE"),
        ("short_command", [dark] * len(times), times, d1.CommandInterval(0., 4.), "UNSUPPORTED_SHORT_COMMAND"),
    ):
        result = d1.detect(frames, ts, [cmd])[0]
        assert result.status == expected and not result.alarm_times_s
        cases[name] = dict(status=result.status, checks=len(result.checks), alarms=list(result.alarm_times_s),
                           valid_fraction=result.valid_check_fraction)
        if name == "short_command":
            try:
                evaluation.score_interval(result, [])
            except ValueError as error:
                cases[name]["evaluation_error"] = str(error)
            else:
                raise AssertionError("short-grid counterexample disappeared; re-review upstream")
    for name, ts in (("duplicate_time", [0., 0.]), ("reversed_time", [1., 0.]),
                     ("nonfinite_time", [0., float("nan")])):
        try:
            d1.detect([dark, dark], ts, [command])
        except ValueError as error:
            cases[name] = dict(status="RAISES_NO_INTERVAL_RESULT", error=str(error))
        else:
            raise AssertionError("timestamp rejection changed; re-review upstream")
    # A timestamp gap remains on the full grid; no interpolation or omission.
    result = d1.detect([dark, dark], [0., 5.9], [command])[0]
    assert len(result.checks) == 25 and all(c.state == "MISSING_FRAME" for c in result.checks)
    cases["gap"] = dict(status=result.status, checks=len(result.checks), missing=25)
    cases["blocked_at_start_cap"] = dict(detected=24, denominator=30, sensitivity=24 / 30,
                                         required_sensitivity=.9, pass_gate=False)
    assert evaluation.stall_cohort_status(list(evaluation.STALL_KINDS) * 6) == "COMPLETE"
    assert evaluation.stall_cohort_status(list(evaluation.STALL_KINDS[:-1]) * 6) == "INCOMPLETE"
    print(json.dumps(dict(review_sha=SHA, detector_sha256=detector_hash, evaluation_sha256=evaluation_hash,
                          cases=cases, physics_sim_s=0, renderer_calls=0, model_calls=0,
                          note="synthetic arithmetic, not D1 sensitivity or physical stop evidence"), indent=2))


if __name__ == "__main__":
    main()
