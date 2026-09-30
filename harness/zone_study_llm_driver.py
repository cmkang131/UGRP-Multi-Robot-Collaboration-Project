"""Real multi-turn model driver for the integrated zone study (B7, PR #254, #222).

The integration runner already had the seam (``IntegratedTrial(model_adapter=...)``)
but its CLI only ever ran the fixture actor, and the only live send ledger
(``PilotSendLedger``) is bound to the #222 pilot budget with its fixed
600-attempt / 5M-token cap. This module supplies the missing pieces without
changing the study core, the scheduler or any robot input:

* a registry (``configs/zone_study_integration/llm_driver.json``) that fixes, per
  registered execution bundle, which speech-cap profiles (v66 default 2/6, main
  pilot 10/30) and driver profiles (model settings, proxy URL, failure rules) a
  prereg may select. No ad hoc ``decision_limits`` in a prereg;
* :class:`MainStudySendLedger`, a ``SendLedger`` whose every POST is written to
  the NEW main-study ledger (``harness.zone_main_budget``) before the wire runs
  and settled after it, with raw request/response bytes, provider token usage,
  wall latency and the failure class;
* failure classes of the prereg (§8): ``infra:API`` / ``infra:HOST_ERROR``
  (ENOSPC included), and the one permitted retry: in place, once, only for a host
  error before the first model request of the attempt.

Tests substitute only the wire (``wire=``); the client stays the registered
``GeminiProxyCompleter`` and the request builder stays the study core's.
"""
from __future__ import annotations

import errno
import json
import os
import shutil
import sqlite3
import time
from collections import Counter
from collections.abc import Mapping
from pathlib import Path
from urllib.error import HTTPError

from harness import zone_study_integration as zi
from harness import zone_study_prompts_ko as pk
from harness.gemini_proxy import GeminiProxyError
from harness.llm_completion import assess_completion, normal_completion
from harness.zone_main_budget import BudgetExceeded, known_total
from harness.zone_pilot_network import NetworkFence, proxy_address
from harness.zone_send_ledger import SendLedger
from harness.zone_study_contract import ContractViolation, digest
from harness.zone_study_decisions import DecisionLimits
from harness.zone_study_llm_transport import gemini_client_factory, no_redirect_opener

ROOT = Path(__file__).resolve().parents[1]
REGISTRY = ROOT / 'configs' / 'zone_study_integration' / 'llm_driver.json'
REGISTRY_SCHEMA = 'ugrp.zone_study_llm_driver.v1'
DRIVER_VERSION = 'ugrp.zone_study_llm_driver.v1'
DEFAULT_SPEECH_CAPS = 'v66_default'
LIMIT_KEYS = ('max_calls_total', 'max_utterances_per_actor', 'max_utterances_total')
MODEL_KEYS = ('model', 'temperature', 'reasoning_effort', 'max_tokens', 'timeout')
HOST_ERROR, API_ERROR, OTHER = 'infra:HOST_ERROR', 'infra:API', 'other'
MAX_ATTEMPTS = 2
HOST_ERRNOS = frozenset((errno.ENOSPC, errno.EDQUOT, errno.EIO, errno.ENOMEM, errno.EMFILE, errno.ENFILE))
API_FAILURE_TRIAL_RULE = 'any_api_error_or_budget_cap_or_no_successful_model_reply'


class HostError(RuntimeError):
    """Host/process failure (disk, ENOSPC, proxy process not up). Deliberately NOT an
    ``OSError``: ``GeminiProxyCompleter`` would turn an OSError into an API connection error."""

    def __init__(self, message, *, errno_=None):
        super().__init__(message)
        self.errno = errno_


# ---------------------------------------------------------------------------
# Registry

def load_registry(path=REGISTRY) -> dict:
    data = json.loads(Path(path).read_text())
    if data.get('schema') != REGISTRY_SCHEMA:
        raise ContractViolation(f'{path}: not a {REGISTRY_SCHEMA} file')
    for name, caps in data['speech_cap_profiles'].items():
        if set(caps) - {'note_ko', 'prompt_versions'} != set(LIMIT_KEYS):
            raise ContractViolation(f'speech cap profile {name}: keys must be {LIMIT_KEYS}')
        DecisionLimits(**{k: caps[k] for k in LIMIT_KEYS})
    return data


