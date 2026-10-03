"""Live model path of the pair LLM layer (v99): the study's own live driver behind the pair trial.

Nothing here is a new transport. A real model call goes through exactly the chain the zone study uses:
``GeminiProxyCompleter`` -> ``MainStudySendLedger`` (durable budget row BEFORE the wire, raw request and response
bytes with hashes, provider usage, wall latency, failure class) -> the audited local subscription proxy on
127.0.0.1 (read-only identity check, never started or edited here) -> the private non-redirecting opener under
``NetworkFence``. This module adds only what the pair layer needs on top:

* :class:`PairLiveLedger` keeps the body and ``Retry-After`` of an HTTP error response (the study ledger drops
  it), so a 429 / quota answer is evidence and is classified explicitly;
* :func:`check_health` stops the run at the next tick after a rate-limit / quota answer
  (``RATE_LIMIT``), a fatal host/storage error, the cohort token cap, or a run with no normal model reply;
* :func:`run_pair_live` runs the case through the study's documented retry rule and nothing else.

Retry layers (all documented, none new; recorded in the bundle):

1. scheduler: ``CallPolicy.max_retries = 0``. A failed call is never re-sent as a new POST
   (``MainStudySendLedger.attach`` refuses any other value);
2. run: ``llm_driver.json`` ``retry_policy = once_in_place_only_if_host_error_before_first_model_request``
   (``llm.run_attempts`` / ``llm.may_retry``). A 429, an API error or a host error after the first request is
   never retried;
3. proxy: the audited proxy retries an upstream 429 INSIDE one POST, at most 2 upstream attempts per POST.

A rate-limit or quota answer is therefore explicit and final for the run: failure label ``RATE_LIMIT``
(study class ``infra:API``), the run is invalid, no silent retry changes it.
"""
from __future__ import annotations

import hashlib
import os
import re
from pathlib import Path
from urllib.error import HTTPError

from harness import pair_llm_contract as contract
from harness import zone_study_integration as zi
from harness import zone_study_llm_driver as llm
from harness.gemini_proxy import GeminiProxyError
from harness.zone_final_environment import digest

LIVE_VERSION = 'ugrp.pair_llm_live.v1'
RATE_LIMIT = 'RATE_LIMIT'
#: Quota / throttle wording in an error body. HTTP 429 alone is enough; this catches the same condition
#: reported under another status (403 quota, 503 resource exhausted).
QUOTA_TEXT = re.compile(r'quota|rate[ _-]?limit|resource[ _-]?exhausted|too many requests', re.IGNORECASE)
ERROR_EXCERPT_BYTES = 600
#: A smoke is allowed to spend this long a case only; a longer live case is a separate decision.
LIVE_MAX_CAP_S = contract.SMOKE_MAX_S


class RateLimited(GeminiProxyError):
    """A rate-limit / quota answer reached the run. Study class ``infra:API``; the pair label is ``RATE_LIMIT``."""

    failure_label = RATE_LIMIT

    def __init__(self, rows):
        first = rows[0]
        reply = first.get('error_response') or {}
        super().__init__(
            f'rate limit / quota answer on {first["call_id"]} (HTTP {first.get("http_status")}, '
            f'Retry-After {reply.get("retry_after")}); {len(rows)} such answer(s); the run is stopped and not retried',
            error_kind='rate_limit', retryable=False, http_status=first.get('http_status'))
        self.rows = [{'seq': r['seq'], 'call_id': r['call_id'], 'http_status': r.get('http_status'),
                      'retry_after': (r.get('error_response') or {}).get('retry_after')} for r in rows]


def is_rate_limit(status, text) -> bool:
    return status == 429 or (isinstance(status, int) and status >= 400 and bool(QUOTA_TEXT.search(text or '')))


