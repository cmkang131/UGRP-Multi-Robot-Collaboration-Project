"""PR #236 round-3 regressions. No live slot directories or physical episodes."""
import json
import os
from pathlib import Path
import signal
import sys
import types
from unittest import mock

import pytest

from scripts import sim_equivalence as eq, sim_profile as profile, sim_slots as slots
from sim_speed_fixtures import LOGS, full_profile, refresh_manifest, write_rows
from test_sim_speed_review2 import make_proc


@pytest.mark.parametrize('moment', ['during_poll', 'after_reap'])
def test_never_signal_reaped_group_even_when_pgid_reused(tmp_path, moment):
    handlers, sent = {}, []
    class Child:
        pid = 222
        returncode = None
        def poll(self):
            self.returncode = 0  # simulate waitpid reaping before Python poll returns
            if moment == 'during_poll': handlers[signal.SIGTERM](signal.SIGTERM, None)
            return 0
    child = Child()
    def handler(sig, value):
        old = handlers.get(sig, signal.SIG_DFL)
        handlers[sig] = value
        return old
    def group_alive(pgid):
        if moment == 'after_reap': handlers[signal.SIGTERM](signal.SIGTERM, None)
        return False
    slot = slots._try_slot(tmp_path, 1, {})
    slot.additional = []
    try:
        with mock.patch.object(slots.subprocess, 'Popen', return_value=child), \
             mock.patch.object(slots.signal, 'signal', side_effect=handler), \
             mock.patch.object(slots, 'process_identity', return_value='original'), \
             mock.patch.object(slots.os, 'getpgid', return_value=222), \
             mock.patch.object(slots, '_group_alive', side_effect=group_alive), \
             mock.patch.object(slots.os, 'killpg', side_effect=lambda *a: sent.append(a)):
            slots.run_reserved(slot, ['fixture'])
        assert sent == []
    finally:
        slot.release()


@pytest.mark.parametrize('options', ['rw,hidepid=2', 'rw,hidepid=invisible', 'rw,hidepid=ptraceable', 'rw'])
def test_linux_hidden_or_unproven_host_census_is_rejected(tmp_path, options):
    proc = tmp_path/'proc'
    d = make_proc(proc)
    (d/'maps').write_text('')  # the *visible* list has zero MuJoCo imports
    (proc/'self').mkdir()
    (proc/'self'/'mountinfo').write_text(f'24 1 0:1 / {proc} rw - proc proc {options}\n')
    with pytest.raises(RuntimeError):
        slots.scan_proc(tmp_path/'slots', proc)


@pytest.mark.parametrize('name', LOGS[2:])
def test_identical_missing_full_logs_are_insufficient(tmp_path, name):
    a, b = (full_profile(tmp_path/s) for s in ('a', 'b'))
    for p in (a, b): (p/'run'/name).unlink()
    assert eq.compare(a, b)['verdict'] == 'insufficient_evidence'


@pytest.mark.parametrize('case', ['frames', 'commands', 'frame_gap', 'frame_tail', 'gt_gap', 'gt_tail',
                                  'eval_gap', 'post_grasp', 'phase_result', 'manifest'])
def test_full_log_completeness_beyond_qpos(tmp_path, case):
    a, b = (full_profile(tmp_path/s) for s in ('a', 'b'))
    for p in (a, b):
        run = p/'run'
        name = {'commands': LOGS[0], 'gt_gap': 'eval_only/gt_trajectory.jsonl',
                'gt_tail': 'eval_only/gt_trajectory.jsonl', 'eval_gap': 'eval_only/frames_eval.jsonl'}.get(case, LOGS[1])
        rows = [json.loads(line) for line in (run/name).read_text().splitlines()]
        if case in ('frames', 'commands', 'frame_tail', 'gt_tail'): rows = rows[:1]
        if case in ('frame_gap', 'gt_gap', 'eval_gap'): rows.pop(2)
        if case == 'post_grasp':
            for r in rows: r['skill_phase'] = 'grasp'
        write_rows(run/name, rows)
        if case == 'phase_result':
            result = json.loads((run/'result.json').read_text())
            result['phase_times'].pop('skill:to_carry_posture')
            (run/'result.json').write_text(json.dumps(result))
        # Even an updated manifest cannot substitute for counts/cadence/phases.
        refresh_manifest(run)
        if case == 'frame_tail':
            result = json.loads((run/'result.json').read_text()); result['frames'] = 1
            (run/'result.json').write_text(json.dumps(result))
            write_rows(run/'eval_only/frames_eval.jsonl', [json.loads((run/'eval_only/frames_eval.jsonl').read_text().splitlines()[0])])
            refresh_manifest(run)
        if case == 'manifest':
            meta = json.loads((run/'manifest.json').read_text()); meta['files'].pop(LOGS[0])
            (run/'manifest.json').write_text(json.dumps(meta))
    assert eq.compare(a, b)['verdict'] == 'insufficient_evidence'


