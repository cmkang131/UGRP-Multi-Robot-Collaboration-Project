# TASK-CHEN2D-15: a same-state "reading load" probe for the leader and the own-actions caller (2026-11-24)

Context: tasks 1 to 14 are done. Same hard limits (this folder only, no network, fake model for tests, no real-model
batches, nothing under `20261123-phase3/`). Defaults of every existing framework and option must stay byte for byte.

Why: the user moved the paper away from Chen's structures. The open question is whether a call gets worse when it has
to READ more, and whether that depends on who is calling: the leader (one call writes the plan for every robot) or one
robot in the own-actions structure (OWN: writes only its own actions, sees the lists of robots that spoke before it).
An earlier probe (`<work>/20261123-plan3/analysis/context_rot/probe.py`, written by the
main session without review; read it, do not reuse it blindly) did this only for Chen's two prompts.
The main session will run the new tool with the real model. You build and test it offline.

## P0. Maps whose amount of work grows with the team (the user decided this on 2026-11-24 21:08 KST)
The registered maps have about 10 boxes whatever the grid (the generator draws 1 to 3 boxes for each of 5 colours).
The user: "로봇 수를 축으로 쓰려면 상자 수도 로봇 수에 맞춰 늘려야 … 아니 당연히 늘렸어야지".
- Add an opt-in way to generate and register maps with `--boxes-per-robot R` (a positive number; total boxes =
  round(R x robots), at least one). Keep the generator's mechanism (colours, targets, placement rules) and change only
  how many boxes are drawn; deterministic in the seed; every generated map must be solvable by the existing scripted
  solver. Say how the boxes are split over colours and whether more colours or targets are needed for large teams.
- Scaled maps live in their own registry (for example `envs-scaled/r<R>/<size>/env<seed>.json`) and are selected with a
  run option (for example `--map-set scaled:R`). Without the option everything stays byte for byte: the 45 registered
  maps, prompts, replays.
- Record `map_set`, `boxes_per_robot` and the box count in every episode record and CSV row; the summary tools
  group by it and never pool legacy and scaled maps.
- Report, for R = 0.5, 1 and 2 and sizes 2x2, 2x4, 4x4, 4x8, seeds 0 to 11: boxes per map, steps and planning rounds
  the scripted solver needs at horizon 1 and 5, and whether the existing step limits (30, or 40 on 4x8) and
  `--max-env-steps 30` still leave room; propose step limits that scale with the work if they do not. Do not pick R;
  the main session decides.
- Tests: determinism, legacy byte identity, solvability, registry separation.

## P1. Tool `probe_reading.py` (new file in this folder)
For a fixed list of saved board states taken from finished real episodes, rebuild the prompt of one caller with
different amounts of material to read, call the model once per prompt, and judge the proposed actions against the
current state. Nothing but the reading material may differ between the arms of one state.

- **States.** `--episodes DIR[,DIR...]` (episode folders of earlier runs, any framework) and `--per-episode K`:
  choose K steps per episode spread evenly over steps 2..last (step 1 has no history). Record run, episode, step,
  size, number of boxes left. The selection must be deterministic and independent of the caller and arm.
- **Callers** (`--callers leader,own_first,own_last`):
  - `leader`: the CMAS prompt of this code base at `--horizon H` (default 1).
  - `own_last`: the OWN prompt for the LAST robot in speaking order that has a doable action in this state; the lists of
    all earlier robots are filled with the action each of them actually executed at this step in the source episode
    (null when it did nothing), padded to H with nulls. Say in the report how you map a joint action to per-robot lists.
  - `own_first`: the same robot and state, but with no earlier lists (`{}`), so that only the peer lists differ from `own_last`.
- **History arms** (`--arms none,last1,all_before,all_after`): state-action history built by the existing history
  code from the source episode's real earlier steps; identical content for every caller of the same state.
  `none` = no history; `last1` = only the previous state-action pair; `all_before` = every earlier pair with the
  current state placed BEFORE the history; `all_after` = every earlier pair with the current state AFTER the history.
  The leader template natively has the state after the history; for this probe only, add the missing leader variant
  with the state before the history (move the same sentences, change nothing else) so that caller x order is complete.
  The existing run options must not change behaviour.
- **Call.** One attempt, temperature 0, `--max-output-tokens` (default 8192), the same client, spending guards,
  `--max-calls`, `--max-cost-usd` and per-call records as `run_chen2d.py`; `--model fake` works offline.
  `--shuffle SEED` randomises the call order; `--jobs N`. Resumable: a finished (state, caller, arm) is not asked again.
