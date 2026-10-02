"""V91 non-exclusive slot admission, including both sides of timing exclusion."""
from concurrent.futures import ThreadPoolExecutor
import json
import os
import threading

import pytest

from scripts import agent_lock as lock


def slot(root, name='sim-one', branch='codex/one'):
    return lock.acquire_sim_slot(root, slot=name, owner='codex', branch=branch,
        purpose='SIM only', pid=os.getpid(), expected_minutes=2)


def physics(root, timing=True):
    return lock.acquire(root, owner='claude', branch='claude/physics', purpose='timing',
                        pid=os.getpid(), expected_minutes=2, timing_sensitive=timing)


def test_different_branches_coexist_with_non_timing_legacy_holder(tmp_path):
    physics(tmp_path, False)
    old = (tmp_path/'physics/owner.json').read_bytes()
    slot(tmp_path)
    slot(tmp_path, 'sim-two', 'codex/two')
    report = lock.require_sim_slot(tmp_path, slot='sim-one', owner='codex', branch='codex/one')
    assert [r['name'] for r in report['concurrent_holders']] == ['sim-one', 'sim-two']
    assert len(report['loadavg']) == 3
    assert report['physics_holder']['owner'] == 'claude'
    lock.release(tmp_path, owner='codex', name='sim-one')
    assert (tmp_path/'physics/owner.json').read_bytes() == old
    assert lock.status(tmp_path, 'sim-two')['pid_alive']


def test_opposing_timing_sensitive_acquisitions_refuse_in_both_orders(tmp_path):
    physics(tmp_path)
    with pytest.raises(RuntimeError, match='timing-sensitive'):
        slot(tmp_path)
    lock.release(tmp_path, owner='claude')
    slot(tmp_path)
    with pytest.raises(RuntimeError, match='SIM slots held'):
        physics(tmp_path)
    assert lock.status(tmp_path) is None


def test_public_named_acquire_cannot_bypass_timing_exclusion(tmp_path):
    physics(tmp_path)
    with pytest.raises(RuntimeError, match='timing-sensitive'):
        lock.acquire(tmp_path, name='sim-public', owner='codex', branch='codex/one',
                     purpose='SIM', pid=os.getpid(), expected_minutes=1)


def test_preview_snapshot_does_not_create_lock_root(tmp_path):
    root = tmp_path/'absent'
    assert lock.sim_snapshot(root)['concurrent_holders'] == []
    assert not root.exists()


def test_concurrent_admissions_cannot_both_succeed(tmp_path):
    barrier = threading.Barrier(2)
    def attempt(fn):
        barrier.wait()
        try:
            fn(tmp_path)
            return True
        except RuntimeError:
            return False
    with ThreadPoolExecutor(2) as pool:
        futures = [pool.submit(attempt, fn) for fn in (physics, slot)]
        assert sum(f.result() for f in futures) == 1


@pytest.mark.parametrize('mismatch', ['owner', 'branch', 'dead', 'missing', 'exclusive'])
def test_runner_refuses_nonowned_dead_or_opposing_lock(tmp_path, mismatch, monkeypatch):
    slot(tmp_path)
    owner, branch, name = 'codex', 'codex/one', 'sim-one'
    if mismatch == 'owner': owner = 'claude'
    if mismatch == 'branch': branch = 'codex/two'
    if mismatch == 'dead': monkeypatch.setattr(lock, '_alive', lambda _: False)
    if mismatch == 'missing': name = 'sim-missing'
    if mismatch == 'exclusive':
        # Simulate an older tool which does not know about SIM slots.
        lock._acquire(tmp_path, owner='claude', branch='claude/old', purpose='old tool',
                      pid=os.getpid(), expected_minutes=2, timing_sensitive=True)
    with pytest.raises((ValueError, RuntimeError)):
        lock.require_sim_slot(tmp_path, slot=name, owner=owner, branch=branch)


def test_incomplete_physics_lock_fails_closed(tmp_path):
    (tmp_path/'physics').mkdir()
    with pytest.raises(RuntimeError):
        slot(tmp_path)


@pytest.mark.parametrize('name', ['physics', '../physics', 'sim-../x', '/tmp/sim-x', 'sim-'])
def test_slot_names_cannot_escape_root(tmp_path, name):
    with pytest.raises(RuntimeError, match='safe name'):
        slot(tmp_path, name)


def test_slot_cli_and_old_cli_status_are_separate(tmp_path, capsys):
    prefix = ['--root', str(tmp_path)]
    assert lock.main(prefix+['acquire', '--owner', 'codex', '--branch', 'codex/one',
        '--purpose', 'SIM only', '--pid', str(os.getpid()), '--expected-minutes', '2',
        '--sim-slot', 'sim-one']) == 0
    capsys.readouterr()
    assert lock.main(prefix+['status']) == 0
    assert json.loads(capsys.readouterr().out) is None
    assert lock.main(prefix+['status', '--sim-slots']) == 0
    assert len(json.loads(capsys.readouterr().out)['concurrent_holders']) == 1
    assert lock.main(prefix+['status', '--sim-slot', 'sim-one']) == 0
    assert json.loads(capsys.readouterr().out)['branch'] == 'codex/one'
    assert lock.main(prefix+['release', '--owner', 'codex', '--sim-slot', 'sim-one']) == 0
    assert lock.sim_holders(tmp_path) == []


def test_stale_slot_requires_explicit_release_and_cannot_hide_live_pid(tmp_path, monkeypatch):
    slot(tmp_path)
    with pytest.raises(RuntimeError):
        lock.release(tmp_path, owner='claude', name='sim-one', stale=True)
    monkeypatch.setattr(lock, '_alive', lambda _: False)
    with pytest.raises(RuntimeError):
        physics(tmp_path)
    lock.release(tmp_path, owner='claude', name='sim-one', stale=True)
    physics(tmp_path)
