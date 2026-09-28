"""Main-study model usage ledger, keyed by execution bundle and run (B7, PR #254).

This is a NEW SQLite file. The #222 pilot budget (``harness.zone_pilot_budget``,
``outputs/zone-study-adapter-pilot-r10/budget.sqlite``) is never opened, copied,
migrated or changed by this module.

Differences from the pilot budget, by design (prereg draft §5.5, §10.3):

* it RECORDS usage; it does not reserve a conservative envelope and it never
  blocks because usage is large;
* the only stop is an explicit per-cohort token cap registered once from the
  prereg (``llm_driver.cohort_token_cap``). A cohort registered with ``None``
  never stops. Caps are immutable after registration;
* a request whose provider usage is unknown (wire error, missing ``usage``,
  crashed driver) is charged the cohort's registered
  ``unknown_usage_charge_tokens`` when checking the cap; its raw rows stay
  ``usage_known = 0``, never a guessed zero.

Every row is written before the wire runs (``record_request``) and settled after
it (``settle_request``), so a crash leaves a durable ``sent_unknown`` row.
Every operation reopens the database, so several processes may share it.
"""
from __future__ import annotations

from datetime import datetime, timezone
import hashlib
import json
import os
from pathlib import Path
import sqlite3
import uuid

from harness.zone_pilot_budget import BudgetExceeded

SCHEMA = 'ugrp.zone_main_study_budget.v1'
REQUEST_STATUSES = ('sent_unknown', 'response_received', 'wire_error')


def canonical(value) -> str:
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(',', ':'))


def sha(text: str) -> str:
    return hashlib.sha256(text.encode()).hexdigest()


def now_utc() -> str:
    return datetime.now(timezone.utc).isoformat()


def known_total(usage):
    """Provider ``total_tokens`` when every counter is a consistent non-negative int, else None."""
    if not isinstance(usage, dict):
        return None
    values = [usage.get(k) for k in ('prompt_tokens', 'completion_tokens', 'total_tokens')]
    if any(type(v) is not int or v < 0 for v in values):
        return None
    prompt, completion, total = values
    return total if total >= prompt + completion else None


