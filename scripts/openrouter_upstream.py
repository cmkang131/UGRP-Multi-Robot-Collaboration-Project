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
import os
import math
import random
from pathlib import Path
import subprocess
import time
import threading
from urllib.error import HTTPError
from urllib.request import Request

from harness.s4_relay_journal import Journal
from harness.zone_study_llm_transport import no_redirect_opener
from harness.task_planner_model import ModelSelection, DEFAULT_MODEL, DEFAULT_PROVIDER, ModelBudgetExceeded

UPSTREAM_ID = 'openrouter_v1'
ENDPOINT = 'https://openrouter.ai/api/v1/chat/completions'
MODEL = DEFAULT_MODEL
REGISTERED_MODEL = 'gemma-4-31b-it'      # model name the driver sends
PROVIDER_ORDER = (DEFAULT_PROVIDER,)
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


def config(provider_order=PROVIDER_ORDER, *, selection=None, max_attempts=MAX_ATTEMPTS, max_calls=None, rate_limit_policy='off', max_usd=None):
    choice = selection or ModelSelection()
    if selection is not None: provider_order = (choice.provider,)
    value = dict(upstream=UPSTREAM_ID, endpoint=ENDPOINT, model=choice.model, provider_order=list(provider_order),
                allow_fallbacks=False, dropped_fields=list(DROPPED_FIELDS), usage_include=True,
                reasoning=choice.reasoning, max_calls=max_calls,
                max_attempts=max_attempts, retry_statuses=list(RETRY_STATUSES), retry_delay_s=RETRY_DELAY_S,
                key_location='macOS Keychain: ' + SERVICE)
    if rate_limit_policy != 'off':
        from scripts.openrouter_ling_policy import POLICY,PARAMETERS
        from harness.task_planner_model import LING, GEMMA_FP4
        if (rate_limit_policy,choice) not in ((POLICY,LING),('planner_rate_limit_v1',GEMMA_FP4)):raise ValueError('REGISTERED_RATE_POLICY_REQUIRED')
        value.update(rate_limit_policy=rate_limit_policy,rate_limit_parameters=PARAMETERS,max_usd=max_usd,
            rate_limit_source_sha256=hashlib.sha256(Path(__file__).with_name('openrouter_ling_policy.py').read_bytes()).hexdigest())
    return value


def upstream_body(request, provider_order=PROVIDER_ORDER, *, selection=None):
    choice = selection or ModelSelection()
    if selection is not None: provider_order = (choice.provider,)
    if request.get('stream') or request.get('tools'):
        raise ValueError('stream_and_tools_unsupported')
    if request.get('model') != choice.wire_model:
        raise ValueError('single_model_profile_mismatch')
    body = {k: v for k, v in request.items() if k not in DROPPED_FIELDS}
    body['model'] = choice.model
    body.update(choice.request_options())
    body['usage'] = {'include': True}
    body['provider'] = {'order': list(provider_order), 'allow_fallbacks': False}
    return body


def http_send(payload, key, timeout=180):
    request = Request(ENDPOINT, data=json.dumps(payload).encode(), headers={
        'Content-Type': 'application/json', 'Authorization': 'Bearer ' + key})
    try:
        with no_redirect_opener().open(request, timeout=timeout) as response:
            return response.status, response.read(8_000_000), response.headers.get('Retry-After'), dict(response.headers)
    except HTTPError as exc:
        return exc.code, exc.read(8_000_000), exc.headers.get('Retry-After'), dict(exc.headers)


