# TASK-CHEN2D-16: sub-team leaders, one structure with a group size (2026-11-24)

Context: tasks 1 to 15 are done (15 added scaled maps, `probe_reading.py` and `--protocol matched`). Same hard limits
(this folder only, no network, fake model for tests, no real-model batches, nothing under `20261123-phase3/`). Defaults
of every existing framework and option must stay byte for byte.

The user (2026-11-24 21:37 KST): "근데 이거 실험은 크게 어려운 게 아니니까 계층구조도 비교해보면 안돼? 그니까 트리 구조처럼,
팀A의 팀장, 팀B의 팀장... -> 이런 식으로 여러 팀으로 나뉘어서 N명이 계획을 결정하는 방식으로".
The main session's reading: several sub-teams, each with a leader that writes the plan of its own sub-team; no
top-level leader above them (a full tree is a later question). The paper's axis becomes "how many robots does one
call decide for": all (leader), a sub-team (new), one (own actions).

## P1. Framework `GROUP` with `--group-size G` (valid with `--protocol matched`, any horizon)
- The grid is partitioned into rectangular blocks of G squares (one robot per square). `--group-size 4` = 2x2 blocks,
  `--group-size 8` = 2x4 blocks; refuse a size that does not tile the grid, and say which sizes are valid for 2x2, 2x4,
  4x4, 4x8 (and 2x8, 4x6, 6x6, 8x8). The partition is deterministic, recorded in the run file, and shown in the report
  for every grid.
- One planning round: the sub-team leaders are called in a fixed order (row-major over blocks). Each call sees exactly
  what an OWN call sees (whole board, history and state position as selected, and the lists already accepted from
  earlier callers in this round) and writes H steps for every robot of ITS block, in the same joint format the leader
  (CMAS) uses, restricted to its robots. The program merges the blocks step by step, as OWN does.
- By construction: G = number of robots must behave like the matched CMAS (one caller, all robots) and G = 1 like the
  matched OWN. Test both equivalences on the wire (identical prompts and identical merged plans with the fake model),
  or say exactly which sentence must differ and why.
- Same wording as the other two matched structures except the sentences that say whose actions to write; same
  per-author repair rule, same cut-off bookkeeping, same "what stopped the team" record, same ceilings and end labels,
  same lenient-parsing rules (reuse, do not fork, the CMAS joint-plan parser and the OWN peer-visibility rules: a
  block's list is shown to later callers only after its first step passes the doable check; a refused or dropped
  block is shown as null and contributes no actions that round).
- A box may have to cross a block border. State how a handover across blocks is planned (the receiving block's leader
  speaks later and sees the plan; the earlier one does not) and whether the scripted solver in tests exercises one.
- Records: `framework=GROUP`, `group_size`, number of callers per round, and for every call how many robots it wrote
  for and how many of them had a doable action. `summarize.py` and the token totals group by framework and group size.
- Works with scaled maps and with `probe_reading.py` (caller `group_first`, `group_last` analogous to the own callers).

## P2. Tests (fake model) and report
Partition for every valid grid and size; the two equivalences; cross-border handover; repairs per author; visibility;
resume; byte identity of all earlier defaults; all earlier tests pass.
Append "CHEN2D-16" to `REPORT-CHEN2D.md`: the rules, the full prompt of the second sub-team leader on a 4x4 board at
H=5 next to the matched CMAS and OWN prompts with the differing sentences marked, calls per round for 16 and 32
robots at G = 1, 4, 8, all, fairness points you think a reviewer would raise (list them plainly), commands for the
main session, test results, and "확인 안 됨". Last step: create `review/ASTRA-CHEN2D-16.done`.
