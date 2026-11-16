"""Counted OpenRouter requests with a persistent dollar reservation budget."""

import fcntl
import hashlib
import http.client
import json
import math
import os
from pathlib import Path
import re
import threading
import time
from decimal import Decimal
import uuid


class CallLimitError(RuntimeError):
    """A local or shared campaign budget has been exhausted."""


class TransportError(RuntimeError):
    """The request failed; it remains counted and must not be silently retried."""


class ResponseError(ValueError):
    """The gateway or action response did not satisfy the protocol."""


class RateLimitError(TransportError):
    """HTTP 429; counted, unbilled, and retryable within the episode cap."""


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
        # The key stays in a file the operator names; only its path is in the environment (a missing variable fails closed).
        key = Path(os.environ["OPENROUTER_API_KEY_FILE"]).read_text().strip()
        if not key or "\r" in key or "\n" in key:
            raise ValueError()
        return "openrouter.ai", 443, "/api/v1/chat/completions", model, key
    except Exception:
        raise RuntimeError("OpenRouter credential unavailable") from None


def key_usage():
    host, port, _, _, key = _load_route("z-ai/glm-5.3-flash")
    connection = http.client.HTTPSConnection(host, port, timeout=60)
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
HARD_EPISODE_CALLS = 300
HARD_CAMPAIGN_USD = 1.5
# Path of the approved spend-guard JSON ({"baseline_usage_usd": ..., "limit_usd": ...}), from the environment. Unset = no guard
# file = paid calls are blocked (check_spend_guard fails closed).
GUARD_FILE = os.environ.get("UGRP_SPEND_GUARD_FILE")
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
        guard = json.loads(Path(GUARD_FILE).read_text())
        baseline, limit = float(guard["baseline_usage_usd"]), float(guard["limit_usd"])
        if not math.isfinite(baseline) or not math.isfinite(limit) or limit <= 0:
            raise ValueError("Invalid spend guard")
        limit = min(limit, 2.0)
    except Exception:
        raise CallLimitError("Spend guard file missing or unreadable; paid calls blocked") from None
    usage = None
    for _ in range(3):
        try:
            usage = key_usage()["usage"]
            break
        except Exception:
            time.sleep(2)
    if usage is None:
        raise CallLimitError("Key usage unavailable; paid calls blocked by the spend guard")
    spent = usage - baseline
    if spent >= limit:
        raise CallLimitError("Project spend guard reached: %.4f of %.2f USD" % (spent, limit))
    return {"spent_usd": spent, "limit_usd": limit}


class RealLLM:
    """Counted HTTP attempts, with bounded HTTP429 retries and no implicit fallback.

    All processes in a campaign must use the same campaign_log_path (the default
    is campaign-calls.jsonl beside log_path). Its append-only, flock-protected
    reservation ledger counts attempts, including crashes and failures. Unknown
    costs and unfinished reservations block further paid calls, not cache hits.
    records contains one mutable record per call (including cache hits).
    """

    def __init__(self, max_calls, log_path, model="z-ai/glm-5.3-flash", *, timeout_s=90.0,
                 campaign_log_path=None, max_output_tokens=384, reasoning=None,
                 budget_usd=1.5, max_input_tokens=71024, campaign_max_calls=None,
                 cache_dir=None, temperature=0.0):
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

    def call(self, prompt, *, response_format=...):
        """Retry only HTTP429, with each attempt independently reserved and counted."""
        logical_call_id = uuid.uuid4().hex
        for retry in range(4):
            try:
                return self._call_once(prompt, response_format=response_format,
                                       logical_call_id=logical_call_id)
            except RateLimitError:
                if retry == 3:
                    raise
                if self.call_count >= self.max_calls:
                    raise CallLimitError("Per-instance call cap reached") from None
                time.sleep((5, 15, 30)[retry])

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
            attempt_id = uuid.uuid4().hex
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
                "attempt_id": attempt_id, "call_index": self.call_count + 1,
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
                connection = http.client.HTTPSConnection(host, port, timeout=self.timeout_s)
                connection.request("POST", path, body=encoded.encode("utf-8"),
                                   headers={"Content-Type": "application/json",
                                            "Authorization": "Bearer " + key})
                response = connection.getresponse()
                if response.status != 200:
                    record["http_status"] = response.status
                    if response.status == 429:
                        record["cost_usd"] = 0
                        record["cost_decision"] = dict(HTTP429_DECISION)
                        raise RateLimitError("HTTP429")
                    raise TransportError("Gateway returned non-200 status")
                # Bounded response size; never follow redirects or use proxy env vars.
                body = response.read(4 * 1024 * 1024 + 1)
                if len(body) > 4 * 1024 * 1024:
                    raise ResponseError("Gateway response exceeds size limit")
                data = _strict_json(body.decode("utf-8"))
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
                    raise ResponseError("Expected text completion")
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
                    raise ResponseError("Completion did not finish normally")
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
