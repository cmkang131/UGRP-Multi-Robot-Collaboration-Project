"""PR #236 round-5: interruption after the launcher exits must remain bounded."""
import json
from pathlib import Path
import signal
import subprocess
import sys
import time
import types
from unittest import mock

import pytest

from scripts import sim_slots as slots


@pytest.mark.parametrize('signum', [signal.SIGINT, signal.SIGTERM])
def test_interrupt_owned_descendant_after_leader_reaped(tmp_path, signum):
    """Keep the legacy regression ID; round 6 now forbids that early reaping."""
    handlers, sent = {}, []
    state = {'alive': True, 'sleeps': 0, 'exited': False}
    leader = ('leader-start', 222, 222, 'live')
    descendant = ('descendant-start', 222, 222, 'live')

    class Child:
        pid = 222
        returncode = None

        def poll(self):
            assert not state['alive'], 'must keep leader pinned until descendants stop'
            self.returncode = 0
            return 0
        wait = poll

    child = Child()

    def handler(sig, value):
        old = handlers.get(sig, signal.SIG_DFL)
        handlers[sig] = value
        return old

    def members(pgid):
        assert pgid == child.pid
        return ({222: leader} if not state['exited'] else {}) | (
            {333: descendant} if state['alive'] else {})

    def exited(_pid):
        state['exited'] = True
        return True

    def send(pid, sig):
        assert pid == 222 and sig == signum
        assert child.returncode is None, 'PGID must be pinned during signalling'
        sent.append((pid, sig))
        state['alive'] = False

    def sleep(_seconds):
        state['sleeps'] += 1
        assert state['sleeps'] <= 3, 'wrapper stuck: descendant received no interrupt'
        assert child.returncode is None  # exited, deliberately NOT reaped
        handlers[signum](signum, None)

    slot = slots._try_slot(tmp_path, 1, {})
    slot.additional = []  # _try_slot at 78945a3c predates Slot's default list
    try:
        with mock.patch.object(slots.subprocess, 'Popen', return_value=child), \
             mock.patch.object(slots.signal, 'signal', side_effect=handler), \
             mock.patch.object(slots.signal, 'getsignal', return_value=signal.SIG_DFL), \
             mock.patch.object(slots, 'process_identity', return_value='leader-start'), \
             mock.patch.object(slots, '_group_alive', side_effect=lambda _: state['alive']), \
             mock.patch.object(slots, '_group_members', side_effect=members, create=True), \
             mock.patch.object(slots, '_process_membership', return_value=descendant, create=True), \
             mock.patch.object(slots, '_child_exited', side_effect=exited), \
             mock.patch.object(slots.os, 'kill', side_effect=AssertionError('individual PID signal')), \
             mock.patch.object(slots.os, 'killpg', side_effect=send), \
             mock.patch.object(slots.time, 'sleep', side_effect=sleep):
            assert slots.run_reserved(slot, ['fixture']) == 128 + signum
        assert len(sent) == 1
        assert all(handlers[sig] == signal.SIG_DFL for sig in (signal.SIGINT, signal.SIGTERM))
    finally:
        slot.release()
    assert slots.held_count(tmp_path) == 0