def test_final_physics_state_preserved_before_between_checkpoint_mutation(monkeypatch):
    class Bytes:
        value = b'before'
        def tobytes(self): return self.value
    data = types.SimpleNamespace(time=0., qpos=Bytes(), qvel=Bytes(), act=Bytes())
    model = types.SimpleNamespace(opt=types.SimpleNamespace(timestep=.25))
    def step(m, d): d.time += m.opt.timestep
    mj = types.SimpleNamespace(mj_step=step)
    monkeypatch.setitem(sys.modules, 'mujoco', mj)
    rec = profile.Recorder(qpos_every=2)
    rec.install_step_hook()
    try:
        for _ in range(5): mj.mj_step(model, data)
        data.qpos.value = b'after'
        rec.finalize_checkpoints()
        assert rec.checkpoint_error == 'state changed after final mj_step'
        assert rec.last_step_checkpoint != rec.final_checkpoint
        assert rec.checkpoints[-1] == rec.last_step_checkpoint
    finally:
        rec.restore()


def test_sim_slot_can_reserve_already_loaded_caller_at_cap_one(tmp_path):
    scan = ({os.getpid()}, set(), set(), {os.getpid(): 1})
    with mock.patch.object(slots, '_scan', return_value=scan):
        with slots.sim_slot(owner='test', root=tmp_path, slots=1, timeout_s=.08):
            assert slots.held_count(tmp_path) == 1
    assert slots.held_count(tmp_path) == 0


@pytest.mark.parametrize('target', [LOGS[0], 'controller_events.jsonl', 'result.json', 'result_null'])
def test_full_comparison_requires_original_bytes(tmp_path, target):
    a, b = (full_profile(tmp_path/s) for s in ('a', 'b'))
    path = b/'run'/('result.json' if target == 'result_null' else target)
    if target == 'result_null':
        doc = json.loads(path.read_text()); doc['extra'] = None
        path.write_text(json.dumps(doc))
    elif path.suffix == '.json':
        path.write_text(json.dumps(json.loads(path.read_text()), indent=4, sort_keys=True))
    else:
        rows = [json.loads(line) for line in path.read_text().splitlines()]
        if target == LOGS[0]: rows[0]['t'] = 0  # parsed 0 and 0.0 compare equal
        path.write_text(''.join(json.dumps(r, sort_keys=True, separators=(',', ':'))+'\n' for r in rows))
    refresh_manifest(b/'run')
    assert eq.compare(a, b)['verdict'] == 'different'


def test_complete_m1_evidence_is_equivalent(tmp_path):
    a, b = (full_profile(tmp_path/s) for s in ('a', 'b'))
    report = eq.compare(a, b)
    assert report['equivalent'], report['evidence_errors']
    for name in (*LOGS, 'result.json'):
        assert len(report['checks'][name]['sha256_a']) == 64
    assert eq.compare(a, b, until=.8)['equivalent']


@pytest.mark.parametrize('steps', [4, 5])
def test_termination_and_last_step_are_independent_and_written(tmp_path, monkeypatch, steps):
    from contextlib import redirect_stdout
    from io import StringIO
    class Bytes:
        value = b'before'
        def tobytes(self): return self.value
    data = types.SimpleNamespace(time=0., qpos=Bytes(), qvel=Bytes(), act=Bytes())
    model = types.SimpleNamespace(opt=types.SimpleNamespace(timestep=.25))
    def step(m, d): d.time += m.opt.timestep
    mj = types.SimpleNamespace(mj_step=step)
    monkeypatch.setitem(sys.modules, 'mujoco', mj)
    rec = profile.Recorder(qpos_every=2)
    rec.install_step_hook()
    try:
        for _ in range(steps): mj.mj_step(model, data)
        saved = rec.last_step_checkpoint.copy()
        data.qpos.value = b'termination'
        args = types.SimpleNamespace(stop_at_phase='')
        summary = dict(episode='fixture', cpu_s={}, counters={}, wall_s_informational=0, mj_steps=steps)
        with redirect_stdout(StringIO()): profile.write_outputs(tmp_path, args, rec, summary, None)
        doc = json.loads((tmp_path/'profile.json').read_text())
        rows = [json.loads(line) for line in (tmp_path/'qpos_checkpoints.jsonl').read_text().splitlines()]
        assert doc['last_step_checkpoint'] == rows[-1] == saved
        assert doc['final_checkpoint'] != saved
        assert doc['checkpoint_error'] == 'state changed after final mj_step'
    finally:
        rec.restore()


@pytest.mark.parametrize('identity_ok', [True, False])
def test_signal_during_live_poll_is_deferred_until_ownership_checked(tmp_path, identity_ok):
    handlers, sent = {}, []
    class Child:
        pid = 222
        returncode = None
        calls = 0
        def poll(self):
            self.calls += 1
            if self.calls == 1:
                handlers[signal.SIGTERM](signal.SIGTERM, None)
                assert not sent  # handler may interrupt a reaping syscall; it cannot send here
                return None
            self.returncode = 0
            return 0
    child = Child()
    def handler(sig, value):
        old = handlers.get(sig, signal.SIG_DFL)
        handlers[sig] = value
        return old
    slot = slots._try_slot(tmp_path, 1, {})
    try:
        starts = ['original', 'original' if identity_ok else 'reused']
        with mock.patch.object(slots.subprocess, 'Popen', return_value=child), \
             mock.patch.object(slots.signal, 'signal', side_effect=handler), \
             mock.patch.object(slots, 'process_identity', side_effect=starts), \
             mock.patch.object(slots.os, 'getpgid', return_value=222), \
             mock.patch.object(slots, '_group_alive', return_value=False), \
             mock.patch.object(slots.os, 'killpg', side_effect=lambda *a: sent.append(a)):
            assert slots.run_reserved(slot, ['fixture']) == 128 + signal.SIGTERM
        assert sent == ([(222, signal.SIGTERM)] if identity_ok else [])
    finally:
        slot.release()


