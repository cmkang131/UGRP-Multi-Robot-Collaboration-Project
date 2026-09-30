"""File sharding must preserve every offline module and reject partial coverage."""

import ast
from collections import Counter
import json
from pathlib import Path
import re
import subprocess
import textwrap

import pytest

from scripts import run_ci_tests as runner


def forbid_execution(monkeypatch):
    def forbidden(*args, **kwargs):
        pytest.fail("listing/invalid input must not acquire a lock or spawn pytest")

    monkeypatch.setattr(runner, "local_lock_root", forbidden)
    monkeypatch.setattr(runner.subprocess, "call", forbidden)
    monkeypatch.setattr(runner, "run_locked", forbidden)


@pytest.mark.parametrize("count", [1, 2, 3, 8, 17])
def test_file_count_balance_is_deterministic_and_complete(count):
    files = [f"tests/test_{i:02d}.py" for i in range(13)]
    shards = runner.shard_test_files(files, count)
    assert shards == runner.shard_test_files(list(reversed(files)), count)
    assert shards == [files[index::count] for index in range(count)]
    assert Counter(path for shard in shards for path in shard) == Counter(files)
    assert max(map(len, shards)) - min(map(len, shards)) <= 1


def test_recorded_durations_spread_expensive_files_and_break_ties_stably():
    files = ["a.py", "b.py", "c.py", "d.py"]
    durations = {"a.py": 8, "b.py": 7, "c.py": 6, "d.py": 5}
    shards = runner.shard_test_files(files, 2, durations)
    assert shards == [["a.py", "d.py"], ["b.py", "c.py"]]
    assert [sum(durations[path] for path in shard) for shard in shards] == [13, 13]
    assert runner.shard_test_files(files[::-1], 2, dict(reversed(list(durations.items())))) == shards


def test_new_files_use_median_cost_and_stale_durations_do_not_change_balance():
    assert runner.shard_test_files(["a", "b", "c"], 2, {"a": 10, "b": 2, "retired": 999}) == [
        ["a"], ["b", "c"],
    ]
    assert runner.shard_test_files(["a", "b", "c"], 2, {"retired": 999}) == [["a", "c"], ["b"]]
    assert runner.shard_test_files(["a", "b", "c"], 2, {"a": 0, "b": 0}) == [["a", "c"], ["b"]]


@pytest.mark.parametrize("count", [0, -1, True, 1.5])
def test_invalid_counts_fail(count):
    with pytest.raises(ValueError, match="positive integer"):
        runner.shard_test_files(["a"], count)


@pytest.mark.parametrize("durations", [[], {"a": -1}, {"a": float("nan")},
                                        {"a": float("inf")}, {"a": "2"}, {"a": True}, {1: 2}])
def test_invalid_duration_data_fails(durations):
    with pytest.raises(ValueError, match="finite nonnegative"):
        runner.shard_test_files(["a"], 2, durations)


@pytest.mark.parametrize("files,shards,reason", [
    (["a", "b"], [["a"], []], "missing="),
    (["a", "b"], [["a", "b"], ["a"]], "duplicates="),
    (["a", "b"], [["a", "a", "b"]], "duplicates="),
    (["a", "b"], [["a"], ["b", "c"]], "unexpected="),
    (["a", "a"], [["a"], ["a"]], "duplicate_input="),
])
def test_union_check_rejects_gaps_duplicates_and_extra_files(files, shards, reason):
    with pytest.raises(ValueError, match=reason):
        runner.validate_shards(files, shards)


def test_union_check_accepts_order_independent_exact_coverage_and_empty_shards():
    runner.validate_shards(["a", "b", "c"], [["c", "a"], [], ["b"]])
    with pytest.raises(ValueError, match="duplicate_input"):
        runner.shard_test_files(["a", "a"], 2)


def test_collection_retains_original_glob_expansion_and_deduplication(tmp_path):
    for name in ("test_a.py", "test_b.py", "helper.py"):
        (tmp_path / name).touch()
    assert runner.collect_test_files(tmp_path, ("test_*.py", "test_a.py")) == ["test_a.py", "test_b.py"]


def test_dry_run_covers_actual_ci_list_without_lock_or_pytest(monkeypatch, capsys):
    forbid_execution(monkeypatch)
    assert runner.main(["--shard-count", "8", "--list-shards"]) == 0
    listing = json.loads(capsys.readouterr().out)
    original = sorted({str(path.relative_to(runner.ROOT))
                       for pattern in runner.TEST_PATTERNS for path in runner.ROOT.glob(pattern)})
    assert listing["coverage_verified"] is True
    assert listing["balance"] == "file_count"
    assert listing["shard_count"] == 8
    assert listing["total_files"] == len(original)
    assert Counter(path for shard in listing["shards"] for path in shard) == Counter(original)


def test_cli_uses_recorded_durations(tmp_path, monkeypatch, capsys):
    forbid_execution(monkeypatch)
    monkeypatch.setattr(runner, "collect_test_files", lambda *_: ["a", "b", "c", "d"])
    costs = tmp_path / "durations.json"
    costs.write_text(json.dumps({"a": 8, "b": 7, "c": 6, "d": 5}))
    assert runner.main(["--shard-count", "2", "--durations-json", str(costs), "--list-shards"]) == 0
    listing = json.loads(capsys.readouterr().out)
    assert listing["balance"] == "durations"
    assert listing["shards"] == [["a", "d"], ["b", "c"]]


