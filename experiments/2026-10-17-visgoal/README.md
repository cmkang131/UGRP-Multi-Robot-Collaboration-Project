# visgoal — own-RGB destination visual search (zone B blue), 2026-10-17

Default-off module `sim/visual_goal_search.py` (`visual_goal_search_v1`).
The skill receives only its own raw fisheye RGB, its own issued wheel/servo
commands, and the egocentric landmark memory.  No static map, world pose, spawn
pose, visibility label or zone coordinate enters the controller.  Ground truth
is used only in the arrival verdict and in `eval-only.json`.

## Goal and gate

Find the blue zone-B floor paint without a map, remember it egocentrically, and
arrive inside it.  N=16 fixed starts, eight west of the divider (zone B not
visible at tick 0) and eight east of it (visible or a look-around is needed).
Each episode is capped at 120 SIM s and labelled `cap_end` if the cap is hit.
The report recounts, from raw files: find success n/N, arrival success n/N,
elapsed SIM seconds, and rotation.  Initially-invisible starts are counted from
the tick-0 own-RGB paint pixels, not from a truth label.

Acceptance is reported, not tuned after seeing the result:

* **find** = a metric (<=1.2 m) floor-paint landmark was formed in memory at
  least once (`memory_observation` returned an observation), or the episode
  arrived.
* **arrival declared** = the skill's own on-paint + memory-range test stopped it.
* **arrival verdict (GT, verdict cell only)** = at the declaration tick the
  robot's world pose was inside the authored zone-B rectangle.  It appears only
  as `arrival_verdict_gt_inside_zone_B` in the per-episode verdict, never in a
  controller argument.

## Reuse (byte copies, `vendor/provenance.json`)

| source | commit | used as |
|---|---|---|
| PR #541 `claude/reloc19` | `b73e815f6d93cdf5ec70f8b98267277f7fedf3a3` | `floor_patch` metric paint fit, nominal-fisheye transforms, obstacle detector |
| PR #527 `claude/scene-tex2` | `f710fbafae621f18af460edc268a202951599816` | `scene_colour_boundary.surface_masks` + frozen indigo110_s80 calibration for wall feet |
| PR #574 `codex/egomem1` (egomem2) | `a134260f254a326d8dae96a5a5a11c1b738fca11` | `LandmarkMemory` legacy_v1 (Castellanos old-frame EKF), byte vendor only |
| own-command prior | `15a14b3e5` | exact issued-pulse yaw calibration r2 |

Public navigation primitives are used at the level of relative motion: Nav2
1.4.2 (`3478badb7e2802c9ff1f805fb5493dc1d0792a5a`) Spin signed-relative-yaw
accumulation and DriveOnHeading relative-distance travel.  The look-around is
one full in-place Spin using the calibrated exact pulse.  Wall following follows
Bug2 (Lumelsky & Stepanov 1987) and is bounded to 30 SIM s before handing over
to a lawnmower search.  Frontier exploration (Yamauchi 1997) is not used because
there is no occupancy grid (`static_map_use=none`).

## Behaviour

1. `orient`: if blue paint is already visible, go to `target`; otherwise scan
   one full revolution with one calibrated left pulse per 0.1 s tick.  If paint
   appears during the scan, interrupt and target it.
2. After the scan: if a front wall foot is already within 3.0 m, approach it.
   Otherwise `seek_wall` drives the initial heading for at most 20 SIM s until
   the wall foot enters the <=1.6 m fitted range (the foot is not projectable
   at longer range because it is at the image horizon).  Then follow the wall
   with it on a fixed side.  A missing side wall for 3 ticks opens `gap_cross`
   (forward, 90 deg toward the opening, forward), which is how the divider door
   is crossed.  No door coordinate is used.
3. `east_search`: bounded lawnmower legs (20 ticks, +8 every 4 legs) with left
   turns, interrupted by paint or obstacles.
