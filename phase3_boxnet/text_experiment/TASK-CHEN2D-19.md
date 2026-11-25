# TASK-CHEN2D-19: tell the writer that planning continues after the horizon; classify cut-offs; equal failure rule (2026-11-25)

Context: tasks 1 to 18 are done (251 tests). Same hard limits (this folder only, no network, fake model for tests, no
real-model batches). Defaults of every existing framework, option and registered map stay byte for byte: everything
below is OPT-IN.

Why. Real-model pilots on the new boards with two boxes per robot (`../20261124-chen2d-snap-v18/runs/v18-pilot-r2`
at limit 8,192: 6 of 18 episodes completed, 12 ended on the output limit, 10 of them at the first plan;
`runs/v18-pilot-r2-16k` at 16,384: 9 of 18 completed, 8 output limit, 1 syntactic) show replies cut with an EMPTY
visible answer: hidden reasoning fills the limit, in all three structures. An independent review
(`../20261123-plan3/review-neon/REPORT-NEON-6.md`, sections 0.1 and 1.2) found the likely cause in the reply text:
`"No valid 5-step plan exists; Agent[0.5, 1.5] needs 6 actions."`
(`../20261124-chen2d-snap-v18/runs/v18-pilot-r2-16k/episodes/1x3_GROUP-g3_static_env0/calls/00001.json`), and
"Need all matched within 5 steps" in other calls. The matched prompt says "Match all boxes to their color-coded
targets ... Return a JSON list for the next 5 steps" and never says that the job may take longer than the horizon and
that another planning round follows. With two boxes per robot most boards need 6 to 15 steps, so the model searches
for a complete 5-step solution that does not exist. The main session checked the prompt text and found such wording
in 5 of 428 saved calls; reasoning text of cut-off attempts is not stored, so this is a plausible cause, not a proven
one. This task makes it testable.

## P1. `--plan-note continue` (default `none` = today's prompt, byte for byte)
With `continue`, the matched prompt of EVERY writer (CMAS, GROUP, OWN; the same sentence, same place) gets one more
sentence directly after the sentence that asks for the next H steps:
"The job may need more than {H} steps: plan only the next {H} steps; after they are executed, another planning round
continues from the new state."
(H = the horizon in use; at H = 1 use the singular wording.) Record the option in the run file and in every call
record; the probe tools (`probe_reading.py`, `probe_wording.py`) accept the same option.

## P2. Cut-off classes from the raw reply
For every physical attempt record the length of the visible reply (characters) and classify a cut-off as `empty`
(no visible text or only whitespace) or `partial` (some visible text). Do not derive visible tokens from
`completion - reasoning` (the provider's reasoning meter can exceed the completion total: 8,282 > 8,192 and
16,763 > 16,384 in the pilots). Add to the episode row and to `summarize.py`'s matched table: cut-off attempts
empty / partial, and rounds whose attempts were all cut split by the class of the LAST attempt. Old runs must still
summarize (derive the classes from stored raw replies where they exist, otherwise report `unknown`).

## P3. `--failed-writer fail` (default `drop` = today's behaviour)
Today an OWN or GROUP writer that never produces a usable reply can be dropped while a CMAS failure ends the episode
(`horizon.py` around lines 340 and 409). With `fail`, a required writer that exhausts its attempts or repairs ends
the planning round as failed in every structure, with the same end label and first-blocked cause as for CMAS. State
exactly what "required" means (a writer whose robots have at least one doable action?) and keep it the same for the
three structures.

## P4. A cheap same-state check for the main session
Extend or reuse the existing probe so that the main session can ask ONLY the first planning round of chosen maps,
once per writer, with `--plan-note none` and `--plan-note continue` on the same boards, same limit, and get per arm:
attempts, cut-offs empty / partial, usable replies, generated and reasoning tokens (as metered), visible reply
length. Give the exact command for boards 1x3, 2x3, 3x3, map set `scaled:2`, seeds 0 to 3, structures CMAS, GROUP
(G = 3) and OWN, limit 8,192, with the number of calls and the reserved cost.

## P5. Tests and report
Fake-model tests for P1 to P4 (prompt identity without the option; the sentence present for all three writers and in
repairs; classes; the equal failure rule; old run folders still summarize). All earlier tests pass. Append
"CHEN2D-19" to `REPORT-CHEN2D.md` with the full prompt of each writer for one 2x3 board with and without the note,
the commands for the main session (the first-round check, and the 18-episode pilot of task 18 with
`--plan-note continue --failed-writer fail --dropoff event --map-set scaled:2` at limit 8,192), test results and
"확인 안 됨". Last step: create `review/ASTRA-CHEN2D-19.done`.
