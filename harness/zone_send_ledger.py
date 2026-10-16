"""Send ledger at the transport entry point of the zone dialogue study.

PR 194 seventh review (Codex ``codex-194-r7``, P1): the scheduler used to take an
adapter's word for what it sent. ``NotSent`` refunded a call whose request had
already left, and a ``sent_attempts`` that was too small freed a budget slot for
one more request. The root fix is that the scheduler reads sends from THIS
ledger, not from the adapter's report.

The ledger wraps the one function that puts a request on the wire. For the real
model path that function is the ``http_open`` of
``harness.gemini_proxy.GeminiProxyCompleter`` (the audited-opener pattern of the
2026-09-25 Korean pilot, ``scripts/pilot_korean_dialogue.py``); for the no-LLM
paths it is an offline wire with the same ``(request, *, timeout)`` signature.
The ledger:

* asks its owner (the SIM scheduler) to AUTHORISE every request before it
  reaches the wire; a refused request raises :class:`SendBlocked` and never
  reaches it, so an adapter cannot spend budget it does not have;
* records every request that reached the wire, BEFORE the wire runs: a wire that
  raises may already have written the request, so it still counts as sent;
* can store the request and response bytes (refusing to overwrite a file), as
  the pilot's audited opener did.

Openers are bound to one call (:meth:`SendLedger.opener_for`), so a send is
attributed to its call without any thread-local state. Nothing here reads a
clock: the entries are deterministic for identical requests.

R8: the counting unit is a proxy POST, not an upstream generation or a bill.
The real pilot uses PilotSendLedger to reserve up to TWO upstream attempts
per POST. All ledger I/O is restricted to its creating thread.
"""
from __future__ import annotations

import hashlib
import io
import json
import os
import threading
from pathlib import Path
from urllib.request import Request

LEDGER_SCHEMA = 'ugrp.zone_send_ledger.v1'
#: URL of the requests an offline wire receives. Never a network address.
SCRIPTED_URL = 'ledger://scripted'


class SendBlocked(RuntimeError):
    """The ledger refused a request before it reached the wire: nothing was sent.

    Deliberately NOT an ``OSError``: ``GeminiProxyCompleter`` turns ``OSError``
    into a retryable connection error, while a refusal must reach the adapter
    unchanged.
    """

    def __init__(self, call_id, reason):
        super().__init__(f'{call_id}: request blocked before the wire ({reason})')
        self.call_id, self.reason = call_id, reason


def _sha256(data):
    return hashlib.sha256(data).hexdigest()


class SendLedger:
    """Every request of a run that reached the wire, or was blocked before it.

    ``wire(request, *, timeout)`` is the real entry point (``urllib.request.urlopen``
    for the live proxy, :class:`ScriptedWire`/:class:`FixtureWire` offline). It
    must return a readable response (a context manager with ``read()``).
    ``store_dir`` keeps the request/response bytes of every send.
    """

    def __init__(self, wire, *, store_dir=None):
        if not callable(wire):
            raise TypeError('a send ledger needs a callable wire(request, *, timeout)')
        self._wire = wire
        self._authorize = None
        self._owner = None
        self._lock = threading.Lock()
        self._thread = threading.get_ident()
        self.entries = []
        self.store_dir = None if store_dir is None else Path(store_dir)
        if self.store_dir is not None:
            self.store_dir.mkdir(parents=True, exist_ok=True)

    # -- owner -----------------------------------------------------------------
    def attach(self, authorize, *, owner):
        """Make ``authorize(call_id) -> None | reason`` the gate of every send.

        One owner only: two schedulers sharing a ledger would each authorise the
        other's calls against their own budget.
        """
        if not callable(authorize):
            raise TypeError('authorize must be callable')
        if self._authorize is not None:
            raise ValueError('this send ledger already has an owner; use one ledger per scheduler')
        self._authorize, self._owner = authorize, owner

    def opener_for(self, call_id, actor):
        """An ``http_open``-compatible callable whose sends belong to ``call_id``."""
        if not isinstance(call_id, str) or not call_id:
            raise ValueError('call_id must be a non-empty string')

        def http_open(request, *, timeout=None):
            return self._send(call_id, actor, request, timeout)

        http_open.call_id = call_id
        http_open.ledger = self
        return http_open

    # -- the wire --------------------------------------------------------------
    def _send(self, call_id, actor, request, timeout):
        if threading.get_ident() != self._thread:
            raise RuntimeError('single-thread send ledger: only the owner may send')
        body = getattr(request, 'data', None)
        if not isinstance(body, (bytes, bytearray)):
            raise TypeError('a ledgered request must carry its body as bytes (urllib Request.data)')
        body = bytes(body)
        with self._lock:
            reason = 'no_owner' if self._authorize is None else self._authorize(call_id)
            row = {'seq': len(self.entries) + 1, 'call_id': call_id, 'actor': actor,
                   'status': 'blocked' if reason else 'sent', 'reason': reason,
                   'url': getattr(request, 'full_url', None), 'method': request.get_method()
                   if hasattr(request, 'get_method') else None,
                   'body_sha256': _sha256(body), 'bytes': len(body)}
            self.entries.append(row)
        if reason:
            raise SendBlocked(call_id, reason)
        try:
            self._store(row, 'request', body)
        except BaseException:
            # not stored = not sent: the audit copy must exist before the wire runs
            row.update(status='blocked', reason='store_failed')
            raise
        try:
            response = self._wire(request, timeout=timeout)
            with response:
                data = response.read()
        except BaseException as exc:
            # the request reached the wire: it stays a send whatever happened next
            row['wire_error'] = type(exc).__name__
            raise
        row['response_sha256'] = _sha256(data)
        row['response_bytes'] = len(data)
        self._store(row, 'response', data)
        return io.BytesIO(data)

    def _store(self, row, kind, data):
        if self.store_dir is None:
            return
        safe = row['call_id'].replace('/', '_').replace(':', '_')
        path = self.store_dir / f'{row["seq"]:06d}-{safe}-{kind}.json'
        with open(path, 'xb') as handle:          # never overwrite a stored send
            handle.write(data)
            handle.flush()
            os.fsync(handle.fileno())
        row[f'{kind}_path'] = path.name

    # -- reading -----------------------------------------------------------------
    def sends(self, call_id=None):
        """Requests that reached the wire (of one call, or of the whole run)."""
        return sum(1 for row in self.entries if row['status'] == 'sent'
                   and (call_id is None or row['call_id'] == call_id))

    def blocked(self, call_id=None):
        return sum(1 for row in self.entries if row['status'] == 'blocked'
                   and (call_id is None or row['call_id'] == call_id))

    def by_call(self):
        out = {}
        for row in self.entries:
            counts = out.setdefault(row['call_id'], {'sent': 0, 'blocked': 0})
            counts[row['status']] += 1
        return out

    def digest(self):
        return _sha256(json.dumps(self.entries, sort_keys=True, separators=(',', ':')).encode())

    def to_dict(self, *, entries=True):
        value = {'schema': LEDGER_SCHEMA, 'sent': self.sends(), 'blocked': self.blocked(),
                 'by_call': self.by_call(), 'sha256': self.digest()}
        if entries:
            value['entries'] = [dict(row) for row in self.entries]
        return value


