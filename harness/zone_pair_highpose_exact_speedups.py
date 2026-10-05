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

``v98-exact-v2`` = v1 + ``render_pipeline`` (CANDIDATE: adopt only after a full-run byte comparison)
    The host captures r1 then r2 (render on the GL owner thread, JPEG, files, logs) and only then runs
    the controllers (r1 then r2); the main thread idles while each camera renders. Here r1 is captured
    exactly as before, the r2 render is queued on the same GL thread right after r1's render returns,
    and r2's post-processing (the original per-robot body, unchanged) runs when the runtime first reads
    ``frames['r2']`` - after r1's controller update. Nothing between those points touches the world,
    the ports or the backend command state (the controllers only read their own frame), so the r2
    render sees the same physics state, the same GL calls run in the same order on the same context,
    and each output file receives the same rows in the same order. Only the interleaving of writes to
    DIFFERENT files changes. A pending r2 is completed before any later backend call.

``v98-exact-v3`` = v1 + ``pf_geometry_shared`` (CANDIDATE: adopt only after a full-run byte comparison)
    ``vision_loc.expected_rows`` replaced by the bit-identical rewrite in
    ``harness.zone_pair_highpose_pf_geometry_shared`` (shared bottom/top trace work, subset corner times);
    refused unless the frozen functions' source hashes to the recorded value. Offline: ~45 % less time per
    P=2000 call, 110 inputs and a 400-frame replay byte-equal.

``v98-exact-v4`` = v1 + ``render_pipeline`` + ``pf_geometry_shared`` (the v2 and v3 candidates together, one run)

``v98-exact-v5`` = v4 + ``opencv_exact`` (CANDIDATE): ``harness.zone_pair_highpose_opencv_exact`` caches the
    image-independent part of the frozen ``detect_boundaries`` per camera model, gathers window sums by flat
    index, and returns the previous ``ColumnObs`` for a byte-identical repeated frame. Offline: 215 recorded
    frame x camera-model pairs bit-equal, 12.2 -> 9.0 ms per detection.

``v98-exact-v6`` = v1 + ``pf_geometry_shared`` + ``opencv_exact`` (no ``render_pipeline``): the set for research runs
    (coordinator 2026-10-05: render_pipeline off, its GIL contention makes the gain doubtful). v1 is full-run
    byte-identical to ``none`` (align_to_carry s911, 382.65 SIM s); the two added items are proven offline
    (recorded inputs and a 400-frame replay byte-equal).