class PairLiveLedger(llm.MainStudySendLedger):
    """``MainStudySendLedger`` that also keeps an HTTP error response (body hash, excerpt, Retry-After)."""

    def _send(self, call_id, actor, request, timeout):
        try:
            return super()._send(call_id, actor, request, timeout)
        except HTTPError as exc:
            self._keep_error_response(call_id, exc)
            raise

    def _keep_error_response(self, call_id, exc) -> None:
        row = next((r for r in reversed(self.entries) if r['call_id'] == call_id), None)
        if row is None:
            return
        try:
            body = exc.read() or b''
        except Exception:                                  # noqa: BLE001 - the status line is still evidence
            body = b''
        excerpt = body[:ERROR_EXCERPT_BYTES].decode('utf-8', 'replace')
        headers = getattr(exc, 'headers', None)
        retry_after = headers.get('Retry-After') if headers is not None else None
        record = {'http_status': exc.code, 'bytes': len(body), 'sha256': hashlib.sha256(body).hexdigest(),
                  'excerpt': excerpt, 'retry_after': retry_after}
        if body and self.store_dir is not None:
            safe = row['call_id'].replace('/', '_').replace(':', '_')
            path = self.store_dir / f'{row["seq"]:06d}-{safe}-error.json'
            try:
                with open(path, 'xb') as handle:           # never overwrite a stored response
                    handle.write(body)
                    handle.flush()
                    os.fsync(handle.fileno())
            except OSError as error:
                raise self._storage_error(row, error, 'store error response') from error
            record['path'] = path.name
        row['error_response'] = record
        row['rate_limit'] = is_rate_limit(exc.code, excerpt)


def rate_limited_rows(ledger) -> list:
    return [r for r in ledger.entries if r.get('rate_limit') or r.get('http_status') == 429]


def check_health(trial, *, final=False) -> None:
    """Runner boundary, once per tick: stop before another physics step after a rate limit or a fatal error."""
    ledger = trial.send_ledger
    if not isinstance(ledger, llm.MainStudySendLedger):
        return
    hits = rate_limited_rows(ledger)
    if hits:
        raise RateLimited(hits)
    llm.check_trial_health(trial, final=final)


def live_adapter(profile, *, budget, run_key, store_dir, proxy_pid=None, wire=None, pacer=None):
    """``(ModelAdapter, None)`` of one attempt. Live: read-only proxy identity first (HOST_ERROR before any POST).

    ``wire`` replaces only the network (tests); then no proxy process is checked and ``ledger.live`` is False.
    Called BEFORE the first model call: the identity check spawns ``ps``/``lsof``, which the network fence forbids.
    """
    llm.check_disk(store_dir, min_free_gib=profile['min_free_disk_gib'])
    proxy = runtime = None
    if wire is None:
        if type(proxy_pid) is not int:
            raise llm.HostError('a live model run needs the running proxy PID (--proxy-pid)')
        proxy, runtime = llm.live_proxy(profile, proxy_pid)
    ledger = PairLiveLedger(store_dir=store_dir, budget=budget, run_key=run_key, profile=profile,
                            runtime=runtime, proxy=proxy, wire=wire, pacer=pacer)
    ledger.proxy_identity = {'profile': proxy, 'runtime': runtime}
    return zi.ModelAdapter(llm.client_factory(profile), ledger), None


def live_records(ledger) -> dict | None:
    """Per-POST rows and the usage summary of a live ledger, or None for a stub ledger."""
    if not isinstance(ledger, llm.MainStudySendLedger):
        return None
    rows = llm.call_rows(ledger)
    by_seq = {e['seq']: e for e in ledger.entries}
    for row in rows:                                       # keep the evidence the study rows leave out
        entry = by_seq[row['seq']]
        for key in ('error_response', 'rate_limit', 'sent_at_ns'):
            if key in entry:
                row[key] = entry[key]
    return {'rows': rows, 'usage': llm.usage_summary(rows)}


def live_walls(trial) -> list:
    """Wall seconds of every POST that reached the wire (recorded, never charged as SIM time)."""
    records = live_records(getattr(trial, 'send_ledger', None)) if trial is not None else None
    if records is None:
        return []
    return [r['latency_ms'] / 1000. for r in records['rows'] if r['status'] == 'sent' and r['latency_ms'] is not None]


