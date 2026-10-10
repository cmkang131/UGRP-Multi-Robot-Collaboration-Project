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
