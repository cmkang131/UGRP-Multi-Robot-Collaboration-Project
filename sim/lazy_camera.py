"""Synchronous, demand-rendered own-camera batches with lossless retention.

Only the capture adapters use this module. No world/model state is copied or
reconstructed. Pending recording frames are materialized before host mutation,
the next capture, or close. Thus a requested historical frame never renders a
newer physics state. The default is the original eager capture order.
"""
from collections.abc import Mapping
from functools import wraps
import base64
import hashlib
import io
import json
import os
from pathlib import Path
import time

ENV = 'UGRP_CAMERA_RENDER'
MODES = ('eager', 'lazy-v1')


class FrameBatch(Mapping):
    def __init__(self, keys, produce, valid):
        self._keys = tuple(keys)
        self._produce, self._valid = produce, valid
        self._values = {}

    def __iter__(self):
        return iter(self._keys)

    def __len__(self):
        return len(self._keys)

    def __contains__(self, key):
        return key in self._keys

    def __getitem__(self, key):
        return self.get_frame(key, 'consumer')

    def get_frame(self, key, reason):
        if key not in self._keys:
            raise KeyError(key)
        if key not in self._values:
            if not self._valid():
                raise RuntimeError('pending camera frame crossed a physics boundary')
            self._values[key] = self._produce(key, reason)
        return self._values[key]

    def retain(self):
        for key in self:
            self.get_frame(key, 'recording')


def flush(host):
    pending = getattr(host, '_lazy_camera_pending', None)
    if pending is not None:
        pending.retain()
        host._lazy_camera_pending = None


def _initialize(host):
    mode = os.environ.get(ENV, 'eager')
    if mode not in MODES:
        raise ValueError(f'unknown {ENV}: {mode}')
    record = dict(schema='ugrp.lazy_camera.v1', mode=mode, batches=0,
                  offered=0, rendered=0, consumer=0, recording=0, eager=0,
                  render_wall_s=0., capture_wall_s=0., skipped=0,
                  retention='all legacy JPEGs and frame-ledger rows',
                  module_sha256=hashlib.sha256(Path(__file__).read_bytes()).hexdigest())
    host._lazy_camera_record = record
    # Bind the most-derived methods, including the integer clock and physical
    # supervisor. Their implementation/order is unchanged after the flush.
    for name in ('issue', 'advance_to', 'reset'):
        original = getattr(host, name)
        def guarded(*args, _original=original, **kwargs):
            flush(host)
            return _original(*args, **kwargs)
        setattr(host, name, wraps(original)(guarded))
    close = host.close
    @wraps(close)
    def finish():
        try:
            flush(host)
        finally:
            try:
                close()
            finally:
                host.out.mkdir(parents=True, exist_ok=True)
                (host.out/'camera-render.json').write_text(json.dumps(record, indent=2)+'\n')
    host.close = finish
    return record


def capture_robot_frames(host, robot_ids):
    """Same port/JPEG/ledger body as S3 and solo capture; lazy per robot.

    Keys/len/membership never render. Reading a value does. All legacy recorded
    frames are mandatory consumers, so skipping requires a separate recording
    contract; this option never silently reduces that contract.
    """
    import numpy as np
    from PIL import Image
    record = getattr(host, '_lazy_camera_record', None)
    if record is None:
        record = _initialize(host)
    flush(host)
    index, captured_at = host.frame, host.now
    keys = tuple(robot_ids)
    if len(set(keys)) != len(keys):
        raise ValueError('duplicate camera owner')
    record['batches'] += 1
    record['offered'] += len(keys)

    def produce(rid, reason):
        started = time.perf_counter()
        obs = host.ports[rid].capture()
        record['render_wall_s'] += time.perf_counter()-started
        jpeg = base64.b64decode(obs['image'], validate=True)
        rgb = np.asarray(Image.open(io.BytesIO(jpeg)).convert('RGB'))
        relative = f'robots/{rid}/rgb/{index:05d}.jpg'
        path = host.out/relative
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(jpeg)
        host._append(f'robots/{rid}/frames.jsonl', {
            **{k: v for k, v in obs.items() if k != 'image'},
            'path': relative, 'commanded_servo': host.commands[rid]})
        record['rendered'] += 1
        record[reason] += 1
        record['capture_wall_s'] += time.perf_counter()-started
        return obs, rgb

    batch = FrameBatch(keys, produce, lambda: host.now == captured_at)
    if record['mode'] == 'eager':
        frames = {rid: batch.get_frame(rid, 'eager') for rid in keys}
    else:
        host._lazy_camera_pending = batch
        frames = batch
    host.frame += 1
    return frames


def install_adapter():
    """Use the same implementation with immutable older experiment adapters.

    The comparison driver records both archive identities and this module hash.
    This is explicit; importing the module never patches a frozen adapter.
    """
    from sim.solo_cyan_v106 import PhysicsBackend as Solo
    from sim.zone_s3_host import PhysicsBackend as Team
    previous = (Solo.capture, Team.capture)
    Solo.capture = lambda self: capture_robot_frames(self, (self.bundle['task']['robot_id'],))
    Team.capture = lambda self: capture_robot_frames(self, ('r1', 'r2', 'r3'))
    def undo():
        Solo.capture, Team.capture = previous
    return undo
