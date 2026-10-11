"""Mac-only, opt-in DEV Gemma gateway. Keys never leave Keychain except in an API header.

No model name or quota is guessed: models.list resolves the requested family;
headers/QuotaFailure establish account limits. Unknown limits remain unknown.
"""
from __future__ import annotations

import argparse
import base64
from contextlib import contextmanager
from datetime import datetime, timedelta
import fcntl
import hashlib
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
import json
import math
from pathlib import Path
import re
import subprocess
import threading
import time
from urllib.error import HTTPError
from urllib.parse import urlencode
from urllib.request import Request
from zoneinfo import ZoneInfo

from harness.s4_relay_journal import Journal
from harness.zone_study_llm_transport import no_redirect_opener

API = 'https://generativelanguage.googleapis.com/v1beta/'
SERVICE = 'ugrp-gemma-aistudio'
PROVIDER = 'google_aistudio_gemma'
PROFILE = 'dev_gemini_gemma_fallback_v1'
ROOT = Path('/Users/changmin/projects/ugrp/outputs/gemma-fallback')
PACIFIC = ZoneInfo('America/Los_Angeles')


def write(path, value):
    path = Path(path)
    temporary = path.with_suffix('.new')
    temporary.write_text(json.dumps(value, ensure_ascii=False, indent=2) + '\n')
    temporary.replace(path)


def keychain_key():
    result = subprocess.run(['security', 'find-generic-password', '-s', SERVICE, '-w'],
                            capture_output=True, timeout=15)
    if result.returncode or not result.stdout.strip():
        raise ValueError('key_needed: macOS Keychain service ' + SERVICE)
    return result.stdout.decode().strip()


def google(path, payload=None, *, timeout=180):
    # Only this function sees the key. No query-string key, CLI arg, env or redirect.
    key = keychain_key()
    request = Request(API + path, data=None if payload is None else json.dumps(payload).encode(),
                      headers={'x-goog-api-key': key, 'Content-Type': 'application/json'})
    try:
        try:
            with no_redirect_opener().open(request, timeout=timeout) as reply:
                status, raw, headers = reply.status, reply.read(8_000_000), dict(reply.headers)
        except HTTPError as error:
            status, raw, headers = error.code, error.read(8_000_000), dict(error.headers)
        # Even an upstream error echoing the credential cannot persist it.
        raw = raw.replace(key.encode(), b'[REDACTED_SECRET]')
        headers = {k: v.replace(key, '[REDACTED_SECRET]') for k, v in headers.items()}
        return status, json.loads(raw), headers
    except Exception:
        raise RuntimeError('google_transport_or_invalid_json; ambiguous request not retried') from None


def discover(send=google):
    models, token, pages = [], None, 0
    while True:
        query = {'pageSize': 1000}
        if token:
            query['pageToken'] = token
        status, body, _ = send('models?' + urlencode(query))
        if status != 200:
            raise ValueError('models.list_failed_http_' + str(status))
        models.extend(body.get('models', [])); pages += 1
        token = body.get('nextPageToken')
        if not token:
            break
        if pages >= 20:
            raise ValueError('models.list_pagination_limit')
    matches = []
    for model in models:
        label = (model.get('name', '') + ' ' + model.get('displayName', '')).lower()
        if (re.search(r'gemma[\s_-]*4\b', label) and re.search(r'31[\s_-]*b\b', label)
                and 'generateContent' in model.get('supportedGenerationMethods', [])):
            matches.append(model)
    if len(matches) != 1 or not re.fullmatch(r'models/[a-zA-Z0-9._-]+', matches[0].get('name', '')):
        raise ValueError('Gemma_4_31B_missing_or_ambiguous_in_models.list')
    return matches[0], dict(source='models.list', pages=pages, checked_unix=time.time(),
                            model=matches[0], model_id=matches[0]['name'].removeprefix('models/'))


