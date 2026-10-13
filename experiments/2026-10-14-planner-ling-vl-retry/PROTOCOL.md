# Ling VL 429 diagnosis and bounded retry check

Previous a17f8fb1 run was stopped by the coordinator. Its 137 HTTP attempts
are preserved separately and excluded from this new run. This run permits
at most 600 HTTP attempts TOTAL, including 1–3 diagnostic attempts, retries,
400 fixed r4 DEV decisions, 5 image probes and 40 static-first decisions.
USD limit is $0.08; all paid attempt costs are summed in the upstream ledger.
Missing costs retain conservative reservations and are reported as unknown.
Startup and every 50 upstream attempts check projected key balance >=$1.5.

The opt-in `ling_rate_limit_v1` policy is restricted to Ling VL/Novita.
Gemma's existing fixed-delay policy and default options remain unchanged.
The relay serializes provider traffic (one active request) and spaces starts
by at least 2 s (30/min, a conservative configured rate, not a claimed provider
quota). 429 and all 5xx get at most two retries, using Retry-After seconds or
HTTP date first, otherwise exponential full jitter (base 2 s, cap 20 s).
No alternate provider or model is allowed. Pacing/retry waits, every response
status, sanitized error body and an allowlist of rate-limit response headers
are durably recorded. Client requests have a 30 s deadline; the relay stops
admitting retries before it, rather than sending late requests after fallback.

The actual HTTP attempt counter and cost ledger persist across process
restart. Diagnostic probes and main check use the SAME new upstream directory;
previous 137 attempts use a different immutable directory. The checker stops
submitting immediately if format errors >5%, fallback after transport retries
>5%, or end-to-end response latency median >8 s. Uncalled and failed decisions
remain in original denominators; main scores cannot be presented as completed
if the stop condition fires. No format reasks are used in this check.

Dataset/request/candidate content is unchanged from r4 DEV. Cached ratio is
sum(cached_tokens)/sum(prompt_tokens), with missing reporting marked unknown.
Image probes use r80's previously verified own RGB. No VM submission.

## References checked 2026-10-14

- [OpenRouter limits](https://openrouter.ai/docs/api_reference/limits): distinguishes platform vs upstream 429; platform rate headers and provider error metadata are diagnostic evidence. Paid variants do not have the documented free-model RPM cap. Actual provider quota requires response evidence.
- [OpenRouter errors](https://openrouter.ai/docs/api_reference/errors-and-debugging): standard error envelope, provider_code, and Retry-After handling; preserve response body as well as status.
- [AWS exponential backoff and jitter](https://aws.amazon.com/blogs/architecture/exponential-backoff-and-jitter/): full jitter spreads retries instead of synchronizing bursts (verification below before final report).

A numeric quota is reported only if returned by the provider/platform. The
configured 30/min client limit and observed throughput are separate quantities.
For 16 E2E runs × 2 robots, use r80 archived decision timestamps to estimate
calls/SIM-second, and explicitly convert to wall seconds using the assumed
wall/SIM factor; no live concurrency test is authorized.
