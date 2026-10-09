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

The initial frontend-only probe was abandoned after full-run parity failed
as described below. The admitted comparison uses the complete archived
controller and saved commands. S3 also uses its complete runtime. Neither
replay is a new closed-loop physical success.

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

### S3 C3 active-predictor correction (before corrected S3 replay)

The first S3 C3/v149 result still equaled C1 exactly. Its old pulse table
survived in a command closure, but slip initialization had installed a second
predictor using `flow.profiles`. The previous dictionary-identity test could
not prove actual consumption. That result and interrupted C3/v150 remain in
replays-v3 and are excluded as C3 evidence. Only our managed queue was stopped.

The shared module now follows the final AMCL predictor to its actual active
pulse cell. After the existing provider command selects a profile, C3 replaces
that selected immutable profile with the same independently calibrated alpha-Q
copy; loaded/lateral profiles and all means remain unchanged. This also retains
temporary rotation/slip selections instead of overriding their mean models.
The provider-command regression on all three real S3 factory instances now
checks changed particle propagation, not merely dictionary presence. Actual
own-map consumer regression remains in the same test file. No coefficients,
seeds, thresholds or candidates are added after results.

The next comparison view retains12 B/C1/C2 arms at105ffc70 and the two valid
own-map C3 arms atbfce6a01. Dependency bytes and consumer-scoped AST equality
are checked against both source commits. Only the two affected S3 C3 arms are
rerun on the next committed source; every receipt declares its own source.

## Saved-input comparison result

Sources: B/C1/C2 `105ffc70` (retained with byte/AST equivalence); own-map C3 `bfce6a01`; corrected S3 C3 `403f4e8bd661586716bed966aa4479e6c8229a5a` (per-arm receipts in comparison.json); four saved runs / eight trajectories, four settings, physics0. S3 sigma is sqrt(trace overall XY covariance); own-map sigma is sqrt(max XY eigenvalue). Full matching per-frame XY covariance is retained only for own-map; see the S3 covariance field audit below.