def generate_body(request):
    if request.get('stream') or request.get('tools'):
        raise ValueError('stream_and_tools_unsupported')
    contents, system = [], []
    for message in request['messages']:
        role = message['role']
        if role not in ('system', 'user', 'assistant'):
            raise ValueError('unsupported_message_role')
        content = message['content']
        parts = []
        for item in ([{'type': 'text', 'text': content}] if isinstance(content, str) else content):
            if item['type'] == 'text':
                parts.append({'text': item['text']})
            elif item['type'] == 'image_url':
                url = item['image_url']['url']
                match = re.fullmatch(r'data:(image/(?:jpeg|png|webp));base64,([A-Za-z0-9+/=\s]+)', url)
                if not match:
                    raise ValueError('only_inline_RGB_images_supported; no remote URL fetch')
                base64.b64decode(match[2], validate=True)
                parts.append({'inlineData': {'mimeType': match[1], 'data': match[2]}})
            else:
                raise ValueError('unsupported_message_part')
        if role == 'system':
            system.extend(parts)
        else:
            contents.append({'role': 'model' if role == 'assistant' else 'user', 'parts': parts})
    config = {'temperature': request.get('temperature', .2),
              'maxOutputTokens': request.get('max_tokens', 1400),
              'thinkingConfig': {'thinkingLevel': 'minimal'}}
    # Study JSON contract is already in the prompt; no native schema assumptions.
    body = {'contents': contents, 'generationConfig': config}
    if system:
        body['systemInstruction'] = {'parts': system}
    return body


def openai_reply(body, model, request_id):
    candidates = body.get('candidates') or [{}]
    choice = candidates[0]
    text = ''.join(p.get('text', '') for p in choice.get('content', {}).get('parts', [])
                   if not p.get('thought'))
    finish = choice.get('finishReason')
    usage = body.get('usageMetadata', {})
    # Missing usage stays unknown; thinking tokens belong to completion cost.
    totals = {}
    for source, target in (('promptTokenCount', 'prompt_tokens'), ('totalTokenCount', 'total_tokens')):
        if type(usage.get(source)) is int:
            totals[target] = usage[source]
    if 'prompt_tokens' in totals and 'total_tokens' in totals:
        totals['completion_tokens'] = max(0, totals['total_tokens'] - totals['prompt_tokens'])
    return {'id': request_id, 'object': 'chat.completion', 'model': body.get('modelVersion') or model,
            'provider': PROVIDER, 'usage': totals or None, 'upstream_finish_reason': finish,
            'promptFeedback': body.get('promptFeedback'),
            'choices': [{'index': 0, 'finish_reason': 'stop' if finish == 'STOP' else
                         ('length' if finish == 'MAX_TOKENS' else 'content_filter'),
                         'safetyRatings': choice.get('safetyRatings'),
                         'message': {'role': 'assistant', 'content': text}}]}