"""
from __future__ import annotations

import functools

import numpy as np

SETS = {'none': (), 'v98-exact-v1': ('expected_memo', 'drive_kernel', 'schedule_memo'),
        'v98-exact-v2': ('expected_memo', 'drive_kernel', 'schedule_memo', 'render_pipeline'),
        'v98-exact-v3': ('expected_memo', 'drive_kernel', 'schedule_memo', 'pf_geometry_shared'),
        'v98-exact-v4': ('expected_memo', 'drive_kernel', 'schedule_memo', 'render_pipeline', 'pf_geometry_shared'),
        'v98-exact-v5': ('expected_memo', 'drive_kernel', 'schedule_memo', 'render_pipeline', 'pf_geometry_shared',
                         'opencv_exact'),
        'v98-exact-v6': ('expected_memo', 'drive_kernel', 'schedule_memo', 'pf_geometry_shared', 'opencv_exact')}
VERSION = 'ugrp.v98_exact_speedups.v1'
# sha256 of inspect.getsource(sim.final_pair_v3.PhysicsBackend.capture) whose per-robot body render_pipeline copies
CAPTURE_SOURCE_SHA256 = 'fd76fe25a67bd1a9dc1c2cf80eee900a6912bc85fc0b0fd1e01a8882cf1d0cad'


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

    if 'render_pipeline' in items:
        undo.append(_install_render_pipeline(record))
    if 'pf_geometry_shared' in items:
        from harness import zone_pair_highpose_pf_geometry_shared as geometry
        undo.append(geometry.install(record))
    if 'opencv_exact' in items:
        from harness import zone_pair_highpose_opencv_exact as opencv_exact
        undo.append(opencv_exact.install(record))

    def uninstall():
        while undo:
            undo.pop()()
    return record, uninstall


DEFAULT_SET = 'v98-exact-v6'
SIDECAR = 'speedups.json'


class RunSpeedups:
    """A runner's ``--speedups`` choice, installed late and undone at the end.

    ``start()`` is called by the runner right before the simulation is built (after every argument, source, slot and
    output check, so those refusals need no simulator). ``finish(rc)`` undoes the set and writes
    ``<output>/speedups.json`` (run root, never a case directory) when ``start()`` ran and created the output.
    """

    def __init__(self, name, output):
        self.name, self.output, self.record, self.undo, self.existed = name, output, None, None, None

    def start(self):
        from pathlib import Path
        if self.undo is None:
            self.existed = Path(self.output).exists()
            self.record, self.undo = install(self.name)

    def finish(self, rc=None):
        import json
        from pathlib import Path
        if self.undo is None:
            return
        undo, self.undo = self.undo, None
        undo()
        out = Path(self.output)
        if out.is_dir() and not self.existed:
            (out / SIDECAR).write_text(json.dumps({'schema': 'ugrp.run_speedups.v1', 'speedups': summary(self.record),
                                                   'runner_rc': rc}, indent=1) + '\n')


def summary(record):
    """JSON-safe counters (memo hits/misses per provider) for a sidecar or manifest."""
    out = {k: v for k, v in record.items() if k not in ('expected_memo', 'opencv_exact')}
    if 'expected_memo' in record:
        out['expected_memo'] = [{'hits': m.hits, 'misses': m.misses} for m in record['expected_memo']]
    if 'opencv_exact' in record:
        ox = record['opencv_exact']
        out['opencv_exact'] = {k: v for k, v in ox.items() if k not in ('cache', 'memo')}
        for k in ('cache', 'memo'):
            if k in ox:
                out['opencv_exact'][k] = {'hits': ox[k].hits, 'misses': ox[k].misses}
    return out


class _PipelinedFrames(dict):
    """capture() result whose second robot entry is completed on first read."""

    def __init__(self, first, finish):
        super().__init__(first)
        self._finish = finish

    def _complete(self):
        if self._finish is not None:
            finish, self._finish = self._finish, None
            dict.update(self, finish())

    def __getitem__(self, key):
        if key not in self.keys():
            self._complete()
        return dict.__getitem__(self, key)

    def __iter__(self):
        self._complete()
        return dict.__iter__(self)

    def items(self):
        self._complete()
        return dict.items(self)

    def values(self):
        self._complete()
        return dict.values(self)


def _install_render_pipeline(record):
    import base64
    import io
    from sim import final_pair_v3
    from sim.multi_masterpi_production import MultiMasterPiProductionV2
    from harness import zone_final_pair_contract as contract
    backend_cls, world_cls = final_pair_v3.PhysicsBackend, MultiMasterPiProductionV2
    capture0, render_for0 = backend_cls.capture, world_cls._render_rgb_for
    stats = record.setdefault('render_pipeline', {'prefetched': 0, 'completed_late': 0, 'forced': 0})

    def _render_rgb_for(world, robot, camera):
        pending = getattr(world, '_v98_prefetch', None)
        if pending is not None and pending[0] is robot and pending[1] == camera:
            world._v98_prefetch = None
            return pending[2].result(timeout=30.0)
        if pending is not None:
            raise RuntimeError('render_pipeline: unexpected render while a prefetch is pending')
        return render_for0(world, robot, camera)

    def one(backend, rid):
        """The original per-robot body of sim.final_pair_v3.PhysicsBackend.capture (verbatim order)."""
        import numpy as np
        from PIL import Image
        obs = backend.ports[rid].capture()
        jpeg = base64.b64decode(obs['image'], validate=True)
        rgb = np.asarray(Image.open(io.BytesIO(jpeg)).convert('RGB'))
        relative = f'robots/{rid}/rgb/{backend.frame:05d}.jpg'
        path = backend.out / relative
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(jpeg)
        backend._append(f'robots/{rid}/frames.jsonl', {**{k: v for k, v in obs.items() if k != 'image'},
                        'path': relative, 'commanded_servo': backend.commands[rid]})
        base = backend.world.data.body(rid+'__robot')
        cam = backend.world.data.camera(rid+'__robot_cam')
        rb = np.asarray(base.xmat).reshape(3, 3)
        from harness.zone_final_pair_camera import measurement_label
        label = measurement_label(base.xpos, rb, cam.xpos, np.asarray(cam.xmat).reshape(3, 3))
        backend._append(f'eval_only/{rid}/camera_labels.jsonl', {
            't': backend.now, 'frame_id': obs['frame_id'], 'sha256': obs['sha256'],
            'commanded_servo': backend.commands[rid], **label, 'base_position_m': base.xpos.tolist(),
            'base_rotation': rb.tolist(), 'requested_check': backend.bundle['check'],
            'load_validity': 'UNCLASSIFIED; inspect contacts and beam trajectory offline'})
        return obs, rgb

    def capture(backend):
        robots = tuple(contract.ROBOTS)
        world = backend.world
        executor = getattr(world, '_render_executor', None)
        if len(robots) != 2 or executor is None:
            return capture0(backend)
        _flush(backend)
        first, second = robots
        world_robot = world.robot(second)

        result = {first: one(backend, first)}
        # r1's render has returned; queue r2's render on the GL owner thread (same order as before).
        world._v98_prefetch = (world_robot, 'robot_cam',
                               executor.submit(world._render_rgb_direct, world_robot, 'robot_cam'))
        stats['prefetched'] += 1
        frame = backend.frame

        def finish():
            if backend.frame != frame:
                raise RuntimeError('render_pipeline: frame counter moved before completion')
            out = {second: one(backend, second)}
            backend.frame += 1
            backend._v98_pending = None
            stats['completed_late'] += 1
            return out
        frames = _PipelinedFrames(result, finish)
        backend._v98_pending = frames
        return frames

    def _flush(backend):
        pending = getattr(backend, '_v98_pending', None)
        if pending is not None:
            stats['forced'] += 1
            pending._complete()

    import hashlib
    import inspect
    source = hashlib.sha256(inspect.getsource(capture0).encode()).hexdigest()
    if source != CAPTURE_SOURCE_SHA256:
        stats['installed'] = False
        stats['refused'] = f'sim.final_pair_v3.PhysicsBackend.capture source {source[:12]} differs from the copied body'
        return lambda: None
    stats['installed'] = True
    owners = [backend_cls]
    try:
        from sim.final_pair_highpose_clock import IntegerClock
        owners.insert(0, IntegerClock)
    except ImportError:
        pass
    for base in backend_cls.__mro__[1:]:
        if base is not object:
            owners.append(base)
    patched = [(world_cls, '_render_rgb_for', render_for0)]
    world_cls._render_rgb_for = _render_rgb_for
    for owner in owners:
        for name in ('advance_to', 'issue', 'eval_sample', 'close', 'reset'):
            if name not in vars(owner):
                continue
            original = vars(owner)[name]

            def method(backend, *args, _original=original, _name=name, **kwargs):
                if _name == 'close':     # error path: complete best-effort, never block the cleanup
                    try:
                        _flush(backend)
                    except Exception:    # noqa: BLE001 - the original error is already being reported
                        pass
                else:
                    _flush(backend)      # a pending r2 is always completed before any later backend call
                return _original(backend, *args, **kwargs)
            method.__wrapped__ = original
            patched.append((owner, name, original))
            setattr(owner, name, method)
    patched.append((backend_cls, 'capture', capture0))
    backend_cls.capture = capture

    def uninstall():
        for owner, name, value in reversed(patched):
            setattr(owner, name, value)
    return uninstall