| Option | Trajectory | Frames | XY RMSE m | Final error m | RMS sigma m | >3sigma | Mean XY NEES | NEES >11.829 | False certificate frames |
|---|---|---:|---:|---:|---:|---:|---:|---:|---:|
| B | v149/r1 | 5249 | 0.155314 | 0.172448 | 0.383101 | 4647/5249 (88.53%) | unavailable | unavailable | 0 |
| B | v149/r2 | 5249 | 0.348725 | 0.387965 | 0.059634 | 4006/5249 (76.32%) | unavailable | unavailable | 2549 |
| B | v149/r3 | 5249 | 0.007660 | 0.007505 | 0.058307 | 0/5249 (0.00%) | unavailable | unavailable | 0 |
| B | v150/r1 | 6041 | 0.157667 | 0.172457 | 0.357218 | 5439/6041 (90.03%) | unavailable | unavailable | 0 |
| B | v150/r2 | 6041 | 0.356132 | 0.409033 | 0.056639 | 4798/6041 (79.42%) | unavailable | unavailable | 3236 |
| B | v150/r3 | 6041 | 0.007636 | 0.007449 | 0.058307 | 0/6041 (0.00%) | unavailable | unavailable | 0 |
| B | 55001/r3 | 1341 | 0.307760 | 0.707885 | 0.098310 | 651/1341 (48.55%) | 2463.280 | 52.87% | unavailable |
| B | 55002/r3 | 2528 | 0.265523 | 0.510407 | 0.094645 | 974/2528 (38.53%) | 13.189 | 46.99% | unavailable |
| C1 | v149/r1 | 5249 | 0.153699 | 0.170609 | 0.438275 | 4444/5249 (84.66%) | unavailable | unavailable | 0 |
| C1 | v149/r2 | 5249 | 0.360101 | 0.395757 | 0.168598 | 4316/5249 (82.23%) | unavailable | unavailable | 3507 |
| C1 | v149/r3 | 5249 | 0.016864 | 0.016664 | 0.473626 | 0/5249 (0.00%) | unavailable | unavailable | 0 |
| C1 | v150/r1 | 6041 | 0.156021 | 0.170617 | 0.408686 | 5236/6041 (86.67%) | unavailable | unavailable | 0 |
| C1 | v150/r2 | 6041 | 0.367463 | 0.421623 | 0.157182 | 5108/6041 (84.56%) | unavailable | unavailable | 4299 |
| C1 | v150/r3 | 6041 | 0.016834 | 0.016623 | 0.473626 | 0/6041 (0.00%) | unavailable | unavailable | 0 |
| C1 | 55001/r3 | 1341 | 0.657461 | 1.100318 | 0.135300 | 1064/1341 (79.34%) | 1336176.295 | 80.31% | unavailable |
| C1 | 55002/r3 | 2528 | 0.683394 | 0.346485 | 0.236155 | 816/2528 (32.28%) | 10.685 | 33.19% | unavailable |
| C2 | v149/r1 | 5249 | 0.154355 | 0.170448 | 0.470827 | 4047/5249 (77.10%) | unavailable | unavailable | 0 |
| C2 | v149/r2 | 5249 | 0.355198 | 0.382784 | 0.299580 | 4232/5249 (80.62%) | unavailable | unavailable | 2680 |
| C2 | v149/r3 | 5249 | 0.036099 | 0.035884 | 1.135440 | 0/5249 (0.00%) | unavailable | unavailable | 0 |
| C2 | v150/r1 | 6041 | 0.156559 | 0.170456 | 0.439311 | 4839/6041 (80.10%) | unavailable | unavailable | 0 |
| C2 | v150/r2 | 6041 | 0.361456 | 0.408984 | 0.279355 | 5024/6041 (83.17%) | unavailable | unavailable | 3472 |
| C2 | v150/r3 | 6041 | 0.036067 | 0.035851 | 1.135440 | 0/6041 (0.00%) | unavailable | unavailable | 0 |
| C2 | 55001/r3 | 1341 | 0.351851 | 0.537879 | 0.180721 | 147/1341 (10.96%) | 8.844 | 19.54% | unavailable |
| C2 | 55002/r3 | 2528 | 0.717722 | 0.347937 | 0.306479 | 731/2528 (28.92%) | 11.927 | 33.11% | unavailable |
| C3 | v149/r1 | 5249 | 0.157624 | 0.174596 | 0.440071 | 4271/5249 (81.37%) | unavailable | unavailable | 0 |
| C3 | v149/r2 | 5249 | 0.337278 | 0.376728 | 0.173943 | 3321/5249 (63.27%) | unavailable | unavailable | 1348 |
| C3 | v149/r3 | 5249 | 0.016864 | 0.016664 | 0.473626 | 0/5249 (0.00%) | unavailable | unavailable | 0 |
| C3 | v150/r1 | 6041 | 0.159952 | 0.174604 | 0.410465 | 5063/6041 (83.81%) | unavailable | unavailable | 0 |
| C3 | v150/r2 | 6041 | 0.344978 | 0.400220 | 0.162166 | 4113/6041 (68.08%) | unavailable | unavailable | 2110 |
| C3 | v150/r3 | 6041 | 0.016834 | 0.016623 | 0.473626 | 0/6041 (0.00%) | unavailable | unavailable | 0 |
| C3 | 55001/r3 | 1341 | 0.254971 | 0.272435 | 0.182393 | 113/1341 (8.43%) | 303846.874 | 18.87% | unavailable |
| C3 | 55002/r3 | 2528 | 1.061603 | 0.674377 | 0.165874 | 1832/2528 (72.47%) | 85.335 | 74.72% | unavailable |

The preregistered selection rule is unchanged. Selected smoke option: `off`.

| Candidate | Eligible | Failed checks | Pooled >3sigma |
|---|---:|---:|---:|
| C1 | False | 15 | 55.60% |
| C2 | False | 10 | 50.40% |
| C3 | False | 11 | 49.59% |

No candidate meets the consistency and no-error-deterioration gate. Observation tempering is not admitted for this smoke. This comparison does not establish correlated evidence as the sole cause or resolve overconfidence.

All input streams are fixed saved observations/issued commands; counterfactual controller proposals are logged but not substituted into the archived input stream. These compare reported beliefs from the complete controller under saved inputs, not new closed-loop success trials.

### Remaining instantaneous covariance collapse

