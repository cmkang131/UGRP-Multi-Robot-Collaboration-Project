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


def main():
    p = argparse.ArgumentParser()
    p.add_argument('--proxy-pid', type=int, required=True)
    p.add_argument('--output', type=Path, required=True)
    p.add_argument('--seconds', type=int, default=3600)
    a = p.parse_args()
    if not 0 < a.seconds <= 3600: raise ValueError('finite <=1h relay required')
    a.output.mkdir(parents=True, exist_ok=False)
    profile = load_registry()['driver_profiles']['main_study_gemini_v1']
    proxy, runtime = live_proxy(profile, a.proxy_pid)
    receipt = dict(schema='ugrp.s4_ssh_proxy.v1', remote_url=URL, proxy=proxy,
        runtime=runtime, checked_unix=time.time(), audit_per_post=True,
        authentication='existing_mac_proxy_no_credentials_transferred')
    (a.output/'identity.json').write_text(json.dumps(receipt, indent=2)+'\n')
    lock = threading.Lock()

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
            status, raw = 502, b'{"error":"relay unavailable"}'
            try:
                current, _ = live_proxy(profile, a.proxy_pid)
                if current != proxy: raise ValueError('proxy identity changed')
                request = Request(profile['proxy_url'], data=body, headers={
                    'Content-Type': 'application/json', 'X-UGRP-Call-ID': call_id})
                try:
                    with no_redirect_opener().open(request, timeout=180) as response:
                        status, raw = response.status, response.read(8_000_000)
                except HTTPError as exc:
                    status, raw = exc.code, exc.read(8_000_000)
            except Exception as exc:
                raw = json.dumps({'error': 'relay_identity_or_transport', 'type': type(exc).__name__}).encode()
            row = dict(call_id=call_id, started_unix=started, wall_s=time.time()-started,
                status=status, request_sha256=hashlib.sha256(body).hexdigest(),
                response_sha256=hashlib.sha256(raw).hexdigest(), proxy_source_sha256=proxy['source_sha256'])
            with lock, (a.output/'receipts.jsonl').open('a') as f:
                f.write(json.dumps(row)+'\n')
            self.send_response(status); self.send_header('Content-Type', 'application/json')
            self.send_header('Content-Length', str(len(raw))); self.end_headers()
            self.wfile.write(raw)

    server = ThreadingHTTPServer(('127.0.0.1', 18392), Handler)
    timer = threading.Timer(a.seconds, server.shutdown); timer.daemon = True; timer.start()
    try: server.serve_forever()
    finally: timer.cancel(); server.server_close()


if __name__ == '__main__': main()
