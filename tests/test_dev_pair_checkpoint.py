"""DEV checkpoint/resume tool (scripts/dev_pair_checkpoint.py): reducers, triggers, gate. No physics."""
from __future__ import annotations

import io
import json
import pickle
import threading
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

import numpy as np
import pytest

dpc = pytest.importorskip('scripts.dev_pair_checkpoint')
pytest.importorskip('cloudpickle')


def dumps(obj, out='/runs/a/case', renderers=None, streams=None):
    buf = io.BytesIO()
    dpc.CheckpointPickler(buf, out=out, renderers=renderers or {}, streams=streams or {}).dump(obj)
    return buf.getvalue()


def loads(raw, out='/runs/b/case'):
    dpc._LOAD['out'] = Path(out)
    try:
        return pickle.loads(raw)
    finally:
        dpc._LOAD['out'] = None


class Delegating:
    def __init__(self, inner):
        self._inner = inner
        self.mine = 1

    def __getattr__(self, name):
        return getattr(self._inner, name)


class Inner:
    value = 7


def test_locks_are_recreated_unheld_and_held_lock_is_refused():
    lock, rlock = threading.Lock(), threading.RLock()
    a, b = loads(dumps([lock, rlock]))
    assert not a.locked() and a is not lock
    assert repr(b).startswith('<unlocked')
    with lock:
        with pytest.raises(RuntimeError, match='lock held'):
            dumps(lock)
    with rlock:
        with pytest.raises(RuntimeError, match='RLock held'):
            dumps(rlock)


def test_paths_under_the_case_dir_are_remapped_others_kept():
    got = loads(dumps({'a': Path('/runs/a/case/robots/r1'), 'b': Path('/runs/a/case'), 'c': Path('/elsewhere/x')}))
    assert got == {'a': Path('/runs/b/case/robots/r1'), 'b': Path('/runs/b/case'), 'c': Path('/elsewhere/x')}


def test_delegating_getattr_instance_round_trips_with_cycle():
    obj = Delegating(Inner())
    obj.self_ref = obj
    got = loads(dumps(obj))
    assert got.mine == 1 and got.value == 7 and got.self_ref is got


def test_executor_and_streams_become_placeholders_and_unknown_files_are_refused(tmp_path):
    stream = (tmp_path / 's.jsonl').open('w')
    try:
        executor, stream_slot = loads(dumps([ThreadPoolExecutor(1), stream], streams={'robots/r1/x.jsonl': stream}))
        assert isinstance(executor, dpc.Slot) and executor.kind == 'executor'
        assert isinstance(stream_slot, dpc.Slot) and stream_slot.key == 'robots/r1/x.jsonl'
        with pytest.raises(RuntimeError, match='unknown open file'):
            dumps(stream)
        with pytest.raises(TypeError):
            pickle.dumps(executor)
    finally:
        stream.close()


def test_mjvoption_fields_round_trip():
    mujoco = pytest.importorskip('mujoco')
    option = mujoco.MjvOption()
    option.geomgroup[:] = 0
    option.geomgroup[2] = 1
    option.flags[3] = 1
    got = loads(dumps(option))
    assert isinstance(got, mujoco.MjvOption)
    assert list(got.geomgroup) == list(option.geomgroup) and got.flags[3] == 1


def test_view_into_mujoco_buffer_is_refused_but_mjdata_round_trips_bitwise():
    mujoco = pytest.importorskip('mujoco')
    model = mujoco.MjModel.from_xml_string('<mujoco><worldbody><body><freejoint/><geom size=".1"/></body>'
                                           '<geom type="plane" size="1 1 1"/></worldbody></mujoco>')
    data = mujoco.MjData(model)
    for _ in range(40):
        mujoco.mj_step(model, data)
    with pytest.raises(RuntimeError, match='MuJoCo buffer'):
        dumps({'view': data.qpos[:3]})
    m2, d2 = loads(dumps((model, data)))
    for _ in range(200):
        mujoco.mj_step(model, data)
        mujoco.mj_step(m2, d2)
    assert np.array_equal(data.qpos, d2.qpos) and np.array_equal(data.qvel, d2.qvel)
    assert np.array_equal(data.qacc_warmstart, d2.qacc_warmstart) and data.time == d2.time


