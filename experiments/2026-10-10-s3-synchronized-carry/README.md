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

## r2 completed raw audit — v165 (DEV, no adoption)

Physics/evaluation source `bf1c9b6acaacefa4200786e42a971eeb94dc3943`, host=oracle-x86. All10 completed before evaluation; fixed10 conditions/seeds/criteria. The initial wrong full SHA was refused at0SIM in `s3fix17-batch-r2`, retained/excluded. Actual unchanged cohort ran in **s3fix17-batch-r2-ready**, elapsed460.79wall seconds. No third physical round or threshold retuning.

**Alignment/grasp/contact-lift/carry>=20mm/registered distance10/10** (pair6/6, cyan4/4), HOST_ERROR0. This distance receipt is not correct endpoint arrival or complete transport: pair first static endpoint<=20mm **1/6**, later lowering **LOAD_DROP guard4/6** and **FLOOR_POSE_NOT_COMMANDED2/6**. Consequently pair error-free completion0/6; no E2E claim. The two controller failures appear inside raw `DEV_STAGE_FINISHED`; final controller states must also be read, not only outer status. Cyan c0 regression retained.

|case|alignment/grasp/lift/carry/target|contact-lift carry mm|first-leg endpoint error mm|cargo max tilt deg|end or actual stop|wall/SIM s|
|---|---|---:|---:|---:|---|---|
|s3fix17-pair-c0-r2|1/1 each|228.096|42.486|1.420|LOAD_DROP:beam_1|334.590/52.30|
|s3fix17-pair-c1-r2|1/1 each|228.438|48.593|0.608|LOAD_DROP:beam_1|334.831/51.80|
|s3fix17-pair-c2-r2|1/1 each|185.277|16.483|0.581|FLOOR_POSE_NOT_COMMANDED|343.878/54.55|
|s3fix17-pair-c3-r2|1/1 each|210.757|37.276|0.512|FLOOR_POSE_NOT_COMMANDED|344.611/55.05|
|s3fix17-pair-c4-r2|1/1 each|225.548|50.366|1.176|LOAD_DROP:beam_1|327.234/51.25|
|s3fix17-pair-c5-r2|1/1 each|228.420|53.987|0.828|LOAD_DROP:beam_1|335.087/52.80|
|s3fix17-cyan-c0-r2|1/1 each|631.580|—|24.008|60SIM horizon, carry|407.039/60.00|
|s3fix17-cyan-c3-r2|1/1 each|274.728|—|23.923|60SIM horizon, carry|410.190/60.00|
|s3fix17-cyan-c4-r2|1/1 each|575.222|—|24.227|60SIM horizon, carry|430.047/60.00|
|s3fix17-cyan-c5-r2|1/1 each|662.025|—|24.075|60SIM horizon, carry|430.667/60.00|

Cargo tilt: pair max0.51–1.42deg, cyan23.92–24.23deg; robot-tilt abort0 and LOAD_DROP guard abort4. The cargo angle is reported separately from the unchanged robot tilt guard. All pair lowering failures occur after first-carry completion and refix_decide; no drop occurs inside the first carry window.

|pair|issued nonzero ticks r1/r2 (planned12)|matching ticks / unilateral wait|first-carry excursion mm|rim/chassis path mm r1; r2|mean normal squeeze N r1/r2|mean net resultant N r1/r2|
|---|---|---|---:|---|---|---|
|s3fix17-pair-c0-r2|17/17|18/18, 0|222.887|227.805/227.502; 226.839/221.760|11.130/11.476|1.511/1.489|
|s3fix17-pair-c1-r2|17/17|18/18, 0|223.939|227.750/227.470; 227.628/222.056|11.434/11.695|1.503/1.492|
|s3fix17-pair-c2-r2|14/14|16/16, 0|185.277|187.058/187.005; 189.768/184.352|11.343/11.466|1.483/1.496|
|s3fix17-pair-c3-r2|16/16|18/18, 0|210.757|212.319/212.662; 215.022/209.919|11.280/11.488|1.498/1.483|
|s3fix17-pair-c4-r2|17/17|18/18, 0|225.548|229.085/229.338; 229.070/224.660|10.987/11.006|1.506/1.490|
|s3fix17-pair-c5-r2|17/17|19/19, 0|227.621|230.357/230.653; 229.485/225.246|11.238/11.364|1.454/1.539|

Every pair: mirrored ±0.35/100ms, start skew0s, unilateral waiting0, both fingers57/57 samples **each robot** in first carry. Wheel rim/chassis path187–231mm versus184–231mm supports powered translation rather than the old subthreshold stall; proxy is not exact contact-point slip. Exact contact force is new evaluation-only evidence (squeeze and net resultant are different quantities).

**Remaining pulse-clock defect:** nominal12 intervals yielded14–17 issued nonzero actions per robot. For c0, boundary29.4 was issued after29.3, and more adjacent100ms actions followed: legacy half-open `start <= now < end` window uses unrounded float boundaries (e.g.29.3+.1=29.400000000000002) against the rounded tick29.4, allowing a boundary reissue and extending drive. No per-pulse index suppresses that reissue. This is consistent with first-leg excursions185–228mm instead of nominal155.265mm and endpoint errors16–54mm. Counts/skew above are measured; isolated causal calibration remains unperformed. Do not claim the nominal12-pulse distance was physically executed. No post-result controller change in this round.

