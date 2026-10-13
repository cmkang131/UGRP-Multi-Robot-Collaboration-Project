"""Existing study_gemma4_31b_v1 Mac relay only. No API-key handling here."""
from __future__ import annotations
import copy
import hashlib
import json
import threading
import time
import urllib.request
from urllib.parse import urlsplit
from uuid import uuid4
from harness.task_planner import ModelReply

PROFILE = 'study_gemma4_31b_v1'
MODEL = 'google/gemma-4-31b-it'


class NoRedirect(urllib.request.HTTPRedirectHandler):
    def redirect_request(self, *args, **kwargs): return None


class Budget:
    def __init__(self, max_calls=1800, max_usd=2., reserve_usd=.002):
        self.max_calls, self.max_usd, self.reserve_usd = max_calls, max_usd, reserve_usd
        self.calls = 0; self.charged = 0.; self.unknown = 0
        self.lock = threading.Lock()

    def reserve(self):
        with self.lock:
            if self.calls >= self.max_calls or self.charged + self.reserve_usd > self.max_usd:
                raise RuntimeError('PLANNER_MODEL_BUDGET')
            self.calls += 1; self.charged += self.reserve_usd

    def reconcile(self, cost):
        with self.lock:
            if type(cost) not in (int, float) or cost < 0:
                self.unknown += 1
            else: self.charged += cost - self.reserve_usd


class Gemma:
    def __init__(self, *, url='http://127.0.0.1:18424', profile=PROFILE, budget=None, run_id=None):
        p = urlsplit(url)
        if (profile != PROFILE or p.scheme != 'http' or p.hostname not in ('127.0.0.1', 'localhost')
                or p.username or p.password or p.query or p.fragment or p.path not in ('', '/')):
            raise ValueError('EXISTING_LOOPBACK_GEMMA_RELAY_REQUIRED')
        self.url = url.rstrip('/'); self.budget = budget or Budget()
        self.run_id = run_id or uuid4().hex
        self.opener = urllib.request.build_opener(NoRedirect)
        self.identity = self._json('/identity', timeout=5)
        cfg = self.identity.get('openrouter_v1', {})
        if (cfg.get('model') != MODEL or cfg.get('allow_fallbacks') is not False
                or self.identity.get('jev_source_sha256') or self.identity.get('dialogue_decider') in ('d1_v1', 'code_v1')):
            raise ValueError('DIRECT_OPENROUTER_GEMMA_IDENTITY_REQUIRED')

    def _json(self, path, *, body=None, headers=None, timeout=30.):
        request = urllib.request.Request(self.url+path,
            data=None if body is None else json.dumps(body).encode(),
            headers={'Content-Type': 'application/json', **(headers or {})})
        with self.opener.open(request, timeout=timeout) as response:
            return json.load(response)

    def __call__(self, request, *, timeout_s):
        context = copy.deepcopy(request['input'])
        rgb = (context.get('own') or {}).get('rgb') or {}
        image = rgb.pop('image_b64', None)
        content = json.dumps(context, ensure_ascii=True)
        if image:
            import base64
            if hashlib.sha256(base64.b64decode(image, validate=True)).hexdigest() != rgb['sha256']:
                raise ValueError('OWN_RGB_HASH_MISMATCH')
            content = [dict(type='text', text=content),
                       dict(type='image_url', image_url=dict(url='data:image/jpeg;base64,'+image))]
        body = dict(model='gemma-4-31b-it', temperature=0, max_tokens=320,
                    messages=[dict(role='system', content=request['system']), dict(role='user', content=content)])
        key = hashlib.sha256(json.dumps(body, sort_keys=True).encode()).hexdigest()
        call_id = 's4live1-taskplanner-' + self.run_id + '-' + uuid4().hex
        self.budget.reserve(); started = time.monotonic()
        try:
            data = self._json('/v1/chat/completions', body=body, timeout=timeout_s,
                              headers={'X-UGRP-Call-ID': call_id, 'X-UGRP-Idempotency-Key': hashlib.sha256((call_id+'-'+key).encode()).hexdigest()})
        except Exception:
            self.budget.reconcile(None)
            raise
        elapsed = time.monotonic()-started
        usage = dict(data.get('usage') or {})
        cost = usage.get('cost', (data.get('ugrp_openrouter') or {}).get('cost'))
        self.budget.reconcile(cost)
        if data.get('model') != MODEL or data.get('provider') != 'DeepInfra':
            raise ValueError('PROVIDER_IDENTITY_MISMATCH')
        usage.update(cost=cost, call_id=call_id, request_sha256=key, model=data['model'], provider=data['provider'])
        choice = data['choices'][0]
        return ModelReply(raw=choice['message']['content'], finish_reason=choice.get('finish_reason'),
                          elapsed_s=elapsed, usage=usage)