class FakeEndpoint:
    def __init__(self):
        self.events = []


class FakeRuntime:
    def __init__(self):
        self.endpoints = {'r1': FakeEndpoint(), 'r2': FakeEndpoint()}
        self.team = type('T', (), {'sessions': [{'endpoints': self.endpoints}]})()


def test_triggers_every_at_and_after_carry_go(tmp_path):
    dc = dpc.DevCheckpoint(checkpoint_dir=tmp_path, every_s=1.0, at_sim_s=[2.52], after_carry_go_s=0.5)
    runtime, fired = FakeRuntime(), {}
    for i in range(80):
        now = 1.3 + i * .05
        if i == 20:
            runtime.endpoints['r1'].events.append({'event': 'barrier_go', 'barrier': 'carry'})
        reasons = dc._triggers(now, 1.3, runtime)
        if reasons:
            fired[round(now, 2)] = reasons
    assert fired[2.3] == ['every_1s'] and fired[3.3] == ['every_1s'] and fired[4.3] == ['every_1s']
    assert fired[2.55] == ['at_sim_s_2.52']
    assert fired[2.8] == ['carry_go_plus_0.5s']


def test_stop_at_sim_s_breaks_and_labels():
    dc = dpc.DevCheckpoint(stop_at_sim_s=2.0)
    backend = type('B', (), {'now': 2.0})()
    result = {}
    assert dc.at_tick(14, backend=backend, runtime=None, start=1.3, commands={}, result=result) is True
    assert result['dev_stop']['stop_at_sim_s'] == 2.0


def _case(root, rows, frames, events):
    (root / 'robots/r1/rgb').mkdir(parents=True)
    (root / 'robots/r1/commands.jsonl').write_text(''.join(json.dumps(r) + '\n' for r in rows))
    for name, data in frames.items():
        (root / 'robots/r1/rgb' / name).write_bytes(data)
    (root / 'student_record.json').write_text(json.dumps({'robots': {'r1': {'events': events}}}))
    return root


def test_compare_gate_identical_prefix_passes_and_any_change_fails(tmp_path):
    rows = [{'t': 1.0 + .05 * k, 'kind': 'hold', 'k': k} for k in range(200)]
    events = [{'event': 'e', 'sim_s': 1.0 + k} for k in range(8)]
    frames = {f'{k:05d}.jpg': bytes([k % 250]) * 10 for k in range(100, 140)}
    cont = _case(tmp_path / 'c', rows, {**frames, '00999.jpg': b'x'}, events + [{'event': 'late', 'sim_s': 99.}])
    good = _case(tmp_path / 'g', rows[:150], frames, events)
    report = dpc.compare(cont, good, from_sim_s=3.0, min_horizon_s=4.0)
    assert report['bit_identical'], report['divergences']
    bad_rows = [dict(r) for r in rows[:150]]
    bad_rows[120]['k'] = -1
    bad = _case(tmp_path / 'b', bad_rows, frames, events)
    report = dpc.compare(cont, bad, from_sim_s=3.0, min_horizon_s=4.0)
    assert not report['bit_identical'] and report['streams']['robots/r1/commands.jsonl']['first_divergent_row'] == 120
    bad_frames = dict(frames)
    bad_frames['00120.jpg'] = b'changed'
    report = dpc.compare(cont, _case(tmp_path / 'f', rows[:150], bad_frames, events), 3.0, 4.0)
    assert not report['bit_identical'] and report['frames']['r1']['first_divergent'].endswith('00120.jpg')
    report = dpc.compare(cont, _case(tmp_path / 'e', rows[:150], frames, events[:3] + [{'event': 'x', 'sim_s': 4.}]),
                         3.0, 4.0)
    assert not report['bit_identical'] and report['divergences'][0]['record']['index'] == 3
    report = dpc.compare(cont, good, from_sim_s=3.0, min_horizon_s=60.)
    assert not report['bit_identical']        # horizon shorter than required


def test_runner_default_is_unchanged_signature():
    import inspect
    from scripts import run_pair_highpose as rph
    assert inspect.signature(rph.student_run_case).parameters['dev_checkpoint'].default is None
