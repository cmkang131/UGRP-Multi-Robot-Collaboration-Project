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

## Yaw audit and mirror-pulse candidate (gate r1/r8 raw)

`scripts/visgoal_yaw_audit.py` (stdlib, read-only) groups recorded ticks by the
exact issued command signature and motion source and compares the controller's
own-command yaw with the sign-wrapped eval-only GT yaw. The GT yaw is read only
for this audit; it is never a controller input, and the recorded runs/verdicts
are unchanged. Result file `yaw-audit-r1-r8.json`:

| run | signature | n | GT yaw/pulse | prior yaw/pulse | ratio |
|---|---|---:|---:|---:|---:|
| gate r1 e00 | calibrated left pulse, `own_command_motion_v1` | 552 | 0.024445 | 0.022921 | 0.94 |
| r8 e00 | calibrated left pulse, `own_command_motion_v1` | 358 | 0.023700 | 0.022921 | 0.97 |
| r8 e00 | mirrored right pulse, `nominal_6f_unqualified_native` | 40 | -0.025511 | -0.039661 | **1.55** |
| r8 e01 | mirrored right pulse, `nominal_6f_unqualified_native` | 7 | -0.023916 | -0.039661 | **1.66** |

The analytic wheel model over-predicts pure-rotation yaw 1.55-1.66x, but only
where `CommandPrior` cannot match the calibration. The calibrated left pulse
(-0.35, 0.35, -0.35, 0.35, 0.02786 s, qualified servo) tracks GT at 0.94-0.97x;
the exact mirrored right pulse (0.35, -0.35, 0.35, -0.35) has no calibration
entry and falls back to the analytic model. Forward drive signatures have
|GT yaw/pulse| <= 0.0005 rad and no measurable bias.

Candidate B `visgoal_mirror_pulse_v1` (default off, `sim/visual_goal_search.py`
`mirrored_pulse_delta`) mirrors the calibrated delta and covariance
(`S P S`, `S = diag(1, -1, -1)`) only when the issued command is the exact
negation of the calibrated pulse under the same qualified servo state and
interval, and only when the prior would otherwise use the nominal fallback. It
introduces no new constant and changes only the motion prediction, not the
issued command. Offline replay of the new helper over the same raw (r8 e00, 40
exact mirrored pulses, no sim rerun): GT -1.02043 rad, nominal prior -1.58644
(1.55x), mirrored -0.91684 (0.90x). The runner enables it from the queue's `toggles` object (or
`--mirror-pulse`) and records the applied value in `stack.json`; the name was
dup-checked against all remote branches. Candidate B is queued with the same 16
starts after gate r2 and its results are not pooled with the default (mirror
off) gate run.

## Gate r2 (16 starts)

Gate r2 (`visgoal-gate-r2`, source `cc2c9cfd9`, 16 starts, 120 SIM s each,
prior funnel = preflight r8) started at 13:01Z on gcp3. It runs the default
mirror-off configuration, so it is the unpooled baseline for candidate B.
Results are added here only after the run is complete and independently
recounted from the raw files; a `cap_end` episode is reported separately and
not counted as a failure.

First completed episode (preliminary, while the rest run): e00 (west, setup 0)
is `cap_end` at 120.0 SIM s, found 0, colour_seen 0, final eval-only pose
(1.711, -1.045), never inside zone B. It reached `gap_cross`/`gap_forward` at
54.9/55.2 s and `east_search` at 62.4 s; after 69.0 s it spent 414 of 511 ticks
(81%) in left 90-degree leg turns (six leg turns: 3 `leg_complete`, 3
`leg_wall`) and only 91 ticks with forward>0 in 62-120 s; integrated rotation
22.8 rad. The montage (ticks 0/200/400/550/600/700/900/1100/1199, VM raw
`analysis/e00-cap-end-montage.jpg`, sha256 `afb4b672...`) shows open floor near
the divider and different headings, so the base is not physically stuck. Cause
for this episode: at the calibrated pulse a 90-degree leg turn costs 6.9 s and
the 2 s legs turn over faster than they translate, so the lawnmower did not
progress into the east area within the cap. This is recorded as the
pre-registered skill's result, not as a physics/command failure; the full
16-episode cause table follows after completion.

### Gate r2 stopped: SPEED_GATE_FAIL (execution mode)

At 13:40Z the first two episodes showed wall/SIM 1174.07/120.0 = 9.78 and
1176.76/120.0 = 9.81, above the AGENTS block threshold 6.0. The VM recorded
`SPEED_GATE_FAIL.json` (median 9.795, nworld 1) and `ABORTED.json`
(`valid_gate=false`, reason `SPEED_GATE_FAIL`); e00/e01 are complete raw
`cap_end` episodes, e02 was stopped at 59.8 SIM s (wall 579.1 s) with
`SUPERVISOR_STOP.json`, and all three episode directories are preserved as
invalid/partial. None of r2 is pooled.

Cause (checked on the VM): the runner was strictly sequential — one process,
one world, 400 MJWarp physics steps per 0.1 s control tick at timestep
0.00025 through `wp.capture_launch` — so the GPU stayed mostly idle (2-48%
sampled) while one CPU core ran at ~129%. Render/JPEG work is inside the same
serial loop, but physics stepping dominates and no control code reads wall
time. Fix: the same queue runs as four independent worker processes over
disjoint episode subsets (0-3, 4-7, 8-11, 12-15). Each process still runs
`nworld=1` with identical per-episode code, queue, source pin and seeds, so
per-episode physics and results are unchanged; the effective metric uses
nworld=4 (four concurrent episodes). Rerun `visgoal-gate-r3-p0..p3` started
13:52Z with leases `visgoal-p0..p3`; raw r2 stays under
`/home/ugrp/ugrp-sim/runs/visgoal-gate-r2`.

