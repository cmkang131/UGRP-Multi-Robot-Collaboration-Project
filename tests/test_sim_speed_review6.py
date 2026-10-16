"""Pinned process-group lifetime: PR #236 round-6 PID reuse counterexamples."""
import errno
import os
from pathlib import Path
import signal
import subprocess
import sys
import time
from unittest import mock

import pytest

from scripts import sim_slots as slots
from test_sim_slots import isolated_cli


@pytest.mark.parametrize('signum', [signal.SIGINT, signal.SIGTERM])
@pytest.mark.parametrize('reuse', ['before_last_lookup', 'after_last_lookup'])
def test_pid_reuse_at_last_membership_lookup_never_signals_other_job(tmp_path, signum, reuse):
    """The review's exact gap: return old identity, then reuse PID before kill.

    Also runs against HEAD 56697ab2 in the in-memory baseline runner. Its final
    PID kill reaches the injected unrelated job for both interrupt signals.
    """
    handlers, unrelated, group_signals = {}, [], []
    state = dict(exited=False, alive=True, reused=False, reaped=False)
    leader = ('leader-start', 222, 222, 'live')
    descendant = ('descendant-start', 222, 222, 'live')
    replacement = ('other-job-start', 999, 999, 'live')

    def exited(_pid=222):
        if not state['exited']:
            state['exited'] = True
            handlers[signum](signum, None)
        return True

    class Child:
        pid = 222
        returncode = None

        def poll(self):
            exited()
            state['reaped'] = True
            self.returncode = 0
            return 0

        wait = poll

    child = Child()

    def handler(sig, value):
        previous = handlers.get(sig, signal.SIG_DFL)
        handlers[sig] = value
        return previous

    def members(_pgid):
        return ({222: leader} if not state['exited'] else {}) | (
            {333: descendant} if state['alive'] else {})

    def membership(pid):
        assert pid == 333
        state['reused'] = True
        # The lookup was true at the instant it ran. Reuse occurs after its
        # last observation, so another lookup cannot solve this counterexample.
        return replacement if reuse == 'before_last_lookup' else descendant

    def kill(pid, sig):
        assert state['reused'] and pid == 333
        unrelated.append((pid, sig))
        state['alive'] = False

    def killpg(pgid, sig):
        assert pgid == child.pid and child.returncode is None and not state['reaped']
        group_signals.append((pgid, sig))
        # Replacement PID 333 belongs to PGID 999, never to the pinned 222.
        state['alive'] = False

    slot = slots._try_slot(tmp_path, 1, {})
    slot.record.update(waited_s=0, census_at_acquire={'running': 0})
    try:
        with mock.patch.object(slots, 'acquire', return_value=slot), \
             mock.patch.object(slots.subprocess, 'Popen', return_value=child), \
             mock.patch.object(slots.signal, 'signal', side_effect=handler), \
             mock.patch.object(slots.signal, 'getsignal', return_value=signal.SIG_DFL), \
             mock.patch.object(slots, 'process_identity', return_value='leader-start'), \
             mock.patch.object(slots, '_child_exited', side_effect=exited, create=True), \
             mock.patch.object(slots, '_group_members', side_effect=members), \
             mock.patch.object(slots, '_process_membership', side_effect=membership), \
             mock.patch.object(slots, '_group_alive', side_effect=lambda _: state['alive']), \
             mock.patch.object(slots.os, 'kill', side_effect=kill), \
             mock.patch.object(slots.os, 'killpg', side_effect=killpg), \
             mock.patch.object(slots.time, 'sleep'):
            code = slots.main(['--root', str(tmp_path), '--slots', '1', 'run',
                               '--owner', 'test', '--', 'fixture'])
        assert unrelated == [], f'TOCTOU delivered a signal to a reused PID: {unrelated}'
        assert code == (70 if reuse == 'before_last_lookup' else 128 + signum)
        assert group_signals == ([] if reuse == 'before_last_lookup' else [(222, signum)])
        assert slots.held_count(tmp_path) == 0
        assert all(handlers[sig] == signal.SIG_DFL for sig in (signal.SIGINT, signal.SIGTERM))
    finally:
        slot.release()


