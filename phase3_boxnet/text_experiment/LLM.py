"""Chen's model entry point, exact message traces, and the read-only RealLLM bridge."""
import os
import sys
from contextvars import ContextVar
from decimal import Decimal
from functools import partial, wraps
from pathlib import Path
from tempfile import TemporaryDirectory
from threading import Lock
from time import monotonic
from uuid import uuid4

import fake_model
from limits import CALL_CEILING, CLIENT_LIMIT, MODEL_SERVICE, OUTPUT_LIMIT, TOKEN_LIMIT, UNUSABLE_REPLY, StopEpisode
from storage import read_json, write_json

BRAIN = Path(os.environ.get("BOXNET_BRAIN_DIR", Path(__file__).resolve().parents[1] / "planner_client")).resolve()
MODEL = "z-ai/glm-5.3-flash"
QWEN = "qwen/qwen3-235b-a22b-2507"
SMALL_QWEN = "qwen/qwen3.5-9b"
REASONING_SETTINGS = ("default", "off")
MAX_OUTPUT_TOKENS = 8192
MAX_REPLY_ATTEMPTS = 3
# Kept as the legacy constructor default; matched records name the reply budget
# explicitly so it cannot be confused with transport retries.
MAX_ATTEMPTS = MAX_REPLY_ATTEMPTS
# Matched protocol retry budgets are deliberately disjoint.  A reply-bearing
# attempt is one that reached the provider enough to be cut off or judged
# unreadable; a 429/timeout/5xx is transport only.  The two matched-format
# repairs are separate logical calls, not part of either budget here.
MAX_TRANSPORT_ATTEMPTS = 3
TRANSPORT_RETRY_TOTAL_S = 60.0
_TRANSPORT_KINDS = frozenset(("rate_limit", "http_5xx", "network", "duplicate_request_id"))
_session = ContextVar("chen_model_session")
_finish_capture = ContextVar("chen_provider_finish", default=None)
_decoder_lock = Lock()
_LENGTH_REASONS = {"length", "max_tokens", "max_output_tokens"}


def is_transport_attempt(attempt):
    """Whether a metered attempt never supplied a reply-bearing completion."""
    status = attempt.get("http_status")
    return (attempt.get("transport_error", False) or (status is not None and status != 200)
            or attempt.get("kind") in _TRANSPORT_KINDS)


def was_truncated(attempt):
    """Include salvaged provider length finishes in reports using historical client kinds."""
    return attempt["kind"] == "truncated" or attempt.get("cut_answer_salvaged") is True


def capture_provider_finish(api):
    """Older clients discard the choice's finish fields after decoding the provider body.

    Measure visible content at that decode, before validation or credential redaction.
    A context variable keeps simultaneous attempts separate. Native retries, redaction,
    validation and both spending ledgers remain on the ordinary client path.
    """
    with _decoder_lock:
        decode = getattr(api, "_strict_json", None)
        if decode is None or getattr(decode, "_chen_finish_observer", False):
            return

        @wraps(decode)
        def observe(*args, **kwargs):
            value = decode(*args, **kwargs)
            target = _finish_capture.get()
            if target is not None and isinstance(value, dict):
                choices = value.get("choices")
                if isinstance(choices, list) and len(choices) == 1 and isinstance(choices[0], dict):
                    message = choices[0].get("message")
                    content = message.get("content") if isinstance(message, dict) else None
                    if content is None or isinstance(content, str):
                        visible = content or ""
                        target.update(visible_reply_chars=len(visible), nonblank=bool(visible.strip()))
                    for key in ("finish_reason", "native_finish_reason"):
                        reason = choices[0].get(key)
                        if isinstance(reason, str):
                            target[key] = reason
            return value

        observe._chen_finish_observer = True
        api._strict_json = observe


def visible_reply_fields(raw, cut_off):
    chars = len(raw) if isinstance(raw, str) else None
    kind = None
    if cut_off is True:
        kind = "unknown" if chars is None else "partial" if raw.strip() else "empty"
    return dict(visible_reply_chars=chars, cutoff_reply_class=kind)