The four-process rerun was stopped too: with four single-world processes
sharing one L4, each worker fell to 0.32 ticks/s (3.1 s per 0.1 s tick,
3.2x slower than one process) with the GPU at 100%, so the effective
metric was about 7.8 wall/SIM (4 concurrent worlds), still above 6.0.
Those partial dirs (`visgoal-gate-r3-p0..p3`, ABORTED with
`SPEED_GATE_FAIL_EXECUTION_MODE`) are preserved and invalid. Root fix:
in-process nworld batching (`--nworld`, queue `worlds_per_batch`), which
is what `physics_backend: mjwarp_batch_v1` declares. Every selected start
is initialized as its own world in one MJWarp data batch; each 0.1 s tick
issues one 400-step graph launch for all worlds, while each world keeps
the identical per-episode perception, control and command tape. The
sequential `nworld=1` path is unchanged and stays the default; batch is a
separate execution condition and is not pooled with it.

Batch evidence (VM `visgoal-batch-eq-n1` vs `n2`, 10 SIM s, same queue and
seeds; `scripts/visgoal_batch_compare.py`): e00 0/101 and e01 4/101 command
mismatches (max wheel diff 0.7, max duration diff 0.024 s), all
status/found/stage values identical, max eval-only pose/yaw diff 0.088.
A 16-world short run (`visgoal-batch-g16-short`, 16 x 10 SIM s) completed
16/16 as `cap_end` with wall 490.9 s, i.e. wall/(sim_s*nworld) = 3.07
(steady-state per-tick 2.9), below the 6.0 block. Gate r4
(`visgoal-gate-r4`) reruns all 16 seeds at 120 SIM s with the same queue,
source pin `3d06f8b4f` and `worlds_per_batch: 16`; candidate B
(`visgoal_mirror_pulse_v1`) is queued after it in the same batch mode.

### Gate r4 results (nworld=16 batch, 16 starts, 120 SIM s)

Raw `/home/ugrp/ugrp-sim/runs/visgoal-gate-r4` (VM), copied summary/recount/
analysis/montages under `gate-r4/`. Run wall 5270.1 s for the batch
(120 SIM s x 16 worlds) = 2.745 wall/(sim_s*nworld); first-30-SIM check
(progress at tick 300) was 1439.87/(30*16) = 3.00, both below the 6.0 block
and record-only 3.5 warning. `EXIT` DONE, no HOST_ERROR.

Result: n=16, found 9/16, colour_seen 9/16, arrived_declared 8/16,
GT-inside-zone-B 1/16 (e13), entered zone any 1/16, cap_end 8/16
(separate, never counted as a failure). The strict recounted funnel
(`recount.json`, scripts/visgoal_recount.py) is starts 16 -> colour_seen 9
-> found_metric_or_arrived 9 -> arrived_declared 8 -> arrived_gt 1. The
runner's own table lists `found` before `colour_seen`; the recounted table
keeps a strictly sequential chain (colour can exceed found, and the short
run exposed a negative rejected_n under the old order), so the recount is
the funnel of record for this run.

Failure table (each episode has a 9-frame self-camera montage in
`gate-r4/montages/`, hashes in `gate-r4/montages.json`):

| reason_category | n | episodes | blocked_object | minimum_gap_m |
|---|---:|---|---|---|
| cap_end_no_colour_metric | 7 | 00,02,03,04,05,06,07 | not_observed | null (not_measured) |
| cap_end_found_no_arrival | 1 | 01 | not_observed | null (not_measured) |
| false_arrival_outside_zone | 7 | 08,09,10,11,12,14,15 | not_observed | null (not_measured) |
| arrived_gt_inside (success) | 1 | 13 | - | - |

All seven false arrivals declared at a remembered point whose stop pose was
just outside the west zone boundary: final eval-only x = 4.247-4.292
(boundary 4.3) and y = -1.49 to -1.94, i.e. 0.0084-0.0528 m outside zone B,
`final_stage=approach`. The skill's declared-arrival tolerance is 0.10 m to
the remembered paint point, so a stop on the outside edge is accepted by
the skill while the pre-registered GT-inside gate rejects it. e13 (the only
start where the paint was visible at t=0, 28,856 px) stopped at x=4.423 and
is the single GT-inside success. The 7 no-colour cap_end episodes ended at
`leg_forward` after a full 120 s search; e01 found the paint at 96.2 s but
hit the cap 23.8 s before it could declare. This is a search/arrival
judgment result of the pre-registered skill, not a physics or command
failure; no blocked object was observed, so the ledger records
`not_observed` and a null gap explicitly.

The recount cross-checks reported 0 mismatches and all aggregate checks
true (summary n/found/declared/GT and source_sha); control fields stay zero
(`static_map_control`, `truth_control`, `top_camera_frames`,
`held_world_reads`), but these are runner-written constants (see the
verification-scope note in the candidate B section), not an independent
input audit. This batch run is a separate execution condition from
the invalid sequential r2 (and from the aborted r3 workers); none of their
results are pooled here.

**Gate r4 verdict: FAIL** against the pre-registered arrival criterion
(GT-inside 1/16, seven false arrivals). Candidate B is a separate condition
and its results will not be pooled with this table.

### West/east mission split (gate r4)

The mission-relevant question is whether a robot starting **west of the
divider wall** crosses the gap and then finds zone B on the far side. The
authored setup index defines the split: e00-e07 start west (paint not visible
at tick 0), e08-e15 start east of the divider (already on the destination
side; only e13 sees the paint at tick 0). Split funnel from the same raw
trace/eval-only cells (`analysis-mission.json`, reproduced by
`scripts/visgoal_mission_split.py`; truth is read only in the eval-only
distance/verdict cells):

| side | starts | crossed gap | colour after crossing | found | declared | GT-inside |
|---|---:|---:|---:|---:|---:|---:|
| west (e00-e07) | 8 | 7 | 1 | 1 | 0 | 0/8 |
| east (e08-e15) | 8 | not needed | 8 | 8 | 8 | 1/8 |

