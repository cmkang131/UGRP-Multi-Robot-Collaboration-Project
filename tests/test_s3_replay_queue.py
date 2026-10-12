"""A waiting job must not bypass a disk/lock change after session startup."""
import importlib.util
from pathlib import Path
from types import SimpleNamespace


def test_recheck_each_launch_without_touching_other_owner(monkeypatch):
    path = Path('experiments/2026-10-09-s3-no-prior/s3fix9/run_replays.py')
    spec = importlib.util.spec_from_file_location('s3_replay_queue', path)
    m = importlib.util.module_from_spec(spec); spec.loader.exec_module(m)
    held = dict(owner='codex', branch='codex/sim-speed-ctrl2', pid=123)
    state = dict(held=held, free=20*1024**3)
    monkeypatch.setattr(m.agent_lock, 'status', lambda root: state['held'])
    monkeypatch.setattr(m.shutil, 'disk_usage', lambda root: SimpleNamespace(free=state['free']))
    assert not m.launch_state()['ready'] and m.launch_state()['held'] is held
    state.update(held=None, free=9*1024**3)
    assert not m.launch_state()['ready'] and m.launch_state()['reason'] == 'disk_reserve'
    state['free'] = 10*1024**3
    assert m.launch_state()['ready']
    state['held'] = held
    assert not m.launch_state()['ready']
