"""Durable pilot send boundary and read-only installed proxy provenance."""
from __future__ import annotations

import json
import os
from pathlib import Path
import subprocess
import threading
import time

from harness.zone_pilot_budget import (EFFECTIVE, PROXY_SHA256, REQUESTED, sha, token_envelope,
                                       usage_total)
from harness.zone_pilot_network import NetworkFence, proxy_address
from harness.zone_send_ledger import SendLedger
from harness.zone_study_llm_transport import no_redirect_opener
from harness.llm_completion import (COMPLETION_POLICY, PROXY_COMPLETION_LIMITATION,
                                     assess_completion, normal_completion, generated_utterances)
from harness.zone_study_prompts_ko import count_tokens


def proxy_profile(source, url):
    proxy_address(url)
    source = Path(source).resolve(strict=True)
    digest = sha(source.read_bytes())
    if digest != PROXY_SHA256:
        raise ValueError('proxy source version is not audited; review settings/retry bound before running')
    return {'source_path': str(source), 'source_sha256': digest, 'version': 'sha256:' + digest,
            'url': url, 'requested_settings': REQUESTED, 'effective_settings': EFFECTIVE,
            'internal_429_retry': True, 'upstream_timeout_s': 300, 'upstream_attempts_per_post_bound': 2,
            'completion_policy': COMPLETION_POLICY,
            'completion_limitation': dict(PROXY_COMPLETION_LIMITATION),
            'accounting': 'option_b_full_two_attempt_reservation_no_refunds'}


def runtime_identity(profile, pid):
    """Local process/listener evidence. Never starts/restarts the installed proxy."""
    if type(pid) is not int or pid <= 0:
        raise ValueError('explicit running proxy PID required')
    command = subprocess.run(['ps', '-p', str(pid), '-o', 'command='], check=True,
                             text=True, capture_output=True).stdout.strip()
    started = subprocess.run(['ps', '-p', str(pid), '-o', 'lstart='], check=True,
                             text=True, capture_output=True).stdout.strip()
    start_s = time.mktime(time.strptime(started, '%a %b %d %H:%M:%S %Y'))
    source = Path(profile['source_path'])
    if str(source) not in command or start_s + 1 < source.stat().st_mtime:
        raise ValueError('proxy runtime/source mismatch: process must start after audited source was saved')
    host, port = proxy_address(profile['url'])
    listeners = subprocess.run(['lsof', '-nP', '-a', '-p', str(pid), f'-iTCP:{port}',
                                '-sTCP:LISTEN', '-Fn'], check=True, capture_output=True,
                               text=True).stdout.splitlines()
    if f'n{host}:{port}' not in listeners:
        raise ValueError('proxy PID is not the explicit loopback URL listener')
    return {'pid': pid, 'started_local': started, 'command_sha256': sha(command.encode()),
            'source_sha256': profile['source_sha256'], 'url': profile['url'],
            'verification': 'pid_listener_and_process_started_after_source_mtime'}


def log_cursor(path):
    if path is None:
        return None
    try:
        stat = Path(path).stat()
        return {'path': str(Path(path).resolve()), 'inode': stat.st_ino, 'offset': stat.st_size}
    except OSError:
        return None


def log_window(cursor):
    """Only event categories and hashes; never copy unrelated proxy log content.

    This alone is not correlation. The separate exclusive-window verifier
    checks padded wall-time bounds, all POSTs, raw bytes and exact response usage.
    """
    if cursor is None:
        return {'available': False, 'correlated': False}
    path = Path(cursor['path'])
    try:
        stat = path.stat()
        if stat.st_ino != cursor['inode'] or stat.st_size < cursor['offset']:
            return {'available': False, 'correlated': False, 'reason': 'rotated'}
        with path.open('rb') as stream:
            stream.seek(cursor['offset'])
            raw = stream.read(1_000_000)
        events = []
        for line in raw.splitlines():
            for marker in (b'transient_429_retry', b'complete_http_error', b'complete_exception', b'POST /v1/chat/completions'):
                if marker in line:
                    events.append({'kind': marker.decode(), 'line_sha256': sha(line)})
        return {**cursor, 'end_offset': cursor['offset'] + len(raw), 'sha256': sha(raw),
                'events': events, 'available': True, 'correlated': False}
    except OSError:
        return {'available': False, 'correlated': False, 'reason': 'unreadable'}