Post-crossing west (the 7 episodes that crossed): `leg_forward` absorbed
50.8-71.4 s of the remaining 56-86 s of the cap; the trajectory's closest
approach to the zone-B rectangle was 2.62-4.91 m (e04 2.62, e05 2.79,
e02 2.83 m; the other four 3.76-4.91 m) and no post-cross tick was within
2.5 m. Only e01 saw colour after crossing (found at 96.2 s) and it hit the
cap before declaring. So in gate r4 the wall crossing worked in 7/8 west
starts, but the post-cross search found the destination in 0/8: under the
mission framing the failure point is the search range after the door, not
the crossing. This record measures destination search/arrival only; carrying
cargo to the far side (grasp, transport, release) is not part of these runs
and is not verified here.

### False-arrival stop condition and the 0.10 m tolerance (raw analysis, no rerun)

All seven false arrivals stopped through
`arrival_inside_paint_hypothesis`: the EKF point memory `m1`
(`destination-paint-B`) was within 0.0952-0.0983 m of the robot frame
origin, and that remembered point was itself only 0.0228-0.0602 m inside
zone B.  The base centre was therefore 0.0121-0.0534 m outside.  At the
same tick the *currently visible* paint median was 0.53-0.56 m ahead
(nearest visible paint 0.406-0.414 m; lower-centre pixels 35,451-40,962),
so `on_paint` was satisfied by paint in front of the robot although the base
centre had not reached the paint.

| ep | declared t | base (x,y) m | base margin to zone B (m) | memory range (m) | remembered point world (x,y) | remembered-point margin (m) | nearest visible paint (m) |
|---:|---:|---|---:|---:|---|---:|---:|
| 08 | 31.6 | 4.2466,-1.5682 | -0.0534 | 0.0972 | 4.3228,-1.6284 | +0.0228 | 0.4082 |
| 09 | 26.0 | 4.2745,-1.5541 | -0.0255 | 0.0973 | 4.3509,-1.6143 | +0.0509 | 0.4119 |
| 10 | 19.2 | 4.2506,-1.5966 | -0.0494 | 0.0966 | 4.3278,-1.6547 | +0.0278 | 0.4064 |
| 11 | 34.8 | 4.2771,-1.4870 | -0.0229 | 0.0983 | 4.3411,-1.5617 | +0.0411 | 0.4094 |
| 12 | 27.9 | 4.2770,-1.5040 | -0.0230 | 0.0953 | 4.3414,-1.5743 | +0.0414 | 0.4078 |
| 14 | 20.6 | 4.2872,-1.9119 | -0.0128 | 0.0976 | 4.3602,-1.9768 | +0.0602 | 0.4139 |
| 15 | 14.0 | 4.2879,-1.9398 | -0.0121 | 0.0952 | 4.3584,-2.0038 | +0.0584 | 0.4092 |

Margin is signed distance to the zone-B rectangle (positive inside); the
world point is the trace `relative_xy_m` transported by the eval-only pose,
and truth is read only for this table.  The stop radius is the distance from
the robot frame origin (base) to the remembered point, so when that radius
(0.10 m) exceeds the point's inset (0.023-0.060 m here) the base can stop
outside while the skill declares arrival.  `radius95_m` of the memory was
0.044-0.045 m in these rows, so the stop radius is not a sensor-noise value
either.

**Where 0.10 m came from.**  There is no external spec, field percentile or
literature value in the repository for this constant.  The only recorded
basis is the comment in `sim/visual_goal_search.py` `_approach`: preflight
r3 e13 put the median of *visible* paint at x=4.48 against zone edge 4.30
(0.18 m inset), and an earlier rule that stopped 0.25-0.55 m short declared
a place while the base was still outside; the comment therefore says "drive
to the point itself".  That observation justified reducing the standoff, not
the 0.10 m radius, and the inset in gate r4 (0.023-0.060 m) is 3-4x smaller
than the r3 value.  Per the study rule (do not tune an acceptance constant
without evidence) the tolerance is left unchanged; the declared arrival and
the strict GT-inside verdict are reported side by side, and success stays at
1/16.  A base-over-paint or near-edge crossing criterion would need its own
default-off toggle and evidence before it can replace this verdict.

### Cap-end no-colour: search coverage and FOV/colour check

All seven episodes rotated 23.7-31.3 rad and visited all 12 yaw bins
(30 deg each, full 360 deg).  `paint_ticks` counts trace ticks with any
paint component; none was a zone-sized saturated patch on the in-FOV frames.

| ep | rotation cmd (rad) | yaw bins | reached x>1.2 | max x | min GT range (m) | ticks GT in 2D FOV, <=3.5 m (share) | in-FOV paint check |
|---:|---:|---:|---|---:|---:|---|---|
| 00 | 31.269 | 12/12 | no | 0.669 | 3.634 | 0 (0%) | stayed `approach_wall` 80.1 s |
| 02 | 23.716 | 12/12 | yes | 1.693 | 2.831 | 167 (13.9%) | trace paint 0 (`destination_colour_absent`); sampled offline S>=110: max component 7 px, 88 px total |
| 03 | 27.447 | 12/12 | no | -0.125 | 4.906 | 0 (0%) | gap crossed, per-leg forward did not progress east |
| 04 | 24.131 | 12/12 | yes | 1.681 | 2.619 | 213 (17.7%) | trace paint 0; max component 6 px, 82 px total |
| 05 | 23.856 | 12/12 | yes | 1.704 | 2.792 | 119 (9.9%) | trace paint 0; sampled 2-35 px, max component 1-8 px |
| 06 | 27.478 | 12/12 | no | 0.614 | 4.101 | 0 (0%) | gap crossed, ended west of x=0.7 |
| 07 | 26.171 | 12/12 | no | -0.074 | 4.604 | 0 (0%) | gap crossed, ended west of x=0.2 |