def _bundle_entry(registry, bundle_id):
    entry = registry['bundles'].get(bundle_id)
    if entry is None:
        raise ContractViolation(f'execution bundle {bundle_id!r} is not registered in {REGISTRY.name}')
    return entry


def speech_caps(profile_id, *, bundle_id=None, registry=None):
    """``(DecisionLimits, record)`` of a speech-cap profile the bundle registered."""
    registry = registry or load_registry()
    bundle_id = bundle_id or zi.EXECUTION_BUNDLE_ID
    if profile_id not in _bundle_entry(registry, bundle_id)['speech_cap_profiles']:
        raise ContractViolation(f'speech cap profile {profile_id!r} is not registered for bundle {bundle_id}')
    caps = registry['speech_cap_profiles'][profile_id]
    values = {k: caps[k] for k in LIMIT_KEYS}
    version = pk.prompt_version(values['max_utterances_total'], values['max_utterances_per_actor'])
    if version not in caps.get('prompt_versions', ()):
        raise ContractViolation(f'speech cap profile {profile_id}: unsupported prompt version {version}')
    return DecisionLimits(**values), {'profile': profile_id, 'values': values, 'sha256': digest(values),
                                     'prompt_version': version}


def speech_caps_for(prereg, *, bundle_id=None, registry=None):
    """The prereg's registered speech caps. Raw ``decision_limits`` are ad hoc and refused."""
    if 'decision_limits' in prereg:
        raise ContractViolation('prereg decision_limits are ad hoc; select a registered speech_cap_profile')
    return speech_caps(prereg.get('speech_cap_profile', DEFAULT_SPEECH_CAPS), bundle_id=bundle_id,
                       registry=registry)


def driver_profile(profile_id, *, bundle_id=None, registry=None) -> dict:
    registry = registry or load_registry()
    bundle_id = bundle_id or zi.EXECUTION_BUNDLE_ID
    if profile_id not in _bundle_entry(registry, bundle_id)['driver_profiles']:
        raise ContractViolation(f'driver profile {profile_id!r} is not registered for bundle {bundle_id}')
    profile = dict(registry['driver_profiles'][profile_id])
    model = profile['model']
    if set(model) != set(MODEL_KEYS):
        raise ContractViolation(f'driver profile {profile_id}: model keys must be {MODEL_KEYS}')
    planned = {k: zi.PLANNED_MODEL[k] for k in ('model', 'temperature', 'reasoning_effort')}
    if {k: model[k] for k in planned} != planned:
        raise ContractViolation(f'driver profile {profile_id} drifts from the bundle PLANNED_MODEL {planned}')
    proxy_address(profile['proxy_url'])
    if profile['api_failure_trial_rule'] != API_FAILURE_TRIAL_RULE:
        raise ContractViolation('unsupported api_failure_trial_rule')
    if type(profile.get('min_request_interval_s')) not in (int, float) or profile['min_request_interval_s'] < 0:
        raise ContractViolation('min_request_interval_s must be non-negative')
    return {**profile, 'profile_id': profile_id, 'sha256': digest(profile)}


def client_factory(profile, *, url=None):
    """The registered ``GeminiProxyCompleter`` factory (strict completion, study JSON)."""
    return gemini_client_factory(**profile['model'], url=url or profile['proxy_url'], study_json=True)


# ---------------------------------------------------------------------------
# Failure classes (prereg §8)

def _chain(exc):
    seen = []
    while exc is not None and exc not in seen:
        seen.append(exc)
        exc = exc.__cause__ or exc.__context__
    return seen


def classify_exception(exc) -> str:
    """``infra:HOST_ERROR`` for host/process/disk (ENOSPC), ``infra:API`` for the model path, else ``other``."""
    chain = _chain(exc)
    for item in chain:
        if isinstance(item, HostError) or (isinstance(item, OSError) and item.errno in HOST_ERRNOS):
            return HOST_ERROR
        if type(item).__name__ == 'FatalError' and type(item).__module__.startswith('mujoco'):
            return HOST_ERROR
        if isinstance(item, (MemoryError,)):
            return HOST_ERROR
    for item in chain:
        if isinstance(item, (GeminiProxyError, HTTPError, BudgetExceeded)):
            return API_ERROR
        if type(item).__name__ == 'TransportFailure':
            return API_ERROR
    return OTHER