class Quota:
    """Durable cross-session, cross-process quota admission. Serializes reservations on Mac."""
    def __init__(self, root, *, clock=time.time):
        self.root, self.clock = Path(root), clock
        self.root.mkdir(parents=True, exist_ok=True)
        self.lock = threading.Lock()

    @contextmanager
    def transaction(self):
        with self.lock, (self.root / 'quota.lock').open('a') as handle:
            fcntl.flock(handle, fcntl.LOCK_EX)
            path = self.root / 'quota.json'
            state = json.loads(path.read_text()) if path.exists() else {
                'rpm': None, 'rpd': None, 'day_requests': 0, 'minute_requests': [], 'hold_until': 0}
            now = self.clock()
            day = datetime.fromtimestamp(now, PACIFIC).date().isoformat()
            if state.get('day') != day:
                state.update(day=day, day_requests=0)
            state['minute_requests'] = [t for t in state['minute_requests'] if t > now - 60]
            try:
                yield state
            finally:
                write(path, state)
                fcntl.flock(handle, fcntl.LOCK_UN)

    def midnight(self):
        local = datetime.fromtimestamp(self.clock(), PACIFIC)
        return (local + timedelta(days=1)).replace(hour=0, minute=0, second=0, microsecond=0).timestamp()

    def reserve(self, state):
        now = self.clock()
        hold = state['hold_until']
        if state['rpd'] is not None and state['day_requests'] >= state['rpd']:
            hold = max(hold, self.midnight())
        if state['rpm'] is not None and len(state['minute_requests']) >= state['rpm']:
            hold = max(hold, state['minute_requests'][0] + 60 if state['minute_requests'] else now + 60)
        if hold > now:
            return str(max(1, math.ceil(hold - now)))
        state['minute_requests'].append(now); state['day_requests'] += 1
        return None

    def observe(self, state, status, body, headers):
        headers = {k.lower(): v for k, v in headers.items()}
        evidence = {k: v for k, v in headers.items() if k == 'retry-after' or
                    re.fullmatch(r'(?:x-)?ratelimit-(?:limit|remaining|reset)-requests(?:-minute|-day)?', k)}
        daily, delays = False, []
        for unit, key in (('minute', 'rpm'), ('day', 'rpd')):
            value = headers.get('x-ratelimit-limit-requests-' + unit)
            if value is not None and str(value).isdigit():
                state[key] = int(value)
            if headers.get('x-ratelimit-remaining-requests-' + unit) == '0':
                state['hold_until'] = max(state['hold_until'], self.midnight() if unit == 'day' else self.clock()+60)
        violations = []
        error = body.get('error')
        for detail in (error.get('details', []) if isinstance(error, dict) else []):
            if detail.get('@type', '').endswith('RetryInfo'):
                delay = str(detail.get('retryDelay', ''))
                if re.fullmatch(r'\d+(?:\.\d+)?s', delay): delays.append(float(delay[:-1]))
            if detail.get('@type', '').endswith('QuotaFailure'):
                for v in detail.get('violations', []):
                    identity = v.get('quotaId', '')
                    violations.append({'quotaId': identity, 'quotaValue': v.get('quotaValue')})
                    daily |= 'perday' in identity.lower()
                    key = 'rpd' if 'perday' in identity.lower() else 'rpm' if 'perminute' in identity.lower() else None
                    if key and 'request' in identity.lower() and str(v.get('quotaValue', '')).isdigit():
                        state[key] = int(v['quotaValue'])
        retry = headers.get('retry-after')
        if retry:
            from harness.s4_call_recovery import server_delay
            delays.append(server_delay({'Retry-After': retry}, '', self.clock()))
        if status == 429:
            # No known reset => stop until daily reset, rather than hammer quota.
            until = self.midnight() if daily or not delays else self.clock() + max(60, *delays)
            state['hold_until'] = max(state['hold_until'], until)
        state['last_evidence'] = dict(http_status=status, headers=evidence, violations=violations,
                                      checked_unix=self.clock())
        return evidence