The 2D FOV test uses half-HFOV 27.3 deg and range <=3.5 m at every 10 Hz
tick.  For e02/e04/e05, where the zone geometry entered that wedge, the
sampled frames were checked online in the trace and offline in HSV: the
online detector saw 0 paint pixels, and the offline band (H 99-125, V>=30)
with paint saturation S>=110 had at most 88 px in total (largest component
7-8 px).  The large band counts present on some frames (50k-170k px) are the
blue floor tint, whose median saturation is 66-77, below the S>=110 paint
threshold; they are not zone paint.  The zone was therefore not visible from
those viewpoints/ranges (wall occlusion); colour detection was not the
limiting step.  The other four episodes never brought the zone within
3.5 m in the wedge at all.  The dominant cause in this gate is east
traversal/occlusion: four of seven never reached x>1.2, and the three that
did plateaued at x=1.68-1.70 (2.6-2.8 m from the zone).

`leg_forward` is the stage that fails: in all six cap-end episodes that
entered it, 75-79% of ticks were `exact_turn` and only 20-24% commanded
forward, with 6-9 `_next_leg` calls (`search_leg_turn`, `leg_wall`) and net
displacement 0.032-0.537 m against 1.679-2.429 m of path over 51-71 s.  The
per-run timing shows this is the designed square search, not a wall
re-trigger deadlock: each leg drives 19-27 ticks (1.9-3.1 s) and each 90 deg
turn takes 69 ticks (6.9 s; 69 x 0.0244 rad/pulse ~= 96 deg, consistent with
the yaw audit), i.e. 6-9 leg cycles with `leg_wall` firing at the end of each
short leg because the start-bay walls are within 0.55 m.  Four equal legs
close a small square near the start, which is why the net displacement stays
0.03-0.54 m while 1.7-2.4 m of path is driven.  The search pattern is the
defect: a leg of ~1.1 m with a ~7 s turn cannot cover the 2.6-4.4 m east
distance (gap exit to zone) inside the 120 s cap; e02/e04/e05 end 2.6-2.8 m
from the zone and e03/e06/e07 end west of x=0.6.  The mirror-pulse candidate
finishes first because it is the already-queued paired condition; it changes
only the own-motion prediction, not the issued command or the leg pattern, so
it is not expected to fix this cause, but its result decides the next step.
Candidate C (below) fixes this cause and the arrival aim; it is queued to run
after B with the same 16 starts and batch, and is not pooled with B or r4.

### Paired candidate B results (nworld=16 batch, mirror pulse on)

Raw `/home/ugrp/ugrp-sim/runs/visgoal-gate-r4-mirror` (VM); copied summary,
strict recount, analysis, arrival/FOV analysis, cap-end analysis and the 16
9-frame montages under `gate-mirror/`. Queue `queue-gate-mirror.json` (source
pin `3d06f8b4f`, checkout `aa8c6fe26`, toggle `visgoal_mirror_pulse_v1: on`,
`worlds_per_batch: 16`), stack admission `stack-gate-mirror-v17.json`, prior
funnel = gate-r4 `recount.json`. The execution stack, source pin and pinned
input hashes are identical to gate r4, but the committed gate-r4 `queue.json`
differs from B's in seven metadata keys: `candidate`, `output`, `paired_with`,
`pairing_note`, `rejection_table`, `run_name` and `toggles`.  In gate-r4's
copy `run_name` and `output` still say `visgoal-gate-r2`, `rejection_table`
points to the preflight-r8 funnel, and the four pairing fields are absent;
the other 26 keys (`stack_values`, `source_sha`, `input_sha256`, `setups`,
`sim_cap_s` 120, `worlds_per_batch` 16, `renderer_source`, `legacy_source`,
...) are identical.  Whether that gate-r4 metadata is a copy error or
reflects a different launch queue cannot be determined from the artifacts;
it is recorded as unverified and no cause is estimated.  The mirror toggle
rewrites no issued command: it changes only the motion prediction used by
the same controller, so behaviour can still diverge in closed loop (below).

Run `EXIT` DONE (no error, no HOST_ERROR). Batch wall 5277.47 s for
120 SIM s x 16 worlds = 2.749 wall/(sim_s*nworld); the first-30-SIM check
(tick-300 `progress.json` wall 1441.52/1441.69 s) is
1441.69/(30*16) = 3.004, below the 6.0 block and the record-only 3.5
warning; in-flight samples are 2.746-3.066.

Result (independent recount, `gate-mirror/recount.json`: 0 mismatches, all
aggregate checks true): n=16, colour_seen 8/16, found 8/16, arrived_declared
8/16, GT-inside-zone-B 1/16 (e13), entered zone any 1/16, cap_end 8/16
(separate, never counted as a failure). Strict funnel: starts 16 ->
colour_seen 8 -> found_metric_or_arrived 8 -> arrived_declared 8 ->
arrived_gt 1.

| reason_category | n | episodes | blocked_object | minimum_gap_m |
|---|---:|---|---|---|
| cap_end_no_colour_metric | 8 | 00,01,02,03,04,05,06,07 | not_observed | null (not_measured) |
| false_arrival_outside_zone | 7 | 08,09,10,11,12,14,15 | not_observed | null (not_measured) |
| arrived_gt_inside (success) | 1 | 13 | - | - |

West/east mission split (candidate B): the authored split is e00-e07 west
(behind the divider; they must cross the gap before any destination search)
and e08-e15 east (already on the destination side).

| side | starts | crossed gap | colour after crossing | found | declared | GT-inside |
|---|---:|---:|---:|---:|---:|---:|
| west (e00-e07) | 8 | 6 | 0 | 0 | 0 | 0/8 |
| east (e08-e15) | 8 | not needed | 8 | 8 | 8 | 1/8 |

