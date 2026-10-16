# R2 full headless pre-check: clock failure and narrow fix

The initial `07c497410fb469b10f9899a1df9a1c742ac097ef` headless run stopped at
610.7000000099933 recorded SIM seconds with `inexact SIM advance`.
Raw: `/Users/changmin/projects/ugrp/outputs/v92-headless-check-20261003T071802Z/raw`.
It is a failed/incomplete exploratory pre-check, not a collection. The completed
motion prefix alone has 288/288 supported cells (minimum 137 complete windows);
this does not substitute for a completed full schedule.

Repeated `data.time += .00025` eventually differs from `start + tick*.05` by
more than the existing `1e-8` advance tolerance. The old loop then takes 199
rather than 200 substeps in a tick and fails its existing `1e-7` completion
check. A deterministic clock-only regression reproduces this at ~611 s.

The v92 runner now precomputes the float targets by the same repeated addition,
with exactly 200 substeps per .05 s tick and 2,880,000 substeps for 720 s. The
headless probe shares that helper. Neither data.time nor physics state is
rewritten. The final float deadline differs from nominal time only by recorded
roundoff below the existing completion tolerance; the unchanged world cap
rejects even one additional .00025 s step. No guard threshold, timestep,
contact, actuator, B″, or command-schedule byte changes.

The full headless path also calls the existing non-rendering
`_sync_real_camera_mount` for both cameras on every .2 s capture boundary. This
retains production capture's `mj_forward` side effects while constructing no
renderer and producing no RGB. Its own summary and auditor explicitly reject
use as a collection or training artifact. A new full run on the committed fix
is required before final support can be reported.

Targeted verification: **6 passed, 25 deselected in 33.56s** (clock reproducer,
unchanged cap rejection, two-camera sync, full fake schedule, interlock/ENOSPC
retention and owned SIM slot).
