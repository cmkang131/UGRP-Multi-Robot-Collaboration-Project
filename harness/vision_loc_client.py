"""Owned subprocess client of the vision localization worker (keeps torch out of the MuJoCo process).

Same pattern as ``harness/recovery_act_client.py`` / ``harness/carry_input_client.py`` (JSON lines on
stdin/stdout, selector-bounded reads, terminate -> kill on close), plus what a closed loop needs:

* writes are bounded too (non-blocking pipe + deadline), so a hung worker cannot block the SIM;
* every failure (timeout, exit, broken pipe, malformed reply) kills the worker and raises
  ``WorkerFailure``; the client never restarts it (the pose provider fails closed for the episode);
* the worker exits on stdin EOF, so a killed parent leaves no orphan; ``close`` is idempotent and is
  also registered with ``atexit``.

``InProcessWorker`` is the torch-free stand-in with the same ``observe`` / ``close`` / ``record``
interface (CI and tests): observations come from a caller-supplied function.
"""
from __future__ import annotations

import atexit
import json
import os
import selectors
import subprocess
import time
from pathlib import Path

from harness import vision_loc_protocol as vp
from harness.recovery_act_client import interpreter_path


class WorkerFailure(RuntimeError):
    """The worker cannot answer any more (timeout, exit, broken pipe, protocol error)."""


class FrameRejected(ValueError):
    """The worker answered, but refused this one frame (the provider skips its measurement)."""


