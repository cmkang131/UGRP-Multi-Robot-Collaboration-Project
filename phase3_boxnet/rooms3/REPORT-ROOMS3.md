# ROOMS3 work report

**Continuation 2 prepares a longer step rerun. Nothing has run in the cloud since Continuation 1.** The Continuation 1 cohort `rooms3-c1-2j5AueoF` passed all three camera checks. Its three step checks ended at the 1,500 s budget while boxes were still moving: 7 placements were seen across the 10 requested moves, and none was scored, because the end-of-round survey was cut. The step check now takes a 5,400 s budget, and its execution alone gets a 7,200 s Cloud Run task limit. The hand-over gate keeps 1,800 s. The rerun is in [Continuation 2 rerun](#continuation-2-rerun-step-only). R3–R5 remain untouched. [Camera and board measurements](rooms3/verification/c1-comparison.json) · [Continuation 1 chain log](cloudrun/runs/.chains/rooms3-c1.log) · [Estimate](#estimate-after-continuation-2)

## Continuation 2 · Changes and tests

- **Step budget.** `rooms3/check_step.py` takes `--budget-s`, which defaults to 1,500 s, so local runs are unchanged. The alarm, its message and a new `budget_s` field in `check.json` follow the argument. A budget below 1 s is refused before any output is written.
- **Limits.** `rooms3/checks.py` holds `LIMITS`. The camera child keeps a 1,620 s driver limit. The step child has a 5,400 s budget, a 5,520 s driver limit (budget plus 120 s, as before) and a 7,200 s task limit. The worker passes `--budget-s 5400` between the module name and `--scene`, so the result directory stays the last argument pair. Hand-over keeps its 1,140 s driver and 1,800 s task limits. [Worker](cloudrun/handover/worker.py)
- **Task limit, step only.** The `rooms3-step` execution carries `--task-timeout 7200s`. `gcloud run jobs execute` takes this per-execution override. I confirmed the flag in the installed SDK source. It sits in the GA `Execute` class of `lib/surface/run/jobs/execute.py` (line 99, in `CommonArgs`, which `Args` calls, next to the `--tasks` flag). Line 171 passes it into the overrides, through `AddTaskTimeoutFlags` in `lib/googlecloudsdk/command_lib/run/flags.py`. `gcloud-p` runs `exec gcloud`, which resolves to that SDK in this shell. The job default in `deploy` and `job.yaml.in` stays 1,800 s, so the camera and hand-over executions are unchanged. No new cloud call was added to the launch path. [Operator](cloudrun/handover/ops.py) · [Offline plan with the exact lines](cloudrun/handover/verification/rooms3-c2-plan.txt)
- **Staging.** Four files differ from the Continuation 1 context: `rooms3/check_step.py`, `rooms3/checks.py`, `cloudrun/handover/worker.py` and `layer.json`. The Continuation 2 context has 56 files and 52 layer hashes. [Inventory](cloudrun/handover/verification/rooms3-c2-staged.sha256) · [Context](cloudrun/handover/verification/rooms3-c2-context/layer.json). The hand-over tests now pin this inventory. The Continuation 1 inventory stays as the record of the image that ran.
- **Tests.** Before the change: handover 49 (2 skipped), `test_handover_cloud` 20, `test_rooms3_cloud` 7, rooms3 29 (3 skipped). After the change, all pass:

| Suite | Command, from the phase folder | Result |
|---|---|---|
| Hand-over | `(cd handover && python3 -B -m unittest discover -s tests -p 'test_*.py')` | Ran 49 tests · OK (skipped=2) |
| Cloud kit, mandated | `(cd cloudrun/handover && python3 -B -m unittest test_handover_cloud)` | Ran 21 tests · OK |
| Cloud kit, rooms3 | `(cd cloudrun/handover && python3 -B -m unittest test_rooms3_cloud)` | Ran 9 tests · OK |
| rooms3 | `<home>/ugrp-venv/bin/python -B -m unittest discover -s rooms3/tests` | Ran 33 tests · OK (skipped=3) |

The four new tests are in `rooms3/tests/test_step_budget.py`. Two new cloud tests check the step child's argument and timeouts, and the task-limit override. One hand-over test checks that its execution carries no override. [rooms3 log](rooms3/verification/c2-tests.txt) · [cloud-kit log](cloudrun/handover/verification/rooms3-c2-tests.log). None of these runs touches the cloud, the network or a model.

The three-room experiment inherits the FIX6 choice to set down a held box even when tilted and score its landing. The archived two-room cohorts scored 9/12 and 8/12. Both figures belong to hand-over. [Task and user decision](TASK-ROOMS3.md)

## Main-session cloud commands

Continuation 1 ran this Bash block from the main session. It builds one image, deploys its recorded digest to the existing hand-over job, and runs one task per seed in each requested mode. Each execution uses one parallel task, 2 vCPU, 6 GiB, zero retries and a 1,800 s task limit. Continuation 2 changes the limit for the step mode only, as the rerun below shows. The camera child uses the frozen cameras and survey. The step child uses the image's local ACT grasp actor. Both children use the network-disabled driver path. [Operator](cloudrun/handover/ops.py) · [Worker](cloudrun/handover/worker.py) · [Job definition](cloudrun/handover/job.yaml.in)

```bash
(
  set -eu
  cd <work>/20261123-phase3
  kit="$PWD/cloudrun/handover/ops.py"
  work=$(mktemp -d "$PWD/cloudrun/runs/rooms3-c1-XXXXXXXX")
  printf 'Cohort directory %s\n' "$work"

  python3 -B "$kit" build "$work"
  python3 -B "$kit" deploy "$work"

  run_check() {
    local mode="$1" watch_rc=0 fetch_rc=0
    python3 -B "$kit" run "$work" "$mode" --seeds 0 3 6 || return $?
    python3 -B "$kit" watch "$work" "$mode" || watch_rc=$?
    python3 -B "$kit" fetch "$work" "$mode" || fetch_rc=$?
    (( watch_rc == 0 && fetch_rc == 0 ))
  }
  run_check rooms3-camera
  run_check rooms3-step
)
```

Results appear under `$work/rooms3-camera/results/seed-{0,3,6}/` and `$work/rooms3-step/results/seed-{0,3,6}/`. Each contains `check.json`, the child log and an execution receipt. Camera folders also contain the two ceiling images and each robot's first wrist and decoded-sign images. A failed check keeps its diagnostics. Fetch visits the other seeds and returns a nonzero status for failures or incomplete evidence. To resume, set `work` to the printed cohort directory and repeat the relevant `watch` or `fetch` command. Repeating `run` in that directory with the same mode and seeds reuses the execution receipt. [Collector](cloudrun/handover/fetch.py)

### Continuation 2 rerun (step only)

Use a new cohort; the camera mode is not needed again. The block builds the image from the current context, checks that the staged inventory is the one recorded here, deploys the unchanged 1,800 s job, and runs `rooms3-step` for seeds 0, 3 and 6. The step executions get the 7,200 s task limit from the operator. [Operator](cloudrun/handover/ops.py) · [Offline plan with the exact execute lines](cloudrun/handover/verification/rooms3-c2-plan.txt)

```bash
(
  set -eu
  cd <work>/20261123-phase3
  kit="$PWD/cloudrun/handover/ops.py"
  # Preflight: stop before the paid build if this SDK does not accept the per-execution task limit.
  gcloud-p <project-id> run jobs execute --help | grep -q -- --task-timeout
  work=$(mktemp -d "$PWD/cloudrun/runs/rooms3-c2-XXXXXXXX")
  printf 'Cohort directory %s\n' "$work"

  python3 -B "$kit" build "$work"
  cmp "$work/build/staged.sha256" "$PWD/cloudrun/handover/verification/rooms3-c2-staged.sha256"
  python3 -B "$kit" deploy "$work"

  run_check() {
    local mode="$1" watch_rc=0 fetch_rc=0
    python3 -B "$kit" run "$work" "$mode" --seeds 0 3 6 || return $?
    python3 -B "$kit" watch "$work" "$mode" || watch_rc=$?
    python3 -B "$kit" fetch "$work" "$mode" || fetch_rc=$?
    (( watch_rc == 0 && fetch_rc == 0 ))
  }
  run_check rooms3-step
)
```

Results appear under `$work/rooms3-step/results/seed-{0,3,6}/`, as in Continuation 1. The job has parallelism 1, so the three tasks run one after another. Expected task wall time is about 5,000 to 6,200 s (1.4 to 1.7 h), or $0.24 to $0.30 at the planning rate. The lower end is 10 requested moves at 3.3 × 150 s with no retries. The upper end uses the 3.75 ratio of seeds 0 and 3 and two retries of 74 s sim each. The hard cap is 3 × 7,200 s = 21,600 s, about $1.04. To resume, set `work` to the printed cohort directory and repeat the `watch` or `fetch` line. [Estimate](#estimate-after-continuation-2)

The Continuation 1 staging directory contains 56 files. Its layer records hashes for 52 runtime files, including the calibration, the three maps and every asset referenced by their MJCF. A native seed-0 camera child ran from these files with the local interpreter and simulator assets. The local test store returned the camera result and every capture byte-for-byte. A staged seed-6 physical-check child reached the missing checkpoint. Fetch returned its failure receipt and both initial boards, then signalled the failed check. The execution IDs and zero image digest identify local fixtures. Deployment and Cloud Storage transfer remain unverified. [Staged inventory](cloudrun/handover/verification/rooms3-c1-staged.sha256) · [Layer](cloudrun/handover/verification/rooms3-c1-context/layer.json) · [Camera transport log](rooms3/verification/c1-local-archive.log) · [Failed-step transport log](rooms3/verification/c1-local-step-archive.log)

## R2 · Measured boards and box moves

The executor resolves all three requests against the same pre-step camera board. It runs motor stages serially within that step, then surveys again. A receiver can request a newly arrived box on the following step. A directed pad has the map's configured capacity. The executor tests occupancy at the step boundary and again just before a door move in case an earlier action dropped a box there. The referee can veto a full pad. The motor policy gets the selected wrist track, colour and destination. [Step executor](rooms3/steps.py) · [Physical stages](rooms3/motors.py)

Both moves use the hand-over wrist approach, ACT grasp and lift witness. Door transfers use a stand 0.31 m inside the sending room, facing the selected pad. Sign placements use the robot's decoded sign corners to choose the final stand. Both use the 87-row release table and ten rest observations. A tilted held box proceeds to release. The referee scores the settled centre against the directed pad or matching sign area and target multiplicity. A missed grasp, dropped box or missed landing retains its measured position. Room guards check every integrated chassis centre. [Board readers](rooms3/board.py) · [Native bindings](rooms3/motors.py) · [Placement tests](rooms3/tests/test_r2.py)

The referee reads simulator body positions, speed, floor clearance and finger forces. Each robot's planner input comes from its own wrist tracks and decoded room sign, with its own ceiling-card pose used to locate the tracks. A missing sign leaves the target list unknown. A missing track stays absent. The comparison pairs same-colour tracks and bodies within the same room solely to measure position error. [Board readers](rooms3/board.py) · [Comparison from the saved sensor observations](rooms3/verification/c1-comparison.json)

| Seed | Initial position error in metres, r1 / r2 / r3 | Native step evidence |
|---|---|---|
| 0 | 0.0544 / 0.0057 / 0.0694 | r1 approached its red box for a door move, displaced 0.772 m and reached wide-face alignment. The probe stopped before grasp at 70.0 simulated seconds. [Receipt](rooms3/verification/c1-step/seed-0/check.json) |
| 3 | 0.0547 / 0.0057 / 0.0694 | r3 approached its red box for a sign move, displaced 0.768 m and reached wide-face alignment. The probe stopped before grasp at 69.5 simulated seconds. [Receipt](rooms3/verification/c1-step/seed-3/check.json) |
| 6 | 0.0544 / 0.0057 / 0.0697 | The full driver completed its survey and exited 2 at the local actor load. [Receipt](rooms3/verification/c1-step/seed-6/check.json) |

Across these nine initial views, the two readers agreed on every room's box and target counts, all four empty pads and zero deliveries. The smallest chassis-to-boundary margin in the two approach probes was 0.806 m. The probes exited 3, the explicit pre-grasp component result. The native runtime reported `STRUCTURAL_ONLY_DYNAMICS_UNCALIBRATED`. [Measurements](rooms3/verification/c1-comparison.json) · [Door approach events](rooms3/verification/c1-step/seed-0/events.jsonl) · [Sign approach events](rooms3/verification/c1-step/seed-3/events.jsonl)

The staged image check requests the following moves. Seed 3's receiver round was added after the local pre-grasp probes and uses the board remeasured after its first round. Each completed round writes both boards, physical witnesses, per-robot status and landed position to `step-1.json` or `step-2.json`. A failed move makes the physical check fail while preserving the evidence. [Check driver](rooms3/check_step.py) · [Fixed requests and acceptance](rooms3/checks.py)

| Seed / round | r1 | r2 | r3 |
|---|---|---|---|
| 0 / 1 | red → r2 | blue → sign | red → r2 |
| 3 / 1 | blue → r2 | red → r1 | red → sign |
| 3 / 2 | red → sign | idle | idle |
| 6 / 1 | red → sign | red → sign | blue → r2 |

Continuation 1 passed 24 workspace scene and step tests and 27 cloud-kit tests. These cover the step barrier, room guard, occupied and opposite pads, missing observations, wrong-body and dropped-box outcomes, target multiplicity, and release from an archived 16.12° hold. The motor-stage tests used scripted effects. The cloud-kit tests used local archive and control-plane fixtures. The two native approach runs and the native camera checks are recorded separately above. [Scene and step tests](rooms3/verification/c1-tests.txt) · [Cloud-kit tests](cloudrun/handover/verification/rooms3-c1-tests.log)

## Estimate after Continuation 2

Measured in the Continuation 1 archive, from the step child's `events.jsonl` (simulated seconds):

- Seed 6 completed three moves in 135.1, 197.5 and 117.4 s, a mean of 150.0 s per move. Each move runs from the previous placement event to its own, and the first from the initial survey at 9.9 s. This is the "about 150 s" of the continuation. The seven completed moves across the three seeds average 136 s (range 107 to 198 s). One of them includes a missed grasp and a second approach, which took 74 s of sim in seed 0.
- The 1,500 s alarm stopped the seeds at 398.7 to 462.8 s of sim. The implied wall-to-sim ratio is 1,500 / sim: 3.24 for seed 6, and 3.75 and 3.76 for seeds 0 and 3. The ratio includes start-up. The archive has no wall-clock stamps, so it cannot be split further. The continuation's 3.3x matches seed 6 only. This section uses 3.3 and cross-checks it against 136 s × 3.57 = 486 s per move, where 3.57 is total wall over total sim (4,500 s over 1,262 s).

Reference plan. The task does not define it. I read it as the shortest plan that starts with the fixed first round in `rooms3/checks.py` and delivers every box. I worked it out by hand from the converted maps. Each seed needs three rounds:

| Seed | Moves | Round 1 (fixed) | Round 2 | Round 3 |
|---|---:|---|---|---|
| 0 | 5 | red r1 → r2 door; blue r2 → sign 12; red r3 → r2 door | red r2 → sign 12 | red r2 → sign 12 |
| 3 | 6 | blue r1 → r2 door; red r2 → r1 door; red r3 → sign 13 | red r1 → sign 11; blue r2 → door 2–3 | blue r3 → sign 13 |
| 6 | 5 | red r1 → sign 11; red r2 → sign 12; blue r3 → r2 door | blue r2 → r1 door | blue r1 → sign 11 |

The motor stages run one after another, so wall time follows the number of moves. A robot with no move in a round costs nothing, so three rounds do not mean three full rounds of wall time. At 3.3 × 150 s = 495 s per move:

| Seed | Moves | Wall time | Compute at $0.000048 per second |
|---|---:|---|---|
| 0 | 5 | 2,475 s (41.3 min) | $0.119 |
| 3 | 6 | 2,970 s (49.5 min) | $0.143 |
| 6 | 5 | 2,475 s (41.3 min) | $0.119 |

At the 3.75 ratio instead, the three episodes take 2,813, 3,375 and 2,813 s, or $0.135, $0.162 and $0.135. The 1,500 s figure includes start-up, which the archive does not time. Over a longer run the start-up is spread thinner, so 3.3 is plausible and 3.75 is the conservative end.

Not included: the survey after each round, which the archive does not time; planner latency; and retries. A retry adds about 245 s of wall time and $0.012. The 7,200 s task limit covers about 14 move attempts at 495 s, and the 5,400 s check budget about 11. The rate is the archived Jobs rate for 2 vCPU and 6 GiB: $0.000018 per vCPU-second plus $0.000002 per GiB-second ([REPORT-HANDOVER-CLOUD.md](REPORT-HANDOVER-CLOUD.md), line 93). Build, storage and model charges are outside this compute estimate.

The earlier estimate of 9.2 to 27.6 minutes and $0.027 to $0.080 assumed 184 s per move, from an idealised donor and receiver split. The archive shows the moves run in series, so that split does not hold and the earlier figures are superseded. [Archived trials](cloudrun/runs/handover-fix4-Zc6HAKV9/trials)

## R1 · Scene and converted maps

The converter reads an enrolled `1x3` board and checks its bytes against the v20 registry manifest. The three examples use `scaled:1`, the three-box density. Seeds 0, 3 and 6 are the first three enrolled seeds with one box in each room. Across these examples every robot starts with each supported paint colour at least once. Other seeds retain their original uneven distributions. The converter preserves the order and multiplicity of box and target tokens in each square. [Converter](rooms3/convert.py) · [Map rules](rooms3/maps.py) · [Source registry](../20261124-chen2d-snap-v20/envs-scaled/r1/1x3/manifest.json)

I mapped source green to red for both boxes and targets. The physical planner would therefore treat two red targets of different source colours as interchangeable. The original source colour of each box, the source hash and the paint mapping are stored in each map. The six-box registry is also supported through `--boxes-per-robot 2`. Paint overrides, room dimensions, door width and pad capacity are converter parameters. Capacity is stored in the scene definition for R2 to enforce. [Example map](rooms3/scenes/seed-0/map.json)

The three 2.65 × 2.70 m rooms share two 1.10 m doors. Each door has two directed, one-box places whose centres are 0.55 m apart. I put one inward-facing ArUco destination sign on the south wall of each room. A sign ID identifies the room's full list of targets, including empty and repeated targets. The three complete MasterPi bodies use the archived FIX4 geometry, wrist optics, actuators and native finger–box contact parameters. Every box has its own free joint. The ceiling reader uses two overlapping views over the 7.95 m row. The portable MJCF refers to bundled mesh and card files by relative path. [Scene builder](rooms3/scene.py) · [Seed 3 MJCF](rooms3/scenes/seed-3/scene.xml)

| Seed | Initial boxes, west to east | Targets at sign 11 | Targets at sign 12 | Targets at sign 13 | Minimum moves | Estimated compute (Continuation 2) |
|---|---|---|---|---|---:|---|
| 0 | red, blue, red | — | blue, red, red | — | 5 | 41.3 min · $0.119 |
| 3 | blue, red, red | red | — | blue, red | 6 | 49.5 min · $0.143 |
| 6 | red, red, blue | blue, red | red | — | 5 | 41.3 min · $0.119 |

![Converted seed 0. All three targets are at sign 12.](rooms3/scenes/seed-0/map.png)

![Converted seed 3. Sign 11 has one red target and sign 13 has blue and red targets.](rooms3/scenes/seed-3/map.png)

![Converted seed 6. Sign 11 has blue and red targets and sign 12 has one red target.](rooms3/scenes/seed-6/map.png)

### Verification

| Evidence | Result |
|---|---|
| Source and generated files | All 16 three-box seeds preserved cell assignments and target multiplicity after colour conversion. The test also converted a six-box map and rejected a changed source hash. Two independent exports of seed 3 matched byte for byte with the same installed software. |
| MJCF structure | Each example contains three robot trees, three free boxes, 30 actuators, 18 explicit finger–box contact pairs and zero equality constraints. All asset references resolved. The tests checked both door openings, both pad directions and all six card textures per scene. |
| Calibrated image fixtures | OpenCV decoded all three ceiling cards in projected tile images and the expected wall sign in all nine projected starting views. The frozen stationary pan and chooser selected all nine box silhouettes from generated wrist-image sequences. These fixtures use ideal projection, flat paint and unoccluded geometry. |
| Archived two-room RGB | The frozen first-frame projection located the physical red and blue donors within 0.0146 m and 0.0152 m of their archived starts. FIX4's identity radius is 0.25 m. The frames came from FIX4 trials 1 and 2. |
| Native three-room RGB, Continuation 1 | MuJoCo 3.16.0 and OpenCV 5.0.0 compiled and rendered all three scenes. All 36 criteria passed across nine robot views. Maximum ceiling-position error was 0.00660 m and maximum yaw error was 0.0832 rad. [Seed 0](rooms3/verification/c1-camera/seed-0/check.json) · [Seed 3](rooms3/verification/c1-camera/seed-3/check.json) · [Seed 6](rooms3/verification/c1-camera/seed-6/check.json) |

The original R1 run passed 14 tests and stopped on a missing MuJoCo import. The main session supplied MuJoCo and OpenCV and reproduced a missing `exec/sim/masterpi_scene.xml` on all three seeds. Continuation 1 used the frozen simulator sources and XML already present under `exec-repo/sim`. In the image the driver selects `$HANDOVER_SCENE_ROOT/sim` and the staged calibration file. The native checker uses the stock wrist-camera remap and JPEG encoder and compares its own selected tracks with ground truth afterwards. [Original tests](rooms3/verification/r1-tests.txt) · [Main-session failures](rooms3/verification/native-main.log) · [Runtime selection](rooms3/runtime.py) · [Native checker](rooms3/check_camera.py)

### Local reproduction

These commands reproduce the continuation tests and the native R1 checks from the three enrolled workspace bundles. The first R1 source-registry test run is recorded above. The C2 manifest covers the Continuation 2 code, captured evidence and test output. It omits `TASK-ROOMS3.md`, which the main session appends to. The C1 manifest still describes the Continuation 1 state, so checking it now reports the files Continuation 2 changed.

```bash
(
  set -eu
  cd <work>/20261123-phase3
  export MUJOCO_GL=osmesa PYOPENGL_PLATFORM=osmesa
  export TMPDIR="$PWD/.tmp" XDG_CACHE_HOME="$PWD/.tmp"
  export OPENBLAS_NUM_THREADS=1 OMP_NUM_THREADS=1 LP_NUM_THREADS=2
  export PYTHONDONTWRITEBYTECODE=1 HANDOVER_SCENE_ROOT="$PWD/exec-repo"
  export PYTHONPATH="$PWD/.tmp/v10-offline:<home>/ugrp-venv/lib/python3.12/site-packages"
  native=<home>/ugrp-render-arm-s-20261027/.venv-mujoco/bin/python
  "$native" -B -m unittest -v rooms3.tests.test_r1.CameraControls \
    rooms3.tests.test_r1.NativeDescription.test_robot_trees_actuators_and_native_contact_pairs \
    rooms3.tests.test_r1.NativeDescription.test_two_doors_four_directed_places_and_room_extents \
    rooms3.tests.test_r1.NativeDescription.test_relative_assets_ceiling_coverage_and_marker_ids \
    rooms3.tests.test_r1.Enrolment.test_manifest_mismatch_is_rejected_without_modifying_source \
    rooms3.tests.test_r2 rooms3.tests.test_r2_motors
  <home>/ugrp-venv/bin/python -B -m unittest discover -s cloudrun/handover -v
  <home>/ugrp-venv/bin/python -B -m unittest discover -s rooms3/tests
  sha256sum --quiet -c rooms3/verification/C2-SHA256SUMS
  camera_out=$(mktemp -d "$PWD/rooms3/verification/camera-rerun-XXXXXXXX")
  for seed in 0 3 6; do
    "$native" -B -m rooms3.check_camera \
      --scene "rooms3/scenes/seed-$seed" --out "$camera_out/seed-$seed"
  done
  approach_out=$(mktemp -d "$PWD/rooms3/verification/approach-rerun-XXXXXXXX")
  for probe in 0:r1 3:r3; do
    seed=${probe%:*}
    robot=${probe#*:}
    rc=0
    "$native" -B -m rooms3.check_step --scene "rooms3/scenes/seed-$seed" \
      --out "$approach_out/seed-$seed" --approach-only "$robot" || rc=$?
    test "$rc" -eq 3
  done
)
```

## 확인 안 됨

Continuation 2 ran nothing in the cloud, made no model call and used no network. In Continuation 1, the native approaches never issued a grasp, because the local `handover/runtime/act` lacked four checkpoint files. The image's own checkpoint is what will run, and this continuation did not inspect it. Not verified yet:

- The 5,400 s budget, the 5,520 s child timeout and the 7,200 s execution limit have not run in Cloud Run. The `--task-timeout` override is confirmed only in the installed SDK source (`execute.py` lines 99 and 171, `AddTaskTimeoutFlags`), not against a live execution.
- The wall-to-sim factor. The continuation's 3.3 matches seed 6 only. The per-seed ratios are 3.24 to 3.76, so a 150 s move takes 486 to 564 s of wall time, against 495 s in the estimate.
- The per-round survey time, planner latency and retry rate of a full episode.
- The image that the main session's `build` stages. The rerun block checks it against `rooms3-c2-staged.sha256` with `cmp` before deploying.
- The reference plan is my reading. The planner's real plans may need more rounds.
- The deployed job's state. The offline plan shows the command lines only.
- The native lines of the local reproduction block (MuJoCo camera and approach checks) were not rerun. The cloud-kit and rooms3 discovery lines were.
- A `--task-timeout` that the live gcloud rejects would fail at `run`, after the build. The reservation folder would then be left without an execution, and that cohort would need a fresh one. The rerun block's preflight stops before the build if the local SDK lacks the flag. It cannot catch a live rejection.

[Continuation 1 checkpoint receipt](rooms3/verification/c1-step/seed-6/check.json) · [Continuation stop condition](TASK-ROOMS3.md#continuation-1-2026-11-25-1740-kst-main-session)

| Package | Pending |
|---|---|
| R1 image run | Camera checks passed inside the image for seeds 0, 3 and 6 in Continuation 1. Nothing further is pending for R1. |
| R2 | The Continuation 1 step checks stopped at the 1,500 s budget after 7 of the 10 requested moves had placed a box. The Continuation 2 rerun (step only, new cohort) is the next physical run; its result is not known. Post-move comparison of referee and perceived boards is still to be read from it. |
| R3 | The stop after R2 leaves the unchanged v20 planner adapter, scripted-fake calls and recorded-plan execution pending. |
| R4 | Episode-level planner failure causes, execution-failure aggregation and the observed delivery score remain pending. |
| R5 | The one-episode job remains pending. Episode time and cost above are projections from the Continuation 1 move times and the two-room archive. |