Corrected C3/55001 lowers XY RMSE0.307760 ->0.254971m and scalar >3sigma
48.55 ->8.43%, but full XY NEES mean2463.28 ->303846.87 remains unacceptable
as a calibration claim. At62.1s, actual error0.201853m coexists with both XY
covariance eigenvalues equal1e-10m²: that report's NEES is4.074446e8.
The median improves12.8848 ->3.6137 and NEES>11.829 decreases52.87 ->18.87%;
neither removes that instantaneous failure. This is an observed covariance
collapse, not proof of a unique resampling or correlated-feature cause.
No floor, seed or threshold is tuned on this result. The preregistered gate
still applies to all eight trajectories; see [directional audit and source hashes](nees-direction.json).

### S3 covariance scope

`zone_solo_cyan_best_cluster.extract` publishes the maximum-mass cluster's
point estimate with the **overall filter** XY covariance trace. Its saved
`selected_cluster_cov` is a different matrix, not a complete per-frame record
of that published covariance. In B/v149, selected trace matches published
sigma on4965/5249 r1 frames,5016/5249 r2, and0/5249 r3; B/v150 has
5757/6041,5703/6041,0/6041. At13.34s r1's published sigma is1.840407m
while the selected-cluster value is0.060478m. Substituting that matrix into
NEES would change the uncertainty definition. The S3 comparison therefore
retains its preregistered scalar >3sigma metric; full matching XY NEES is
calculated for own-map only. No gate, window or coefficient changes.
[Covariance field audit and source hashes](covariance-scope.json).

### Complete-controller replay scope

The archived own-map controller includes causal route matching and its original
per-leg budget. It may stop assimilating RGB after a counterfactual terminal
state while the harness continues delivering the fixed original command/frame
stream. The table therefore measures the controller's reported belief under
saved inputs; its row count does not establish a fresh visual update on every
row. These are not closed-loop physical trajectories or a pure isolated
likelihood-function benchmark. Controller proposals never replace the archived
issued commands, and the original policy/budgets are not overridden.

C1/55002 proposes only hold for the final1,188 rows after its last nonhold at
271.1s. No unrecorded terminal flag is inferred from hold commands alone.
Before that suffix (1,340 rows), baseline/C1 XY RMSE is0.200207/0.522878m,
endpoint error0.417529/1.252930m and >3sigma fraction22.09/28.21%.
C1/55001 has only one final hold row; its corresponding prefix RMSE is
0.307267/0.657019m. Thus C1's rejection does not depend on scoring the long
hold-only suffix. This extra diagnostic does not replace the preregistered
full-stream selection window or alter any threshold/coefficient.
Evidence: `outputs/s3fix6-20261010/c1-hold-prefix-audit.json`.

Corrected C3/55002 also has1188 final hold-only proposal rows. Before that
suffix (1340 rows), RMSE is already0.200207m B vs0.888301m C3 and >3sigma
22.09% vs48.06%. Its degradation therefore is not explained solely by that
suffix. The full-stream selection and original controller budget are unchanged.
The linked evidence now contains all six own-map candidate/baseline prefix
comparisons; hold proposals alone do not establish a specific terminal flag.

### Actual score coverage

C1's S3 likelihood hook is active on every recorded scored update: v149
r1/r2/r3 have17/66/8 calls, v150 has17/72/8. All calls have N>=2, so none
is an identity N=1 call. For r2,62/66 and68/72 calls use N=5 (one existing
wall aggregate plus four floor/door features). The negative result is not
explained by an option that never reaches the scoring boundary.

The existing S3 update is motion-triggered AMCL; thousands of pose-report
rows are not thousands of independent visual likelihood updates. Observation
counts and temporal independence are not inferred from publication frequency.
This audit proves hook coverage, not a single causal explanation for overconfidence.
Evidence: `outputs/s3fix6-20261010/c1-effective-count-audit.json`.

### Error was present at the latest scored update

In B/v149, r1's latest visual weight update is86.45s (last drive86.4s).
The first report after it already has0.173157m error with0.024689m sigma;
its final values are0.172448/0.024701m. Actual displacement after that
report is only0.003394m (predicted0.000781m), too small to explain the
0.172m endpoint error as later passive drift. r2's latest update at275.3s
already has0.386255m error with0.005358m sigma, before ending at
0.387965/0.005400m. Thus the end overconfidence is not explained solely
by a long absence of new visual updates. These are timeline/scale checks,
not a proof that correlated likelihoods are the unique cause. No coefficients
or selection criteria are changed. [Six baseline timeline rows and hashes](last-update-audit.json).

