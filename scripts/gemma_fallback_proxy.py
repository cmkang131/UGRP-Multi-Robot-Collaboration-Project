"""Mac-only, opt-in DEV Gemma gateway. Keys never leave Keychain except in an API header.

models.list resolves the requested family. Legacy limits come from upstream
evidence; multi_key_v1 uses the user-approved per-project caps and cooldowns.
"""
from __future__ import annotations

import argparse
import base64
from contextlib import contextmanager, ExitStack
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
from harness.s4_gemma_quota import SharedQuota

API = 'https://generativelanguage.googleapis.com/v1beta/'
SERVICE = 'ugrp-gemma-aistudio'
PROVIDER = 'google_aistudio_gemma'
PROFILE = 'dev_gemini_gemma_fallback_v1'
STANDARD_PROFILE = 'study_gemma4_31b_v1'
ROOT = Path('/Users/changmin/projects/ugrp/outputs/gemma-fallback')
PACIFIC = ZoneInfo('America/Los_Angeles')


def write(path, value):
    path = Path(path)
    temporary = path.with_suffix('.new')
    temporary.write_text(json.dumps(value, ensure_ascii=False, indent=2) + '\n')
    temporary.replace(path)


def keychain_key(service=SERVICE):
    result = subprocess.run(['security', 'find-generic-password', '-s', service, '-a', 'aistudio', '-w'],
                            capture_output=True, timeout=15)
    if result.returncode or not result.stdout.strip():
        raise ValueError('key_needed: macOS Keychain service ' + SERVICE)
    return result.stdout.decode().strip()


def keychain_keys():
    """Enumerate metadata (never security -d); load only matching account/services.

    Indexes are stable service suffixes, including gaps. Duplicate credentials
    share one bucket. Different credentials must belong to different projects.
    """
    result = subprocess.run(['security', 'dump-keychain'], capture_output=True, timeout=15)
    if result.returncode:
        raise ValueError('keychain_service_inventory_failed')
    indexes = set()
    for item in result.stdout.decode().split('keychain:'):
        if not re.search(r'"acct"<blob>="aistudio"', item):
            continue
        match = re.search(r'"svce"<blob>="ugrp-gemma-aistudio(?:-([2-9]\d*|1\d+))?"', item)
        if match:
            indexes.add(int(match[1]) if match[1] else 1)
    keys = {}
    for index in sorted(indexes):
        try:
            key = keychain_key(SERVICE if index == 1 else SERVICE + '-' + str(index))
        except ValueError:
            continue
        if key not in keys.values():
            keys[index] = key
    if not keys:
        raise ValueError('key_needed: macOS Keychain account aistudio')
    return keys


def google(path, payload=None, *, timeout=180, key=None, secrets=()):
    # Credentials stay in memory/API headers. No URL, CLI arg, env or redirect.
    key = key if key is not None else keychain_key()
    request = Request(API + path, data=None if payload is None else json.dumps(payload).encode(),
                      headers={'x-goog-api-key': key, 'Content-Type': 'application/json'})
    try:
        try:
            with no_redirect_opener().open(request, timeout=timeout) as reply:
                status, raw, headers = reply.status, reply.read(8_000_000), dict(reply.headers)
        except HTTPError as error:
            status, raw, headers = error.code, error.read(8_000_000), dict(error.headers)
        # Even an upstream error echoing the credential cannot persist it.
        for secret in (key, *secrets):
            raw = raw.replace(secret.encode(), b'[REDACTED_SECRET]')
            headers = {k: v.replace(secret, '[REDACTED_SECRET]') for k, v in headers.items()}
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


class PoolUnavailable(Exception):
    def __init__(self, reservation):
        super().__init__('gemma_key_pool_wait')
        self.reservation = reservation


