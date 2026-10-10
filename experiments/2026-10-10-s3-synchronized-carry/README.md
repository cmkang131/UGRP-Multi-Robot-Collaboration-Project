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