West details (`analysis-mission.json`): e00,01,03,04,06,07 crossed at
34.5-58.2 s; e02/e05 never crossed (`approach_wall` for 92.6 s each, final
zone range 4.15/4.48 m). After crossing, `leg_forward` absorbed 47.7-71.4 s
of the remaining cap; the trajectory's closest approach to the zone-B
rectangle was 2.58-4.83 m (e04 2.58, e00 2.63, e01 2.80 m; the other three
4.08-4.83 m), no post-cross tick came within 2.5 m, and colour was never
seen after crossing (0/6). So candidate B also fails at the post-cross
search range, and the crossing itself degraded from 7/8 (gate r4) to 6/8.

The seven false arrivals are the same stop geometry as gate r4: the skill
declares at a base->remembered-point range of 0.0959-0.0993 m (its unchanged
0.10 m tolerance) while the remembered point is only 0.0385-0.0610 m inside
zone B, so the base centre stops 0.0079-0.0375 m outside. The currently
visible paint was 0.407-0.413 m ahead with 35,552-41,037 lower-centre pixels,
so `on_paint` was satisfied by paint in front; no arrival test was changed.

| ep | declared t | base (x,y) m | base margin (m) | memory range (m) | remembered point margin (m) | radius95 (m) | nearest visible paint (m) |
|---:|---:|---|---:|---:|---:|---:|---:|
| 08 | 31.9 | 4.2852,-1.5589 | -0.0148 | 0.0964 | +0.0592 | 0.0450 | 0.4097 |
| 09 | 25.9 | 4.2625,-1.5625 | -0.0375 | 0.0985 | +0.0411 | 0.0447 | 0.4108 |
| 10 | 19.5 | 4.2632,-1.5499 | -0.0368 | 0.0959 | +0.0385 | 0.0447 | 0.4131 |
| 11 | 32.9 | 4.2921,-1.5089 | -0.0079 | 0.0971 | +0.0541 | 0.0444 | 0.4071 |
| 12 | 27.2 | 4.2774,-1.4888 | -0.0226 | 0.0993 | +0.0425 | 0.0443 | 0.4093 |
| 14 | 20.5 | 4.2887,-1.9214 | -0.0113 | 0.0972 | +0.0610 | 0.0451 | 0.4124 |
| 15 | 14.0 | 4.2853,-1.9416 | -0.0147 | 0.0959 | +0.0571 | 0.0451 | 0.4093 |

Cap-end/no-colour episodes: all eight rotated 20.5-27.4 rad and visited all
12 yaw bins; with half-HFOV 27.3 deg and <=3.5 m, the zone geometry entered
the wedge on e00 208 ticks (17.3%), e04 187 (15.6%), e01 146 (12.2%) and
never on the other five. The offline paint-band check (H 99-125, V>=30,
S>=110) on 16 sampled in-FOV frames found at most 7-8 px largest component
(e00 7, e04 8, e01 6) against the zone-sized >=600 px requirement; the
43k-167k band pixels are the blue-tinted floor, whose saturation stays below
the paint threshold. The zone was therefore not visible from the visited
viewpoints (search coverage/occlusion), not a colour-detection failure.
e02/e05 ended in `approach_wall`; the other six ended in `leg_forward` (r4:
e02/e04/e05 leg_forward). e01 is the one changed find: gate r4 found the
paint at 96.2 s, B never saw colour at all.

Visual check: all 16 episode montages (9 self-camera frames each, ticks
0..last, `gate-mirror/montages/eNN.jpg`, sha256 in `montages.json`) were
opened. The eight west/no-colour episodes never show the saturated zone-B
patch; e02/e05 linger on cargo (a green beam / yellow cube) and e03/e06/e07
turn through the divider area and the start-bay walls. The seven false
arrivals show the bright patch appearing through the doorway at 4.1-16.4 s
and the base stopping on its near edge with paint in the lower field of view;
e13 shows the patch from tick 0 and stops inside. No blocked object was
observed in any episode, so the ledger keeps `not_observed` and a null gap
explicitly.

Effect of B versus gate r4 (comparison scope: B's own raw recount plus a
cross-run comparison of the runner summary fields — `rotation_cmd_rad`,
declared times and final eval-only poses — and of the raw `stage_runs`; no
full 16-episode raw recount of gate r4 and no trajectory-path comparison
were made). Although the mirror toggle itself rewrites no command, the
closed loop diverges: `rotation_cmd_rad` differs in 15/16 episodes (e00
31.269 -> 20.514 rad, e02 23.716 -> 25.396 rad; cross-checked against the
raw trace sum of |command_delta[2]|), and among the seven shared cap_end
episodes the stage progression differs in 6/7 (only e07 identical: e00 gains
follow_north/gap_cross/gap_forward/east_search/leg_forward over 45.5-120 s,
while e02 keeps only orient then approach_wall 27.4-120 s). Outcome counts do
not improve: found 8 vs 9 (e01 lost), declared 8 vs 8, GT-inside 1 vs 1;
declared-time differences are -1.9 to +0.3 s (median 0.0) and final
eval-only positions differ by 0.0032-1.4809 m (median 0.1724). B therefore
changes behaviour as well as the own-motion prior, but the score stays the
same.

Verification scope: B's funnel and aggregates are an independent recount of
its raw trace/eval-only cells (`recount.json`: 0 mismatches, all aggregate
checks true). The control-field zeros (`held_world_reads`,
`static_map_control`, `spawn_control`, `truth_control`, `top_camera_frames`)
are runner-written constants in the episode records
(`scripts/visgoal_probe.py` lines 649-650 and 961-962), so they are not an
independent input audit; whether any held-object world read actually
happened is unverified. The B-vs-r4 comparison above uses runner summary
fields and raw stage runs, not a full recount of gate r4's 16 episodes and
not a trajectory comparison.