def verified_proc_fixture(tmp_path, monkeypatch):
    proc = tmp_path/'proc'
    d = make_proc(proc)
    (d/'maps').write_text('')
    (proc/'self/ns').mkdir(parents=True)
    (proc/'1/ns').mkdir(parents=True)
    (proc/'sys/kernel/random').mkdir(parents=True)
    (proc/'self/ns/pid').write_text('fixture namespace')
    os.link(proc/'self/ns/pid', proc/'1/ns/pid')
    st = (proc/'self/ns/pid').stat()
    (proc/'sys/kernel/random/boot_id').write_text('boot-fixture')
    (proc/'self/mountinfo').write_text(f'24 1 0:1 / {proc} rw - proc proc rw,hidepid=0\n')
    reference = {'schema': 'ugrp.host_proc_visibility.v1', 'boot_id': 'boot-fixture',
                 'pid_namespace': {'device': st.st_dev, 'inode': st.st_ino}}
    # Only administrative provenance is mocked; actual mount/namespace validation runs.
    monkeypatch.setattr(slots, '_host_visibility_reference', lambda: reference)
    return proc, reference


def test_verified_linux_visible_empty_census_can_be_zero(tmp_path, monkeypatch):
    proc, _ = verified_proc_fixture(tmp_path, monkeypatch)
    assert slots.scan_proc(tmp_path/'slots', proc)[0] == set()


@pytest.mark.parametrize('case', ['namespace', 'boot', 'overlay', 'subtree', 'hidepid'])
def test_linux_visibility_pin_does_not_override_restrictions(tmp_path, monkeypatch, case):
    proc, reference = verified_proc_fixture(tmp_path, monkeypatch)
    mount = proc/'self/mountinfo'
    if case == 'namespace': reference['pid_namespace']['inode'] += 1
    if case == 'boot': reference['boot_id'] = 'previous-boot'
    if case == 'overlay':
        mount.write_text(mount.read_text() + f'25 24 0:2 / {proc}/22 rw - tmpfs tmpfs rw\n')
    if case == 'subtree': mount.write_text(mount.read_text().replace('0:1 / ', '0:1 /subset '))
    if case == 'hidepid': mount.write_text(mount.read_text().replace('hidepid=0', 'hidepid=2'))
    with pytest.raises(RuntimeError): slots.scan_proc(tmp_path/'slots', proc)


def test_new_worker_cannot_spend_caller_credit(tmp_path):
    scan = ({os.getpid()}, set(), set(), {os.getpid(): 1})
    with mock.patch.object(slots, '_scan', return_value=scan):
        slot, _ = slots.try_admit(tmp_path, 1, {}, workers=1)
        assert slot is None  # CLI/worker admission adds a worker
        slot, seen = slots.try_admit(tmp_path, 1, {}, workers=1, include_current=True)
    try:
        assert slot is not None and seen['current_process_credit'] == 1
    finally:
        if slot: slot.release()


def test_current_plus_child_needs_two_reservations(tmp_path):
    scan = ({os.getpid()}, set(), set(), {os.getpid(): 1})
    with mock.patch.object(slots, '_scan', return_value=scan):
        with slots.sim_slot(owner='test', root=tmp_path, slots=2, workers=2, timeout_s=.2):
            assert slots.held_count(tmp_path) == 2


def test_linux_group_exit_requires_visible_census(monkeypatch):
    monkeypatch.setattr(slots.sys, 'platform', 'linux')
    # An empty visible list cannot prove that the work group has exited.
    monkeypatch.setattr(Path, 'iterdir', lambda _: iter(()))
    monkeypatch.setattr(slots, 'verify_linux_visibility', mock.Mock(side_effect=RuntimeError('hidepid=2')))
    with pytest.raises(RuntimeError, match='hidepid'):
        slots._group_alive(222)


@pytest.mark.parametrize('name,field', [('macros.jsonl', 'skill_phase'), ('skill_events.jsonl', 'event')])
def test_malformed_phase_evidence_is_insufficient(tmp_path, name, field):
    a, b = (full_profile(tmp_path/s) for s in ('a', 'b'))
    for p in (a, b):
        run = p/'run'
        rows = [json.loads(line) for line in (run/name).read_text().splitlines()]
        rows[0][field] = []
        write_rows(run/name, rows)
        refresh_manifest(run)
    assert eq.compare(a, b)['verdict'] == 'insufficient_evidence'
