"""Offline tests are unlocked by default; host serialization is opt-in."""
import json
import os
from pathlib import Path
import signal
import subprocess
import sys
import time
from types import SimpleNamespace

import pytest

from scripts import agent_lock, run_ci_tests as runner


@pytest.fixture(autouse=True)
def clear_host_lock_env(monkeypatch):
    monkeypatch.delenv("UGRP_TEST_HOST_LOCK", raising=False)


@pytest.mark.parametrize("lock_kind", ["absent", "ordinary", "timing", "legacy"])
def test_default_runs_pytest_without_modifying_host_lock(tmp_path, monkeypatch, capsys, lock_kind):
    root = tmp_path / "locks"
    owner_path = root / "physics/owner.json"
    if lock_kind != "absent":
        agent_lock.acquire(root, owner="claude", branch="claude/physics", purpose="cohort",
                           pid=os.getpid(), expected_minutes=1, timing_sensitive=lock_kind == "timing")
        if lock_kind == "legacy":
            record = json.loads(owner_path.read_text())
            record.pop("timing_sensitive")
            owner_path.write_text(json.dumps(record))
    before = owner_path.read_bytes() if owner_path.exists() else None
    marker = tmp_path / "pytest-ran"
    test_file = tmp_path / "test_offline.py"
    test_file.write_text(f"from pathlib import Path\ndef test_runs():\n    Path({str(marker)!r}).touch()\n")
    monkeypatch.setattr(runner, "ROOT", tmp_path)
    monkeypatch.setattr(runner, "TEST_PATTERNS", ("test_offline.py",))
    monkeypatch.setattr(runner, "check_fixtures", lambda _: True)
    monkeypatch.setattr(runner, "local_lock_root", lambda: root)

    def forbidden(*args, **kwargs):
        pytest.fail("default offline tests must not acquire or release the host lock")

    monkeypatch.setattr(agent_lock, "acquire", forbidden)
    monkeypatch.setattr(agent_lock, "release", forbidden)
    assert runner.main([]) == 0
    assert marker.exists()
    assert ("Warning: timing-sensitive host lock" in capsys.readouterr().err) == (lock_kind == "timing")
    assert (owner_path.read_bytes() if owner_path.exists() else None) == before
    assert not (root / "released.jsonl").exists()
    if lock_kind == "absent":
        assert not root.exists()


@pytest.mark.parametrize("argv,env_value,expected", [
    ([], None, 7), ([], "0", 7), ([], "1", 3), (["--host-lock"], None, 3), (["--host-lock"], "0", 3),
])
def test_cli_and_environment_opt_in_restore_busy_refusal(tmp_path, monkeypatch, argv, env_value, expected):
    root = tmp_path / "locks"
    held = agent_lock.acquire(root, owner="claude", branch="claude/physics", purpose="cohort",
                              pid=os.getpid(), expected_minutes=1)
    if env_value is not None:
        monkeypatch.setenv("UGRP_TEST_HOST_LOCK", env_value)
    monkeypatch.setattr(runner, "check_fixtures", lambda _: True)
    monkeypatch.setattr(runner, "local_lock_root", lambda: root)
    calls = []

    def execute(command, **kwargs):
        calls.append(command)
        return 7

    monkeypatch.setattr(subprocess, "call", execute)
    assert runner.main(argv) == expected
    assert bool(calls) == (expected == 7)
    assert agent_lock.status(root)["acquired_unix"] == held["acquired_unix"]


@pytest.mark.parametrize("error", [FileNotFoundError("released during read"), ValueError("partial JSON")])
def test_advisory_lock_read_failure_does_not_block_tests(tmp_path, monkeypatch, capsys, error):
    monkeypatch.setattr(runner, "check_fixtures", lambda _: True)
    monkeypatch.setattr(runner, "local_lock_root", lambda: tmp_path)

    def read_status(_):
        raise error

    monkeypatch.setattr(agent_lock, "status", read_status)
    monkeypatch.setattr(subprocess, "call", lambda *a, **k: 7)
    assert runner.main([]) == 7
    assert "Warning: cannot read host lock" in capsys.readouterr().err


