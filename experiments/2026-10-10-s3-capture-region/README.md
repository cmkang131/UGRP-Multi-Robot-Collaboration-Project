# S3 s3fix14: grasp capture region and actuator resolution

2026-10-10, DEV tuning diagnostic. PR #416 remains DRAFT; no CI wait/merge.
Remote refs scanned before reservation: maximum v159; reserve **v160 /7.53.0**
for the evaluation-only diagnostic. Existing registered files/defaults remain unchanged.
Host **oracle-x86**, OSMesa, MuJoCo3.12, LP_NUM_THREADS=4, OMP_NUM_THREADS=1,
at most10 S3 subprocesses. No physics/render/replay on Mac. ENOSPC/execution errors
are HOST_ERROR. Memory admission refusal waits then resubmits the same immutable list.

## Measurement plan fixed before results

[diagnostic-plan.json](diagnostic-plan.json) lists every name, seed, command flag.
All15 jobs are submitted before reading outcomes; fixed queue of10 (no SIGSTOP/nice).
Nine capture jobs: r1/r2/r3 × yaw(-.14,0,.14)rad; each contains the full
5×5 dx/dy grid (-24,-12,0,12,24)mm = **75 attempts/robot,225 total**.
dx/dy are object grip-centre errors in the rotated robot base frame, the same
coordinates as RGB alignment; dyaw rotates about the nominal grip point.
The setup solves base_xy = grip_xy - R(yaw)*(grasp_radius+dx,dy). This avoids
mistaking the203mm yaw lever arm for independent translational capture tolerance.
Pair partner is nominal and executes the
same synchronized tape, so these are **conditional individual capture regions**,
not proof that two arbitrary errors can be combined. Cyan is single-robot.
Existing stage fixture supplies scene only. The evaluation-side setup places the
robot at the static grasp convention plus the defined grip-frame offset; no pose/contact is supplied
to a student. There is no student controller in this diagnostic.

Fixed existing `ArmSequence` eased hover1s, seven0.12s descent steps, existing
hover settle, close0.5s+0.4s settle, low-hover lift1.2s+2.8s settle; finish at12SIMs.
No weld, base motion, live IK retarget, feedback correction, or success-driven retry.
**Grasp:** tested robot both fingers touching in >=4 samples (0.20s) between
close-ramp end and lift start. **Lift:** every sample in final1s has cargo COM>.06m
and both fingers of all carriers touching. Both criteria required for capture.
Actual tilt/drop/nonfinite stop is a physical failure; other exceptions HOST_ERROR.
Nominal0-offset captures own RGB at5Hz as representative raw; all attempts preserve
command tape, contacts, trajectory, cargo truth, outcome, hashes. Grasp/lift diagnostic
is not alignment, transport, E2E, or real-hardware success.

