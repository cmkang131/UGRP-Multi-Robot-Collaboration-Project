# TASK-CHEN2D-17: the matched protocol fails with the real model (2026-11-24)

Context: tasks 1 to 16 are done. Same hard limits (this folder only, no network, fake model for tests, no real-model
batches, nothing under `20261123-phase3/`). Defaults of every existing framework and option stay byte for byte;
`--protocol matched` may change (it has no results worth keeping yet).

## Evidence (read it first; it is real GLM output)
`<work>/20261124-chen2d-snap-v15/runs/v15-pilot-r1/`: matched, `--map-set scaled:1`,
4x4 and 4x8, seeds 0-1, CMAS and OWN, H=5, limit 8192, all history, state after. 1 of 8 episodes completed.
- OWN, all four episodes: almost every reply is refused as unreadable (in `4x8_OWN_static_env0` 574 of 586 calls have
  no `own_reply_form`; 28 to 32 of 32 robots are dropped in every round; three episodes end on the call ceiling after
  2 to 6 steps). The replies are sensible but in another shape, for example
  `[{"Agent[0.5, 0.5]": "move(box_green, target_green)"}, {"Agent[0.5, 0.5]": null}, ...]` or `[{}, {}, {}, {}, {}]`.
  Cause: the matched prompt gives the individual writer the sentence that describes BOTH shapes ("Use a joint object
  mapping each acting Agent[row, col] to its action string, with {} for an idle step. Use one action string or the
  JSON literal null for an individual entry."), and the repair message only says the reply "could not be read".
- CMAS: logical calls that end with attempt kinds such as `['truncated', 'truncated', 'rate_limit']` or
  `['rate_limit', 'truncated', 'truncated']` are labelled "failure model service", so output-limit failures and
  provider rate limits are mixed in one label and one attempt budget.
- `--episode-call-ceiling 900` was requested; the episodes stopped at 600.

## P1. Unambiguous format per role, tolerant reading (matched protocol; CMAS, OWN, GROUP)
- The sentence(s) that describe the output shape belong to the role-specific part: a joint writer (CMAS, GROUP) is
  told only about joint objects, an individual writer (OWN) only about its own list of action strings / null.
  Everything else stays byte-identical between the roles. Show the new prompts side by side with the differing
  sentences marked, for H=1 and H=5.
- Lenient reading accepts every reply whose meaning is unambiguous for that writer, and records the shape in the
  call record:
  individual writer: a list of action strings / null (as now); a list of objects each keyed by the writer's OWN agent
  name with an action string or null; `{}` or an object with a null value = wait; a mixture of these; one object for
  H=1. An object naming any OTHER agent is still a refusal (format repair naming that agent).
  group writer: joint objects naming only robots of its block (as now); `{}` = idle step.
  Strict mode keeps refusing everything but the requested shape.
- Repair prompts say exactly what was wrong (unknown agent named, wrong length, not a list, action not doable now and
  which actions are doable) and show the expected shape with one of the writer's own doable actions (or null).
- Offline replay (no model calls): run every saved OWN reply of the four pilot episodes through the new reader and
  report, per episode, how many replies were refused before and are accepted now, and the reasons for the rest.
  Put the replay script and its output under `review/chen2d-17/`.

## P2. Clean end labels and attempt budgets
- A provider rate limit, timeout or 5xx must not use up one of the three attempts reserved for cut-off or unusable
  replies, and must not turn an output-limit failure into "model service". Give transport errors their own bounded
  retry (state the bound and the wait rule), record both counts per logical call, and label the call
  "output limit" when every reply-bearing attempt was cut off, "model service" only when no usable transport was
  obtained within the transport bound. If this needs a change outside this folder, do not make it: describe it.
- Say where the 600-call stop comes from. When the requested `--episode-call-ceiling` exceeds a hard cap the runner
  must say so at start, record the effective ceiling, and give the "episode call ceiling" label only for it.
- Report calls per planning round for 16 and 32 robots under CMAS, GROUP (G=4, 8) and OWN with no repairs and with
  every writer using all its repairs, so the main session can choose a ceiling.

## P3. Tests and report
Fake-model tests for every bullet (including the exact pilot reply shapes above as fixtures); all earlier tests pass;
legacy byte replays unchanged. Append "CHEN2D-17" to `REPORT-CHEN2D.md` with the replay table, the side-by-side
prompts, what changed, commands, test results and "확인 안 됨". Last step: create `review/ASTRA-CHEN2D-17.done`.
