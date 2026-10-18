# Cross-room carry — Stage A (unloaded) : west pickup room -> divider door -> zone B

[![](https://img.shields.io/badge/powered_by-dsh-4D6BFE?style=flat-square&logo=deepseek&logoColor=white)](https://github.com/deepseek-ai/deepseek-harness)

Status: **Stage A executed; Stage B pre-registered** (2026-10-18). This record
holds the pre-registration, execution and analysis pipeline for Stage A
(unloaded) and the Stage B (loaded arrival) pre-registration. B+ (release/GT
delivered) remains out of scope.

## Mission framing and scope

The mission-level task is "pick up a box in the west pickup room, carry it
through the 0.50 m divider door, and arrive in a destination zone on the east
side". This experiment measures only the **unloaded navigation half**:

| split | measured by this record |
|---|---|
| start west of the divider, cross the 0.50 m door | `door_crossed`, lateral offset, min jamb gap |
| after crossing, find zone B with own RGB only | `post_cross_colour_seen`, `post_cross_found` |
| arrive in zone B | `arrived_declared`, eval-only `gt_inside`, zone margin |
| carry/keep the cargo | **not measured** (Stage B; ACT grasp/release not verified) |

So a Stage A success is **not** a full-mission success: no cargo is grasped,
held or released, and no held-object world pose is read by any control path.
Results are not pooled with visgoal gate r4/B/C, egonav gate-09 or any ACT
run (different starts, stage and 180 s cap). The previous visgoal runs (no
cargo, 120 s cap, 8 west + 8 east starts) are used only as the prior funnel
and as the reason this gate exists: in visgoal B the west side crossed 6/8
but found zone B after crossing 0/6 (`experiments/2026-10-17-visgoal/`,
candidate B section). The candidate C gate then showed that the C arrival
aim change breaks the declaration test (found 9/16, declared 0/16; see
`experiments/2026-10-17-visgoal/` candidate C section), so Stage A keeps C's
expanding search but reverts the arrival aim to the r4/B declaration. That
separation is pre-registered here before this gate runs.

## Pre-registration (condensed §3-4)

* **Destination**: zone B (blue floor paint), eval-only rectangle
  x 4.30-4.90, y -2.80..-1.40. The door is `door_1` at [2.20, 0.05], width
  0.50 m, opening y [-0.20, 0.30]. Map `zone_wide_door_geometry_v3`, scene
  `s1_normal_mixed_v7` **full scene** (cargo boxes and the long_beam at
  [1.275, 0.45] remain as obstacles), scene profile
  `walls_floor_contrast_v5_indigo110_s80`, host `ugrp-act-l4-gcp3`.
* **Starts**: 16 starts, all west of the divider (`setups.json`). Group N =
  8 near-wall starts (new, setup-validated before the gate), group F = 8
  far-side starts reusing the visgoal west e00-e07 coordinates. Both peer
  robots are parked at (5.15, 1.20) and (5.15, -2.85) (setup/eval only).
* **Execution**: MJWarp `nworld=16` batch, `sim_cap_s=180`, 1200->1800 control
  ticks at 10 Hz; `cap_end` is a separate termination label, never a
  rejection reason. Physics `warp_native_contact_v1`, noslip 0, weld off.
* **Policy (two separated toggles)**: the search half of the vendored visgoal
  candidate C build (`sim/visual_goal_search.py` @ policy source `c390105c2`,
  PR #582 draft) is used with `visgoal_expanding_search_v1=on`
  (expanding lawnmower `20/344/60/300/60` ticks, own-RGB full spin, Bug2 wall
  following, gap crossing); the arrival half stays at the gate r4/B
  declaration (`visgoal_arrival_aim_inset_v1=off`, arrival aim inset 0).
  Rationale (measured, not tuned): the candidate C gate on 2026-10-18/19
  produced found 9/16 but **arrived_declared 0/16** — all eight east episodes
  ended physically inside zone B (eval-only) but never declared, because the
  C-only 0.142 m aim inset caused a near-field paint loss ->
  `local_reacquire_spin` loop. Both toggles are read from the queue and
  recorded in `stack.json`; the vendored policy bytes are unchanged. The
  search schedule and the 180 s cap are the pre-registered hypothesis, not a
  measured optimum, and are not tuned after seeing this gate's result.
* **Control inputs only**: own raw fisheye RGB, issued wheel/servo commands,
  egocentric memory items. No static map, world pose, spawn pose, zone/door
  coordinate, top camera or truth enters the controller.
* **Input audit (actual, not constants)**: every controller call
  (`skill.control`, `memory_observation`, `memory.step`) goes through
  `controller_boundary_v1` (in `scripts/crossroom_probe.py`): its argument
  dicts are scanned for gt_/world/static_map/spawn/top_camera/
  invisible_measurement keys, detections are counted in the episode record and
  the episode fails as `input_audit_fail`. The visgoal/egonav runner wrote
  those zeroes as constants; this flow counts actual boundary attempts.

### Funnel (sequential, reported n/N, never pooled)

```
requested_n16
-> input_audit_zero
-> start_valid            (setup admission)
-> door_crossed           (eval-only crossing with y inside the opening)
-> post_cross_colour_seen (own RGB, after the crossing tick)
-> post_cross_found       (metric <=1.2 m paint landmark, after crossing)
-> arrived_declared       (skill's own arrival test)
-> gt_inside              (eval-only base xy inside zone B at the declared tick)
```

`cap_end` is reported separately. There is no pass/fail success-rate threshold
in Stage A: it is a measurement gate. Per the pre-registration draft, Stage B
is only opened if `door_crossed != 0` and `post_cross_found != 0`; that is a
logical precondition, not a tuned threshold.

### Metrics

`door_crossed`, `door_cross_t_s`, `door_lateral_offset_m`,
`door_min_jamb_gap_m`, `post_cross_colour_seen`, `post_cross_found_t_s`,
`found_any_pre_cross_reference_only`, `arrived_declared`, `declared_t_s`,
`gt_inside`, `gt_zone_margin_m`, `gt_post_cross_zone_distance_m`,
`time_to_cross_s`, `time_to_declare_s`, `collision_events` (recorded as
`not_measured` unless the runner records contacts; it is not inferred),
`cap_end`, batch wall and `wall/(sim_s*nworld)`. Truth is read only in
eval-only/verdict/analysis cells.

## Files

* `prereg.json` — frozen pre-registration (funnel, metrics, constraints,
  input-audit definition, no-pooling, prior funnel).
* `setups.json` — 16 west starts (N01-N08, F01-F08) plus peer parks.
* `queue-stageA.json` — gate queue with the policy source pin, stack values
  and 19 pinned input sha256; `make_queue.py` regenerates it.
* `stack-stageA.json` — `scripts/check_current_stack.py --flow self_map`
  admission receipt (ok: true, admission: pass).
* `scripts/crossroom_probe.py` — Stage A MJWarp nworld=16 runner (adapted
  from the visgoal runner pattern; vendored policy registration, boundary
  input audit, eval-only outputs, `cap_end`).
* `scripts/crossroom_setup_check.py` — setup-only validator: builds the scene
  once, resets every start, reports sim admission plus beam/cargo/park
  clearances. Output `setup-validation.json` is committed before the gate.
* `scripts/crossroom_recount.py` — independent raw recount: door metrics from
  eval-only poses, post-cross funnel, rejection table, speed.
* `vendor/` — byte copies with `provenance.json` (visgoal candidate C policy,
  paint/wall masks, metric paint fit, command prior, landmark memory, MJWarp
  core/scene/native contact).
* Raw outputs stay on gcp3 under `/home/ugrp/ugrp-sim/runs/crossroom-*`.

## Run commands (gcp3, after the freeze commit)

```bash
# 0) stack admission (committed before the run)
python3 scripts/check_current_stack.py \
  experiments/2026-10-18-crossroom-carry/queue-stageA.json \
  --flow self_map --output experiments/2026-10-18-crossroom-carry/stack-stageA.json

# 1) setup-only validation (no rollout)
python3 experiments/2026-10-18-crossroom-carry/scripts/crossroom_setup_check.py \
  --renderer /home/ugrp/ugrp-sim/src/16a946ff3 \
  --legacy /home/ugrp/ugrp-sim/src/warp8f-selfmap-0ace43f25 \
  --setups experiments/2026-10-18-crossroom-carry/setups.json \
  --output experiments/2026-10-18-crossroom-carry/setup-validation.json

# 2) preflight (2 starts, 60 Sim s, nworld=2)
python3 experiments/2026-10-18-crossroom-carry/scripts/crossroom_probe.py \
  --enabled --stage A_unloaded --preflight --episodes 0,8 --sim-cap 60 --nworld 2 \
  --lease-name crossroom-stageA-preflight \
  --queue experiments/2026-10-18-crossroom-carry/queue-stageA.json \
  --renderer /home/ugrp/ugrp-sim/src/16a946ff3 \
  --legacy /home/ugrp/ugrp-sim/src/warp8f-selfmap-0ace43f25 \
  --setups experiments/2026-10-18-crossroom-carry/setups.json \
  --output /home/ugrp/ugrp-sim/runs/crossroom-stageA-preflight

# 3) gate (16 starts, 180 Sim s, nworld=16)
python3 experiments/2026-10-18-crossroom-carry/scripts/crossroom_probe.py \
  --enabled --stage A_unloaded --sim-cap 180 --nworld 16 \
  --episodes 0,1,2,3,4,5,6,7,8,9,10,11,12,13,14,15 \
  --lease-name crossroom-stageA \
  --queue experiments/2026-10-18-crossroom-carry/queue-stageA.json \
  --renderer /home/ugrp/ugrp-sim/src/16a946ff3 \
  --legacy /home/ugrp/ugrp-sim/src/warp8f-selfmap-0ace43f25 \
  --setups experiments/2026-10-18-crossroom-carry/setups.json \
  --output /home/ugrp/ugrp-sim/runs/crossroom-stageA

# 4) independent recount + rejection table (VM CPU)
python3 experiments/2026-10-18-crossroom-carry/scripts/crossroom_recount.py \
  /home/ugrp/ugrp-sim/runs/crossroom-stageA \
  --output /home/ugrp/ugrp-sim/runs/crossroom-stageA/recount.json
```

## Constraints

`static_map_use=none`, `localization_initial_prior=none`,
`goal_discovery=visual_search`, `held_object_hidden_v1=true`,
`held_world_reads` audited at the controller boundary, weld off,
`top_camera_control=false`, `noslip_iterations=0`, `warp_native_contact_v1`,
`mjwarp_batch_v1`, scene `walls_floor_contrast_v5_indigo110_s80`, no LLM/API
calls. The map/door/zone/spawn values are setup and eval-only; they are never
handed to the controller.

## Stage B (loaded) — pre-registration

Stage B is a separate condition from Stage A: the same map, door and zone B,
but the solo robot starts **already holding one red box** (0.030 kg,
34x40x32 mm) and the scene is the default-off reduced scene
`crossroom_carry_scene_v1` (single red box, no long_beam, end-color profile
off). The cap is 180 Sim s, `nworld=16`, host gcp3; **results are never pooled
with Stage A** or with any visgoal/egonav/ACT run.

* `prereg-stageB.json` — frozen pre-registration (loaded funnel, metrics,
  input audit, no-pooling, prior funnel = Stage A recount).
* `crossroom_carry_scene_v1.json` — reduced single-box scenario (default off;
  only the Stage B queue turns it on).
* `scripts/carry_state_own.py` — own-RGB + own-command cargo monitor
  (`held`/`uncertain`/`lost`); no world pose, no contact flag, no truth.
* `scripts/stageB_settle_check.py` — setup-only loaded-start validator: the
  box free joint is placed at the r1 grip site with the calibrated SEARCH
  joints and the gripper commanded closed (1500 pulse), then the CPU solver
  settles 1 Sim s. 16/16 starts keep the box at the gripper site
  (`setup-validation-B.json`). No weld and no teacher after t=0.
  Start admission (`start_valid`) is evaluated on the authored start state
  before the loaded placement; the loaded grasp intentionally touches the box,
  so a loaded-state overlap check is reference-only and the loaded validity is
  established by the settle check plus the preflight carry monitor.
* Loaded funnel: requested_n16 -> input_audit_zero -> start_valid ->
  cargo_held_own_at_start -> door_crossed -> cargo_held_own_at_cross ->
  post_cross_colour_seen -> post_cross_found -> arrived_declared ->
  cargo_held_own_at_arrival -> gt_cargo_in_zone. `cap_end` is a separate
  label; `gt_delivered` is B+ only (`not_measured` here).
* Mission success definition for this stage: `arrived_declared` AND
  `gt_cargo_in_zone_at_declared` AND `cargo_held_own_at_arrival == held`.
  This is **loaded arrival**, not full-mission delivery: grasp is a setup-only
  initial state and release is out of scope (B+ after an ACT release gate).
* Run commands: `queue-stageB.json`, `stack-stageB.json`,
  `--stage B_loaded --sim-cap 180 --nworld 16`, output
  `/home/ugrp/ugrp-sim/runs/crossroom-stageB`.

Status: **executed (FAIL, loaded baseline); see Stage B results below**. Stage B is a separate condition and is not
pooled with Stage A. It uses the **same search/gap/door policy as Stage A with
no fixes**: the Stage A failure modes (skill-claimed gap crossing without a GT
crossing, jamb overlap on the single GT crossing, declaration just outside
zone B, near-field blue end-band false paint hints) are expected to carry over
unchanged, so Stage B is the loaded **baseline** measurement, not a fix. See
`prereg-stageB.json` `stage_a_carryover`.

## Stage A results (16 starts, 180 Sim s, nworld=16)

Raw VM `/home/ugrp/ugrp-sim/runs/crossroom-stageA`; copied summary, strict
recount, 16 9-frame self-camera montages and SHA256SUMS under `stageA/`.
Executed from freeze commit `bc84e35cf` (branch `claude/crossroom-carry`) with
queue `queue-stageA.json`; `EXIT` DONE, no HOST_ERROR. Batch wall 8772.13 s
for 180 SIM s x 16 worlds = **3.046 wall/(sim_s*nworld)** (record-only speed
gate); the first-30-SIM check could not use a `progress.json` t=30 record
because no episode ended that early, so the only available first-30-SIM
number is a **frame-mtime estimate** 1401.6/(30*16) = 2.92 (not a
progress-record measurement; labelled as such).

Recounted funnel (raw trace/eval-only; 0 mismatches):
`requested_n16 16 -> input_audit_zero 16 -> start_valid 16 -> **GT door_crossed
1** -> post_cross_colour_seen 1 -> post_cross_found 1 -> arrived_declared 1 ->
gt_inside 0`. `cap_end` 13/16 (separate label, not a failure reason); two
episodes ended `STOPPED_NO_ARRIVAL`; one false arrival (declared outside zone).

| ep | grp | status | skill gap_cross claim | GT door crossed | t_cross s | lateral m | jamb gap m | post-cross colour | post-cross found | declared | GT-inside | GT margin m | final (x,y) | final stage |
|---:|---|---|---|---|---:|---:|---:|---|---|---|---:|---:|---|---|
| 0 | N | cap_end | yes | no | - | - | - | no | no | no | - | - | 1.32,0.32 | leg_forward |
| 1 | N | cap_end | no | no | - | - | - | no | no | no | - | - | 0.81,-1.26 | approach_wall |
| 2 | N | ARRIVED_DECLARED | no | yes | 55.2 | -0.1634 | -0.1084 | yes | yes | yes | no | -0.0281 | 4.27,-1.57 | approach |
| 3 | N | cap_end | yes | no | - | - | - | no | no | no | - | - | 0.72,-1.29 | leg_forward |
| 4 | N | cap_end | yes | no | - | - | - | no | no | no | - | - | 0.62,-2.17 | leg_forward |
| 5 | N | cap_end | no | no | - | - | - | no | no | no | - | - | 1.2,0.14 | approach |
| 6 | N | STOPPED_NO_ARRIVAL | yes | no | - | - | - | no | no | no | - | - | 1.26,0.52 | approach |
| 7 | N | STOPPED_NO_ARRIVAL | no | no | - | - | - | no | no | no | - | - | 0.77,1.09 | leg_forward |
| 8 | F | cap_end | yes | no | - | - | - | no | no | no | - | - | 0.88,-0.31 | leg_forward |
| 9 | F | cap_end | no | no | - | - | - | no | no | no | - | - | 0.48,0.15 | approach_wall |
| 10 | F | cap_end | yes | no | - | - | - | no | no | no | - | - | -0.37,0.32 | leg_forward |
| 11 | F | cap_end | no | no | - | - | - | no | no | no | - | - | 0.48,0.49 | leg_forward |
| 12 | F | cap_end | yes | no | - | - | - | no | no | no | - | - | 1.32,0.28 | leg_forward |
| 13 | F | cap_end | no | no | - | - | - | no | no | no | - | - | -0.1,-0.59 | approach_wall |
| 14 | F | cap_end | yes | no | - | - | - | no | no | no | - | - | -0.05,0.97 | leg_forward |
| 15 | F | cap_end | yes | no | - | - | - | no | no | no | - | - | -0.18,1.04 | leg_forward |

Key facts:

* **The skill's own "gap crossed" claim and the GT door crossing disagree.**
  Nine episodes (e00,03,04,06,08,10,12,14,15) reached a `gap_cross`/
  `gap_forward` stage, and **all nine had no GT door crossing**: their
  eval-only base x stayed below 2.175 while the skill ran `east_search` in the
  pickup room (eight after an `approach_wall` phase, e15 via
  orient->follow_north->gap_cross). The only GT crossing is e02/N03, and it
  did not claim `gap_cross` at all. So the false-gap trigger is 9/9 of the
  gap claims. This is the dominant failure mode of Stage A and it also
  explains the earlier visgoal mission split: the "crossed" column there was
  the skill's stage claim, not a GT crossing. (Independent verifier recount,
  2026-10-18: headline matched; the three text corrections are folded in
  below.)
* **The single GT crossing was not a clean door passage.** e02 crossed at
  t=55.2 s with base lateral offset -0.1634 m and minimum jamb clearance
  **-0.1084 m** (the 0.39 m robot body overlaps the jamb envelope by ~10.8 cm
  at the crossing ticks); it then found the paint (the metric paint bbox on
  the zone-B floor appears at t=64.9 s) and declared arrival at
  **t=77.1 s** (episode `sim_s` 78.0) with the base **0.0281 m outside zone
  B** at the declared tick - the same stop-margin geometry as visgoal gate
  r4/B (see the 0.10 m tolerance note there). The
  door-passage budget for an unloaded robot is +/-0.055 m, so any clean
  passage needs a lateral-offset control that this policy does not have.
* **No post-crossing destination search success.** Only e02 saw zone-B colour
  after crossing; every other episode never physically reached the east room.
  Four episodes claim `found`, but three of them are confirmed false paint
  hints: e05 at t=30.6 s, e06 at t=88.8 s and e07 at t=4.3 s all fit their
  metric paint bbox exactly on the **blue end band of the green long_beam**
  at [1.275, 0.45] (independent verifier check), and none of the three had a
  GT crossing. e02's bbox is the only one on the zone-B blue floor.
* Montages (all 16, 9 self-camera frames each, ticks 0..1800 or last) show the
  robots circling cargo cubes in the pickup room, or facing the long_beam
  (e05/e06/e09/e14) - there is no blocked-object claim beyond that; the
  ledger keeps `not_observed`/`not_measured` for gaps.
* Input audit (actual controller-boundary counters) passed 16/16; start
  admission 16/16; no truth/world/static-map/top-camera key reached a
  controller call. `collision_events` is `not_measured` (the raw does not
  carry contact events); the -0.1084 m jamb clearance of e02 is the only
  direct evidence of a jamb interaction.
* **Stage A verdict: FAIL under the mission framing** (GT door crossing 1/16,
  GT-inside 0/16). The failure is upstream of destination search: the
  gap/door crossing trigger and the door alignment. Next-fix direction from
  this table: (1) make the gap trigger require the divider wall faces on both
  sides / a clear door opening, so a lost wall foot cannot start an
  east_search in the pickup room; (2) add door-center lateral alignment
  (measured -0.163 m vs the +/-0.055 m budget) before crossing; (3) reject
  near-field blue end-bands (beam) as destination paint; (4) only then the
  post-cross search range fix carries over from the visgoal table.
* Scope: this stage measures the unloaded destination search on the far side.
  No cargo is grasped, carried or released; Stage B is a separate condition
  and no result is pooled with Stage A.

### Stage A rejection ledger (per-episode)

Reason categories: `cap_end` 13 (separate label), `door_not_crossed` 2
(`STOPPED_NO_ARRIVAL`), `false_arrival_outside_zone` 1 (e02: GT margin
-0.0281 m). `blocked_object` is `not_observed` and `minimum_gap_m` is `null`
with `gap_status: not_measured` for all rows except that e02 records the
measured jamb clearance above. Full per-episode ledger with evidence paths in
`stageA/recount.json` (rejection_table block).


### Stage B results (loaded, single red box, 16 starts, 180 SIM s)

Raw VM `/home/ugrp/ugrp-sim/runs/crossroom-stageB`; copied summary, strict
recount, 16 9-frame montages and SHA256SUMS under `stageB/`. Executed from
freeze commit `868236f55`; `EXIT` DONE, no HOST_ERROR. Batch wall 8229.22 s
for 180 SIM s x 16 worlds = **2.857 wall/(sim_s*nworld)**; the first-30-SIM
number is a **frame-mtime estimate** 1372.81/(30*16) = 2.86 (all episodes ran
to the cap, so no progress t=30 record exists).

Recounted loaded funnel (raw trace/eval-only; 0 mismatches):
`requested_n16 16 -> input_audit_zero 16 -> start_valid 16 ->
**cargo_held_own_at_start 16** -> **GT door_crossed 0** ->
cargo_held_own_at_cross 0 -> post_cross_colour 0 -> post_cross_found 0 ->
arrived_declared 0 -> cargo_at_arrival 0 -> gt_cargo_in_zone 0`.
`cap_end` 16/16 (separate label). Loaded Stage B did not reach the door.

| ep | grp | status | skill gap_cross claim | GT door crossed | cargo held (own) | box final (x,y) | base final (x,y) |
|---:|---|---|---|---|---|---|---|
| 0 | N | cap_end | yes | no | held | -0.69,-0.06 | -0.67,0.08 |
| 1 | N | cap_end | yes | no | held | 0.87,-2.16 | 0.76,-2.08 |
| 2 | N | cap_end | yes | no | held | 0.65,0.88 | 0.69,0.74 |
| 3 | N | cap_end | yes | no | held | -0.4,-2.33 | -0.45,-2.2 |
| 4 | N | cap_end | yes | no | held | -0.57,0.74 | -0.5,0.87 |
| 5 | N | cap_end | yes | no | held | 1.77,-2.25 | 1.66,-2.33 |
| 6 | N | cap_end | yes | no | held | 0.14,-0.15 | 0.23,-0.25 |
| 7 | N | cap_end | yes | no | held | 0.47,0.68 | 0.61,0.73 |
| 8 | F | cap_end | yes | no | held | 0.53,-2.72 | 0.44,-2.61 |
| 9 | F | cap_end | yes | no | held | 1.58,-2.54 | 1.47,-2.45 |
| 10 | F | cap_end | yes | no | held | 1.79,-2.35 | 1.65,-2.31 |
| 11 | F | cap_end | yes | no | held | 0.41,-0.69 | 0.29,-0.62 |
| 12 | F | cap_end | yes | no | held | 0.43,0.28 | 0.54,0.37 |
| 13 | F | cap_end | yes | no | held | 0.64,-2.12 | 0.53,-2.22 |
| 14 | F | cap_end | yes | no | held | 0.96,-2.46 | 0.82,-2.48 |
| 15 | F | cap_end | yes | no | held | -0.23,-2.21 | -0.29,-2.08 |

Key facts:

* **The box is physically carried for the whole episode.** The own-evidence
  monitor reports `held` for all 1801 ticks in 16/16 episodes (28,816 /
  28,816 ticks)
  (own RGB + closed-gripper command history), the box final pose stays at the
  gripper site (base->box distance ~0.14 m), and no episode lost the box. The
  setup-only loaded start (closed jaws, 1 Sim s CPU settle, no weld) held
  through wall following and 180 s of driving.
* **The skill's gap claim is 16/16 false and the GT door crossing is 0/16**
  (Stage A: 9 false claims and 1 GT crossing). Every episode followed the
  wall north, entered `gap_cross` at 34.5-83.2 s in the pickup room, turned
  into `east_search`, and stayed west of the divider until the cap.
* **Loaded-condition cause (correlation + frames + code conditions; no
  counterfactual run):** the carried red box renders as a full-width
  near-field band at the bottom of the own-RGB frame (visible in every checked
  montage). In this run `obstacle_avoid` events are **0** (Stage A: 4,736);
  obstacle detections total **657 ticks** across the 16 episodes vs 15,183 in
  Stage A, and **0 ticks on e00 specifically** (Stage A e00: 859). The
  wall-point zero share is **3.75% across the 16 episodes** (e00 3.3%;
  Stage A e00 1.7%) versus **2.37% for Stage A overall**. This is a
  correlation with the occluding box, the montages and the code conditions -
  **not a counterfactual result**. At the e00 gap claim (t=51.6 s) the raw
  trace shows `walls=418` and `obstacles=[]`, so the wall-zero state was not
  itself the trigger at that instant; the `_follow` 3-tick `side_pt is None`
  path is in the code, but the trace does not store side-point counts, so the
  exact trigger cannot be reconstructed from the raw. A held-box-mask on/off
  counterfactual is planned as a separate loaded condition (fix design item 5)
  and was not run here.
* No post-cross colour, found, declaration or cargo-in-zone is possible
  without a crossing; the loaded run says nothing about destination search
  beyond confirming the carry-over gap/alignment failure.
* Input audit (actual controller-boundary counters) 16/16. `start_valid`
  16/16 is the **pre-load authored start** admission; a reference
  loaded-state overlap check was rejected (8 contacts, min gap -1.1646 mm)
  because the closed jaws touch the box by design, which the prereg records
  as the expected semantics. `collision_events` `not_measured` (raw has no
  contact events). Independent verifier: headline counts matched; this
  section carries the corrected stage label (`B_loaded`), the e00-specific
  wall-zero/obstacle framing, the causal wording above and the admission
  semantics.
* Montages: representative set e00,e02,e04,e06,e08,e10,e13,e15 (9 self-camera
  frames each, ticks 0..1800) was opened; all show the red box band at the
  bottom and pickup-room wandering. Full 16-montage set with hashes in
  `stageB/montages.json`.
* **Stage B verdict: FAIL under the mission framing** (GT door crossing 0/16,
  arrived_declared 0/16, gt_cargo_in_zone 0/16). This is the loaded baseline
  with the unchanged Stage A policy; the box-occlusion finding is the
  Stage B-specific addition to the fix list. Not pooled with Stage A or with
  the crossroom-stageA-fix candidate.

## crossroom-stageA-fix (candidate, default off)

A separate candidate fixes the four Stage A failure modes and is **not pooled**
with Stage A or Stage B. Code, prereg and queue are committed; execution runs
after the Stage B gate.

* `FIX_DESIGN.md` — evidence -> fix mapping (gap two-sided confirmation, door
  lateral alignment, blue end-band rejection, contact recording).
* `scripts/vgs_fix.py` — subclass overrides only: `crossroom_gap_twosided_v1`
  (same-side front wall face <=1.6 m + >=12 tracked side-wall ticks before a
  gap; otherwise `gap_rejected_front_missing`) and
  `crossroom_door_align_v1` (two-jamb lateral estimate, small calibrated turns,
  no forward motion while |offset| > 0.02 m).
* `scripts/paint_area_filter.py` — `crossroom_paint_area_v1`: rejects colour
  components whose metric ground extent is below `PAINT_MIN_EXTENT_M = 0.15 m`
  (beam end band 0.054 m diagonal; zone side >=0.30 m).
* `scripts/contact_recorder.py` — `crossroom_contacts_v1`: eval-only MJWarp
  contact counts / geom categories (`nacon` + `contact.geom/worldid`), with
  `layout_unknown` instead of guessing if the layout differs.
* `prereg-stageA-fix.json`, `queue-stageA-fix.json` (180 Sim s, nworld=16,
  16 west starts), `stack-stageA-fix.json` (admission pass).
* Fix metrics on top of the Stage A funnel: false gap claims, gap
  rejected/confirmed counts, door-align turns, paint rejections, contact
  ticks/events; GT crossing lateral offset and min jamb gap stay eval-only.

Produced with [DeepSeek Harness](https://github.com/deepseek-ai/DeepSeek-Harness)
(dsh). Badge above; PR attribution follows the repository `dsh-badge` format.
