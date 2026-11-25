"""Pi -> laptop camera frames with the Pi capture time.

Wire format per frame: 4-byte big-endian header length, JSON header, then the JPEG bytes.
Header: {"frame_id", "t_capture" (Pi monotonic, right after grab), "t_send", "bytes", "width", "height"}.

The laptop keeps only the newest frame (the controller wants the current picture, not a
queue of old ones) and records its own arrival time. Pi and laptop clocks are different:
compare them only through a round trip on one device (see README).
"""
from __future__ import annotations

import json
import socket
import struct
import threading
import time


def encode(header: dict, jpeg: bytes) -> bytes:
    head = json.dumps(header).encode()
    return struct.pack('>I', len(head)) + head + jpeg


def _read_exact(sock, n):
    buf = bytearray()
    while len(buf) < n:
        chunk = sock.recv(n - len(buf))
        if not chunk:
            raise ConnectionError('camera stream closed')
        buf += chunk
    return bytes(buf)


def read_frame(sock):
    (n,) = struct.unpack('>I', _read_exact(sock, 4))
    header = json.loads(_read_exact(sock, n))
    return header, _read_exact(sock, header['bytes'])


class OpenCVSource:
    """640x480 own-camera frames on the Pi (sim contract: own RGB 640x480).

    A background capture thread continuously drains `cap.read()` and keeps only the
    newest `(t_capture, frame)` so `grab()` never returns a stale frame sitting in
    the V4L2 driver ring buffer.
    """

    def __init__(self, index=0, width=640, height=480, quality=70, capture=None):
        import cv2
        self.cv2 = cv2
        if capture is not None:
            self.cap = capture
        else:
            backend = getattr(cv2, 'CAP_V4L2', None)
            self.cap = cv2.VideoCapture(index, backend) if backend is not None else cv2.VideoCapture(index)
            if not self.cap.isOpened() and backend is not None:
                self.cap.release()
                self.cap = cv2.VideoCapture(index)
            if not self.cap.isOpened():
                self.cap.release()
                raise RuntimeError(f'camera index {index} could not be opened')
            self.cap.set(cv2.CAP_PROP_FRAME_WIDTH, width)
            self.cap.set(cv2.CAP_PROP_FRAME_HEIGHT, height)
            self.cap.set(cv2.CAP_PROP_BUFFERSIZE, 1)  # newest frame, not a stale driver queue
        self.quality = quality
        self._cond = threading.Condition()
        self._latest = None
        self._error = None
        self._stop = threading.Event()
        self._thread = threading.Thread(target=self._capture_loop, daemon=True)
        self._thread.start()

    def _capture_loop(self):
        try:
            while not self._stop.is_set():
                ok, frame = self.cap.read()
                t = time.monotonic()
                if not ok:
                    with self._cond:
                        self._error = RuntimeError('camera read failed')
                        self._cond.notify_all()
                    return
                with self._cond:
                    self._latest = (t, frame)
                    self._cond.notify_all()
        except Exception as exc:
            with self._cond:
                self._error = exc
                self._cond.notify_all()

    def grab(self, timeout_s: float = 2.0):
        deadline = time.monotonic() + timeout_s
        with self._cond:
            while self._latest is None and self._error is None and not self._stop.is_set():
                rem = deadline - time.monotonic()
                if rem <= 0.0:
                    raise TimeoutError('timed out waiting for camera frame')
                self._cond.wait(rem)
            if self._error is not None:
                raise self._error
            if self._latest is None:
                raise RuntimeError('camera closed')
            t, frame = self._latest
        ok, jpeg = self.cv2.imencode('.jpg', frame, [self.cv2.IMWRITE_JPEG_QUALITY, self.quality])
        if not ok:
            raise RuntimeError('camera JPEG encode failed')
        return t, jpeg.tobytes(), frame.shape[1], frame.shape[0]

    def close(self):
        self._stop.set()
        with self._cond:
            self._cond.notify_all()
        if self._thread.is_alive():
            self._thread.join(timeout=1.0)
        self.cap.release()


def serve(source, host: str, port: int, period_s: float = 0.1, stop: threading.Event | None = None,
          ready: threading.Event | None = None, address: list | None = None):
    """Send one frame every `period_s` (sim control period 0.1 s) to one client at a time."""
    stop = stop or threading.Event()
    listener = socket.create_server((host, port))
    listener.settimeout(0.2)
    if address is not None:
        address.append(listener.getsockname())
    if ready is not None:
        ready.set()
    frame_id = 0
    try:
        while not stop.is_set():
            try:
                conn, _ = listener.accept()
            except socket.timeout:
                continue
            conn.setsockopt(socket.IPPROTO_TCP, socket.TCP_NODELAY, 1)
            next_t = time.monotonic()
            try:
                while not stop.is_set():
                    t_capture, jpeg, w, h = source.grab()
                    frame_id += 1
                    conn.sendall(encode({'frame_id': frame_id, 't_capture': t_capture, 't_send': time.monotonic(),
                                         'bytes': len(jpeg), 'width': w, 'height': h}, jpeg))
                    now = time.monotonic()
                    next_t = max(next_t + period_s, now)
                    sleep_s = next_t - now
                    if sleep_s > 0.0:
                        time.sleep(sleep_s)
            except OSError:
                pass
            finally:
                conn.close()
    finally:
        listener.close()


class CameraLink:
    """Laptop side: background reader that keeps the newest frame."""

    def __init__(self, host: str, port: int, timeout_s: float = 2.0):
        self.sock = socket.create_connection((host, port), timeout=timeout_s)
        self.sock.settimeout(None)
        self.lock = threading.Lock()
        self.latest = None
        self.received = 0
        self.error = None
        self.thread = threading.Thread(target=self._run, daemon=True)
        self.thread.start()

    def _run(self):
        try:
            while True:
                header, jpeg = read_frame(self.sock)
                header['t_arrival_laptop'] = time.monotonic()
                with self.lock:
                    self.latest = (header, jpeg)
                    self.received += 1
        except (OSError, ConnectionError, ValueError) as exc:
            self.error = str(exc)

    def newest(self):
        with self.lock:
            return self.latest

    def close(self):
        try:
            self.sock.shutdown(socket.SHUT_RDWR)
        except OSError:
            pass
        self.sock.close()
