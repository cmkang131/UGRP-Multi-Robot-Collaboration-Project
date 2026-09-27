"""Round-2 adversarial regressions; only fixture trees and our own child processes."""
import fcntl
import json
import os
from pathlib import Path
import subprocess
import sys
import threading
import time
from unittest import mock

import pytest

from scripts import sim_equivalence as eq, sim_slots as slots
from test_sim_speed_tools import write_profile


def profiles(tmp_path, mutate=lambda rows, meta: None):
    rows = [{'step': i, 't': i / 4, 'sha256': str(i) * 64} for i in (2, 4)]
    meta = {'qpos_every': 2, 'mj_steps': 4, 'checkpoints': 2,
            'initial_sim_s': 0., 'timestep': .25, 'final_checkpoint': rows[-1].copy()}
    mutate(rows, meta)
    paths = []
    for side in ('a', 'b'):
        p = write_profile(tmp_path/side, rows, [b'a', b'b'], [{'t': 0., 'kind': 'hold'}],
                          {'sim_s': 1., 'outcome': 'DONE'}, frame_dt=1.)
        (p/'profile.json').write_text(json.dumps(meta))
        paths.append(p)
    return paths


@pytest.mark.parametrize('row', [{}, {'step': True, 't': .5, 'sha256': '2'*64},
    {'step': 2, 't': float('nan'), 'sha256': '2'*64}, {'step': 2, 't': .5, 'sha256': 'x'},
    {'step': 2.5, 't': .5, 'sha256': '2'*64}, {'step': 2, 't': -.5, 'sha256': '2'*64}])
def test_qpos_schema_rejects_identical_malformed_rows(tmp_path, row):
    a, b = profiles(tmp_path, lambda rows, meta: rows.__setitem__(0, row))
    assert eq.compare(a, b)['verdict'] == 'insufficient_evidence'


@pytest.mark.parametrize('case', ['truncated', 'gap', 'order', 'time', 'count', 'steps', 'final_hash',
                                  'final_time', 'no_final', 'interval', 'both_missing_window'])
def test_qpos_completeness(tmp_path, case):
    def change(rows, meta):
        if case in ('truncated', 'both_missing_window'): rows.pop()
        if case == 'gap': rows[0]['step'] = 1
        if case == 'order': rows.reverse()
        if case == 'time': rows[0]['t'] = .9
        if case == 'count': meta['checkpoints'] = 1
        if case == 'steps': meta['mj_steps'] = 6
        if case == 'final_hash': meta['final_checkpoint']['sha256'] = 'a'*64
        if case == 'final_time': meta['final_checkpoint']['t'] = .9
        if case == 'no_final': meta.pop('final_checkpoint')
        if case == 'interval': meta['qpos_every'] = 0
    a, b = profiles(tmp_path, change)
    assert eq.compare(a, b, 1. if case == 'both_missing_window' else None)['verdict'] == 'insufficient_evidence'


def test_release_keeps_inherited_child_reservation(tmp_path):
    slot = slots._try_slot(tmp_path, 1, {'owner': 'test'})
    child = subprocess.Popen([sys.executable, '-c', 'import time; time.sleep(30)'], pass_fds=(slot.fd,))
    try:
        slot.release()
        assert slots.held_count(tmp_path) == 1
    finally:
        child.terminate()
        child.wait(5)
        slot.release()
    assert slots.held_count(tmp_path) == 0


def test_open_slot_file_without_lock_is_not_a_reservation(tmp_path):
    scan = ({22}, {22}, set(), {22: 1})
    with mock.patch.object(slots, '_scan', return_value=scan):
        seen = slots.census(tmp_path)
    assert seen['unslotted_sim_pids'] == [22]
    assert seen['holder_pids'] == []


def test_nine_children_cannot_hide_behind_one_reservation(tmp_path):
    slot = slots._try_slot(tmp_path, 10, {'owner': 'test'})
    try:
        scan = (set(range(100, 109)), {os.getpid()}, set(),
                {**{p: os.getpid() for p in range(100, 109)}, os.getpid(): 1})
        with mock.patch.object(slots, '_scan', return_value=scan):
            extra, seen = slots.try_admit(tmp_path, 6, {'owner': 'test'})
        if extra: extra.release()
        assert seen['running'] >= 9
        assert extra is None
    finally:
        slot.release()


def test_partial_lsof_failure_is_not_a_census(tmp_path):
    partial = subprocess.CompletedProcess([], 1, stdout='p22\nftxt\nn/libmujoco.dylib\n', stderr='denied')
    with mock.patch.object(slots.sys, 'platform', 'darwin'), \
         mock.patch.object(slots.subprocess, 'run', return_value=partial):
        with pytest.raises(RuntimeError): slots._scan(tmp_path)


def make_proc(proc, pid=22):
    d = proc/str(pid)
    (d/'fd').mkdir(parents=True)
    (d/'stat').write_text(f'{pid} (python) S 1 ' + '0 '*17 + '123 0\n')
    (d/'maps').write_text('libmujoco.so')
    return d