class Gemma:
    def __init__(self, root, *, send=google, clock=time.time, expected_model=None):
        self.root, self.send = Path(root), send
        self.root.mkdir(parents=True, exist_ok=True)
        self.quota = Quota(self.root, clock=clock)
        self.model, self.discovery = discover(send)
        self.model_id = self.discovery['model_id']
        if expected_model is not None and self.model_id != expected_model:
            raise ValueError('models.list_model_differs_from_registered_DEV_profile')
        write(self.root / 'models-list.json', self.discovery)
        self.journal = Journal(self.root / 'responses', retry_rate_limits=False)

    def require_image_probe(self):
        path = self.root / 'image-probe.json'
        probe = json.loads(path.read_text()) if path.exists() else {}
        if probe.get('model_id') != self.model_id or probe.get('image_input_confirmed') is not True:
            raise ValueError('image_probe_required_before_DEV_fallback')

    def complete(self, raw, request_id):
        key = hashlib.sha256(request_id.encode()).hexdigest()
        return self.journal.call(key, raw, lambda: self._complete(raw, request_id))[0]

    def _complete(self, raw, request_id):
        request = json.loads(raw); body = generate_body(request)
        with self.quota.transaction() as state:
            retry = self.quota.reserve(state)
            if retry:
                self.record(request_id, raw, 429, {'error': 'gemma_quota_hold'}, state, forwarded=False)
                return 429, json.dumps(dict(error='gemma_quota_hold',provider=PROVIDER,
                    model=self.model_id, ugrp_upstream_forwarded=False)).encode(), retry
            # Persist the reservation before an ambiguous network failure/crash.
            write(self.root / 'quota.json', state)
            try:
                status, response, headers = self.send(self.model['name'] + ':generateContent', body)
            except Exception:
                response, headers, status = {'error': 'ambiguous_google_transport_not_retried'}, {}, 502
            self.quota.observe(state, status, response, headers)
            result = openai_reply(response, self.model_id, request_id) if status == 200 else {
                'error': 'google_generateContent_http_' + str(status), 'provider': PROVIDER,
                'model': self.model_id}
            result['ugrp_upstream_forwarded'] = True
            self.record(request_id, raw, status, response, state, result=result, forwarded=True)
            return status, json.dumps(result).encode(), (str(max(1, math.ceil(state['hold_until']-self.quota.clock())))
                                                       if status == 429 else None)

    def record(self, request_id, raw, status, response, quota, *, forwarded, result=None):
        from harness.zone_study_llm_driver import _request_summary
        digest = hashlib.sha256(raw).hexdigest()
        # Preserve text and image hashes; callers retain original RGBs in their wire logs.
        request = json.loads(raw)
        for message in request.get('messages', []):
            if isinstance(message.get('content'), list):
                for part in message['content']:
                    if part.get('type') == 'image_url':
                        image = base64.b64decode(part['image_url']['url'].split(',', 1)[1])
                        part['image_url']['url'] = 'sha256:' + hashlib.sha256(image).hexdigest()
        row = dict(request_id=request_id, model=self.model_id, actual_model=(result or {}).get('model'),
                   provider=PROVIDER, status=status, upstream_forwarded=forwarded,
                   request_sha256=digest, request_summary=_request_summary(raw), request=request,
                   response=response, provider_usage=(result or {}).get('usage'),
                   quota={k: quota[k] for k in ('rpm', 'rpd', 'hold_until', 'last_evidence') if k in quota})
        with (self.root / 'ledger.jsonl').open('a') as handle:
            handle.write(json.dumps(row, ensure_ascii=False) + '\n')


def route(primary, body, request_id, *, fallback=None):
    """One completed Gemini HTTP failure -> one Gemma call with unchanged message/request_id."""
    status, raw, retry = primary()
    try:
        response = json.loads(raw)
    except ValueError:
        response = {}
    attempts = [{'provider': 'gemini_subscription', 'model': response.get('model'), 'status': status,
                 'usage': response.get('usage'), 'response_sha256': hashlib.sha256(raw).hexdigest()}]
    # Transport/identity ambiguity is never passed here: relay calls route only after HTTP result.
    quota = status >= 400 and re.search(r'quota|resource[ _-]?exhausted|rate[ _-]?limit', raw.decode('utf8', 'replace'), re.I)
    if fallback is not None and (status == 429 or status >= 500 or quota):
        status, raw, retry = fallback.complete(body, request_id)
        response = json.loads(raw)
        attempts.append({'provider': PROVIDER, 'model': response.get('model') or fallback.model_id,
                         'status': status, 'usage': response.get('usage'),
                         'upstream_forwarded': response.get('ugrp_upstream_forwarded'),
                         'response_sha256': hashlib.sha256(raw).hexdigest()})
    if isinstance(response, dict):
        response['provider'] = attempts[-1]['provider']
        response['ugrp_route'] = dict(request_id=request_id, attempts=attempts, dev_only=True)
        raw = json.dumps(response).encode()
    return status, raw, retry


