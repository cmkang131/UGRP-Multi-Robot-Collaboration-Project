# TASK-CHEN2D-6: tell everyone what a drop-off is (2026-11-24)

Context: tasks 1 to 5 are done (`REPORT-CHEN2D.md`). Same hard limits (this folder only, no network, fake model for tests, no real-model batches).

Finding in the real-model smoke of version 5 (`../20261124-chen2d-snap-v5/runs/v5-smoke-2x4`, 8 robots, `--dropoff always`): DMAS agents put boxes into the neutral drop-off BEFORE any change of orders (for example `2x4_DMAS_e1_member_env100_auto` step 1: box_purple into the drop-off; `..._env101_free` step 2: box_green), which is scored as a wrong delivery and makes strict success fail for a reason that has nothing to do with the news. The drop-off is an object nobody explained. The rules of the world must be known to everyone; only the news (which colour changed, and when) is private.

## J1. `--dropoff-rule on | off` (default on when `--dropoff always`, forced off with `--dropoff event`)
- With `on`, one sentence is added to every prompt that states the task (central planner, local agents in DMAS / HMAS-1 / HMAS-2, in every condition including static, from the first step), placed directly after the authors' sentence that states the goal (the sentence about moving boxes to the same-coloured targets; find the exact site in each template and use the same site in all of them):
  `The dropoff is only for boxes whose order has been changed to the dropoff. Putting any other box into the dropoff counts as a wrong delivery, and a wrong delivery cannot be undone.`
- The sentence is identical for every framework, every robot and every condition, before and after the event. It does not say whether, when or for which colour an order changes.
- The relay prompts of version 5 (`choice`, `free`) do not need it (they contain no task statement); say so in the report if that is right, or add it at the same relative place if they do state the task.
- `off` reproduces version 5 byte for byte (keep the version-5 replay test green with `--dropoff-rule off`).
- The run folder records the switch; the summary refuses to mix values.

## J2. One more outcome column (no change to the primary outcome)
`change_respected`: for e1, 1 if every box of colour A that was still present when the event fired ended in the drop-off and none of them in target_A; 0 otherwise (including boxes of A left at the end); NA when no box of A was present at the event or the event did not fire. For e2 the analogous value for the returned box. Also `dropoff_misuse`: number of boxes put into the drop-off that were not entitled to it, split into before and after the event. Add both to the CSV, the summary and `paired.py --outcome strict|change_respected` (default strict).

## J3. Tests and report
Tests: the sentence is present exactly once in every task-stating prompt of all four frameworks in static and e1, before and after the event, told or not; prompts of untold robots still do not contain the colour of the change; `--dropoff-rule off` equals version 5; the two new columns on constructed episodes (misuse before the event, A into target after the event, A left over). Append "CHEN2D-6" to `REPORT-CHEN2D.md` (the insertion site per template with line numbers, test output, the updated batch commands). Last step: create `review/ASTRA-CHEN2D-6.done`.