def test_listing_ignores_host_lock_opt_in(monkeypatch, capsys):
    monkeypatch.setenv("UGRP_TEST_HOST_LOCK", "1")

    def forbidden():
        pytest.fail("listing must not inspect or acquire host locks")

    monkeypatch.setattr(runner, "local_lock_root", forbidden)
    assert runner.main(["--host-lock", "--shard-count", "8", "--list-shards"]) == 0
    assert json.loads(capsys.readouterr().out)["coverage_verified"] is True


def test_linked_worktrees_share_primary_lock_but_other_clones_do_not(tmp_path, monkeypatch):
    primary = tmp_path / "primary"
    linked = tmp_path / "linked"
    other = tmp_path / "other"
    subprocess.run(["git", "init", "-q", str(primary)], check=True)
    subprocess.run(["git", "-c", "user.name=Test", "-c", "user.email=test@example.invalid",
                    "commit", "--allow-empty", "-qm", "init"], cwd=primary, check=True)
    subprocess.run(["git", "worktree", "add", "-qb", "linked", str(linked)], cwd=primary, check=True)
    subprocess.run(["git", "init", "-q", str(other)], check=True)
    monkeypatch.setenv("CI", "true")  # Local callers must not bypass the lock this way.
    for checkout in (primary, linked):
        monkeypatch.setattr(runner, "ROOT", checkout)
        assert runner.local_lock_root(primary) == primary / "outputs/agent-locks"
    monkeypatch.setattr(runner, "ROOT", other)
    assert runner.local_lock_root(primary) is None
    assert not (other / "outputs").exists()


def test_missing_local_primary_never_invokes_git_or_creates_mac_path(tmp_path, monkeypatch):
    def unexpected(*args, **kwargs):
        pytest.fail("Git should not run without a local primary")
    monkeypatch.setattr(subprocess, "check_output", unexpected)
    assert runner.local_lock_root(tmp_path / "absent") is None
    assert not (tmp_path / "absent").exists()


def test_held_lock_refuses_before_any_test_process_starts(tmp_path):
    root = tmp_path / "locks"
    held = agent_lock.acquire(root, owner="claude", branch="claude/physics", purpose="timing",
                              pid=os.getpid(), expected_minutes=1)
    marker = tmp_path / "must-not-exist"
    code = f"from pathlib import Path; Path({str(marker)!r}).touch()"
    assert runner.run_locked([sys.executable, "-c", code], dict(os.environ), root) == 3
    assert not marker.exists()
    assert agent_lock.status(root)["acquired_unix"] == held["acquired_unix"]
    agent_lock.release(root, owner="claude")


@pytest.mark.parametrize("exit_code", [0, 7])
def test_child_observes_live_lock_and_normal_exit_releases_it(tmp_path, exit_code):
    root = tmp_path / "locks"
    receipt = tmp_path / "receipt.json"
    code = (f"from pathlib import Path; import json,os; "
            f"p=Path({str(root / 'physics/owner.json')!r}); "
            f"r=json.loads(p.read_text()); os.kill(r['pid'], 0); "
            f"Path({str(receipt)!r}).write_text(json.dumps(r)); raise SystemExit({exit_code})")
    assert runner.run_locked([sys.executable, "-c", code], dict(os.environ), root) == exit_code
    record = json.loads(receipt.read_text())
    assert record["pid"] == os.getpid()
    assert record["timing_sensitive"] is True
    assert agent_lock.status(root) is None
    assert len((root / "released.jsonl").read_text().splitlines()) == 1