**Candidate B verdict: FAIL** against the pre-registered arrival criterion
(GT-inside 1/16 with seven false arrivals) — the same failure mode as gate
r4, with one fewer find (e01). Under the mission framing the west side
(behind the wall) crossed in 6/8 but saw the paint after crossing in 0/6, so
it never reached found/declared/GT (0/8); the east side (already on the
destination side) found and declared 8/8 but 7 stops were just outside the
zone. The single GT-inside episode is also the only start where the paint
was visible at tick 0 (`start_visibility_pixels` 28,856; the base was inside
for 29 frames, first at 9.1 s, declared at 10.9 s trace time, episode
`sim_s` 11.8), and among the 15 initially invisible starts the GT-inside
count is 0/15 (`initially_invisible_n` 15, `initially_invisible_gt_n` 0).
The outcome is therefore also consistent with "only the easy,
paint-visible-at-start case succeeds". This record measures destination
search/arrival only: no cargo is grasped, carried or released, so the
mission-level "carry the load to the other side" is not verified by this
candidate or by this thread. B is not pooled with gate r4 or with C.

### Candidate C (default off): expanding lawnmower and arrival aim inset

Candidate C is the fix for the two raw-verified causes above.  It is behind
one default-off queue toggle, `visgoal_expanding_search_v1`
(`Options.expanding_search`, `sim/visual_goal_search.py`); the gate-r4
default remains byte-identical when the toggle is off.

Search: the equal 4-leg square is replaced by a lawnmower that does not close
in place.  Leg lengths and turns are the gate-r4 measured values:

| quantity | gate-r4 measurement | use in C |
|---|---|---|
| forward-only displacement | median 0.0128 m/tick over 42 forward runs (range 0.0095-0.0134), eval-only poses at run ends | 344-tick long stroke = 4.4 m at the median (3.27 m at the slowest run) |
| one 90 deg exact turn | 69 ticks = 6.9 s at 10 Hz (exact_turn_rad 0.022921) | every stroke change; the existing left turns are kept |
| gap exit -> nearest zone point | 2.65, 2.91, 2.94 m (e02/e04/e05); 4.37-5.52 m (e03/e06/e07) | 344-tick stroke covers the coordinator's 2.6-4.4 m bound |
| zone bearing at leg start | +39..+119 deg LEFT of the post-entry heading; the 90 deg left turn at the end of the first stub restores the gap-exit heading, which is within -51..+29 deg of the zone and within 3 deg for e02/e04/e05 | the long stroke is the SECOND leg, after that left turn; the first leg stays a 20-tick stub |
| lateral line spacing | zone B is 1.4 m wide in y | 60-tick (0.77 m) lateral offset, so two lines span 0.77 m and three would span 1.54 m |
| leg_forward time available | leg_forward ran 51-71 s of the 120 s cap (pre-search stages 49-69 s) | entry 6.9 s + stub 2 s + turn 6.9 s + long stroke 34.4 s = 50.2 s; the long stroke ends at 99-119 s in those starts |

The schedule is `(20, 344, 60, 300, 60)` forward ticks with the original left
turn between strokes (entry turn 69 + 4 x 69 = 345 turn ticks, but the later
strokes can end in `cap_end`, which is labeled separately).  The first 20-tick
stub is unchanged; the long stroke is the second leg, after the left turn
that restores the gap-exit heading.  The later 60/300/60 strokes are the
lawnmower lines on a parallel offset.  A closed expanding square cannot cover
4.4 m in the cap (a 3-unit square costs 12*U + 6*69 ticks), which is why the
schedule is strokes, not a square.  If the schedule exhausts, the last stroke
grows by 60 ticks instead of closing a fixed square.

Arrival: the 0.10 m point tolerance is unchanged, but the aim moves inward.
Gate-r4 false arrivals declared at base->remembered-point 0.0952-0.0983 m
while the remembered point was only 0.0228-0.0602 m inside zone B and the base
centre 0.0121-0.0534 m outside.  C aims the same 0.10 m tolerance at a point
`ARRIVAL_AIM_INSET_M = 0.142 m` past the remembered point along the
robot-forward axis (0.098 rounded base->point stop distance + 0.044 rounded
memory radius95), so the base ends ~0.044 m beyond the remembered point.
The `+(inset, 0)` robot-frame form stays valid after the base passes the
point, where a base->memory bearing would flip backwards.  `declared` and
strict GT-inside verdicts stay side by side; no pooling with gate-r4 or B.

Unit coverage: `tests/test_visual_goal_search.py` checks the default-off
square is unchanged, the C schedule (20-tick stub, 344-tick long stroke,
left turns), the growing fallback, and the 0.098 m false-arrival geometry
(default declares; C keeps driving; 0.06 m past the point declares) with the
tolerance untouched.

Candidate C was measured afterwards (results below): the expanding search did
not improve the west side and the 0.142 m arrival aim broke the declaration
test (0/16 declared). The arrival aim is therefore identified as a defect to
separate from the search strategy, not a setting to retune; the constant is
unchanged and the result is not pooled with r4/B.

### Candidate C results (nworld=16 batch, expanding search + arrival aim)

Raw `/home/ugrp/ugrp-sim/runs/visgoal-gate-r4-lawnmower` (VM); copied summary,
strict recount, analysis, arrival/FOV analysis, cap-end analysis, west/east
mission split, the read-only schedule analysis (`analysis-c.json`) and the 16
9-frame montages under `gate-lawnmower/`. Queue `queue-gate-lawnmower.json`
(source pin `c390105c2`, executed checkout `0b44a3f0d`, toggle
`visgoal_expanding_search_v1: on`, `worlds_per_batch: 16`), stack admission
`stack-gate-lawnmower-v19.json`, prior funnel = gate-r4 `recount.json`.

Intended changes vs gate r4/B: the equal short-leg square is replaced by the
expanding lawnmower schedule (`20/344/60/300/60` ticks), the arrival aim moves
from the remembered point to 0.142 m past it along the robot-forward axis
(`ARRIVAL_AIM_INSET_M`), and the runner gained the toggle plumbing that records
both settings in `stack.json`. Gate r4's 120 SIM s cap, `nworld=16`, the 16
starts file, `stack_values` and the renderer/legacy pins are unchanged; the
`input_sha256` differs only for the three intended code files
(`scripts/visgoal_probe.py`, `sim/visual_goal_search.py`,
`tests/test_visual_goal_search.py`). The gate-r4 queue's stale metadata
(seven fields listed in the candidate B section) is the same in this queue;
C's own `run_name`/`output`/`rejection_table` point to its own run.

