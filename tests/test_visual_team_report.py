import json
from pathlib import Path

from scripts.render_visual_team_report import render, summarize_run
from scripts.replay_gemini_team import _is_recorded_stop
from scripts.evaluate_gemini_cohort import run_cohort


def _write(path: Path, value) -> None:
    path.write_text(json.dumps(value, ensure_ascii=False))


def _run(root: Path, name: str, *, mode: str, success: bool, messages: list[dict]) -> Path:
    run = root / name
    run.mkdir()
    _write(run / "result.json", {"seed": 41, "active_robots": ["r1"], "success": success,
        "outcomes": {"r1": {"success": success, "reason": "ok", "gates": {}}},
        "elapsed_sim_s": 3.0, "communication": mode, "messages": len(messages),
        "llm_calls": {"r1": 2}, "controller": "gemini", "model": "gemini-test"})
    (run / "control.jsonl").write_text("")
    (run / "llm-decisions.jsonl").write_text(json.dumps({"event": "llm_result", "robot_id": "r1",
        "disposition": "accepted", "wall_latency_ms": 250,
        "decision": {"action": {"kind": "wait", "duration": .2}, "reason": "내부 판단"}}, ensure_ascii=False) + "\n")
    (run / "messages.jsonl").write_text("".join(json.dumps(row, ensure_ascii=False) + "\n" for row in messages))
    return run


def test_report_renders_actual_transcript_seek_private_reason_and_mode_aggregate(tmp_path):
    message = {"message_id": "msg-1", "sender": "r1", "sent_at": 1.25, "observed_at": 1.0,
               "decision_id": "d1", "mode": "status",
               "content": {"observed": "앞에 장애물", "intent": "wait", "request": "clear_path"}}
    _run(tmp_path, "status-41", mode="status", success=True, messages=[message])
    (tmp_path / "supplement.html").write_text("<aside>보충 자료 유지</aside>")
    output = tmp_path / "index.html"
    summary = render(tmp_path, output)
    page = output.read_text()
    assert "통신 모드 <strong>status</strong>" in page
    assert "seekVideo('video-status-41',1.250000)" in page
    assert "R1" not in page  # sender is preserved, not cosmetically rewritten
    assert "<strong>r1</strong> 방송" in page
    assert "비공개 Gemini 판단 이유:" in page and "내부 판단" in page
    assert "앞에 장애물 / 의도 wait / 요청 clear_path" in page
    assert "보충 자료 유지" in page
    assert summary["communication_modes"]["status"]["successful_runs"] == 1
    assert summary["communication_modes"]["status"]["successful_robot_deliveries"] == 1
    assert summary["communication_modes"]["status"]["llm_calls"] == 2
    assert summary["communication_modes"]["status"]["broadcasts"] == 1
    assert summary["communication_modes"]["status"]["wall_latency_ms"] == [250.0]


def test_legacy_zero_message_run_still_renders(tmp_path):
    run = _run(tmp_path, "old-41", mode="none", success=False, messages=[])
    (run / "messages.jsonl").unlink()
    summary = render(tmp_path, tmp_path / "index.html")
    assert summarize_run(run)["message_rows"] == []
    assert "기록된 실제 방송 메시지 0건" in (tmp_path / "index.html").read_text()
    assert summary["communication_modes"]["none"]["broadcasts"] == 0


def test_replay_treats_logged_raw_wait_as_recorded_stop_for_deduplication():
    assert _is_recorded_stop({"event": "raw_action", "raw_action": {"kind": "wait"}})
    assert _is_recorded_stop({"event": "explicit_stop"})
    assert not _is_recorded_stop({"event": "raw_action", "raw_action": {"kind": "drive"}})


def test_manifest_mode_and_blocked_not_started_lifecycle_are_preserved(tmp_path):
    _write(tmp_path / "cohort-manifest.json", {"runs": [
        {"path": "team-41-status", "seed": 41, "communication": "status"},
        {"path": "team-41-natural", "seed": 41, "communication": "natural"}]})
    _write(tmp_path / "cohort-status.json", {"status": "infrastructure_blocked",
        "started_runs": ["team-41-status"]})
    started = tmp_path / "team-41-status"
    started.mkdir()
    (started / "control.jsonl").write_text("")
    summary = render(tmp_path, tmp_path / "index.html")
    by_name = {run["name"]: run for group in summary["groups"].values() for run in group}
    assert by_name["team-41-status"]["communication_mode"] == "status"
    assert by_name["team-41-status"]["lifecycle"] == "running"
    assert by_name["team-41-natural"]["communication_mode"] == "natural"
    assert by_name["team-41-natural"]["lifecycle"] == "not_attempted"
    assert by_name["team-41-natural"]["success"] is None
    assert summary["communication_modes"]["natural"]["completed_runs"] == 0
    assert summary["communication_modes"]["natural"]["not_attempted_runs"] == 1
    page = (tmp_path / "index.html").read_text()
    assert "통신 모드 <strong>natural</strong>" in page
    assert "미시작" in page
    assert "0/0" in page


