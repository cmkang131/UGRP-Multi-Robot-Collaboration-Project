# TASK-CHEN2D-3: replies cut off at the output limit (2026-11-24)

Context: after `TASK-CHEN2D-2.md` is done. Same hard limits (this folder only, no network, fake model for tests, do not run real-model batches).

Finding (version 1, real model, `../20261124-chen2d-snap-v1/runs/v1-cmas-*`): 5 of 12 CMAS episodes ended as `failure model service` with detail `truncated`: the reply used all 8,192 completion tokens (5,300 to 6,400 of them reasoning tokens), took 50 to 65 s, and the bridge gives one HTTP attempt per call (`retry_total_s=0` in `LLM.py`). It happened at the first or second planning call of all three 4x8 `change` episodes. A single cut-off reply must not end an episode.

## D0. The event must have something to change (found in your own scripted batch: 45 of 54 e1 episodes had no box of colour A left at the event)
- e1 colour A: at map enrolment, run the reference planner to `event_step` and take A among the colours that still have at least one box after that step IN THE REFERENCE TRAJECTORY: the colour with most boxes left, ties by the seeded draw. (At `ceil(S/2)` the reference run is not finished, so such a colour exists; if a map has none at the clamped step, lower `event_step` to the largest step where one exists and record that.) D: seeded draw among squares that hold no target_A at the start and are not the square of a box_A in the reference state at the event, when such a square exists. Still a function of the initial map only; store the reference counts in `event.json`.
- e2 colour A2: among colours whose first delivery in the reference trajectory happens at step 2 or later when such a colour exists (so that the team has moved before the cancellation), seeded draw.
- Who is the told member M (replaces the random draw of C7): e1: the agent of square D (the drop-off is installed in its square, so it is the robot that is told). e2: the agent of the square where the returned box reappears (the robot whose delivery was rejected is told); this is known only when e2 fires; record it. L: seeded draw among the other agents (for e2, drawn at enrolment among all agents; if L turns out to be the same agent as the e2 member, record `leader_is_member = true` and keep it).
- Re-enrol the 12 existing maps (the map files themselves must not change; the event files get a new version field and the summary must refuse to mix results of different event-file versions). Show in the report, for each of the 12 maps, A, D, event_step, reference boxes of A left at the event, L and M.
- Scripted batch again: report how many e1 episodes have nothing to change (expected 0 with the correct script).

## D1. Retry a cut-off reply
- For a reply the client reports as truncated (and for the client's other transient kinds: rate limit, 5xx, network), let the client retry with its own rules: set the client's retry budget so that up to 3 attempts in total are made for one author call (use the client's existing parameters; read how `retry_total_s`, the retry window environment variable and the per-attempt accounting work; do not edit `link/`). Every attempt is counted in calls, tokens and cost as the client reports them.
- If all attempts are cut off: the episode ends with a new label `failure output limit` (not `failure model service`). Other exhausted transient errors keep `failure model service`.
- Record per call the number of attempts and their kinds; per episode `retried_calls`, `truncated_attempts`. Summary: columns for both, and the count of `failure output limit`.
- `--max-output-tokens N` (default stays 8192) so that the main session can test a different limit without code changes. Record it in the run folder; the summary refuses to mix runs with different values.
- The cache must stay off for retries (a retry must be a new request).

## D2. Tests
D0: A has a box left at the event in the reference trajectory for all 12 maps; M is the agent of D; the map files are byte-identical to before.
Scripted transport: first attempt truncated, second fine: the episode continues and counts 2 attempts; three truncated attempts: `failure output limit`; costs of all attempts are in the episode cost and in the invocation guard.

## D3. Report
Append a section "CHEN2D-3" to `REPORT-CHEN2D.md` (what changed, test output, anything about the client's retry rules that limits this). Last step: create the empty file `review/ASTRA-CHEN2D-3.done`.
