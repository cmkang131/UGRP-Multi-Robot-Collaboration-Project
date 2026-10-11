"""Finite-session idempotency journal: response text only, never request images/keys.

Pending records survive a relay crash and fail closed: an ambiguous upstream
request is never repeated. A dropped SSH client cannot cancel the owner thread.
"""
import hashlib
import json
import os
from pathlib import Path
import re
import threading
import time
from harness.s4_call_recovery import server_delay


class Journal:
    def __init__(self, root, *, clock=time.time, retry_rate_limits=True):
        self.root = Path(root)
        self.root.mkdir(parents=True, exist_ok=True)
        self.lock = threading.Lock()
        self.pending = {}
        self.clock = clock
        self.retry_rate_limits = retry_rate_limits

    def write(self, path, value):
        temporary = path.with_suffix('.new')
        with temporary.open('w') as f:
            json.dump(value, f); f.flush(); os.fsync(f.fileno())
        os.replace(temporary, path)

    def call(self, key, body, forward):
        if not re.fullmatch('[0-9a-f]{64}', key):
            return (400, b'{"error":"idempotency_key_required"}', None), 'rejected'
        digest = hashlib.sha256(body).hexdigest()
        path = self.root / (key + '.json')
        while True:
            with self.lock:
                old = json.loads(path.read_text()) if path.exists() else None
                if old and old['request_sha256'] != digest:
                    return (409, b'{"error":"idempotency_body_mismatch"}', None), 'rejected'
                if old and old['state'] == 'complete':
                    return (old['status'], old['response'].encode(), old['retry_after']), 'cached'
                if old and old['state'] == 'retryable' and self.clock() < old['retry_at']:
                    return (old['status'], old['response'].encode(),
                            str(max(1, int(old['retry_at']-self.clock()+.999)))), 'rate_limited'
                if key in self.pending:
                    wait = self.pending[key]
                elif old and old['state'] == 'pending':
                    return (503, b'{"error":"ambiguous_upstream_not_repeated"}', '30'), 'ambiguous'
                else:
                    self.write(path, dict(state='pending', request_sha256=digest))
                    wait = self.pending[key] = threading.Event()
                    break
            if not wait.wait(200):
                return (503, b'{"error":"upstream_still_pending"}', '2'), 'pending'
        try:
            value = forward()
            status, response, retry_after = value
            # Only an explicit rate-limit permits another upstream attempt.
            # Ambiguous network errors remain cached failures, not double calls.
            record = dict(state='retryable' if status == 429 and self.retry_rate_limits else 'complete',
                request_sha256=digest, status=status, response=response.decode('utf-8'),
                retry_after=retry_after, response_sha256=hashlib.sha256(response).hexdigest())
            if status == 429:
                record['retry_at'] = self.clock() + max(2., server_delay(
                    {'Retry-After': retry_after}, response.decode(), self.clock()))
            with self.lock:
                self.write(path, record)
            return value, 'forwarded'
        finally:
            with self.lock:
                self.pending.pop(key).set()
