# TASK-HANDOVER-FIX3: the FIX2 image build fails in `check_image.py` (2026-11-25)

Context: FIX2 is done offline (62 tests). The main session built the FIX2 image
(`python3 -B cloudrun/handover/ops.py build cloudrun/runs/handover-fix2-20261125b`, Cloud Build
<record-id>). The build FAILED at Dockerfile step 10, the in-image check you added in FIX2:

```
File "/opt/ugrp/check_image.py", line 70, in main
    raise ValueError(f"magnified centre-card fixture decoded to {pose}")
ValueError: magnified centre-card fixture decoded to (0.039101760684286425, 0.00015584297930056556, -0.04164257909858842)
```

All earlier Dockerfile steps passed. So inside the real image (its OpenCV build, the real calibration and reader) the
12 px marker fixture IS decoded through the magnified path, but the pose it returns is about 0.039 m in x and
-0.042 rad in yaw away from what the check expects. Note your own FIX2 analysis: the top card is rear-mounted and the
card-to-chassis offset is about 8.3 px at 201.3 px/m, i.e. about 0.041 m.

Same hard limits as FIX2 (work only under `20261123-phase3/`, opt-in hand-over path only, no network, no cloud
command, no LLM call, local commit on `phase3/handover-cloud` in `exec-repo/` only, no push, phase-2 folders
read-only).

Do:
1. Decide from the code whether the image check's EXPECTED pose or tolerance is wrong (for example it ignores the
   card-to-chassis offset the calibrated reader applies, or compares with a tolerance tighter than one pixel at this
   scale) or whether the magnified decoding path maps coordinates wrongly (which would also be wrong in the trial).
   Show the arithmetic. If the decoder is wrong, fix the decoder; if the check is wrong, fix the check. Do not simply
   widen a tolerance without a derivation.
2. Make the offline tests cover exactly this: the same fixture, the same reader configuration as in the image, the
   expected pose with the card offset, native path and magnified path giving the same chassis pose within a stated
   pixel-derived tolerance. If the offline environment cannot run the real decoder (no OpenCV here), say so and make
   the in-image check print the native-path and magnified-path poses and the tolerance before asserting, so that a
   failure can be read from the build log.
3. Keep the build check meaningful (it must still fail if the magnified path is broken).
4. Rerun all suites (`handover/tests`, `cloudrun/handover/test_handover_cloud.py`, dispatcher), update staged file
   list and hashes, append "FIX3" to `REPORT-HANDOVER-GATE.md` with cause, change and the commands for the main
   session (a NEW cohort directory), and "확인 안 됨".
Last step: create `review/ASTRA-HANDOVER-FIX3.done`.