class PilotSendLedger(SendLedger):
    """Persists each send BEFORE network I/O; settles BEFORE any reply can act.

    Offline tests inject a wire with identical request/response semantics.
    Real mode always uses the private non-redirecting opener under NetworkFence.
    """
    def __init__(self, *, store_dir, budget, profile, context, runtime=None, proxy_log=None, wire=None):
        self.budget, self.profile, self.context = budget, profile, dict(context)
        self.runtime, self.proxy_log = runtime, proxy_log
        self.live = wire is None
        self.guard = NetworkFence(profile['url'] if self.live else None)
        opener = no_redirect_opener()

        def guarded_wire(request, *, timeout):
            with self.guard.wire():
                return opener.open(request, timeout=timeout)

        super().__init__(wire or guarded_wire, store_dir=store_dir)

    def _store(self, row, kind, data):
        if kind == 'response':
            row['response_received_at_ns'] = time.time_ns()
            # Keep known usage even when response-file storage fails.
            response = None
            try:
                response = json.loads(data)
                row['provider_usage'] = response.get('usage')
                row['proxy_response_id'] = response.get('id')
            except (ValueError, AttributeError):
                pass
            row['completion'] = assess_completion(response, study_json=True)
            # Preserve the actual generated SIM costs even if storage/timeout
            # prevents the response bytes from reaching the client.
            try:
                text = response['choices'][0]['message']['content']
            except (KeyError, IndexError, TypeError):
                text = None
            if isinstance(text, str):
                row['sim_generated'] = {'output_tokens': count_tokens(text),
                                        'utterances': generated_utterances(text)}
        super()._store(row, kind, data)
        if kind == 'request':
            if row['url'] != self.profile['url'] or row['method'] != 'POST':
                raise ValueError('pilot only authorises POST to the recorded proxy URL')
            envelope = token_envelope(data)
            row['effective_settings'] = dict(EFFECTIVE)
            row['proxy_source_sha256'] = self.profile['source_sha256']
            row['proxy_correlation_id'] = 'ugrp-' + sha(
                f'{self.context["trial_id"]}:{row["call_id"]}:{row["seq"]}'.encode())[:32]
            record = {**self.context, 'call_id': row['call_id'], 'ledger_seq': row['seq'],
                      'body_sha256': row['body_sha256'], 'request_path': str(self.store_dir / row['request_path']),
                      'proxy_url': row['url'], 'proxy_source_sha256': self.profile['source_sha256'],
                      'proxy_correlation_id': row['proxy_correlation_id']}
            reserved = self.budget.reserve(record, envelope)
            row['reservation_id'] = reserved['reservation_id']
            row['reserved_attempts'] = reserved['reserved_attempts']
            row['reserved_tokens'] = reserved['reserved_tokens']
            row['send_started_at_ns'] = time.time_ns()

    def _send(self, call_id, actor, request, timeout):
        if threading.get_ident() != self._thread:
            raise RuntimeError('single-thread pilot ledger required')
        if self.live:
            if self.runtime is None:
                raise RuntimeError('running proxy identity required')
            # Never execute/import the installed proxy. Detect edits or a dead
            # process after preflight; the initial listener/start check is saved.
            if sha(Path(self.profile['source_path']).read_bytes()) != self.profile['source_sha256']:
                raise RuntimeError('installed proxy changed during pilot')
            os.kill(self.runtime['pid'], 0)
            identity = self.budget.meta['identity']
            root = Path(identity['source_root'])
            if any(sha((root / name).read_bytes()) != digest
                   for name, digest in identity['files'].items()):
                raise RuntimeError('frozen study source/input changed during pilot')
        correlation_id = 'ugrp-' + sha(f'{self.context["trial_id"]}:{call_id}:{len(self.entries) + 1}'.encode())[:32]
        request.add_header('X-UGRP-Call-ID', correlation_id)
        before = len(self.entries)
        cursor = log_cursor(self.proxy_log)
        started = time.monotonic()
        failed = True
        try:
            response = super()._send(call_id, actor, request, timeout)
            if timeout is not None and time.monotonic() - started > timeout:
                self.entries[-1]['late'] = True
                raise TimeoutError('late response discarded after send deadline')
            failed = False
            return response
        finally:
            if len(self.entries) > before:
                row = self.entries[-1]
                if 'reservation_id' in row:
                    # If settlement storage fails this raises; the durable
                    # reserved_unknown row remains spent and no action escapes.
                    self.budget.settle(row['reservation_id'],
                                       status=('failed' if failed else 'response_received'
                                               if normal_completion(row.get('completion')) else 'completion_rejected'),
                                       completion=row.get('completion'),
                                       provider_usage=row.get('provider_usage'),
                                       proxy_response_id=row.get('proxy_response_id'),
                                       response_sha256=row.get('response_sha256'),
                                       wire_error=row.get('wire_error'), late=row.get('late', False),
                                       ledger=dict(row), proxy_log_window=log_window(cursor))
