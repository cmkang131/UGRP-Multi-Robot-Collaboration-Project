"""Bit-exact wall-time cuts for the v98 pair HIGH-carry host (opt-in, default off; no behaviour change).

Same contract as sim.exact_speedups (PR #209): every item returns the same IEEE-754 values in the
same order as the original path, so commands, frames, events and records are byte-identical. Nothing
touches the physics model, timestep, solver, contacts, cameras, renderer, control or frame rates, the
PF, its random stream or any frozen file. A set is chosen by name; 'none' is the original path.

``v98-exact-v1``

``expected_memo``
    One frame's PF scan update evaluates the expected wall rows of the SAME particle array twice:
    ``harness.zone_final_pair_scan.quality`` (the v3 informative receipt) calls ``pf.expected(pf.px, pose)``
    and then the wrapped ``apply_scan -> scan_loglik`` calls ``self.expected(self.px, pose)`` again with
    unchanged particles, servo pose and load state (cProfile 2026-10-05: 2 x ~23% of the probe wall).
    The second call returns copies of the first result. The cache holds one entry, only for the
    filter's own ``pf.px`` array, keyed by the exact particle bytes/shape/dtype, the servo pose, the
    load state and the column positions; any change misses and recomputes. Small curvature-probe calls
    (other arrays) are never cached. ``expected_rows`` is a pure function of these inputs (static map
    geometry and camera calibration are fixed per provider).

``drive_kernel``
    ``sim.exact_speedups.install_drive_kernel`` on the v98 world (np.dot-ordered scalar drive arithmetic;
    self-checked, falls back to the original path when the BLAS order differs). Proven bit-identical on
    the M1 and pair runners (experiments/2026-09-26-sim-speed).

``schedule_memo``
    ``harness.zone_final_pair_loaded_schedule.schedule_bytes`` is a pure function (no arguments) that the
    calibration admission recomputes three times at start-up (~6 s each under load). Later calls
    return the same ``bytes`` object.
"""
from __future__ import annotations

import functools

import numpy as np

SETS = {'none': (), 'v98-exact-v1': ('expected_memo', 'drive_kernel', 'schedule_memo')}
VERSION = 'ugrp.v98_exact_speedups.v1'


def resolve(name):
    name = 'none' if name in (None, '') else str(name)
    if name not in SETS:
        raise ValueError(f'unknown v98 speedup set {name!r}; known: {sorted(SETS)}')
    return name, SETS[name]


class ExpectedMemo:
    """One-entry exact cache of ``pf.expected(pf.px, pose)`` (instance attribute, original kept)."""

    def __init__(self, pf):
        self.pf, self.original = pf, pf.expected
        self.key = self.value = None
        self.hits = self.misses = 0

    def _key(self, px, pose):
        px = np.asarray(px)
        load = getattr(getattr(self.pf, 'load', None), 'loaded', None)
        columns = getattr(self.pf, 'columns', None)
        return (px.shape, px.dtype.str, px.tobytes(), tuple(sorted(dict(pose).items())), bool(load),
                None if columns is None else np.asarray(columns).tobytes())

    def __call__(self, px, pose):
        if px is not self.pf.px:
            return self.original(px, pose)
        key = self._key(px, pose)
        if key == self.key:
            self.hits += 1
        else:
            self.misses += 1
            self.key, self.value = None, None
            value = self.original(px, pose)
            self.key, self.value = key, tuple(np.array(v, copy=True) for v in value)
        return tuple(np.array(v, copy=True) for v in self.value)


def install(name, record=None):
    """Install a set for this process; returns (record, uninstall). Call before the backend/runtime are built."""
    name, items = resolve(name)
    record = {} if record is None else record
    record.update({'schema': VERSION, 'set': name, 'items': list(items), 'note':
                   'execution infrastructure only; same commands/frames/events (harness.zone_pair_highpose_exact_speedups)'})
    undo = []
    if 'expected_memo' in items:
        from harness import vision_pose_source_highpose as src
        cls, init = src.HighPoseSource, src.HighPoseSource.__init__
        memos = record.setdefault('expected_memo', [])

        @functools.wraps(init)
        def __init__(self, *args, **kwargs):
            init(self, *args, **kwargs)
            pf = self.loc._pf
            memo = ExpectedMemo(pf)
            pf.expected = memo
            memos.append(memo)
        cls.__init__ = __init__
        undo.append(lambda: setattr(cls, '__init__', init))
    if 'drive_kernel' in items:
        from sim import zone_final_v3_scene as scene
        from sim.exact_speedups import install_drive_kernel
        build = scene.build_world
        kernels = record.setdefault('drive_kernel', [])

        @functools.wraps(build)
        def build_world(*args, **kwargs):
            world = build(*args, **kwargs)
            kernels.append(install_drive_kernel(world))
            return world
        scene.build_world = build_world
        undo.append(lambda: setattr(scene, 'build_world', build))
    if 'schedule_memo' in items:
        from harness import zone_final_pair_loaded_schedule as sched
        original = sched.schedule_bytes
        cached = functools.lru_cache(maxsize=1)(original)
        sched.schedule_bytes = cached
        undo.append(lambda: setattr(sched, 'schedule_bytes', original))
        record['schedule_memo'] = True

    def uninstall():
        while undo:
            undo.pop()()
    return record, uninstall


def summary(record):
    """JSON-safe counters (memo hits/misses per provider) for a sidecar or manifest."""
    out = {k: v for k, v in record.items() if k != 'expected_memo'}
    if 'expected_memo' in record:
        out['expected_memo'] = [{'hits': m.hits, 'misses': m.misses} for m in record['expected_memo']]
    return out