def main(argv=None):
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('--output', type=Path, default=ROOT)
    p.add_argument('--check', action='store_true')
    p.add_argument('--image', type=Path)
    p.add_argument('--enable', action='store_true')
    p.add_argument('--seconds', type=int, default=3600)
    a = p.parse_args(argv)
    if not a.check and not a.enable:
        print(json.dumps(dict(enabled=False, model_id=None, key_service=SERVICE))); return 0
    try:
        keychain_key()
    except ValueError:
        report = dict(model_id=None, key_needed=True, image_input_confirmed=None, rpm=None, rpd=None)
        a.output.mkdir(parents=True, exist_ok=True); write(a.output/'check.json', report)
        print(json.dumps(report)); return 2
    from harness.zone_study_llm_driver import load_registry
    registered = load_registry()['driver_profiles'][PROFILE]['fallback']['model_id']
    engine = Gemma(a.output, expected_model=registered)
    if a.check:
        report = dict(model_id=engine.model_id, key_needed=False, image_input_confirmed=None)
        if a.image:
            image = a.image.read_bytes()
            mime = 'image/png' if image.startswith(b'\x89PNG') else 'image/jpeg'
            raw = json.dumps({'messages': [{'role': 'user', 'content': [
                {'type': 'text', 'text': 'Briefly describe visible robots and objects in this RGB image.'},
                {'type': 'image_url', 'image_url': {'url': 'data:' + mime + ';base64,' + base64.b64encode(image).decode()}}]}],
                'max_tokens': 160}).encode()
            request_id = 'gemma-image-probe-' + str(time.time_ns())
            status, response, _ = engine.complete(raw, request_id)
            value = json.loads(response)
            report.update(http_status=status, image_sha256=hashlib.sha256(image).hexdigest(),
                          image_path=str(a.image.resolve()), request_id=request_id,
                          image_input_confirmed=status == 200 and bool(value.get('choices', [{}])[0].get('message', {}).get('content'))
                          and value.get('upstream_finish_reason') == 'STOP',
                          scope='one actual image accepted and text returned; accuracy unmeasured')
            write(a.output/'image-probe.json', report)
        with engine.quota.transaction() as state:
            report.update(rpm=state['rpm'], rpd=state['rpd'], quota_evidence=state.get('last_evidence'))
        write(a.output/'check.json', report); print(json.dumps(report)); return 0
    if not 0 < a.seconds <= 14400:
        raise ValueError('finite <=4h service required')
    engine.require_image_probe()
    class Handler(BaseHTTPRequestHandler):
        def log_message(self, *args): pass
        def do_POST(self):
            if self.path != '/v1/chat/completions': self.send_error(404); return
            n = int(self.headers.get('Content-Length', '0'))
            request_id = self.headers.get('X-UGRP-Call-ID', '')
            if not 0 < n <= 8_000_000 or not request_id: self.send_error(400); return
            try:
                status, raw, retry = engine.complete(self.rfile.read(n), request_id)
            except (ValueError, KeyError, TypeError):
                status, raw, retry = 400, b'{"error":"invalid_OpenAI_request"}', None
            self.send_response(status); self.send_header('Content-Type', 'application/json')
            if retry: self.send_header('Retry-After', retry)
            self.send_header('Content-Length', str(len(raw))); self.end_headers(); self.wfile.write(raw)
    server = ThreadingHTTPServer(('127.0.0.1', 8393), Handler)
    timer = threading.Timer(a.seconds, server.shutdown); timer.daemon = True; timer.start()
    try: server.serve_forever()
    finally: timer.cancel(); server.server_close()


if __name__ == '__main__':
    raise SystemExit(main())
