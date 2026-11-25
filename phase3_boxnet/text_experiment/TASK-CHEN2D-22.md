# TASK-CHEN2D-22: the next difficulty step from the source paper, BoxNet2 (2026-11-25)

Context: tasks 1 to 21 are done (292 tests). Same hard limits (this folder only, other folders read-only, no network,
fake model for tests, no real-model batches, never print or copy the key). Everything is OPT-IN; with the defaults
every prompt, record and summary stays byte for byte as today.

## Why (the user's words, verbatim, 2026-11-25 KST)
- 16:18 "엄; '로봇마다'가 왤케 잘 성공하지 문제가 너무 쉬운가"
- 16:22 "난이도 올리는 거는 막 올리지 말고, 기존 연구 들은 어떻게 난이도 조절이 되는지 확인해봐"
- 16:26 "ㄱㄱ" (answering my proposal below)

Finding: the current board is Chen et al.'s BoxNet1 ("We assume no collisions"). The reference solver
`map_events.reference_plan` is an independent per-robot rule (nearest box one hop toward the nearest matching target,
no look at other robots) and solves every map in 5 to 15 steps, so the task needs no coordination. The survey
(`../20261123-plan3/DIFFICULTY-SURVEY-20261125.md`) shows that prior work raises difficulty by a ladder of
qualitatively different constraints with a countable value per step. The source paper's next step is BoxNet2
(arXiv 2309.15943, IV-A): "each box can only be moved between cells by being placed at a corner, and a given corner
can only hold one box at a time; we treat placing two or more boxes on the same corner as a collision". The user
approved: adopt BoxNet2 as it is, add no other constraint, count difficulty per map, and count a collision as "that
action is not executed" (not as a failed episode, which is what Chen did), to fit our `--failed-writer idle` rule.

The source code is here (read-only, MIT licence as in `../20261113-l0-planning-env/refs/hmas/LICENSE`):
`../20261113-l0-planning-env/refs/hmas/env2_create.py`, `env2-box-arrange.py`, `prompt_env2.py`. Follow it exactly
unless this task says otherwise; cite file and line for every rule you take from it.