def call_failure_class(row) -> str | None:
    """Per-request class from a settled send row: None = normal reply."""
    if row.get('host_error'):
        return HOST_ERROR
    if row.get('storage_error'):
        return OTHER
    if row.get('status') == 'blocked':
        return 'budget_cap' if row.get('budget_cap') else 'blocked'
    if row.get('wire_error') or row.get('http_status'):
        return API_ERROR
    completion = row.get('completion')
    if completion is not None and not normal_completion(completion):
        return 'model_output_rejected'
    return None


def check_disk(path, *, min_free_gib):
    """Prereg ENOSPC prevention: refuse to start below the free-space floor (HOST_ERROR)."""
    path = Path(path)
    while not path.exists():
        path = path.parent
    free = shutil.disk_usage(path).free
    if free < min_free_gib * 2 ** 30:
        raise HostError(f'free disk {free / 2 ** 30:.1f} GiB < {min_free_gib} GiB before start (ENOSPC guard)',
                        errno_=errno.ENOSPC)
    return free


# ---------------------------------------------------------------------------
# Send ledger

class RequestPacer:
    """Common wall-clock POST spacing; never fed back into the SIM cost model."""

    def __init__(self, interval_s, *, clock=time.monotonic, sleep=time.sleep):
        self.interval_s, self.clock, self.sleep = interval_s, clock, sleep
        self.last_start = None

    def wait(self):
        if self.last_start is not None:
            delay = self.interval_s - (self.clock() - self.last_start)
            if delay > 0:
                self.sleep(delay)
        self.last_start = self.clock()

def _request_summary(body: bytes) -> dict:
    """Image hashes/bytes and text size of one proxy request (raw bytes are stored separately)."""
    import base64
    import hashlib
    images, text_chars = [], 0
    try:
        request = json.loads(body)
        for message in request.get('messages', []):
            content = message.get('content')
            if isinstance(content, str):
                text_chars += len(content)
                continue
            for part in content or ():
                if part.get('type') == 'text':
                    text_chars += len(part.get('text', ''))
                elif part.get('type') == 'image_url':
                    raw = base64.b64decode(part['image_url']['url'].split(',', 1)[1])
                    images.append({'sha256': hashlib.sha256(raw).hexdigest(), 'bytes': len(raw)})
        settings = {k: request.get(k) for k in ('model', 'temperature', 'max_tokens', 'reasoning_effort')}
    except (ValueError, KeyError, TypeError, AttributeError, IndexError):
        return {'parse_error': True}
    return {'images': images, 'text_chars': text_chars, 'settings': settings}


