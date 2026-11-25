"""Counted OpenRouter requests with a persistent dollar reservation budget."""

import fcntl
import hashlib
import http.client
import json
import math
import os
from pathlib import Path
import random
import re
import threading
import time
from decimal import Decimal
import uuid
from email.utils import parsedate_to_datetime


class CallLimitError(RuntimeError):
    """A local or shared campaign budget has been exhausted."""


class TransportError(RuntimeError):
    """The request failed; it remains counted and must not be silently retried."""


class ResponseError(ValueError):
    """The gateway or action response did not satisfy the protocol."""


class RateLimitError(TransportError):
    """HTTP 429; counted, unbilled, and retryable within the episode cap."""
    retry_kind = "rate_limit"


class ServerBusyError(TransportError):
    """HTTP 408/5xx/529 from the gateway or its provider: counted, billing unknown (charged at its reservation upper bound), retryable."""
    retry_kind = "http_5xx"


class DuplicateRequestIdError(TransportError):
    """HTTP 400 reporting a duplicate request ID from the gateway or provider: counted, billing unknown (charged at its reservation upper bound), retryable once with a fresh request ID."""
    retry_kind = "duplicate_request_id"


class TransientResponseError(ResponseError):
    """A 200 reply that holds no usable completion (empty content, cut off by the output limit, unreadable body): counted and billed as the gateway reports, retryable a few times."""
    retry_kind = "truncated"


class InfraError(RuntimeError):
    """The LLM service did not deliver after the bounded retries (429, 5xx, timeouts, cut-off or unreadable replies, duplicate request ID, or the key-usage endpoint of the spend guard stayed unreachable).
    An infrastructure failure, not a result of the experiment: the brain marks the run (brain-record `infra_error`) and ends it instead of halting one robot silently.
    kind: rate_limit | http_5xx | network | truncated | bad_body | duplicate_request_id | key_usage_unavailable; the message never holds a credential or a reply body."""

    def __init__(self, kind, *, http_status=None, attempts=0, waited_s=0.0, gave_up="", detail=None):
        super().__init__("LLM infrastructure error: %s after %d attempts (%.0f s waited)%s" % (kind, attempts, waited_s, ", " + gave_up if gave_up else ""))
        self.kind, self.http_status, self.attempts, self.waited_s, self.gave_up, self.detail = kind, http_status, attempts, waited_s, gave_up, detail


FAILED_ATTEMPT_DECISION = {
    "authority": "worker", "date": "2026-11-21", "basis": "reservation upper bound",
    "reason": "a transient failed attempt whose billing the gateway did not report is charged at its reservation, so the ledger stays resolved and the budget stays bounded",
}

HTTP429_DECISION = {
    "authority": "main", "date": "2026-11-13",
    "reason": "HTTP429 unprocessed request; main confirms no charge",
    "provider_delta_usd": "0.020548816", "known_ledger_usd": "0.0208428128",
}


def validate_http429_reconciliation(entry, settlement):
    """Validate an owner's explicit historical correction, never infer unknown costs."""
    proof = entry.get("http429_evidence", {})
    if (entry.get("event") != "reconcile_http429"
            or entry.get("decision") != HTTP429_DECISION
            or type(entry.get("cost_usd")) not in (int, float)
            or entry["cost_usd"] != 0
            or settlement is None or settlement.get("cost_usd") is not None
            or settlement.get("status") != "transport_error"
            or settlement.get("auth_quota_error") is not True
            or entry.get("original_settlement") != settlement
            or proof != {"attempt_id": entry.get("attempt_id"),
                         "http_status": 429, "status": "transport_error",
                         "event": "finish", "cost_usd": None}):
        raise ValueError("Invalid HTTP429 reconciliation")


HTTP402_ATTEMPT = "cbfe63e0543b44339c84bb6101a6d020"
HTTP402_DECISION = {
    "authority": "user", "date": "2026-11-14", "source": "TASK-ASTRA-8.md",
    "reason": "Explicit zero-cost correction of the historical Task7 HTTP402 attempt",
}


def validate_http402_reconciliation(entry, settlement):
    """Only the Task8-authorized historical failure may be corrected to zero."""
    if (entry.get("event") != "reconcile_http402"
            or entry.get("attempt_id") != HTTP402_ATTEMPT
            or entry.get("decision") != HTTP402_DECISION
            or type(entry.get("cost_usd")) not in (int, float)
            or entry["cost_usd"] != 0
            or settlement is None
            or settlement.get("event") != "settle"
            or settlement.get("attempt_id") != HTTP402_ATTEMPT
            or "cost_usd" not in settlement or settlement["cost_usd"] is not None
            or settlement.get("status") != "transport_error"
            or settlement.get("auth_quota_error") is not True
            or entry.get("original_settlement") != settlement
            or entry.get("http402_evidence") != {
                "attempt_id": HTTP402_ATTEMPT, "http_status": 402,
                "status": "transport_error", "event": "finish", "cost_usd": None}):
        raise ValueError("Invalid HTTP402 reconciliation")


def _money(value):
    return type(value) in (int, float) and math.isfinite(value) and value >= 0


def _strict_json(text):
    def pairs(items):
        result = {}
        for key, value in items:
            if key in result:
                raise ValueError("duplicate JSON key")
            result[key] = value
        return result

    def constant(_):
        raise ValueError("non-finite JSON constant")

    def number(value):
        result = float(value)
        if not math.isfinite(result):
            raise ValueError("non-finite JSON number")
        return result

    return json.loads(text, object_pairs_hook=pairs, parse_constant=constant,
                      parse_float=number)