Run `EXIT` DONE (no error, no HOST_ERROR). Batch wall 6091.75 s for
120 SIM s x 16 worlds = 3.173 wall/(sim_s*nworld) (r4 2.745, B 2.749 on the
same host; record-only speed gate, still below the 6.0 block). All 16 episodes
ran to the cap, so the `progress.json` records only hold `t=120`; the
first-30-SIM frame-mtime estimate is 1504.34/(30*16) = 3.134 and is labelled
as an estimate, not a progress-record measurement.

Result (independent recount, `gate-lawnmower/recount.json`: 0 mismatches):
n=16, colour_seen 9/16, found 9/16, **arrived_declared 0/16**, GT-inside
0/16, entered-zone-any 8/16 (eval-only reference only, never a success),
cap_end 16/16. Strict funnel: starts 16 -> colour_seen 9 ->
found_metric_or_arrived 9 -> arrived_declared 0 -> arrived_gt 0. Reasons:
`cap_end_no_colour_metric` 7 (e00,01,02,03,05,06,07) and
`cap_end_found_no_arrival` 9 (e04,08,09,10,11,12,13,14,15).

West/east mission split (e00-e07 west of the divider, e08-e15 east):

| side | starts | crossed gap | colour after crossing | found | declared | GT-inside |
|---|---:|---:|---:|---:|---:|---:|
| west (e00-e07) | 8 | 5 | 0 | 0 | 0 | 0/8 |
| east (e08-e15) | 8 | not needed | 8 | 8 | 0 | 0/8 |

West: crossing at 34.5-59.3 s for e01,02,03,06,07; e00/e05 never crossed
(`approach_wall` to the cap); e04 saw paint while still west of the divider
(found without crossing). After crossing, `leg_forward` absorbed 60.8-85.6 s
of the cap and the closest approach to the zone-B rectangle was 2.54-4.49 m
(e01 2.54, e06 2.54, e02 2.70 m) — the post-cross search still does not reach
the zone. East: all eight episodes found the paint and their final eval-only
pose was inside zone B (final zone range 0.0 m), yet none declared arrival.

**Arrival declaration regression (raw trace, no rerun).** Gate r4 and B
declared 8/16 arrivals; C declared 0/16 although the east side found the paint
8/8 and ended physically inside the zone. All found episodes stay in
`approach` until the cap; each has 2-3 `local_reacquire_spin` events (a full
calibrated 2*pi spin, ~27 s each at this pulse rate) and continuous paint
memory observations. At the final ticks the paint is still in the lower-centre
field of view and the memory is fresh, but `aim_rng` is about 0.18 m > 0.10 m,
so the declaration test — which in C targets a point 0.142 m past the
remembered point — never fires. r4/B declared at a base->remembered-point
range of 0.0952-0.0983 m, i.e. before the remembered point. The only
arrival-path change from r4/B is `ARRIVAL_AIM_INSET_M = 0.142 m`; the constant
is not retuned after seeing this result, no rerun was made, and the exact
limit-cycle mechanism is unconfirmed. This is recorded as a defect of the C
candidate, separate from its search change: the arrival-aim change must be
separated from the search change before it is used again (Stage A does this).

Cap-end/no-colour (7 episodes): rotations 20.5-35.6 rad, all 12 yaw bins
visited. Zone geometry entered the half-HFOV 27.3 deg / <=3.5 m wedge on e02
152 ticks (12.7%), e01 41 (3.4%), e06 40 (3.3%) and never on the other four;
the offline paint-band check on 16 sampled in-FOV frames found at most 8 px
largest component (e02; 7 frames with any paint pixel) against the
zone-sized >=600 px requirement. As in r4/B the large band counts are the
blue-tinted floor below the S>=110 paint threshold; the zone was not visible
from those viewpoints, not a colour-detection failure.

Visual check: all 16 episode montages (9 self-camera frames each, ticks
0..last, `gate-lawnmower/montages/eNN.jpg`, sha256 in `montages.json`) were
opened. The west episodes never show the saturated zone-B patch (pickup room,
corridor and walls; e05 lingers on a yellow cube). The eight east episodes
show the robot approaching and then standing on/next to the blue zone paint
while still turning and re-acquiring (e13-e15 are stationary over the paint at
the last frames) — the paint is visible but the arrival test never fires. No
blocked object was observed (`not_observed`) and no gap was measured
(`not_measured`).

**Candidate C verdict: FAIL (worse than r4/B)** — arrived_declared 0/16 and
GT-inside 0/16, west crossing 5/8 with post-cross colour 0/5 and found 0/8.
The search schedule did not improve the west search, and the arrival-aim
change broke the declaration test that had produced eight declarations in
r4/B. Next-fix direction from this table: (1) separate or revert the arrival
aim change (done for Stage A); (2) harden west crossing (2/8 stalled in
`approach_wall`); (3) the post-cross search still ends 2.5-4.5 m from the zone
with `leg_forward` absorbing 61-86 s, so search coverage remains the dominant
cause. C is not pooled with gate r4/B, Stage A, or each other.

## Files

* `setups.json` — 16 fixed starts (setup only; includes parked
  r2/r3 poses to keep the other two robots out of the route).
* `scripts/visgoal_probe.py` — MJWarp runner: 10 Hz render -> raw fisheye ->
  paint/wall/obstacle detection -> memory -> control -> command tape.
* `scripts/visgoal_mission_split.py` — read-only west/east mission split:
  crossing -> colour-after-crossing -> found -> declared -> GT funnel, plus
  post-crossing stage times and eval-only distance bands to zone B.