class MainStudySendLedger(SendLedger):
    """Each POST: durable main-study row before the wire, settled after, raw bytes kept.

    ``wire`` is for tests only (fake model); without it the private
    non-redirecting opener under :class:`NetworkFence` sends to the loopback
    proxy, after checking the proxy process/source identity (read only).
    """

    # The SIM pipeline's local token counts cannot certify provider usage.
    requires_provider_usage = True

    def __init__(self, *, store_dir, budget, run_key, profile, runtime=None, proxy=None, wire=None, pacer=None):
        if store_dir is None:
            raise ValueError('the main study keeps raw request/response bytes: store_dir is required')
        self.budget, self.run_key, self.profile = budget, run_key, profile
        self.runtime, self.proxy = runtime, proxy
        self.live = wire is None
        self.guard = NetworkFence(profile['proxy_url'] if self.live else None)
        self.fatal = None
        self.host_errors = []
        self.pacer = pacer or RequestPacer(profile['min_request_interval_s'])
        opener = no_redirect_opener()

        def guarded_wire(request, *, timeout):
            self.pacer.wait()
            with self.guard.wire():
                return opener.open(request, timeout=timeout)

        super().__init__(wire or guarded_wire, store_dir=store_dir)

    def attach(self, authorize, *, owner):
        # The common scheduler's default retries a failed decision as a NEW
        # call/POST. That is incompatible with this driver's registered policy:
        # only run_attempts may retry, before any request, for a HOST_ERROR.
        # Refuse a contradictory configuration rather than silently rewriting
        # the call policy recorded in the execution bundle.
        retries = getattr(getattr(owner, 'policy', None), 'max_retries', None)
        if type(retries) is not int or retries != 0:
            raise ContractViolation('main-study driver requires call_policy.max_retries=0; '
                                    'post-send scheduler retries are forbidden')
        return super().attach(authorize, owner=owner)

    def _host_error(self, row, exc, what):
        err = HostError(f'{what}: {type(exc).__name__}: {exc}', errno_=getattr(exc, 'errno', None))
        row['host_error'] = {'what': what, 'type': type(exc).__name__, 'errno': getattr(exc, 'errno', None)}
        self.host_errors.append(dict(row['host_error'], call_id=row['call_id']))
        self.fatal = self.fatal or err
        return err

    def _storage_error(self, row, exc, what):
        if isinstance(exc, sqlite3.Error) or classify_exception(exc) == HOST_ERROR:
            return self._host_error(row, exc, what)
        row['storage_error'] = {'what': what, 'type': type(exc).__name__, 'errno': getattr(exc, 'errno', None)}
        self.fatal = self.fatal or exc
        return exc

    def _store(self, row, kind, data):
        try:
            super()._store(row, kind, data)
        except OSError as exc:
            raise self._storage_error(row, exc, f'store {kind}') from exc
        if kind == 'request':
            summary = _request_summary(data)
            record = {'call_id': row['call_id'], 'actor': row['actor'], 'ledger_seq': row['seq'],
                      'body_sha256': row['body_sha256'], 'request_bytes': row['bytes'],
                      'request_path': str(self.store_dir / row['request_path']), 'url': row['url'],
                      **summary}
            try:
                reserved = self.budget.record_request(self.run_key, record)
            except BudgetExceeded as exc:
                row['budget_cap'] = True
                self.fatal = self.fatal or exc
                raise
            except (OSError, sqlite3.Error) as exc:  # ledger storage (disk full, locked file) = host
                raise self._storage_error(row, exc, 'ledger') from exc
            row['budget_request_id'] = reserved['id']
            row['images'] = summary.get('images', [])
        else:
            response = None
            try:
                response = json.loads(data)
            except ValueError:
                pass
            usage = response.get('usage') if isinstance(response, dict) else None
            row['provider_usage'] = usage if isinstance(usage, dict) else None
            row['response_model'] = response.get('model') if isinstance(response, dict) else None
            row['completion'] = assess_completion(response, study_json=True)

    def _preflight_live(self):
        if self.runtime is None or self.proxy is None:
            raise HostError('running proxy identity required (preflight not done)')
        from harness.zone_pilot_budget import sha
        if sha(Path(self.proxy['source_path']).read_bytes()) != self.proxy['source_sha256']:
            raise HostError('installed proxy source changed during the run')
        try:
            os.kill(self.runtime['pid'], 0)
        except OSError as exc:
            raise HostError(f'proxy process {self.runtime["pid"]} is gone') from exc

    def _send(self, call_id, actor, request, timeout):
        if self.fatal is not None:
            raise self.fatal
        if self.live:
            self._preflight_live()
        request.add_header('X-UGRP-Call-ID', f'{self.run_key}:{call_id}:{len(self.entries) + 1}')
        before = len(self.entries)
        wall0, tick = time.time_ns(), time.monotonic_ns()
        error = None
        try:
            return super()._send(call_id, actor, request, timeout)
        except BaseException as exc:
            error = exc
            raise
        finally:
            if len(self.entries) > before:
                row = self.entries[-1]
                if row.get('budget_cap'):
                    row['reason'] = 'budget_cap'
                row['sent_at_ns'], row['latency_ms'] = wall0, round((time.monotonic_ns() - tick) / 1e6, 3)
                if isinstance(error, HTTPError):
                    row['http_status'] = error.code
                if error is not None and 'wire_error' not in row and row['status'] == 'sent':
                    row['wire_error'] = type(error).__name__
                row['failure_class'] = call_failure_class(row)
                if row.get('budget_request_id'):
                    try:
                        self.budget.settle_request(
                            row['budget_request_id'],
                            status='response_received' if 'response_sha256' in row else 'wire_error',
                            provider_usage=row.get('provider_usage'), response_model=row.get('response_model'),
                            response_sha256=row.get('response_sha256'), response_bytes=row.get('response_bytes'),
                            response_path=(str(self.store_dir / row['response_path'])
                                           if row.get('response_path') else None),
                            completion=row.get('completion'), wire_error=row.get('wire_error'),
                            http_status=row.get('http_status'), latency_ms=row['latency_ms'],
                            sent_at_ns=wall0, failure_class=row['failure_class'])
                    except (OSError, sqlite3.Error) as exc:
                        failure = self._storage_error(row, exc, 'ledger settle')
                        row['failure_class'] = call_failure_class(row)
                        raise failure from exc


