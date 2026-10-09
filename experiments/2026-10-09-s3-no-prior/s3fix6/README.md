# s3fix6: numerical validity and posterior consistency

Preregistered 2026-10-10, before candidate replay results. Exploratory DEV
replays, not a new independent success cohort. Seed and stopping thresholds
stay unchanged. Evaluation truth is read only by the separate evaluator.

## Inputs and comparison rule

Four saved runs / eight trajectories: S3 v149 and v150 (r1, r2, r3), and
goal-route-motion-audit-v1 seeds 55001 and 55002 (r3). Replay each original
own RGB and issued-command stream. Own-map retains its own inferred maps;
no S3 static map, live pose, or evaluation residual enters either filter.
First reproduce baseline poses/commands, including the v150 invalid-pose
failure. Numerical repair B is evaluated separately from sensor changes.

Candidates in one shared, default-off observation-consistency module:

* C1: temper the existing whole observation log score by 1/sqrt(N).
* C2: temper it by 1/N.
* C3: C1 plus alpha1--alpha4 process covariance from the existing independent
  pulse calibration residual fit (s3fix5), including forward pulses.

N is the score's existing effective evidence count, never a truth-derived
quantity: S3 uses one cubic-sum wall aggregate (if nonempty) plus the number
of distinct floor/door features; own-map uses min(number of endpoints, 12),
the existing robust likelihood's effective-point cap. N >= 1. S3 walls
already use the Nav2 cubic accumulator, not a product of individual beams;
own-map already caps the sum at 12 points. These candidates test additional
tempering, not an assertion that those mitigations are absent. No tuning
after seeing these eight trajectories. Random seeds and calibration means
are unchanged by C1/C2; C3 adds covariance only, not GT correction.

Selection: first require no invalid poses and no increase in XY RMSE or
last-frame XY error on any of the eight trajectories relative to repaired
baseline B (numerical tolerance 1e-9 m). Then require no increase in >3-sigma
fraction on any trajectory and a strict decrease in the pooled fraction.
Among eligible candidates minimize pooled >3-sigma fraction, then RMSE,
then prefer C1, C2, C3 in that order. If none qualify, retain off for the
single smoke and report the failed hypothesis; do not weaken this rule.
S3 comparison starts at t_est >= 13.34 s, through each saved run's end;
own-map uses its original local-coordinate evaluation gauge and every
recorded frontend pose with matching truth. Report frame counts, invalid
frames, actual errors, RMS uncertainty and >3-sigma together. Full XY NEES
is supplementary where the full matching covariance is available; do not
call scalar error/sigma a full covariance NEES.

## Numerical and integration gates

Trace the first nonfinite arithmetic in v150 before prescribing its repair.
Keep frozen historical sources intact. Normal finite input with options
off must preserve values, RNG and command bytes. Reject/record invalid
sensor updates explicitly, preserving the finite predicted belief rather
than silently inventing a pose. Add None/NaN stage cases through the real
motor-stub port and retain hard execution failure when no finite belief
exists. Formal conservative stops remain enabled outside dev_light.

Only after the offline sweep and relevant local tests pass: commit/push,
reserve the next bundle ID across main/open PR branches, and run one
dev_light smoke after the speedctrl exclusive replay slot. Keep v3 host
mount, single-robot heading, coupled-carry sideways exception and pre-GO
rewait. No dock prior, weld, shared top camera or GT control. Record every
failure and would_stop, per-robot localization/stages, wall/SIM and video.
Do not wait for CI or merge PR #416.

## Primary references

* Thrun, Burgard, Fox, Probabilistic Robotics, chapters 5.4, 6.3/6.4:
  https://robots.stanford.edu/probabilistic-robotics/ (author page verified;
  chapter text not retrieved here; chapter pointers supplied by supervisor).
* Nav2 likelihood-field model: cubic accumulator and beam subsampling:
  https://api.nav2.org/nav2-rolling/html/likelihood__field__model_8cpp_source.html
* Nav2 probability model: log accumulation and convergence-gated beam skip:
  https://api.nav2.org/nav2-rolling/html/likelihood__field__model__prob_8cpp_source.html
