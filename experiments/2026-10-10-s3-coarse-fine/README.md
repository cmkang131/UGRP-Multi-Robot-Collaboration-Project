# S3 s3fix15: stopped-base / own-RGB arm fine alignment

2026-10-10 DEV tuning, PR #416 DRAFT, **v161 /7.54.0** (remote main/open
branches maximum v160 scanned before reservation). Default `off` preserves
existing controllers, postures, calibration and physics. No CI wait/merge.

## Preregistration (before new outcomes)

Use previous s3fix14 as calibration only, never as confirmatory evidence. Its
independent dx/yaw slices do not prove a joint rectangular capture volume.
These ten previously used initial conditions are a development regression
cohort, not fresh confirmation. Same oracle-x86/OSMesa, LP_NUM_THREADS=4,
OMP_NUM_THREADS=1, maximum ten simultaneous S3 jobs, each60SIM seconds,
heading on for solo/approach; coupled beam carry retains lateral exception.
No Mac physics/render/replay, no GT/dock prior/shared top/weld control.

Frozen controls, selected before results:

|quantity|previous capture slices|new halfwidth / rule|minimum chassis step compatibility|
|---|---|---|---|
|pair dx|±24mm|±18mm (6mm margin)|max35/100ms16.686mm <18mm|
|cyan dx|±12mm|±9.6mm after arm correction|16.686mm >9.6mm: body-only fails; bounded radial arm correction required|
|pair relative yaw|±.14rad|±.112rad|conservative previous max+spread .101447rad <.112|
|dy|-12…0mm at nominal dx/yaw|centre−6mm, halfwidth3mm|body step unsuitable; servo6 correction|

This is a **new** controller/acceptance preregistration; the previous grid's
max+spread22.354mm forward sufficient condition is not silently passed.
Pair now uses measured max16.686mm against18mm; uncertain coupled capture
and drift are tested by the new cohort, not assumed safe/guaranteed.
Cyan radius from own RGB is limited to148…170mm about the arm yaw joint
(existing calibrated IK envelope145…180mm), sampled every0.5mm and filtered
by SDK IK reachability and <=2mm XY departure along the vertical descent,
<=75mm descent. Final residual stays±9.6mm.
The pure command-space IK test admits28 radii148…161.5mm at0.5mm spacing;
161.5…170mm candidates that fail the full vertical path are excluded.
Pair keeps155mm radial posture; only its commanded yaw changes.
Body coarse selection enumerates up to3 existing ±35/100ms forward/turn
pulses, issues one axis/pulse then >=.5s coast/new-frame reobservation.
No invented sub100ms pulse and no15/20/25 command. No fine lateral base pulse.

Once an arm-reachable grasp region is visible, hold base. Solve servo6 from
own RGB grip coordinate: theta=atan2(y,x−mount)−asin(−.006/r).
Quantize pan to4µs, restrict1300…1700 (±18°). Command .30s and settle.45s,
then require two distinct fresh valid own frames whose residuals meet the
above bounds. Integer target rounding is command resolution, not measured
servo accuracy. Existing SDK IK makes cyan radial correction at visible
standoff; after this reference, hover/descent are open loop because the
cargo may be hidden at hover. Never call hidden hover a new visual fix.
Fine pan uses only the fixed camera mount and command-space rotation about
the known yaw joint; per-instance local RGB camera table only, PF unchanged.
Unmeasured PF views remain prediction-only; no old video-fitting extrinsics.

Existing pair hover/close/lift mutual GO, fixed age/blind command envelope,
real drop/tilt/contact abort, and dev_light sigma logging remain. New own-RGB
reference supplies the dynamic commanded hover/descent path. Low lift uses
that path; the existing HIGH transition/carry follows unchanged.
Runtime live GT/contact never supplies a correction or stage success receipt.
−6mm is a frozen **SIM calibration constant**, no live coordinate offset.
Its transfer to arbitrary yaw/radial conditions and real hardware is unproven.

## Frozen batch

