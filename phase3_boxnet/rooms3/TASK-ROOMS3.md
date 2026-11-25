# TASK-ROOMS3 (DRAFT, NOT STARTED): three rooms in a row, three robots, BoxNet rules in MuJoCo (2026-11-25)

STATUS: started 2026-11-25 after TASK-HANDOVER-FIX6. The user chose (16:21 KST, answer "1") to set a held box down
even when tilted and to score by where it lands; build the three-room scene on that rule (FIX6 option
`--station-tilt ignore`). The hand-over result was 9 of 12 and 8 of 12 (colour-swapped), below the pre-set 10 of 12;
the user's choice of option 1 is the go-ahead to build this scene.

## Why
The user (2026-11-25 02:01 KST, verbatim): "사실상 BoxNet처럼 가는 거 어떄?", "실제 시뮬이랑 sim2real도 그 방향으로 가게",
and before that "흠; 걍 각자 하나의 방을 가지면 안되나?", "그러고 문 주변에 두면 서로 넘길 수 있고, 자기 방에 QR이
있어서 목적지가 있는 느낌으로다가". The text experiment runs on the BoxNet code (`../20261124-chen2d`, boards 1x3 / 2x3 /
3x3, two boxes per robot, plans of 5 steps, structures leader / sub-teams / own). This task builds the MuJoCo
confirmation for the 1x3 board only: three rooms in a row, one robot per room, the same rules.

## What exists (read first)
- Two-room hand-over test: `handover/` (driver `run_trial.py`, `layout.py`, `score.py`, `scenes/trials.csv`), executor
  hooks `exec/sim/handover_scene.py`, `exec/scripts/handover_world.py`, `exec/harness/handover_policy.py`, cloud kit
  `cloudrun/handover/`. Reports `REPORT-HANDOVER-GATE.md` (sections up to FIX4), `REPORT-HANDOVER-CLOUD.md`.
  Result of the fixed cohort `cloudrun/runs/handover-fix4-Zc6HAKV9`: 9 of 12 complete transfers (blue 6 / 6, red
  3 / 6; failures: box lost in the carry, box lost before set-down, receiver grasp failed twice).
- Text-experiment planner and prompts: `../20261124-chen2d-snap-v20` (`matched_protocol.py`, `run_chen2d.py`,
  `--failed-writer idle`), board text format in `prompt_env1.py`.
- Design notes: `../20261123-plan3/debate/DESIGN-20261125.md` ("DRAFT 3"), reviews `R17`, `R18`, Neon 6
  (`../20261123-plan3/review-neon/REPORT-NEON-6.md`: colours, door congestion, floor size).

## Rules to implement (same as the 1x3 text board)
- Room = BoxNet square. The room's robot never leaves its room. One QR sign per room = the targets of that room.
- One step of one robot = one box move: either `move(box, target)` (carry the box to the room's sign and set it
  down) or `move(box, neighbour room)` (carry it to the hand-over place at that door and release it there; from
  then on the box belongs to the neighbour room's board state).
- A plan is a list of up to 5 steps per robot, written by the leader (all three robots) or by each robot (own). The
  sub-team structure equals the leader on this board and is not run here.
- Execution of a plan is step-synchronous as in the text experiment: step k of every robot is attempted, then the
  board state is rebuilt from what actually happened (a failed grasp or a dropped box leaves the box where it lies
  and the step counts as executed-but-failed; a held box that is tilted is set down anyway and counts by where it
  lands), then step k+1. After the plan's steps a new plan is asked from the
  measured state. A robot whose writer gave no usable list idles for that plan (`idle` rule).

## Defaults used in this draft (each is an OPEN user decision; keep them as parameters)
- Colours: red and blue only (the frozen perception and grasp skills know these two).
- Hand-over places: two per door, one per direction, so that opposite transfers do not collide. Each place holds ONE
  box (as in the physical setup). A step that would put a second box on an occupied place is not executable and is
  reported to the planner like any other not-doable action. Keep the capacity as a parameter: the text experiment
  does not have this rule yet and the user has not decided whether it gets it.
- Rooms: the hand-over test's room size (2.65 m x 2.70 m, door 1.10 m). A smaller room for the real floor is a
  later parameter.
- Boxes: one per robot in MuJoCo (three boxes), because a run with six boxes needs about eleven grasps and the
  archived grasp failure rate is 19 of 82.

## Work packages (report after each; stop and report if one cannot be done within its limit)
R1. Scene: three rooms in a row with two doors, three signs, hand-over places, three robots, boxes from a map file
    that is generated from a 1x3 BoxNet map of the text experiment (same seeds; give the converter and show three
    converted maps as pictures). Offline checks as in the hand-over scene (card visibility, box selectable by the
    own camera in both colours: the FIX4 check).
R2. Step executor: the two step kinds above built from the hand-over policy's stages (pick, carry, release at the
    door place / set down at the sign), with the board-state reader (which box is in which room, at a hand-over
    place or delivered) from the simulator's ground truth for scoring AND from the robots' own perception for the
    planner input; report where the two differ.