- **Judging** (per call, written to `results.jsonl` with the full prompt and reply saved beside it):
  plan produced or not; reply cut off at the limit; prompt tokens, generated tokens, reasoning tokens;
  number of proposed actions for the first step; number not doable in the current state by the authors' own checker;
  of those: exact repeat of what that robot did in the previous step, and "the box was in that square in the previous
  state and is not there now"; for the own callers also: conflict with an earlier robot's list (same box).
  For the leader judge every robot's action; for the own callers judge the caller's own action.
- **Summary** `probe_reading.py --summarize OUTDIR`: per caller x arm: states asked, plans produced, plans with at
  least one not-doable action, median prompt tokens, median generated tokens, cut-offs; and the paired counts between
  any two arms of the same caller (wrong only in A, wrong only in B, both, neither). Every share with its denominator.

## P1b. Fairness report (no behaviour change)
An independent review (`<work>/20261123-plan3/review-neon/REPORT-NEON-2.md`, section D2)
found two confounds in the earlier first-call comparison: the single-robot call was always put to the first robot,
which often has nothing to do on large maps, and the two prompts differ in wording outside the structural part (only
one has a "respond concisely" instruction, examples differ).
- The own callers here must be a robot that has a doable action (already required above); record in every row how
  many doable actions the caller has and how many robots on the board have any.
- In the report, list every textual difference between the leader prompt and the OWN prompt that is not required by
  the structure (length or brevity instructions, "think step by step", examples, output-format wording), with the
  exact sentences. Do not change them. Add `--strip-style` to the probe only: it removes exactly those listed
  non-structural sentences from BOTH callers so the main session can run the probe with and without them.

## P1c. A matched protocol for the main comparison (opt-in, `--protocol matched`; defaults unchanged)
Two design reviews (`<work>/20261123-plan3/debate/R11-ASTRA-extracted.md` Q3, Q7 and
`R12-ASTRA-extracted.md` Q6; read both) require that leader (CMAS) and own-actions (OWN) differ only in who writes what.
With `--protocol matched` (valid for CMAS and OWN at any horizon):
- **Same wording.** Both prompts use the same task description, action vocabulary, examples, brevity instruction and
  output-format sentences; only the sentences that say whose actions to write and what the caller sees from earlier
  speakers may differ. Use the wording list from P1b to decide what to align; show the two full prompts side by side
  in the report with the differing sentences marked.
- **Same reading layout.** History (state-action pairs of executed steps) is available to both with the same
  `--history-method` / `--history-window`, and `--state-position before|after` applies to both (today CMAS ignores it).
- **Same repair chances per author.** Each writer (the leader, or each robot) gets the same number of repair prompts
  per planning round, every repair reply is checked (today the leader's sixth repair reply is left unchecked), and
  the report states the rule. Record repair calls per round and robots dropped.
- **Cut-off bookkeeping.** For every logical call keep, per attempt, the provider finish reason (or the raw length
  flag), generated and reasoning tokens. Classify each planning round as: no cut-off; first attempt cut off and
  recovered by a retry; all attempts cut off (round stops); unknown. Add these counts to the episode record, the CSV
  and `summarize.py`.
- **Ceilings stated up front.** Environment-step cap, planning-round cap and the per-episode call ceiling are explicit
  options recorded in the run file; the same round cap for every size; an episode that ends on a ceiling gets its own
  end label (not "failed", not "output limit"). Report how many calls a 32-robot OWN episode needs per round so the
  main session can set the ceiling.
- **What stopped the team.** For each episode record the first planning round after which no joint action could be
  executed and why (output limit, unusable replies after repairs, not-doable actions, ceiling), separately from the
  final end label; `summarize.py` prints per cell: episodes by that cause, strict completions, and total calls,
  prompt tokens and generated tokens (failed episodes and retries included) divided by strict completions
  (print "no completion" when the divisor is zero).
- Works with the scaled maps of P0 and with `probe_reading.py` (the probe uses the matched wording when asked).
Tests for each bullet with the fake model; all earlier tests and byte replays still pass.

## P2. Tests (fake model)
Deterministic state selection; arms of one state differ only in the reading material (assert by diffing prompts);
identical history content across callers; the leader "state before history" variant moves only those sentences;
`own_first` and `own_last` differ only in the peer lists; the judge flags a stale action and a conflict in a constructed
case; resume; guards. All earlier tests still pass. Byte replay of defaults still matches.

## P3. Report
Append "CHEN2D-15" to `REPORT-CHEN2D.md`: what the tool does, the exact prompts of the three callers for one state
and the four arms (as collapsible blocks), the command the main session should run for
`--callers leader,own_first,own_last --arms none,last1,all_before,all_after --horizon 1` on 36 states drawn from six
episodes of sizes 2x4, 4x4, 4x8 (name suitable finished episodes from `../20261124-chen2d-snap-v12/runs/` or
`../20261124-chen2d-snap-v10/runs/`), the number of calls that command makes, test results, and a list
"확인 안 됨". Last step: create `review/ASTRA-CHEN2D-15.done`.