def test_real_waitid_retains_zombie_until_explicit_reap():
    child = subprocess.Popen([sys.executable, '-c', 'raise SystemExit(7)'], start_new_session=True)
    try:
        deadline = time.monotonic() + 5
        while not slots._child_exited(child.pid) and time.monotonic() < deadline:
            time.sleep(.01)
        assert slots._child_exited(child.pid)
        assert child.returncode is None
        assert slots._child_exited(child.pid)  # WNOWAIT status remains available
        assert child.wait(5) == 7             # exit status not consumed by observation
        with pytest.raises(ChildProcessError):
            slots._child_exited(child.pid)
    finally:
        child.wait(5)


@pytest.mark.parametrize('signum', [signal.SIGINT, signal.SIGTERM])
def test_exit_between_waitid_and_live_lookup_keeps_pending_signal(tmp_path, signum):
    handlers, sent = {}, []
    state = dict(exited=False, alive=True, identity_calls=0, sleeps=0)
    leader, descendant = ('leader', 222, 222, 'live'), ('descendant', 222, 222, 'live')

    class Child:
        pid = 222
        returncode = None

        def poll(self):
            assert not state['alive']
            self.returncode = 0
            return 0

        wait = poll

    def handler(sig, value):
        previous = handlers.get(sig, signal.SIG_DFL)
        handlers[sig] = value
        return previous

    def exited(pid):
        if not state['exited']:
            handlers[signum](signum, None)  # only ONE interrupt, while still live
        return state['exited']

    def identity(pid):
        state['identity_calls'] += 1
        if state['identity_calls'] == 2:
            state['exited'] = True
            raise ProcessLookupError('macOS leader became an invisible zombie')
        return 'leader'

    def send(pgid, sig):
        assert (pgid, sig) == (222, signum)
        sent.append(sig)
        state['alive'] = False

    def sleep(seconds):
        state['sleeps'] += 1
        assert state['sleeps'] <= 2, 'stop request lost at leader exit'

    slot = slots._try_slot(tmp_path, 1, {})
    try:
        with mock.patch.object(slots.subprocess, 'Popen', return_value=Child()), \
             mock.patch.object(slots.signal, 'signal', side_effect=handler), \
             mock.patch.object(slots.signal, 'getsignal', return_value=signal.SIG_DFL), \
             mock.patch.object(slots, 'process_identity', side_effect=identity), \
             mock.patch.object(slots, '_child_exited', side_effect=exited), \
             mock.patch.object(slots, '_group_members', side_effect=lambda _: (
                 {222: leader} if not state['exited'] else {}) | (
                 {333: descendant} if state['alive'] else {})), \
             mock.patch.object(slots, '_group_alive', side_effect=lambda _: state['alive']), \
             mock.patch.object(slots, '_process_membership', return_value=descendant), \
             mock.patch.object(slots.os, 'kill', side_effect=AssertionError('individual PID signal')), \
             mock.patch.object(slots.os, 'killpg', side_effect=send), \
             mock.patch.object(slots.time, 'sleep', side_effect=sleep):
            assert slots.run_reserved(slot, ['fixture']) == 128 + signum
        assert sent == [signum]
    finally:
        slot.release()
    assert slots.held_count(tmp_path) == 0


def test_waitid_uses_nonreaping_flags():
    constants = dict(P_PID=1, WEXITED=4, WNOHANG=1, WNOWAIT=32)
    with mock.patch.multiple(slots.os, **constants, create=True), \
         mock.patch.object(slots.os, 'waitid', side_effect=[None, object()], create=True) as waitid:
        assert not slots._child_exited(222)
        assert slots._child_exited(222)
        assert waitid.call_args_list == [mock.call(1, 222, 37)] * 2


