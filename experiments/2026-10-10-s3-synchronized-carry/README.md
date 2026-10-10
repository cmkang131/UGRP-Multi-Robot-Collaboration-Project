# s3fix17: synchronized loaded pulses and jointly feasible pan (v164)

## Preregistration — before new physical results

Parent v162 source ad844d13, records222e2327. Host=oracle-x86/OSMesa only,
LP_NUM_THREADS4/OMP1, all ten cases simultaneous, max10, dev_light,60SIM.
Pair c0–c5 and cyan c0/c3/c4/c5; seeds14201–14206 frozen in `batch-plan.json`.
No within-batch retuning/rerun; all are DEV regressions in viewed conditions.
All new toggles default off; registered run enables `synchronized_pulses_v1`
and `joint_pan_v1` plus v162 abc options. Old workflow catalog bytes unchanged.
No weld, dock prior, runtime GT/force/contact input, or camera change.
Heading on for solo/approach; closed-beam coupled translation/crab exception.
ENOSPC or execution exceptions=HOST_ERROR and preserved separately.

## Hypothesis and smallest change

v162 both carry clocks/commands matched, but the obsolete continuous schedule
issued ±0.043618/150ms versus input start threshold0.325. The V104 pair gain
profile also belongs to a different plant; merely restoring its inverse is not
adequate. Use existing calibrated **loaded** S2 finite primitives instead:
axial ±0.35/100ms at200ms period; crab ±0.65/650ms at800ms period.
Each endpoint derives mirrored local signs from its fixed role and the same
static object route; one shared consumed carry GO establishes the clock.
The smaller of paired calibrated response magnitudes sets the same pulse count
at both ends, ceil(distance/step). No per-end pose correction or yaw turn.
100ms loaded forward response is12.9387mm; first static leg151.8mm therefore
12pulses/155.265mm nominal. This is transferred calibration, not a measurement
of S3 two-gripper transport. Real grasp/contact/tilt/drop guards and GO kept.
The finite primitive port capability is explicitly versioned; old ports remain
unchanged off. No feedback of evaluated dynamics to the controller.

c3 pan1672 minimizes dy separately but yaw0.112553 exceeds0.112rad.
Enumerate integer4µs pan candidates1300–1700 and require simultaneous original
bounds **dx18mm/dy3mm around−6mm/yaw0.112rad** and reachable original IK.
A feasible candidate wins before per-axis centring; best normalised maximum
residual selects among feasible candidates. Legacy/cyan plan retained when
already ready or no jointly feasible pan. No acceptance-width change.

## Outcomes fixed before results

Joint and per-robot n/N alignment / sustained both-finger grasp>=.20s /
contact-supported lift z>.06m / carry>=20mm, separately **target distance**.
Pair target=first static route leg151.8mm; count target-distance success only
when lifted/contact-supported path excursion>=151.8mm. Also report endpoint
error to the static leg endpoint at carry completion, tolerance20mm, evaluation
only. Cyan report>=20mm and fixed100mm probe-distance outcome, not B delivery.
Record robot/cargo max tilt and actual physical tilt/drop abort counts,
contact force N, wheel rotation versus chassis displacement (slip evidence),
paired pulse start/direction/amplitude equality and one-sided waits.
No controller state entry is a physical-success receipt.