[batch-plan.json](batch-plan.json): pairc0–c5, cyanc0/c3/c4/c5,
seeds14201–14206 matched to condition, names` s3fix15-CASE-cC-r1`.
All ten submitted together after all edits/tests; no mid-batch tuning.
Optional one5SIM-second path check, excluded from ten-case denominator.
Execution errors/HOST_ERROR and ENOSPC recorded, raw originals preserved.
Memory admission refusal waits then retries same frozen list.

```
ORACLE_HOST=oracle-x86 oracle_run.sh WORKTREE s3fix15-batch-r1 -- .venv-sim/bin/python -m scripts.run_s3_coarse_fine_cohort --expected-source-sha SHA --output outputs/s3fix15-batch-r1/cohort --execute
```
Each row expands to `.venv-sim/bin/python -m scripts.run_s3_coarse_fine_probe
--expected-source-sha SHA --output outputs/NAME/raw --case CASE --condition C
--coarse-fine stopped_base_arm_v1 --execute`.

Frozen evaluations: alignment = two fresh RGB residual passes and reference
receipt; grasp = bilateral finger contact after close; lift = cargoCOM>.06m
with both fingers (pair both robots) for>=.20s; carry = entered carry state
AND>=.02m XY cargo displacement while contact-lifted. Report entry separately
from physical movement. n/N per robot(pair6 each/cyan4), pair joint6 and
all10 cases, cyan c0 regression explicit. Count consecutive nonzero chassis
turn sign reversals, stage timestamps, physical stop, wall/SIM. A synthetic
stage receipt never proves original mission approach/location success.

## References (checked2026-10-10)