@pytest.mark.parametrize('case', [
    'initial_scan_error', 'initial_identity_error', 'leader_reused', 'liveness_error', 'scan_error',
    'unobserved_descendant',
    'unknown_pid', 'pid_reused', 'wrong_session', 'wrong_group',
    'late_pid_reuse', 'late_session_change', 'late_group_change', 'late_lookup_error',
])
def test_unverified_descendants_error_without_signal_and_release_all_slots(tmp_path, capsys, case):
    handlers = {}
    leader = ('leader-start', 222, 222, 'live')
    owned = ('descendant-start', 222, 222, 'live')
    child = types.SimpleNamespace(pid=222, returncode=None)
    state = {'exited': False}

    def poll():
        child.returncode = 0
        return 0

    def exited(_pid):
        state['exited'] = True
        handlers[signal.SIGTERM](signal.SIGTERM, None)
        return True

    child.poll = poll

    def handler(sig, value):
        old = handlers.get(sig, signal.SIG_DFL)
        handlers[sig] = value
        return old

    def members(_pgid):
        if not state['exited']:
            if case == 'initial_scan_error':
                raise PermissionError('snapshot denied')
            if case == 'unobserved_descendant':
                return {222: leader}
            return {222: ('new-leader', 222, 222, 'live') if case == 'leader_reused' else leader,
                    333: owned}
        if case == 'scan_error':
            raise TimeoutError('snapshot deadline expired')
        if case == 'unknown_pid':
            return {444: owned}
        return {333: {
            'pid_reused': ('new-process', 222, 222, 'live'),
            'wrong_session': ('descendant-start', 222, 999, 'live'),
            'wrong_group': ('descendant-start', 999, 222, 'live'),
        }.get(case, owned)}

    def membership(_pid):
        if case == 'late_lookup_error':
            raise PermissionError('identity denied')
        return {
            'late_pid_reuse': ('new-process', 222, 222, 'live'),
            'late_session_change': ('descendant-start', 222, 999, 'live'),
            'late_group_change': ('descendant-start', 999, 222, 'live'),
        }.get(case, owned)

    slot = slots._try_slot(tmp_path, 2, {})
    slot.additional = [slots._try_slot(tmp_path, 2, {})]
    slot.record.update(waited_s=0, census_at_acquire={'running': 0})
    try:
        with mock.patch.object(slots, 'acquire', return_value=slot), \
             mock.patch.object(slots.subprocess, 'Popen', return_value=child), \
             mock.patch.object(slots.signal, 'signal', side_effect=handler), \
             mock.patch.object(slots.signal, 'getsignal', return_value=signal.SIG_DFL), \
             mock.patch.object(slots, 'process_identity', **(
                 {'side_effect': ProcessLookupError(222)} if case == 'initial_identity_error'
                 else {'return_value': 'leader-start'})), \
             mock.patch.object(slots, '_group_members', side_effect=members), \
             mock.patch.object(slots, '_process_membership', side_effect=membership), \
             mock.patch.object(slots, '_child_exited', side_effect=exited), \
             mock.patch.object(slots, '_group_alive', **(
                 {'side_effect': PermissionError('census denied')} if case == 'liveness_error'
                 else {'return_value': True})), \
             mock.patch.object(slots.os, 'kill') as kill, \
             mock.patch.object(slots.os, 'killpg') as killpg, \
             mock.patch.object(slots.time, 'sleep', side_effect=AssertionError('must not keep waiting')):
            assert slots.main(['--root', str(tmp_path), '--slots', '2', 'run', '--owner', 'test',
                               '--workers', '2', '--', 'fixture']) == 70
        kill.assert_not_called()
        killpg.assert_not_called()
        error = capsys.readouterr().err
        assert 'cannot verify' in error and 'releasing wrapper reservation' in error
        assert all(handlers[sig] == signal.SIG_DFL for sig in (signal.SIGINT, signal.SIGTERM))
        assert all(s.fd == -1 for s in (slot, *slot.additional))
        assert slots.held_count(tmp_path) == 0
    finally:
        slot.release()


