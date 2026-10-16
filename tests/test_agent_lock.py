import json
import os

import pytest

from scripts import agent_lock


def _acquire(root, owner='claude', pid=None):
    return agent_lock.acquire(root, owner=owner, branch='claude/x', purpose='realtime A/B',
                              pid=os.getpid() if pid is None else pid, expected_minutes=20)


def test_second_agent_cannot_acquire_a_held_lock(tmp_path):
    _acquire(tmp_path)
    held = agent_lock.status(tmp_path)
    assert held['owner'] == 'claude' and held['pid_alive'] is True
    assert held['timing_sensitive'] is False
    with pytest.raises(RuntimeError, match='lock held'):
        _acquire(tmp_path, owner='codex')


def test_only_owner_releases_and_release_is_recorded(tmp_path):
    _acquire(tmp_path)
    with pytest.raises(RuntimeError, match='only the owner'):
        agent_lock.release(tmp_path, owner='codex')
    agent_lock.release(tmp_path, owner='claude')
    assert agent_lock.status(tmp_path) is None
    row = json.loads((tmp_path / 'released.jsonl').read_text().splitlines()[-1])
    assert row['released_by'] == 'claude' and row['stale_release'] is False


def test_stale_release_requires_dead_pid(tmp_path):
    _acquire(tmp_path, pid=os.getpid())
    with pytest.raises(RuntimeError):
        agent_lock.release(tmp_path, owner='codex', stale=True)
    agent_lock.release(tmp_path, owner='claude')
    _acquire(tmp_path, pid=2 ** 22 + 12345)
    assert agent_lock.status(tmp_path)['pid_alive'] is False
    agent_lock.release(tmp_path, owner='codex', stale=True)
    assert agent_lock.status(tmp_path) is None


def test_cli_status_acquire_release(tmp_path, capsys):
    assert agent_lock.main(['--root', str(tmp_path), 'status']) == 0
    assert agent_lock.main(['--root', str(tmp_path), 'acquire', '--owner', 'codex', '--branch', 'b',
                            '--purpose', 'p', '--pid', str(os.getpid()), '--expected-minutes', '5']) == 0
    assert agent_lock.main(['--root', str(tmp_path), 'acquire', '--owner', 'claude', '--branch', 'b',
                            '--purpose', 'p', '--pid', str(os.getpid()), '--expected-minutes', '5']) == 1
    assert agent_lock.main(['--root', str(tmp_path), 'release', '--owner', 'codex']) == 0


def test_timing_sensitive_cli_flag_is_persisted_and_reported(tmp_path, capsys):
    assert agent_lock.main(['--root', str(tmp_path), 'acquire', '--owner', 'codex', '--branch', 'b',
                           '--purpose', 'wall timing', '--pid', str(os.getpid()),
                           '--expected-minutes', '5', '--timing-sensitive']) == 0
    assert json.loads(capsys.readouterr().out)['timing_sensitive'] is True
    assert json.loads((tmp_path / 'physics/owner.json').read_text())['timing_sensitive'] is True
    assert agent_lock.main(['--root', str(tmp_path), 'status']) == 0
    assert json.loads(capsys.readouterr().out)['timing_sensitive'] is True
    agent_lock.release(tmp_path, owner='codex')


def test_legacy_lock_defaults_to_not_timing_sensitive_without_rewriting(tmp_path):
    _acquire(tmp_path)
    path = tmp_path / 'physics/owner.json'
    record = json.loads(path.read_text())
    record.pop('timing_sensitive')
    path.write_text(json.dumps(record))
    before = path.read_bytes()
    assert agent_lock.status(tmp_path)['timing_sensitive'] is False
    assert path.read_bytes() == before
