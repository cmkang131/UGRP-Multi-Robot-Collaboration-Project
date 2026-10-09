"""Opt-in exact memoization of the v7 input relay; original arithmetic retained.

No mj_step/mj_forward, clock, control, physics, or camera changes. The cache is
per immutable DriveParameters instance, keyed by complete array bytes, dtype and
shape. Returned arrays are copied, so caller mutation cannot poison the cache.
The default ``off`` installs nothing. Existing runners never enable this module.
"""
from functools import lru_cache
from types import MethodType
import json

import numpy as np

MODES = ('off', 'relay-cache-v1', 'relay-cache-buffered-v1')


class CachedParameters:
    def __init__(self, original):
        from sim.masterpi_drive_friction_v7 import DriveParameters
        if type(original) is not DriveParameters:
            raise TypeError('exact cache requires the frozen v7 DriveParameters')
        self.original = original

        @lru_cache(maxsize=256)
        def calculate(command, state):
            def restore(key):
                dtype, shape, data = key
                return np.frombuffer(data, dtype=np.dtype(dtype)).reshape(shape)
            return original.command_step(restore(command), restore(state))
        self._calculate = calculate

    def __getattr__(self, name):
        return getattr(self.original, name)

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


def _buffered_append(self, relative, value):
    if relative not in self.streams:
        path = self.out / relative
        path.parent.mkdir(parents=True, exist_ok=True)
        self.streams[relative] = path.open('x', buffering=65536)
    # Serialize now, never queue mutable dictionaries/array views.
    self.streams[relative].write(json.dumps(value, ensure_ascii=False, allow_nan=False) + '\n')


def install(backend, mode='off'):
    """Call once after backend construction, before reset; return a receipt.

    Buffered mode flushes each completed eval_sample (one host frame), and the
    backend's existing close() closes every stream on normal/error shutdown.
    Abrupt termination may lose the current buffered frame; it stays opt-in.
    Contact rows/fields and JSON formatting are never reduced in this module.
    """
    if mode not in MODES:
        raise ValueError(f'unknown speedup mode: {mode}')
    if mode == 'off':
        return {'mode': mode, 'installed': False}
    if backend.streams:
        raise ValueError('install speedups before reset or any log writes')
    if hasattr(backend, '_v7_exact_speedups'):
        raise ValueError('speedups already installed')
    world = backend.world
    cached = CachedParameters(world.drive_parameters)
    with world.physics_lock:
        world.drive_parameters = cached
    if mode == 'relay-cache-buffered-v1':
        backend._append = MethodType(_buffered_append, backend)
        original_eval = backend.eval_sample

        def eval_sample():
            try:
                return original_eval()
            finally:
                for stream in backend.streams.values():
                    stream.flush()
        backend.eval_sample = eval_sample
    backend._v7_exact_speedups = cached
    return {'mode': mode, 'installed': True, 'cache_maxsize': 256,
            'physics_changed': False, 'log_fields_changed': False}
