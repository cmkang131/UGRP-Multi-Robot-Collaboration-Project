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
    def __init__(self, root=ROOT, *, clock=time.time):
        self.root, self.clock = Path(root), clock
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
        if type(tokens) is not int or not 0 < tokens <= TPM:
            raise ValueError('request exceeds the shared token bucket capacity')
        now = self.clock()
        with self.locked() as s:
            local = datetime.fromtimestamp(now, PACIFIC)
            if s.get('day') != local.date().isoformat():
                s.update(day=local.date().isoformat(), day_requests=0)
            elapsed = max(0, now-s.get('updated', now))
            s['tokens'] = min(TPM, s.get('tokens', TPM)+elapsed*TPM/60)
            s['requests'] = min(RPM, s.get('requests', RPM)+elapsed*RPM/60)
            s['updated'] = now
            s['window'] = [r for r in s.get('window', []) if r['at'] > now-60]
            wait = max(0, (tokens-s['tokens'])*60/TPM, (1-s['requests'])*60/RPM)
            if s['day_requests'] >= RPD:
                wait = max(wait, ((local+timedelta(days=1)).replace(hour=0,minute=0,second=0,microsecond=0).timestamp()-now))
            rows = list(s['window'])
            while len(rows) >= RPM or sum(r['tokens'] for r in rows)+tokens > TPM:
                wait = max(wait, rows.pop(0)['at']+60-now)
            admitted = wait <= 0
            if admitted:
                s['tokens'] -= tokens; s['requests'] -= 1; s['day_requests'] += 1
                s['window'].append(dict(at=now,tokens=tokens))
            row = dict(at=now, request_id=request_id, request_sha256=request_sha256,
                       reserved_tokens=tokens, admitted=admitted, retry_after_s=math.ceil(wait),
                       effective_limits=dict(tpm=TPM,rpm=RPM,rpd=RPD),
                       accounting='input + max output; conservative versus input-only TPM')
            with (self.root/'reservations.jsonl').open('a') as f:
                f.write(json.dumps(row)+'\n')
            return row
