# Cross-room carry — Stage A (unloaded) : west pickup room -> divider door -> zone B

[![](https://img.shields.io/badge/powered_by-dsh-4D6BFE?style=flat-square&logo=deepseek&logoColor=white)](https://github.com/deepseek-ai/deepseek-harness)

Status: **frozen, run pending** (2026-10-18). This record is the pre-registration
and the execution/analysis pipeline for Stage A only. Stage B (loaded arrival)
and B+ (release/GT delivered) are separate future gates and are not run here.

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

## Results

Pending. This section will carry the raw VM path, Mac evidence path, sha256
list, the recounted n/16 funnel, per-episode rejection table (reason
category, blocked object, minimum gap; `not_observed`/`not_measured` kept
explicit) and failure-frame montages. Stage A is not pooled with Stage B or
with the visgoal/egonav/ACT runs.

Produced with [DeepSeek Harness](https://github.com/deepseek-ai/DeepSeek-Harness)
(dsh). Badge above; PR attribution follows the repository `dsh-badge` format.
