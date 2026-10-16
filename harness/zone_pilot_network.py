"""Fail-closed Python network boundary for the single-threaded adapter pilot.

This is an accidental-bypass guard, not a sandbox against hostile native code.
Only the ledger wire can grant one connect/send capability, for a numeric
loopback proxy endpoint. Direct sockets, other openers and child processes
outside that capability fail before I/O. HTTP redirects are separately refused.
"""
from __future__ import annotations

from contextlib import contextmanager
import socket
import sys
import threading
from urllib.parse import urlsplit

_ACTIVE = None
_INSTALLED = False


def proxy_address(url):
    parsed = urlsplit(url)
    if (parsed.scheme != 'http' or parsed.hostname != '127.0.0.1' or not parsed.port
            or parsed.username or parsed.password or parsed.query or parsed.fragment
            or parsed.path != '/v1/chat/completions'):
        raise ValueError('pilot URL must be http://127.0.0.1:PORT/v1/chat/completions')
    return parsed.hostname, parsed.port


def _audit(event, args):
    guard = _ACTIVE
    if guard is None:
        return
    if event in ('socket.connect', 'socket.getaddrinfo', 'socket.sendto', 'socket.sendmsg'):
        guard.assert_wire()
        if event == 'socket.connect':
            if tuple(args[1]) != guard.address or guard.connected:
                raise RuntimeError('pilot network: unapproved endpoint or second connection')
            guard.connected = True
        elif event == 'socket.getaddrinfo' and tuple(args[:2]) != guard.address:
            raise RuntimeError('pilot network: unapproved resolver request')
        elif event in ('socket.sendto', 'socket.sendmsg'):
            raise RuntimeError('pilot network: datagram path forbidden')
    elif event in ('subprocess.Popen', 'os.system', 'os.exec', 'os.posix_spawn'):
        raise RuntimeError('pilot network: subprocess escape forbidden')


class NetworkFence:
    def __init__(self, url=None):
        self.address = proxy_address(url) if url is not None else None
        self.thread = threading.get_ident()
        self.depth = 0
        self.allowed = False
        self.connected = False

    def assert_thread(self):
        if threading.get_ident() != self.thread:
            raise RuntimeError('single-thread pilot transport required')

    def assert_wire(self):
        self.assert_thread()
        if _ACTIVE is not self or not self.allowed:
            raise RuntimeError('pilot network: only the ledger wire may send')

    def __enter__(self):
        global _ACTIVE, _INSTALLED
        self.assert_thread()
        if _ACTIVE is not None and _ACTIVE is not self:
            raise RuntimeError('another pilot network fence is active')
        if not _INSTALLED:
            sys.addaudithook(_audit)
            _INSTALLED = True
        if self.depth == 0:
            self.originals = {}
            # Python has no audit event for TCP send on an already-open socket.
            for name in ('send', 'sendall'):
                original = getattr(socket.socket, name)
                self.originals[name] = original

                def guarded(sock, *args, _original=original, **kwargs):
                    self.assert_wire()
                    if tuple(sock.getpeername()) != self.address:
                        raise RuntimeError('pilot network: unapproved connected socket')
                    return _original(sock, *args, **kwargs)

                setattr(socket.socket, name, guarded)
        self.depth += 1
        _ACTIVE = self
        return self

    def __exit__(self, *exc):
        global _ACTIVE
        self.depth -= 1
        if not self.depth:
            for name, method in self.originals.items():
                setattr(socket.socket, name, method)
            _ACTIVE = None

    @contextmanager
    def wire(self):
        self.assert_thread()
        if _ACTIVE is not self or self.allowed or self.address is None:
            raise RuntimeError('pilot wire requires its active exclusive network fence')
        self.allowed, self.connected = True, False
        try:
            yield
        finally:
            self.allowed = False