c3 fine pan failure repaired: r1/r2 alignment, grasp, lift, transport reached; stage robot turn reversals0 for all pair cases. Cyan later navigation reversals c0/c3/c4/c5=1/4/1/1, distinct from solved alignment cycles.

Run aggregate wall/SIM **3698.173317/557.75=6.631**, commands19775, model calls0; concurrent batch wall460.79s is a separate measure. Measured render 1146.561s and physics 1170.705s dominate; capture timers nested/not additive. No speed optimization or controlled benchmark claim.

Raw: `/Users/changmin/projects/ugrp/outputs/oracle-runs/s3fix17-batch-r2-ready/cohort/*/raw`; evaluation: `outputs/oracle-runs/s3fix17-eval-r2/evaluation`. Retrieved raw hashes all match; [all ten results](results-r2.json), [first-carry commands/forces/endpoint audit](pair-dynamics-r2.json), [retrieval receipt](retrieval-r2.json). Force helper performs0 physics steps and hash-checks saved source files. It never feeds controller input.

Next proposed round: offline scheduled-pulse index deduplication and complete pan-owned lowering/safe-release sweep first, then preregister a single short concurrent10-case carry→lower batch. No B-delivery or real-hardware success claim.

Lowering classification from the last evaluated samples: all4 LOAD_DROP guards fired while both fingers of **both robots still contacted the beam**, held=True, COM z49.6–50.8mm, speed7.3–24.1mm/s during commanded lower. The guard itself uses beam body origin<=35mm and closed grippers. These are confirmed guard stops, **not proven grip-loss/free-fall events**; safe set-down/height-reference contract needs separate checking. c2/c3 reached COM15.6–15.9mm with both-finger contact, then r1 failed FLOOR_POSE_NOT_COMMANDED. [Last-frame records](lowering-last-sample.json). No guard disabled or success relabelled after seeing results.

## TensorBoard / delivery

New immutable snapshots `1010-s3fix17-v164-r1`, `1010-s3fix17-v165-r2`, `1010-s3fix17-aux-v1`:25 views,565 scalar tags,20 saved-RGB4x videos. All event values match derived source JSON; native API loaded25, all20 videos hash/Range206 checked. Retrieved raw r1 24,538 files / r2 33,835 files match all artifact hashes; originals preserved. Pathcheck5SIM,0SIM wrong-SHA preflight and0-physics old-raw audit have separate views, excluded from10-case denominators.

[Native comparison dashboard](http://127.0.0.1:6006/?runFilter=%5E%281010-s3fix17-v164-r1%7C1010-s3fix17-v165-r2%7C1010-s3fix16-alignment-ownership-v1%29%2F&pinnedCards=%5B%7B%22plugin%22%3A%22scalars%22%2C%22tag%22%3A%22offline%2Falignment%22%7D%2C%7B%22plugin%22%3A%22scalars%22%2C%22tag%22%3A%22offline%2Fgrasp%22%7D%2C%7B%22plugin%22%3A%22scalars%22%2C%22tag%22%3A%22offline%2Flift%22%7D%2C%7B%22plugin%22%3A%22scalars%22%2C%22tag%22%3A%22offline%2Fcarry%22%7D%2C%7B%22plugin%22%3A%22scalars%22%2C%22tag%22%3A%22offline%2Ftarget_distance%22%7D%2C%7B%22plugin%22%3A%22scalars%22%2C%22tag%22%3A%22offline%2Fn%22%7D%2C%7B%22plugin%22%3A%22scalars%22%2C%22tag%22%3A%22offline%2Fhost_errors%22%7D%2C%7B%22plugin%22%3A%22scalars%22%2C%22tag%22%3A%22offline%2Ftilt_aborts%22%7D%2C%7B%22plugin%22%3A%22scalars%22%2C%22tag%22%3A%22offline%2Fdrop_aborts%22%7D%2C%7B%22plugin%22%3A%22scalars%22%2C%22tag%22%3A%22result%2Fwall_s%22%7D%2C%7B%22plugin%22%3A%22scalars%22%2C%22tag%22%3A%22result%2Fcommands%22%7D%2C%7B%22plugin%22%3A%22scalars%22%2C%22tag%22%3A%22result%2Fmodel_calls%22%7D%5D&smoothing=0#timeseries), [pair c3 representative4x video](http://127.0.0.1:6007/video/52b6fbcf36661c55bd43), [HParams](http://127.0.0.1:6006/#hparams). Chrome **강** actual HParams page448,10 rows/page: v165 cases and cohort10-r2 load, case/policy/seed/source_sha columns applied; cohort wall3698.2/SIM557.75/commands19775/model0 match source. Time Series actual cohort carry4/4/10 forv162/v164r1/v165r2 and first four outcome cards checked; twelve pinned tags saved (not all simultaneously visible). Video readyState4,1920×480,13.8s. [Verification](tensorboard-verification.json). Plugin export status is not full mission success.

Operational preservation: to satisfy the remote disk guard, two own **inactive** source archives were deduplicated by same-path,size,mode,SHA-verified hard links; no raw changed/deleted and no other process stopped. [Receipt](source-cache-preservation.json). No Mac physics, CI wait or merge; PR416 remains DRAFT. Final documentation commit is separate from fixed physics source.