- [Hiwonder MasterPi product](https://www.hiwonder.com/products/masterpi?variant=39783006961751):
  LD-1501MG and LFD-01M servo family;4DOF+gripper. Installed specimen is not newly measured.
- [Official MasterPi tracking code](https://wiki.hiwonder.com/projects/MasterPi/en/latest/docs/9.ai_vision_project_course.html):
  §5.5 ID3/ID6 integer PWM from own image x/y PID, motor stop before arm-only mode;
  command range500…2500. §5.3 shows base yaw servo6. Used only the arm mechanism,
  not the official example's low wheel speeds or its unrelated tracking success.
- [Official MasterPi IK course](https://wiki.hiwonder.com/projects/MasterPi/en/latest/docs/7.basic_course_kinematics.html):
  articulated-arm coordinate geometry, IK and PWM control interface.
- [Hiwonder LD-1501MG specification table](https://www.hiwonder.com/products/ackermann-steering-chassis):
  same named servo,500…2500µs→0…180°, advertised precision0.3°.
  Derived SDK grid1µs=.09°, candidate4µs=.36°≈.974mm at155mm radius;
  advertised0.3°≈.812mm, both <3mm halfwidth. Manufacturer spec is not our
  loaded/installed servo repeatability calibration. No actual hardware commanded.
- [Kragic et al., Systems integration for real-world manipulation tasks, ICRA2002](https://faculty.cc.gatech.edu/~hic/hic-papers/icra-02-intg.pdf):
  mobile manipulation split into coarse-to-fine subtasks and wrist-camera visual
  servoing. Retrieved abstract/index text; PDF rendering unavailable in browser.
- [CFVS,2022](https://arxiv.org/abs/2209.08864): coarse then iterative fine visual
  alignment with an eye-in-hand sensor in assembly. We adopt staged feedback,
  not its learned point-cloud model or reported success rates.
- [Hutchinson/Hager/Corke1996](https://faculty.cc.gatech.edu/~seth/ResPages/pdfs/HutHagCor96.pdf):
  calibrated image/pose servo and look-then-move; no stability guarantee transferred.

## Results

Prepared before physics:8 controller/runner tests + catalog plan passed;
subsequent guard/receipt changes verified by4 targeted tests (pair and cyan
real motor-stub ports, contiguous contact evaluation, IK radial grid).
Catalog runner mapping rechecked after its correction. Source/receipt and raw
n/N will be appended after the whole batch.

Storage admission: raw unchanged. Six inactive immutable own S3 git-archive
source caches deduplicated by identical relative path/mode/size/fullSHA using
hardlinks;35,377 source files,6,100,575,734 duplicate bytes. Full receipt under
`outputs/oracle-runs/s3fix15-storage-record/source-dedup.json`; no run outputs,
venv, live source, process or worktree removed. Free space15GiB before shipment.


### Completed frozen round — source `4e19382d59a9bb2bbf351a7fca1356cdf480e8a0`

All10 submitted together and completed on oracle-x86, LP4/OMP1/nice0;
60SIM s each, HOST_ERROR0, physical abort0, model calls0. The sole5SIM
pathcheck passed and is excluded. No outcome-driven threshold/code change.
**Candidate not adopted; default remains off, PR #416 DRAFT.**

|denominator|alignment|bilateral grasp|contact lift|physical carry >=20mm|
|---|---:|---:|---:|---:|
|r1 (pair)|0/6|0/6|0/6|0/6|
|r2 (pair)|0/6|0/6|0/6|0/6|
|r3 (cyan)|2/4|2/4|2/4|2/4|
|pair joint|0/6|0/6|0/6|0/6|
|all cases (pair joint or cyan)|2/10|2/10|2/10|2/10|

Cyan c0 regression recovered versus s3fix13; c5 also passes. This is a
new development regression with changed gates, not fresh confirmation of
s3fix14 calibration. Neither synthetic stage entry nor cargo carry here
proves mission approach, B delivery, return, S3 E2E, or real hardware.

|case|alignment / hover|descent / close|contact lift / carry entry|contact-lifted XY|turn reversals|wall/SIM|
|---|---|---|---|---:|---:|---:|
|pair-c0|— / —|— / —|— / —|0.000m|0|374.67/60 = 6.24|
|pair-c1|— / —|— / —|— / —|0.000m|0|343.72/60 = 5.73|
|pair-c2|— / —|— / —|— / —|0.000m|0|371.14/60 = 6.19|
|pair-c3|— / —|— / —|— / —|0.000m|0|372.60/60 = 6.21|
|pair-c4|— / —|— / —|— / —|0.000m|0|322.02/60 = 5.37|
|pair-c5|— / —|— / —|— / —|0.000m|0|340.40/60 = 5.67|
|cyan-c0|4.75 / 4.75|6.05 / 7.25|8.95 / 29.95|0.685m|0|401.22/60 = 6.69|
|cyan-c3|— / —|— / —|— / —|0.000m|116|402.53/60 = 6.71|
|cyan-c4|— / —|— / —|— / —|0.000m|115|403.35/60 = 6.72|
|cyan-c5|8.75 / 8.75|10.05 / 11.25|12.95 / 33.95|0.565m|8|418.99/60 = 6.98|

Times above are raw world SIM timestamps; stage start=2.35s. Cyan c0/c5
alignment elapsed=2.40/6.40s, hover then blind descent then close;
contact-lift samples1069/989, maximum COM height0.1607/0.1635m.
Original `fine_pan_commands` in evaluator-v1 counts event appearances
(cyan record repeats the same event in two containers); do not treat it as
physical actuator pulses. Raw command-based turn reversal counts above are
unaffected; cyan each successful case has one unique fine-pan decision.

### Remaining causes — measured before another change

- **Pair endpoint visibility:8/12 robot-cases.** r1 c0/c1/c2/c3 has end-visible
  only2/461,1/464,3/457,3/457 frames; r2 c0/c2/c3/c5 only6/445,7/441,6/445,4/453.
  Beam body visible100%, but endpoint detection is no longer accepted after
  coarse approach, so the own-RGB gate supplies no new alignment receipt.
  Actual occlusion versus segmentation/geometric rejection remains unseparated.
  Last accepted residual yaw0.11267…0.16507rad often still exceeds0.112;
  no post-outcome widening. Four-corner capture slices did not establish
  visibility along this closed-loop path.
- **Pair arm/PF posture ownership conflict:4/12 robot-cases.** c1r2,c4r1,
  c4r2,c5r1 request fine pan39/40/39/40 times but existing
  `zone_pair_highpose_posture_defer.DeferRelook.tick/_v98_restore` restores
  pan1500 from the private local-vision pan38/39/39/39 times. Example c4r1:
  commanded1544 at3.80s; `align_posture_restore` at3.90s targets1500.
  These views are deliberately not registered as measured PF views. The
  motor-stub regression called `_align` directly and missed the outer tick
  conflict. This is an unresolved integration bug, not successful fine servo.
- **Cyan coarse yaw cycle:2/4 cases (c3,c4).** Each issues119 coarse decisions;
  residual dx26.591/28.135mm remains outside9.6mm, with turn sign reversals
  116/115. Successful c5 still has8 reversals before convergence, c0 has0.
  Pair chassis reversals0. Total reversal count239; oscillation was not
  eliminated for all conditions by this candidate.
- Disjoint case outcomes:cyan2 success; cyan2 coarse cycle; pair3 lose both
  endpoints, pair2 have one lost endpoint+one pan restore, pair1 has two pan
  restores. All finish at the60s horizon; no new physics round was started.

Speed: sum measured run wall3750.63s /600SIM=6.25 (per case5.37…6.98),
concurrent driver elapsed444.89s including startup. Nested host timers:
render1147.49s, physics1016.59s, capture including render/I/O1236.97s,
JSONL append10.47s. Three cameras at20Hz plus three-robot physics dominate
these measured host costs; residual includes controller/init/evaluation and
was not separately profiled here. No optimization or single-run benchmark
claim; wall values from simultaneous jobs must not be summed as batch latency.

Next proposed round: test the full pair tick with private local arm views
while retaining PF prediction-only, preserve endpoint visibility during
coarse approach, and register a non-cycling coarse action rule before new
probes. The current2/10 result remains attached to the original SHA.

Raw: `outputs/oracle-runs/s3fix15-batch-r1/cohort/NAME/raw/`;
post-run reports/videos: `outputs/oracle-runs/s3fix15-eval-r1/evaluation/`.
[results.json](results.json) binds raw paths and report hashes. Originals and
4× saved-RGB videos retained; no Mac physics/render/controller replay.

### Delivery verification

Retrieved ten raw manifests: **36354 files, every SHA256 matched**.
Pathcheck335 files independently matched. Oracle evaluator exit0 and all ten
4× videos decoded at20fps with saved-frame counts matched.
New immutable TensorBoard snapshot `1010-s3fix15-coarse-fine-v1`:12 views
(ten cases + count aggregate + excluded pathcheck),244 scalar tags and10
registered videos; event reload and media HTTP206 range checks passed.
[Open pinned TensorBoard](http://127.0.0.1:6006/?runFilter=%5E1010-s3fix15-coarse-fine-v1%2F&pinnedCards=%5B%7B%22plugin%22%3A%22scalars%22%2C%22tag%22%3A%22offline%2Falignment%22%7D%2C%7B%22plugin%22%3A%22scalars%22%2C%22tag%22%3A%22offline%2Fgrasp%22%7D%2C%7B%22plugin%22%3A%22scalars%22%2C%22tag%22%3A%22offline%2Flift%22%7D%2C%7B%22plugin%22%3A%22scalars%22%2C%22tag%22%3A%22offline%2Fcarry%22%7D%2C%7B%22plugin%22%3A%22scalars%22%2C%22tag%22%3A%22offline%2Fn%22%7D%2C%7B%22plugin%22%3A%22scalars%22%2C%22tag%22%3A%22offline%2Fhost_errors%22%7D%2C%7B%22plugin%22%3A%22scalars%22%2C%22tag%22%3A%22result%2Fwall_s%22%7D%2C%7B%22plugin%22%3A%22scalars%22%2C%22tag%22%3A%22result%2Fcommands%22%7D%2C%7B%22plugin%22%3A%22scalars%22%2C%22tag%22%3A%22result%2Fmodel_calls%22%7D%5D&smoothing=0#timeseries); baseline s3fix13 is kept separately in
`outputs/tensorboard-view.json:s3fix15_20261010`. Chrome 강 display verified:12 selected views,9 pinned cards, displayed
alignment/grasp count2; HParams case/policy/seed/source_sha reapplied.
Representative cyan c0 video played to15.00s end without error.
Source and result docs are separate commits; physics source remains4e19382d.
CI not awaited; no merge.