@pytest.mark.parametrize('signum', [signal.SIGINT, signal.SIGTERM])
def test_real_cli_interrupts_orphan_without_slot_fd(tmp_path, signum):
    """Real setsid/fork/identity/signal/flock; only admission census is isolated."""
    from test_sim_slots import isolated_cli

    ready, stop, received, exited, reaped = (tmp_path/name for name in
                                           ('ready', 'stop', 'received', 'exited', 'reaped'))
    child_code = f'''
import json, os, signal, sys, time
from pathlib import Path
def interrupted(signum, frame):
    Path({str(received)!r}).write_text(str(signum))
    raise SystemExit(0)
signal.signal(signal.SIGINT, interrupted)
signal.signal(signal.SIGTERM, interrupted)
while os.getppid() == int(sys.argv[1]):
    time.sleep(.01)
pending = Path({str(ready.with_suffix('.pending'))!r})
pending.write_text(json.dumps({{'pid': os.getpid(), 'group': os.getpgrp(), 'session': os.getsid(0)}}))
pending.rename({str(ready)!r})
deadline = time.monotonic() + 10
while not Path({str(stop)!r}).exists() and time.monotonic() < deadline:
    time.sleep(.01)
'''
    parent_code = ('import os, subprocess, sys; '
                   f'subprocess.Popen([sys.executable, "-c", {child_code!r}, str(os.getpid())])')
    root = tmp_path/'slots'
    command = isolated_cli('--root', str(root), '--slots', '1', 'run',
                           '--owner', 'test', '--', sys.executable, '-c', parent_code)
    observer = f'''
original_exited = s._child_exited
def observe_exit(pid):
    done = original_exited(pid)
    if done:
        s.Path({str(exited)!r}).touch()
    return done
s._child_exited = observe_exit
class ObservedPopen(s.subprocess.Popen):
    def poll(self):
        code = super().poll()
        if code is not None:
            s.Path({str(reaped)!r}).touch()
        return code
    def wait(self, *args, **kwargs):
        code = super().wait(*args, **kwargs)
        s.Path({str(reaped)!r}).touch()
        return code
s.subprocess.Popen = ObservedPopen
'''
    command[2] = command[2].replace('raise SystemExit(s.main())',
                                     f'exec({observer!r}); raise SystemExit(s.main())')
    wrapper = subprocess.Popen(command, stderr=subprocess.PIPE, text=True)
    try:
        deadline = time.monotonic() + 5
        while not (ready.exists() and exited.exists()) and wrapper.poll() is None and time.monotonic() < deadline:
            time.sleep(.01)
        assert ready.exists(), 'descendant did not become orphaned'
        assert exited.exists(), 'wrapper did not observe launcher exit without reaping'
        assert not reaped.exists(), 'wrapper must retain the zombie to pin PGID'
        info = json.loads(ready.read_text())
        assert info['group'] == info['session']
        assert info['pid'] != info['group']
        assert wrapper.poll() is None
        assert slots.held_count(root) == 1
        wrapper.send_signal(signum)
        assert wrapper.wait(5) == 128 + signum, wrapper.stderr.read()
        assert received.read_text() == str(signum)
        assert reaped.exists(), 'wrapper must reap the leader after group signalling'
        assert slots.held_count(root) == 0
    finally:
        stop.touch()  # graceful bounded cleanup also works against the broken baseline
        try:
            wrapper.wait(5)
        except subprocess.TimeoutExpired:
            wrapper.kill()
            wrapper.wait(5)
        wrapper.stderr.close()


def test_linux_membership_reads_session_and_start_from_one_stat():
    text = '333 (child (worker)) S 1 222 222 ' + '0 '*15 + '9876 0\n'
    with mock.patch.object(slots.sys, 'platform', 'linux'), \
         mock.patch.object(Path, 'read_text', return_value=text):
        assert slots._process_membership(333) == ('9876', 222, 222, 'S')


@pytest.mark.parametrize('changed', ['start_sec', 'start_usec', 'pgid'])
def test_mac_membership_rejects_reuse_during_getsid(changed):
    before = types.SimpleNamespace(start_sec=123, start_usec=456, pgid=222, status=2)
    after = types.SimpleNamespace(**vars(before))
    setattr(after, changed, getattr(after, changed) + 1)
    with mock.patch.object(slots.sys, 'platform', 'darwin'), \
         mock.patch.object(slots, '_mac_info', side_effect=[before, after]), \
         mock.patch.object(slots.os, 'getsid', return_value=222):
        with pytest.raises(RuntimeError, match='identity changed'):
            slots._process_membership(333)