class KeyPool:
    """Atomic most-headroom admission; only stable key_index values reach disk.

    Key 1 shares the legacy Mac-wide bucket, so an active single-key relay's
    reservations remain visible. Locks are released before every API call.
    """
    LIMITS = dict(rpm=30, tpm=16000, rpd=14400)

    def __init__(self, root, indexes, *, clock=time.time):
        self.root, self.clock = Path(root), clock
        self.buckets = {i: SharedQuota(self.root if i == 1 else self.root/('key-'+str(i)),
                                      clock=clock, limits=self.LIMITS)
                        for i in sorted(indexes)}
        self.providers = {i: Quota(q.root/'provider', clock=clock) for i, q in self.buckets.items()}

    def select(self, tokens, *, exclude=(), reserve=True, request_id='', request_sha256=''):
        # Lock order is numeric and identical in every process. The legacy
        # relay acquires only key 1; no extra global capacity bottleneck exists.
        with ExitStack() as stack:
            states = {i: stack.enter_context(q.locked()) for i, q in self.buckets.items()}
            available = {i: q.availability(states[i], tokens) for i, q in self.buckets.items()}
            choices = [i for i, (wait, _) in available.items() if wait <= 0 and i not in exclude]
            if not choices:
                waits = [wait for i,(wait,_) in available.items() if i not in exclude]
                return dict(admitted=False, retry_after_s=max(1, math.ceil(min(waits or [v[0] for v in available.values()]))),
                            effective_limits=self.LIMITS)
            index = max(choices, key=lambda i: (*available[i][1], -i))
            if not reserve:
                return dict(admitted=True, key_index=index)
            return self.buckets[index].reserve_state(states[index], tokens, request_id=request_id,
                request_sha256=request_sha256, key_index=index)

    def observe(self, index, status, body, headers):
        provider = self.providers[index]
        with provider.transaction() as state:
            provider.observe(state, status, body, headers)
            if status in (403, 429) or 500 <= status <= 599:
                from harness.s4_call_recovery import server_delay
                streak = min(7, state.get('failure_streak', 0)+1)
                state['failure_streak'] = streak
                retry = next((v for k,v in headers.items() if k.lower() == 'retry-after'), None)
                delay = max(min(3600, 60*2**(streak-1)),
                            server_delay({'Retry-After': retry}, json.dumps(body), self.clock()))
                error = body.get('error')
                for detail in error.get('details',[]) if isinstance(error,dict) else []:
                    value = str(detail.get('retryDelay',''))
                    if detail.get('@type','').endswith('RetryInfo') and re.fullmatch(r'\d+(?:\.\d+)?s',value):
                        delay = max(delay,float(value[:-1]))
                state['hold_until'] = max(state['hold_until'], self.clock()+delay)
            elif status == 200:
                state['failure_streak'] = 0
            with self.buckets[index].locked() as bucket:
                bucket['hold_until'] = max(bucket.get('hold_until', 0), state['hold_until'])
            return dict(state)


