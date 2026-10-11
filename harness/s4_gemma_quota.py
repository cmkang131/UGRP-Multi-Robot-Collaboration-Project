"""Mac-wide, durable token bucket plus rolling-window guard (no credentials).

One path for standard AND fallback relays. Reservations survive process death;
uncertain sends are not refunded. The caller retries local 429 while SIM holds.
"""
from contextlib import contextmanager
from datetime import datetime, timedelta
import fcntl
import json
import math
from pathlib import Path
import time
from zoneinfo import ZoneInfo

ROOT = Path('/Users/changmin/projects/ugrp/outputs/gemma-quota-v1')
LIMITS = dict(tpm=16000, rpm=30, rpd=14400, headroom=.1)
TPM, RPM, RPD = 14400, 27, 12960
PACIFIC = ZoneInfo('America/Los_Angeles')


class SharedQuota:
    def __init__(self, root=ROOT, *, clock=time.time, limits=None):
        self.root, self.clock = Path(root), clock
        self.limits = limits or dict(tpm=TPM, rpm=RPM, rpd=RPD)
        self.root.mkdir(parents=True, exist_ok=True)

    @contextmanager
    def locked(self):
        with (self.root/'bucket.lock').open('a') as lock:
            fcntl.flock(lock, fcntl.LOCK_EX)
            path = self.root/'bucket.json'
            state = json.loads(path.read_text()) if path.exists() else {}
            yield state
            tmp = path.with_suffix('.new')
            tmp.write_text(json.dumps(state)+'\n'); tmp.replace(path)

    def reserve(self, tokens, *, request_id, request_sha256):
        with self.locked() as state:
            return self.reserve_state(state, tokens, request_id=request_id,
                                      request_sha256=request_sha256)

    def availability(self, s, tokens):
        tpm, rpm, rpd = (self.limits[k] for k in ('tpm', 'rpm', 'rpd'))
        if type(tokens) is not int or not 0 < tokens <= tpm:
            raise ValueError('request exceeds the shared token bucket capacity')
        now = self.clock()
        local = datetime.fromtimestamp(now, PACIFIC)
        if s.get('day') != local.date().isoformat():
            s.update(day=local.date().isoformat(), day_requests=0)
        elapsed = max(0, now-s.get('updated', now))
        s['tokens'] = min(tpm, s.get('tokens', tpm)+elapsed*tpm/60)
        s['requests'] = min(rpm, s.get('requests', rpm)+elapsed*rpm/60)
        s['updated'] = now
        s['window'] = [r for r in s.get('window', []) if r['at'] > now-60]
        wait = max(0, (tokens-s['tokens'])*60/tpm, (1-s['requests'])*60/rpm,
                   s.get('hold_until', 0)-now)
        if s['day_requests'] >= rpd:
            wait = max(wait, ((local+timedelta(days=1)).replace(hour=0,minute=0,second=0,microsecond=0).timestamp()-now))
        rows = list(s['window'])
        while len(rows) >= rpm or sum(r['tokens'] for r in rows)+tokens > tpm:
            wait = max(wait, rows.pop(0)['at']+60-now)
        remaining = (min(s['tokens'], tpm-sum(r['tokens'] for r in s['window']))/tpm,
                     min(s['requests'], rpm-len(s['window']))/rpm,
                     max(0, rpd-s['day_requests'])/rpd)
        return wait, (min(remaining), sum(remaining))

    def reserve_state(self, s, tokens, *, request_id, request_sha256, key_index=None):
        wait, _ = self.availability(s, tokens)
        admitted = wait <= 0
        if admitted:
            s['tokens'] -= tokens; s['requests'] -= 1; s['day_requests'] += 1
            s['window'].append(dict(at=self.clock(), tokens=tokens))
        row = dict(at=self.clock(), request_id=request_id, request_sha256=request_sha256,
                   reserved_tokens=tokens, admitted=admitted, retry_after_s=math.ceil(wait),
                   effective_limits=dict(self.limits),
                   accounting='input + max output; conservative versus input-only TPM')
        if key_index is not None:
            row['key_index'] = key_index
        with (self.root/'reservations.jsonl').open('a') as f:
            f.write(json.dumps(row)+'\n')
        return row
