"""Finite, loopback-only S4 forwarding through the existing audited Mac proxy."""
import argparse
import hashlib
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
import json
from pathlib import Path
import threading
import time
from urllib.request import Request
from urllib.error import HTTPError

from harness.zone_study_llm_driver import live_proxy, load_registry
from harness.zone_study_llm_transport import no_redirect_opener
from harness.s4_live_transport import URL
from harness.s4_relay_journal import Journal


def main():
    p = argparse.ArgumentParser()
    p.add_argument('--proxy-pid', type=int)
    p.add_argument('--output', type=Path, required=True)
    p.add_argument('--seconds', type=int, default=3600)
    p.add_argument('--idempotent', action='store_true')
    p.add_argument('--gemma-fallback', action='store_true', help='DEV only; default off')
    p.add_argument('--driver-profile',choices=('main_study_gemini_v1','study_gemma4_31b_v1'),
                   default='main_study_gemini_v1')
    p.add_argument('--gemma-state', type=Path,
        default=Path('/Users/changmin/projects/ugrp/outputs/gemma-fallback'))
    a = p.parse_args()
    if not 0 < a.seconds <= 14400: raise ValueError('finite <=4h relay required')
    a.output.mkdir(parents=True, exist_ok=False)
    single=a.driver_profile=='study_gemma4_31b_v1'
    if single and a.gemma_fallback:raise ValueError('single model cannot fallback')
    profile = load_registry()['driver_profiles'][a.driver_profile]
    if single:
        source=Path(__file__).parent/'gemma_fallback_proxy.py'
        proxy=dict(source_sha256=hashlib.sha256(source.read_bytes()).hexdigest())
        runtime=dict(provider='google_aistudio_gemma',key_location='Mac Keychain only')
    else:
        if a.proxy_pid is None:raise ValueError('Gemini proxy PID required')
        proxy, runtime = live_proxy(profile, a.proxy_pid)
    fallback = None
    if a.gemma_fallback or single:
        from scripts.gemma_fallback_proxy import Gemma
        registered = profile['model']['model'] if single else load_registry()['driver_profiles']['dev_gemini_gemma_fallback_v1']['fallback']['model_id']
        fallback = Gemma(a.gemma_state, expected_model=registered,standard=single,
                         expected_version='001' if single else None)
        fallback.require_image_probe()
    receipt = dict(schema='ugrp.s4_ssh_proxy.v1', remote_url=URL, proxy=proxy,
        runtime=runtime, checked_unix=time.time(), valid_for_s=a.seconds, audit_per_post=True,
        authentication='existing_mac_proxy_no_credentials_transferred')
    (a.output/'identity.json').write_text(json.dumps(receipt, indent=2)+'\n')
    lock = threading.Lock()
    journal = Journal(a.output/'responses', retry_rate_limits=single or not a.gemma_fallback) if a.idempotent or fallback else None
    receipt['idempotent_response_journal'] = bool(journal)
    if fallback:
        from scripts.gemma_fallback_proxy import PROFILE
        receipt.update(driver_profile=PROFILE, dev_only=True, gemma_fallback=dict(
            model_id=fallback.model_id, provider='google_aistudio_gemma',
            model_source='models.list', image_input_confirmed=True,
            source_sha256=hashlib.sha256((Path(__file__).parent/'gemma_fallback_proxy.py').read_bytes()).hexdigest(),
            attempts_per_request=1, key_location='macOS Keychain: ugrp-gemma-aistudio'))
        if single:
            receipt.update(driver_profile=a.driver_profile,single_model=True,gemma_model_pin=dict(
                model_id=fallback.model_id,version=fallback.model['version']),
                global_quota=dict(tpm=14400,rpm=27,rpd=12960),fallback_enabled=False)
    (a.output/'identity.json').write_text(json.dumps(receipt, indent=2)+'\n')

    class Handler(BaseHTTPRequestHandler):
        def log_message(self, *args): pass

        def do_GET(self):
            if self.path != '/identity': self.send_error(404); return
            self.send_response(200); self.end_headers()
            self.wfile.write(json.dumps(receipt).encode())

        def do_POST(self):
            if self.path != '/v1/chat/completions': self.send_error(404); return
            n = int(self.headers.get('Content-Length', '0'))
            call_id = self.headers.get('X-UGRP-Call-ID', '')
            if not 0 < n <= 8_000_000 or not call_id.startswith('s4live1-'):
                self.send_error(400); return
            body = self.rfile.read(n)
            started = time.time()
            key = self.headers.get('X-UGRP-Idempotency-Key', '')
            def forward():
                retry_after = None
                try:
                    current = dict(source_sha256=hashlib.sha256(source.read_bytes()).hexdigest()) if single else live_proxy(profile,a.proxy_pid)[0]
                    if current != proxy: raise ValueError('proxy identity changed')
                    if fallback and hashlib.sha256((Path(__file__).parent/'gemma_fallback_proxy.py').read_bytes()).hexdigest() != receipt['gemma_fallback']['source_sha256']:
                        raise ValueError('fallback source changed')
                    def primary():
                        request = Request(profile['proxy_url'], data=body, headers={
                            'Content-Type': 'application/json', 'X-UGRP-Call-ID': call_id})
                        try:
                            with no_redirect_opener().open(request, timeout=180) as response:
                                return response.status, response.read(8_000_000), None
                        except HTTPError as exc:
                            return exc.code, exc.read(8_000_000), exc.headers.get('Retry-After')
                    if single:
                        status,raw,retry_after=fallback.complete(body,call_id,idempotency_key=key)
                    elif fallback:
                        from scripts.gemma_fallback_proxy import route
                        status, raw, retry_after = route(primary, body, call_id, fallback=fallback, idempotency_key=key)
                    else:
                        status, raw, retry_after = primary()
                except Exception as exc:
                    status = 502
                    raw = json.dumps({'error': 'relay_identity_or_transport', 'type': type(exc).__name__}).encode()
                return status, raw, retry_after
            value, disposition = journal.call(key, body, forward) if journal else (forward(), 'legacy')
            status, raw, retry_after = value
            row = dict(call_id=call_id, started_unix=started, wall_s=time.time()-started,
                status=status, request_sha256=hashlib.sha256(body).hexdigest(),
                response_sha256=hashlib.sha256(raw).hexdigest(), retry_after=retry_after,
                proxy_source_sha256=proxy['source_sha256'], idempotency_key=key,
                disposition=disposition, upstream_forwarded=disposition in ('forwarded', 'legacy'))
            if fallback:
                try:
                    response = json.loads(raw)
                    row.update(response_model=response.get('model'), provider=response.get('provider'),
                        route=response.get('ugrp_route'))
                except (ValueError, AttributeError): pass
            with lock, (a.output/'receipts.jsonl').open('a') as f:
                f.write(json.dumps(row)+'\n')
            self.send_response(status); self.send_header('Content-Type', 'application/json')
            if retry_after is not None: self.send_header('Retry-After', retry_after)
            self.send_header('Content-Length', str(len(raw))); self.end_headers()
            try: self.wfile.write(raw)
            except (BrokenPipeError, ConnectionResetError): pass  # journal already durable

    server = ThreadingHTTPServer(('127.0.0.1', 18392), Handler)
    timer = threading.Timer(a.seconds, server.shutdown); timer.daemon = True; timer.start()
    try: server.serve_forever()
    finally: timer.cancel(); server.server_close()


if __name__ == '__main__': main()