def _load_route(model):
    if not isinstance(model, str) or not re.fullmatch(r"[\w.-]+/[\w.:-]+", model):
        raise ValueError("Expected an explicit OpenRouter model ID")
    try:
        key = (Path.home() / ".config/openrouter/api_key").read_text().strip()
        if not key or "\r" in key or "\n" in key:
            raise ValueError()
        return "openrouter.ai", 443, "/api/v1/chat/completions", model, key
    except Exception:
        raise RuntimeError("OpenRouter credential unavailable") from None


def key_usage():
    host, port, _, _, key = _load_route("z-ai/glm-5.3-flash")
    connection = http.client.HTTPSConnection(host, port, timeout=30)      # was 60 s: the guard retries up to 6 times, so one slow try must not eat the request's budget
    try:
        connection.request("GET", "/api/v1/key", headers={"Authorization": "Bearer " + key})
        response = connection.getresponse()
        if response.status != 200:
            raise TransportError("Key usage unavailable: HTTP " + str(response.status))
        data = _strict_json(response.read(65536).decode())["data"]
        return {"usage": float(data["usage"]), "measured_at": time.time()}
    finally:
        connection.close()


# ---- Hard spending guards (coordinator, 2026-11-13, at the user's request). ----------------------
# They sit below every caller: no runner, campaign script or argument can raise them.
#   * HARD_EPISODE_CALLS: paid calls one client instance (one episode) may make. An episode that
#     never finished made 906 calls before this existed.
#   * HARD_CAMPAIGN_USD: ceiling for any single campaign ledger.
#   * the guard file: total dollars this project may spend from the moment the file was written,
#     checked against the provider's own key usage when a client is created. Raising any of these
#     is a decision for the user, not for a worker.
HARD_EPISODE_CALLS = 600
HARD_CAMPAIGN_USD = 1.5
GUARD_FILE = Path.home() / ".config/openrouter/l0_spend_guard.json"
_REAL_HTTPS = http.client.HTTPSConnection

# ---- Per-model request profile (second-model work, 2026-11-15). ---------------------------------------
# The default model (z-ai/glm-5.3-flash) keeps its exact request body: no entry here, so ceilings 0.1/0.2 USD per
# million tokens and reasoning {"effort": "low"} apply as before. A listed model differs only where it must:
#   * reasoning: False -> the request carries no "reasoning" key (the model has no reasoning parameter; with
#     require_parameters=true OpenRouter would find no provider for a request that names one);
#   * max_price: provider price ceilings in USD per million tokens, also the unit prices of the dollar reservation.
# Provider listing checked 2026-11-15 (OpenRouter /models/<id>/endpoints): qwen/qwen3-235b-a22b-2507 is offered at
# 0.072-0.20 USD/M in and 0.44-0.825 USD/M out, none of the six endpoints lists "reasoning" among supported parameters.
MODEL_PROFILES = {
    "qwen/qwen3-235b-a22b-2507": {"reasoning": False, "max_price": {"prompt": 0.25, "completion": 0.9}},
}
DEFAULT_MAX_PRICE = {"prompt": 0.1, "completion": 0.2}

# ---- Retry policy of one logical call (Neon/pilot-1 finding 2026-11-21: 429 four times in a row, 5 + 15 + 30 s, stopped a robot silently). -------------------------
# Wall-clock waits only: the simulator advances in its own loop (run_team_carry clock = MuJoCo time) and does nothing while a planner request is open, so waiting changes no result.
# RETRY_STATUS: statuses that are retried. 429 is unbilled (HTTP429_DECISION); for the others the billing of the failed attempt is unknown, so it is charged at its
# reservation (an upper bound) and the campaign ledger stays resolved. Every attempt is reserved, counted (call_count, the per-instance and campaign caps) and logged.
RETRY_STATUS = frozenset({408, 425, 429, 500, 502, 503, 504, 529})
RETRY_BASE_S = 5.0            # backoff 5, 10, 20, 40, 60, 60 ... s (x 0.75-1.25 jitter)
RETRY_MAX_BACKOFF_S = 60.0
RETRY_AFTER_CAP_S = 300.0     # a longer Retry-After is clipped (and by the remaining budget)
RETRY_TOTAL_S = 600.0         # most cumulative wait of one logical call (the brain's per-request deadline shortens it: the executor reads a planner reply for 600 s at most)
# At minimum jitter, 17 backoff waits cover 600 s. Three short retries and the final attempt still fit.
RETRY_MAX_ATTEMPTS = 24
LEGACY_RETRY_MAX_ATTEMPTS = 14
RESPONSE_RETRIES = 2          # cut-off / empty / unreadable 200 replies: two more tries (billed), a short jitter wait
RESPONSE_KINDS = ("truncated", "bad_body")
DUPLICATE_REQUEST_ID_RETRIES = 1      # HTTP 400 "duplicate request ID" (provider-side collision, e.g. Relace): one retry with a fresh X-Request-Id
DUPLICATE_REQUEST_ID_RE = re.compile(r"duplicate\s+request[\s_-]*id", re.I)


