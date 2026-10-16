"""Task-owned Mac loopback relay, reusing the existing pinned upstream/journal.

No runtime deadline: shut down the owned process after the batch. No key or
credentials are put in identity.json, console output or the VM.
"""
import argparse
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
import json
from pathlib import Path
import platform
import re
import time
from urllib.request import Request

from harness.e2e_warp_runtime import SYSTEM, encode, sha
from scripts.openrouter_upstream import OpenRouter, config, keychain_key
from harness.zone_study_llm_transport import no_redirect_opener


def preflight():
    if platform.system() != 'Darwin':
        raise ValueError('Mac-only credentials boundary')
    from scripts.model_endpoint_watch import check
    root = Path(__file__).resolve().parents[1]
    alerts = check(json.loads((root/'configs/model_endpoints.json').read_text()))
    if alerts:
        raise ValueError('MODEL_ENDPOINT_ALERT:' + encode(alerts))
    req = Request('https://openrouter.ai/api/v1/credits',
                  headers={'Authorization': 'Bearer '+keychain_key()})
    with no_redirect_opener().open(req, timeout=30) as response:
        data = json.load(response)['data']
    balance = float(data['total_credits']) - float(data['total_usage'])
    if balance <= 0:
        raise ValueError('OPENROUTER_BALANCE_EXHAUSTED')
    return dict(checked_unix=time.time(), alerts=alerts, balance_usd=balance,
                scope='provider credits API; actual final usage remains in upstream ledger')


def validate(raw, call_id):
    if not re.fullmatch(r'e2ewarp-[a-zA-Z0-9_-]+:w\d+:r[123]:\d+', call_id):
        raise ValueError('e2ewarp namespace only')
    body = json.loads(raw)
    messages = body.get('messages', [])
    if len(messages) != 3 or messages[0] != dict(role='system', content=SYSTEM):
        raise ValueError('new cache-ordered own-input prompt required')
    if not isinstance(messages[1]['content'], str):
        raise ValueError('static text prefix required')
    content = messages[-1]['content']
    if len(content) != 2 or content[0]['type'] != 'text' or content[1]['type'] != 'image_url':
        raise ValueError('dynamic text then one own RGB image required')
    if not content[1]['image_url']['url'].startswith('data:image/jpeg;base64,'):
        raise ValueError('embedded own JPEG only')
    return body


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('--output', type=Path, required=True)
    p.add_argument('--port', type=int, default=18626)
    p.add_argument('--serve', action='store_true')
    a = p.parse_args()
    receipt = preflight()
    a.output.mkdir(parents=True, exist_ok=False)
    receipt.update(upstream=config(), cache_order=['system', 'static', 'dynamic', 'image'],
                   own_rgb_count=1, credentials_on_vm=False, wall_cap=None)
    (a.output/'identity.json').write_text(encode(receipt)+'\n')
    print(encode(receipt), flush=True)
    if not a.serve:
        return
    upstream = OpenRouter(a.output/'upstream')

    class Handler(BaseHTTPRequestHandler):
        def log_message(self, *args):
            pass

        def do_GET(self):
            if self.path != '/identity':
                self.send_error(404)
                return
            self.send_response(200)
            self.end_headers()
            self.wfile.write(encode(receipt).encode())

        def do_POST(self):
            try:
                if self.path != '/v1/chat/completions':
                    raise ValueError('invalid path')
                length = int(self.headers.get('Content-Length', 0))
                if not 0 < length <= 8_000_000:  # existing s4 relay transport envelope
                    raise ValueError('invalid transport length')
                raw = self.rfile.read(length)
                call_id = self.headers.get('X-UGRP-Call-ID', '')
                validate(raw, call_id)
                status, result, retry = upstream.complete(raw, call_id, idempotency_key=call_id)
            except (KeyError, TypeError, ValueError) as exc:
                status, result, retry = 400, encode(dict(error=str(exc))).encode(), None
            self.send_response(status)
            self.send_header('Content-Type', 'application/json')
            if retry:
                self.send_header('Retry-After', retry)
            self.end_headers()
            self.wfile.write(result)

    server = ThreadingHTTPServer(('127.0.0.1', a.port), Handler)
    try:
        server.serve_forever()
    finally:
        server.server_close()


if __name__ == '__main__':
    main()
