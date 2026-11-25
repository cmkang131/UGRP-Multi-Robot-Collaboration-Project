# TASK-CHEN2D-20: a writer that fails idles only its own robots; the episode goes on (2026-11-25)

Context: tasks 1 to 19 are done (263 tests). Same hard limits (this folder only, no network, fake model for tests, no
real-model batches). Everything below is OPT-IN; defaults stay byte for byte.

Why. The user (2026-11-25 08:04 KST, verbatim): "잘리면 한 번도 못 움직인다로 하는 게 맞나.."
Today a call whose attempts are all cut at the output limit ends the whole episode in every structure
(`horizon.py`, `StopEpisode` with the output-limit label, around line 482), so in the pilots one robot's failed call
stopped all nine robots and scores were all-or-nothing (`../20261124-chen2d-snap-v18/runs/v18-pilot-r2`: 12 of 18
episodes ended on the output limit, 10 of them before any move). The research question is "which failure blocks how
much of the team's next action". A rule that turns every failure into a full stop hides exactly the difference
between the structures: a failed leader call leaves nobody with a plan, a failed sub-team call leaves one row, a
failed own call leaves one robot. In a real team the other robots would keep moving.

## P1. `--failed-writer idle` (a third value next to `drop` and `fail`)
With `idle`, in the matched protocol:
- A writer that ends without a usable list for ANY reason that today ends the round or the episode on that writer
  (every attempt cut at the output limit; client reply attempts exhausted on unusable replies; last repair still
  unreadable; last repair still proposing a first-step action outside the doable list) does NOT end the episode. The
  robots that writer is responsible for get no action for this planning round (all H steps idle). Record a
  `writer_blocked` event with round, structure, speaker, the robots it covers, the cause (same cause names as
  today), attempts, empty / partial cut-off class of the last attempt, and tokens spent.
- Later writers of the same round see, in the earlier-lists slot, that the blocked writer's robots have no entries
  (say exactly how it is shown; use the same representation in all three structures, for example an explicit empty
  list for those robots, and state it in the prompt wording only if a wording already exists for idle robots).
- The other writers' lists are merged and executed as today. A round in which no robot executed any action (all
  required writers blocked, or all lists empty or rejected) is a `stalled round`. The next planning round starts from
  the current state.
- The episode ends when the board is complete, at the existing step / round / call ceilings, or after
  `--max-stalled-rounds K` consecutive stalled rounds (default 3 with `idle`; option recorded in the run file) with
  the end label of the last blocking cause (for example `failure output limit`). Model-service (transport) failures
  keep today's behaviour and labels: they are not planning failures.
- "Required" has the meaning of task 19. A blocked optional writer (no doable action for any of its robots) is
  recorded but never makes a round stalled by itself.

## P2. Measures for this rule (episode row, `summarize.py` matched table, per structure and size)
- delivered boxes and total boxes (already there: `correct_deliveries`, `box_count`); show delivered / total as the
  first result columns of the matched summary;
- robot-rounds blocked, by cause (a blocked leader on a 3x3 board counts 9 robot-rounds, a blocked row 3, an own
  writer 1), and writer calls blocked by cause;
- stalled rounds, planning rounds with at least one blocked writer, first blocked cause (existing field kept);
- tokens (prompt, generated) spent on blocked calls separately from tokens of calls that produced an executed list,
  and tokens per delivered box (all tokens of the cell divided by all delivered boxes of the cell; `NA` with the
  totals shown when nothing was delivered). Fix `cost.py` the same way if it still divides by completed episodes.
Old run folders must still summarize.

## P3. Tests and report
Fake-model tests: one blocked own writer while the others move; a blocked row; a blocked leader (stalled round) that
recovers in the next round; K stalled rounds ending the episode with the right label; the later-writer view of a
blocked writer; counts and token splits; `drop` and `fail` unchanged; all earlier tests pass. Append "CHEN2D-20" to
`REPORT-CHEN2D.md`: the rule in plain words, the exact record fields, the command for the main session (the 18-episode
pilot of task 19 with `--failed-writer idle --plan-note continue --dropoff event --map-set scaled:2` at limits 8,192
and 16,384, seeds 0 to 1; and the experiment command for seeds 4 to 15), fake call counts, test results, "확인 안 됨".
Last step: create `review/ASTRA-CHEN2D-20.done`.
