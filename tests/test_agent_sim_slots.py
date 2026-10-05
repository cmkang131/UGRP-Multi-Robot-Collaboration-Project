"""V91 same-owner coordinator admission, including frozen legacy lock exclusion."""
from concurrent.futures import ThreadPoolExecutor
import json
import os
from pathlib import Path
import threading

import pytest

from scripts import agent_sim_slots as lock
from scripts import agent_lock as legacy


def slot(root, name='sim-one', branch='codex/one'):
    return lock.acquire_sim_slot(root, slot=name, owner='codex', branch=branch,
        purpose='SIM only', pid=os.getpid(), expected_minutes=2)


def physics(root, timing=True, owner='claude'):
    return legacy.acquire(root, owner=owner, branch=owner+'/physics', purpose='timing',
                        pid=os.getpid(), expected_minutes=2, timing_sensitive=timing)


def test_different_branches_coexist_with_non_timing_legacy_holder(tmp_path):
    physics(tmp_path, False, owner='codex')
    old = (tmp_path/'physics/owner.json').read_bytes()
    slot(tmp_path)
    slot(tmp_path, 'sim-two', 'codex/two')
    report = lock.require_sim_slot(tmp_path, slot='sim-one', owner='codex', branch='codex/one')
    assert [r['name'] for r in report['concurrent_holders']] == ['sim-one', 'sim-two']
    assert len(report['loadavg']) == 3
    assert report['physics_holder']['owner'] == 'codex'
    lock.release(tmp_path, owner='codex', name='sim-one')
    assert (tmp_path/'physics/owner.json').read_bytes() == old
    assert legacy.status(tmp_path, 'sim-two')['pid_alive']


def test_opposing_timing_sensitive_acquisitions_refuse_in_both_orders(tmp_path):
    physics(tmp_path)
    with pytest.raises(RuntimeError, match='timing-sensitive'):
        slot(tmp_path)
    legacy.release(tmp_path, owner='claude')
    slot(tmp_path)
    with pytest.raises(RuntimeError, match='lock held'):
        physics(tmp_path)
    assert legacy.status(tmp_path)['owner'] == 'codex'


@pytest.mark.parametrize('timing', [False, True])
@pytest.mark.parametrize('owner', ['claude', 'codex'])
def test_existing_physics_requires_same_owner_and_non_timing(tmp_path, timing, owner):
    physics(tmp_path, timing, owner)
    if owner == 'codex' and not timing:
        slot(tmp_path)
    else:
        with pytest.raises(RuntimeError):
            slot(tmp_path)


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


@pytest.mark.parametrize('first', [physics, slot], ids=['legacy-first', 'slot-first'])
def test_admission_while_winner_is_publishing_owner(tmp_path, monkeypatch, first):
    """Pause after creating an empty owner file, before writing any JSON."""
    publishing, finish = threading.Event(), threading.Event()
    write_text = Path.write_text

    def paused_write(path, data, *args, **kwargs):
        if path.parent == tmp_path / 'physics' and not publishing.is_set():
            write_text(path, '', *args, **kwargs)
            publishing.set()
            assert finish.wait(5), 'test did not release the owner writer'
        return write_text(path, data, *args, **kwargs)

    monkeypatch.setattr(Path, 'write_text', paused_write)
    second = slot if first is physics else physics
    with ThreadPoolExecutor(1) as pool:
        winner = pool.submit(first, tmp_path)
        try:
            assert publishing.wait(5), 'owner writer was not reached'
            with pytest.raises(RuntimeError):
                second(tmp_path)
        finally:
            finish.set()
        winner.result()
    assert legacy.status(tmp_path)['owner'] == ('claude' if first is physics else 'codex')
    assert (tmp_path / 'sim-one').exists() is (first is slot)


@pytest.mark.parametrize('partial', ['', '{"owner":'])
def test_partial_legacy_owner_refuses_slot_and_snapshot_without_mutation(tmp_path, partial):
    (tmp_path / 'physics').mkdir()
    path = tmp_path / 'physics/owner.json'
    path.write_text(partial)
    for operation in (slot, lock.sim_snapshot):
        with pytest.raises(RuntimeError, match='owner metadata'):
            operation(tmp_path)
    assert path.read_text() == partial
    assert not (tmp_path / 'sim-one').exists()


def test_legacy_wins_between_slot_existence_check_and_mkdir(tmp_path, monkeypatch):
    mkdir = Path.mkdir
    raced = False

    def race(path, *args, **kwargs):
        nonlocal raced
        if path == tmp_path / 'physics' and not raced:
            raced = True
            mkdir(path)
            (path / 'owner.json').write_text('')
        return mkdir(path, *args, **kwargs)

    monkeypatch.setattr(Path, 'mkdir', race)
    with pytest.raises(RuntimeError, match='lock held'):
        slot(tmp_path)
    assert raced
    assert (tmp_path / 'physics/owner.json').read_text() == ''
    assert not (tmp_path / 'sim-one').exists()