Six pulse jobs: conditions0–5, seeds14201–14206, each same fixed list of48 actions:
2 repeats × levels15/20/25/**35 reference** × forward/left/turn × signs±,
100ms drive then900ms native-expiry rest (48SIMs). All3 robots measured together
in the existing empty-room setup, inspect posture. Body displacement at10ms grid,
no outcome-dependent pulse or origin reset. Report signed response, cross-axis drift,
median/range and rest drift. Low-speed capability is diagnostic-only and rejects
`student_control != false`; the normal port contract is unchanged.

Command template (each row substitutes its name/kind/condition/flags):
```
.venv-sim/bin/python -m scripts.run_s3_capture_diagnostic --expected-source-sha SHA --output outputs/NAME/raw --kind KIND --condition C FLAGS --execute
```
Whole batch:
```
ORACLE_HOST=oracle-x86 oracle_run.sh WORKTREE s3fix14-diagnostics-r1 -- .venv-sim/bin/python -m scripts.run_s3_capture_cohort --expected-source-sha SHA --output outputs/s3fix14-diagnostics-r1/cohort --execute
```
Optional **one8SIM pathcheck**, nominalr3 open-loop tape. If infrastructure/contract
failure, fix and retest once; it does not tune the grid or count as a research unit.

## Selection rule fixed before diagnostic outcomes

1. **Hardware floor:** repository physical reference explicitly records wheel commands
   <=30 do not move the chassis; use35. Thus15/20/25 are measured but **ineligible** for
   control even if SIM residual motion is nonzero. Official SDK accepts a range but
   does not provide measured deadband; no conversion of SDK argument range into
   physical minimum. See sources below.
2. For each robot, consider origin-centred boxes bounded by measured XY levels and
   yaw±.14. Require every tested grid point inside the box to grasp AND sustain lift,
   including nominal. Select maximum-volume such box; ties choose smaller x, then y.
   Missing/error points fail qualification. Shrink each halfwidth to**80%** as margin.
   This is a finite-grid DEV estimate, not a proof of all unmeasured interior poses.
3. Effective robot/object alignment halfwidth must contain the worst measured absolute
   relevant-axis35/100ms step (all6 conditions and both signs) plus residual spread.
   Conservatively use maxstep + (maxstep-minstep). Full width>=2×this bound.
   This is an explicit sufficient engineering rule for a scalar quantized loop,
   **not a universal theorem** claiming every smaller interval must oscillate.
   Existing 3mm/0.035rad thresholds are retained in default-off code.
4. If no hardware-valid pulse fits the conservative capture box, mark candidate
   **NOT_ADMISSIBLE**; do not fake movement at15/20/25, widen beyond capture evidence,
   or silently shorten100ms. Report the precise incompatible bounds. A ten-case
   candidate is only launched after a concrete admissible profile and its hashes
   are preregistered; otherwise all10 are recorded blocked with this cause.
5. If admissible, freeze new default-off profile and all downstream alignment/hover/
   fixed-posture gate tolerances consistently before the10-case DEV batch. Keep fresh
   RGB/settling/hysteresis/one-axis behavior, heading on except joint beam carry.
   Pairc0–c5 + cyanc0/c3/c4/c5, each<=60SIMs, one batch. Cyan c0 regression mandatory.
   Use **n/N** for reached alignment, grasp, lift, carry. Never call tuning data confirmatory.

## References (checked2026-10-10)

- [Hiwonder MasterPi official motion tutorial](https://wiki.hiwonder.com/projects/MasterPi/en/latest/docs/6.motion_control_course.html):
  SDK command range and50 example; **no numeric measured minimum**. Do not infer
  wheel PWM deadband from its mm/s API description.
- [Physical reference in this repository](../../scripts/red_block/physical_state_machine_reference.py#L266):
  recorded physical observation <=30 stationary,35 normal; minimum fine turn100ms.
  [v7 provenance](../2026-10-06-drive-friction/README.md) and
  [v7 input relay](../../sim/masterpi_drive_friction_v7.py) use this observation's
  bracket32.5. Installed motor/voltage/load-dependent deadband remains uncalibrated.
- [Hutchinson/Hager/Corke1996 visual servo tutorial](https://faculty.cc.gatech.edu/~seth/ResPages/pdfs/HutHagCor96.pdf):
  image-feedback control, calibration and convergence/stability limitations;
  use actual grasp task region instead of assuming arbitrary precise pose alignment.
- [Liberzon2009, Nonlinear control with limited information](https://liberzon.csl.illinois.edu/research/legacy.pdf):
  quantization/time-delay errors and practical stability. Our full-width>=2×step
  condition above is a stated conservative design bound, not a quotation from it.
- [Johns/Leutenegger/Davison2016, Grasp Function under Gripper Pose Uncertainty](https://arxiv.org/abs/1608.02239):
  choose a region of good grasp outcomes under pose uncertainty instead of a brittle
  isolated optimum. We measure a fixed-motion grid only; no learned grasp network
  or GT online grasp selection is added.

## Results

Pending entire diagnostic batch. No new physical results claimed yet.

Local pre-execution checks: `test_s3_capture_diagnostic.py` and catalog plan subset,
6 passed; no local physics/render/replay. Central catalog matches origin/main bytes.
