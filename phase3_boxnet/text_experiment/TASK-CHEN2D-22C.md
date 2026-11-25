# TASK-CHEN2D-22C: redo the model-free BoxNet2 analysis with fair baselines (2026-11-25)

Start only after `review/ASTRA-CHEN2D-22B.done` exists. Same hard limits as task 22 (this folder only, no network, no
real-model calls, never print or copy the key). Analysis code goes into `boxnet2_planning.py` (new functions; keep the
existing ones and their outputs byte for byte) and `review/chen2d-22/analysis-c/`.

The user (2026-11-25 17:12 KST, verbatim): "BoxNet2 분석 좀 다시 해줘봐".

## What is wrong with the first analysis (main session reading `boxnet2_planning.py`)
1. `coordinated_plan` is serial: one robot moves one box per step (it executes `{robot: action}` alone), so
   `coordinated_steps` counts total box moves, not the team's makespan. That is why 3x3 needs 17 "steps" while the
   independent rule finishes the maps it can in 6. It proves solvability but is not a step baseline.
2. `independent_plan` ignores even the robot's OWN four corners: it moves a box toward the target without checking
   whether the destination corner, which the robot itself can see, already holds a box. Many of its "collisions"
   (3x3 median 77.5 cancelled moves, up to 196) are therefore moves into visibly occupied corners repeated every step,
   not the coordination problem we want to show. The LLM writers see the whole board. The honest no-coordination
   baseline is a robot that sees the whole current board but not the other robots' intended moves.
3. `min_corner_handovers` uses `corner_distance` (hops to a corner of the target cell) per box and ignores occupancy.
   Say exactly what it counts; it may count corner moves rather than changes of robot.

## A1. Baselines to compute on all 48 maps (`scaled:1`, the registered BoxNet2 maps of task 22B), limit 40 steps
(a) `parallel_coordinated`: a centralized planner that moves several robots in the same step without collisions
    (reserve destination corners within the step; a corner vacated in the same step may be reused only if Chen's
    executor allows it, check `boxnet2.execute`). Prioritise by remaining distance; deterministic. Report makespan.
    If an exact minimum makespan is cheap for 1x3 (search over joint states), compute it there to show how far the
    heuristic is from optimal; say for which sizes it was feasible.
(b) `independent_local`: every robot sees the whole current board (all corners and their boxes) and chooses its own
    move as the current rule does, but never chooses a destination corner that is occupied at the start of the step.
    It cannot know the other robots' moves of the same step, so two robots may still pick the same empty corner
    (collision: both moves cancelled under `skip`). Deterministic tie-break as now, AND a randomised tie-break / wait
    variant (with probability 0.5 a robot whose move was cancelled in the previous step waits one step), 20 random
    seeds per map; report completion rate and steps over seeds.
(c) the existing `independent_plan` result, kept for reference, labelled "ignores occupancy".
For every baseline and map: completed (yes/no), steps, cancelled moves, and for failures the kind: livelock (the
same collision repeats), deadlock (no robot has a move toward a target), or ran out of steps while progressing.

## A2. Difficulty values, defined exactly
- `min_box_moves`: sum over boxes of the minimum number of corner moves to delivery (including the final move onto the
  target), ignoring other boxes; and the same with other boxes treated as fixed obstacles (from `shortest_delivery`).
- `min_robot_changes`: sum over boxes of the minimum number of times a different robot must make the next move of that
  box along a shortest route (a true hand-over count). Explain how it relates to the rooms-and-doors picture (in a
  1x3 row, crossing from one room's corners to a corner shared with the next room).
- Keep the existing `min_corner_handovers` column only with its exact meaning stated.

## A3. Report
Append "CHEN2D-22C" to `REPORT-CHEN2D.md`: per size the median and range of each value; completion of (a), (b)
deterministic, (b) randomised, (c); how many maps each baseline completes and why the others fail; BoxNet1 control
(the independent rule of `map_events.reference_plan` on the same `scaled:1` maps). End with one paragraph in plain
words: does BoxNet2 with one box per robot require coordination for a team that sees the whole board but not the
others' plans, and on which boards. "확인 안 됨" for anything not measured. Tests for the new functions; rerun the
whole suite.
Last step: create `review/ASTRA-CHEN2D-22C.done`.
