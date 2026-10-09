"""No model construction/physics: relay and completed JSON bytes must match."""
from contextlib import nullcontext
from types import SimpleNamespace

import numpy as np
import pytest

from sim.masterpi_drive_friction_v7 import DriveParameters
from sim.v7_exact_speedups import CachedParameters, install


def test_relay_bytes_transitions_and_mutations():
    p = DriveParameters()
    cache = CachedParameters(p)
    rng = np.random.default_rng(49001)
    state = np.zeros(4, dtype=int)
    commands = [np.zeros(4), -np.zeros(4)]
    for threshold in (p.start_fraction, p.kinetic_fraction):
        for value in (np.nextafter(threshold, -np.inf), threshold, np.nextafter(threshold, np.inf)):
            commands.extend([np.full(4, value), np.full(4, -value)])
    commands.extend(rng.uniform(-1, 1, (1000, 4)))
    for u in commands:
        for _ in range(2):
            want = p.command_step(u, state)
            got = cache.command_step(u, state)
            assert all(a.dtype == b.dtype and a.tobytes() == b.tobytes() for a, b in zip(got, want))
            for a in got:
                a[:] = 99
            again = cache.command_step(u, state)
            assert all(a.tobytes() == b.tobytes() for a, b in zip(again, want))
            state = want[1]
    assert cache.cache_info()['currsize'] <= 256
    assert cache.cache_info()['hits'] > 1000


@pytest.mark.parametrize('command,state', [([2., 0, 0, 0], [0]*4), ([float('nan')]*4, [0]*4),
    ([0]*4, [2]*4), ([0]*3, [0]*4)])
def test_original_validation_preserved(command, state):
    p = DriveParameters()
    cache = CachedParameters(p)
    for candidate in (p, cache):
        for _ in range(2):
            with pytest.raises(ValueError):
                candidate.command_step(np.array(command), np.array(state))


def backend(out):
    from sim.final_environment_checks import PhysicsBackend
    b = PhysicsBackend.__new__(PhysicsBackend)
    b.out, b.streams = out, {}
    b.world = SimpleNamespace(drive_parameters=DriveParameters(), physics_lock=nullcontext())
    b.eval_sample = lambda: None
    return b


def test_off_installs_nothing_and_buffered_bytes(tmp_path):
    a, b = backend(tmp_path/'a'), backend(tmp_path/'b')
    original = dict(a.__dict__)
    assert not install(a)['installed']
    assert a.__dict__ == original
    install(b, 'relay-cache-buffered-v1')
    row = {'t': -0., '한국어': [1.25, None, True], 'contacts': []}
    for i in range(5):
        row['contacts'].append({'id': i})
        a._append('contacts.jsonl', row)
        b._append('contacts.jsonl', row)
    b.eval_sample()
    assert (a.out/'contacts.jsonl').read_bytes() == (b.out/'contacts.jsonl').read_bytes()
    for obj in (a, b):
        for stream in obj.streams.values():
            stream.close()
    with pytest.raises(ValueError, match='before reset'):
        install(b, 'relay-cache-v1')


def test_parameter_instances_and_noncontiguous_inputs():
    for p in (DriveParameters(), DriveParameters(start_fraction=.4)):
        cache = CachedParameters(p)
        u = np.array([.35, 9, -.35, 9, .8, 9, -.8, 9])[::2]
        state = np.array([1, 0, -1, 0, 0, 0, 1, 0])[::2]
        assert all(a.tobytes() == b.tobytes() for a, b in zip(p.command_step(u, state), cache.command_step(u, state)))
