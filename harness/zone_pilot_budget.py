"""Durable, conservative provider budget; independent of the frozen SIM cost.

One proxy POST reserves TWO upstream attempts and two complete token envelopes.
No refund, even for known usage: a proxy response only describes the last
upstream attempt. SQLite commits the reservation before the wire can run.
Interrupted/unknown entries survive a restart. No implicit creation/reset.
"""
from __future__ import annotations

import base64
from datetime import datetime, timezone
import hashlib
import io
import json
import os
from pathlib import Path
import sqlite3
import uuid

from PIL import Image

SCHEMA = 'ugrp.zone_pilot_budget.v1'
ATTEMPT_CAP = 600
TOKEN_CAP = 5_000_000
UPSTREAM_BOUND = 2
# Audited proxy version, not a claim about an arbitrary Gemini endpoint.
PROXY_SHA256 = '7d4c4e8c2addf9e0dc159de6ba0f4ec4374f876d915a6bc0752d3fd18db3e556'
EFFECTIVE = {'model': 'gemini-3.8-flash-low', 'thinking_level': 'LOW',
             'max_output_tokens_including_reasoning': 8192, 'temperature': 0.0}
REQUESTED = {'model': 'gemini-3.8-flash', 'max_tokens': 1400,
             'reasoning_effort': 'none', 'temperature': 0.0, 'timeout': 180.0}


def sha(data):
    return hashlib.sha256(data).hexdigest()


def canonical(value):
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(',', ':'))


def usage_total(usage):
    """Missing/inconsistent provider counters are UNKNOWN, never zero usage."""
    if not isinstance(usage, dict):
        return None
    values = [usage.get(k) for k in ('prompt_tokens', 'completion_tokens', 'total_tokens')]
    if any(type(v) is not int or v < 0 for v in values):
        return None
    prompt, completion, total = values
    # total includes hidden reasoning; don't replace it with prompt+completion.
    return total if total > 0 and total >= prompt + completion else None


def token_envelope(body):
    """Conservative bound, NOT the frozen SIM tokenizer or measured usage.

    UTF-8 JSON bytes (including labels/framing) bound text tokens; each JPEG
    <=1024x1024 reserves 65,536 image tokens (16 tiles x 4096). Larger/unrecognised
    images are refused. Both potential upstream attempts reserve the full
    8192 output+reasoning limit; preflight must reconcile provider usage.
    """
    request = json.loads(body)
    for key in ('model', 'max_tokens', 'reasoning_effort', 'temperature'):
        if request.get(key) != REQUESTED[key]:
            raise ValueError(f'pilot request settings drift: {key}')
    if set(request) != {'model', 'messages', 'max_tokens', 'reasoning_effort', 'temperature'}:
        raise ValueError('unregistered request fields (stream/tools/retries forbidden)')
    images = []
    for message in request['messages']:
        content = message.get('content')
        if isinstance(content, list):
            for part in content:
                if part.get('type') != 'image_url':
                    continue
                uri = part['image_url']['url']
                prefix, data = uri.split(',', 1)
                if prefix != 'data:image/jpeg;base64':
                    raise ValueError('pilot requires original JPEG bytes')
                raw = base64.b64decode(data, validate=True)
                with Image.open(io.BytesIO(raw)) as image:
                    if image.format != 'JPEG' or not (0 < image.width <= 1024 and 0 < image.height <= 1024):
                        raise ValueError('image exceeds audited pilot envelope (1024x1024 JPEG)')
                    image.verify()
                images.append({'sha256': sha(raw), 'bytes': len(raw), 'token_bound': 65536})
    if not 1 <= len(images) <= 2:
        raise ValueError('pilot requires 1-2 allowed images')
    text = len(body) + 1024  # includes base64 as well; intentional over-reservation
    output = EFFECTIVE['max_output_tokens_including_reasoning']
    per_attempt = text + sum(i['token_bound'] for i in images) + output
    return {'method': 'utf8_bytes_plus_1024_and_65536_per_bounded_jpeg.v1',
            'text_bound': text, 'images': images, 'output_reasoning_bound': output,
            'per_upstream_tokens': per_attempt, 'upstream_attempts_bound': UPSTREAM_BOUND,
            'reserved_tokens': UPSTREAM_BOUND * per_attempt}


class BudgetExceeded(RuntimeError):
    pass