@pytest.mark.parametrize('mismatch', ['owner', 'branch', 'dead', 'missing', 'exclusive'])
def test_runner_refuses_nonowned_dead_or_opposing_lock(tmp_path, mismatch, monkeypatch):
    slot(tmp_path)
    owner, branch, name = 'codex', 'codex/one', 'sim-one'
    if mismatch == 'owner': owner = 'claude'
    if mismatch == 'branch': branch = 'codex/two'
    if mismatch == 'dead': monkeypatch.setattr(legacy, '_alive', lambda _: False)
    if mismatch == 'missing': name = 'sim-missing'
    if mismatch == 'exclusive':
        # Simulate an older tool which does not know about SIM slots.
        record = json.loads((tmp_path/'physics/owner.json').read_text())
        record['timing_sensitive'] = True
        (tmp_path/'physics/owner.json').write_text(json.dumps(record))
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
    assert legacy.main(prefix+['status']) == 0
    assert json.loads(capsys.readouterr().out)['owner'] == 'codex'
    assert lock.main(prefix+['status']) == 0
    assert len(json.loads(capsys.readouterr().out)['concurrent_holders']) == 1
    assert lock.main(prefix+['status', '--sim-slot', 'sim-one']) == 0
    assert json.loads(capsys.readouterr().out)['branch'] == 'codex/one'
    assert lock.main(prefix+['release', '--owner', 'codex', '--sim-slot', 'sim-one']) == 0
    assert lock.sim_holders(tmp_path) == []


def test_stale_slot_requires_explicit_release_and_cannot_hide_live_pid(tmp_path, monkeypatch):
    slot(tmp_path)
    with pytest.raises(RuntimeError):
        lock.release(tmp_path, owner='claude', name='sim-one', stale=True)
    monkeypatch.setattr(legacy, '_alive', lambda _: False)
    with pytest.raises(RuntimeError):
        physics(tmp_path)
    lock.release(tmp_path, owner='claude', name='sim-one', stale=True)
    physics(tmp_path)


def test_managed_physics_lasts_until_final_slot_and_legacy_cannot_enter(tmp_path):
    slot(tmp_path)
    original = (tmp_path/'physics/owner.json').read_bytes()
    slot(tmp_path, 'sim-two', 'codex/two')
    lock.release(tmp_path, owner='codex', name='sim-one')
    assert (tmp_path/'physics/owner.json').read_bytes() == original
    with pytest.raises(RuntimeError):
        physics(tmp_path, False)
    lock.require_sim_slot(tmp_path, slot='sim-two', owner='codex', branch='codex/two')
    lock.release(tmp_path, owner='codex', name='sim-two')
    assert legacy.status(tmp_path) is None
    physics(tmp_path, False)


def test_different_coordinator_pid_refused(tmp_path, monkeypatch):
    slot(tmp_path)
    monkeypatch.setattr(legacy, '_alive', lambda _: True)
    with pytest.raises(RuntimeError, match='coordinator PID'):
        lock.acquire_sim_slot(tmp_path, slot='sim-two', owner='codex', branch='codex/two',
            purpose='wrong driver', pid=os.getpid()+100000, expected_minutes=1)


def test_borrowed_physics_is_not_released_after_last_slot(tmp_path):
    physics(tmp_path, False, owner='codex')
    original = (tmp_path/'physics/owner.json').read_bytes()
    slot(tmp_path)
    lock.release(tmp_path, owner='codex', name='sim-one')
    assert (tmp_path/'physics/owner.json').read_bytes() == original


def test_replaced_coordinator_invalidates_slot_and_is_not_released(tmp_path):
    slot(tmp_path)
    legacy.release(tmp_path, owner='codex')
    physics(tmp_path, False, owner='codex')
    with pytest.raises(RuntimeError, match='replaced'):
        lock.require_sim_slot(tmp_path, slot='sim-one', owner='codex', branch='codex/one')
    lock.release(tmp_path, owner='codex', name='sim-one')
    assert legacy.status(tmp_path) is not None


def test_dead_coordinator_or_orphan_slot_fails_closed(tmp_path, monkeypatch):
    slot(tmp_path)
    monkeypatch.setattr(legacy, '_alive', lambda _: False)
    with pytest.raises(RuntimeError):
        slot(tmp_path, 'sim-two')
    legacy.release(tmp_path, owner='codex')
    monkeypatch.setattr(legacy, '_alive', lambda _: True)
    with pytest.raises(RuntimeError, match='orphan'):
        slot(tmp_path, 'sim-two')


def test_incomplete_slot_blocks_new_admission_and_group_release(tmp_path):
    slot(tmp_path)
    (tmp_path/'sim-incomplete').mkdir()
    with pytest.raises(RuntimeError):
        slot(tmp_path, 'sim-two')
    lock.release(tmp_path, owner='codex', name='sim-one')
    assert legacy.status(tmp_path) is not None
