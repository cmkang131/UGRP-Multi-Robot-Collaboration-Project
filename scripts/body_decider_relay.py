"""Finite loopback Mac relay for body-motion decisions (Liquid d1 / Jev).

Keys are read once from the Mac Keychain into process memory: never argv,
logs, receipts or the VM. Requests come only through the reverse tunnel.
Journal rows keep request text, image sha256 (not bytes), response and timing.
"""
import argparse
import base64
import hashlib
import json
import platform
import subprocess
import threading
import time
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

from harness.body_decider_upstream import decide, scrub
from harness.e2e_body_controller import URL, relay_hashes
from harness.model_http import post

ROOT = Path(__file__).resolve().parents[1]
KEYCHAIN = {'liquid': ('ugrp-liquid-d1', 'd1'), 'jev': ('ugrp.typesafe.ai', 'jev')}
MAX_SECONDS = 8 * 3600


def keychain(service, account):
    if platform.system() != 'Darwin':
        raise ValueError('MAC_KEYCHAIN_RELAY_ONLY')
    r = subprocess.run(['security', 'find-generic-password', '-s', service, '-a', account, '-w'],
                       capture_output=True, timeout=15)
    if r.returncode or not r.stdout.strip():
        raise ValueError('KEYCHAIN_UNAVAILABLE:' + service)
    return r.stdout.decode().strip()


def main():
    p = argparse.ArgumentParser()
    p.add_argument('--output', type=Path, required=True)
    p.add_argument('--seconds', type=int, required=True)
    p.add_argument('--listen-port', type=int, choices=(18434,), default=18434)
    p.add_argument('--backends', default='jev')
    a = p.parse_args()
    if not 0 < a.seconds <= MAX_SECONDS:
        raise ValueError('FINITE_RELAY_REQUIRED')
    backends = tuple(x for x in a.backends.split(',') if x)
    a.output.mkdir(parents=True, exist_ok=False)
    keys = {}
    if 'liquid_d1' in backends:
        keys['liquid'] = keychain(*KEYCHAIN['liquid'])
    if 'jev' in backends:
        keys['jev'] = keychain(*KEYCHAIN['jev'])
    secrets = tuple(keys.values())
    receipt = dict(schema='ugrp.body_decider_relay.v1', remote_url=URL, backends=list(backends),
                   source_sha256=relay_hashes(ROOT), checked_unix=time.time(), valid_for_s=a.seconds,
                   key_location='Mac Keychain only', models=dict(liquid_d1=['d1'], jev=['jev-1.13.0']))
    (a.output / 'identity.json').write_text(json.dumps(receipt, indent=2) + '\n')
    lock = threading.Lock()

    def journal(row):
        with lock, (a.output / 'calls.jsonl').open('a') as f:
            f.write(json.dumps(scrub(row, secrets), ensure_ascii=False) + '\n')

    class Handler(BaseHTTPRequestHandler):
        def log_message(self, *args):
            pass

        def do_GET(self):
            if self.path != '/identity':
                self.send_error(404)
                return
            raw = json.dumps(receipt).encode()
            self.send_response(200)
            self.send_header('Content-Length', str(len(raw)))
            self.end_headers()
            self.wfile.write(raw)

        def do_POST(self):
            if self.path != '/v1/body/decide':
                self.send_error(404)
                return
            n = int(self.headers.get('Content-Length', '0'))
            if not 0 < n <= 4_000_000:
                self.send_error(400)
                return
            started = time.time()
            try:
                payload = json.loads(self.rfile.read(n))
                if payload.get('backend') not in backends or relay_hashes(ROOT) != receipt['source_sha256']:
                    raise ValueError('BACKEND_OR_SOURCE')
                img = payload.get('image_jpeg_b64')
                image_sha = hashlib.sha256(base64.b64decode(img)).hexdigest() if img else None
                out = decide(payload, keys=keys, send=post, journal=lambda row: journal(dict(row, image_sha256=image_sha)))
                out = scrub(out, secrets)
                status = 200
            except Exception as exc:
                out, status, image_sha = dict(status='relay_error', error_type=type(exc).__name__), 200, None
            journal(dict(event='reply', call_id=(locals().get('payload') or {}).get('call_id'), wall_s=time.time() - started,
                         image_sha256=image_sha, reply=out))
            raw = json.dumps(out).encode()
            self.send_response(status)
            self.send_header('Content-Type', 'application/json')
            self.send_header('Content-Length', str(len(raw)))
            self.end_headers()
            try:
                self.wfile.write(raw)
            except (BrokenPipeError, ConnectionResetError):
                pass

    server = ThreadingHTTPServer(('127.0.0.1', a.listen_port), Handler)
    timer = threading.Timer(a.seconds, server.shutdown)
    timer.daemon = True
    timer.start()
    try:
        server.serve_forever()
    finally:
        timer.cancel()
        server.server_close()


if __name__ == '__main__':
    main()
