# s3fix16: endpoint visibility, command ownership and coarse servo

2026-10-10. DEV development round, not confirmation. Mac physics/render/replay forbidden;
all replay and physics on `host=oracle-x86`. PR #416 remains draft; no merge/CI wait.

## Before diagnosis

A is classified from s3fix15 original raw, per `beam_obs` timestamp: exact saved
MuJoCo camera pose and qpos, nearest grip-band top centre + four corners projected
into the actual rendered pinhole support (raw fisheye remap cannot restore missing
pinhole pixels). `fov_clipped` means at least one corner is outside support;
`in_fov_rejected` means all corners inside, not proof of absence of occlusion.
No physics step, no image regeneration, no GT enters controller.
Raw: `outputs/oracle-runs/s3fix15-batch-r1/cohort/`; archived source
`4e19382d59a9bb2bbf351a7fca1356cdf480e8a0`.
If FOV loss: freeze own RGB measurement before loss and use only issued-command
calibration in a bounded final open-loop segment. If in-FOV rejection: fix only
the identified detector cause. B: fine alignment owns arm commands exclusively,
PF measured calibration unchanged. C: retain s3fix15 acceptance widths, require
single-axis immediate progress with move-settle-look and hysteresis.
Full 10-case manifest will be committed before physics; no midbatch adaptation.

## References

- Hutchinson, Hager, Corke (1996), [A Tutorial on Visual Servo Control](https://faculty.cc.gatech.edu/~seth/ResPages/pdfs/HutHagCor96.pdf): position/image visual feedback and look-then-move architecture.
- [ROS2 control command ownership](https://docs.universal-robots.com/Universal_Robots_ROS_Documentation/rolling/doc/ur_robot_driver/ur_robot_driver/doc/usage/controllers.html): one active controller per claimed command interface; explicit handover.

## Diagnosis / frozen physical preregistration (before new physics)

Evaluation source `bc06ec0347cf926055fdde981593d818a2ebd7ac`, Oracle x86, 0 physics steps,
5.88 wall seconds. All band centres remained visible; partial corners matter.

|condition|r1 visible / in-FOV rejected / FOV clipped|r2 visible / in-FOV rejected / FOV clipped|
|---|---:|---:|
|c0|2 / 459 / 0|6 / 0 / 439|
|c1|1 / 463 / 0|43 / 0 / 0|
|c2|3 / 454 / 0|7 / 0 / 434|
|c3|3 / 454 / 0|6 / 0 / 439|
|c4|41 / 0 / 0|42 / 0 / 0|
|c5|41 / 0 / 0|4 / 0 / 449|

Every rejection was `BAND_CLIPPED`. Example c0/r1 at 4.0 s: deepest band
corner y=475.614/480 in ideal rendered image; all four inside. c0/r2 at6.0s:
y=512.267/480, one corner outside. The detector uses a **14-pixel eroded**
valid mask, explaining r1 rejection of a complete near-border band. Candidate
`band_border` uses a 1px sampling margin, retaining complete-band, length20–60mm,
colour and identity checks. A saved RGB replay checks this exact claim separately.
`endpoint_memory`: only a prior fully visible, existing standoff-quality own RGB
fit can start it; accepted issued calibrated forward/turn100ms pulses propagate
that fit, max3 pulses,60mm/.32rad,8s; no timestamp renewal. Partial band evidence
is never re-labelled a fresh visual measurement. No new camera or runtime GT.

B: `posture_ownership` gives own-RGB alignment the arm until that state exits.
Neither a pending PF re-look nor `_v98_restore` may overwrite its pan; measured
PF camera keys remain unchanged. Status, partner abort and arm interpolation
continue in the outer tick. Reset/reentry is scoped by state and open gripper.

C: s3fix15 c3/c4 requested100ms forward pulses, but `real_fine_v1` rewrote them
as60ms before heading admission. Heading replaced these illegal pulses with
alternating yaw; this is command ownership conflict, not an RGB detection loss.
`coarse_axis_ownership` preserves the exact calibrated proposal through that
adapter, one axis at a time, immediate error decrease, .50s minimum settle plus
fresh frame, 1.25x hysteresis exit. Alignment acceptance remains **pair dx18mm,
cyan dx9.6mm, dy3mm about -6mm, yaw.112rad**, two fresh confirmation frames.
A hysteresis latch never grants an aligned receipt.

All four booleans default false. `abc_v1` enables all for this DEV round.
Bundle **zone-s3-alignment-ownership-v162**, workflow7.55.0 reserved after main
and all12 open PR heads scanned (maximum161). Central workflow JSON unchanged.

`batch-plan.json` freezes names, conditions, seeds14201–14206, commands and flags.
Exactly pair c0–c5 plus cyan c0/c3/c4/c5, ten concurrent workers,60SIM each,
OSMesa/LP_NUM_THREADS4/OMP1, dev_light, heading on except coupled carry.
One optional pathcheck5SIM uses pair c0 and the same flags. No batch results
read for tuning until all cases finish; no rerun or threshold change within round.
Command per manifest row:
`python -m scripts.run_s3_alignment_ownership --expected-source-sha SHA --output outputs/NAME/raw --case CASE --condition CONDITION --coarse-fine stopped_base_arm_v1 --refinements abc_v1 --execute`.
Batch: `python -m scripts.run_s3_alignment_ownership_cohort --expected-source-sha SHA --output outputs/s3fix16-batch-r1/cohort --execute`.

Primary outcomes: joint n/10 and per-robot alignment / actual two-finger contact
for>=.20s / contact-supported lift z>.06m / carry>=.02m while lifted. Cyan c0
regression included. Report A missed-end stalls, B restore collisions, C turn
reversals; retain all errors including ENOSPC=HOST_ERROR. Report wall/SIM and
existing nested host timers without performance optimization. These initial
conditions were already viewed: development regression, not confirmation.

Implementation note: the legacy 60ms adapter source is sealed by previous PF
replay evidence. It remains byte-identical. The new S3-only instance class binds
its command conversion to the exact calibrated pulse while this alignment owns
it; all other proposals use the original converter. No shared source/seal change.
[OpenCV erosion semantics](https://docs.opencv.org/4.13.0/d9/d61/tutorial_py_morphological_ops.html)
explain why a14px valid-mask erosion rejects fully visible near-border bands.
- [Nav2 SimpleGoalChecker source](https://github.com/ros-navigation/navigation2/blob/main/nav2_controller/plugins/simple_goal_checker.cpp): stateful XY acceptance with a separate reset buffer is the reference for entry/exit hysteresis. Here the buffer controls axis selection only; final RGB acceptance still requires all original bounds.

Local validation before physics:17 controller/probe tests passed after final
changes;20 catalog/planning tests passed. Both fully visible and endpoint-lost
pair fixtures reach hover through the real outer tick and motor stub; peer abort
still stops, PF measured keys unchanged. Cyan outer step preserves100ms forward,
issues hold at100ms and waits for the fresh settled frame. Central catalog and
sealed common60ms converter are byte-identical to the parent. No Mac physics.