class PilotBudget:
    """All conditions/trials/retries share this file, including after restart.

    Every operation reopens the DB (safe across processes). BEGIN IMMEDIATE
    serializes check+reservation. Caps/pilot ID are immutable. Source changes
    require an explicit append-only migration in this SAME file. Reserved rows
    are never deleted or refunded. Corrupt/missing files fail closed.
    """
    @classmethod
    def create(cls, path, *, identity):
        path = Path(path).resolve()
        path.parent.mkdir(parents=True, exist_ok=True)
        fd = os.open(path, os.O_CREAT | os.O_EXCL | os.O_WRONLY, 0o600)
        os.close(fd)
        with sqlite3.connect(path) as db:
            db.execute('PRAGMA synchronous=FULL')
            db.execute('CREATE TABLE meta (value TEXT NOT NULL)')
            db.execute('CREATE TABLE sends (id TEXT PRIMARY KEY, tokens INTEGER NOT NULL, '
                       'attempts INTEGER NOT NULL, record TEXT NOT NULL)')
            db.execute('CREATE TABLE runs (id TEXT PRIMARY KEY, stage TEXT NOT NULL, record TEXT NOT NULL)')
            db.execute('INSERT INTO meta VALUES (?)', (canonical({
                'schema': SCHEMA, 'pilot_id': uuid.uuid4().hex, 'budget_path': str(path),
                'attempt_cap': ATTEMPT_CAP, 'token_cap': TOKEN_CAP, 'identity': identity}),))
        return cls(path, identity=identity)

    def __init__(self, path, *, identity=None, read_only=False):
        self.path = Path(path).resolve(strict=True)
        self.read_only = read_only
        meta = self.snapshot()['meta']
        if (meta.get('schema'), meta.get('attempt_cap'), meta.get('token_cap'), meta.get('budget_path')) != (
                SCHEMA, ATTEMPT_CAP, TOKEN_CAP, str(self.path)):
            raise ValueError('budget identity/caps/path mismatch; never reset or copy a pilot budget')
        if identity is not None and meta['identity'] != identity:
            raise ValueError('frozen pilot source/settings changed; resume refused')
        self.meta = meta

    def _connect(self):
        db = sqlite3.connect(self.path.as_uri() + ('?mode=ro' if self.read_only else '?mode=rw'),
                             uri=True, timeout=10)
        if not self.read_only:
            db.execute('PRAGMA synchronous=FULL')
        return db

    def snapshot(self):
        with self._connect() as db:
            db.execute('BEGIN')
            return self._snapshot(db)

    @staticmethod
    def _snapshot(db):
        meta = json.loads(db.execute('SELECT value FROM meta').fetchone()[0])
        rows = [json.loads(r[0]) for r in db.execute('SELECT record FROM sends ORDER BY rowid')]
        runs = [json.loads(r[0]) for r in db.execute('SELECT record FROM runs ORDER BY rowid')]
        migrations = []
        if db.execute("SELECT 1 FROM sqlite_master WHERE type='table' AND name='source_migrations'").fetchone():
            expected_meta = None
            for revision, raw, checksum in db.execute('SELECT revision, record, sha256 FROM source_migrations ORDER BY revision'):
                row = json.loads(raw)
                if (sha(raw.encode()) != checksum or revision != len(migrations) + 1
                        or row['revision'] != revision
                        or row['from_meta'].get('source_revision', 0) != revision - 1
                        or (expected_meta is not None and row['from_meta'] != expected_meta)):
                    raise ValueError('source migration audit chain mismatch')
                expected_meta = {**row['from_meta'], 'identity': row['to_identity'],
                                 'source_revision': revision, 'source_migration_sha256': checksum}
                migrations.append({**row, 'sha256': checksum})
            if migrations and expected_meta != meta:
                raise ValueError('active source does not match migration audit chain')
        if meta.get('source_revision', 0) != len(migrations):
            raise ValueError('source migration audit missing')
        return {'meta': meta, 'reserved_attempts': sum(r['reserved_attempts'] for r in rows),
                'reserved_tokens': sum(r['reserved_tokens'] for r in rows), 'sends': rows, 'runs': runs,
                'source_migrations': migrations}

    def _require_current_source(self, db):
        if json.loads(db.execute('SELECT value FROM meta').fetchone()[0]) != self.meta:
            raise ValueError('budget source changed; reopen with the reviewed source identity')

    def migrate_source(self, identity, *, reason, expected_identity_sha256, expected_state_sha256):
        """Atomically append source provenance and reseal this file, never refund.

        Does not reconcile unknown billing or authorize a run. The existing
        reconciliation gate still applies; a new preflight is mandatory.
        The caller must stop drivers and pass the reviewed committed identity.
        This object becomes stale on success and cannot send/settle/start runs.
        """
        if not isinstance(reason, str) or not reason.strip():
            raise ValueError('source migration requires a nonempty review reason')
        old = self.meta['identity']
        if expected_identity_sha256 != sha(canonical(old).encode()):
            raise ValueError('reviewed source identity hash mismatch')
        mutable = {'source_head', 'source_root', 'files', 'rgb_execution_bundle'}
        if ({k: v for k, v in old.items() if k not in mutable}
                != {k: v for k, v in identity.items() if k not in mutable}):
            raise ValueError('source migration cannot change provider/settings/cost/input policy')
        previous_bundle, next_bundle = old.get('rgb_execution_bundle', {}), identity.get('rgb_execution_bundle', {})
        if (not next_bundle.get('id') or next_bundle['id'] == previous_bundle.get('id')
                or {k: v for k, v in next_bundle.items() if k not in {'id', 'sha256'}}
                != {k: v for k, v in previous_bundle.items() if k not in {'id', 'sha256'}}):
            raise ValueError('source migration requires a new bundle with identical effective settings')
        with self._connect() as db:
            db.execute('BEGIN IMMEDIATE')
            self._require_current_source(db)
            before = self._snapshot(db)
            if expected_state_sha256 != sha(canonical([before['sends'], before['runs']]).encode()):
                raise ValueError('pilot state changed since migration review')
            if any(r['status'] == 'running' for r in before['runs']):
                raise ValueError('stop/reconcile unfinished runs before source migration')
            # Hash exact SQL column values/JSON strings without duplicating raw
            # history. The original rows stay in this same DB, untouched.
            history = {table: [list(r) for r in db.execute(f'SELECT * FROM {table} ORDER BY rowid')]
                       for table in ('sends', 'runs')}
            revision = self.meta.get('source_revision', 0) + 1
            row = {'schema': 'ugrp.zone_pilot_source_migration.v1', 'revision': revision,
                   'created_at_utc': datetime.now(timezone.utc).isoformat(), 'reason': reason.strip(),
                   'from_meta': before['meta'], 'to_identity': identity,
                   'from_identity_sha256': expected_identity_sha256,
                   'to_identity_sha256': sha(canonical(identity).encode()),
                   'before_state_sha256': expected_state_sha256,
                   'preserved_sql_row_counts': {k: len(v) for k, v in history.items()},
                   'preserved_sql_history_sha256': sha(canonical(history).encode()),
                   'reserved_attempts': before['reserved_attempts'],
                   'reserved_tokens': before['reserved_tokens'], 'refunds': 0,
                   'billing_reconciliation': 'unchanged; migration does not resolve unknown sends',
                   'next_stage': 'new_four_condition_preflight_required'}
            raw = canonical(row)
            checksum = sha(raw.encode())
            db.execute('CREATE TABLE IF NOT EXISTS source_migrations '
                       '(revision INTEGER PRIMARY KEY, record TEXT NOT NULL, sha256 TEXT NOT NULL)')
            db.execute('INSERT INTO source_migrations VALUES (?,?,?)', (revision, raw, checksum))
            meta = {**before['meta'], 'identity': identity, 'source_revision': revision,
                    'source_migration_sha256': checksum}
            db.execute('UPDATE meta SET value=?', (canonical(meta),))
            self._snapshot(db)  # verify the durable audit chain before commit
        return {**row, 'sha256': checksum}

    def reserve(self, record, envelope):
        need = envelope.get('reserved_tokens')
        per_attempt = envelope.get('per_upstream_tokens')
        if type(need) is not int or type(per_attempt) is not int or per_attempt < 1 or need != UPSTREAM_BOUND * per_attempt:
            raise ValueError('reservation must cover two positive complete upstream token envelopes')
        with self._connect() as db:
            db.execute('BEGIN IMMEDIATE')
            self._require_current_source(db)
            if any(json.loads(r[0])['status'] == 'usage_exceeds_reservation'
                   for r in db.execute('SELECT record FROM sends')):
                raise BudgetExceeded('prior provider usage exceeded reservation; pilot halted')
            attempts, tokens = db.execute('SELECT COALESCE(SUM(attempts),0), COALESCE(SUM(tokens),0) '
                                         'FROM sends').fetchone()
            if attempts + UPSTREAM_BOUND > ATTEMPT_CAP or tokens + need > TOKEN_CAP:
                raise BudgetExceeded('global pilot 600 attempts / 5,000,000 tokens exhausted')
            row = {**record, 'reservation_id': uuid.uuid4().hex, 'status': 'reserved_unknown',
                   'reserved_attempts': UPSTREAM_BOUND, 'reserved_tokens': need,
                   'envelope': envelope, 'effective_settings': EFFECTIVE,
                   'provider_usage': None, 'completion': None, 'actual_upstream_attempts': None,
                   'proxy_request_id': None, 'upstream_complete': False}
            db.execute('INSERT INTO sends VALUES (?,?,?,?)',
                       (row['reservation_id'], need, UPSTREAM_BOUND, canonical(row)))
        return row

    def settle(self, reservation_id, **updates):
        allowed = {'status', 'provider_usage', 'proxy_response_id', 'response_sha256',
                   'wire_error', 'ledger', 'proxy_log_window', 'late', 'completion'}
        if set(updates) - allowed:
            raise ValueError('settlement cannot alter reservations or claim upstream reconciliation')
        with self._connect() as db:
            db.execute('BEGIN IMMEDIATE')
            self._require_current_source(db)
            row = json.loads(db.execute('SELECT record FROM sends WHERE id=?', (reservation_id,)).fetchone()[0])
            if row['status'] != 'reserved_unknown':
                raise ValueError('reservation already settled; evidence is immutable')
            row.update(updates)
            total = usage_total(row.get('provider_usage'))
            if total is not None and total > row['envelope']['per_upstream_tokens']:
                row['status'] = 'usage_exceeds_reservation'
            db.execute('UPDATE sends SET record=? WHERE id=?', (canonical(row), reservation_id))
        if row['status'] == 'usage_exceeds_reservation':
            raise BudgetExceeded('provider usage exceeds audited envelope; stop pilot')
        return row

    def start_run(self, run_id, stage, record, *, expected_state=None):
        with self._connect() as db:
            db.execute('BEGIN IMMEDIATE')
            self._require_current_source(db)
            runs = [json.loads(r[0]) for r in db.execute('SELECT record FROM runs ORDER BY rowid')]
            sends = [json.loads(r[0]) for r in db.execute('SELECT record FROM sends ORDER BY rowid')]
            if expected_state is not None and expected_state != sha(canonical([sends, runs]).encode()):
                raise RuntimeError('pilot state changed since reconciliation; retry preflight checks')
            if any(r['status'] == 'running' for r in runs):
                raise RuntimeError('unfinished run: reconcile outstanding upstream work before restart')
            value = {**record, 'run_id': run_id, 'stage': stage, 'status': 'running',
                     'source_revision': self.meta.get('source_revision', 0)}
            db.execute('INSERT INTO runs VALUES (?,?,?)', (run_id, stage, canonical(value)))

    def finish_run(self, run_id, *, status, manifest_sha256):
        with self._connect() as db:
            db.execute('BEGIN IMMEDIATE')
            self._require_current_source(db)
            row = json.loads(db.execute('SELECT record FROM runs WHERE id=?', (run_id,)).fetchone()[0])
            row.update(status=status, manifest_sha256=manifest_sha256)
            db.execute('UPDATE runs SET record=? WHERE id=?', (canonical(row), run_id))

    def recover_run(self, run_id, *, report, report_path):
        """Close an interrupted driver only after terminal upstream evidence.

        This does not settle by guessing, replay actions, or refund anything.
        The original send records (including reserved_unknown) remain intact.
        """
        if report['pilot_id'] != self.meta['pilot_id'] or not report['complete']:
            raise ValueError('terminal upstream reconciliation required for crash recovery')
        with self._connect() as db:
            db.execute('BEGIN IMMEDIATE')
            self._require_current_source(db)
            row = json.loads(db.execute('SELECT record FROM runs WHERE id=?', (run_id,)).fetchone()[0])
            if row['status'] != 'running':
                raise ValueError('only an interrupted running record can be recovered')
            row.update(status='recovered_without_actions', recovery_report=str(report_path),
                       recovery_sha256=sha(Path(report_path).read_bytes()))
            db.execute('UPDATE runs SET record=? WHERE id=?', (canonical(row), run_id))