class Gemma:
    def __init__(self, root, *, send=google, clock=time.time, expected_model=None,
                 expected_version=None, shared_quota=None, standard=False,
                 multi_key_v1=False, keys=None):
        self.root, self.send = Path(root), send
        self.root.mkdir(parents=True, exist_ok=True)
        self.quota = Quota(self.root, clock=clock)
        self.shared_quota = shared_quota or SharedQuota(clock=clock)
        self.standard = standard
        self.multi_key_v1 = multi_key_v1
        self.key_pool = None
        if multi_key_v1:
            self._keys = keychain_keys() if keys is None else dict(keys)
            if not self._keys:
                raise ValueError('key_needed')
            # Exactly one key keeps the legacy quota/journal/response behavior.
            if len(self._keys) == 1:
                self.send = lambda path, payload=None: send(path, payload, key=next(iter(self._keys.values())))
            else:
                self.key_pool = KeyPool(self.shared_quota.root, self._keys, clock=clock)
                self._key_send = send
                self.send = self._metadata_send
        self.model, self.discovery = discover(self.send)
        self.model_id = self.discovery['model_id']
        if expected_model is not None and self.model_id != expected_model:
            raise ValueError('models.list_model_differs_from_registered_DEV_profile')
        if expected_version is not None and self.model.get('version') != expected_version:
            raise ValueError('models.list_version_drift')
        write(self.root / 'models-list.json', self.discovery)
        self.journal = Journal(self.root / 'responses', clock=clock,
                               retry_rate_limits=standard or self.key_pool is not None)

    def _metadata_send(self, path, payload=None):
        attempted = set()
        while True:
            reservation = self.key_pool.select(1, exclude=attempted, reserve=False)
            if not reservation['admitted']:
                raise PoolUnavailable(reservation)
            index = reservation['key_index']; attempted.add(index)
            status, body, headers = self._key_send(path, payload, key=self._keys[index],
                                                  secrets=tuple(self._keys.values()))
            self.key_pool.observe(index, status, body, headers)
            with (self.root / 'metadata-attempts.jsonl').open('a') as handle:
                handle.write(json.dumps(dict(key_index=index, path=path.split('?')[0], status=status))+'\n')
            if status not in (403, 429) and not 500 <= status <= 599:
                return status, body, headers

    def count_tokens(self, body):
        payload={'generateContentRequest':{'model':self.model['name'],**body}}
        sha=hashlib.sha256(json.dumps(payload,sort_keys=True).encode()).hexdigest()
        path=self.shared_quota.root/('count-'+sha+'.json')
        if path.exists():return json.loads(path.read_text())
        status,value,_=self.send(self.model['name']+':countTokens',payload)
        if status!=200 or type(value.get('totalTokens')) is not int:
            raise ValueError('countTokens_failed_closed')
        row=dict(request_sha256=sha,model=self.model_id,version=self.model.get('version'),
                 totalTokens=value['totalTokens'],response=value,source='actual_countTokens')
        # Hash-named cache contains no input text, images or credentials.
        with self.shared_quota.locked():write(path,row)
        return row

    def require_image_probe(self):
        path = self.root / 'image-probe.json'
        probe = json.loads(path.read_text()) if path.exists() else {}
        if probe.get('model_id') != self.model_id or probe.get('image_input_confirmed') is not True:
            raise ValueError('image_probe_required_before_DEV_fallback')

    def complete(self, raw, request_id, *, idempotency_key=None):
        key = idempotency_key or hashlib.sha256(request_id.encode()).hexdigest()
        return self.journal.call(key, raw, lambda: self._complete(raw, request_id))[0]

    def _complete(self, raw, request_id):
        if self.key_pool is not None:
            return self._complete_multi(raw, request_id)
        request = json.loads(raw); body = generate_body(request)
        if self.standard and request.get('model') != self.model_id:
            raise ValueError('single_model_profile_mismatch')
        counted=self.count_tokens(body)
        if self.standard and counted['totalTokens']>2500:
            return 400,b'{"error":"compact_input_exceeds_2500_tokens","ugrp_upstream_forwarded":false}',None
        reservation=self.shared_quota.reserve(counted['totalTokens']+body['generationConfig']['maxOutputTokens'],
            request_id=request_id,request_sha256=hashlib.sha256(raw).hexdigest())
        if not reservation['admitted']:
            return 429,json.dumps(dict(error='global_gemma_token_bucket',provider=PROVIDER,
                model=self.model_id,ugrp_upstream_forwarded=False,quota_wait=reservation,
                usage={'prompt_tokens':0,'completion_tokens':0,'total_tokens':0})).encode(),str(reservation['retry_after_s'])
        with self.quota.transaction() as state:
            retry = self.quota.reserve(state)
            if retry:
                self.record(request_id, raw, 429, {'error': 'gemma_quota_hold'}, state, forwarded=False)
                return 429, json.dumps(dict(error='gemma_quota_hold',provider=PROVIDER,
                    model=self.model_id, ugrp_upstream_forwarded=False)).encode(), retry
            # Persist the reservation before an ambiguous network failure/crash.
            write(self.root / 'quota.json', state)
        # Never hold the quota file lock across a slow provider request: the
        # shared token reservation already fences concurrent admission.
        upstream_started=time.monotonic()
        try:
            status, response, headers = self.send(self.model['name'] + ':generateContent', body)
        except Exception:
            response, headers, status = {'error': 'ambiguous_google_transport_not_retried'}, {}, 502
        upstream_wall_s=time.monotonic()-upstream_started
        with self.quota.transaction() as state:
            self.quota.observe(state, status, response, headers)
            result = openai_reply(response, self.model_id, request_id) if status == 200 else {
                'error': 'google_generateContent_http_' + str(status), 'provider': PROVIDER,
                'model': self.model_id}
            result['ugrp_upstream_forwarded'] = True
            result['ugrp_upstream_wall_s']=upstream_wall_s
            result['ugrp_count_tokens']=counted
            result['ugrp_quota_reservation']=reservation
            result['ugrp_model_pin']=dict(model_id=self.model_id,models_list_version=self.model.get('version'),
                response_model_version=response.get('modelVersion'),immutable_revision_available=False)
            result['ugrp_thoughts_tokens']=response.get('usageMetadata',{}).get('thoughtsTokenCount')
            if self.standard and status==200 and response.get('modelVersion')!=self.model_id:
                status=502
                result.pop('choices',None);result['error']='response_model_version_drift'
            self.record(request_id, raw, status, response, state, result=result, forwarded=True)
            return status, json.dumps(result).encode(), (str(max(1, math.ceil(state['hold_until']-self.quota.clock())))
                                                       if status == 429 else None)

    def _pool_wait(self, reservation, attempts):
        result = dict(error='global_gemma_token_bucket', provider=PROVIDER, model=self.model_id,
                      ugrp_upstream_forwarded=bool(attempts), quota_wait=reservation,
                      ugrp_key_attempts=attempts, multi_key_v1=True,
                      usage=None if attempts else {'prompt_tokens':0,'completion_tokens':0,'total_tokens':0})
        return 429, json.dumps(result).encode(), str(reservation['retry_after_s'])

    def _complete_multi(self, raw, request_id):
        request = json.loads(raw); body = generate_body(request)
        if self.standard and request.get('model') != self.model_id:
            raise ValueError('single_model_profile_mismatch')
        try:
            counted = self.count_tokens(body)
        except PoolUnavailable as wait:
            return self._pool_wait(wait.reservation, [])
        if self.standard and counted['totalTokens'] > 2500:
            return 400,b'{"error":"compact_input_exceeds_2500_tokens","ugrp_upstream_forwarded":false}',None
        attempts, attempted = [], set()
        while True:
            reservation = self.key_pool.select(counted['totalTokens']+body['generationConfig']['maxOutputTokens'],
                exclude=attempted, request_id=request_id, request_sha256=hashlib.sha256(raw).hexdigest())
            if not reservation['admitted']:
                return self._pool_wait(reservation, attempts)
            index = reservation['key_index']; attempted.add(index)
            began = time.monotonic(); ambiguous = False
            try:
                status, response, headers = self._key_send(self.model['name']+':generateContent', body,
                    key=self._keys[index], secrets=tuple(self._keys.values()))
            except Exception:
                status, response, headers = 502, {'error':'ambiguous_google_transport_not_retried'}, {}
                ambiguous = True
            wall = time.monotonic()-began
            quota = self.key_pool.observe(index, status, response, headers)
            result = openai_reply(response, self.model_id, request_id) if status == 200 else dict(
                error='google_generateContent_http_'+str(status), provider=PROVIDER, model=self.model_id)
            attempts.append(dict(key_index=index, status=status, usage=result.get('usage'),
                                 response_sha256=hashlib.sha256(json.dumps(response,sort_keys=True).encode()).hexdigest()))
            result.update(ugrp_upstream_forwarded=True, ugrp_upstream_wall_s=wall,
                ugrp_count_tokens=counted, ugrp_quota_reservation=reservation, key_index=index,
                multi_key_v1=True, ugrp_key_attempts=list(attempts),
                ugrp_model_pin=dict(model_id=self.model_id, models_list_version=self.model.get('version'),
                    response_model_version=response.get('modelVersion'), immutable_revision_available=False),
                ugrp_thoughts_tokens=response.get('usageMetadata',{}).get('thoughtsTokenCount'))
            if self.standard and status == 200 and response.get('modelVersion') != self.model_id:
                status = 502; result.pop('choices',None); result['error']='response_model_version_drift'
            self.record(request_id, raw, status, response, quota, result=result, forwarded=True,
                        key_index=index)
            # Only explicit completed HTTP failures can switch keys. A timeout,
            # malformed response or model-pin failure is terminal in the journal.
            if ambiguous or status not in (403,429) and not 500 <= status <= 599 or result.get('error') == 'response_model_version_drift':
                return status, json.dumps(result).encode(), None

    def record(self, request_id, raw, status, response, quota, *, forwarded, result=None, key_index=None):
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
        if key_index is not None:
            row['key_index'] = key_index
        with (self.root / 'ledger.jsonl').open('a') as handle:
            handle.write(json.dumps(row, ensure_ascii=False) + '\n')