4. `target` / `approach`: bearing-align with exact pulses, drive by coarse
   range, then use the <=1.2 m `floor_patch` metric fit.  Observation is a
   `destination_zone` point in `LandmarkMemory`; arrival uses on-paint pixels in
   the lower image centre plus the remembered range.  If the paint is lost for
   >2 s, search resumes from memory.

The memory observation format is `ugrp.memory_item.v1` as produced unchanged by
the egomem2 `snapshot()` (`relative_xy_m`, `range_m`, `bearing_rad`, `age_s`,
`radius95_m`, covariance); the coordinator's `center_body_m` naming maps to
`relative_xy_m` in this repository's snapshot.

## Paint appearance calibration (preflight blocker)

The v5 floor is deliberately blue-tinted: its hue is 108, inside `PAINT_HUE['B']`
(104-120).  The inherited `floor_patch` gate (S>=30) therefore called the whole
floor a destination.  Preflight r1 (west start e00) saw 202557 "paint" pixels at
tick 0, declared arrival at spawn, and the GT verdict was false.  Runner-accurate
frames rendered on gcp3 with the arm held (the same setup as the loop) showed:

* west/no-zone floor: band saturation p50 66-70, p99 74-77, max 196 (a few
  isolated specular pixels); largest accepted component 0 at S>=110;
* east-away e10: band max 99, no component;
* east-visible e13: paint S p50 128, 29859 band pixels at S>=110, 28856 px
  after the 3x3 opening, one component.

The calibrated gate is `PAINT_SATURATION_MIN=110`.  `floor_patch` is still used
as the metric fit, but only inside the accepted component via
`clear=component_clear(px)`; no fit is attempted without a visible paint
component.  Evidence and frame hashes are in
`calibration/paint_saturation.json` with the two boundary frames
(`e00-west-no-zone.jpg`, `e13-east-zone-visible.jpg`).  This is an appearance
constant only; no zone coordinate or visibility label is used.

## Files

* `setups.json` — 16 fixed starts (setup only; includes parked
  r2/r3 poses to keep the other two robots out of the route).
* `scripts/visgoal_probe.py` — MJWarp runner: 10 Hz render -> raw fisheye ->
  paint/wall/obstacle detection -> memory -> control -> command tape.
* `vendor/` — byte copies; no egomem-owned file is edited.
* Raw outputs stay on gcp3 under `/home/ugrp/ugrp-sim/runs/visgoal-*`; only
  summaries, funnels, montages and failure frames are copied to the Mac.

## Reproduction

```bash
python3 scripts/check_current_stack.py experiments/2026-10-17-visgoal/queue-preflight.json \
  --flow self_map --output experiments/2026-10-17-visgoal/stack-preflight-v4.json
python3 scripts/visgoal_probe.py --enabled --preflight --episodes 0,13 --sim-cap 60 \
  --queue experiments/2026-10-17-visgoal/queue-preflight.json \
  --renderer /home/ugrp/ugrp-sim/src/16a946ff3 \
  --legacy /home/ugrp/ugrp-sim/src/warp8f-selfmap-0ace43f25 \
  --setups /home/ugrp/ugrp-sim/src/<clone>/experiments/2026-10-17-visgoal/setups.json \
  --output /home/ugrp/ugrp-sim/runs/visgoal-preflight-r2
```

`--enabled` is mandatory; the module's default constructor option is `off`.
The runner refuses any host other than `ugrp-act-l4-gcp3`, requires the
worker's own lease file, and checks every pinned input hash.

## Constraints

`static_map_use=none`, `localization_initial_prior=none`,
`goal_discovery=visual_search`, `held_world_reads=0`,
`invisible_measurements=0`, `top_camera_control=false`, weld off,
`noslip_iterations=0`, `warp_native_contact_v1`, `mjwarp_batch_v1`, scene
`walls_floor_contrast_v5_indigo110_s80`.  No LLM/API call is made in this study.