def check_spend_guard():
    """Fail closed: no guard file, an unreadable file or an unreachable usage endpoint blocks paid calls."""
    if http.client.HTTPSConnection is not _REAL_HTTPS:
        # The network class has been replaced (offline tests): no real request can leave, so no money can.
        return {"skipped": "transport is mocked"}
    try:
        if _load_route("z-ai/glm-5.3-flash")[0] != "openrouter.ai":
            # Tests point the route at a local stand-in server: nothing is billed.
            return {"skipped": "route is not the paid provider"}
    except Exception:
        pass
    try:
        guard = json.loads(GUARD_FILE.read_text())
        baseline, limit = float(guard["baseline_usage_usd"]), float(guard["limit_usd"])
        if not math.isfinite(baseline) or not math.isfinite(limit) or limit <= 0:
            raise ValueError("Invalid spend guard")
        limit = min(limit, 10.0)  # was 2.0; raised 2026-11-17 by the user (thread approval)
    except Exception:
        raise CallLimitError("Spend guard file missing or unreadable; paid calls blocked") from None
    usage = None
    for retry in range(6):          # was 3 tries 2 s apart; the key endpoint can be rate limited or slow too: 2, 4, 8, 16, 30 s (+ jitter), about a minute in all
        try:
            usage = key_usage()["usage"]
            break
        except Exception:  # noqa: BLE001
            if retry < 5:
                time.sleep(min(2.0 * 2 ** retry, 30.0) * random.uniform(0.75, 1.25))
    if usage is None:
        # not a budget limit: the guard could not be read. Paid calls stay blocked (fail closed), and the brain marks the run as an infrastructure error
        raise InfraError("key_usage_unavailable", attempts=6, waited_s=60.0, gave_up="key usage endpoint unreachable")
    spent = usage - baseline
    if spent >= limit:
        raise CallLimitError("Project spend guard reached: %.4f of %.2f USD" % (spent, limit))
    return {"spent_usd": spent, "limit_usd": limit}


def parse_retry_after(headers, now=None):
    """Seconds to wait that the gateway asked for, or None: `Retry-After` (seconds or an HTTP date) first, else `X-RateLimit-Reset` (epoch milliseconds, as OpenRouter sends it).
    headers: {lower-case name: value}. Never negative; the caller clips it."""
    now = time.time() if now is None else now
    value = headers.get("retry-after")
    if value is not None:
        try:
            return max(0.0, float(value))
        except ValueError:
            try:
                return max(0.0, parsedate_to_datetime(value).timestamp() - now)
            except (TypeError, ValueError):
                pass
    reset = headers.get("x-ratelimit-reset")
    if reset is not None:
        try:
            when = float(reset)
            return max(0.0, (when / 1000.0 if when > 1e11 else when) - now)
        except ValueError:
            pass
    return None


def _safe_headers(response):
    """The reply headers worth keeping with a failed attempt (retry-after, rate-limit and edge/request ids), lower-cased, cut to 200 chars; never a cookie or credential."""
    out = {}
    for name, value in response.getheaders():
        name = name.lower()
        if any(word in name for word in ("cookie", "authorization", "token", "key")):
            continue
        out[name] = str(value)[:200]
    return out


def _error_detail(body, key):
    """What an error reply says about WHO refused: {code, message, provider_name, raw} cut to 300 chars, the credential replaced; {} when the body is not the usual JSON."""
    try:
        data = json.loads(body.decode("utf-8", "replace"))
        error = data.get("error") if isinstance(data, dict) else None
        if not isinstance(error, dict):
            return {"body_prefix": body[:200].decode("utf-8", "replace").replace(key, "[REDACTED]")}
        meta = error.get("metadata") if isinstance(error.get("metadata"), dict) else {}
        pick = lambda v: None if v is None else str(v).replace(key, "[REDACTED]")[:300]
        return {"code": error.get("code") if type(error.get("code")) in (int, str) else None, "message": pick(error.get("message")),
                "provider_name": pick(meta.get("provider_name")), "raw": pick(meta.get("raw"))}
    except Exception:  # noqa: BLE001
        return {}


def _is_duplicate_request_id(status, raw_body, detail):
    """True when HTTP 400 reports a duplicate request ID in the raw error body or parsed error metadata."""
    if status != 400:
        return False
    parts = [raw_body.decode("utf-8", "replace")] if isinstance(raw_body, (bytes, bytearray)) else []
    if isinstance(detail, dict):
        parts.extend(v for v in detail.values() if isinstance(v, str))
    return any(DUPLICATE_REQUEST_ID_RE.search(part) for part in parts)