class VisionWorkerClient:
    def __init__(self, cfg=None, *, argv=None, cwd=None):
        self.cfg = vp.load_config() if cfg is None else cfg
        python = os.environ.get('UGRP_VISION_WORKER_PYTHON', self.cfg['python'])
        self.argv = list(argv) if argv is not None else [
            str(interpreter_path(Path(python))), str(vp.ROOT / 'scripts' / 'vision_loc_worker.py'),
            '--config', str(vp.CONFIG_FILE)]
        self.frame_timeout_s = float(self.cfg['frame_timeout_s'])
        self.seq = 0
        self.failure: str | None = None
        self.calls: list[dict] = []
        self._buf = b''
        env = {**os.environ, 'OMP_NUM_THREADS': '1', 'OPENBLAS_NUM_THREADS': '1', 'VECLIB_MAXIMUM_THREADS': '1',
               'MKL_NUM_THREADS': '1'}
        t0 = time.perf_counter()
        self.process = subprocess.Popen(self.argv, cwd=cwd or vp.ROOT, stdin=subprocess.PIPE, stdout=subprocess.PIPE,
                                        env=env, bufsize=0)
        os.set_blocking(self.process.stdin.fileno(), False)
        self.selector = selectors.DefaultSelector()
        self.selector.register(self.process.stdout, selectors.EVENT_READ)
        self._closed = False
        atexit.register(self.close)
        try:
            self.ready = vp.check_ready(self._read(time.monotonic() + float(self.cfg['startup_timeout_s'])), self.cfg)
        except BaseException as exc:
            self._fail(f'startup: {type(exc).__name__}: {exc}')
            self.close()
            raise WorkerFailure(self.failure) from exc
        self.startup_s = round(time.perf_counter() - t0, 3)

    @property
    def pid(self) -> int:
        return self.process.pid

    def _fail(self, reason: str):
        if self.failure is None:
            self.failure = reason[:500]
        if self.process.poll() is None:
            try:
                self.process.kill()
            except ProcessLookupError:
                pass

    def _write(self, data: bytes, deadline: float):
        fd = self.process.stdin.fileno()
        view = memoryview(data)
        with selectors.DefaultSelector() as sel:
            sel.register(fd, selectors.EVENT_WRITE)
            while view:
                left = deadline - time.monotonic()
                if left <= 0 or not sel.select(timeout=left):
                    raise TimeoutError('worker did not take the request in time')
                try:
                    n = os.write(fd, view)
                except BlockingIOError:
                    continue
                view = view[n:]

    def _read(self, deadline: float):
        while b'\n' not in self._buf:
            left = deadline - time.monotonic()
            if left <= 0 or not self.selector.select(timeout=left):
                raise TimeoutError('worker reply timed out')
            chunk = os.read(self.process.stdout.fileno(), 1 << 16)
            if not chunk:
                raise EOFError(f'worker exited (code {self.process.poll()}) without a reply')
            self._buf += chunk
        line, self._buf = self._buf.split(b'\n', 1)
        reply = json.loads(line)
        if isinstance(reply, dict) and 'error' in reply:
            raise vp.ProtocolError(f'worker error: {reply["error"]}')
        return reply

    def observe(self, bgr):
        """ColumnObs of one own frame. ``FrameRejected`` for a refused frame, ``WorkerFailure`` otherwise."""
        if self.failure is not None:
            raise WorkerFailure(self.failure)
        payload, digest = vp.encode_request(self.seq, bgr)  # ProtocolError for a bad frame: nothing is sent
        seq, self.seq = self.seq, self.seq + 1
        t0 = time.perf_counter()
        try:
            deadline = time.monotonic() + self.frame_timeout_s
            self._write(payload.encode(), deadline)
            kind, value, infer_ms = vp.check_reply(self._read(deadline), seq=seq, bgr_sha256=digest,
                                                   n_columns=len(vp.columns()))
        except (TimeoutError, EOFError, OSError, ValueError) as exc:  # OSError: broken pipe; ValueError: JSON/protocol
            self._fail(f'frame {seq}: {type(exc).__name__}: {exc}')
            raise WorkerFailure(self.failure) from exc
        self.calls.append({'seq': seq, 'bgr_sha256': digest, 'kind': kind,
                           'round_trip_ms': round(1000. * (time.perf_counter() - t0), 3), 'infer_ms': infer_ms,
                           'obs_sha256': None if kind != 'obs' else vp.sha256_bytes(vp.canonical(value.as_dict()))})
        if kind == 'rejected':
            raise FrameRejected(value)
        return value

    def record(self) -> dict:
        return {'kind': 'subprocess', 'argv': self.argv, 'pid': self.process.pid, 'ready': getattr(self, 'ready', None),
                'startup_s': getattr(self, 'startup_s', None), 'failure': self.failure, 'calls': len(self.calls),
                'returncode': self.process.poll()}

    def close(self):
        if self._closed:
            return
        self._closed = True
        atexit.unregister(self.close)
        if self.process.poll() is None:
            try:
                self.process.stdin.close()                 # EOF: the worker ends its loop
                self.process.wait(timeout=5)
            except (subprocess.TimeoutExpired, OSError):
                self.process.terminate()
                try:
                    self.process.wait(timeout=5)
                except subprocess.TimeoutExpired:
                    self.process.kill()
                    self.process.wait(timeout=5)
        self.selector.close()
        for f in (self.process.stdin, self.process.stdout):
            try:
                f.close()
            except OSError:
                pass


class InProcessWorker:
    """Torch-free worker stand-in: ``fn(seq, bgr) -> ColumnObs | None`` (None = the frame is refused).

    ``fail_at`` makes the given request number raise ``WorkerFailure`` (a crash or timeout of the real
    worker); later requests keep failing, as with the real client.
    """

    def __init__(self, fn, *, fail_at: int | None = None):
        self.fn, self.fail_at, self.seq, self.failure, self.calls = fn, fail_at, 0, None, []
        self.closed = False

    def observe(self, bgr):
        if self.failure is not None:
            raise WorkerFailure(self.failure)
        vp.check_frame(bgr)
        seq, self.seq = self.seq, self.seq + 1
        if self.fail_at is not None and seq >= self.fail_at:
            self.failure = f'frame {seq}: injected worker failure'
            raise WorkerFailure(self.failure)
        obs = self.fn(seq, bgr)
        self.calls.append({'seq': seq, 'kind': 'rejected' if obs is None else 'obs'})
        if obs is None:
            raise FrameRejected('injected rejection')
        return obs

    def record(self) -> dict:
        return {'kind': 'in_process_fake', 'failure': self.failure, 'calls': len(self.calls)}

    def close(self):
        self.closed = True