def finish_fields(entry, observed):
    reasons = {k: entry.get(k) or observed.get(k) for k in ("finish_reason", "native_finish_reason")}
    raw = entry.get("cut_off")
    known = [v.lower() for v in reasons.values() if isinstance(v, str) and v]
    cut = True if any(r in _LENGTH_REASONS for r in known) else (
        raw if isinstance(raw, bool) else False if known else None)
    visible = visible_reply_fields(entry.get("raw_output"), cut)
    if "visible_reply_chars" in observed:
        visible["visible_reply_chars"] = observed["visible_reply_chars"]
        if cut is True:
            visible["cutoff_reply_class"] = "partial" if observed["nonblank"] else "empty"
    elif type(entry.get("output_chars")) is int:
        visible["visible_reply_chars"] = entry["output_chars"]
        if cut is True and entry["output_chars"] == 0:
            visible["cutoff_reply_class"] = "empty"
    elif cut is not True and visible["visible_reply_chars"] is None:
        # No visible reply reached the writer (e.g. transport failure or unreadable body).
        visible["visible_reply_chars"] = 0
    return dict(**reasons, cut_off=cut, **visible)


def validate_reasoning(model, setting):
    if setting not in REASONING_SETTINGS:
        raise ValueError(f"Unknown reasoning setting: {setting}")
    if setting == "off" and model == MODEL:
        raise ValueError(f"--reasoning off is unavailable for {model}: this model requires reasoning")
    if setting == "off" and model == QWEN:
        raise ValueError(f"--reasoning off is unavailable for {model}: its profile has no reasoning parameter")
    return setting


def load_real_api():
    # Even an invocation without -B must never create __pycache__ in the source tree.
    sys.dont_write_bytecode = True
    sys.path.insert(0, str(BRAIN))
    try:
        import llm
        if Path(llm.__file__).resolve() != (BRAIN / "llm.py").resolve():
            raise ImportError("Unexpected RealLLM import path")
        return llm
    finally:
        sys.path.remove(str(BRAIN))


def wire_prompt(messages):
    # RealLLM accepts one string. Keep every turn's content, order and whitespace.
    return "\n\n".join(f'[{m["role"]}]\n{m["content"]}' for m in messages)


def usage_from_record(record, kind, invocation, *, include_transport_status=False):
    reported = None if record.get("cost_decision") else record.get("cost_usd")
    usage = dict(kind=kind, invocation=invocation, temperature=record["temperature"],
                api_calls=int(not record.get("cache_hit", False)),
                prompt_tokens=record.get("input_tokens"), completion_tokens=record.get("output_tokens"),
                reasoning_tokens=record.get("reasoning_tokens"), cost_usd=reported,
                guard_cost_usd=record.get("cost_usd"), cost_decision=record.get("cost_decision"),
                attempt_id=record.get("attempt_id"), actual_model=record.get("actual_model"), provider=record.get("provider"),
                logical_call_id=record.get("logical_call_id"), raw_output=record.get("raw_output"),
                cache_hit=record.get("cache_hit", False))
    if include_transport_status:
        usage["transport_error"] = record.get("status") == "transport_error"
        usage["http_status"] = record.get("http_status")
    return usage


def call_usage(attempts, *, partition_retries=False):
    usage = dict(attempt_count=len(attempts), attempt_kinds=[a["kind"] for a in attempts],
                 api_calls=sum(a["api_calls"] for a in attempts),
                 cache_hit=any(a["cache_hit"] for a in attempts))
    if partition_retries:
        transport = [a for a in attempts if is_transport_attempt(a)]
        usage.update(reply_attempt_count=len(attempts) - len(transport),
                     transport_attempt_count=len(transport),
                     reply_attempt_limit=MAX_REPLY_ATTEMPTS,
                     transport_attempt_limit=MAX_TRANSPORT_ATTEMPTS)
    for field in ("prompt_tokens", "completion_tokens", "reasoning_tokens"):
        values = [a[field] for a in attempts]
        known = sum(v for v in values if v is not None)
        usage["known_" + field] = known
        usage[field] = None if None in values else known
    for field in ("cost_usd", "guard_cost_usd"):
        values = [a[field] for a in attempts]
        known = sum((Decimal(str(v)) for v in values if v is not None), Decimal(0))
        usage[field] = None if None in values else float(known)
        if field == "cost_usd":
            usage["known_reported_cost_usd"] = float(known)
    return usage