@pytest.mark.parametrize("argv", [
    ["--shard-count", "0", "--list-shards"], ["--shard-count", "-1"],
    ["--shard-count", "2"], ["--shard-count", "2", "--shard-index", "2"],
    ["--shard-index", "-1"], ["--shard-index", "bad"],
])
def test_invalid_cli_selection_fails_before_execution(argv, monkeypatch):
    forbid_execution(monkeypatch)
    with pytest.raises(SystemExit) as error:
        runner.main(argv)
    assert error.value.code == 2


@pytest.mark.parametrize("contents", [None, "not-json", "null", "[]", '{"a": -1}'])
def test_invalid_duration_file_fails_before_execution(contents, tmp_path, monkeypatch):
    forbid_execution(monkeypatch)
    path = tmp_path / "durations.json"
    if contents is not None:
        path.write_text(contents)
    with pytest.raises(SystemExit) as error:
        runner.main(["--durations-json", str(path), "--list-shards"])
    assert error.value.code == 2


def test_invalid_partition_cannot_reach_pytest(monkeypatch):
    forbid_execution(monkeypatch)
    monkeypatch.setattr(runner, "collect_test_files", lambda *_: ["a", "a"])
    with pytest.raises(SystemExit) as error:
        runner.main([])
    assert error.value.code == 2


@pytest.mark.parametrize("files,argv", [([], []), (["a"], ["--shard-count", "2", "--shard-index", "1"])])
def test_empty_selection_never_falls_back_to_collecting_entire_repo(files, argv, monkeypatch):
    forbid_execution(monkeypatch)
    monkeypatch.setattr(runner, "collect_test_files", lambda *_: files)
    assert runner.main(argv) == 2


@pytest.mark.parametrize("locked", [False, True])
@pytest.mark.parametrize("index", [None, 0, 1, 2])
def test_execution_forwards_only_selected_files_and_preserves_failure_code(index, locked, monkeypatch):
    files = [f"tests/test_{i}.py" for i in range(7)]
    monkeypatch.setattr(runner, "collect_test_files", lambda *_: files)
    lock = Path("fixture-lock") if locked else None
    monkeypatch.setattr(runner, "local_lock_root", lambda: lock)
    calls = []

    def execute(command, *, cwd, env):
        calls.append(command)
        assert cwd == runner.ROOT
        assert env["CI"] == "true"
        return 7

    def execute_locked(command, env, lock_root):
        assert lock_root == lock
        return execute(command, cwd=runner.ROOT, env=env)

    monkeypatch.setattr(runner.subprocess, "call", execute)
    monkeypatch.setattr(runner, "run_locked", execute_locked)
    argv = [] if index is None else ["--shard-count", "3", "--shard-index", str(index)]
    assert runner.main([*argv, "--host-lock", "--junitxml", "report.xml"]) == 7
    selected = files if index is None else runner.shard_test_files(files, 3)[index]
    assert calls == [[runner.sys.executable, "-m", "pytest", "-q", *selected,
                      "--junitxml=report.xml", "-o", "junit_family=legacy"]]


def test_workflow_matrix_executes_every_planned_shard_exactly_once():
    workflow = (runner.ROOT / ".github/workflows/tests.yml").read_text()
    job = workflow.split("  offline-regression-shards:\n", 1)[1].split("\n  offline-regression-checks:", 1)[0]
    indices = ast.literal_eval(re.search(r"^        shard: (\[.*\])$", job, re.MULTILINE).group(1))
    counts = {int(value) for value in re.findall(r"--shard-count (\d+)", workflow)}
    assert len(counts) == 1, "execution and coverage listing must use the same shard count"
    assert indices == list(range(counts.pop()))
    assert "      fail-fast: false\n" in job
    assert "continue-on-error" not in job


@pytest.mark.parametrize("shards", ["success", "failure", "cancelled", "skipped"])
@pytest.mark.parametrize("checks", ["success", "failure", "cancelled", "skipped"])
def test_required_status_gate_rejects_every_non_success_result(shards, checks):
    workflow = (runner.ROOT / ".github/workflows/tests.yml").read_text()
    gate = workflow.split("  offline-regressions:\n", 1)[1].split("\n  ubuntu-simulation-runtime:", 1)[0]
    assert "    name: offline-regressions\n" in gate
    assert "    needs: [ci-preflight, offline-regression-shards, offline-regression-checks]\n" in gate
    assert "    if: ${{ always() }}\n" in gate
    script = textwrap.dedent(gate.split("        run: |\n", 1)[1])
    result = subprocess.run(["sh", "-eu", "-c", script],
                            env={"PREFLIGHT_RESULT": "success", "FULL_SUITE": "true",
                                 "SHARDS_RESULT": shards, "CHECKS_RESULT": checks})
    assert (result.returncode == 0) == (shards == checks == "success")