@pytest.mark.parametrize('error', [errno.ECHILD, errno.EPERM])
def test_darwin_waitid_retries_eintr_but_does_not_hide_ownership_errors(monkeypatch, error):
    monkeypatch.delattr(slots.os, 'waitid', raising=False)
    monkeypatch.setattr(slots.sys, 'platform', 'darwin')
    errors = iter([errno.EINTR, error])

    def waitid(*args):
        slots.ctypes.set_errno(next(errors))
        return -1

    with mock.patch.object(slots, '_darwin_waitid', return_value=waitid):
        with pytest.raises(OSError) as exc:
            slots._child_exited(222)
    assert exc.value.errno == error


@pytest.mark.parametrize('detach', ['setsid', 'setpgid'])
def test_real_detached_descendant_is_not_signalled_and_wrapper_releases(tmp_path, detach):
    """Real Darwin/Linux detach after observation; no FD inherited by descendant."""
    seen, ready, stop, received, done = (tmp_path/n for n in ('seen', 'ready', 'stop', 'received', 'done'))
    child_code = f'''
import json, os, signal, time
from pathlib import Path
signal.signal(signal.SIGINT, lambda sig, frame: Path({str(received)!r}).touch())
signal.signal(signal.SIGTERM, lambda sig, frame: Path({str(received)!r}).touch())
deadline = time.monotonic() + 10
while not Path({str(seen)!r}).exists() and time.monotonic() < deadline:
    time.sleep(.01)
{'os.setsid()' if detach == 'setsid' else 'os.setpgid(0, 0)'}
Path({str(ready)!r}).write_text(json.dumps({{'pid': os.getpid(), 'pgid': os.getpgrp()}}))
while not Path({str(stop)!r}).exists() and time.monotonic() < deadline:
    time.sleep(.01)
Path({str(done)!r}).touch()
'''
    parent_code = f'''
import os, subprocess, sys, time
from pathlib import Path
subprocess.Popen([sys.executable, '-c', {child_code!r}], stderr=subprocess.DEVNULL)
deadline = time.monotonic() + 10
while not Path({str(ready)!r}).exists() and time.monotonic() < deadline:
    time.sleep(.01)
'''
    root = tmp_path/'slots'
    command = isolated_cli('--root', str(root), '--slots', '1', 'run', '--owner', 'test',
                           '--', sys.executable, '-c', parent_code)
    observer = f'''
original_members = s._group_members
original_exited = s._child_exited
def exited(pid):
    done = original_exited(pid)
    if done and s.Path({str(ready)!r}).exists():
        s.signal.raise_signal(s.signal.SIGTERM)
    return done
s._child_exited = exited
def members(pgid):
    found = original_members(pgid)
    if any(pid != pgid for pid in found):
        s.Path({str(seen)!r}).touch()
    return found
s._group_members = members
'''
    command[2] = command[2].replace('raise SystemExit(s.main())',
                                   f'exec({observer!r}); raise SystemExit(s.main())')
    wrapper = subprocess.Popen(command, stderr=subprocess.PIPE, text=True)
    try:
        assert wrapper.wait(5) == 70
        error = wrapper.stderr.read()
        assert 'left process group' in error and 'not signalled' in error
        assert seen.exists() and ready.exists()
        assert not received.exists() and not done.exists()
        assert slots.held_count(root) == 0
    finally:
        stop.touch()  # controlled descendant exits on its own; never signal its PID
        deadline = time.monotonic() + 5
        while ready.exists() and not done.exists() and time.monotonic() < deadline:
            time.sleep(.01)
        try:
            wrapper.wait(5)
        except subprocess.TimeoutExpired:
            wrapper.kill()
            wrapper.wait(5)
        wrapper.stderr.close()
    assert done.exists()


def test_run_reserved_contains_no_individual_pid_signal():
    import ast
    tree = ast.parse(Path(slots.__file__).read_text())
    assert not [node for node in ast.walk(tree) if isinstance(node, ast.Call)
                and isinstance(node.func, ast.Attribute) and node.func.attr == 'kill'
                and isinstance(node.func.value, ast.Name) and node.func.value.id == 'os']