def live_proxy(profile, pid):
    """Read-only proxy identity: audited source hash + running PID listening on the URL.

    Never starts, restarts or edits the installed proxy. Any failure is a
    HOST_ERROR before the first model request.
    """
    from harness.zone_pilot_ledger import proxy_profile, runtime_identity
    try:
        proxy = proxy_profile(Path(profile['proxy_source']).expanduser(), profile['proxy_url'])
        proxy['requested_settings'] = dict(profile['model'])
        proxy.pop('accounting', None)
        return proxy, runtime_identity(proxy, pid)
    except Exception as exc:  # noqa: BLE001 - classified, then re-raised as a host error
        raise HostError(f'proxy preflight failed: {exc}') from exc


def build_adapter(profile, *, budget, run_key, store_dir, runtime=None, proxy=None, wire=None):
    ledger = MainStudySendLedger(store_dir=store_dir, budget=budget, run_key=run_key, profile=profile,
                                 runtime=runtime, proxy=proxy, wire=wire)
    return zi.ModelAdapter(client_factory(profile), ledger)


class LiveDriver:
    """One cohort's model driver: registered profile + main-study ledger (+ live proxy identity).

    ``wire`` replaces only the network (fake model in tests); then no proxy
    process is checked and ``live`` is False.
    """

    def __init__(self, profile, *, budget, cohort_id, proxy_pid=None, wire=None):
        self.profile, self.budget, self.cohort_id = profile, budget, cohort_id
        self.proxy_pid, self.wire = proxy_pid, wire
        self.pacer = RequestPacer(profile['min_request_interval_s'])
        self.client_factory = client_factory(profile)
        budget.cohort(cohort_id)  # registered, or KeyError

    @classmethod
    def from_prereg(cls, prereg, *, prereg_sha256, source, proxy_pid=None, create_budget=False, wire=None,
                    bundle_id=None):
        """Prereg ``llm_driver``: profile, cohort_id, cohort_token_cap, unknown_usage_charge_tokens, budget_db."""
        from harness.zone_main_budget import MainStudyBudget
        spec = prereg.get('llm_driver')
        keys = {'profile', 'cohort_id', 'cohort_token_cap', 'unknown_usage_charge_tokens', 'budget_db'}
        if not isinstance(spec, Mapping) or set(spec) != keys:
            raise ContractViolation(f'prereg llm_driver must have exactly {sorted(keys)} (cap may be null)')
        if 'speech_cap_profile' not in prereg:
            raise ContractViolation('a model run needs an explicit registered speech_cap_profile in the prereg')
        speech_caps_for(prereg, bundle_id=bundle_id)
        profile = driver_profile(spec['profile'], bundle_id=bundle_id)
        path = Path(spec['budget_db']).expanduser()
        if not path.is_absolute():
            raise ContractViolation('llm_driver.budget_db must be an absolute path (primary checkout outputs/)')
        budget = MainStudyBudget.create(path) if create_budget else MainStudyBudget(path)
        budget.register_cohort(spec['cohort_id'], token_cap=spec['cohort_token_cap'],
                               unknown_usage_charge_tokens=spec['unknown_usage_charge_tokens'],
                               prereg_sha256=prereg_sha256, source=source)
        return cls(profile, budget=budget, cohort_id=spec['cohort_id'], proxy_pid=proxy_pid, wire=wire)

    @property
    def live(self):
        return self.wire is None

    def bundle_record(self) -> dict:
        """What the run bundle pins: the profile, not the cohort/ledger location."""
        return {'driver_version': DRIVER_VERSION, 'profile_id': self.profile['profile_id'],
                'profile_sha256': self.profile['sha256'], 'model': dict(self.profile['model']),
                'proxy_url': self.profile['proxy_url'], 'retry_policy': self.profile['retry_policy'],
                'min_request_interval_s': self.profile['min_request_interval_s'],
                'api_failure_trial_rule': self.profile['api_failure_trial_rule']}

    def ledger_record(self) -> dict:
        return {'ledger_id': self.budget.meta['ledger_id'], 'path': str(self.budget.path),
                'cohort': self.budget.cohort(self.cohort_id), 'live': self.live}

    def start_run(self, run_key, *, bundle_id, bundle_sha256, record):
        return self.budget.start_run(run_key, cohort_id=self.cohort_id, bundle_id=bundle_id,
                                     bundle_sha256=bundle_sha256, record=record)

    def adapter(self, *, run_key, store_dir):
        """Per attempt. Live: read-only proxy preflight first (HOST_ERROR before any request)."""
        check_disk(store_dir, min_free_gib=self.profile['min_free_disk_gib'])
        proxy = runtime = None
        if self.live:
            if type(self.proxy_pid) is not int:
                raise HostError('live model run needs the running proxy PID (--proxy-pid)')
            proxy, runtime = live_proxy(self.profile, self.proxy_pid)
        ledger = MainStudySendLedger(store_dir=store_dir, budget=self.budget, run_key=run_key,
                                     profile=self.profile, runtime=runtime, proxy=proxy, wire=self.wire,
                                     pacer=self.pacer)
        ledger.proxy_identity = {'profile': proxy, 'runtime': runtime}
        return zi.ModelAdapter(self.client_factory, ledger)


