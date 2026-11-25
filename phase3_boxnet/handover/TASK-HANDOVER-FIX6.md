# TASK-HANDOVER-FIX6: a held box is set down even when tilted; score by where it lands (2026-11-25)

Context: FIX5 is done (`REPORT-HANDOVER-GATE.md`, section FIX5). Same hard limits as FIX5 (work only under
`handover/`, `cloudrun/handover/`, the three executor hook files on the local branch `phase3/handover-cloud`; nothing
under `link/`, phase-2 folders; no network, NO cloud commands, no model calls; commits local only, no push; archived
runs read-only).

## Decision (the user, 2026-11-25 16:21 KST)
I offered two options for the 10° tilt rule: "1 (추천): 기울어도 들고 있으면 내려놓게 하고, 실제로 표지 앞에 바르게
놓였는지로 채점합니다. 지금은 내려놓기 전에 실패로 끝내서 결과를 모릅니다" / "2: 10도 조건을 그대로 두고 빨강의 기울기
원인을 더 찾습니다". The user answered: "1".

## Measured background
Across the two cohorts `cloudrun/runs/handover-fix4-Zc6HAKV9` (original colours) and
`cloudrun/runs/handover-fix5-swap-yimHXMgy` (swapped colours), four trials stopped at the station check with the box
still gripped (both fingers 3.6 to 5.1 N, clearance 65 to 74 mm) but tilted 10.7° to 16.1°: original trials 4
(`release`) and 6 (`set_down`), swapped trials 2 and 5 (`set_down`). All four were red. The check is
`criteria.held(...)` with `layout.TILT_TOL` at `exec/harness/handover_policy.py` around line 266.

## F1. The station check
- At the release station (donor) and at the set-down station (receiver), the condition to go on becomes: the box is
  held (both fingers at or above the existing force threshold, clearance at or above `LIFT_FLOOR`) WITHOUT the tilt
  condition. Record the tilt at that moment in the existing `station_hold_failed`-style observation, renamed or
  complemented so that the record says `held_tilted` with the tilt value when tilt > TILT_TOL, and the run goes on.
- Nothing else changes: the lift check after grasping, the carry watchdog, the resting / at-mark / at-sign scoring
  (a box resting on the floor must still be flat within TILT_TOL and inside the existing distance tolerances), the
  number of grasp attempts. The final success is decided only by where and how the box comes to rest.
- Opt-in by one option recorded in the trial records (`--station-tilt ignore`, default the old behaviour), so old
  cohorts re-score unchanged; the new cohort uses the option. Explain in the report where the 10° value came from
  (existing comment or record) and why it is kept for the resting check.

## F2. Tests, image, commands
- Tests: a tilted-but-held box at each station proceeds and is scored by its resting pose (success when it lands flat
  at the mark / sign, failure with the resting reason when not); the default keeps the old stop; old cohorts re-score
  byte-identical.
- Rerun the three suites. Stage the image context (one new image).
- Report section "FIX6" in `REPORT-HANDOVER-GATE.md` with the exact commands for the main session for ONE new cohort
  that runs only the four affected trials (original table trials 4 and 6, swapped table trials 2 and 5) with the new
  option, if the cloud kit can run a subset of trials and two tables in one cohort; if not, give the smallest set of
  commands (two cohorts are acceptable). Then how to score them together with the other 20 unchanged results of the
  two earlier cohorts (the simulation is deterministic for unchanged trials; say so only if the records support it:
  compare the fix3 and fix4 cohorts' unchanged red trials). "확인 안 됨" at the end.
Last step: create `review/ASTRA-HANDOVER-FIX6.done`.