* Existing independent alpha fit and provenance: ../s3fix5/README.md.

## First invalid report (before candidate comparison)

Exact archived replay reproduced all 12,409 issued commands. With NumPy
invalid/divide/overflow set to raise, no floating arithmetic fault occurred.
At 315.3 s the provider rejected the issued, unmeasured camera posture
`unloaded:1072,2400,1482,1630`; fail-closed reporting created an uninitialized
NaN/inf pose, released at315.5 s, and the sweep dereferenced its None conversion.
This is a camera-availability/invalid-pose integration bug, not weight collapse.
[Trace evidence](first-invalid.json). B skips only such unavailable measurements,
retains normal command prediction without a fresh fix, and records would_stop.
It never changes a camera extrinsic or supplies a saved/GT pose. Unknown provider
failures remain hard and records explicitly carry null plus invalid-field paths.
The None/NaN sweep takes the unchanged bounded wait, never nominal geometry.

Own-map replay uses the actual frontend observation and issued-command boundary
without navigation/virtual forecast work. The first50 off poses/covariances and
RGB-derived contacts reproduce the raw exactly; full-run parity is required.
This isolates the filter and avoids truncation when a counterfactual planner
would finish early. S3 uses the complete runtime with saved issued commands.
Neither replay is a new closed-loop physical success.

### Replay completeness correction, before any candidate results

The initial frontend-only off replay matched its first424 rows, then differed
at88.1s: `GoalRoute._localize` applies a causal own-image graph match to every
particle and rotates pending covariance. The isolated frontend omitted this
feedback. Its full1341-row result is invalid for candidate comparison and is
preserved under `outputs/s3fix6-20261010/replays/55001-off`. Full RGB contact
records still matched. The replay now calls the complete original controller,
including route matching and map feedback, and requires both all frontend
poses/covariances and command proposals to match. No candidate results have
been inspected; candidates and selection rule are unchanged.

Timing-slot correction: after the failed frontend-only replay released its
lock, a full-path probe was mistakenly started without acquiring the lock.
On detecting speedctrl PID72922's timing-sensitive slot, only our probe
PID72986 was stopped immediately; no other process or lock was changed.
The startup overlap was disclosed on PR423 ([comment6084754741](https://github.com/cmkang131/UGRP-Multi-Robot-Collaboration-Project/pull/423#issuecomment-6084754741)). Its incomplete local directory
and managed log are retained. All subsequent heavy probes/replays wait at
atomic acquire; no speed claim uses this overlap.

### C3 own-map consumer correction (before corrected replay)

The first C3/55001 result was identical to C1 because the GMapping
`_command_propagate` intentionally discards pulse-table Q. Editing that table
had not changed cloud covariance. That result and the interrupted55002 arm
are preserved in `replays-v2` but excluded as C3 evidence. Only our managed
queue was stopped; speedctrl's owner yielded its slot and remains paused.

C3 now applies the same independently fitted alpha1--alpha4 at the existing
GMapping own-observation delta boundary, taking the elementwise maximum of
its diagonal Q and existing diagonal GMapping Q. This preserves the old floor
and avoids counting pulse Q twice. Callback scope comes from issued unloaded
forward/turn profiles only; loaded/lateral intervals keep original Q. Means,
RNG order, coefficients, thresholds, N and selection rule are unchanged.
The actual archived PulseOdometry -> callback -> GMapping advance functions
are a regression fixture, proving Q reaches particle pending covariance and
that repeated-time advance, unsupported scope and other instances stay intact.
OpenSLAM's existing delta-based noise boundary was checked directly:
https://raw.githubusercontent.com/ros-perception/openslam_gmapping/master/gridfastslam/motionmodel.cpp

The12 complete B/C1/C2 arms retain source105ffc70. Their replay scripts and
runtime dependency bytes must match; the only shared-module change is an
own-map C3-only branch/helper, checked by AST equivalence outside that branch.
Corrected C3 runs use a new committed source recorded per receipt. A fresh
`replays-v3` comparison view references immutable old results and new C3
results; it does not overwrite or silently relabel invalid results. This is
a consumer wiring repair after detecting missing treatment, not parameter
tuning. No physical run has been made for s3fix6 yet.
