"""Default-off, same-logical-request retry while the synchronous SIM stays held."""
import hashlib
from http.client import HTTPException
from urllib.error import HTTPError, URLError

from harness.s4_call_recovery import RetryMixin
from harness.s4_live_transport import TunnelLedger
from harness.zone_study_llm_driver import HostError


class TunnelRecoveryMixin(RetryMixin):
    def __init__(self, *args, tunnel_recovery=False, **kwargs):
        super().__init__(*args, **kwargs)
        self.tunnel_recovery = tunnel_recovery

    def _send(self, call_id, actor, request, timeout):
        if not self.tunnel_recovery:
            return super()._send(call_id, actor, request, timeout)
        # Body and its request_id stay byte-identical. Per-POST audit IDs still
        # differ; the relay journal binds this logical ID to exactly one body.
        key = hashlib.sha256(f'{self.run_key}:{call_id}'.encode()).hexdigest()
        request.add_header('X-UGRP-Idempotency-Key', key)
        began = self._retry_clock()
        failures = []
        for attempt in range(7):
            try:
                result = super()._send(call_id, actor, request, timeout)
            except (URLError, TimeoutError, ConnectionError, HTTPException) as exc:
                if isinstance(exc, HTTPError) and exc.code not in (502, 503, 504):
                    raise
                row = self.entries[-1]
                failures.append(row)
                delay = min(30., 2. ** (attempt + 1))
                snapshot = getattr(self, 'retry_snapshot', lambda: None)
                event = dict(kind='tunnel', call_id=call_id, seq=row['seq'],
                    retry=attempt + 1, idempotency_key=key, delay_s=delay,
                    same_request_sha256=row['body_sha256'], before=snapshot(),
                    wait_started_unix=self._retry_wall(), status='WAIT',
                    physics_held='synchronous_no_backend_advance')
                if attempt == 6 or self._retry_clock() - began + delay > 600:
                    event['status'] = 'EXHAUSTED'
                    self._retry_record(event)
                    self.fatal = HostError('S4_TUNNEL_RECOVERY_EXHAUSTED')
                    raise self.fatal from exc
                self._retry_record(event)
                self._retry_sleep(delay)
                after = snapshot()
                self._retry_record({**event, 'status': 'RESUMED', 'after': after,
                    'hold_verified': after == event['before'],
                    'wait_wall_s': self._retry_wall()-event['wait_started_unix']})
                if after != event['before']:
                    self.fatal = HostError('SIM_OR_COMMAND_CHANGED_DURING_TUNNEL_WAIT')
                    raise self.fatal
            else:
                for row in failures:
                    row['tunnel_recovered'] = True
                    row['idempotency_key'] = key
                return result


class RecoveryLedger(TunnelRecoveryMixin, TunnelLedger):
    def __init__(self, **kwargs):
        super().__init__(**kwargs)
        if self.tunnel_recovery and not self.receipt.get('idempotent_response_journal'):
            raise HostError('tunnel retry requires idempotent Mac relay')
