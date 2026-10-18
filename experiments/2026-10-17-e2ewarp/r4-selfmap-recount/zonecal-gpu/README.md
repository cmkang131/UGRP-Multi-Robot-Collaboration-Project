# GPU zone-B appearance calibration capture

**GPU appearance calibration, not research result.** No LLM, no control,
no physics stepping; experimenter-configured static poses of the
recorded R4 scene rendered with the MJWarp native renderer, same camera
and raw-fisheye remap/JPEG settings as the recorded own frames. Zone
rectangle (4.3, 4.9, -2.8, -1.4) and pose/label fields are eval-only. Not pooled
with any research result.

## Evidence notes

- Official capture: gcp6 `/home/ugrp/ugrp-sim/runs/e2ewarp-zonecal-gpu-v2`
  (VM TERMINATED; disk preserved), Mac `/tmp/e2ewarp-zonecal-gpu-v2`.
  A first capture (`...-zonecal-gpu`) had a camera-aim bug (wrong wrist-camera
  yaw) and is **superseded / not used**.
- `capture-stack.json` / `stack-check.json` were produced as the pre-run stack
  check: the repo `check_current_stack.py` on the R4 queue reports
  `ok=false / admission=blocked` because of pre-existing R4 stack deviations.
  This capture is a render-only calibration (**not a queue research run**), so
  the deviation is recorded here and no admission is claimed; the capture does
  not read or change the R4 physics/control stack.
- Labels (`zone rectangle`, base/actual camera pose, distance) are eval-only;
  the detector never receives them. Not pooled with any research result.

## Reproduce

The capture script is `scripts/e2ewarp_zonecal_capture.py` (run on gcp6 with the
warp venv; the R4 scene XML plus its asset dir; no physics stepping):

```
python3 scripts/e2ewarp_zonecal_capture.py \
  --scene /tmp/zonecal/scene.xml \
  --out /home/ugrp/ugrp-sim/runs/e2ewarp-zonecal-gpu-v2 \
  --source-root /home/ugrp/ugrp-sim/src/e2ewarp-r4-src
```

Threshold fitting: `scripts/e2ewarp_zonecal_analyze.py` (Mac, non-physics) with
the capture dir and the recorded R4 raw; it writes `zone-appearance-calib.json`.
