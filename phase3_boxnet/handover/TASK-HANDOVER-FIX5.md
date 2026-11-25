# TASK-HANDOVER-FIX5: why do red and blue differ? (2026-11-25)

Context: `TASK-HANDOVER-FIX4.md` is done (`REPORT-HANDOVER-GATE.md`, section FIX4). Same hard limits (work only under
`handover/`, `cloudrun/handover/`, the three executor hook files on the local branch `phase3/handover-cloud`; nothing
under `link/`, phase-2 folders; no network, NO cloud commands, no model calls; commits local only, no push; archived
runs are read-only).

The user asked (2026-11-25 11:24 KST, verbatim): "아니 대체 왜 빨강이랑 파랑이 다른 거야".

## What was measured (cohort `cloudrun/runs/handover-fix4-Zc6HAKV9`, FIX4 image, 12 trials)
9 of 12 complete. Blue 6 of 6 (trials 2, 3, 5, 8, 10, 11); red 3 of 6 (1, 7, 12 complete; 4 lost the box before the
release station; 6 lost it before set-down; 9 missed both receiver grasps). Grasp attempts from `events.jsonl`
(`grasp_attempt.outcome`): red 15 attempts = 10 `lift` + 5 `miss` (trial 1 donor and receiver first attempts, trial 9
receiver twice, trial 12 receiver first attempt), and 2 of the lifted red boxes were lost later; blue 12 attempts =
12 `lift`, none lost. Every one of these grasps followed an approach that ended `arrived` with an `aligned_*` label.
The box is the same body in both colours (34 x 40 x 32 mm, 30 g; FIX4 report); only the paint differs. The layouts
differ from trial to trial (`handover/scenes/trials.csv`), so colour and layout are confounded.

## A1. Archive count by colour (read-only; do this first)
From the 12 archived three-robot runs with detailed logs that R16 used
(`cloudrun/runs/*/outroot/*S10*/`, the "19 of 82 box selections produced grasp_failed" count; reproduce that count
first and say exactly which records it comes from), give per colour: box selections, grasp attempts, lifts, misses,
boxes lost after a lift, and where the logs allow it the alignment label and the finger forces at the end of the lift.
Also give the same split for the grasp policy's own evaluation if its records keep the colour
(`../20261114-release/RELEASE-NOTES.md` and what it points to: "19/20 development and 12/12 held-out"), and the
colour split of the 140 training demonstrations. Say plainly whether the archive shows a red / blue gap, with counts.

## A2. What differs between a red miss and a blue lift in the hand-over cohort
For the 5 red misses and the 2 red losses, compare with the lifts on the same robot role: the approach end state
(selected entry, alignment label, last measured box-to-chassis distance and yaw error), the wrist frames at the grasp
(`*-grasp-wrist.jpg`), the box pose when the fingers close (offset from the gripper centre line, yaw), finger forces
and the lift samples. Look for a systematic offset in the red cases: does the approach stop at a different distance
or lateral offset for red (the red and the cyan detector use different colour tests and may give a different
centroid or face estimate), or does the approach end the same and the learned grasp then move differently? Numbers
for every case in one table. If the difference is in OUR hooks (for example a colour-dependent threshold or offset in
`handover_policy.py`), fix it; if it is inside the frozen approach or the frozen grasp policy, do not change it:
report it.

## A3. The swapped cohort (colour and layout separated)
Add a second trial table `handover/scenes/trials-swapped.csv`: the same 12 layouts, seeds and directions with the
colour of every trial swapped (red <-> blue), selectable with one option of the trial driver and of `ops.py`
(cohort-level, recorded in the cohort's files; the default table and every existing byte stay as they are). Tests:
the swapped table differs from the original only in the colour column; the driver and the cloud wrapper pass the
table through; the scorer reports the table name. No new image is needed if the table can be passed at run time;
if a new image is needed, say why and stage it.

## A4. Report
Append "FIX5" to `REPORT-HANDOVER-GATE.md`: A1 counts, A2 table and what it shows, A3 with the exact commands for the
main session to run the swapped cohort (smoke with one trial first, then the rest, as before), the rerun of the three
test suites, and "확인 안 됨". State what each outcome of the swapped cohort would mean (failures follow the colour /
stay with the layouts / neither).
Last step: create `review/ASTRA-HANDOVER-FIX5.done`.
