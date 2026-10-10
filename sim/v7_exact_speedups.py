"""Exact memoization of the v7 input relay; original arithmetic retained.

No mj_step/mj_forward, clock, control, physics, or camera changes. The cache is
per immutable DriveParameters instance, keyed by complete array bytes, dtype and
shape. Returned arrays are copied, so caller mutation cannot poison the cache.
New worlds default to relay-cache-v1; UGRP_V7_EXACT_SPEEDUPS=off restores
the original relay. No logging durability or physics pipeline changes.
"""
from functools import lru_cache
import hashlib
import os
from pathlib import Path

import numpy as np

MODES = ('off', 'relay-cache-v1')
ENV = 'UGRP_V7_EXACT_SPEEDUPS'
DEFAULT = 'relay-cache-v1'


class CachedParameters:
    def __init__(self, original):
        from sim.masterpi_drive_friction_v7 import DriveParameters
        if type(original) is not DriveParameters:
            raise TypeError('exact cache requires the frozen v7 DriveParameters')
        self.original = original
        # Frozen parameter: avoid __getattr__ on every wheel torque assignment.
        self.torque_cap_nm = original.torque_cap_nm

        @lru_cache(maxsize=256)
        def calculate(command, state):
            def restore(key):
                dtype, shape, data = key
                return np.frombuffer(data, dtype=np.dtype(dtype)).reshape(shape)
            return original.command_step(restore(command), restore(state))
        self._calculate = calculate

    def __getattr__(self, name):
        return getattr(self.original, name)

    def __reduce__(self):
        # lru_cache's local closure is not serializable. Its values are pure
        # memoized original arithmetic, so reconstruct an empty cache; wheel
        # direction/physical state are owned and saved by the world, not here.
        return type(self), (self.original,)

    def command_step(self, command, previous_direction):
        # Preserve the original validation/conversion for noncanonical inputs.
        arrays = (command, previous_direction)
        if any(type(a) is not np.ndarray or a.shape != (4,) or a.dtype.kind not in 'fiu'
               for a in arrays):
            return self.original.command_step(command, previous_direction)
        keys = tuple((a.dtype.str, a.shape, a.tobytes()) for a in arrays)
        return tuple(a.copy() for a in self._calculate(*keys))

    def cache_info(self):
        return self._calculate.cache_info()._asdict()


def configure(world, mode=None):
    """The v7 build_world entry calls this once, before constructor settling."""
    mode = os.environ.get(ENV, DEFAULT) if mode is None else mode
    if mode not in MODES:
        raise ValueError(f'{ENV} must be one of {MODES}, got {mode!r}')
    from sim.masterpi_drive_friction_v7 import DriveParameters
    supported = type(world.drive_parameters) is DriveParameters
    enabled = mode != 'off' and supported
    if enabled:
        world.drive_parameters = CachedParameters(world.drive_parameters)
    world.v7_speedups_record = {
        'schema': 'ugrp.v7_exact_speedups.v1', 'mode': mode, 'enabled': enabled,
        'fallback': None if supported else 'custom_parameters_not_cached',
        'module_sha256': hashlib.sha256(Path(__file__).read_bytes()).hexdigest(),
        'cache_maxsize': 256 if enabled else 0,
        'physics_changed': False, 'log_buffering': False,
    }
    return dict(world.v7_speedups_record)


def write_receipt(backend):
    """Keep the physics profile/bundle bytes intact; separate runtime provenance."""
    receipt = getattr(backend.world, 'v7_speedups_record', None)
    if receipt is not None:
        from scripts.run_final_environment_checks import write
        write(backend.out / 'v7-speedups.json', receipt)
        # A runtime bundle works for legacy writers too, without rewriting their
        # sealed input bundle or requiring per-runner activation.
        import json
        bundle = backend.bundle
        write(backend.out / 'runtime-bundle.json', {
            'schema': 'ugrp.v7_runtime_bundle.v1',
            'execution_bundle_id': bundle.get('execution_bundle_id'),
            'source_sha': bundle.get('source_sha'),
            'input_bundle_sha256': hashlib.sha256(json.dumps(bundle, sort_keys=True).encode()).hexdigest(),
            'runtime_speedups': receipt})


def result_record(path, value):
    """Attach actual-world provenance to host results, never to sealed bundles."""
    receipt_path = path.parent / 'v7-speedups.json'
    if path.name == 'result.json' and isinstance(value, dict) and receipt_path.is_file():
        import json
        return {**value, 'runtime_speedups': json.loads(receipt_path.read_text())}
    return value
