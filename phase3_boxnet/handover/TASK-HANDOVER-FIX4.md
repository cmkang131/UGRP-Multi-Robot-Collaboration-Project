# TASK-HANDOVER-FIX4: the gate ran 12 trials and failed 3 / 12; diagnose from the records, fix what is ours (2026-11-25)

Context: `TASK-HANDOVER-GATE.md`, `-CLOUD.md`, `-FIX2.md`, `-FIX3.md` are done (`REPORT-HANDOVER-GATE.md`,
`REPORT-HANDOVER-CLOUD.md`). Same hard limits as those tasks (work only under `handover/`, `cloudrun/handover/`, and
the three executor hook files on the local branch `phase3/handover-cloud`; nothing under `link/`, phase-2 folders;
no network, NO cloud commands, no model calls; commits local only, no push). The main session runs the cloud.

## Result to explain (cohort `cloudrun/runs/handover-fix3-20261125c`, image of FIX3, all 12 trials fetched)
`chain.log` (trial 1) and `chain-remaining.log` (trials 2-12, score lines at the end). 3 / 12 successes, gate FAIL.

| trials | colour | outcome |
| --- | --- | --- |
| 2, 3, 5, 8, 10, 11 | blue (all six blue trials) | `donor_pick` at sim 9.90 s: `approach_end` with `reason: not_found`, `selected: null` ("own-camera approach could not hand off a selected box to ACT") |
| 1, 7, 12 | red | SUCCESS (grasp retries: donor 1 + receiver 1; none; receiver 1) |
| 4 | red | `release`, sim 43.3 s: "box was no longer held at the release station" |
| 6 | red | `sign_seen`, sim 117.6 s: "destination card was not localized from the receiver's own RGB" |
| 9 | red | `receiver_pick`, sim 196.0 s: "both grasp attempts failed" |

Each trial folder has `events.jsonl`, `driver.log`, `chassis.csv`, `scene.xml`, `map.json`, the step pictures and
`scratch/`. `handover/scenes/trials.csv` has the layouts.

## F1. Blue is never found (six identical failures; do this first)
Find the cause from the records and the code, not by guessing: compare the blue box of the hand-over scene (its
geometry / material / rgba / name in `trials/trial-02/scene.xml` and in `exec/sim/handover_scene.py`) with a blue box
that the frozen executor DID find and carry in an archived phase-3 or phase-2 MuJoCo run (name the run and file), and
with what the own-camera approach looks for (colour thresholds, class names, the "selected box" filter by colour or
by order). State the exact mismatch with file and line. Fix it in OUR scene / hooks if the mismatch is ours. If the
frozen perception itself cannot see this blue at this distance or pose, say so with numbers (pixel size of the box in
the donor's first frames, detector score) and propose the smallest change of the trial layout that stays within what
the real robot would see. Add an offline regression test that renders the donor's first own-camera frame for one blue
and one red trial and asserts that the approach selects the box (if no local environment can render, say so and add
the check to `check_image.py` so that the image build fails when a blue box is not selectable; FIX3 did the same for
the centre card).

## F2. The three red failures (one each): say what happened, with evidence
- Trial 4 (release): where was the box lost (time, pose from `events.jsonl` / `chassis.csv`, finger forces), during
  the carry or at the station? Was it a grasp that never closed properly (compare the grasp event with trials 1, 7,
  12)? Is the hold check before departure missing or too weak?
- Trial 6 (sign_seen): the receiver had the box; where was it and what did its own camera see when it scanned for the
  card (range, bearing, was the card in the field of view, was the carried box occluding it)? Compare with the scans of
  trials 1, 7, 12.
- Trial 9 (receiver_pick): where was the box left by the donor (offset and yaw from the mark) and how did the two
  receiver grasps fail (alignment values, finger forces)? Is the released pose within what the grasp policy was trained
  on? Compare with the released poses of trials 1, 7, 12 and with the archived grasp statistics (R16: 19 of 82
  grasps failed in archived runs).
For each: classify as (a) our harness / layout (fix it), (b) a known rate of the frozen skills (give the rate from the
archive and from these 12 trials), (c) unknown. Do not tune until it passes; a fix must have a stated cause.

## F3. What the gate should be, given the rates
With the measured per-stage rates (donor grasp, carry, receiver grasp, sign scan), compute what success rate a
hand-over trial can be expected to reach after the fixes of F1 and F2(a), and say honestly whether 10 / 12 is
reachable with the frozen skills. If not, list the smallest changes that would raise it (for example one more grasp
attempt, a scan sweep before giving up), each with its expected effect and its cost, and mark which of them would
also be possible on the real robots. Do not implement the (b)-type changes; list them for the user.

## F4. Tests, image, report
- Rerun the three suites (hand-over tests, cloud wrapper, dispatcher). Stage the new image context; the build must
  check blue selectability (F1).
- Append "FIX4" to `REPORT-HANDOVER-GATE.md`: the cause of each failure with file / line / numbers, what was changed,
  the expected rate (F3), the exact commands for the main session for a NEW cohort (build, deploy, smoke with ONE BLUE
  trial first, then the remaining), test results, and "확인 안 됨".
Last step: create `review/ASTRA-HANDOVER-FIX4.done`.
