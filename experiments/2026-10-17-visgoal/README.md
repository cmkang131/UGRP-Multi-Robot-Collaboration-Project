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
   `destination_zone` point in `LandmarkMemory`.  The target is the **freshest**
   snapshot (not the smallest range: a failed association after a large spin
   created a stale 0.33 m ghost).  Arrival requires a fresh (<=1 s) target and
   drives to the remembered point itself (range <=0.10 m), because the visible
   patch median can be only ~0.18 m inside the near edge; stopping 0.25-0.55 m
   short left the base outside the authored zone.  If the paint is lost for
   >2 s within 1.2 m, a bounded in-place Spin reacquires it before search
   resumes from memory.

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

## Preflight r3/r4 (stage probe, not the gate)

Two starts: setup 0 (west, destination not visible at tick 0) and setup 13
(east, 28856 paint px at tick 0).  r3 is the signed-turn + wall-seek build; r4
adds fresh-memory target choice and the drive-to-patch-point arrival.

| run | episode | start vis px | found | declared | GT inside | sim s | final eval-only x,y | status |
|---|---|---|---:|---:|---:|---:|---|---|
| r3 | e00/setup0 | 0 | 0 | 0 | - | 60.0 | 0.732,-1.799 | cap_end |
| r3 | e01/setup13 | 28856 | 1 | 1 | **0** | 4.1 | 3.902,-1.436 | ARRIVED_DECLARED (false place) |
| r4 | e00/setup0 | 0 | 0 | 0 | - | 60.0 | - | cap_end |
| r4 | e01/setup13 | 28856 | 1 | 1 | **1** | 11.7 | 4.420,-1.514 | ARRIVED_DECLARED |

r3 e01 stopped after 0.30 m because the on-paint test used a 0.55 m remembered
range; the base was still 0.40 m west of zone B.  r4 drives to the remembered
point and crosses both zone bounds.  `cap_end` is a separate label, not a
failure reason.  Raw: `/home/ugrp/ugrp-sim/runs/visgoal-preflight-r4` (summary
sha256 `91bb0a31...`, funnel `0aafb183...`; copies in `preflight-r4/`).  The
r1/r2/r3 runs are excluded from current success claims because they contain the
known S-gate false positive (r1), the old unsigned-turn/import failures
(r2), or the false place claim fixed in r4 (r3).

## Gate r1 (aborted, not counted)

Gate r1 (`visgoal-gate-r1`, source `422fa98f`, started 11:52Z) ran the west
start first. Episode e00 was stopped by the worker at 67.7 SIM s after the
trace showed `seek_wall` handing over at 1.576 m while `approach_wall` accepted
only <=1.2 m: the visible divider was lost, the full 27 s spin restarted, and
the supervisor stop was initially written to the run root instead of
`episodes/eNN`. `ABORTED.json` records `valid_gate=false` and lists e00
SUPERVISOR_STOP, e01 SUPERVISOR_STOP at 0.6 s and e02 killed; the run is
**not counted** and no result from it is pooled. This was an internal
(worker) stop, not an external one. The defect was fixed in `725f0d194`
(accept the same band on both sides of the handover) and re-probed below.

## Preflight r5-r8 (west cap and door, east arrival)

All runs are two starts with a 60 SIM s cap: setup 0 (west, no destination
colour at tick 0) and setup 13 (east, 28856 paint px at tick 0). Each run
changed one control defect found by the previous run.

| run | source | west e00 | east e01 | change |
|---|---|---|---|---|
| r5 | `725f0d194` | cap_end 60.0 s, final (-0.68,-2.27) | arrived GT-inside 11.8 s | accept 1.8 m wall handover |
| r6 | `2a1a12ed1` | cap_end 60.0 s, final (-0.54,-2.27) | arrived GT-inside 11.8 s | bounded turn around cargo cubes instead of abandoning the wall |
| r7 | `1e2826404` | cap_end 60.0 s, final (0.865,-0.317) | arrived GT-inside 11.6 s | accept the full 3.0 m scan handover (r6 accepted 2.71 m, then lost it at 1.8 m and restarted the 27 s scan) |
| r8 | `cc2c9cfd9` | cap_end 60.0 s, final (1.62,-0.95), stage `gap_forward` | arrived GT-inside 11.7 s, final (4.42,-1.51) | require zone-sized (>=600 px) colour components; r7 spent 10 s on a 25x7 px blue end cap of a green beam |

r8 west e00 stage timeline: orient 0-27.4 s (full calibrated spin), seek_wall
27.4-40.2 s (one cyan-cube evasion at .526 m gap), approach_wall 40.2-48.6 s
(wall at 1.598 m), follow_north 48.6-55.7 s, gap_cross/gap_forward 55.7-60 s.
The montage (ticks 0/100/200/300/400/500/590/600, raw
`/home/ugrp/ugrp-sim/runs/visgoal-preflight-r8/analysis/e00-cap-end-montage.jpg`,
sha256 `78d3c827...`) shows the divider doorway ahead at ticks 590-600: the
west episode is cut by the 60 s preflight cap while crossing the door, not
stuck. Failure frames stay with the raw run; JSON summaries and funnels are
committed here.
The gate's pre-registered 120 s cap covers the crossing and the subsequent
east search; `cap_end` is still labelled separately in the gate report.

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
  --flow self_map --output experiments/2026-10-17-visgoal/stack-preflight-v14.json
python3 scripts/visgoal_probe.py --enabled --preflight --episodes 0,13 --sim-cap 60 \
  --queue experiments/2026-10-17-visgoal/queue-preflight.json \
  --renderer /home/ugrp/ugrp-sim/src/16a946ff3 \
  --legacy /home/ugrp/ugrp-sim/src/warp8f-selfmap-0ace43f25 \
  --setups /home/ugrp/ugrp-sim/src/<clone>/experiments/2026-10-17-visgoal/setups.json \
  --output /home/ugrp/ugrp-sim/runs/visgoal-preflight-r8

# Gate r2: all 16 starts, 120 SIM s each, prior funnel = r8.
python3 scripts/check_current_stack.py experiments/2026-10-17-visgoal/queue-gate.json \
  --flow self_map --output experiments/2026-10-17-visgoal/stack-gate-v14.json
python3 scripts/visgoal_probe.py --enabled --sim-cap 120 \
  --queue experiments/2026-10-17-visgoal/queue-gate.json \
  --renderer /home/ugrp/ugrp-sim/src/16a946ff3 \
  --legacy /home/ugrp/ugrp-sim/src/warp8f-selfmap-0ace43f25 \
  --setups /home/ugrp/ugrp-sim/src/<clone>/experiments/2026-10-17-visgoal/setups.json \
  --output /home/ugrp/ugrp-sim/runs/visgoal-gate-r2
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