def test_live_proc_permission_error_fails_closed(tmp_path):
    proc = tmp_path/'proc'
    d = make_proc(proc)
    real = Path.read_text
    def read(p, *a, **kw):
        if p == d/'maps': raise PermissionError('hidden live maps')
        return real(p, *a, **kw)
    with mock.patch.object(Path, 'read_text', read):
        with pytest.raises((RuntimeError, PermissionError)):
            slots.scan_proc(tmp_path/'slots', proc)


def test_pid_reuse_cannot_cover_a_new_sim(tmp_path):
    slot = slots._try_slot(tmp_path, 2, {'owner': 'test', 'pid': 22, 'start_id': 'old'})
    try:
        with mock.patch.object(slots, '_scan', return_value=({23}, {22}, set(), {22: 1, 23: 22})):
            assert slots.census(tmp_path)['unslotted_sim_pids'] == [23]
    finally:
        slot.release()


def test_import_only_contract_is_explicit(tmp_path):
    with mock.patch.object(slots, '_scan', return_value=({22}, set(), set(), {22: 1})):
        seen = slots.census(tmp_path)
    assert seen.get('counting_contract') == 'loaded_mujoco_process_upper_bound'
    assert seen.get('active_sim_count') is None
    assert seen['unslotted_sim_pids'] == [22]


def test_timeout_includes_admission_lock_wait(tmp_path):
    fd = os.open(tmp_path/'admission.lock', os.O_CREAT | os.O_RDWR, 0o600)
    fcntl.flock(fd, fcntl.LOCK_EX)
    def unblock():
        time.sleep(.8)
        fcntl.flock(fd, fcntl.LOCK_UN)
    thread = threading.Thread(target=unblock)
    thread.start()
    start = time.monotonic()
    try:
        with mock.patch.object(slots, 'census', return_value={'unslotted_sim_pids': []}):
            try: slot = slots.acquire(tmp_path, 1, {}, timeout_s=.1, poll_s=.01)
            except TimeoutError: slot = None
        elapsed = time.monotonic() - start
        if slot: slot.release()
        assert elapsed < .5
        assert slot is None
    finally:
        thread.join()
        os.close(fd)


def test_linux_root_is_shared_across_worktrees_and_portable():
    with mock.patch.object(slots.sys, 'platform', 'linux'):
        # Public helper deliberately tested at runtime; no filesystem access.
        assert hasattr(slots, 'default_root')
        a = slots.default_root()
        assert a.is_absolute() and not str(a).startswith('/Users/')
        with mock.patch.object(slots, '__file__', '/different/worktree/scripts/sim_slots.py'):
            assert slots.default_root() == a


def test_valid_full_profile_and_terminal_remainder(tmp_path):
    a, b = profiles(tmp_path)
    assert eq.compare(a, b)['equivalent']
    for p in (a, b):
        meta = json.loads((p/'profile.json').read_text())
        end = {'step': 5, 't': 1.25, 'sha256': '5'*64}
        meta.update(mj_steps=5, checkpoints=3, final_checkpoint=end)
        (p/'profile.json').write_text(json.dumps(meta))
        with (p/'qpos_checkpoints.jsonl').open('a') as f: f.write(json.dumps(end)+'\n')
        (p/'run'/'result.json').write_text(json.dumps({'sim_s': 1.25, 'outcome': 'DONE'}))
    assert eq.compare(a, b)['equivalent']
    assert eq.compare(a, b, until=1.)['equivalent']


def test_recorder_preserves_final_noninterval_state(monkeypatch):
    import types
    from scripts import sim_profile
    # No physics, imports, workers or writes outside the fixture.
    data = types.SimpleNamespace(time=0., qpos=mock.Mock(), qvel=mock.Mock(), act=mock.Mock())
    for part in (data.qpos, data.qvel, data.act): part.tobytes.return_value = b'state'
    model = types.SimpleNamespace(opt=types.SimpleNamespace(timestep=.25))
    def step(m, d): d.time += m.opt.timestep
    mj = types.SimpleNamespace(mj_step=step)
    monkeypatch.setitem(sys.modules, 'mujoco', mj)
    rec = sim_profile.Recorder(qpos_every=2)
    rec.install_step_hook()
    try:
        for _ in range(5): mj.mj_step(model, data)
        rec.finalize_checkpoints()
        assert [r['step'] for r in rec.checkpoints] == [2, 4, 5]
        assert rec.final_checkpoint == rec.checkpoints[-1]
        assert rec.final_checkpoint['t'] == 1.25
        rec.finalize_checkpoints()
        assert len(rec.checkpoints) == 3
    finally:
        rec.restore()
    assert mj.mj_step is step


def fixture_table(parents, starts):
    table = slots.ProcessTable()
    table.update(parents)
    table.starts.update(starts)
    return table


def test_nine_children_count_is_nine_with_verified_owner(tmp_path):
    owner = os.getpid()
    slot = slots._try_slot(tmp_path, 10, {})
    table = fixture_table({**{p: owner for p in range(100, 109)}, owner: 1},
                          {owner: slot.record['start_id']})
    try:
        with mock.patch.object(slots, '_scan', return_value=(set(range(100, 109)), {owner}, set(), table)):
            extra, seen = slots.try_admit(tmp_path, 6, {})
        assert seen['running'] == 9
        assert len(seen['unslotted_sim_pids']) == 8
        assert extra is None
    finally:
        slot.release()