def driver_record(ledger, profile, budget, cohort_id) -> dict:
    """What the live driver was: profile, proxy identity of this attempt, ledger and cohort usage at the end."""
    return {'schema': LIVE_VERSION, 'live': bool(getattr(ledger, 'live', False)),
            'profile_id': profile['profile_id'], 'profile_sha256': profile['sha256'],
            'model': dict(profile['model']), 'proxy_url': profile['proxy_url'],
            'retry_policy': profile['retry_policy'], 'api_failure_trial_rule': profile['api_failure_trial_rule'],
            'min_request_interval_s': profile['min_request_interval_s'],
            'proxy_identity': getattr(ledger, 'proxy_identity', None), 'run_key': getattr(ledger, 'run_key', None),
            'budget_ledger_id': budget.meta['ledger_id'], 'budget_path': str(budget.path),
            'cohort': budget.cohort(cohort_id), 'cohort_usage': budget.usage(cohort_id)}


def run_pair_live(out_root, *, condition, seed, cap_s, profile, budget, cohort_id, backend_factory, calibration,
                  calibration_sha, provider_factory=None, synthetic_calibration=False, source_sha='unknown',
                  proxy_pid=None, wire=None, root=contract.ROOT):
    """One live case through the study's retry rule. Returns ``(record, attempts)``.

    ``out_root/<condition>`` is attempt 1; ``<condition>-attempt2`` exists only after a pre-request host error.
    """
    from harness.pair_llm_case import run_pair_case, write
    if condition == 'rule':
        raise ValueError('the rule arm makes no model call; it has no live path')
    if not 0 < float(cap_s) <= LIVE_MAX_CAP_S:
        raise ValueError(f'a live case is capped at {LIVE_MAX_CAP_S:g} SIM s (a longer one is a separate decision)')
    out_root = Path(out_root)
    bundle = contract.bundle(condition, kind='live', calibration={'path': calibration, 'sha256': calibration_sha},
                             synthetic_calibration=synthetic_calibration, source_sha=source_sha, root=root)
    bundle_sha = digest(bundle)
    run_id = f'{condition}-s{seed}'

    def start(attempt, run_key):
        budget.start_run(run_key, cohort_id=cohort_id, bundle_id=contract.BUNDLE_ID, bundle_sha256=bundle_sha,
                         record={'run_id': run_id, 'attempt': attempt, 'condition': condition, 'cap_s': float(cap_s),
                                 'seed': seed})

    def attempt_fn(attempt, run_key):
        out = out_root / (condition if attempt == 1 else f'{condition}-attempt{attempt}')
        held = {}

        def adapter_for(o):
            adapter, recorder = live_adapter(profile, budget=budget, run_key=run_key, store_dir=o / 'llm' / 'wire',
                                             proxy_pid=proxy_pid, wire=wire)
            held['ledger'] = adapter.send_ledger
            return adapter, recorder

        def finalize(o, _result):
            if 'ledger' in held:
                write(o / 'llm' / 'live_driver.json', driver_record(held['ledger'], profile, budget, cohort_id))

        result = run_pair_case(
            bundle, out, condition=condition, seed=seed, backend_factory=backend_factory, calibration=calibration,
            calibration_sha=calibration_sha, provider_factory=provider_factory, cap_s=cap_s, kind='live',
            source_sha=source_sha, root=root, health=check_health, finalize=finalize, adapter_factory=adapter_for)
        return result, None

    record, exc, attempts = llm.run_attempts(attempt_fn, budget=budget, run_id=run_id, start=start)
    write(out_root / 'attempts.json', {'schema': LIVE_VERSION, 'run_id': run_id, 'bundle_sha256': bundle_sha,
                                       'attempts': attempts, 'retry_policy': profile['retry_policy'],
                                       'cohort_id': cohort_id, 'cohort_usage': budget.usage(cohort_id),
                                       'budget_ledger_id': budget.meta['ledger_id']})
    if exc is not None:
        raise exc
    return record, attempts


__all__ = ['LIVE_VERSION', 'RATE_LIMIT', 'LIVE_MAX_CAP_S', 'RateLimited', 'PairLiveLedger', 'is_rate_limit',
           'rate_limited_rows', 'check_health', 'live_adapter', 'live_records', 'live_walls', 'driver_record',
           'run_pair_live']
