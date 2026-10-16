"""Mac-only opt-in OpenAI adapter; leaves the default API/model untouched."""
import json
import time
from pathlib import Path
from urllib.error import HTTPError
from urllib.request import Request

from harness.s4_relay_journal import Journal
from harness.zone_study_llm_transport import no_redirect_opener
from scripts.llmhost_common import check_alerts, digest, identity, images, loopback


def upstream_body(request, candidate):
    if request.get('stream') or request.get('tools'):
        raise ValueError('stream_and_tools_unsupported')
    if request.get('model') != 'gemma-4-31b-it':
        raise ValueError('registered_driver_model_required')
    images(request)
    # Same reasoning-off policy as the current Gemma API cohort, explicit in identity.
    body = {k: v for k, v in request.items()
            if k not in ('reasoning_effort', 'provider', 'usage')}
    body.update(model=identity(candidate)['model'],
                chat_template_kwargs={'enable_thinking': False})
    return body


def http_send(body, endpoint):
    req = Request(loopback(endpoint), data=json.dumps(body).encode(),
                  headers={'Content-Type': 'application/json'})
    try:
        # 180s is the existing relay's transport watchdog, never an action/search cap.
        with no_redirect_opener().open(req, timeout=180) as response:
            return response.status, response.read(8_000_000), None
    except HTTPError as exc:
        return exc.code, exc.read(8_000_000), exc.headers.get('Retry-After')


class SelfGCP:
    standard = True

    def __init__(self, root, candidate, *, send=http_send):
        check_alerts()
        self.root, self.candidate, self.send = Path(root), candidate, send
        self.root.mkdir(parents=True, exist_ok=True)
        self.config = identity(candidate)
        self.model_id = self.config['model']
        self.journal = Journal(self.root / 'responses', retry_rate_limits=True, cache_errors=False)

    def complete(self, raw, request_id, *, idempotency_key=None):
        return self.journal.call(idempotency_key or digest(request_id.encode()), raw,
                                 lambda: self._complete(raw, request_id))[0]

    def _complete(self, raw, request_id):
        check_alerts()
        request = json.loads(raw)
        body = upstream_body(request, self.candidate)
        started = time.monotonic()
        status, response, retry = self.send(body, self.config['endpoint'])
        data = json.loads(response)
        if not isinstance(data, dict):
            raise ValueError('invalid_server_response')
        if status == 200 and data.get('model') != self.model_id:
            status, data = 502, {'error': 'served_model_mismatch'}
        data.update(provider='self_gcp_l4', upstream='self_gcp_l4',
                    ugrp_self_gcp=self.config,
                    ugrp_upstream_wall_s=time.monotonic() - started)
        row = dict(request_id=request_id, status=status, request_sha256=digest(raw),
                   wire_sha256=digest(json.dumps(body).encode()), image_sha256=images(request),
                   usage=data.get('usage'), identity=self.config,
                   response_sha256=digest(response), attempts=1)
        with (self.root / 'ledger.jsonl').open('a') as f:
            f.write(json.dumps(row) + '\n')
        return status, json.dumps(data).encode(), retry
