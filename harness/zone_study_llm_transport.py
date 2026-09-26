"""Scheduler transport of the zone dialogue study's model calls (PR 194, seventh review).

:class:`ModelCallTransport` is the adapter between package D's
``EventScheduler`` and a chat completer. The completer is
``harness.gemini_proxy.GeminiProxyCompleter`` for the live proxy and the SAME
class for the offline smoke; only the wire behind the send ledger differs
(``urllib.request.urlopen`` vs :class:`harness.zone_send_ledger.FixtureWire`).
Every HTTP request therefore passes the scheduler's
:class:`~harness.zone_send_ledger.SendLedger`: the completer's ``http_open`` is
the ledger opener of the call (``PendingCall.http_open``), and that is its only
network path (``GeminiProxyCompleter.complete`` sends through ``self.http_open``
and nothing else).

The adapter reports what it saw (attempts, usage), but the scheduler charges
what the ledger counted; the report is cross-checked, never trusted
(``EventScheduler._reply_of``).

A ``pipeline`` builds the request of a call and turns the reply text into a
``CallReply``::

    prepared = pipeline.prepare_call(call)       # validated inputs + package C request
    reply = pipeline.finish_call(call, prepared, raw_text, provider_usage=usage)

``prepared.request`` is the package C request (``messages`` and labelled
``images``). No live model is called by this module's tests or by the offline
smoke; :func:`live_send_ledger` exists so a runner never builds its own opener.
"""
from __future__ import annotations

from urllib.request import urlopen

from harness.gemini_proxy import GeminiProxyCompleter, GeminiProxyError
from harness.zone_event_scheduler import TransportFailure
from harness.zone_send_ledger import SendLedger
from harness.zone_sim_cost import Attempt

TRANSPORT_VERSION = 'ugrp.zone_study_llm_transport.v1'


def gemini_client_factory(*, model, url, max_tokens, temperature, reasoning_effort='none', timeout=45.0):
    """``http_open -> GeminiProxyCompleter``: one completer per call, bound to its opener.

    ``url`` is required: the completer's environment fallback would let a run
    pick a proxy nobody recorded.
    """
    if not isinstance(url, str) or not url:
        raise ValueError('the completer URL must be given explicitly')
    settings = {'model': model, 'url': url, 'max_tokens': max_tokens, 'temperature': temperature,
                'reasoning_effort': reasoning_effort, 'timeout': timeout}

    def make(http_open):
        if not callable(http_open) or getattr(http_open, 'call_id', None) is None:
            raise ValueError('a completer must send through the call\'s send-ledger opener')
        return GeminiProxyCompleter(http_open=http_open, **settings)

    make.settings = dict(settings)
    return make


def live_send_ledger(*, store_dir):
    """The send ledger of a LIVE run: the real wire, every request stored on disk."""
    return SendLedger(urlopen, store_dir=store_dir)


class ModelCallTransport:
    """``submit`` records the call; ``reply`` builds, sends and parses it.

    A completer failure (HTTP status, timeout, connection, malformed body) is a
    ``TransportFailure`` with an unknown usage: the request reached the wire, so
    the ledger has it and the scheduler charges it. A failure before the first
    send (building or validating the request) propagates unchanged and the
    ledger shows 0 sends, which is the only case the scheduler refunds.
    """

    def __init__(self, pipeline, *, send_ledger, client_factory):
        if not isinstance(send_ledger, SendLedger):
            raise TypeError('ModelCallTransport needs a harness.zone_send_ledger.SendLedger')
        for name in ('prepare_call', 'finish_call'):
            if not callable(getattr(pipeline, name, None)):
                raise TypeError(f'the pipeline needs {name}()')
        self.pipeline, self.send_ledger, self.client_factory = pipeline, send_ledger, client_factory
        self.submitted, self.resolved = [], []

    def submit(self, call):
        self.submitted.append(call.call_id)
        return call

    def reply(self, call):
        self.resolved.append(call.call_id)
        prepared = self.pipeline.prepare_call(call)
        client = self.client_factory(call.http_open)
        request = prepared.request
        try:
            raw = client.complete(request['messages'], images=request['images'])
        except GeminiProxyError as exc:
            outcome = 'timeout' if exc.error_kind == 'timeout' else 'error'
            raise TransportFailure(f'{exc.error_kind}: {exc}', attempts=(Attempt(outcome=outcome),),
                                   usage_known=False) from exc
        return self.pipeline.finish_call(call, prepared, raw, provider_usage=client.last_usage)


__all__ = ['TRANSPORT_VERSION', 'ModelCallTransport', 'gemini_client_factory', 'live_send_ledger']