R3. Adapter to the text planner: the MuJoCo state is rendered in exactly the text board format, the planner of
    `../20261124-chen2d-snap-v20` is called unchanged (matched protocol, leader and own), its lists are executed by
    R2. No real-model call by you: test with the scripted fake model and a recorded plan.
R4. Records and score: per plan and step what was asked, what the robot did, whether the box moved as planned;
    episode result = delivered boxes / boxes, planning failures by cause (same names as the text experiment) and
    execution failures by kind, kept apart.
R5. Cloud kit: one trial = one episode; estimate wall time and cost per episode from the hand-over numbers
    (4,417 s of wall time for the 12 hand-over trials) before anything is run; the main session runs the cloud.
Tests for every package; `REPORT-ROOMS3.md` with the commands for the main session and "확인 안 됨".

## CONTINUATION 1 (2026-11-25 17:40 KST, main session)
Your R1 stop is understood. The main session tried the native check locally with MuJoCo 3.16.0 plus OpenCV 5.0.0
(`<home>/ugrp-render-arm-s-20261027/.venv-mujoco/bin/python` with cv2 on PYTHONPATH): it then fails with
`FileNotFoundError: .../20261123-phase3/exec/sim/masterpi_scene.xml` (log `rooms3/verification/native-main.log`).
No local environment has the full executor assets; the hand-over trials ran on Cloud Run for this reason.
- Add to the hand-over cloud kit (`cloudrun/handover/`, same patterns as FIX5/FIX6: one image, staged context, tests)
  a job mode that runs `rooms3.check_camera` for given seeds inside the image and returns its result folder, plus the
  exact main-session commands (build, deploy, run for seeds 0, 3, 6, fetch). Do not run cloud commands yourself.
- Then continue with R2 to R5 offline as far as possible without the native scene (code and offline tests, fake
  planner), and give the main-session commands for each cloud check that needs the image. Stop and report after R2 if
  R2's physical execution cannot be tested offline at all.
Last step: create `review/ASTRA-ROOMS3-C1.done`.

## CONTINUATION 2 (2026-11-25 19:50 KST, main session)
Cloud cohort `cloudrun/runs/rooms3-c1-2j5AueoF` (log `cloudrun/runs/.chains/rooms3-c1.log`):
- `rooms3-camera`: seeds 0, 3, 6 all `passed` in the image.
- `rooms3-step`: all three ended `error`, `TimeoutError: 1500 s step-check budget` (`rooms3/check_step.py` line 93,
  `signal.alarm(1500)`), at sim 398 to 463 s. Moves done before the stop: seed 0 r1 lift+place, r2 miss then lift+place,
  r3 started; seed 3 r1 and r2 lift+place, r3 miss; seed 6 r1, r2, r3 all lift+place (round 1 physically finished,
  the end-of-round survey and scoring were cut). Wall time is about 3.3x sim time, so one round of three serial moves
  needs about 1,500 to 1,600 s of wall time.
Do now:
1. Make the step-check budget a parameter (default unchanged for the tests), and give the cloud job enough time:
   step-check budget 5,400 s and the Cloud Run task timeout 7,200 s for this mode only (job template / ops option;
   the hand-over gate mode keeps 1,800 s). Tests for both.
2. Re-stage the image context and give the exact main-session commands to rerun `rooms3-step` for seeds 0, 3, 6 in a
   NEW cohort (camera mode not needed again).
3. Update the per-episode time and cost estimate in `REPORT-ROOMS3.md` with the measured 3.3x factor and about 150 s
   of sim per move (say how many rounds a 3-box episode needs at the reference plan and the resulting wall time and
   USD at the existing 2 vCPU / 6 GiB price).
Do not start R3 to R5 in this continuation. Last step: create `review/ASTRA-ROOMS3-C2.done`.
