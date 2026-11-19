"""Pi-side command server: one laptop client, JSON lines over TCP.

Laptop -> Pi lines:
  {"init_servos": {"1": 2000, ...}, "duration_s": 2.0}
  {"seq": 17, "command": {"t": ..., "wheels": [...], "duration_s": [...], "pwm": {...}}}
  {"stop": "reason"}
Pi -> laptop lines (one per request): {"seq": 17, "status": "applied"|"rejected", "t_recv": ..., "reason"?}

The loop wakes at the next wheel deadline (or every `idle_s`) and writes the stops.
When the client disconnects, every wheel is stopped at once.
"""
from __future__ import annotations

import json
import select
import socket
import time

from .executor import Executor


class Server:
    def __init__(self, executor: Executor, host: str, port: int, clock=time.monotonic, idle_s: float = 0.05):
        self.ex = executor
        self.clock = clock
        self.idle_s = idle_s
        self.listener = socket.create_server((host, port))
        self.listener.setblocking(False)
        self.client = None
        self.buffer = b''
        self.running = True

    @property
    def address(self):
        return self.listener.getsockname()

    def _handle(self, line: bytes) -> dict:
        now = self.clock()
        try:
            msg = json.loads(line)
        except json.JSONDecodeError as exc:
            return {'status': 'rejected', 'reason': f'bad json: {exc}', 't_recv': now}
        if 'command' in msg:
            event = self.ex.apply(int(msg.get('seq', -1)), msg['command'], now)
            reply = {'seq': event['seq'], 'status': event['status'], 't_recv': now}
            if 'reason' in event:
                reply['reason'] = event['reason']
            return reply
        if 'init_servos' in msg:
            try:
                self.ex.initialize_servos(msg['init_servos'], float(msg['duration_s']), now)
                return {'status': 'initialized', 't_recv': now}
            except (ValueError, KeyError, TypeError) as exc:
                return {'status': 'rejected', 'reason': str(exc), 't_recv': now}
        if 'stop' in msg:
            self.ex.stop_all(str(msg['stop']))
            return {'status': 'stopped', 't_recv': now}
        if 'shutdown' in msg:
            self.ex.stop_all('shutdown')
            self.running = False
            return {'status': 'shutdown', 't_recv': now}
        return {'status': 'rejected', 'reason': 'unknown message', 't_recv': now}

    def _drop_client(self, reason: str) -> None:
        if self.client is not None:
            self.client.close()
        self.client, self.buffer = None, b''
        self.ex.stop_all(reason)

    def step(self) -> None:
        now = self.clock()
        deadline = self.ex.next_deadline()
        timeout = self.idle_s if deadline is None else max(0.0, min(self.idle_s, deadline - now))
        sockets = [self.listener] + ([self.client] if self.client else [])
        readable, _, _ = select.select(sockets, [], [], timeout)
        self.ex.poll(self.clock())
        for sock in readable:
            if sock is self.listener:
                conn, _ = self.listener.accept()
                if self.client is not None:
                    conn.close()  # one controller per robot
                    continue
                conn.setsockopt(socket.IPPROTO_TCP, socket.TCP_NODELAY, 1)
                self.client = conn
                continue
            try:
                data = sock.recv(65536)
            except OSError:
                data = b''
            if not data:
                self._drop_client('client disconnected')
                continue
            self.buffer += data
            while b'\n' in self.buffer:
                line, self.buffer = self.buffer.split(b'\n', 1)
                if line.strip():
                    reply = self._handle(line)
                    try:
                        self.client.sendall((json.dumps(reply) + '\n').encode())
                    except OSError:
                        self._drop_client('send failed')
                        break
                    self.ex.poll(self.clock())
                if self.client is None:
                    break

    def serve_forever(self) -> None:
        try:
            while self.running:
                self.step()
        finally:
            self.ex.stop_all('server exit')
            if self.client is not None:
                self.client.close()
            self.listener.close()


class RobotLink:
    """Laptop side: send the same command rows the simulator port receives."""

    def __init__(self, host: str, port: int, timeout_s: float = 2.0):
        self.sock = socket.create_connection((host, port), timeout=timeout_s)
        self.sock.setsockopt(socket.IPPROTO_TCP, socket.TCP_NODELAY, 1)
        self.file = self.sock.makefile('rb')
        self.seq = 0

    def _request(self, msg: dict) -> dict:
        self.sock.sendall((json.dumps(msg) + '\n').encode())
        return json.loads(self.file.readline())

    def init_servos(self, pwm: dict, duration_s: float) -> dict:
        return self._request({'init_servos': pwm, 'duration_s': duration_s})

    def send(self, row: dict) -> dict:
        self.seq += 1
        return self._request({'seq': self.seq, 'command': row})

    def stop(self, reason: str = 'laptop stop') -> dict:
        return self._request({'stop': reason})

    def close(self) -> None:
        self.file.close()  # makefile() holds the socket open until closed too
        self.sock.close()