@pytest.mark.parametrize("exit_code", [0, 7])
@pytest.mark.parametrize("disappears", [True, False], ids=["delayed", "never-confirmed"])
def test_group_cleanup_waits_for_confirmation(tmp_path, monkeypatch, exit_code, disappears):
    """Deterministically reproduce delayed group teardown after leader wait()."""
    from scripts import ugrp_session
    root = tmp_path / "locks"
    now, probes = [0.0], []
    monkeypatch.setattr(ugrp_session, "stop_group", lambda *a, **k: None)

    def alive(pgid):
        assert agent_lock.status(root) is not None
        probes.append(pgid)
        return not disappears or len(probes) < 3

    def sleep(delay):
        assert agent_lock.status(root) is not None
        now[0] += delay

    monkeypatch.setattr(ugrp_session, "process_group_alive", alive)
    monkeypatch.setattr(runner, "time", SimpleNamespace(monotonic=lambda: now[0], sleep=sleep))
    command = [sys.executable, "-c", f"raise SystemExit({exit_code})"]
    if disappears:
        assert runner.run_locked(command, dict(os.environ), root) == exit_code
        assert len(probes) == 3
        assert agent_lock.status(root) is None
        assert len((root / "released.jsonl").read_text().splitlines()) == 1
    else:
        with pytest.raises(RuntimeError, match="cleanup unconfirmed"):
            runner.run_locked(command, dict(os.environ), root)
        held = agent_lock.status(root)
        assert held is not None
        assert not (root / "released.jsonl").exists()
        agent_lock.release(root, owner=held["owner"])
    assert len(set(probes)) == 1


def test_spawn_failure_releases_only_unused_lock(tmp_path):
    root = tmp_path / "locks"
    with pytest.raises(FileNotFoundError):
        runner.run_locked([str(tmp_path / "not-an-executable")], dict(os.environ), root)
    assert agent_lock.status(root) is None


def test_uncertain_cleanup_retains_reservation(tmp_path, monkeypatch):
    from scripts import ugrp_session
    root = tmp_path / "locks"
    monkeypatch.setattr(ugrp_session, "stop_group", lambda *a, **k: None)
    monkeypatch.setattr(ugrp_session, "process_group_alive", lambda _pgid: True)
    with pytest.raises(RuntimeError, match="cleanup unconfirmed"):
        runner.run_locked([sys.executable, "-c", "pass"], dict(os.environ), root)
    held = agent_lock.status(root)
    assert held is not None and held["pid"] == os.getpid()
    assert not (root / "released.jsonl").exists()
    agent_lock.release(root, owner=held["owner"])


def test_signal_waits_for_owned_child_before_unlocking(tmp_path):
    root = tmp_path / "locks"
    ready = tmp_path / "ready"
    child_code = (f"from pathlib import Path; import os,time; "
                  f"Path({str(ready)!r}).write_text(str(os.getpid())); time.sleep(60)")
    driver_code = ("from scripts.run_ci_tests import run_locked; from pathlib import Path; import os; "
                   f"raise SystemExit(run_locked({[sys.executable, '-c', child_code]!r}, "
                   f"dict(os.environ), Path({str(root)!r})))")
    child_pid = None
    driver = subprocess.Popen([sys.executable, "-c", driver_code], cwd=runner.ROOT,
                              start_new_session=True)
    try:
        deadline = time.monotonic() + 10
        while not ready.exists() and driver.poll() is None and time.monotonic() < deadline:
            time.sleep(0.02)
        assert ready.exists(), "owned child did not start"
        child_pid = int(ready.read_text())
        assert agent_lock.status(root)["pid"] == driver.pid
        driver.send_signal(signal.SIGTERM)
        assert driver.wait(timeout=10) == 143
        assert agent_lock.status(root) is None
        with pytest.raises(ProcessLookupError):
            os.kill(child_pid, 0)
    finally:
        if driver.poll() is None:
            driver.kill()
            driver.wait(timeout=5)
        if child_pid is not None:
            try:
                os.killpg(child_pid, signal.SIGKILL)
            except ProcessLookupError:
                pass
