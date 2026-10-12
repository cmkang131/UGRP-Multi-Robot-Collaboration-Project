"""Opt-in synchronous 429 recovery: every POST audited, no physics during wall waits.

The scheduler and wire are single-threaded. Retrying the identical request here
cannot advance a backend, deliver a message, or release a command. Only a final
validated completion can reach finish_call. Unknown upstream usage stays unknown.
"""
from dataclasses import replace
from email.utils import parsedate_to_datetime
import hashlib
import json
import os
import re
import time
from urllib.error import HTTPError

from harness.s4_live_transport import TunnelLedger
from harness.s4_llm_host import _Transport
from harness.zone_event_scheduler import TransportFailure
from harness.zone_sim_cost import Attempt


def server_delay(headers, text, now):
    value = (headers or {}).get('Retry-After')
    if value:
        try:
            return max(0., float(value))
        except ValueError:
            try:
                return max(0., parsedate_to_datetime(value).timestamp()-now)
            except (ValueError, TypeError, OverflowError):
                pass
    # This proxy sometimes forwards only an explicit quota reset in the body.
    match = re.search(r'Resets in\s+(?:(\d+)h)?(?:(\d+)m)?(?:(\d+)s)?', text or '', re.I)
    return sum(int(v or 0)*factor for v,factor in zip(match.groups(),(3600,60,1))) if match else 0.


class RetryMixin:
    def __init__(self, *args, retry_429=False, sleep=time.sleep, monotonic=time.monotonic,
                 wall=time.time, **kwargs):
        super().__init__(*args, **kwargs)
        self.retry_429 = retry_429
        self.retry_events = []
        self._retry_sleep, self._retry_clock, self._retry_wall = sleep, monotonic, wall

    def _send(self, call_id, actor, request, timeout):
        if not self.retry_429:
            return super()._send(call_id, actor, request, timeout)
        failed = []; began = self._retry_clock()
        for attempt in range(7):  # initial + at most six retries, budgeted individually
            try:
                response = super()._send(call_id, actor, request, timeout)
            except HTTPError as exc:
                row = self.entries[-1]
                if exc.code != 429:
                    raise
                failed.append(row)
                detail = row.get('error_response') or {}
                jitter = int(hashlib.sha256(f'{self.run_key}:{call_id}:{attempt}'.encode()).hexdigest()[:8],16)/2**32
                delay = max(min(60., 2.**(attempt+1))*(1.+.2*jitter),
                    server_delay({'Retry-After':detail.get('retry_after')},detail.get('excerpt'),self._retry_wall()))
                remaining = 300.-(self._retry_clock()-began)
                event = dict(call_id=call_id, seq=row['seq'], retry=attempt+1, delay_s=delay,
                    wait_started_unix=self._retry_wall(), same_request_sha256=row['body_sha256'],
                    physics_held='synchronous_no_backend_advance', status='WAIT')
                snapshot = getattr(self, 'retry_snapshot', lambda: None)
                event['before'] = snapshot()
                if attempt == 6 or delay > remaining:
                    event['status']='EXHAUSTED'; self._retry_record(event)
                    raise  # never shorten Retry-After or hammer a multi-hour quota
                row['retry_wait_s'] = delay
                self._retry_record(event)
                self._retry_sleep(delay)
                after = snapshot()
                self._retry_record({**event,'status':'RESUMED','after':after,
                    'hold_verified':event['before']==after,
                    'wait_wall_s':self._retry_wall()-event['wait_started_unix']})
                if after != event['before']:
                    raise RuntimeError('SIM_OR_COMMAND_CHANGED_DURING_API_WAIT')
            else:
                for row in failed:row['rate_limit_recovered']=True
                return response

    def _retry_record(self, event):
        self.retry_events.append(event)
        if self.store_dir is not None:
            with (self.store_dir.parent/'retry-events.jsonl').open('a') as f:
                f.write(json.dumps(event)+'\n');f.flush();os.fsync(f.fileno())
            (self.store_dir.parent/'retry-state.json').write_text(json.dumps(event)+'\n')


class RetryLedger(RetryMixin, TunnelLedger):
    pass


class RetryTransport(_Transport):
    """Account for each retry, keeping one logical response/action and message set."""
    def reply(self, call):
        try:
            reply = super().reply(call)
        except TransportFailure as exc:
            n=self.send_ledger.sends(call.call_id)
            if n>len(exc.attempts):
                exc.attempts=tuple(Attempt(outcome='error') for _ in range(n-len(exc.attempts)))+exc.attempts
                exc.sent_attempts=n;exc.usage_known=False
            raise
        n=self.send_ledger.sends(call.call_id)
        if n>len(reply.attempts):
            failures=tuple(Attempt(outcome='error',input_tokens=reply.attempts[-1].input_tokens)
                for _ in range(n-len(reply.attempts)))
            return replace(reply,attempts=failures+reply.attempts,sent_attempts=n,usage_known=False)
        return reply