def route(primary, body, request_id, *, fallback=None, idempotency_key=None):
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
        status, raw, retry = fallback.complete(body, request_id, idempotency_key=idempotency_key)
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
    p.add_argument('--multi-key-v1', action='store_true', help='multi_key_v1; default off')
    a = p.parse_args(argv)
    if not a.check and not a.enable:
        print(json.dumps(dict(enabled=False, model_id=None, key_service=SERVICE))); return 0
    try:
        if a.multi_key_v1:
            keys = keychain_keys()
        else:
            keychain_key()
    except ValueError:
        report = dict(model_id=None, key_needed=True, image_input_confirmed=None, rpm=None, rpd=None)
        a.output.mkdir(parents=True, exist_ok=True); write(a.output/'check.json', report)
        print(json.dumps(report)); return 2
    from harness.zone_study_llm_driver import load_registry
    registered = load_registry()['driver_profiles'][PROFILE]['fallback']['model_id']
    engine = Gemma(a.output, expected_model=registered, multi_key_v1=a.multi_key_v1,
                   keys=keys if a.multi_key_v1 else None)
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
        if a.multi_key_v1:
            report.update(multi_key_v1=True, keys=[dict(key_index=i) for i in sorted(engine._keys)],
                          per_key_limits=engine.key_pool.LIMITS if engine.key_pool else None,
                          single_key_legacy_behavior=engine.key_pool is None)
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
                status, raw, retry = engine.complete(self.rfile.read(n), request_id,
                    idempotency_key=self.headers.get('X-UGRP-Idempotency-Key'))
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
