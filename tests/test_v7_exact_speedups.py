"""No model construction/physics: relay and completed JSON bytes must match."""
from contextlib import nullcontext
from types import SimpleNamespace

import numpy as np
import pytest

pytest.importorskip('mujoco')  # CI excludes native simulation dependencies.

from sim.masterpi_drive_friction_v7 import DriveParameters
from sim.v7_exact_speedups import CachedParameters, configure, write_receipt


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


def test_parameter_instances_and_noncontiguous_inputs():
    for p in (DriveParameters(), DriveParameters(start_fraction=.4)):
        cache = CachedParameters(p)
        u = np.array([.35, 9, -.35, 9, .8, 9, -.8, 9])[::2]
        state = np.array([1, 0, -1, 0, 0, 0, 1, 0])[::2]
        assert all(a.tobytes() == b.tobytes() for a, b in zip(p.command_step(u, state), cache.command_step(u, state)))


def test_defaults_override_receipt_and_result(tmp_path, monkeypatch):
    from scripts.run_final_environment_checks import write
    import hashlib
    import json
    import sim.v7_exact_speedups as speed
    monkeypatch.delenv(speed.ENV, raising=False)
    world = SimpleNamespace(drive_parameters=DriveParameters())
    receipt = configure(world)
    assert receipt['enabled'] and isinstance(world.drive_parameters, CachedParameters)
    assert receipt['module_sha256'] == hashlib.sha256(open(speed.__file__, 'rb').read()).hexdigest()
    backend = SimpleNamespace(world=world, out=tmp_path, bundle={})
    write_receipt(backend)
    original = {'outcome': 'bounded replay'}
    write(tmp_path/'result.json', original)
    assert json.loads((tmp_path/'result.json').read_text()) == {**original, 'runtime_speedups': receipt}
    assert original == {'outcome': 'bounded replay'}
    write(tmp_path/'bundle.json', original)
    assert json.loads((tmp_path/'bundle.json').read_text()) == original
    monkeypatch.setenv(speed.ENV, 'off')
    world = SimpleNamespace(drive_parameters=DriveParameters())
    previous = world.drive_parameters
    assert not configure(world)['enabled'] and world.drive_parameters is previous
    assert configure(world, 'relay-cache-v1')['enabled']
    with pytest.raises(ValueError): configure(world, 'typo')


def test_non_v7_provenance_unchanged(tmp_path):
    from scripts.run_final_environment_checks import write
    write_receipt(SimpleNamespace(world=SimpleNamespace(), out=tmp_path))
    write(tmp_path/'result.json', {'x': 1})
    assert (tmp_path/'result.json').read_bytes() == b'{\n  "x": 1\n}\n'
    assert not (tmp_path/'v7-speedups.json').exists()


def test_shared_build_entry_applies_before_constructor_settle(monkeypatch):
    from sim import masterpi_drive_friction_v7 as v7
    from sim.session_scenes import Scene
    seen = []
    def fake_init(world, **kwargs):
        seen.append(isinstance(world.drive_parameters, CachedParameters))
        world.physical_params, world.calibration_parameters = {}, {}
        world.scene_xml = '<mujoco/>'
    monkeypatch.setattr(v7.MultiMasterPiProductionV2, '__init__', fake_init)
    monkeypatch.delenv('UGRP_V7_EXACT_SPEEDUPS', raising=False)
    scene = Scene.__new__(Scene)
    scene.robot_transform = lambda xml, **kw: xml
    on = v7.build_world(scene, drive_profile=v7.PROFILE)
    off = v7.build_world(scene, drive_profile=v7.PROFILE, exact_speedups='off')
    assert seen == [True, False]
    assert on.v7_speedups_record['enabled'] and not off.v7_speedups_record['enabled']
    assert on.drive_profile_record == off.drive_profile_record