def keep_cut_prefix(record, reader):
    """Decide at the physical retry boundary, using the client's recorded visible output."""
    attempt = record["attempts"][-1]
    raw = attempt.get("raw_output")
    if (reader is None or attempt.get("cut_off") is not True or is_transport_attempt(attempt)
            or not isinstance(raw, str) or not raw.strip()):
        return False
    prefix = reader(raw)
    if prefix is None:
        return False
    response, count = prefix
    attempt.update(cut_answer_salvaged=True, salvaged_steps=count, cutoff_reply_class="partial")
    record.update(response=response, cut_answer_salvaged=True, salvaged_steps=count,
                  response_from_attempt=len(record["attempts"]))
    return True


class CallSession:
    def __init__(self, directory, budget, model, script, ceiling, max_output_tokens=MAX_OUTPUT_TOKENS,
                 temperature=0.0, retry_temperature=None, *, reasoning_setting="default",
                 max_attempts=MAX_ATTEMPTS, trace_finish=False, partition_retries=False, plan_note="none"):
        # An unversioned standalone replay uses the original scripted trace format.
        self.reasoning_setting = reasoning_setting
        setting = validate_reasoning(model, "default" if reasoning_setting is None else reasoning_setting)
        self.directory = directory / "calls"
        self.directory.mkdir(exist_ok=True)
        self.budget, self.model, self.script = budget, model, script
        self.records = []
        for number, path in enumerate(sorted(self.directory.glob("[0-9]*.json")), 1):
            record = read_json(path)
            if record["number"] != number or record["status"] == "pending":
                raise ValueError(f"Unresolved call trace at {path}. Inspect it before resuming.")
            if (record["model"], record.get("reasoning_setting", "default")) != (model, setting):
                raise ValueError(f"Saved model or reasoning setting changed: {path}")
            self.records.append(record)
        self.cursor = self.api_calls = self.step = self.round = 0
        self.planning_round = None
        self.speaker = self.role = None
        self.told = False
        self.ceiling = ceiling
        self.max_attempts = max_attempts
        self.physical_attempt_limit = max_attempts + (MAX_TRANSPORT_ATTEMPTS - 1 if partition_retries else 0)
        self.trace_finish = trace_finish
        self.plan_note = plan_note
        self.partition_retries = partition_retries
        self.max_output_tokens = max_output_tokens
        self.temperature = temperature
        self.retry_temperature = temperature if retry_temperature is None else retry_temperature
        self.client = None
        if model != "fake":
            self.api = load_real_api()
            if trace_finish:
                capture_provider_finish(self.api)
            self.ceiling = min(ceiling, self.api.HARD_EPISODE_CALLS)

            class EpisodeClient(self.api.RealLLM):
                # Native call() owns retry decisions and sleeps. Meter each physical attempt at its boundary.
                def _call_once(client, prompt, **options):
                    return client.account_attempt(super()._call_once, prompt, **options)

            # RealLLM selects reasoning and provider price ceilings from the requested model's profile.
            self.client = EpisodeClient(
                min(self.max_attempts, self.ceiling), directory / "client-calls.jsonl", model=model,
                reasoning={"enabled": False} if setting == "off" else None,
                campaign_log_path=directory / "campaign-calls.jsonl",
                budget_usd=self.api.HARD_CAMPAIGN_USD, temperature=temperature,
                max_output_tokens=max_output_tokens, retry_total_s=0 if max_attempts == 1 else self.api.RETRY_TOTAL_S,
                cache_dir=directory / "cache")

    def __enter__(self):
        self.binding = _session.set(self)
        return self

    def __exit__(self, *_):
        _session.reset(self.binding)

    def call(self, messages, *, scope=None, prefix_reader=None):
        if self.api_calls >= self.ceiling:
            raise StopEpisode(CALL_CEILING)
        if self.cursor < len(self.records):
            record = self.records[self.cursor]
            if (record["messages"], record["step"], record["round"], record["speaker"], record["role"], record["told"]) != (
                    messages, self.step, self.round, self.speaker, self.role, self.told) or (
                    record.get("planning_round") != self.planning_round):
                raise ValueError("Saved call differs from the resumed protocol")
            if scope is not None and any(record.get(k) != v for k, v in scope.items()):
                raise ValueError("Saved group writer assignment differs on resume")
            if record.get("plan_note", "none") != self.plan_note:
                raise ValueError("Saved plan note differs on resume")
            if (record.get("cut_answer") == "prefix") != (prefix_reader is not None):
                raise ValueError("Saved cut-answer setting differs on resume")
            if record["status"] == "interrupted":
                record = self.new_call(messages, record, scope=scope, prefix_reader=prefix_reader)
        else:
            record = self.new_call(messages, scope=scope, prefix_reader=prefix_reader)
            self.records.append(record)
        self.cursor += 1
        self.api_calls += record["api_calls"]
        if record.get("failure"):
            raise StopEpisode(record["failure"], record["detail"], interrupted=record["status"] == "interrupted")
        if self.api_calls >= self.ceiling and self.role != "relay" and not self.trace_finish:
            raise StopEpisode(CALL_CEILING)
        prompt, completion = record["prompt_tokens"], record["completion_tokens"]
        tokens = prompt + completion if prompt is not None and completion is not None else None
        return record["response"], tokens

    def mark_rescue(self):
        # A reply can pass through both the extraction site and the checker.
        record = self.records[self.cursor - 1]
        if not record["lenient_rescue"]:
            record["lenient_rescue"] = True
            write_json(self.directory / f"{record['number']:05d}.json", record)

    def record_own_reply(self, parsed):
        if parsed is None:
            return
        record = self.records[self.cursor - 1]
        fields = dict(own_reply_form=parsed.form, own_reply_padded=parsed.padded,
                      own_reply_cut=parsed.cut, own_reply_invalid_position=parsed.invalid_position,
                      lenient_rescue=parsed.rescued)
        if any(record.get(key) != value for key, value in fields.items()):
            record.update(fields)
            write_json(self.directory / f"{record['number']:05d}.json", record)

    def record_reply_shape(self, shape):
        """Persist matched-reader provenance without changing legacy records."""
        record = self.records[self.cursor - 1]
        fields = dict(reply_shape=shape.form, reply_shape_accepted=shape.accepted,
                      reply_refusal_reason=shape.reason, reply_refusal_detail=shape.detail)
        if any(record.get(key) != value for key, value in fields.items()):
            record.update(fields)
            write_json(self.directory / f"{record['number']:05d}.json", record)

    def new_call(self, messages, record=None, *, scope=None, prefix_reader=None):
        number = self.cursor + 1
        path = self.directory / f"{number:05d}.json"
        key = str(path.relative_to(self.budget.out))
        if record is None:
            record = dict(number=number, step=self.step, round=self.round, speaker=self.speaker,
                          role=self.role, told=self.told, lenient_rescue=False, attempts=[],
                          invocation=self.budget.path.stem, model=self.model, messages=messages,
                          response=None, usage_source="api" if self.client is not None else "scripted")
            if scope is not None:
                record.update(scope)
            if self.trace_finish:
                record["plan_note"] = self.plan_note
            if prefix_reader is not None:
                record["cut_answer"] = "prefix"
            if self.reasoning_setting is not None:
                record["reasoning_setting"] = self.reasoning_setting
            if self.planning_round is not None:
                record["planning_round"] = self.planning_round
            if self.role == "own":
                record.update(own_reply_form=None, own_reply_padded=False, own_reply_cut=False,
                              own_reply_invalid_position=None)
        record.update(status="pending", failure=None, detail="")
        started = monotonic()
        write_json(path, record)
        try:
            if self.client is None:
                self.fake_call(messages, record, key, prefix_reader)
            else:
                self.real_call(wire_prompt(messages), record, key, prefix_reader)
            record["status"] = "ok"
        except StopEpisode as stop:
            record.update(failure=stop.label, detail=stop.detail, status="interrupted" if stop.interrupted else "error")
            if not record["attempts"] and (stop.interrupted or stop.label == CLIENT_LIMIT):
                record.update(call_usage([], partition_retries=self.partition_retries), status="refused")
                write_json(path, record)
                path.replace(self.directory / f"refused-{self.budget.path.stem}-{number}.json")
                raise
        except BaseException:
            # Keep uncertain attempts identifiable even if their settlement already reached disk.
            with self.budget.transaction() as state:
                state.update(stop_label=CLIENT_LIMIT, stop_detail=f"Unresolved attempt: {key}")
            raise
        record.update(call_usage(record["attempts"], partition_retries=self.partition_retries))
        record["elapsed_seconds"] = record.get("elapsed_seconds", 0) + (monotonic() - started)
        write_json(path, record)
        return record

    def fake_call(self, messages, record, key, prefix_reader):
        attempts = record["attempts"]
        cost = fake_model.COST
        while self.api_calls + len(attempts) < self.ceiling:
            self.budget.reserve(key, cost)
            reply = fake_model.reply(messages, self.script)
            cut = isinstance(reply, fake_model.CutReply)
            retry = attempts and attempts[-1].get("cut_off") is True
            attempt = dict(kind="truncated" if cut else "ok", invocation=self.budget.path.stem, api_calls=1,
                           temperature=self.retry_temperature if retry else self.temperature,
                           prompt_tokens=11, completion_tokens=7, reasoning_tokens=0 if self.reasoning_setting == "off" else 2,
                           cost_usd=float(cost), guard_cost_usd=float(cost), cache_hit=False)
            if self.reasoning_setting is not None:
                attempt["provider"] = None
            if self.trace_finish:
                attempt.update(finish_reason="length" if cut else "stop", native_finish_reason=None, cut_off=cut,
                               raw_output=reply, **visible_reply_fields(reply, cut))
            attempts.append(attempt)
            self.budget.settle(key, 1, cost, cost)
            if not cut:
                record["response"] = reply
                return
            if keep_cut_prefix(record, prefix_reader):
                return
            if len(attempts) >= self.max_attempts:
                raise StopEpisode(OUTPUT_LIMIT, "truncated")
        raise StopEpisode(CALL_CEILING)

    def account_attempt(self, attempts, key, reserve, send, wire, **options):
        if self.trace_finish and len(attempts) >= self.physical_attempt_limit:
            raise self.api.CallLimitError("Per-instance call cap reached")
        key = f"{key}#{len(attempts) + 1}"
        self.budget.reserve(key, reserve)
        before = len(self.client.records)
        kind = "ok"
        observed = {}
        binding = _finish_capture.set(observed) if self.trace_finish else None
        try:
            with TemporaryDirectory(dir=self.directory, prefix=".response-cache-") as cache:
                self.client.cache_dir = Path(cache)
                if self.partition_retries:
                    prior_reply = next((a for a in reversed(attempts)
                                        if not is_transport_attempt(a)), None)
                    retrying_cutoff = prior_reply is not None and prior_reply.get("cut_off") is True
                else:
                    retrying_cutoff = attempts and attempts[-1]["kind"] == "truncated"
                self.client.temperature = self.retry_temperature if retrying_cutoff else self.temperature
                return send(wire, **options)
        except Exception as exc:
            if len(self.client.records) == before:
                if isinstance(exc, self.api.InfraError):
                    raise StopEpisode(MODEL_SERVICE, exc.kind, interrupted=True) from None
                if (isinstance(exc, (OSError, RuntimeError, ValueError)) and not isinstance(exc, self.api.CallLimitError)
                        and str(exc) != "Conservative input token cap exceeded"):
                    raise StopEpisode(MODEL_SERVICE, type(exc).__name__, interrupted=True) from None
            kind = getattr(exc, "retry_kind", type(exc).__name__)
            raise
        finally:
            if binding is not None:
                _finish_capture.reset(binding)
            entries = self.client.records[before:]
            if entries:
                entry, = entries
                attempt = usage_from_record(entry, kind, self.budget.path.stem,
                                            include_transport_status=self.partition_retries)
                if self.trace_finish:
                    attempt.update(finish_fields(entry, observed))
                if attempt["cache_hit"] or entry["status"] == "started":
                    raise RuntimeError("Unexpected cache hit or unresolved client attempt")
                attempts.append(attempt)
                charge = attempt["guard_cost_usd"]
                self.budget.settle(key, 1, Decimal(str(attempt["cost_usd"] or 0)),
                                   None if charge is None else Decimal(str(charge)))
            else:
                # The episode ledger or the client preflight refused before transport.
                self.budget.settle(key, 0, Decimal(0), Decimal(0))

    @staticmethod
    def _matched_label(attempts):
        reply_attempts = [a for a in attempts if not is_transport_attempt(a)]
        if reply_attempts and all(a.get("cut_off") is True for a in reply_attempts):
            return OUTPUT_LIMIT
        if not reply_attempts:
            return MODEL_SERVICE
        return UNUSABLE_REPLY

    def matched_real_call(self, wire, result, prefix_reader=None):
        """Matched-only retry loop around the already-metered physical transport.

        This does not depend on an upstream private retry-loop method: archived
        RealLLM revisions put that loop in different places.  The underlying
        `_call_once` still owns request IDs, reservations, settlements, cache
        suppression and provider decoding; this loop only partitions retries.
        """
        attempts = result["attempts"]
        previous = attempts[0].get("logical_call_id") if attempts else None
        logical_call_id = previous or uuid4().hex
        transport_waited = result.get("transport_retry_waited_seconds", 0.0)
        reply_waited = result.get("reply_retry_waited_seconds", 0.0)
        while True:
            before = len(attempts)
            try:
                reply = self.client._call_once(wire, response_format=None, logical_call_id=logical_call_id)
                if prefix_reader is not None and attempts[-1].get("cut_off") is True:
                    # Some clients return normally when only native_finish_reason says length.
                    raise self.api.ResponseError("Provider output limit")
                result.update(response=reply["raw_output"], attempt_id=reply["attempt_id"],
                              actual_model=reply.get("actual_model"))
                return
            except StopEpisode as stop:
                if stop.label == MODEL_SERVICE and attempts:
                    raise StopEpisode(self._matched_label(attempts), stop.detail, stop.interrupted) from None
                raise
            except self.api.CallLimitError:
                raise
            except Exception as error:  # noqa: BLE001
                if len(attempts) == before:
                    raise
                # The durable metered entry is more reliable than exception
                # attributes across archived RealLLM client revisions.
                attempt = attempts[-1]
                if keep_cut_prefix(result, prefix_reader):
                    result.update(attempt_id=attempt["attempt_id"], actual_model=attempt.get("actual_model"))
                    return
                kind = attempt["kind"]
                transport = is_transport_attempt(attempt)
                # Permanent HTTP transport failures can have a generic kind in
                # archived clients; use the recorded transport boundary.
                transport_attempts = sum(is_transport_attempt(a) for a in attempts)
                reply_attempts = len(attempts) - transport_attempts
                exhausted = (transport_attempts >= MAX_TRANSPORT_ATTEMPTS if transport
                             else reply_attempts >= self.max_attempts)
                if exhausted:
                    raise StopEpisode(self._matched_label(attempts), kind) from None
                retry_kind = getattr(error, "retry_kind", None)
                if transport and retry_kind is None:
                    # A permanent HTTP transport refusal (such as 401) did
                    # reach the service but is not retryable.
                    raise StopEpisode(self._matched_label(attempts), kind) from None
                if self.client.max_calls is not None and self.client.call_count >= self.client.max_calls:
                    raise self.api.CallLimitError("Per-instance call cap reached") from None
                waited = transport_waited if transport else reply_waited
                limit = TRANSPORT_RETRY_TOTAL_S if transport else self.client.retry_total_s
                room = limit - waited
                if self.client.deadline is not None:
                    room = min(room, self.client.deadline - self.client._clock() - self.client.timeout_s - 2.0)
                requested = getattr(error, "retry_after_s", None)
                # Never shorten a provider Retry-After: if it cannot fit in
                # this bounded logical wait window, return the terminal label.
                if room <= 0 or (requested is not None and requested > room):
                    raise StopEpisode(self._matched_label(attempts), kind) from None
                retry_index = transport_attempts - 1 if transport else reply_attempts - 1
                # Some archived clients expose an unusable 200 reply as a
                # plain ResponseError.  It is a reply-bearing failure, so give
                # it the same bounded short retry class as a bad body.
                wait = (self.client._retry_wait(error, retry_index) if retry_kind is not None else 1.0)
                wait = min(max(wait, requested or 0), room)
                self.client._append({"event": "retry", "logical_call_id": logical_call_id,
                                     "attempt": len(attempts), "kind": kind,
                                     "retry_scope": "transport" if transport else "reply",
                                     "http_status": getattr(error, "http_status", None),
                                     "wait_s": round(wait, 3), "retry_after_s": requested,
                                     "waited_s": round(waited, 3), "at": self.api.time.time()})
                self.client._sleep(wait)
                if transport:
                    transport_waited += wait
                    result["transport_retry_waited_seconds"] = transport_waited
                else:
                    reply_waited += wait
                    result["reply_retry_waited_seconds"] = reply_waited

    def real_call(self, wire, result, key, prefix_reader=None):
        attempts = result["attempts"]
        # max_calls is cumulative for a client instance. Prefix attempts already settled on resume
        # occupy slots in this author call as well as in its episode.
        remaining = min(self.physical_attempt_limit, self.ceiling - self.api_calls) - len(attempts)
        self.client.max_calls = self.client.call_count + remaining
        price = self.client.max_price
        reserve = (Decimal(len(wire.encode("utf-8")) + 1024) * Decimal(str(price["prompt"])) +
                   self.max_output_tokens * Decimal(str(price["completion"]))) / 1_000_000
        self.client.account_attempt = partial(self.account_attempt, attempts, key, reserve)
        try:
            if self.partition_retries:
                return self.matched_real_call(wire, result, prefix_reader)
            reply = self.client.call(wire, response_format=None)
            result.update(response=reply["raw_output"], attempt_id=reply["attempt_id"],
                          actual_model=reply.get("actual_model"))
            return
        except self.api.CallLimitError as exc:
            if str(exc) != "Per-instance call cap reached":
                raise StopEpisode(CLIENT_LIMIT, str(exc), interrupted=str(exc) != "Campaign dollar budget exhausted") from None
            if self.partition_retries:
                if self.api_calls + len(attempts) >= self.ceiling:
                    raise StopEpisode(CALL_CEILING, str(exc)) from None
                raise StopEpisode(CLIENT_LIMIT, str(exc)) from None
            if len(attempts) < self.max_attempts:
                raise StopEpisode(CALL_CEILING, str(exc)) from None
            detail = attempts[-1]["kind"]
        except self.api.InfraError as exc:
            detail = exc.kind
        except (self.api.TransportError, ValueError) as exc:
            if str(exc) == "Conservative input token cap exceeded":
                raise StopEpisode(TOKEN_LIMIT, "RealLLM conservative input bound") from None
            raise StopEpisode(MODEL_SERVICE, type(exc).__name__, interrupted=not attempts) from None
        if self.trace_finish:
            length_stop = bool(attempts) and all(a.get("cut_off") is True for a in attempts)
        else:
            length_stop = detail == "truncated" and attempts and all(a["kind"] == detail for a in attempts)
        label = OUTPUT_LIMIT if length_stop else MODEL_SERVICE
        raise StopEpisode(label, detail)


def GPT_response(messages, model_name):
    session = _session.get()
    if session.model != model_name:
        raise ValueError("Model does not match the episode")
    return session.call(messages)