class RealLLM:
    """Counted HTTP attempts, with bounded retries of transient failures (429, 5xx, timeouts, cut-off replies) and no implicit fallback.

    All processes in a campaign must use the same campaign_log_path (the default
    is campaign-calls.jsonl beside log_path). Its append-only, flock-protected
    reservation ledger counts attempts, including crashes and failures. Unknown
    costs and unfinished reservations block further paid calls, not cache hits.
    records contains one mutable record per call (including cache hits).
    Set UGRP_V8_RETRY_WINDOW=1 before construction to keep exponential backoff
    when the gateway supplies a short Retry-After and use the full retry budget.
    """

    def __init__(self, max_calls, log_path, model="z-ai/glm-5.3-flash", *, timeout_s=90.0,
                 campaign_log_path=None, max_output_tokens=384, reasoning=None,
                 budget_usd=1.5, max_input_tokens=71024, campaign_max_calls=None,
                 cache_dir=None, temperature=0.0, retry_total_s=RETRY_TOTAL_S):
        for name, value in (("max_calls", max_calls), ("campaign_max_calls", campaign_max_calls)):
            if value is not None and (type(value) is not int or value < 0):
                raise ValueError(name + " must be None or a nonnegative integer")
        if max_calls is not None and campaign_max_calls is not None and max_calls > campaign_max_calls:
            raise ValueError("max_calls must be within the campaign cap")
        for name, value in (("max_output_tokens", max_output_tokens),
                            ("max_input_tokens", max_input_tokens)):
            if type(value) is not int or value <= 0:
                raise ValueError(name + " must be a positive integer")
        for name, value in (("budget_usd", budget_usd), ("temperature", temperature)):
            if type(value) not in (int, float) or not math.isfinite(value) or value < 0:
                raise ValueError(name + " must be finite and nonnegative")
        if temperature > 2:
            raise ValueError("temperature must be at most 2")
        profile = MODEL_PROFILES.get(model, {})
        if profile.get("reasoning") is False:
            if reasoning is not None:
                raise ValueError("%s has no reasoning parameter" % model)
            reasoning = None
        else:
            reasoning = {"effort": "low"} if reasoning is None else dict(reasoning)
        if reasoning is not None and (set(reasoning) - {"effort", "enabled", "exclude", "max_tokens"}
                or ("effort" in reasoning and reasoning["effort"] not in
                    ("none", "minimal", "low", "medium", "high", "xhigh", "max"))
                or any(type(reasoning[k]) is not bool for k in ("enabled", "exclude") if k in reasoning)
                or ("max_tokens" in reasoning and (type(reasoning["max_tokens"]) is not int
                    or reasoning["max_tokens"] <= 0 or "effort" in reasoning))):
            raise ValueError("Invalid reasoning configuration")
        if model == "z-ai/glm-5.3-flash" and (
                reasoning.get("enabled") is False or "max_tokens" in reasoning
                or reasoning.get("effort", "low") not in ("low", "high", "max")):
            raise ValueError("GLM 5.3 Flash requires reasoning; supported efforts: low, high, max")
        if not isinstance(timeout_s, (int, float)) or not math.isfinite(timeout_s) or timeout_s <= 0:
            raise ValueError("timeout_s must be finite and positive")
        if not isinstance(retry_total_s, (int, float)) or not math.isfinite(retry_total_s) or retry_total_s < 0:
            raise ValueError("retry_total_s must be finite and nonnegative")
        self.max_calls = HARD_EPISODE_CALLS if max_calls is None else min(max_calls, HARD_EPISODE_CALLS)
        self.spend_guard = None  # checked once, right before the first paid request
        self.log_path = Path(log_path)
        self.campaign_log_path = (Path(campaign_log_path) if campaign_log_path is not None
                                  else self.log_path.parent / "campaign-calls.jsonl")
        if self.log_path.resolve() == self.campaign_log_path.resolve():
            raise ValueError("Call log and campaign ledger must be distinct")
        self.model = model
        self.max_output_tokens = max_output_tokens
        self.max_input_tokens = max_input_tokens
        self.reasoning = reasoning
        self.max_price = dict(profile.get("max_price", DEFAULT_MAX_PRICE))
        self.budget_usd = min(budget_usd, HARD_CAMPAIGN_USD)
        self.campaign_max_calls = campaign_max_calls
        self.temperature = float(temperature)
        self.cache_dir = (Path(cache_dir) if cache_dir is not None else
                          self.campaign_log_path.parent / "llm-cache-v3")
        self.timeout_s = float(timeout_s)
        self.retry_total_s = float(retry_total_s)
        self._retry_window = os.environ.get("UGRP_V8_RETRY_WINDOW") == "1"
        self.deadline = None                  # time.monotonic() value by which the caller needs its answer (brain_server sets it per request): retries stop in time to finish before it
        self._sleep, self._clock, self._rng = time.sleep, time.monotonic, random.Random()      # replaced in tests
        self.records = []
        self._lock = threading.Lock()
        self._route = None

    @property
    def call_count(self):
        return sum(not record.get("cache_hit", False) for record in self.records)

    @property
    def cache_hits(self):
        return sum(record.get("cache_hit", False) for record in self.records)

    def _append(self, record):
        with self.log_path.open("a", encoding="utf-8") as stream:
            fcntl.flock(stream, fcntl.LOCK_EX)
            stream.write(json.dumps(record, ensure_ascii=True, allow_nan=False) + "\n")
            stream.flush()
            os.fsync(stream.fileno())

    def _ledger(self, attempt_id, *, reserve_usd=None, settlement=None, reconciliation=None):
        with self.campaign_log_path.open("a+", encoding="utf-8") as stream:
            fcntl.flock(stream, fcntl.LOCK_EX)
            stream.seek(0)
            attempts = {}
            settlements = {}
            reconciled = set()
            streak = 0
            halted = False
            budget = Decimal(str(self.budget_usd))
            cap = self.campaign_max_calls
            for line in stream:
                # A damaged ledger fails closed rather than resetting the budget.
                entry = _strict_json(line)
                if not isinstance(entry, dict) or not isinstance(entry.get("attempt_id"), str):
                    raise ValueError("Invalid campaign ledger")
                ident = entry["attempt_id"]
                event = entry.get("event", "legacy")
                if event in ("reserve", "legacy"):
                    if ident in attempts:
                        raise ValueError("Duplicate campaign reservation")
                    amount = entry.get("reserve_usd")
                    if amount is not None and not _money(amount):
                        raise ValueError("Invalid campaign reservation amount")
                    attempts[ident] = {"reserve": amount, "cost": None, "settled": False}
                    if event == "reserve":
                        prior_cap = entry.get("campaign_max_calls")
                        if (not _money(entry.get("budget_usd"))
                                or "campaign_max_calls" not in entry
                                or (prior_cap is not None and
                                    (type(prior_cap) is not int or prior_cap < 0))):
                            raise ValueError("Invalid campaign limits")
                        budget = min(budget, Decimal(str(entry["budget_usd"])))
                        if prior_cap is not None:
                            cap = prior_cap if cap is None else min(cap, prior_cap)
                elif event == "settle":
                    if ident not in attempts or attempts[ident]["settled"]:
                        raise ValueError("Invalid campaign settlement")
                    cost = entry.get("cost_usd")
                    if cost is not None and not _money(cost):
                        raise ValueError("Invalid campaign cost")
                    attempts[ident].update(cost=cost, settled=True)
                    settlements[ident] = entry
                    if type(entry.get("auth_quota_error")) is not bool:
                        raise ValueError("Invalid campaign error flag")
                    streak = streak + 1 if entry["auth_quota_error"] else 0
                    halted = halted or streak >= 2
                elif event in ("reconcile_http429", "reconcile_http402"):
                    if ident in reconciled:
                        raise ValueError("Duplicate HTTP reconciliation")
                    validator = (validate_http402_reconciliation if event == "reconcile_http402"
                                 else validate_http429_reconciliation)
                    validator(entry, settlements.get(ident))
                    reconciled.add(ident)
                    attempts[ident]["cost"] = 0
                else:
                    raise ValueError("Unknown campaign ledger event")
            # Recompute historical auth streaks after explicit corrections.
            streak = 0
            halted = False
            for ident, prior in settlements.items():
                streak = streak + 1 if prior["auth_quota_error"] and ident not in reconciled else 0
                halted = halted or streak >= 2
            if reconciliation is not None:
                if attempt_id in reconciled:
                    raise ValueError("Duplicate HTTP reconciliation")
                entry = dict(reconciliation, attempt_id=attempt_id)
                validator = (validate_http402_reconciliation
                             if entry.get("event") == "reconcile_http402"
                             else validate_http429_reconciliation)
                validator(entry, settlements.get(attempt_id))
            elif settlement is not None:
                if attempt_id not in attempts or attempts[attempt_id]["settled"]:
                    raise ValueError("Invalid settlement target")
                entry = dict(settlement, event="settle", attempt_id=attempt_id,
                             settled_at=time.time())
            else:
                if not _money(reserve_usd):
                    raise ValueError("Invalid reservation")
                if cap is not None and len(attempts) >= cap:
                    raise CallLimitError("Campaign attempt cap reached")
                if halted:
                    raise CallLimitError("Campaign halted after two authentication/quota errors")
                # Do not guess costs for old ledgers, crashes, or missing usage.
                # Serial admission also prevents concurrent calls bypassing the stop rule.
                if any(a["cost"] is None for a in attempts.values()):
                    raise CallLimitError("Campaign cost unresolved; reconcile before further paid calls")
                spent = sum((Decimal(str(a["cost"])) for a in attempts.values()), Decimal(0))
                if spent + Decimal(str(reserve_usd)) > budget or spent >= budget:
                    raise CallLimitError("Campaign dollar budget exhausted")
                if attempt_id in attempts:
                    raise ValueError("Duplicate campaign reservation")
                entry = {"event": "reserve", "attempt_id": attempt_id,
                         "reserved_at": time.time(), "reserve_usd": reserve_usd,
                         "budget_usd": float(budget), "campaign_max_calls": cap}
            stream.write(json.dumps(entry, allow_nan=False) + "\n")
            stream.flush()
            os.fsync(stream.fileno())
            return len(attempts) + (settlement is None and reconciliation is None)

    def reconcile_http429(self, finish_record, original_settlement):
        """Owner-only explicit append; no automatic migration of real ledgers."""
        proof = {k: finish_record.get(k) for k in
                 ("attempt_id", "http_status", "status", "event", "cost_usd")}
        return self._ledger(finish_record["attempt_id"], reconciliation={
            "event": "reconcile_http429",
            "cost_usd": 0, "decision": dict(HTTP429_DECISION),
            "original_settlement": original_settlement, "http429_evidence": proof,
            "reconciled_at": time.time()})

    def reconcile_http402(self, finish_record, original_settlement):
        """Explicit Task8 correction only; never infer zero cost for new HTTP402s."""
        proof = {k: finish_record[k] for k in
                 ("attempt_id", "http_status", "status", "event", "cost_usd")
                 if k in finish_record}
        return self._ledger(finish_record.get("attempt_id"), reconciliation={
            "event": "reconcile_http402",
            "cost_usd": 0, "decision": dict(HTTP402_DECISION),
            "original_settlement": original_settlement, "http402_evidence": proof,
            "reconciled_at": time.time()})

    def _reserve(self, attempt_id, reserve_usd=0):
        return self._ledger(attempt_id, reserve_usd=reserve_usd)

    def _settle(self, record):
        return self._ledger(record["attempt_id"], settlement={
            "cost_usd": record["cost_usd"],
            "auth_quota_error": record.get("http_status") in (401, 402, 403),
            "status": record["status"],
        })

    def _retry_wait(self, error, retry):
        """Choose the delay for zero-based retry `retry`, before budget and deadline clipping."""
        asked = getattr(error, "retry_after_s", None)
        short_retry = error.retry_kind in RESPONSE_KINDS or error.retry_kind == "duplicate_request_id"
        retry_after = 0.0
        if asked is not None:
            retry_after = min(max(asked, 1.0), RETRY_AFTER_CAP_S)
            if not self._retry_window or short_retry:
                return retry_after + self._rng.uniform(0.0, 0.25 * max(asked, 4.0))
        if short_retry:
            return self._rng.uniform(1.0, 3.0)
        backoff = min(RETRY_BASE_S * 2 ** retry, RETRY_MAX_BACKOFF_S) * self._rng.uniform(0.75, 1.25)
        return max(retry_after, backoff)

    def call(self, prompt, *, response_format=...):
        """Retry transient failures (RETRY_STATUS, HTTP 400 duplicate request ID once, timeouts, connection errors, cut-off or unreadable replies) with Retry-After / exponential backoff and jitter, within a cumulative wait of
        retry_total_s and the caller's deadline; every attempt carries a fresh request ID, is reserved, counted against the per-instance and campaign caps and logged (event "retry"). When the retries are used up it
        raises InfraError (the service did not deliver; the brain marks the run), never a silent RateLimitError. Other failures raise at once, as before."""
        logical_call_id = uuid.uuid4().hex
        max_attempts = RETRY_MAX_ATTEMPTS if self._retry_window else LEGACY_RETRY_MAX_ATTEMPTS
        waited, attempts, response_retries, dup_id_retries, kinds = 0.0, 0, 0, 0, []
        while True:
            attempts += 1
            try:
                record = self._call_once(prompt, response_format=response_format, logical_call_id=logical_call_id)
                if attempts > 1:
                    record["retries"], record["retry_kinds"], record["retry_wait_s"] = attempts - 1, list(kinds), round(waited, 3)
                return record
            except Exception as error:  # noqa: BLE001
                kind = getattr(error, "retry_kind", None)
                if kind is None:
                    raise
                kinds.append(kind)
                http_status = getattr(error, "http_status", None)
                give_up = ""
                if self.max_calls is not None and self.call_count >= self.max_calls:
                    raise CallLimitError("Per-instance call cap reached") from None
                wait = self._retry_wait(error, attempts - 1)
                if attempts >= max_attempts:
                    give_up = "attempt limit %d" % max_attempts
                elif kind in RESPONSE_KINDS and response_retries >= RESPONSE_RETRIES:
                    give_up = "%d retries of an unusable reply" % RESPONSE_RETRIES
                elif kind == "duplicate_request_id" and dup_id_retries >= DUPLICATE_REQUEST_ID_RETRIES:
                    give_up = "%d retry of duplicate request id" % DUPLICATE_REQUEST_ID_RETRIES
                else:
                    room, why = self.retry_total_s - waited, "wait budget %.0f s used" % self.retry_total_s
                    if self.deadline is not None:
                        left = self.deadline - self._clock() - self.timeout_s - 2.0           # the next attempt may run for timeout_s; the caller's reply is due at the deadline
                        if left < room:
                            room, why = left, "request deadline"
                    if room <= 0:
                        give_up = why
                    else:
                        wait = min(wait, room)
                if give_up:
                    raise InfraError(kind, http_status=http_status, attempts=attempts, waited_s=waited, gave_up=give_up, detail=getattr(error, "detail", None)) from None
                response_retries += kind in RESPONSE_KINDS
                dup_id_retries += kind == "duplicate_request_id"
                self._append({"event": "retry", "logical_call_id": logical_call_id, "attempt": attempts, "kind": kind, "http_status": http_status, "wait_s": round(wait, 3),
                              "retry_after_s": getattr(error, "retry_after_s", None), "waited_s": round(waited, 3), "at": time.time()})
                self._sleep(wait)
                waited += wait

    def _call_once(self, prompt, *, response_format=..., logical_call_id=None):
        """Return raw_output; default to JSON, or omit response_format for None."""
        if not isinstance(prompt, str):
            raise TypeError("prompt must be a string")
        with self._lock:
            if self._route is None:
                self._route = _load_route(self.model)
            host, port, path, model_id, key = self._route
            if key in prompt:
                raise ValueError("Prompt contains a configured credential; not logged or sent")
            attempt_uuid = uuid.uuid4()
            attempt_id = attempt_uuid.hex
            request_id = str(attempt_uuid)
            input_bound = len(prompt.encode("utf-8")) + 1024
            if input_bound > self.max_input_tokens:
                raise ValueError("Conservative input token cap exceeded")
            payload = {"model": model_id,
                       "messages": [{"role": "user", "content": prompt}],
                       "temperature": self.temperature, "stream": False,
                       "max_tokens": self.max_output_tokens, "reasoning": self.reasoning,
                       "provider": {"max_price": self.max_price,
                                    "require_parameters": True, "allow_fallbacks": False}}
            if self.reasoning is None:
                del payload["reasoning"]
            if response_format is not None:
                payload["response_format"] = ({"type": "json_object"}
                                              if response_format is ... else response_format)
            encoded = json.dumps(payload, sort_keys=True, ensure_ascii=True, allow_nan=False)
            if key in encoded:
                raise ValueError("Request settings contain a configured credential")
            cache_key = hashlib.sha256(("l0-response-v3:" + encoded).encode()).hexdigest()
            cache_path = self.cache_dir / (cache_key + ".json")
            if self.temperature == 0 and cache_path.exists():
                cached = _strict_json(cache_path.read_text(encoding="utf-8"))
                if (not isinstance(cached, dict) or cached.get("cache_key") != cache_key
                        or cached.get("status") != "ok" or not isinstance(cached.get("raw_output"), str)
                        or set(cached) != {"cache_key", "raw_output", "actual_model",
                            "requested_model", "provider", "status", "temperature",
                            "max_tokens", "reasoning", "source_usage"}
                        or not isinstance(cached.get("source_usage"), dict)
                        or not _money(cached["source_usage"].get("cost_usd"))
                        or key in json.dumps(cached)):
                    raise ResponseError("Invalid cached response")
                record = dict(cached, attempt_id=attempt_id, logical_call_id=logical_call_id,
                              call_index=self.call_count,
                              cache_hit=True, paid_call=False, cost_usd=0.0,
                              started_at=time.time(), elapsed_s=0.0, raw_prompt=prompt,
                              input_tokens=0, output_tokens=0, reasoning_tokens=0,
                              cached_tokens=0, cache_write_tokens=0,
                              input_chars=len(prompt), output_chars=len(cached["raw_output"]),
                              output_redacted=False)
                self.records.append(record)
                self._append(dict(record, event="cache_hit"))
                return record
            if self.max_calls is not None and self.call_count >= self.max_calls:
                raise CallLimitError("Per-instance call cap reached")
            # Bytes upper-bound text tokens; add framing margin. Price ceilings
            # are enforced in provider routing, including reasoning output.
            if self.spend_guard is None:
                self.spend_guard = check_spend_guard()
            reserve_usd = float((Decimal(input_bound) * Decimal(str(self.max_price["prompt"])) +
                                 Decimal(self.max_output_tokens) * Decimal(str(self.max_price["completion"]))) / Decimal(1000000))
            campaign_count = self._reserve(attempt_id, reserve_usd)
            record = {
                "logical_call_id": logical_call_id,
                "attempt_id": attempt_id, "request_id": request_id, "call_index": self.call_count + 1,
                "campaign_index": campaign_count, "started_at": time.time(),
                "requested_model": model_id, "actual_model": None,
                "temperature": self.temperature, "raw_prompt": prompt, "raw_output": None,
                "input_chars": len(prompt), "output_chars": 0,
                "input_tokens": None, "output_tokens": None,
                "elapsed_s": None, "status": "started", "output_redacted": False,
                "provider": None, "cost_usd": None, "max_tokens": self.max_output_tokens,
                "reasoning": None if self.reasoning is None else dict(self.reasoning),
                "reasoning_tokens": None,
                "cached_tokens": None, "cache_write_tokens": None,
                "input_tokens_upper_bound": input_bound, "reserve_usd": reserve_usd,
                "cache_hit": False, "paid_call": True, "cache_key": cache_key,
            }
            self.records.append(record)
            # Both the campaign reservation and prompt are durable before any socket.
            self._append(dict(record, event="start"))
            started = time.monotonic()
            connection = None
            failure = None
            try:
                timeout = self.timeout_s if self.deadline is None else max(5.0, min(self.timeout_s, self.deadline - self._clock() - 2.0))     # the last attempt ends before the caller's deadline
                connection = http.client.HTTPSConnection(host, port, timeout=timeout)
                connection.request("POST", path, body=encoded.encode("utf-8"),
                                   headers={"Content-Type": "application/json",
                                            "Authorization": "Bearer " + key,
                                            "X-Request-Id": request_id})
                response = connection.getresponse()
                if response.status != 200:
                    record["http_status"] = response.status
                    headers = _safe_headers(response)
                    record["response_headers"] = headers
                    raw_err = b""
                    try:
                        raw_err = response.read(4096)
                        record["error_detail"] = _error_detail(raw_err, key)       # who refused: the gateway's own error object, credential replaced, cut short
                    except Exception:  # noqa: BLE001
                        record["error_detail"] = {}
                    retry_after = parse_retry_after(headers)
                    if response.status == 429:
                        record["cost_usd"] = 0
                        record["cost_decision"] = dict(HTTP429_DECISION)
                        failed = RateLimitError("HTTP429")
                        failed.retry_after_s, failed.http_status, failed.detail = retry_after, 429, record["error_detail"]
                        raise failed
                    if response.status in RETRY_STATUS:
                        record["cost_usd"] = reserve_usd
                        record["cost_decision"] = dict(FAILED_ATTEMPT_DECISION)
                        failed = ServerBusyError("Gateway returned a retryable status")
                        failed.retry_after_s, failed.http_status, failed.detail = retry_after, response.status, record["error_detail"]
                        raise failed
                    if _is_duplicate_request_id(response.status, raw_err, record["error_detail"]):
                        record["cost_usd"] = reserve_usd
                        record["cost_decision"] = dict(FAILED_ATTEMPT_DECISION)
                        failed = DuplicateRequestIdError("Gateway returned HTTP 400 duplicate request ID")
                        failed.retry_after_s, failed.http_status, failed.detail = retry_after, 400, record["error_detail"]
                        raise failed
                    raise TransportError("Gateway returned non-200 status")
                # Bounded response size; never follow redirects or use proxy env vars.
                body = response.read(4 * 1024 * 1024 + 1)
                if len(body) > 4 * 1024 * 1024:
                    raise ResponseError("Gateway response exceeds size limit")
                try:
                    data = _strict_json(body.decode("utf-8"))
                except ValueError as exc:                 # an unreadable body (cut off, HTML, a stray constant): the gateway reported no usage, so its billing is unknown
                    record["cost_usd"] = reserve_usd
                    record["cost_decision"] = dict(FAILED_ATTEMPT_DECISION)
                    unreadable = TransientResponseError("Unreadable gateway body")
                    unreadable.retry_kind = "bad_body"
                    raise unreadable from exc
                # Account even for billed truncation, tool calls, or invalid actions.
                usage = data.get("usage") or {}
                if _money(usage.get("cost")):
                    record["cost_usd"] = usage["cost"]
                for target, source, details in (
                        ("input_tokens", "prompt_tokens", usage),
                        ("output_tokens", "completion_tokens", usage),
                        ("reasoning_tokens", "reasoning_tokens", usage.get("completion_tokens_details") or {}),
                        ("cached_tokens", "cached_tokens", usage.get("prompt_tokens_details") or {}),
                        ("cache_write_tokens", "cache_write_tokens", usage.get("prompt_tokens_details") or {})):
                    value = details.get(source)
                    if type(value) is int and value >= 0:
                        record[target] = value
                choices = data["choices"]
                if not isinstance(choices, list) or len(choices) != 1:
                    raise ResponseError("Expected one completion")
                message = choices[0]["message"]
                output = message.get("content")
                if not isinstance(output, str):
                    raise TransientResponseError("Expected text completion")
                record["output_chars"] = len(output)
                record["output_redacted"] = key in output
                record["raw_output"] = output.replace(key, "[REDACTED]")
                actual_model = data.get("model")
                if isinstance(actual_model, str):
                    record["actual_model"] = actual_model.replace(key, "[REDACTED]")
                record["provider"] = str(data.get("provider", "unknown")).replace(key, "[REDACTED]")
                if message.get("tool_calls") or message.get("function_call"):
                    raise ResponseError("Tool calls are not permitted")
                if choices[0].get("finish_reason") not in (None, "stop"):
                    raise TransientResponseError("Completion did not finish normally")
                if record["output_redacted"]:
                    raise ResponseError("Credential present in completion")
                record["status"] = "ok"
            except Exception as exc:
                is_transport = isinstance(exc, (OSError, http.client.HTTPException, TransportError))
                record["status"] = "transport_error" if is_transport else "response_error"
                # Exception text and HTTP error bodies may contain credentials.
                failure = (TransportError("Local gateway transport failed; attempt counted")
                           if is_transport else ResponseError("Invalid gateway response; attempt counted"))
                if isinstance(exc, RateLimitError):
                    failure = RateLimitError("HTTP429; attempt counted, no charge")
                elif isinstance(exc, ServerBusyError):
                    failure = ServerBusyError("HTTP %s; attempt counted, charged at its reservation" % getattr(exc, "http_status", "5xx"))
                elif isinstance(exc, DuplicateRequestIdError):
                    failure = DuplicateRequestIdError("HTTP 400 duplicate request ID; attempt counted, charged at its reservation")
                elif isinstance(exc, (OSError, http.client.HTTPException)):          # timeout, reset, DNS, a cut-off HTTP exchange: transient, billing unknown
                    failure.retry_kind = "network"
                    record["cost_usd"] = reserve_usd
                    record["cost_decision"] = dict(FAILED_ATTEMPT_DECISION)
                elif isinstance(exc, TransientResponseError):
                    failure = TransientResponseError("Unusable gateway response; attempt counted")
                    failure.retry_kind = exc.retry_kind
                if isinstance(exc, (RateLimitError, ServerBusyError, DuplicateRequestIdError)):
                    failure.retry_after_s, failure.http_status, failure.detail = exc.retry_after_s, exc.http_status, exc.detail
                if record["cost_usd"] is None:
                    record["cost_usd"] = reserve_usd
                    record["cost_decision"] = dict(FAILED_ATTEMPT_DECISION)
            finally:
                record["elapsed_s"] = time.monotonic() - started
                try:
                    self._settle(record)
                    self._append(dict(record, event="finish"))
                finally:
                    if connection is not None:
                        connection.close()
            if failure is not None:
                raise failure from None
            if self.temperature == 0 and record["cost_usd"] is not None:
                # Only explicit safe fields; never store prompts, headers, or reasoning text.
                cached = {name: record[name] for name in (
                    "cache_key", "raw_output", "actual_model", "requested_model", "provider",
                    "status", "temperature", "max_tokens", "reasoning")}
                cached["source_usage"] = {name: record[name] for name in (
                    "input_tokens", "output_tokens", "reasoning_tokens", "cached_tokens",
                    "cache_write_tokens", "cost_usd")}
                self.cache_dir.mkdir(parents=True, exist_ok=True)
                temporary = cache_path.with_suffix("." + attempt_id + ".tmp")
                with temporary.open("x", encoding="utf-8") as stream:
                    json.dump(cached, stream, ensure_ascii=True, allow_nan=False)
                    stream.flush()
                    os.fsync(stream.fileno())
                os.replace(temporary, cache_path)
            return record

    def decide(self, prompt):
        """Require an unwrapped, nonempty JSON object; environment validates fields."""
        record = self.call(prompt)
        try:
            action = _strict_json(record["raw_output"])
            if not isinstance(action, dict) or not action:
                raise ValueError()
        except (ValueError, TypeError, RecursionError):
            record["status"] = "parse_error"
            self._append(dict(record, event="parse_error"))
            raise ResponseError("Expected one strict JSON action object; attempt counted") from None
        return action