## P1. `--env boxnet2` (default `boxnet1` = today)
- Board as in `env2_create.py`: cells `i+0.5_j+0.5` hold targets; corners `i_j` (integers, `(rows+1) x (cols+1)`)
  hold boxes, at most one each. A robot in a cell can act only on boxes on the four corners of its cell: move one box
  to one of the other three corners of its cell, or move it to a same-colour target in its cell (the box and that
  target are removed, exactly as `action_from_response` in `env2_create.py` does). Doable actions are listed per robot
  exactly as `state_update_func` in `env2_create.py` lists them (adapted to our board text format and the matched
  protocol's sentences). Note in the report that in a 1 x 3 row the two corners on each shared edge are the two
  hand-over places of that door (one per direction in the MuJoCo scene).
- Collision rule `--collision skip|fail` (default with boxnet2: `skip`). The step is simultaneous as in Chen
  (`action_from_response`: all moves applied, then occupancy checked). With `skip`: every move whose destination
  corner would hold more than one box after the step is not executed (the box stays where it was); repeat until no
  corner holds more than one box (a cancelled move can free or keep a corner; say exactly how the iteration ends and
  that it terminates); the other moves of that step execute. Record each cancelled move as `collision` with step,
  robot, box, corner and the moves that met there. With `fail`: Chen's behaviour, the episode ends with the label
  `collision` (kept only for a fidelity check against the source).
- Everything else as today: matched protocol, horizon 5, three structures with the same sentences, earlier-lists
  slot, `--plan-note continue`, `--failed-writer idle`, `--cut-answer prefix`, delivered boxes / total, tokens per
  delivered box. The collision sentence of `prompt_env2.py` line 15 ("Do remember that each corner can only contain at
  most one box! ...") is added once, identically for every structure; show the full prompt of one 3x3 leader, sub-team
  and own writer in the report.

## P2. Maps and the difficulty value
- Generate BoxNet2 maps for 1x3, 2x3, 3x3, seeds 0 to 15, with the SAME number of boxes per colour as the registered
  `scaled:2` maps of the same size and seed (two boxes per robot), boxes placed with `env_create`'s corner rule and the
  seed's own random stream, targets in cells as in `env_create`. Register them as a map family the runner selects with
  `--env boxnet2 --map-set scaled:2`; store hashes; keep the BoxNet1 maps untouched.
- For every map compute and store:
  (a) `coordinated_steps`: steps of a collision-free centralized reference plan (a deterministic search or a
      prioritized planner over the corner graph that never collides; say which, and whether it is optimal);
  (b) `min_corner_handovers`: the minimum number of times boxes must change cell (robot) along their routes, summed
      over boxes (the Collab-Overcooked-style difficulty value: "minimum number of collaborative actions");
  (c) the independent rule's result: each robot moves its nearest box one corner toward the nearest matching target
      without looking at the others, under `--collision skip`; completed or not within 40 steps, steps, number of
      cancelled moves. This shows whether coordination is now needed. Give the table for all 48 maps and the summary
      per size (median and range), and compare with BoxNet1 (where the independent rule completes every map).
- If many maps cannot be solved even by (a) within 40 steps, or if the independent rule still completes nearly every
  map without collisions, STOP and report: that changes what the user was told, and the main session decides.

## P3. Tests and report
- Fake-model tests: rule fidelity against the source functions on random boards (doable lists, state updates,
  collision check under `fail`), `skip` cancellation cases (two boxes into one corner; a box into an occupied corner
  whose box leaves in the same step; a chain), prompts for the three structures, the reference planner never collides
  and completes, the difficulty values, byte identity of every BoxNet1 path, interplay with `--failed-writer idle` and
  `--cut-answer prefix`. Rerun the whole suite.
- Append "CHEN2D-22" to `REPORT-CHEN2D.md`: the rules with source lines, the map table and summaries, the three
  prompts, the exact pilot commands for the main session (18 episodes = sizes 1x3/2x3/3x3 x seeds 0 to 1 x three
  structures, at limits 8,192 and 2,048, `--jobs 8`, with call and cost estimates from the fake pilot), test results,
  "확인 안 됨".
Last step: create `review/ASTRA-CHEN2D-22.done`.

## CONTINUATION (2026-11-25 16:55 KST, main session)
Your P2 stop was right: two boxes per robot do not fit on BoxNet2 corners (3x3: 18 boxes, 16 corners). Continue with:
- Boxes: ONE per robot (`--map-set scaled:1`, the registered BoxNet1 `scaled:1` maps exist for all 48 size-seed pairs
  and give the colour counts: 3 / 6 / 9 boxes for 1x3 / 2x3 / 3x3 on 8 / 12 / 16 corners). This matches Chen's own
  BoxNet2 density (one box per colour) more closely than two per robot, and the MuJoCo plan (one box per robot).
  The user has not confirmed this change yet; build it so that the box count stays a parameter.
- Placement: Chen's loop can skip a pair when the drawn cell has no free corner. Deviate minimally so every pair is
  placed: when the drawn box cell has no free corner, draw the box cell again from the same seeded stream until a cell
  with a free corner comes up (say in the report how many redraws each map needed). Everything else as `env_create`.
- Then do P1 to P3 as written (runner integration, collision `skip|fail`, prompts, the 48-map table with
  `coordinated_steps`, `min_corner_handovers`, the independent rule under `skip`; BoxNet1 `scaled:1` as the control),
  and keep the P2 stop rule: if the independent rule still completes nearly every map without cancelled moves, or the
  coordinated reference cannot solve many maps within 40 steps, stop and report.
- Pilot commands in the report: 18 episodes (seeds 0 to 1) at 8,192 and 2,048 with `--jobs 8`.
Last step: create `review/ASTRA-CHEN2D-22B.done`.
