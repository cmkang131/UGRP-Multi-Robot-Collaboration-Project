# TASK-HANDOVER-FIX2: the first physical trial stopped at "donor_clear" (2026-11-25)

Context: `TASK-HANDOVER-GATE.md`, `TASK-HANDOVER-CLOUD.md` and FIX1 are done. The main session built the image and ran
trial 1 on Cloud Run. Records: `cloudrun/runs/handover-20261125a/trials/trial-01/` (`events.jsonl`, `chassis.csv`,
`driver.log`, `run.json`, the JPEG frames, `scene.xml`). What happened:
- donor r1: first grasp missed, second grasp lifted; it carried the box to the door and released it at
  (0.002, -0.007) m from the mark, yaw about -0.012 rad, box resting (events 9 to 11). The donor part works.
- then `failure: stage donor_clear, reason "ceiling camera lost r1's card"` at 132.6 simulated seconds. The last
  chassis samples put r1 at about (-0.824, 0.006): it had backed almost to the first clearance point (-0.85, 0) and
  had not yet moved sideways to the parking point. The receiver never got its turn.
- 132.6 simulated seconds took 378 wall seconds on the 2 vCPU task.

Same hard limits as before (work only under `20261123-phase3/`, new behaviour only in the opt-in hand-over path, no
network, no cloud command, no LLM call, phase-2 folders read-only, existing files of other modes byte for byte,
local commit on the existing local branch `phase3/handover-cloud` in `exec-repo/` only, no push).

Do:
1. Find out from the records and the code WHY the ceiling camera lost r1's top card at that moment (arm posture
   covering the card after the release, the card leaving the camera frame, the detector's size or angle limits, a
   single dropped frame treated as fatal, ...). Say what the evidence is; if the records cannot decide between two
   causes, say so and make the fix cover both.
2. Fix it in the hand-over policy only: for example bring the arm to the travel posture before backing, tolerate a
   bounded number of missed overhead frames by holding still and re-detecting before declaring a failure, and record
   every lost-and-recovered interval as an event. A real persistent loss must still end the trial with this stage.
   Do not loosen the room-limit checks or the scoring criteria.
3. Look ahead for the same class of problem on the receiver's side (its approach to the mark, the lift, the drive to
   the sign and the set-down) and in the other three transfer directions and the rotated wall, and harden those in
   the same way where the code shows the same pattern. Do not change anything that the first trial showed working.
4. Tests (constructed observations: a short loss recovers, a long loss fails, the event records), all earlier suites
   (`handover/tests`, `cloudrun/handover/test_handover_cloud.py`, dispatcher), staged-file list and hashes updated so
   that `python3 -B cloudrun/handover/ops.py build <new cohort dir>` builds the fixed code. Append "FIX2" to
   `REPORT-HANDOVER-GATE.md`: cause, change, the commands for the main session (a NEW cohort directory, build,
   deploy, smoke of trial 1, then the remaining eleven), and "확인 안 됨".
Last step: create `review/ASTRA-HANDOVER-FIX2.done`.