First all code/tests and this plan are committed and pushed. Optional one5SIM
pathcheck only; after ready send unchanged entire10case batch once.
Raw under outputs/s3fix17-batch-r1/cohort/*/raw, source receipt full committedSHA.
Commands from plan:
`python -m scripts.run_s3_synchronized_carry --expected-source-sha SHA --output outputs/NAME/raw --case CASE --condition CONDITION --coarse-fine stopped_base_arm_v1 --refinements abc_v1 --carry synchronized_pulses_v1 --pan joint_pan_v1 --execute`.
Batch:
`python -m scripts.run_s3_synchronized_carry_cohort --expected-source-sha SHA --output outputs/s3fix17-batch-r1/cohort --execute`.

## References and applicability

- [Yufka & Ozkan2015, formation-based transport](https://journals.sagepub.com/doi/10.5772/60972): an object virtual leader, local-frame follower commands and synchronized communication. We use its common trajectory/clock principle for straight cardinal legs; do not claim its pose-feedback controller or stability theorem applies to our uncertain camera estimates.
- [Bechlioulis & Kyriakopoulos2018, implicit leader–follower transport](https://www.frontiersin.org/journals/robotics-and-ai/articles/10.3389/frobt.2018.00090/full): adaptive/compliant coordination requires force/torque and motion measurements. These measurements are unavailable to this controller; force-based impedance is therefore not implemented or simulated by feeding evaluation truth.
- [Mohan et al.2023, collaborative leader follower](https://arxiv.org/abs/2305.01614): coordinated end-effector references and force control for two mobile manipulators. Here existing positional servo compliance is retained; synchronized command-only translation is the minimal supported part.
- [Hutchinson/Hager/Corke1996, visual servo](https://faculty.cc.gatech.edu/~seth/ResPages/pdfs/HutHagCor96.pdf): look-and-move/fresh observations; discrete actuator search remains inside calibrated grasp constraints.
- Existing measured response `configs/s2_v133_full_template.json`, real35/100 primitive contract, and v7 input relay `sim/masterpi_drive_friction_v7.py` are calibration/plant sources, not public evidence of installed hardware response.

Local pre-execution validation:22 relevant tests passed across3 changed/dependent modules; catalog dry planning passed. Tests include c3 fixed-bounds pan selection, fresh settled frames, mirrored axial/crab clocks, actual apply/expiry on motor stubs, and outer pan/heading regressions. No Mac physics. Maximum bundle ID across main and11 open heads163; v164/workflow7.57.0 reserved.

## Previous v162 raw diagnosis (0 physics steps, Oracle x86)

|case|carry-only beam excursion mm|r1/r2 wheel rim path mm|r1/r2 chassis path mm|both-finger contacts per robot|matched commands / one-side wait|
|---|---:|---:|---:|---|---|
|s3fix16-pair-c0-r1|0.582|0.531/1.147|0.539/1.041|201/201 each|94/94,0|
|s3fix16-pair-c1-r1|0.495|0.853/1.747|0.823/1.675|201/201 each|94/94,0|
|s3fix16-pair-c2-r1|4.203|7.876/1.882|7.983/1.952|201/201 each|94/94,0|
|s3fix16-pair-c4-r1|0.109|0.346/0.260|0.308/0.212|201/201 each|94/94,0|
|s3fix16-pair-c5-r1|0.266|0.460/0.841|0.416/0.663|201/201 each|94/94,0|

Every case:59 neutral+35 matched nonzero ticks, mirrored ±0.043618/150ms, no one-sided wait. Wheel/chassis path proxies are both sub-mm to8mm; no evidence of substantial powered wheel spin/slip. This carry-only window differs from the older4–8mm excursion over all lifted samples after carry entry (includes refix/lowering). Both fingers contact the lifted beam in201/201 samples per robot. The v7 relay generates0 source motor torque for input0.043618 after the neutral reset; this is a command-side model fact, not a measured force. **Exact contact forces were not recorded in v162** (no qvel/ctrl/constraint forces): not reconstructable from qpos alone. New eval-only force recording addresses that evidence gap; controller receives none. c3 never entered carry. [Full numerical audit](previous-carry-diagnosis.json).

## r1 completed, integration bug / r2 preregistration BEFORE r2 physics

r1 source03029adb, all ten finished before inspecting/tuning. Raw scored
alignment/grasp/lift10/10, carry/target4/10(cyan4/4), **HOST_ERROR6/10(pair)**.
No pair pulse reached the motor: the first carry tick tried to drive before the
peer's carry enum publication. Example c0: both consumed `carry_go_0`29.1;
benign heartbeat repeated it29.15; first r1 pulse29.2; the unchanged inner
validator requires the latest grant stamp==29.1, and rejects29.15. This error
was hidden by v162's six-second neutral prefix; direct apply test had not tested
loaded authorization through both outer publisher ticks. Raw/failures preserved.

Small **v165 / workflow7.58.0** correction: first pulse begins **GO+0.20s**,
allowing two normal100ms controller ticks to publish live carry status at both
ends. No validator relaxation or invented GO, peer pose, pulse size, gain,
threshold, seed, target criterion, or number of pulses changes. Regression uses
actual M2 outer publisher/carry ticks, loaded command-state fixture, motor stub
apply/expiry, then live peer abort rejection. Initial bad repeated-GO stamp is
explicitly rejected; motion begins only after both carry enum publications.

A NEW frozen ten-case round `batch-plan-r2.json` is submitted simultaneously,
same conditions/flags/seeds/caps. r1 and r2 denominators are kept separate;
r1 failures cannot be discarded or relabelled. No per-case retry/adaptation.
Optional pathcheck was already performed in r1 (5SIM, HOST_ERROR0), no extra
single physics case is added. r2 uses `scripts.run_s3_synchronized_start` and
`python -m scripts.run_s3_synchronized_start_cohort --expected-source-sha SHA --output outputs/s3fix17-batch-r2/cohort --execute`.
Results of r2 are pending at this registration; same original outcomes.

R2 preflight:6 synchronized carry regressions passed (23 unique relevant tests including prior17 unchanged regressions); catalog dry plan verified forv164, v165 follows same adapter. v165 is next after main/open heads maximum164. r1 score source719c9744 (documentation-only descendant of03029adb) and [all10 results](results-r1.json) are preserved. No new physics pathcheck.