def test_started_crash_without_artifacts_remains_in_attempt_denominator(tmp_path):
    runs = [{"path": f"team-{seed}-none", "seed": seed, "communication": "none"}
            for seed in (41, 42, 43)]
    _write(tmp_path / "cohort-manifest.json", {"runs": runs})

    def execute(run):
        if run["seed"] == 41:
            _run(tmp_path, run["path"], mode="none", success=True, messages=[])
            return 0
        return 2  # Child exits before it creates a result or trace directory.

    state = run_cohort(tmp_path, runs, jobs=1, execute=execute)
    summary = render(tmp_path, tmp_path / "index.html")
    by_name = {run["name"]: run for group in summary["groups"].values() for run in group}
    crashed = by_name["team-42-none"]
    mode = summary["communication_modes"]["none"]
    assert len(state["attempted"]) == summary["attempted_runs"] == mode["attempted_runs"] == 2
    assert crashed["attempted"] and crashed["terminal"]
    assert crashed["lifecycle"] == "operational_failure"
    assert crashed["operational_failure"] == "PROCESS_EXIT_2"
    assert crashed["success"] is None and not crashed["complete"]
    assert by_name["team-43-none"]["lifecycle"] == "not_attempted"
    assert mode["successful_runs"] == mode["operational_failed_runs"] == mode["not_attempted_runs"] == 1
    assert summary["finished_runs"] == 2 and summary["unfinished_runs"] == 1
    page = (tmp_path / "index.html").read_text()
    assert "<tr><td>none</td><td>1/2</td><td>1/1</td><td>1</td><td>1</td>" in page
    assert "성공 / 전체 시도" in page and "기록 성공 / 물리판정 기록" in page
    assert "운영 실패" in page


def test_started_only_without_exit_does_not_invent_terminal_failure(tmp_path):
    _write(tmp_path / "cohort-manifest.json", {"runs": [
        {"path": "team-41-none", "seed": 41, "communication": "none"}]})
    _write(tmp_path / "cohort-status.json", {"status": "running", "started_runs": ["team-41-none"]})
    summary = render(tmp_path, tmp_path / "index.html")
    run = summary["groups"]["team3"][0]
    assert run["lifecycle"] == "running" and run["attempted"]
    assert not run["terminal"] and run["success"] is None
    assert summary["operational_failed_runs"] == summary["finished_runs"] == 0


def test_operational_failure_preserves_raw_success_but_does_not_count_it(tmp_path):
    name = "team-41-none"
    _run(tmp_path, name, mode="none", success=True, messages=[])
    _write(tmp_path / "cohort-manifest.json", {"runs": [
        {"path": name, "seed": 41, "communication": "none"}]})
    _write(tmp_path / "cohort-status.json", {"status": "infrastructure_blocked",
        "started_runs": [name], "attempted": [{"path": name, "returncode": 2,
                                               "infrastructure_problem": "PROCESS_EXIT_2"}]})
    summary = render(tmp_path, tmp_path / "index.html")
    mode = summary["communication_modes"]["none"]
    assert summary["groups"]["solo1"][0]["success"] is True
    assert mode["recorded_successful_runs"] == mode["completed_runs"] == 1
    assert mode["successful_runs"] == 0 and mode["operational_failed_runs"] == 1


def test_truncated_result_is_terminal_operational_failure_with_unknown_physics(tmp_path):
    runs = [{"path": "team-41-none", "seed": 41, "communication": "none"}]
    _write(tmp_path / "cohort-manifest.json", {"runs": runs})

    def execute(run):
        folder = tmp_path / run["path"]
        folder.mkdir()
        (folder / "result.json").write_text('{"success":')
        return 0

    run_cohort(tmp_path, runs, jobs=1, execute=execute)
    summary = render(tmp_path, tmp_path / "index.html")
    run = summary["groups"]["team3"][0]
    assert run["lifecycle"] == "operational_failure" and run["terminal"]
    assert run["operational_failure"] == "INVALID_RESULT" and run["success"] is None
    assert summary["attempted_runs"] == summary["finished_runs"] == 1
    assert summary["results_available"] == summary["successful_runs"] == 0


def test_non_utf8_result_keeps_failure_ledger_and_report_available(tmp_path):
    runs = [{"path": f"team-{seed}-none", "seed": seed, "communication": "none"}
            for seed in (41, 42)]
    _write(tmp_path / "cohort-manifest.json", {"runs": runs})
    corrupt = b"\xff\xfe\x00"

    def execute(run):
        folder = tmp_path / run["path"]
        folder.mkdir()
        (folder / "result.json").write_bytes(corrupt)
        return 0

    state = run_cohort(tmp_path, runs, jobs=1, execute=execute)
    summary = render(tmp_path, tmp_path / "index.html")
    by_name = {run["name"]: run for group in summary["groups"].values() for run in group}
    assert state["blocking_reason"] == "INVALID_RESULT"
    assert len(state["attempted"]) == summary["attempted_runs"] == 1
    assert state["not_started"] == runs[1:]
    assert by_name["team-41-none"]["operational_failure"] == "INVALID_RESULT"
    assert by_name["team-41-none"]["success"] is None
    assert by_name["team-42-none"]["lifecycle"] == "not_attempted"
    assert summary["operational_failed_runs"] == summary["finished_runs"] == 1
    assert summary["results_available"] == summary["successful_runs"] == 0
    assert (tmp_path / "index.html").is_file()
    assert (tmp_path / "team-41-none" / "result.json").read_bytes() == corrupt