## Forward pulse discrepancy (evaluation only)

Same issued pulse (forward .35, duration .10 s), unloaded/open grip and
commanded servo posture 2000/740/2320/1320/1500 in all compared pulses.
The drive-v7 receipt differs only in scene XML hash; other physical fields match.
In the original .20 s calibration-response window, S3 r2 has 254 pulses,
3.282547 m predicted /2.842355 m actual (1.154869). Beam-contact windows are
34/254: body-forward residual .228261 m, versus .227661 m in220 noncontact
windows. Thus about half of the body-forward discrepancy is concentrated
in beam contacts, before any successful lift; it is not carried-load evidence.

Noncontact consecutive-forward pulses differ in cadence: S3 .4 s spacing,
208 pulses, ratio1.088762; own-map .2 s spacing,197/215 pulses, ratios
.984674/.988431. Own-map fullforward ratios are1.005301/1.011928.
Extending the evaluation response window to .3/.4 s (clipped at the next
motion) leaves S3 allpulse ratios1.143418/1.167388; omitted settling travel
alone does not explain the discrepancy. Command duration is identical.
Contact and pulse-response context are supported factors; the remaining
noncontact cadence association is not an isolated causal experiment. No
coefficient is fit from these evaluation truth records.

Raw audit: `outputs/s3fix6-20261010/forward-audit-v2/summary.json`,
`forward-window-audit.json`, `forward-servo-audit-v2.json`.
The first servo-audit file omitted arm/look handling and is superseded by v2.

Sampling limitation: S3 truth is recorded every 0.05 s (5,553 samples); own-map truth every 0.20 s (1,351/2,538 samples). The shared 0.20 s endpoint comparison is supported; a sub-pulse wheel/start-velocity causal attribution is not resolved by these saved own-map traces. No interpolated sub-pulse motion is treated as an observed measurement.

Issued-command interruption check: all254 S3 and278/356 own-map forward pulses retain the complete0.10s interval before any subsequent hold/motion command; early interruption0 in allthree. This rules out a shorter interval in the issued-command log, not every possible actuator/solver effect. Evidence: `forward-hold-audit.json`.

## v151 admission before physics

One `zone-s3-consistency-v151` / `7.44.0` dev_light smoke, seed14201.
`pose_validity=defer_unmeasured_v1` is on; observation option is sealed in
[registration](registration.json) from [comparison](comparison.json).
Existing heading/v3 host mount/coupled-carry lateral exception/pre-GO rewait
and v149 exact cache remain unchanged. The archived own-map production CLI
is not changed or admitted by this S3 decision. No thresholds, seeds, means,
or outcome-based coefficients change. Raw budget4GiB plus10GiB reserve;
1800SIM/10800wall seconds, one admitted physical attempt, ENOSPC=HOST_ERROR.

Off regression: own-map all1341/2528 poses, covariances, RGB contacts and
proposals reproduce the original. S3 v149 all3×5493 poses match; its11036
proposals match the original prefix, excluding four host termination/settling
holds. v150 all original12409 commands match as a prefix; only the last
invalid r2 pose is repaired, plus three final hold proposals. The repair
retains the last visual-fix time300.4s, does not issue a new convergence
certificate, and produces no nonfinite record fields. See
[baseline admission and raw hashes](baseline-admission.json).

Candidate comparison rows are temporally correlated reported beliefs, not
independent Bernoulli trials. False certificate counts count frames rather
than independent convergence episodes. Values from S3 and own-map use their
original distinct sigma definitions; the pooled gate is the preregistered
selection statistic and does not establish a calibrated shared coverage law.

Bundle reservation: [main and all open PR refs](bundle-reservation.json), maximum150 ->151 immediately before admission.

Pre-execution local validation:24 PASS in38.35s across only the three changed
test files;68 offline stage cases,3192 motor-stub commands,zero errors including
None/NaN and unmeasured-camera paths. Registered workflow plan and non-executing
runner both pass. Original root catalog remains byte-identical to main.
[Validation and tested source hashes](validation.json), [sweep](offline-sweep.json).