# ---------------------------------------------------------------------------
# Offline wires (no network) and a helper to send one scripted request

def completion_body(text, *, usage=None, model=None, finish_reason='stop') -> bytes:
    """An OpenAI-compatible completion response, as the Gemini proxy returns it."""
    value = {'choices': [{'message': {'role': 'assistant', 'content': text},
                          'finish_reason': finish_reason}]}
    if usage is not None:
        value['usage'] = dict(usage)
    if model is not None:
        value['model'] = model
    return json.dumps(value, ensure_ascii=False).encode('utf-8')


class ScriptedWire:
    """Offline wire for tests: scripted response bytes or exceptions, in order.

    ``requests`` holds every body that reached it: the ground truth a test
    compares the ledger with.
    """

    def __init__(self, responses=(), *, default=b'{}'):
        self.responses, self.default = list(responses), default
        self.requests = []

    def __call__(self, request, *, timeout=None):
        self.requests.append(bytes(request.data))
        item = self.responses.pop(0) if self.responses else self.default
        if isinstance(item, BaseException):
            raise item
        return io.BytesIO(item)


class FixtureWire:
    """Offline model wire: ``respond(system_text, user_text) -> reply text``.

    It decodes the request exactly as it would reach the proxy (the JSON body
    ``GeminiProxyCompleter`` wrote), so the fixture's whole input is what went
    on the wire. It returns a completion WITHOUT a usage report: no provider
    answered.
    """

    def __init__(self, respond):
        self.respond = respond
        self.requests = 0

    def __call__(self, request, *, timeout=None):
        self.requests += 1
        body = json.loads(request.data.decode('utf-8'))
        messages = body['messages']
        system = next(m['content'] for m in messages if m['role'] == 'system')
        user = messages[-1]['content']
        if isinstance(user, list):               # the text part before the attached images
            user = next(part['text'] for part in user if part.get('type') == 'text')
        return io.BytesIO(completion_body(self.respond(system, user)))


def send(http_open, body=b'{}', *, url=SCRIPTED_URL, timeout=1.0) -> bytes:
    """Send one request through ``http_open`` (a ledger opener) and read the reply."""
    request = Request(url, data=bytes(body), method='POST',
                      headers={'Content-Type': 'application/json'})
    with http_open(request, timeout=timeout) as response:
        return response.read()


__all__ = ['LEDGER_SCHEMA', 'SCRIPTED_URL', 'SendBlocked', 'SendLedger', 'ScriptedWire', 'FixtureWire',
           'completion_body', 'send']