* `vendor/` — byte copies; no egomem-owned file is edited.
* `gate-r4/` — gate r4 summary, strict-funnel recount, per-episode analysis
  table, the read-only arrival/FOV analysis (`analysis2.json`, reproduced by
  `scripts/visgoal_arrival_analysis.py`), the west/east mission split
  (`analysis-mission.json`) and 9-frame montages (self camera only), plus the
  compressed full SHA256SUMS list (`SHA256SUMS.json.zst`, original sha/bytes
  in `SHA256SUMS.manifest.json`).
* `gate-mirror/` — paired candidate B summary, strict recount, analysis,
  arrival/FOV analysis (`analysis2.json`), cap-end analysis
  (`capend_analysis.json`), west/east mission split
  (`analysis-mission.json`), the 16 9-frame self-camera montages and the
  compressed SHA256SUMS list. Candidate B is a separate condition and is not
  pooled with gate r4.
* `gate-lawnmower/` — paired candidate C summary, strict recount, analysis,
  arrival/FOV analysis (`analysis2.json`), cap-end analysis
  (`capend_analysis.json`), west/east mission split (`analysis-mission.json`),
  the read-only schedule analysis (`analysis-c.json`, reproduced by
  `scripts/visgoal_c_analysis.py`), the 16 9-frame self-camera montages and
  the compressed SHA256SUMS list. Candidate C is a separate condition and is
  not pooled with gate r4/B or with any later run.
* `queue-gate-mirror.json` / `queue-gate-lawnmower.json` — paired candidate B
  and C queues (same 16 starts, 120 SIM s, nworld=16); their stack admission
  files are `stack-gate-mirror-v17.json` and `stack-gate-lawnmower-v19.json`.
  Candidate results are not pooled with gate r4 or with each other.
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

# Gate r4: all 16 starts, 120 SIM s each, nworld=16 batch, prior funnel = r8.
python3 scripts/check_current_stack.py experiments/2026-10-17-visgoal/queue-gate.json \
  --flow self_map --output experiments/2026-10-17-visgoal/stack-gate-v16.json
python3 scripts/visgoal_probe.py --enabled --sim-cap 120 --nworld 16 \
  --episodes 0,1,2,3,4,5,6,7,8,9,10,11,12,13,14,15 \
  --queue experiments/2026-10-17-visgoal/queue-gate.json \
  --renderer /home/ugrp/ugrp-sim/src/16a946ff3 \
  --legacy /home/ugrp/ugrp-sim/src/warp8f-selfmap-0ace43f25 \
  --setups /home/ugrp/ugrp-sim/src/<clone>/experiments/2026-10-17-visgoal/setups.json \
  --output /home/ugrp/ugrp-sim/runs/visgoal-gate-r4

# Read-only arrival/FOV analysis of the gate r4 raw (no physics rerun).
python3 scripts/visgoal_arrival_analysis.py /home/ugrp/ugrp-sim/runs/visgoal-gate-r4 \
  --output /home/ugrp/ugrp-sim/runs/visgoal-gate-r4/analysis2.json

# Candidate B (same 16 starts, mirror pulse on; not pooled with gate r4).
python3 scripts/visgoal_probe.py --enabled --sim-cap 120 --nworld 16 \
  --episodes 0,1,2,3,4,5,6,7,8,9,10,11,12,13,14,15 \
  --queue experiments/2026-10-17-visgoal/queue-gate-mirror.json \
  --renderer /home/ugrp/ugrp-sim/src/16a946ff3 \
  --legacy /home/ugrp/ugrp-sim/src/warp8f-selfmap-0ace43f25 \
  --setups /home/ugrp/ugrp-sim/src/<clone>/experiments/2026-10-17-visgoal/setups.json \
  --output /home/ugrp/ugrp-sim/runs/visgoal-gate-r4-mirror

# Candidate C (same 16 starts, expanding lawnmower + arrival aim on; not pooled).
python3 scripts/check_current_stack.py \
  experiments/2026-10-17-visgoal/queue-gate-lawnmower.json \
  --flow self_map --output experiments/2026-10-17-visgoal/stack-gate-lawnmower-v19.json
python3 scripts/visgoal_probe.py --enabled --sim-cap 120 --nworld 16 \
  --episodes 0,1,2,3,4,5,6,7,8,9,10,11,12,13,14,15 \
  --queue experiments/2026-10-17-visgoal/queue-gate-lawnmower.json \
  --renderer /home/ugrp/ugrp-sim/src/16a946ff3 \
  --legacy /home/ugrp/ugrp-sim/src/warp8f-selfmap-0ace43f25 \
  --setups /home/ugrp/ugrp-sim/src/<clone>/experiments/2026-10-17-visgoal/setups.json \
  --output /home/ugrp/ugrp-sim/runs/visgoal-gate-r4-lawnmower

# Read-only candidate C analysis (schedule strokes, long run, arrival aim).
python3 scripts/visgoal_c_analysis.py /home/ugrp/ugrp-sim/runs/visgoal-gate-r4-lawnmower \
  --output /home/ugrp/ugrp-sim/runs/visgoal-gate-r4-lawnmower/analysis-c.json

# Read-only west/east mission split for any completed run (same raw, no rerun):
#   crossing -> colour after crossing -> found -> declared -> GT-inside, plus
#   post-crossing stage times and eval-only distance bands to zone B.
for run in visgoal-gate-r4 visgoal-gate-r4-mirror visgoal-gate-r4-lawnmower; do
  python3 scripts/visgoal_mission_split.py /home/ugrp/ugrp-sim/runs/$run \
    --output /home/ugrp/ugrp-sim/runs/$run/analysis-mission.json
done
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

Mission scope: these runs measure the own-RGB visual destination search and
the arrival verdict only. No cargo is grasped, carried, released or reported
as transported, and no held-object world coordinate is read by any control
path (`held_world_reads` is a runner-written zero, not an independent audit).
The mission-level task "carry the load to the far side of the wall" (grasp,
transport, release, task allocation) is **not verified** by this thread; the
west/east split only tests whether the robot crosses the divider gap and then
finds the destination zone.
