"""openrouter_v1: opt-in paid Gemma 4 31B upstream for the Mac E2E relay (default off).

Key only from the macOS Keychain (service ugrp-openrouter, account openrouter);
it is held in-process and sent only as an Authorization header. Requests are
the OpenAI-format bodies the driver already produces. Provider is pinned
(recorded config value) with no fallbacks. Error responses are never journaled
as completed results, so a client retry re-forwards instead of replaying a 5xx.
"""
from __future__ import annotations

import hashlib
import json
from pathlib import Path
import subprocess
import time
from urllib.error import HTTPError
from urllib.request import Request

from harness.s4_relay_journal import Journal
from harness.zone_study_llm_transport import no_redirect_opener

UPSTREAM_ID = 'openrouter_v1'
ENDPOINT = 'https://openrouter.ai/api/v1/chat/completions'
MODEL = 'google/gemma-4-31b-it'          # paid; never ':free'
REGISTERED_MODEL = 'gemma-4-31b-it'      # model name the driver sends
PROVIDER_ORDER = ('DeepInfra',)
SERVICE, ACCOUNT = 'ugrp-openrouter', 'openrouter'
DROPPED_FIELDS = ('reasoning_effort',)
RETRY_STATUSES = (429, 500, 502, 503, 504)
MAX_ATTEMPTS, RETRY_DELAY_S = 3, 1.0


def keychain_key():
    result = subprocess.run(['security', 'find-generic-password', '-s', SERVICE, '-a', ACCOUNT, '-w'],
                            capture_output=True, timeout=15)
    if result.returncode or not result.stdout.strip():
        raise ValueError('key_needed: macOS Keychain service ' + SERVICE)
    return result.stdout.decode().strip()


def config(provider_order=PROVIDER_ORDER):
    return dict(upstream=UPSTREAM_ID, endpoint=ENDPOINT, model=MODEL, provider_order=list(provider_order),
                allow_fallbacks=False, dropped_fields=list(DROPPED_FIELDS), usage_include=True,
                max_attempts=MAX_ATTEMPTS, retry_statuses=list(RETRY_STATUSES), retry_delay_s=RETRY_DELAY_S,
                key_location='macOS Keychain: ' + SERVICE)


def upstream_body(request, provider_order=PROVIDER_ORDER):
    if request.get('stream') or request.get('tools'):
        raise ValueError('stream_and_tools_unsupported')
    if request.get('model') != REGISTERED_MODEL:
        raise ValueError('single_model_profile_mismatch')
    body = {k: v for k, v in request.items() if k not in DROPPED_FIELDS}
    body['model'] = MODEL
    body['usage'] = {'include': True}
    body['provider'] = {'order': list(provider_order), 'allow_fallbacks': False}
    return body


def http_send(payload, key, timeout=180):
    request = Request(ENDPOINT, data=json.dumps(payload).encode(), headers={
        'Content-Type': 'application/json', 'Authorization': 'Bearer ' + key})
    try:
        with no_redirect_opener().open(request, timeout=timeout) as response:
            return response.status, response.read(8_000_000), response.headers.get('Retry-After')
    except HTTPError as exc:
        return exc.code, exc.read(8_000_000), exc.headers.get('Retry-After')


class OpenRouter:
    standard = True

    def __init__(self, root, *, key=None, send=http_send, sleep=time.sleep, provider_order=PROVIDER_ORDER):
        self.root = Path(root); self.root.mkdir(parents=True, exist_ok=True)
        self._key = keychain_key() if key is None else key
        self.send, self.sleep = send, sleep
        self.provider_order = tuple(provider_order)
        self.model_id = MODEL
        self.model = {'version': 'openrouter:' + MODEL}
        self.journal = Journal(self.root / 'responses', retry_rate_limits=True, cache_errors=False)

    def require_image_probe(self): pass  # the real E2E wire request is the image check

    def complete(self, raw, request_id, *, idempotency_key=None):
        key = idempotency_key or hashlib.sha256(request_id.encode()).hexdigest()
        return self.journal.call(key, raw, lambda: self._complete(raw, request_id))[0]

    def _complete(self, raw, request_id):
        try:
            body = upstream_body(json.loads(raw), self.provider_order)
        except (ValueError, KeyError, TypeError) as exc:
            return 400, json.dumps(dict(error='invalid_OpenAI_request', detail=str(exc),
                                        ugrp_upstream_forwarded=False)).encode(), None
        attempts, started = [], time.monotonic()
        status, response, retry_after = 502, b'', None
        for n in range(1, MAX_ATTEMPTS + 1):
            t0 = time.monotonic()
            try:
                status, response, retry_after = self.send(body, self._key)
            except Exception as exc:  # transport: ambiguous, reported as 502
                status, response, retry_after = 502, json.dumps(
                    dict(error='openrouter_transport', type=type(exc).__name__)).encode(), None
            attempts.append(dict(attempt=n, status=status, wall_s=time.monotonic() - t0))
            if status not in RETRY_STATUSES or n == MAX_ATTEMPTS:
                break
            self.sleep(RETRY_DELAY_S)
        wall = time.monotonic() - started
        try: data = json.loads(response)
        except ValueError: data = {}
        if not isinstance(data, dict): data = {}
        usage = data.get('usage') or {}
        ok = status == 200 and bool(data.get('choices'))
        if status == 200 and not ok: status = 502
        provider = data.get('provider')
        if ok and provider not in self.provider_order:
            status, ok = 502, False
            data = {'error': 'provider_not_pinned', 'provider': provider}
        if ok:
            result = dict(data)
        else:
            result = dict(error='openrouter_http_' + str(status), upstream_error=data.get('error'))
        result.update(upstream=UPSTREAM_ID, model=data.get('model') or MODEL, provider=provider,
            ugrp_upstream_forwarded=True, ugrp_upstream_wall_s=wall,
            ugrp_openrouter=dict(requested_model=MODEL, provider_order=list(self.provider_order),
                provider_returned=provider, prompt_tokens=usage.get('prompt_tokens'),
                completion_tokens=usage.get('completion_tokens'), cost=usage.get('cost'),
                latency_s=wall, http_status=status, retries=len(attempts) - 1, attempts=attempts))
        if not ok:
            result['host_error'] = status in RETRY_STATUSES or status == 502
        retry = retry_after if status == 429 else None
        self.record(request_id, raw, status, result)
        return status, json.dumps(result).encode(), retry

    def record(self, request_id, raw, status, result):
        row = dict(request_id=request_id, upstream=UPSTREAM_ID, model=MODEL, status=status,
                   request_sha256=hashlib.sha256(raw).hexdigest(), provider=result.get('provider'),
                   openrouter=result.get('ugrp_openrouter'), host_error=result.get('host_error', False))
        with (self.root / 'ledger.jsonl').open('a') as f:
            f.write(json.dumps(row) + '\n')