class OpenRouter:
    standard = True

    def __init__(self, root, *, key=None, send=http_send, sleep=time.sleep, provider_order=PROVIDER_ORDER,
                 selection=None, max_attempts=MAX_ATTEMPTS, max_calls=None, rate_limit_policy='off', max_usd=None,
                 random_fn=random.random, monotonic=time.monotonic):
        self.root = Path(root); self.root.mkdir(parents=True, exist_ok=True)
        self._key = keychain_key() if key is None else key
        self.send, self.sleep = send, sleep
        self.selection = selection
        self.provider_order = (selection.provider,) if selection else tuple(provider_order)
        self.model_id = selection.model if selection else MODEL
        self.model = {'version': 'openrouter:' + self.model_id}
        if max_attempts not in (1, 2, 3) or (max_calls is not None and not 0 < max_calls <= 600):
            raise ValueError('INVALID_UPSTREAM_LIMIT')
        self.max_attempts, self.max_calls = max_attempts, max_calls
        self.call_lock = threading.Lock()
        self.rate_limit_policy=rate_limit_policy;self.max_usd=max_usd;self.random_fn=random_fn;self.monotonic=monotonic
        config(selection=selection,max_attempts=max_attempts,max_calls=max_calls,rate_limit_policy=rate_limit_policy,max_usd=max_usd)
        if rate_limit_policy!='off' and max_attempts>3:raise ValueError('MAX_TWO_RETRIES')
        self.slot=threading.Semaphore(1);self.next_send_at=0.;self.accounted=0.;self.actual_cost=0.;self.unknown_cost=0
        self.evidence_file=self.root/'http_responses.jsonl'
        if self.evidence_file.exists():
            for line in self.evidence_file.read_text().splitlines():
                entry=json.loads(line);self.accounted+=entry['accounted_cost'];self.actual_cost+=entry.get('cost') or 0
                self.unknown_cost+=entry.get('cost') is None
        # Reserve unmatched attempts from interrupted processes as unknown.

        # A crash/restart cannot erase an already reserved actual HTTP attempt.
        self.attempt_file = self.root / 'http_attempts.jsonl'
        self.calls = len(self.attempt_file.read_text().splitlines()) if self.attempt_file.exists() else 0
        if rate_limit_policy!='off' and self.attempt_file.exists():
            settled={json.loads(line)['call'] for line in self.evidence_file.read_text().splitlines()} if self.evidence_file.exists() else set()
            for line in self.attempt_file.read_text().splitlines():
                entry=json.loads(line)
                if entry['call'] not in settled:self.accounted+=entry.get('reserve_usd',.01);self.unknown_cost+=1
        self.journal = Journal(self.root / 'responses', retry_rate_limits=True, cache_errors=False)

    def require_image_probe(self): pass  # the real E2E wire request is the image check

    def complete(self, raw, request_id, *, idempotency_key=None):
        key = idempotency_key or hashlib.sha256(request_id.encode()).hexdigest()
        if self.rate_limit_policy=='off':
            return self.journal.call(key, raw, lambda: self._complete(raw, request_id))[0]
        # One shared provider slot across every robot/client on this relay.
        deadline=self.monotonic()+28.
        if not self.slot.acquire(timeout=25.):
            return 503,b'{"error":"ling_concurrency_deadline","ugrp_upstream_forwarded":false}',None
        try:return self.journal.call(key, raw, lambda: self._complete(raw, request_id,deadline=deadline))[0]
        finally:self.slot.release()

    def _complete(self, raw, request_id,deadline=None):
        try:
            body = upstream_body(json.loads(raw), self.provider_order, selection=self.selection)
        except (ValueError, KeyError, TypeError) as exc:
            return 400, json.dumps(dict(error='invalid_OpenAI_request', detail=str(exc),
                                        ugrp_upstream_forwarded=False)).encode(), None
        from scripts.openrouter_ling_policy import safe_headers,error_body,retry_delay,reserve_cost,redact
        limited=self.rate_limit_policy!='off'
        attempts, started = [], self.monotonic()
        reserve=reserve_cost(body, self.selection) if limited else 0.
        retry_wait=0.
        status, response, retry_after = 502, b'', None
        for n in range(1, self.max_attempts + 1):
            pacing=max(0.,self.next_send_at-self.monotonic()) if limited else 0.
            if limited and deadline is not None and self.monotonic()+pacing+1>=deadline:
                return 429,json.dumps(dict(error='ling_cooldown_exceeds_deadline',retry_after_s=pacing,ugrp_upstream_forwarded=False)).encode(),str(math.ceil(pacing))
            if pacing:self.sleep(pacing)
            t0 = self.monotonic()
            with self.call_lock:
                if self.max_calls is not None and self.calls >= self.max_calls:
                    raise ModelBudgetExceeded('UPSTREAM_CALL_LIMIT')
                if limited and self.max_usd is not None and self.accounted+reserve>self.max_usd:
                    raise ModelBudgetExceeded('UPSTREAM_USD_LIMIT')
                if limited and self.calls%50==0 and self.send is http_send:
                    req=Request('https://openrouter.ai/api/v1/key',headers={'Authorization':'Bearer '+self._key})
                    with no_redirect_opener().open(req,timeout=15) as res:remaining=json.load(res)['data']['limit_remaining']
                    if remaining is None or remaining-(self.max_usd or .08)<1.5:raise ModelBudgetExceeded('KEY_REMAINING_FLOOR')
                self.calls += 1
                if limited:self.accounted+=reserve
                with self.attempt_file.open('a') as f:
                    f.write(json.dumps(dict(call=self.calls, request_id=request_id, model=self.model_id, reserve_usd=reserve,started_unix=time.time()))+'\n')
                    f.flush()
                    os.fsync(f.fileno())
            try:
                sent=self.send(body,self._key,timeout=max(.1,min(12.,deadline-self.monotonic()))) if limited and self.send is http_send else self.send(body,self._key)
                status,response,retry_after=sent[:3]
                headers=redact(safe_headers(sent[3]),self._key) if len(sent)>3 else ({'retry-after':retry_after} if retry_after else {})
            except Exception as exc:  # transport: ambiguous, reported as 502
                status, response, retry_after = 502, json.dumps(
                    dict(error='openrouter_transport', type=type(exc).__name__)).encode(), None
                headers={}
            entry=dict(call=self.calls,request_id=request_id,attempt=n,status=status,wall_s=self.monotonic()-t0,
                pacing_wait_s=pacing,retry_wait_before_s=retry_wait,headers=headers)
            try:attempt_data=json.loads(response)
            except (ValueError,UnicodeDecodeError):attempt_data={}
            usage_now=attempt_data.get('usage') or {} if isinstance(attempt_data,dict) else {}
            cost=usage_now.get('cost')
            known=type(cost) in (int,float) and cost>=0
            if limited:
                if known:self.accounted+=cost-reserve;self.actual_cost+=cost
                else:self.unknown_cost+=1
                self.next_send_at=t0+2.
            entry.update(cost=cost if known else None,accounted_cost=cost if known else reserve,
                model=attempt_data.get('model') if isinstance(attempt_data,dict) else None,
                provider=attempt_data.get('provider') if isinstance(attempt_data,dict) else None,
                prompt_tokens=usage_now.get('prompt_tokens'),completion_tokens=usage_now.get('completion_tokens'),
                cached_tokens=(usage_now.get('prompt_tokens_details') or {}).get('cached_tokens'))
            if status>=400:entry['error_body']=error_body(response,self._key)
            should_retry=(status==429 or 500<=status<600 if limited else status in RETRY_STATUSES) and n<self.max_attempts
            delay,source=retry_delay(n,headers,self.random_fn(),time.time()) if limited and should_retry else (RETRY_DELAY_S,'legacy_fixed')
            if should_retry:
                entry.update(retry_wait_s=delay,retry_wait_source=source)
                # Do not outlive the planner's 30 s deadline. A long server
                # hint is a global cooldown, not permission to hammer again.
                if limited and (self.monotonic()+delay+2>=deadline if deadline is not None else self.monotonic()-started+delay+2>=28):
                    self.next_send_at=max(self.next_send_at,self.monotonic()+delay)
                    entry['retry_skipped']='planner_deadline';should_retry=False
            with self.evidence_file.open('a') as f:
                f.write(json.dumps(entry)+'\n');f.flush();os.fsync(f.fileno())
            attempts.append(entry)
            if not should_retry:break
            retry_wait=delay;self.sleep(delay)
        wall = self.monotonic() - started
        try: data = error_body(response,self._key) if status>=400 else json.loads(response)
        except ValueError: data = {}
        if not isinstance(data, dict): data = {}
        usage = data.get('usage') or {}
        ok = status == 200 and bool(data.get('choices'))
        if status == 200 and not ok: status = 502
        provider = data.get('provider')
        if ok and provider not in ((self.selection.response_provider,) if self.selection else self.provider_order):
            status, ok = 502, False
            data = {'error': 'provider_not_pinned', 'provider': provider}
        if ok and data.get('model') != self.model_id:
            status, ok = 502, False
            data = {**data, 'error': 'model_not_pinned'}
        if ok:
            result = dict(data)
        else:
            result = dict(error='openrouter_http_' + str(status), upstream_error=data.get('error'))
        result.update(upstream=UPSTREAM_ID, model=data.get('model') or self.model_id, provider=provider,
            ugrp_upstream_forwarded=True, ugrp_upstream_wall_s=wall,
            ugrp_openrouter=dict(requested_model=self.model_id, provider_order=list(self.provider_order),
                provider_returned=provider, prompt_tokens=usage.get('prompt_tokens'),
                completion_tokens=usage.get('completion_tokens'), cost=usage.get('cost'),
                latency_s=wall, http_status=status, retries=len(attempts) - 1, attempts=attempts,
                total_cost=sum(x['cost'] for x in attempts if x['cost'] is not None),
                unknown_cost_attempts=sum(x['cost'] is None for x in attempts),
                cumulative_http_attempts=self.calls,cumulative_cost_usd=self.actual_cost,
                cumulative_accounted_usd=self.accounted))
        if not ok:
            result['host_error'] = status in RETRY_STATUSES or status == 502
        retry = retry_after if status == 429 else None
        self.record(request_id, raw, status, result)
        return status, json.dumps(result).encode(), retry

    def record(self, request_id, raw, status, result):
        row = dict(request_id=request_id, upstream=UPSTREAM_ID, model=self.model_id, returned_model=result.get('model'), status=status,
                   request_sha256=hashlib.sha256(raw).hexdigest(), provider=result.get('provider'),
                   upstream_error=result.get('upstream_error'), openrouter=result.get('ugrp_openrouter'), host_error=result.get('host_error', False))
        with (self.root / 'ledger.jsonl').open('a') as f:
            f.write(json.dumps(row) + '\n')
