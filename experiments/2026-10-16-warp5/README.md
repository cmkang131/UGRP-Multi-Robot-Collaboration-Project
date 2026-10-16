# warp5 — RUNNING / NOT_READY

reloc20 2f4f469e + warp-act e97464a3, isolated claude/warp5. gcp2 L4 shared with warp3/warp4/beamact3. No Mac physics/render/GUI, no LLM calls. Existing Gemma+50% alert prohibits LLM batches. CPU paths/results preserved and separate.

R1 static paired88 measured: CPU/MJWarp ORB FAST7 floor median107.5/53, wall2/1; boundary columns4087/2364, false columns0/0, qualified56/88 each; colour count changes62/88. RGB MAE median38.47/255. RGB pairs directly inspected (drive, B paint, box palette), not localization success.

All setup failures retained: r1 EGL library unavailable; r1b contact workspace underallocated; r1c scipy absent; r1d measured88. Image-analysis dependencies were installed in a private target directory, leaving other tasks' Python environments unchanged. Raw `/home/ugrp/ugrp-sim/runs/warp5/`.

Largest source-level visual differences: nonzero alpha is opaque in pinned MJWarp; cutoff180 lights still apply spotlight exponent. `warp5_native_visual_v1` is default off and implements native authored-alpha blend orders plus point-light semantics inside the renderer. No detector constants changed. R2 paired88 required before control admission.

Relocation lane adapters and multi-camera/multi-port batch adapter are implemented but have not run a GPU control gate. Native scene setup is explicitly separate from MJWarp rollout. E2E async/relay integration and place run-first remain in progress. No READY/teacher/student/physical success claim.