class MainStudyBudget:
    """Usage ledger for the main study. Never reset; never created implicitly."""

    @classmethod
    def create(cls, path):
        path = Path(path).resolve()
        path.parent.mkdir(parents=True, exist_ok=True)
        fd = os.open(path, os.O_CREAT | os.O_EXCL | os.O_WRONLY, 0o600)   # refuse an existing file
        os.close(fd)
        with sqlite3.connect(path) as db:
            db.execute('PRAGMA synchronous=FULL')
            db.execute('CREATE TABLE meta (value TEXT NOT NULL)')
            db.execute('CREATE TABLE cohorts (cohort_id TEXT PRIMARY KEY, record TEXT NOT NULL)')
            db.execute('CREATE TABLE runs (run_key TEXT PRIMARY KEY, cohort_id TEXT NOT NULL, '
                       'bundle_id TEXT NOT NULL, record TEXT NOT NULL)')
            db.execute('CREATE TABLE requests (id TEXT PRIMARY KEY, run_key TEXT NOT NULL, '
                       'cohort_id TEXT NOT NULL, bundle_id TEXT NOT NULL, status TEXT NOT NULL, '
                       'total_tokens INTEGER, record TEXT NOT NULL)')
            db.execute('INSERT INTO meta VALUES (?)', (canonical({
                'schema': SCHEMA, 'ledger_id': uuid.uuid4().hex, 'path': str(path), 'created_at_utc': now_utc(),
                'note': 'main-study usage ledger; separate from the #222 pilot budget'}),))
        return cls(path)

    def __init__(self, path):
        self.path = Path(path).resolve(strict=True)
        with self._connect() as db:
            meta = json.loads(db.execute('SELECT value FROM meta').fetchone()[0])
        if meta.get('schema') != SCHEMA or meta.get('path') != str(self.path):
            raise ValueError(f'{self.path}: not a {SCHEMA} ledger at its registered path (never copy a ledger)')
        self.meta = meta

    def _connect(self):
        db = sqlite3.connect(self.path.as_uri() + '?mode=rw', uri=True, timeout=30)
        db.execute('PRAGMA synchronous=FULL')
        return db

    # -- cohorts -----------------------------------------------------------------
    def register_cohort(self, cohort_id, *, token_cap, unknown_usage_charge_tokens, prereg_sha256, source):
        """Register once; a repeat must carry the same cap/charge/prereg or it is refused."""
        if not isinstance(cohort_id, str) or not cohort_id:
            raise ValueError('cohort_id must be a nonempty string')
        if token_cap is not None and (type(token_cap) is not int or token_cap < 1):
            raise ValueError('cohort token cap must be a positive int or None (explicitly no cap)')
        if type(unknown_usage_charge_tokens) is not int or unknown_usage_charge_tokens < 0:
            raise ValueError('unknown_usage_charge_tokens must be a non-negative int')
        fixed = {'cohort_id': cohort_id, 'token_cap': token_cap,
                 'unknown_usage_charge_tokens': unknown_usage_charge_tokens, 'prereg_sha256': prereg_sha256}
        with self._connect() as db:
            db.execute('BEGIN IMMEDIATE')
            row = db.execute('SELECT record FROM cohorts WHERE cohort_id=?', (cohort_id,)).fetchone()
            if row is not None:
                old = json.loads(row[0])
                if {k: old[k] for k in fixed} != fixed:
                    raise ValueError(f'cohort {cohort_id!r} is registered with a different cap/charge/prereg; '
                                     'register a new cohort instead of changing it')
                return old
            record = {**fixed, 'source': source, 'registered_at_utc': now_utc()}
            db.execute('INSERT INTO cohorts VALUES (?,?)', (cohort_id, canonical(record)))
        return record

    def cohort(self, cohort_id):
        with self._connect() as db:
            row = db.execute('SELECT record FROM cohorts WHERE cohort_id=?', (cohort_id,)).fetchone()
        if row is None:
            raise KeyError(f'unregistered cohort {cohort_id!r}')
        return json.loads(row[0])

    @staticmethod
    def _usage(db, cohort):
        rows = db.execute('SELECT status, total_tokens FROM requests WHERE cohort_id=?',
                          (cohort['cohort_id'],)).fetchall()
        known = sum(t for _, t in rows if t is not None)
        unknown = sum(1 for _, t in rows if t is None)
        return {'requests': len(rows), 'known_tokens': known, 'usage_unknown_requests': unknown,
                'pending_requests': sum(1 for s, _ in rows if s == 'sent_unknown'),
                'charged_tokens': known + unknown * cohort['unknown_usage_charge_tokens'],
                'token_cap': cohort['token_cap']}

    def usage(self, cohort_id):
        cohort = self.cohort(cohort_id)
        with self._connect() as db:
            return self._usage(db, cohort)

    # -- runs --------------------------------------------------------------------
    def start_run(self, run_key, *, cohort_id, bundle_id, bundle_sha256, record):
        self.cohort(cohort_id)
        value = {**record, 'run_key': run_key, 'cohort_id': cohort_id, 'bundle_id': bundle_id,
                 'bundle_sha256': bundle_sha256, 'status': 'running', 'started_at_utc': now_utc()}
        with self._connect() as db:
            db.execute('BEGIN IMMEDIATE')
            db.execute('INSERT INTO runs VALUES (?,?,?,?)', (run_key, cohort_id, bundle_id, canonical(value)))
        return value

    def run(self, run_key):
        with self._connect() as db:
            row = db.execute('SELECT record FROM runs WHERE run_key=?', (run_key,)).fetchone()
        if row is None:
            raise KeyError(run_key)
        return json.loads(row[0])

    def run_requests(self, run_key) -> int:
        """Requests recorded for this run attempt (0 = the first model request was never made)."""
        with self._connect() as db:
            return db.execute('SELECT COUNT(*) FROM requests WHERE run_key=?', (run_key,)).fetchone()[0]

    def finish_run(self, run_key, *, status, failure_class=None, summary=None):
        with self._connect() as db:
            db.execute('BEGIN IMMEDIATE')
            row = json.loads(db.execute('SELECT record FROM runs WHERE run_key=?', (run_key,)).fetchone()[0])
            if row['status'] != 'running':
                raise ValueError(f'run {run_key} already finished; run records are immutable')
            requests = db.execute('SELECT COUNT(*) FROM requests WHERE run_key=?', (run_key,)).fetchone()[0]
            row.update(status=status, failure_class=failure_class, summary=summary or {},
                       model_requests=requests, finished_at_utc=now_utc())
            db.execute('UPDATE runs SET record=? WHERE run_key=?', (canonical(row), run_key))
        return row

    # -- requests ----------------------------------------------------------------
    def record_request(self, run_key, record):
        """Durable row BEFORE the wire. Raises BudgetExceeded only at the registered cohort cap."""
        with self._connect() as db:
            db.execute('BEGIN IMMEDIATE')
            run = db.execute('SELECT cohort_id, bundle_id, record FROM runs WHERE run_key=?', (run_key,)).fetchone()
            if run is None or json.loads(run[2])['status'] != 'running':
                raise ValueError(f'no running run {run_key!r} in the main-study ledger')
            cohort_id, bundle_id = run[0], run[1]
            cohort = json.loads(db.execute('SELECT record FROM cohorts WHERE cohort_id=?',
                                           (cohort_id,)).fetchone()[0])
            usage = self._usage(db, cohort)
            if cohort['token_cap'] is not None and usage['charged_tokens'] >= cohort['token_cap']:
                raise BudgetExceeded(f'cohort {cohort_id} reached its registered cap '
                                     f'{cohort["token_cap"]} tokens (charged {usage["charged_tokens"]})')
            rid = uuid.uuid4().hex
            row = {**record, 'id': rid, 'run_key': run_key, 'cohort_id': cohort_id, 'bundle_id': bundle_id,
                   'status': 'sent_unknown', 'recorded_at_utc': now_utc(), 'provider_usage': None,
                   'usage_known': False}
            db.execute('INSERT INTO requests VALUES (?,?,?,?,?,?,?)',
                       (rid, run_key, cohort_id, bundle_id, 'sent_unknown', None, canonical(row)))
        return row

    def settle_request(self, request_id, *, status, **fields):
        if status not in REQUEST_STATUSES[1:]:
            raise ValueError(f'bad settlement status {status!r}')
        with self._connect() as db:
            db.execute('BEGIN IMMEDIATE')
            row = json.loads(db.execute('SELECT record FROM requests WHERE id=?', (request_id,)).fetchone()[0])
            if row['status'] != 'sent_unknown':
                raise ValueError('request already settled; evidence is immutable')
            total = known_total(fields.get('provider_usage'))
            row.update(fields, status=status, usage_known=total is not None, total_tokens=total,
                       settled_at_utc=now_utc())
            db.execute('UPDATE requests SET status=?, total_tokens=?, record=? WHERE id=?',
                       (status, total, canonical(row), request_id))
        return row

    def requests(self, run_key=None):
        query, args = 'SELECT record FROM requests', ()
        if run_key is not None:
            query, args = query + ' WHERE run_key=?', (run_key,)
        with self._connect() as db:
            return [json.loads(r[0]) for r in db.execute(query + ' ORDER BY rowid', args)]


__all__ = ['SCHEMA', 'BudgetExceeded', 'MainStudyBudget', 'known_total']
