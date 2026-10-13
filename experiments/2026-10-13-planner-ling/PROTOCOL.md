# Ling-3.0-Flash-VL adoption check

User selected inclusionai/ling-3.0-flash-vl at Novita; canceled model comparisons
made zero inference calls. New bundles v401 (prompt order off) and v402
(static_first_v1) derive from v387, with code_v1 body and event_v1 calls.
Old Gemma bundle configs and stored records are unchanged. Gemma remains the
legacy selection. No VM submission or physical execution.

Common controls: temperature 0, max_tokens 768, reasoning.enabled=false,
provider order [Novita], allow_fallbacks=false. Novita does not advertise
structured_outputs; retain the existing JSON-body parser, no response_format.
Actual model/provider and cached_tokens are recorded per response; dated
endpoint metadata is not an attestation of immutable served weights.
Own RGB uses the existing image_url path, verified against image_refs SHA-256.

The 400 image-free initial requests are exactly the saved r4 DEV 200 worlds ×
no_comm/peer_en. Ordered-request and gold hashes, and same-input rule choices
are checked before calls. This is tuning evidence, not confirmation.
Historical Gemma r4 DEV is a reference, not a new comparison run.

Hard limits BEFORE HTTP: 440 calls total, $0.08 combined, zero HTTP retries.
A durable relay attempt counter includes failures and survives restart.
No planner reasks in this finite check: 400 cases plus cache/image probes
consume the call allowance. Failures, fallback and uncalled cases stay in N.
Stop submitting immediately if cumulative format errors exceed 5% or response
latency median exceeds 8 seconds. Key remaining balance is checked initially
and every 50 calls; projected remaining must be at least $1.5. Keychain only,
process memory only; no credentials in arguments, files or logs.

static_first_v1 only changes top-level insertion order, never values:
schema, robot_id, condition, task, order_sheet, static_map, public_rules,
can_send_to; then now_s, own, own_act_results, received_messages, events,
candidates; remaining evidence fields follow in deterministic order.
The system message remains first, image blocks last. Off preserves old bytes.

Requested 400 + 40 cache + 5 image calls totals 445, conflicting with the 440
cap. Clarification pending: reduce cache sample to 35, or raise cap to 445.
The 400 main calls can proceed independently; neither extra allowance nor a
reduced cache sample is assumed authorized. Main-only mode records probes as
pending. Continuation must import the previous paid ledger and counter; it
cannot replay the 400 main calls.

The image is r80 v379/s61006/r1 frame 00000, 13,858 bytes, SHA-256
15673f61873991c84cfe449747efa858b4986e36d8f48c5874f483574ec0cfc3.
One existing file was read from the ARM archive (not the active simulation
VM); its hash exactly matches r80 call-0001-r1 image_refs. Local source:
outputs/task-planner-ling-vl-image/r80-r1-00000.jpg. Five probes pair with the
first five frozen text requests; record errors and prompt-token increase.
Image metadata adds some text tokens, so the increase is not a pure image
encoder token count. No image-based task success is claimed.

## References

- [OpenRouter reasoning](https://openrouter.ai/docs/guides/best-practices/reasoning-tokens): enabled=false; neither selected catalog model requires reasoning.
- [Provider routing](https://openrouter.ai/docs/guides/routing/provider-selection): explicit provider and disabled fallbacks.
- [Ling VL endpoints](https://openrouter.ai/api/v1/models/inclusionai/ling-3.0-flash-vl/endpoints): Novita input $0.021/M, output $0.0616/M, cached input $0.0042/M; snapshot saved here.
- [Catalog](https://openrouter.ai/api/v1/models): text/image/video supported; no structured_outputs at selected Novita endpoint. Cached-token reporting is measured, not assumed from advertising.
