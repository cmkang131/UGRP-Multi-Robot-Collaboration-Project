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
