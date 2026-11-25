# TASK-CHEN2D-18: boards of 3, 6 and 9 robots (2026-11-25)

Context: tasks 1 to 17 are done. Same hard limits (this folder only, no network, fake model for tests, no real-model
batches, nothing under `20261123-phase3/`). Defaults of every existing framework, option and registered map stay byte
for byte.

The user (2026-11-24 23:56 KST): "흠 내 생각에 블럭 갯수를 늘리고, 인원은 그대로라서 좀 힘든 거 같은데, 인원을 3대 / 9대로
하면 어때? 꼭 2의 배수여야하나", then "3대 / 6대 / 9대 이렇게". Decision: the main experiment uses 3 robots (a 1x3
board), 6 robots (a 2x3 board) and 9 robots (a 3x3 board),
one box per robot (`--map-set scaled:1`), structures CMAS, GROUP (three robots per sub-team) and OWN, matched protocol.
Today `run_chen2d.py` and `enrol_maps.py` refuse every size except 2x2, 2x4, 4x4, 4x8.

## P1. Sizes 1x3, 2x3 and 3x3
- Accept `1x3`, `2x3` and `3x3` in `--sizes` of the runner, `enrol_maps.py`, `probe_reading.py`, the summary and cost tools,
  for the scaled map family and the matched protocol. Do not add any other size. Do not register legacy maps for
  them; refuse `--map-set legacy` with these sizes with a clear message.
- Check everything that silently assumes at least two rows, an even side or one of the four old sizes: neighbour
  lists, prompts, row-major speaking order, step and round limits, map generation, the scripted reference solver,
  the fake model, event placement code (static only is needed; refuse other conditions for these sizes if they do
  not work), record fields that store the size.
- `GROUP --group-size 3`: on 3x3 three sub-teams and on 2x3 two sub-teams, one per row (1x3 blocks); on 1x3 it must equal the matched CMAS
  (one caller). State the partition in the run file. `--group-size 9` on 3x3 equals CMAS, `--group-size 1` equals OWN.
- Register `scaled:1` maps for the three sizes, seeds 0 to 15 (seeds 0 to 3 are for development, 4 to 15 for the
  experiment). Report per size: boxes per map, scripted steps (min, max, mean), planning rounds at H=5, and, with the
  scripted writers, steps and calls for CMAS, GROUP (G=3) and OWN on every map. Every map must be solvable.

## P2. Tests and report
Fake-model tests: the three sizes run to completion for the three structures at H=1 and H=5; the group equivalences;
1x3 edge cases (a robot with one neighbour); refusal messages; all earlier tests pass; legacy and existing scaled
registries verify unchanged. Append "CHEN2D-18" to `REPORT-CHEN2D.md` with the tables above, the exact commands for
the main session (pilot on seeds 0-1, experiment on seeds 4-15), calls per planning round per structure and size
with and without repairs, test results and "확인 안 됨". Last step: create `review/ASTRA-CHEN2D-18.done`.

## Restart note (2026-11-25 02:30 KST)
A first run of this task was stopped by the main session at 2026-11-24T15:55Z (`review/ASTRA-CHEN2D-18.STOPPED.txt`)
and may have left partial edits in this folder; the last verified code is `../20261124-chen2d-snap-v17` (240 tests).
The task is needed again: the user now wants the project's own 3D task to follow BoxNet's rules ("사실상 BoxNet처럼
가는 거 어떄?", 2026-11-25 02:01 KST), so the 1x3 / 2x3 / 3x3 boards are the main experiment's boards. Inspect what the
interrupted run left (diff against the snapshot), keep what is correct, finish everything above, and say in the report
what you found from the interrupted run. Nothing else changes.