def test_reused_owner_identity_never_covers_child(tmp_path):
    owner = os.getpid()
    slot = slots._try_slot(tmp_path, 2, {})
    try:
        table = fixture_table({owner: 1, 101: owner}, {owner: slot.record['start_id']})
        with mock.patch.object(slots, '_scan', return_value=({101}, {owner}, set(), table)), \
             mock.patch.object(slots, 'process_identity', return_value='new-process'):
            seen = slots.census(tmp_path)
        assert seen['unslotted_sim_pids'] == [101]
        assert seen['holder_pids'] == []
    finally:
        slot.release()


def test_multiworker_reservation_is_atomic(tmp_path):
    gate = threading.Barrier(2)
    admitted, refused = [], []
    def ask():
        gate.wait()
        try:
            admitted.append(slots.acquire(tmp_path, 3, {}, workers=2, timeout_s=.2, poll_s=.01))
        except TimeoutError:
            refused.append(True)
    with mock.patch.object(slots, '_scan', return_value=(set(), set(), set(), {})):
        threads = [threading.Thread(target=ask) for _ in range(2)]
        for t in threads: t.start()
        for t in threads: t.join(3)
    try:
        assert len(admitted) == len(refused) == 1
        assert slots.held_count(tmp_path) == 2
        assert len(admitted[0].fds) == 2
    finally:
        for slot in admitted: slot.release()
    assert slots.held_count(tmp_path) == 0


def test_partial_lsof_is_rejected_after_valid_identity_snapshot(tmp_path):
    partial = subprocess.CompletedProcess([], 1, stdout='p22\nftxt\nn/libmujoco.dylib\n', stderr='denied')
    table = fixture_table({22: 1}, {22: 'start'})
    with mock.patch.object(slots.sys, 'platform', 'darwin'), \
         mock.patch.object(slots, '_mac_table', return_value=table), \
         mock.patch.object(slots.subprocess, 'run', return_value=partial):
        with pytest.raises(RuntimeError, match='incomplete lsof'): slots._scan(tmp_path)


def test_lsof_and_identity_scan_share_admission_deadline(tmp_path):
    table = fixture_table({22: 1}, {22: 'start'})
    timeouts = []
    def slow_lsof(*args, **kw):
        timeouts.append(kw['timeout'])
        raise subprocess.TimeoutExpired(args[0], kw['timeout'])
    with mock.patch.object(slots.sys, 'platform', 'darwin'), \
         mock.patch.object(slots, '_mac_table', return_value=table), \
         mock.patch.object(slots.subprocess, 'run', side_effect=slow_lsof):
        with pytest.raises(TimeoutError):
            slots.acquire(tmp_path, 1, {}, timeout_s=.1)
    assert 0 < timeouts[0] <= .1
    assert slots.held_count(tmp_path) == 0


def test_linux_pid_reuse_during_maps_read_fails_closed(tmp_path):
    proc = tmp_path/'proc'
    d = make_proc(proc)
    read = Path.read_text
    def changed(p, *a, **kw):
        result = read(p, *a, **kw)
        if p == d/'maps':
            (d/'stat').write_text(read(d/'stat').replace('123 0', '456 0'))
        return result
    with mock.patch.object(Path, 'read_text', changed):
        with pytest.raises(RuntimeError, match='changed'):
            slots.scan_proc(tmp_path/'slots', proc)


def test_cli_holds_until_background_child_without_fd_exits(tmp_path):
    from test_sim_slots import isolated_cli
    ready, stop = tmp_path/'ready', tmp_path/'stop'
    child_code = (f'from pathlib import Path; import os, sys, time; '
                  f'\nwhile os.getppid() == int(sys.argv[1]): time.sleep(.01)'
                  f'\nPath({str(ready)!r}).write_text(str(os.getpid()))'
                  f'\nwhile not Path({str(stop)!r}).exists(): time.sleep(.02)')
    parent_code = ('import subprocess, sys, os; '
                   f'subprocess.Popen([sys.executable, "-c", {child_code!r}, str(os.getpid())])')
    root = tmp_path/'slots'
    wrapper = subprocess.Popen(isolated_cli('--root', str(root), '--slots', '1', 'run', '--owner', 'test',
                                            '--', sys.executable, '-c', parent_code), stderr=subprocess.PIPE)
    try:
        end = time.monotonic() + 5
        while not ready.exists() and wrapper.poll() is None and time.monotonic() < end: time.sleep(.02)
        assert ready.exists()
        time.sleep(.15)  # direct command exits; its child explicitly did not inherit the FD
        assert wrapper.poll() is None
        assert slots.held_count(root) == 1
        stop.touch()
        assert wrapper.wait(5) == 0
        assert slots.held_count(root) == 0
    finally:
        stop.touch()
        try: wrapper.wait(5)
        except subprocess.TimeoutExpired:
            wrapper.kill(); wrapper.wait(5)
        wrapper.stderr.close()