# ---------------------------------------------------------------------------
# Records

def call_rows(ledger) -> list:
    """One row per POST: tokens, latency, failure class, raw file names (no bytes duplicated)."""
    rows = []
    for e in ledger.entries:
        usage = e.get('provider_usage')
        rows.append({'seq': e['seq'], 'call_id': e['call_id'], 'actor': e['actor'], 'status': e['status'],
                     'reason': e.get('reason'), 'request_path': e.get('request_path'),
                     'response_path': e.get('response_path'), 'body_sha256': e['body_sha256'],
                     'response_sha256': e.get('response_sha256'), 'images': e.get('images', []),
                     'provider_usage': usage, 'usage_known': known_total(usage) is not None,
                     'response_model': e.get('response_model'), 'latency_ms': e.get('latency_ms'),
                     'http_status': e.get('http_status'), 'wire_error': e.get('wire_error'),
                     'completion': e.get('completion'),
                     'failure_class': e.get('failure_class', call_failure_class(e)),
                     'budget_request_id': e.get('budget_request_id')})
    return rows


def usage_summary(rows) -> dict:
    sent = [r for r in rows if r['status'] == 'sent']
    known = [known_total(r['provider_usage']) for r in sent]
    latencies = sorted(r['latency_ms'] for r in sent if r['latency_ms'] is not None)
    field = lambda k: sum(r['provider_usage'][k] for r in sent if r['usage_known'])  # noqa: E731
    return {'requests': len(sent), 'blocked': len(rows) - len(sent),
            'tokens_prompt': field('prompt_tokens'), 'tokens_completion': field('completion_tokens'),
            'tokens_total_known': sum(t for t in known if t is not None),
            'usage_unknown_requests': sum(t is None for t in known),
            'tokens_complete': bool(sent) and all(t is not None for t in known),
            'api_error_requests': sum(r['failure_class'] == API_ERROR for r in sent),
            'api_error_fraction': (sum(r['failure_class'] == API_ERROR for r in sent) / len(sent)
                                   if sent else None),
            'api_clean': not any(r['failure_class'] == API_ERROR for r in rows),
            'latency_ms': {'n': len(latencies), 'sum': round(sum(latencies), 3),
                           'max': latencies[-1] if latencies else None,
                           'median': latencies[len(latencies) // 2] if latencies else None},
            'failure_classes': dict(Counter(r['failure_class'] for r in rows if r['failure_class'])),
            'response_models': sorted({r['response_model'] for r in sent if r['response_model']})}


def trial_failure_class(exception, ledger, *, transport=None) -> str | None:
    """All conditions: any API error/cap or zero normal model replies is infrastructure."""
    if exception is not None:
        return classify_exception(exception)
    if ledger is None:
        return None
    if getattr(ledger, 'host_errors', None):
        return HOST_ERROR
    if getattr(ledger, 'fatal', None) is not None:
        return classify_exception(ledger.fatal)
    if getattr(transport, 'budget_exhausted', False):
        return API_ERROR
    rows = call_rows(ledger)
    sent = [r for r in rows if r['status'] == 'sent']
    if any(r['failure_class'] in (API_ERROR, 'budget_cap') for r in rows):
        return API_ERROR
    if not any(r.get('completion') and normal_completion(r['completion'])
               and r['failure_class'] is None for r in sent):
        return API_ERROR
    return None


def check_trial_health(trial, *, final=False):
    """Runner boundary: abort before another physics step after a fatal or zero-reply attempt."""
    ledger = trial.send_ledger
    if not isinstance(ledger, MainStudySendLedger):
        return
    if ledger.fatal is not None:
        raise ledger.fatal
    if trial.transport.budget_exhausted:
        raise BudgetExceeded('cohort budget exhausted')
    if not final and getattr(ledger, '_health_checked_entries', -1) == len(ledger.entries):
        return
    ledger._health_checked_entries = len(ledger.entries)
    cohort = ledger.budget.run(ledger.run_key)['cohort_id']
    ledger.budget.check_available(cohort)
    if final or trial.transport.resolved:
        rows = call_rows(ledger)
        if not any(r['status'] == 'sent' and r['failure_class'] is None
                   and r.get('completion') and normal_completion(r['completion']) for r in rows):
            raise GeminiProxyError('no successful model response', error_kind='budget', retryable=False)


# ---------------------------------------------------------------------------
# Attempts: the only retry

def may_retry(*, attempt, failure_class, model_requests) -> bool:
    """Prereg §8: once, in place, only for a host error before the first model request."""
    return attempt < MAX_ATTEMPTS and failure_class == HOST_ERROR and model_requests == 0


def run_attempts(attempt_fn, *, budget, run_id, start):
    """Run ``attempt_fn(attempt, run_key)`` with the single permitted retry; keep every attempt.

    ``start(attempt, run_key)`` registers the attempt in the ledger before any
    work. ``attempt_fn`` returns ``(record, exception_or_None)``. Nothing after
    the first model request is ever re-run.
    """
    attempts = []
    for attempt in range(1, MAX_ATTEMPTS + 1):
        run_key = f'{run_id}#a{attempt}'
        start(attempt, run_key)
        record, exc = None, None
        try:
            record, exc = attempt_fn(attempt, run_key)
        except Exception as raised:  # noqa: BLE001 - recorded as this attempt's failure
            exc = raised
        failure = (classify_exception(exc) if exc is not None
                   else record.get('failure_class') if isinstance(record, Mapping) else None)
        requests = budget.run_requests(run_key)
        budget.finish_run(run_key, status='failed' if exc is not None or failure is not None else 'finished', failure_class=failure,
                          summary={'exception': None if exc is None else f'{type(exc).__name__}: {exc}'[:500]})
        retry = may_retry(attempt=attempt, failure_class=failure, model_requests=requests)
        attempts.append({'attempt': attempt, 'run_key': run_key, 'failure_class': failure,
                         'model_requests': requests, 'retried': retry,
                         'exception': None if exc is None else f'{type(exc).__name__}: {exc}'[:500]})
        if not retry:
            return record, exc, attempts
    return record, exc, attempts


__all__ = ['API_ERROR', 'DEFAULT_SPEECH_CAPS', 'DRIVER_VERSION', 'HOST_ERROR', 'HostError', 'LiveDriver',
           'MainStudySendLedger',
           'build_adapter', 'call_failure_class', 'call_rows', 'check_disk', 'classify_exception', 'client_factory',
           'driver_profile', 'live_proxy', 'load_registry', 'may_retry', 'run_attempts', 'speech_caps',
           'speech_caps_for', 'trial_failure_class', 'usage_summary']
